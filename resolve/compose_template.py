"""Fusion-композ для клипа CorridorKey: RGBA-вырезка over фон → MediaOut.

Зачем вставка текстом: в Resolve 21.1 `AddTool`/`SetInput` строят ноды «за километр»
(1 единица ≈ 14 600 px) и через раз теряют связи. Вставка готового copy-format текста
(`comp.Paste()`) даёт компактный граф со всеми связями. Правила и грабли —
docs/CK_COMP_STRUCTURE.md.

Важно про альфу: в результатах CorridorKey `fg` пишется с alpha=1 (непрозрачный), альфа
лежит отдельным файлом `alpha`. Поэтому в композ идёт **cutout** (RGBA с настоящей
альфой) либо RGBA, собранный из fg+alpha (`prepare_rgba`). Прямой Merge по `fg` даёт
«субъект на чёрном» — он перекрывает фон.

Использование:
    from resolve.compose_template import paste_compose
    paste_compose(resolve, rgba="/path/cutout_000000.exr",
                  bg="/path/bg_000000.png", frames=12)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

LOADER = '''\t\t{name} = Loader {{
\t\t\tClips = {{
\t\t\t\tClip {{
\t\t\t\t\tID = "{clip_id}",
\t\t\t\t\tFilename = "{path}",
\t\t\t\t\tFormatID = "{fmt}",
\t\t\t\t\tLength = {n},
\t\t\t\t\tLengthSetManually = true,
\t\t\t\t\tTrimIn = 0,
\t\t\t\t\tTrimOut = {last},
\t\t\t\t\tExtendFirst = 0,
\t\t\t\t\tExtendLast = 0,
\t\t\t\t\tLoop = 1,
\t\t\t\t\tAspectMode = 0,
\t\t\t\t\tDepth = 0,
\t\t\t\t\tTimeCode = 0,
\t\t\t\t\tGlobalStart = 0,
\t\t\t\t\tGlobalEnd = {last}
\t\t\t\t}}
\t\t\t}},
{inputs}\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {x}, {y} }} }},
\t\t}},
'''

# PNG-лоадеру нужен PostMultiply, иначе альфа 0 (фон ложится прозрачным).
PNG_INPUTS = ('\t\t\tInputs = {\n'
              '\t\t\t\t["Clip2.PNGFormat.PostMultiply"] = Input { Value = 1, }\n'
              '\t\t\t},\n')

TAIL = '''\t\tck_merge = Merge {
\t\t\tInputs = {
\t\t\t\tBackground = Input {
\t\t\t\t\tSourceOp = "ck_bg",
\t\t\t\t\tSource = "Output",
\t\t\t\t},
\t\t\t\tForeground = Input {
\t\t\t\t\tSourceOp = "ck_subject",
\t\t\t\t\tSource = "Output",
\t\t\t\t},
\t\t\t\tPerformDepthMerge = Input { Value = 0, }
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 260, 0 } },
\t\t},
\t\tMediaOut1 = MediaOut {
\t\t\tInputs = {
\t\t\t\tIndex = Input { Value = "0", },
\t\t\t\tInput = Input {
\t\t\t\t\tSourceOp = "ck_merge",
\t\t\t\t\tSource = "Output",
\t\t\t\t}
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 480, 0 } },
\t\t},
\t},
\tActiveTool = "ck_merge",
}
'''


def copy_format(rgba: str, bg: str, frames: int,
                rgba_fmt: str = "OpenEXRFormat", bg_fmt: str = "PNGFormat") -> str:
    """Текст композа в формате копирования Fusion (`Tools = ordered() { ... }`)."""
    last = frames - 1
    out = "{\n\tTools = ordered() {\n"
    out += LOADER.format(name="ck_bg", path=bg, fmt=bg_fmt, n=frames, last=last,
                         x=0, y=130, inputs=PNG_INPUTS if bg_fmt == "PNGFormat" else "",
                         clip_id="Clip1")
    out += LOADER.format(name="ck_subject", path=rgba, fmt=rgba_fmt, n=frames, last=last,
                         x=0, y=-130, inputs="", clip_id="Clip2")
    out += TAIL
    return out


def prepare_rgba(fg_first: str, alpha_first: str, outdir: str, frames: int) -> str:
    """Собирает RGBA-секвенцию из fg (RGB) и alpha через ffmpeg alphamerge.

    Возвращает путь к первому файлу новой секвенции `rgba_000000.exr`.
    """
    out = Path(outdir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    first = out / "rgba_000000.exr"
    if first.is_file():
        return str(first)
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-i", fg_first, "-i", alpha_first,
           "-filter_complex", "[0][1]alphamerge",
           "-frames:v", str(frames), "-pix_fmt", "gbrpf32le",
           "-compression", "zip1", str(out / "rgba_%06d.exr")]
    subprocess.run(cmd, check=True)
    return str(first)


def paste_compose(resolve, rgba: str, bg: str, frames: int,
                  rgba_fmt: str = "OpenEXRFormat", bg_fmt: str = "PNGFormat") -> bool:
    """Кладёт текст в буфер X11 и вставляет композ в текущую композицию клипа.

    Клип должен быть под плейхедом, страница Fusion открыта. Существующие ноды не
    удаляются — чистить граф до вставки.
    """
    text = copy_format(rgba, bg, frames, rgba_fmt, bg_fmt)
    subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=text.encode(),
                   env={"DISPLAY": ":0", "PATH": "/usr/bin:/bin"}, check=True)
    comp = resolve.Fusion().GetCurrentComp()
    if comp is None:
        return False
    return bool(comp.Paste())
