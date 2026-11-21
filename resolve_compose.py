#!/usr/bin/env python3
"""Собрать композицию в Fusion внутри DaVinci Resolve Studio из готовой работы CorridorKey.

Что делает: берёт готовый рендер из `renders/manifest.json`, создаёт в **текущей**
композиции Fusion (страница Fusion активного клипа таймлайна) цепочку

    MediaIn (исходник клипа) ──┐
                                ├─ Merge ─ MediaOut
    Loader (cutout|fg) ─────────┘
    Loader (alpha) ── Garbage Matte у MatteControl  (когда альфа отдельно)

и ничего не рендерит. Исходные медиа не изменяются, создаются только ноды.

**Loader Fusion читает только секвенции.** `.mp4`/`.mov` в Loader дают сплошной
чёрный кадр (проверено на 21.1), одиночная картинка живёт лишь на кадре 0. Поэтому
плашка берётся из `MediaIn` клипа, а фон и видео-результаты сначала перегоняются
`ffmpeg` в PNG-секвенцию в папке работы (`_ck_seq_<роль>/`).

Запуск (системный python 3.12, как в resolve_client.py):

    RESOLVE_SCRIPT_LIB=/opt/resolve/libs/Fusion/fusionscript.so \
    PYTHONPATH=/opt/resolve/Developer/Scripting/Modules \
    /usr/bin/python3.12 resolve_compose.py [--job N|ID] [--plate PATH] \
        [--bg PATH] [--dry-run]

Нужен запущенный Resolve Studio с открытым проектом и «External scripting = Local»,
а также открытая страница Fusion на клипе (Resolve сам создаёт композицию клипа,
когда страница открывается впервые).

Почему Python через Resolve Scripting API, а не Lua в Fusion: тот же внешний процесс,
что уже импортирует работы в медиапул; не нужно держать открытым консольный ввод
Fusion; логика выбора работы и путей живёт в одном месте. Lua-скрипт остаётся
вариантом для запуска изнутри Fusion (Workspace → Scripts), но его нельзя проверить
снаружи так же однозначно.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "renders" / "manifest.json"
STILL_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
MOVIE_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
SEQ_EXT = (".exr", ".dpx", ".tif", ".tiff", ".png", ".jpg", ".jpeg")


# ── выбор работы ────────────────────────────────────────────────────────────
def pick_job(spec: str | None) -> dict:
    """Работа из манифеста: по индексу (0 = свежая) или по id; по умолчанию свежая."""
    try:
        jobs = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError):
        sys.exit(f"нет манифеста {MANIFEST}")
    done = [j for j in jobs if j.get("status") == "done"]
    if not done:
        sys.exit("в манифесте нет завершённых работ")
    if spec:
        for j in done:
            if j.get("id") == spec:
                return j
        try:
            idx = int(spec)
        except ValueError:
            sys.exit(f"работа {spec} не найдена (ни id, ни индекс)")
        if not 0 <= idx < len(done):
            sys.exit(f"индекс {idx} вне диапазона 0..{len(done) - 1}")
        return done[idx]
    return done[-1]


def find_sequences(outdir: Path) -> dict[str, str]:
    """Первые кадры EXR-секвенций работы: {'alpha': path, 'fg': path, 'cutout': path}."""
    seqs: dict[str, str] = {}
    if not outdir.is_dir():
        return seqs
    for d in sorted(outdir.iterdir()):
        if not (d.is_dir() and d.name.endswith("_exr")):
            continue
        frames = sorted(d.glob("*.exr"))
        if not frames:
            continue
        stem = d.name[: -len("_exr")]
        for kind in ("cutout", "alpha", "fg", "checker"):
            if stem.endswith("_" + kind):
                seqs.setdefault(kind, str(frames[0]))
                break
    return seqs


def find_movies(outdir: Path) -> dict[str, str]:
    """Видео-результаты работы (alpha/fg/cutout в mp4): {'alpha': path, ...}.

    В Loader их отдавать нельзя — чёрный кадр, поэтому они перегоняются в PNG.
    """
    found: dict[str, str] = {}
    if not outdir.is_dir():
        return found
    for f in sorted(outdir.iterdir()):
        if not (f.is_file() and f.suffix.lower() in MOVIE_EXT):
            continue
        for kind in ("cutout", "alpha", "fg", "checker"):
            if kind in f.stem:
                found.setdefault(kind, str(f))
                break
    return found


def _media_in(comp):
    """MediaIn композиции клипа = исходник таймлайна (mp4 в Loader не читается)."""
    for tool in (comp.GetToolList() or {}).values():
        if tool.GetAttrs().get("TOOLS_RegID") == "MediaIn":
            return tool
    return None


# ── сборка композа ──────────────────────────────────────────────────────────
def plan(job: dict, seqs: dict[str, str], movies: dict[str, str], plate: str,
         bg: str | None) -> list[str]:
    """Что и как будет соединено — печатается в --dry-run и перед сборкой."""
    lines = [f"работа {job['id']}: {job.get('input')}",
             f"  plate : {plate} → MediaIn клипа (mp4 в Loader не читается)"]
    have = {**{k: v for k, v in movies.items()}, **seqs}
    for kind in ("cutout", "fg", "alpha"):
        if kind in seqs:
            lines.append(f"  {kind:<6}: {seqs[kind]}")
        elif kind in movies:
            lines.append(f"  {kind:<6}: {movies[kind]} → PNG-секвенция")
    if "cutout" in have:
        lines.append("  схема : cutout (RGBA) over " + (bg or "плашка"))
    elif "fg" in have and "alpha" in have:
        lines.append("  схема : fg + MatteControl(alpha) → premult, over " + (bg or "плашка"))
    elif "alpha" in have:
        lines.append(f"  схема : плашка + MatteControl(alpha), over {bg or 'плашка'}")
    else:
        lines.append("  схема : только плашка (в работе нет ни EXR, ни alpha/fg видео)")
    if bg:
        ext = Path(bg).suffix.lower()
        how = "PNG-секвенция" if ext in MOVIE_EXT or ext in STILL_EXT else "как есть"
        lines.append(f"  фон   : {bg} → {how}")
    return lines


def _has_tool(comp, name: str) -> bool:
    for tool in (comp.GetToolList() or {}).values():
        if tool.GetAttrs().get("TOOLS_Name") == name:
            return True
    return False


def _get_or_add(comp, reg_id: str, name: str, x: int, y: int):
    """Нод по имени, а не новый: повторная сборка не плодит ck_*-копии."""
    for tool in (comp.GetToolList() or {}).values():
        if tool.GetAttrs().get("TOOLS_Name") == name:
            return tool
    return _add(comp, reg_id, name, x, y)


def _add(comp, reg_id: str, name: str, x: int, y: int):
    tool = comp.AddTool(reg_id, x, y)
    if tool is None:
        raise RuntimeError(f"Fusion не создал нод {reg_id} (страница Fusion активна?)")
    try:
        tool.SetAttrs({"TOOLS_Name": name})
    except Exception:  # noqa: BLE001 — имя не критично
        pass
    return tool


def _connect(tool, input_name: str, src) -> None:
    """Соединить нод с источником.

    Значения (`Clip`, числа) ставятся через SetInput; картиночные входы — тоже
    SetInput, но проверять результат надо по `INPB_Connected` у объекта входа
    (`GetInput()` для image-входов возвращает None даже при рабочей связи).
    """
    tool.SetInput(input_name, src)
    if (tool.GetInputList() or {}).get(input_name) is None:
        # вложенные имена вроде "Garbage.Matte" приходят с другим ключом
        for inp in (tool.GetInputList() or {}).values():
            if inp.GetAttrs().get("INPS_ID") == input_name:
                if inp.GetAttrs().get("INPB_Connected"):
                    return
                break
    attr = input_name.replace(".", "_").replace(" ", "_")
    try:  # запасной путь: присваивание атрибута
        setattr(tool, attr, src)
    except Exception:  # noqa: BLE001
        pass


def _is_connected(tool, input_name: str) -> bool:
    for inp in (tool.GetInputList() or {}).values():
        if inp.GetAttrs().get("INPS_ID") == input_name:
            return bool(inp.GetAttrs().get("INPB_Connected"))
    return False


def _media_out(comp):
    """Существующий MediaOut композиции (второй создавать нельзя)."""
    for tool in (comp.GetToolList() or {}).values():
        if tool.GetAttrs().get("TOOLS_RegID") == "MediaOut":
            return tool
    return None


def _matte(comp, image, alpha):
    """Обрезать изображение отдельной маской-EXR и получить premultiplied RGBA.

    «Garbage Matte» у MatteControl снимает то, что ВНУТРИ маски, поэтому маску надо
    инвертировать (`Garbage.MaskInverted`), а `PostMultiplyImage` умножает RGB на
    полученную альфу. `MultiplyGarbageMatte` ставить нельзя: он умножает картинку на
    саму garbage-маску, то есть гасит субъект в ноль.
    """
    mc = _get_or_add(comp, "MatteControl", "ck_matte", -200, 200)
    _connect(mc, "Background", image)
    _connect(mc, "Garbage.Matte", alpha)
    for key, val in (("Garbage.MaskInverted", 1.0), ("PostMultiplyImage", 1.0)):
        try:
            mc.SetInput(key, val)
        except Exception:  # noqa: BLE001
            pass
    return mc


def _probe_fps(path: str, default: float = 24.0) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=20).stdout.strip()
        num, _, den = out.partition("/")
        val = float(num) / float(den or 1)
        return val if val > 0 else default
    except (OSError, ValueError, subprocess.SubprocessError):
        return default


def _probe_frames(path: str) -> int:
    """Сколько кадров в файле (для секвенции той же длины, что и плашка)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return max(1, int(out.splitlines()[0]))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1


def _to_sequence(src: str, dst_dir: Path, prefix: str, fps: float,
                 frames: int | None = None) -> str:
    """Файл → PNG-секвенция; вернуть путь первого кадра.

    Loader Fusion не читает mp4/mov (чёрный кадр) и не держит одиночную картинку
    дальше первого кадра. Секвенция PNG снимает оба ограничения. Для статичной
    картинки `frames` задаёт длину: она повторяется нужное число кадров.
    Повторный вызов на готовой секвенции ничего не делает.
    """
    first = dst_dir / f"{prefix}_000000.png"
    if first.is_file():
        return str(first)
    dst_dir.mkdir(parents=True, exist_ok=True)
    still = Path(src).suffix.lower() in STILL_EXT
    args = ["ffmpeg", "-v", "error", "-y"]
    if still:
        dur = max(1, frames or 1) / max(fps, 1.0)
        args += ["-loop", "1", "-t", f"{dur:.4f}", "-i", src]
    else:
        args += ["-i", src]
    args += ["-start_number", "0", "-r", f"{fps:.6g}",
             str(dst_dir / f"{prefix}_%06d.png")]
    try:
        subprocess.run(args, capture_output=True, timeout=900, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"не удалось сделать секвенцию из {src}: {exc}")
    if not first.is_file():
        raise SystemExit(f"ffmpeg не создал ни одного кадра из {src}")
    return str(first)


def build_comp(comp, job: dict, seqs: dict[str, str], movies: dict[str, str],
               plate: str, bg: str | None) -> dict[str, str]:
    """Создать ноды в композиции; вернуть {роль: имя нода}."""
    made: dict[str, str] = {}
    outdir = Path(job.get("output_dir") or ".")
    fps = _probe_fps(plate)
    plate_frames = _probe_frames(plate)

    # плашка — исходник клипа из MediaIn: mp4 в Loader даёт чёрный кадр
    plate_src = _media_in(comp)
    if plate_src is not None:
        made["plate"] = plate_src.Name
    else:
        plate_seq = _to_sequence(plate, outdir / "_ck_seq_plate", "plate", fps)
        plate_src = _get_or_add(comp, "Loader", "ck_plate", -400, 0)
        plate_src.SetInput("Clip", plate_seq)
        made["plate"] = plate_src.Name

    def source(kind: str) -> str | None:
        """EXR-секвенция как есть, видео → PNG-секвенция, иначе None."""
        if kind in seqs:
            return seqs[kind]
        if kind in movies:
            return _to_sequence(movies[kind], outdir / f"_ck_seq_{kind}", kind, fps)
        return None

    fg_ld = None
    alpha_ld = None
    cutout = source("cutout")
    fg = source("fg")
    alpha = source("alpha")
    if cutout:
        fg_ld = _get_or_add(comp, "Loader", "ck_cutout", -400, 200)
        fg_ld.SetInput("Clip", cutout)
        made["cutout"] = fg_ld.Name
    elif fg:
        fg_ld = _get_or_add(comp, "Loader", "ck_fg", -400, 200)
        fg_ld.SetInput("Clip", fg)
        made["fg"] = fg_ld.Name
    if alpha and not cutout:
        alpha_ld = _get_or_add(comp, "Loader", "ck_alpha", -400, 400)
        alpha_ld.SetInput("Clip", alpha)
        made["alpha"] = alpha_ld.Name

    merge = _get_or_add(comp, "Merge", "ck_merge", 0, 0)
    made["merge"] = merge.Name

    background = plate_src
    if bg:  # новый фон вместо исходной плашки
        ext = Path(bg).suffix.lower()
        bg_clip = bg
        if ext in MOVIE_EXT or ext in STILL_EXT:
            # mp4 в Loader чёрный, одиночная картинка живёт один кадр → секвенция
            bg_clip = _to_sequence(bg, outdir / "_ck_seq_bg", "bg", fps,
                                   frames=plate_frames)
        bg_ld = _get_or_add(comp, "Loader", "ck_bg", -400, -200)
        bg_ld.SetInput("Clip", bg_clip)
        made["bg"] = bg_ld.Name
        background = bg_ld

    foreground = None
    if fg_ld is not None:
        foreground = fg_ld
        if alpha_ld is not None:
            foreground = _matte(comp, fg_ld, alpha_ld)
            made["matte"] = foreground.Name
    elif alpha_ld is not None:
        foreground = _matte(comp, plate_src, alpha_ld)
        made["matte"] = foreground.Name

    _connect(merge, "Background", background)
    if foreground is not None:
        _connect(merge, "Foreground", foreground)
    else:
        made["note"] = "нет результатов — в композе только плашка"

    out = _media_out(comp) or _add(comp, "MediaOut", "ck_out", 400, 0)
    for tool in (comp.GetToolList() or {}).values():
        # лишние MediaOut (например от AddFusionComp) тоже ведут на merge:
        # иначе Resolve может смотреть в пустой выход
        if tool.GetAttrs().get("TOOLS_RegID") == "MediaOut":
            _connect(tool, "Input", merge)
    made["out"] = out.Name
    return made


def verify_connections(comp, made: dict[str, str]) -> list[str]:
    """Проверить, что картиночные входы реально соединены.

    Единственный надёжный признак — `INPB_Connected` у объекта входа: `GetInput()`
    для image-входов возвращает None даже при рабочей связи.
    """
    problems = []

    def need(tool_name: str, input_name: str) -> None:
        for tool in (comp.GetToolList() or {}).values():
            if tool.GetAttrs().get("TOOLS_Name") == tool_name:
                if not _is_connected(tool, input_name):
                    problems.append(f"{tool_name}.{input_name} не соединён")
                return
        problems.append(f"{tool_name} не найден в композиции")

    need(made["out"], "Input")
    need(made["merge"], "Background")
    if "matte" in made:
        need(made["matte"], "Background")
        need(made["matte"], "Garbage.Matte")
    else:
        need(made["merge"], "Foreground")
    return problems


# ── Resolve ─────────────────────────────────────────────────────────────────
def connect():
    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        sys.exit("нет модуля DaVinciResolveScript: запускай системным python3.12 с "
                 "RESOLVE_SCRIPT_LIB и PYTHONPATH (см. docstring)")
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        sys.exit("Resolve не отвечает: проверь, что он запущен и External scripting = Local")
    return resolve


def _timeline_item_at_playhead(resolve):
    p = resolve.GetProjectManager().GetCurrentProject()
    tl = p.GetCurrentTimeline() if p else None
    if tl is None:
        return None, None
    items = tl.GetItemListInTrack("video", 1) or []
    if not items:
        return tl, None
    tc = None
    try:
        tc = tl.GetCurrentTimecode()
        hours, minutes, seconds, frames = (int(x) for x in tc.split(":"))
        fps = float(p.GetSetting("timelineFrameRate") or 24)
        frame = int(((hours * 3600 + minutes * 60 + seconds) * fps)) + frames + tl.GetStartFrame()
    except (AttributeError, TypeError, ValueError):
        frame = None
    if frame is not None:
        for it in items:
            if it.GetStart() <= frame < it.GetEnd():
                return tl, it
    return tl, items[0]


def active_comp(resolve):
    """Композиция клипа под плейхедом — «живая» только после открытия Fusion-страницы.

    Проверено на 21.1: пока страница Fusion не открыта, ноды можно построить в любом
    комп-объекте, но клип рендерится исходником. После `OpenPage("fusion")`
    `fusion.GetCurrentComp()` возвращает именно ту композицию, которую Resolve
    применяет к клипу (и во Viewer, и в Deliver).
    """
    resolve.OpenPage("fusion")
    fusion = resolve.Fusion()
    comp = None
    for _ in range(15):
        time.sleep(1.0)
        comp = fusion.GetCurrentComp() if fusion else None
        if comp is not None:
            return comp
    # запасной путь: композиция прямо у клипа (для таймлайнов без открытой страницы)
    tl, item = _timeline_item_at_playhead(resolve)
    if item is not None:
        names = item.GetFusionCompNameList() or []
        if names:
            comp = item.GetFusionCompByIndex(len(names))
        if comp is None:
            comp = item.AddFusionComp()
    if comp is None:
        sys.exit("нет композиции Fusion у клипа под плейхедом: положи клип на таймлайн "
                 "и повтори")
    return comp


def main(argv: list[str]) -> int:
    spec = None
    plate_arg = None
    bg = None
    dry = False
    args = argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--job", "-j") and i + 1 < len(args):
            spec = args[i + 1]; i += 2
        elif a == "--plate" and i + 1 < len(args):
            plate_arg = args[i + 1]; i += 2
        elif a == "--bg" and i + 1 < len(args):
            bg = args[i + 1]; i += 2
        elif a == "--dry-run":
            dry = True; i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            sys.exit(f"неизвестный аргумент {a} (см. --help)")

    job = pick_job(spec)
    outdir = Path(job.get("output_dir") or "")
    seqs = find_sequences(outdir)
    movies = find_movies(outdir)
    plate = plate_arg or job.get("input") or ""
    if not Path(plate).is_file():
        sys.exit(f"нет исходника-плашки: {plate}")

    for line in plan(job, seqs, movies, plate, bg):
        print(line)
    if dry:
        print("dry-run: композиция не тронута")
        return 0

    resolve = connect()
    comp = active_comp(resolve)
    print(f"композиция: {comp.GetAttrs().get('COMPS_Name', '?')}")
    try:
        comp.Lock()
    except Exception:  # noqa: BLE001
        pass
    try:
        made = build_comp(comp, job, seqs, movies, plate, bg)
    finally:
        try:
            comp.Unlock()
        except Exception:  # noqa: BLE001
            pass
    for role, name in made.items():
        print(f"  {role:<7} → {name}")
    problems = verify_connections(comp, made)
    if problems:
        for p in problems:
            print("  [!]", p)
        return 1
    print("проверено: все картиночные входы соединены (INPB_Connected); рендер не запускался")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
