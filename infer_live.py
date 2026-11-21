#!/usr/bin/env python3
"""Run upstream `CorridorKey2.0/infer.py` and drop a live alpha JPEG while it works.

The upstream runtime streams mattes straight into an mp4 (or an EXR sequence), so
nothing is readable until the clip ends and the live preview can only show the
source plate. This wrapper hooks the two writers of `corridorkey.video_io` — the
upstream clone is not modified — and writes `<CK_LIVE_DIR>/_live_alpha.jpg` after
every model window; `GET /jobs/{id}/live` serves that file to the UI.

Environment:
  CK_LIVE_DIR      where to drop the sidecar JPEG (the job output dir)
  CK_LIVE_WIDTH    downscale width for the JPEG (default 880)
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "CorridorKey2.0"


def _install_hook(live_dir: Path, width: int) -> None:
    import cv2
    import numpy as np

    from corridorkey import video_io

    out = live_dir / "_live_alpha.jpg"
    tmp = live_dir / "_live_alpha.tmp.jpg"

    def dump(gray: "np.ndarray") -> None:
        if gray.ndim != 2 or gray.size == 0:
            return
        h, w = gray.shape[:2]
        if width and w > width:
            gray = cv2.resize(gray, (width, max(1, round(h * width / w))),
                              interpolation=cv2.INTER_AREA)
        # tmp + rename: демон не должен поймать недописанный файл
        if cv2.imwrite(str(tmp), gray, [cv2.IMWRITE_JPEG_QUALITY, 82]):
            os.replace(tmp, out)

    orig_video = video_io.ThreadedVideoWriter.write_many

    def write_many_video(self, frames):  # NHWC uint16
        orig_video(self, frames)
        try:
            if "_alpha" in str(getattr(self, "path", "")):
                arr = np.asarray(frames)
                if arr.ndim == 4 and arr.shape[0]:
                    frame = arr[-1]
                    gray = frame[:, :, 0] if frame.ndim == 3 else frame
                    dump((np.asarray(gray).astype(np.uint16) >> 8).astype(np.uint8))
        except Exception:  # noqa: BLE001 — превью не должно ломать инференс
            pass

    orig_exr = video_io.ExrSequenceWriter.write_many

    def write_many_exr(self, frames):  # NHWC float32, 0..1
        orig_exr(self, frames)
        try:
            if "alpha" in str(getattr(self, "dir_path", "")):
                arr = np.asarray(frames)
                if arr.ndim == 4 and arr.shape[0]:
                    frame = arr[-1]
                    gray = frame[:, :, 0] if frame.ndim == 3 else frame
                    dump((np.clip(np.asarray(gray, dtype=np.float32), 0.0, 1.0) * 255).astype(np.uint8))
        except Exception:  # noqa: BLE001
            pass

    video_io.ThreadedVideoWriter.write_many = write_many_video  # type: ignore[assignment]
    video_io.ExrSequenceWriter.write_many = write_many_exr  # type: ignore[assignment]


def main() -> None:
    sys.path.insert(0, str(REPO))
    live_dir = os.environ.get("CK_LIVE_DIR")
    if live_dir:
        try:
            target = Path(live_dir)
            target.mkdir(parents=True, exist_ok=True)
            _install_hook(target, int(os.environ.get("CK_LIVE_WIDTH") or 880))
        except Exception as exc:  # noqa: BLE001
            print(f"[live] alpha preview disabled: {exc}", flush=True)
    runpy.run_path(str(REPO / "infer.py"), run_name="__main__")


if __name__ == "__main__":
    main()
