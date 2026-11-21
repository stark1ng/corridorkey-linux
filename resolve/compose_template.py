"""Текст Fusion-композа для вставки в клип: ck_fg over ck_bg -> MediaOut.

Зачем: в Resolve 21.1 API `AddTool`/`SetInput` строят ноды «за километр» и теряют
связи. Вставка готового copy-format текста (`comp.Paste()`) даёт компактный граф со
всеми связями. Подробности и правила — docs/CK_COMP_STRUCTURE.md.

Использование:
    from resolve.compose_template import paste_compose
    paste_compose(resolve, fg="/path/fg_000000.exr", bg="/path/bg_000000.png", frames=12)
"""
from __future__ import annotations

import subprocess

LOADER = '''\t\t{name} = Loader {{
\t\t\tClips = {{
\t\t\t\tClip {{
\t\t\t\t\tID = "Clip1",
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
\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {x}, {y} }} }},
\t\t}},
'''

TAIL = '''\t\tck_merge = Merge {
\t\t\tInputs = {
\t\t\t\tBackground = Input {
\t\t\t\t\tSourceOp = "ck_bg",
\t\t\t\t\tSource = "Output",
\t\t\t\t},
\t\t\t\tForeground = Input {
\t\t\t\t\tSourceOp = "ck_fg",
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


def copy_format(fg: str, bg: str, frames: int) -> str:
    """Текст композа в формате копирования Fusion (Tools = ordered() { ... })."""
    last = frames - 1
    out = "{\n\tTools = ordered() {\n"
    out += LOADER.format(name="ck_bg", path=bg, fmt="PNGFormat", n=frames, last=last, x=0, y=130)
    out += LOADER.format(name="ck_fg", path=fg, fmt="OpenEXRFormat", n=frames, last=last, x=0, y=-130)
    out += TAIL
    return out


def paste_compose(resolve, fg: str, bg: str, frames: int) -> bool:
    """Кладёт текст в буфер X11 и вставляет композ в текущую композицию клипа.

    Клип должен быть под плейхедом, страница Fusion открыта. Существующие ноды
    не удаляются — чистить граф до вставки (или вызывать на пустой композиции).
    """
    text = copy_format(fg, bg, frames)
    subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=text.encode(),
                   env={"DISPLAY": ":0", "PATH": "/usr/bin:/bin"}, check=True)
    comp = resolve.Fusion().GetCurrentComp()
    if comp is None:
        return False
    return bool(comp.Paste())
