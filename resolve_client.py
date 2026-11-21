#!/usr/bin/env python3
"""Импорт готового кея из CorridorKey daemon в DaVinci Resolve Studio.

Требования: Resolve Studio запущен, Preferences → System → General →
External scripting using = Local. Запускать системным python3.12:

    RESOLVE_SCRIPT_LIB=/opt/resolve/libs/Fusion/fusionscript.so \
    PYTHONPATH=/opt/resolve/Developer/Scripting/Modules \
    /usr/bin/python3.12 resolve_client.py [номер_работы]

fusionscript.so подхватывается через DaVinciResolveScript-загрузчик.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import DaVinciResolveScript as dvr  # provides Resolve() via env vars

RENDER_ROOT = Path(__file__).resolve().parent / "renders"
MANIFEST = RENDER_ROOT / "manifest.json"


def pick_job(index: int = 0) -> dict:
    jobs = json.loads(MANIFEST.read_text())
    done = [j for j in jobs if j["status"] == "done"]
    if not done:
        sys.exit("нет готовых работ в манифесте")
    return done[min(index, len(done) - 1)]


def sequence_files(outdir: Path) -> list[str]:
    """Первые кадры EXR-секвенций (Resolve сам склеит секвенцию)."""
    files = []
    for d in sorted(outdir.iterdir()):
        if d.is_dir() and d.name.endswith("_exr"):
            first = sorted(d.glob("*.exr"))
            if first:
                files.append(str(first[0]))
    if not files:  # video fallback
        for v in sorted(outdir.glob("*.mp4")):
            if "alpha" in v.name or "fg" in v.name:
                files.append(str(v))
    return files


def main() -> None:
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    job = pick_job(idx)
    outdir = Path(job["output_dir"])
    files = sequence_files(outdir)
    if not files:
        sys.exit(f"в {outdir} нет EXR/видео для импорта")

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        sys.exit("Resolve не отвечает: проверь External scripting = Local и что Resolve запущен")
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    if not proj:
        sys.exit("нет открытого проекта в Resolve")
    mp = proj.GetMediaPool()

    clips = mp.ImportMedia(files)
    if not clips:
        sys.exit("ImportMedia вернул пусто")
    print("Импортировано в медиапол проекта", proj.GetName(), ":")
    for c in clips:
        print("  -", c.GetName())
    print("Дальше: перетащи клип на таймлайн или в Fusion (Loader).")


if __name__ == "__main__":
    main()
