#!/usr/bin/env python3
"""CorridorKey 2.0 daemon: job queue over the free CorridorKey2.0 inference engine.

Endpoints:
  POST /jobs           {"input": path, "hint_first_frame"?, "hint_quality"?,
                        "outputs"?, "num_frames"?, "despill"?, "exr"?,
                        "low_vram"?, "output_dir"?}
  GET  /jobs           -> all jobs with status/progress
  GET  /jobs/{id}      -> one job
  POST /jobs/{id}/cancel
  GET  /jobs/{id}/frame?kind=source|alpha|fg&t=<sec>&w=<px>  -> JPEG кадр
  GET  /jobs/{id}/result   -> метаданные + ссылки на готовые файлы
  GET  /jobs/{id}/media/{name} -> готовый файл (video, range-запросы)
  GET  /stats          -> CPU / RAM / GPU
  GET  /health
Manifest of finished jobs: <WORK>/manifest.json
"""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "CorridorKey2.0"
PY = ROOT / ".venv" / "bin" / "python"
WORK = ROOT / "renders"
UI = ROOT / "ui"
WORK.mkdir(exist_ok=True)
MANIFEST = WORK / "manifest.json"

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v")

app = FastAPI()
_jobs: dict[str, dict] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_current: str | None = None

_frames: dict[tuple, bytes] = {}
_frames_lock = threading.Lock()
_cpu_prev: tuple[float, float] | None = None

# Chromium в QtWebEngine собран без H.264, поэтому результаты перекодируются
# в WebM/VP9 (свободный кодек) — так <video> в интерфейсе реально проигрывает.
PREVIEW_H = 720
_previews: dict[tuple[str, str], dict] = {}
_preview_lock = threading.Lock()


def _save_manifest() -> None:
    done = [
        {k: j.get(k) for k in ("id", "input", "output_dir", "outputs", "finished_at", "status")}
        for j in _jobs.values()
        if j["status"] in ("done", "failed")
    ]
    MANIFEST.write_text(json.dumps(done, ensure_ascii=False, indent=1))


class JobIn(BaseModel):
    input: str
    hint_first_frame: str | None = None
    hint_quality: float = 0.95
    outputs: list[str] = ["alpha", "fg"]
    num_frames: int | None = None
    despill: float | None = None
    exr: bool = False
    low_vram: bool = False
    hann_chunk: int | None = None
    hann_stride: int | None = None
    output_dir: str | None = None


def _probe(path: str) -> dict:
    """Длительность/кадры/размер исходника (ffprobe)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=25,
        ).stdout
        data = json.loads(out or "{}")
        st = (data.get("streams") or [{}])[0]
        num, den = (st.get("r_frame_rate") or "25/1").split("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 25.0
        dur = float(st.get("duration") or data.get("format", {}).get("duration") or 0.0)
        frames = int(st.get("nb_frames") or 0) or int(round(dur * fps))
        return {"width": int(st.get("width") or 0), "height": int(st.get("height") or 0),
                "fps": round(fps, 3), "duration": round(dur, 3), "frames": frames}
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return {"width": 0, "height": 0, "fps": 25.0, "duration": 0.0, "frames": 0}


@app.post("/jobs")
def add_job(job: JobIn) -> dict:
    inp = Path(job.input).expanduser()
    if not inp.exists():
        raise HTTPException(404, f"input not found: {job.input}")
    jid = uuid.uuid4().hex[:10]
    base = WORK
    if job.output_dir:
        base = Path(job.output_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)
    outdir = base / f"{inp.stem}_{jid}"
    cmd = [str(PY), "-u", str(REPO / "infer.py"),
           "--input", str(inp),
           "--output_dir", str(outdir),
           "--outputs", *job.outputs]
    if job.hint_first_frame:
        cmd += ["--hint_first_frame", job.hint_first_frame,
                "--hint_quality", str(job.hint_quality)]
    if job.num_frames:
        cmd += ["--num_frames", str(job.num_frames)]
    if job.despill is not None:
        cmd += ["--despill_strength", str(job.despill)]
    if job.exr:
        cmd += ["--output_format", "exr"]
    if job.low_vram:
        cmd += ["--low_vram"]
    if job.hann_chunk:
        cmd += ["--hann_chunk", str(job.hann_chunk),
                "--hann_stride", str(job.hann_stride or job.hann_chunk // 2)]
    media = _probe(str(inp))
    if job.num_frames:
        media["frames"] = min(job.num_frames, media["frames"] or job.num_frames)
        media["duration"] = media["frames"] / (media["fps"] or 25.0)
    rec = {"id": jid, "input": str(inp), "output_dir": str(outdir),
           "cmd": cmd, "outputs": job.outputs, "status": "queued",
           "progress": 0.0, "log_tail": [], "created_at": time.time(),
           "finished_at": None, "hint": job.hint_first_frame,
           "media": media, "frame": 0, "exr": job.exr}
    with _lock:
        _jobs[jid] = rec
    _queue.put(jid)
    return {"id": jid, "media": media}


@app.get("/jobs")
def list_jobs() -> list[dict]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)


@app.get("/jobs/{jid}")
def get_job(jid: str) -> dict:
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    return j


@app.post("/jobs/{jid}/cancel")
def cancel_job(jid: str) -> dict:
    global _proc
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    j["cancel"] = True
    if _current == jid and _proc and _proc.poll() is None:
        _proc.terminate()
    return {"ok": True}


# ── готовые файлы и предпросмотр ─────────────────────────────────────────
def _job_dir(jid: str) -> Path:
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    return Path(j["output_dir"])


def _find_output(jid: str) -> dict[str, Path]:
    """Найти видео-результаты задачи: alpha / fg / checker / cutout."""
    base = _job_dir(jid)
    found: dict[str, Path] = {}
    if not base.is_dir():
        return found
    for p in sorted(base.iterdir()):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXT:
            continue
        low = p.name.lower()
        for kind in ("checker", "cutout", "alpha", "fg"):
            if f"_{kind}" in low and kind not in found:
                found[kind] = p
    return found


@app.delete("/jobs/{jid}")
def delete_job(jid: str) -> dict:
    """Убрать задачу из очереди и истории (файлы на диске остаются)."""
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    if j["status"] in ("running", "queued"):
        raise HTTPException(409, "stop the job first")
    with _lock:
        _jobs.pop(jid, None)
    for key in [k for k in _previews if k[0] == jid]:
        _previews.pop(key, None)
    _save_manifest()
    return {"ok": True}


@app.get("/jobs/{jid}/result")
def job_result(jid: str) -> dict:
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    files = _find_output(jid)
    media = j.get("media") or {}
    return {
        "id": jid,
        "status": j["status"],
        "fps": media.get("fps") or 25.0,
        "frames": media.get("frames") or 0,
        "duration": media.get("duration") or 0.0,
        "width": media.get("width") or 0,
        "height": media.get("height") or 0,
        "output_dir": j["output_dir"],
        "files": {k: f"/jobs/{jid}/media/{v.name}" for k, v in files.items()},
        "exr": bool(j.get("exr")),
    }


@app.get("/jobs/{jid}/frame")
def job_frame(jid: str, kind: str = "source", t: float = 0.0, w: int = 960) -> Response:
    """JPEG-кадр из исходника или из готового результата (для живого превью)."""
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    path: Path | None
    if kind == "source":
        path = Path(j["input"])
    else:
        path = _find_output(jid).get(kind)
    if not path or not path.is_file():
        raise HTTPException(404, f"no {kind} media")

    w = max(160, min(int(w), 1920))
    key = (jid, kind, round(float(t), 2), w)
    with _frames_lock:
        cached = _frames.get(key)
    if cached:
        return Response(content=cached, media_type="image/jpeg")

    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, float(t)):.3f}", "-i", str(path),
           "-frames:v", "1", "-vf", f"scale={w}:-2:flags=bicubic",
           "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"]
    try:
        data = subprocess.run(cmd, capture_output=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        data = b""
    if not data:
        raise HTTPException(404, "frame not ready")
    with _frames_lock:
        if len(_frames) > 240:
            _frames.clear()
        _frames[key] = data
    return Response(content=data, media_type="image/jpeg")


# ── WebM-предпросмотр (H.264 в QtWebEngine нет) ──────────────────────────
def _preview_source(jid: str, kind: str) -> Path | None:
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    if kind == "source":
        p = Path(j["input"])
        return p if p.is_file() else None
    return _find_output(jid).get(kind)


def _preview_path(jid: str, kind: str) -> Path:
    base = _job_dir(jid)
    try:
        base.mkdir(parents=True, exist_ok=True)
        if os.access(base, os.W_OK):
            return base / f"_preview_{kind}.webm"
    except OSError:
        pass
    cache = WORK / "_previews"
    cache.mkdir(exist_ok=True)
    return cache / f"{jid}_{kind}.webm"


def _encode_preview(jid: str, kind: str, src: Path, dst: Path, key: tuple) -> None:
    st = _previews[key]
    dur = float((_jobs.get(jid, {}).get("media") or {}).get("duration") or 0)
    cmd = ["ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-i", str(src),
           "-vf", f"scale={PREVIEW_H}:-2:flags=bicubic",
           "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
           "-row-mt", "1", "-b:v", "0", "-crf", "40"]
    cmd += ["-c:a", "libopus", "-b:a", "96k"] if kind == "source" else ["-an"]
    cmd.append(str(dst))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True)
        for line in proc.stdout:  # type: ignore[union-attr]
            if line.startswith("out_time_us=") and dur:
                try:
                    done = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                st["progress"] = max(0, min(99, int(100 * done / dur)))
        proc.wait()
        st["status"] = "ready" if proc.returncode == 0 and dst.is_file() else "error"
        st["progress"] = 100 if st["status"] == "ready" else st.get("progress", 0)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        st["status"] = "error"
        st["error"] = str(exc)


def _ensure_preview(jid: str, kind: str) -> dict:
    if kind not in ("alpha", "fg", "source"):
        raise HTTPException(400, "kind must be alpha, fg or source")
    key = (jid, kind)
    with _preview_lock:
        st = _previews.get(key)
        if st and st["status"] in ("encoding", "ready"):
            if st["status"] == "ready" and not Path(st["path"]).is_file():
                st["status"] = "pending"
            else:
                return st
        src = _preview_source(jid, kind)
        if not src:
            raise HTTPException(404, f"no {kind} media yet")
        dst = _preview_path(jid, kind)
        try:
            fresh = dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime
        except OSError:
            fresh = False
        if fresh:
            st = {"status": "ready", "progress": 100, "path": str(dst)}
            _previews[key] = st
            return st
        st = {"status": "encoding", "progress": 0, "path": str(dst)}
        _previews[key] = st
        threading.Thread(target=_encode_preview, args=(jid, kind, src, dst, key),
                         daemon=True).start()
        return st


@app.get("/jobs/{jid}/preview/status")
def preview_status(jid: str, kind: str = "fg") -> dict:
    st = _ensure_preview(jid, kind)
    return {k: v for k, v in st.items() if k != "path"}


@app.get("/jobs/{jid}/preview")
def preview_file(jid: str, kind: str = "fg"):
    st = _ensure_preview(jid, kind)
    if st["status"] != "ready":
        return JSONResponse(st, status_code=202)
    path = Path(st["path"])
    if not path.is_file():
        raise HTTPException(404, "preview is gone")
    return FileResponse(path, media_type="video/webm")


@app.get("/jobs/{jid}/source")
def job_source(jid: str) -> FileResponse:
    """Исходный клип для плеера (kind=source)."""
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "no such job")
    path = Path(j["input"])
    if not path.is_file():
        raise HTTPException(404, "source is gone")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "video/mp4")


@app.get("/jobs/{jid}/media/{name:path}")
def job_media(jid: str, name: str) -> FileResponse:
    base = _job_dir(jid).resolve()
    path = (base / name).resolve()
    if not str(path).startswith(str(base)) or not path.is_file():
        raise HTTPException(404, "no such file")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime)  # поддержка Range для <video>


# ── ресурсы машины ───────────────────────────────────────────────────────
def _cpu_percent() -> float:
    global _cpu_prev
    try:
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        nums = [float(x) for x in fields]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)
        total = sum(nums)
    except (OSError, ValueError, IndexError):
        return 0.0
    with _lock:
        prev, _cpu_prev = _cpu_prev, (idle, total)
    if not prev:
        return 0.0
    d_idle, d_total = idle - prev[0], total - prev[1]
    if d_total <= 0:
        return 0.0
    return round(100.0 * (1.0 - d_idle / d_total), 1)


def _mem() -> dict:
    info = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            if k in ("MemTotal", "MemAvailable"):
                info[k] = int(v.strip().split()[0]) // 1024  # MiB
    except (OSError, ValueError):
        return {"used": 0, "total": 0}
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    return {"used": total - avail, "total": total}


def _gpu() -> dict:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
        ).stdout.strip().splitlines()[0]
        util, used, total, temp = [x.strip() for x in out.split(",")[:4]]
        return {"util": int(util), "used": int(used), "total": int(total), "temp": int(temp)}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {"util": 0, "used": 0, "total": 0, "temp": 0}


@app.get("/stats")
def stats() -> dict:
    return {"cpu": _cpu_percent(), "ram": _mem(), "gpu": _gpu(),
            "current": _current, "queued": _queue.qsize()}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "queued": _queue.qsize(), "current": _current}


def _worker() -> None:
    global _proc, _current
    while True:
        jid = _queue.get()
        with _lock:
            j = _jobs[jid]
            j["status"] = "running"
            _current = jid
        logf = WORK / f"{jid}.log"
        Path(j["output_dir"]).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            with open(logf, "w") as lf:
                _proc = subprocess.Popen(j["cmd"], stdout=lf, stderr=subprocess.STDOUT,
                                         cwd=REPO, env=env)
                while _proc.poll() is None:
                    time.sleep(1.0)
                    tail = _tail(logf)
                    j["log_tail"] = tail[-6:]
                    j["progress"], j["frame"] = _parse_progress(tail)
                    if j.get("cancel"):
                        _proc.terminate()
                        break
            rc = _proc.returncode
            j["status"] = "cancelled" if j.get("cancel") else ("done" if rc == 0 else "failed")
            if j["status"] == "done":
                j["progress"] = 100.0
                j["frame"] = (j.get("media") or {}).get("frames") or j.get("frame") or 0
        except Exception as e:  # noqa: BLE001
            j["status"] = "failed"
            j["log_tail"] = [f"daemon error: {e}"]
        finally:
            _current = None
            j["finished_at"] = time.time()
            _save_manifest()


def _tail(path: Path, n: int = 40) -> list[str]:
    try:
        lines = path.read_text(errors="replace").splitlines()
        return lines[-n:]
    except OSError:
        return []


def _parse_progress(lines: list[str]) -> tuple[float, int]:
    """(процент, текущий кадр) из строк infer.py: «window i/N [a:b]»."""
    txt = "\n".join(lines)
    m = re.findall(r"window\s+(\d+)/(\d+)\s+\[(\d+):(\d+)\]", txt)
    if m:
        i, n, _a, b = (int(x) for x in m[-1])
        return 5 + 90 * i / max(n, 1), b
    m = re.findall(r"window\s+(\d+)/(\d+)", txt)
    if m:
        i, n = map(int, m[-1])
        return 5 + 90 * i / max(n, 1), 0
    m = re.findall(r"frame\s+(\d+)/(\d+)", txt)
    if m:
        i, n = map(int, m[-1])
        return 5 + 90 * i / max(n, 1), i
    return 0.0, 0


def _load_manifest() -> None:
    """Подхватить историю готовых работ после рестарта демона."""
    try:
        done = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError):
        return
    for item in done:
        jid = item.get("id")
        if not jid or jid in _jobs:
            continue
        logf = WORK / f"{jid}.log"
        _jobs[jid] = {
            "id": jid,
            "input": item.get("input", ""),
            "output_dir": item.get("output_dir", ""),
            "outputs": item.get("outputs", ["alpha", "fg"]),
            "status": item.get("status", "done"),
            "progress": 100.0 if item.get("status") == "done" else 0.0,
            "log_tail": _tail(logf, 6),
            "created_at": item.get("finished_at") or 0.0,
            "finished_at": item.get("finished_at"),
            "hint": None,
            "cmd": [],
            "media": _probe(item.get("input", "")) if item.get("input") else {},
            "frame": 0,
        }


def main() -> None:
    _load_manifest()
    if UI.is_dir():
        app.mount("/", StaticFiles(directory=str(UI), html=True), name="ui")
    threading.Thread(target=_worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8129, log_level="warning")


if __name__ == "__main__":
    main()
