#!/usr/bin/env python3
"""Собрать композицию в Fusion внутри DaVinci Resolve Studio из готовой работы CorridorKey.

Что делает: берёт готовый рендер из `renders/manifest.json`, создаёт в **текущей**
композиции Fusion (страница Fusion активного клипа таймлайна) цепочку

    Loader (plate / исходник) ─┐
                               ├─ Merge ─ MediaOut
    Loader (cutout|fg EXR) ────┘
    Loader (alpha EXR) ── Garbage Matte у Merge  (когда альфа отдельно)

и ничего не рендерит. Исходные медиа не изменяются, создаются только ноды.

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


# ── сборка композа ──────────────────────────────────────────────────────────
def plan(job: dict, seqs: dict[str, str], plate: str, bg: str | None) -> list[str]:
    """Что и как будет соединено — печатается в --dry-run и перед сборкой."""
    lines = [f"работа {job['id']}: {job.get('input')}", f"  plate : {plate}"]
    for kind in ("cutout", "fg", "alpha"):
        if kind in seqs:
            lines.append(f"  {kind:<6}: {seqs[kind]}")
    if "cutout" in seqs:
        lines.append("  схема : cutout (RGBA) over " + (bg or "plate"))
    elif "fg" in seqs and "alpha" in seqs:
        lines.append("  схема : fg + MatteControl(alpha) → premult, over " + (bg or "plate"))
    elif "alpha" in seqs:
        lines.append(f"  схема : plate + MatteControl(alpha), over {bg or 'plate'}")
    else:
        lines.append("  схема : только plate (в работе нет EXR — нужен рендер с --exr)")
    return lines


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
    mc = _add(comp, "MatteControl", "ck_matte", -200, 200)
    _connect(mc, "Background", image)
    _connect(mc, "Garbage.Matte", alpha)
    for key, val in (("Garbage.MaskInverted", 1.0), ("PostMultiplyImage", 1.0)):
        try:
            mc.SetInput(key, val)
        except Exception:  # noqa: BLE001
            pass
    return mc


def _still_to_video(src: str, like: str, dst: Path) -> str:
    """Fusion-Loader не держит одиночную картинку на кадрах за её диапазоном (0..1).

    Поэтому статичный фон превращаем в короткий клип той же длительности, что и
    плашка: тогда фон виден на всех кадрах композа.
    """
    if dst.is_file():
        return str(dst)
    dur = 5.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", like],
            capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            dur = max(1.0, float(out))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", src, "-t", f"{dur:.3f}",
             "-r", "24", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(dst)],
            capture_output=True, timeout=180, check=True)
        return str(dst)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [warn] не удалось сделать видео из фона ({exc}); беру картинку как есть")
        return src


def build_comp(comp, job: dict, seqs: dict[str, str], plate: str,
               bg: str | None) -> dict[str, str]:
    """Создать ноды в композиции; вернуть {роль: имя нода}."""
    made: dict[str, str] = {}
    plate_ld = _add(comp, "Loader", "ck_plate", -400, 0)
    plate_ld.SetInput("Clip", plate)
    made["plate"] = plate_ld.Name

    fg_ld = None
    alpha_ld = None
    if "cutout" in seqs:
        fg_ld = _add(comp, "Loader", "ck_cutout", -400, 200)
        fg_ld.SetInput("Clip", seqs["cutout"])
        made["cutout"] = fg_ld.Name
    elif "fg" in seqs:
        fg_ld = _add(comp, "Loader", "ck_fg", -400, 200)
        fg_ld.SetInput("Clip", seqs["fg"])
        made["fg"] = fg_ld.Name

    if "alpha" in seqs and "cutout" not in seqs:
        alpha_ld = _add(comp, "Loader", "ck_alpha", -400, 400)
        alpha_ld.SetInput("Clip", seqs["alpha"])
        made["alpha"] = alpha_ld.Name

    merge = _add(comp, "Merge", "ck_merge", 0, 0)
    made["merge"] = merge.Name

    background = plate_ld
    if bg:  # новый фон вместо исходной плашки
        bg_clip = bg
        if Path(bg).suffix.lower() in STILL_EXT:
            # одиночная картинка видна в Fusion только на кадре 0 → делаем клип
            bg_clip = _still_to_video(
                bg, plate, Path(job.get("output_dir") or ".") / "_ck_bg.mp4")
        bg_ld = _add(comp, "Loader", "ck_bg", -400, -200)
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
        foreground = _matte(comp, plate_ld, alpha_ld)
        made["matte"] = foreground.Name

    _connect(merge, "Background", background)
    if foreground is not None:
        _connect(merge, "Foreground", foreground)
    else:
        made["note"] = "нет EXR-результатов — в композе только plate"

    out = _media_out(comp) or _add(comp, "MediaOut", "ck_out", 400, 0)
    _connect(out, "Input", merge)
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


def active_comp(resolve):
    fusion = resolve.Fusion()
    comp = fusion.GetCurrentComp() if fusion else None
    if comp is None:
        # иногда композиция клипа создаётся только после открытия страницы Fusion
        resolve.OpenPage("fusion")
        for _ in range(10):
            time.sleep(1.0)
            comp = fusion.GetCurrentComp() if fusion else None
            if comp is not None:
                break
    if comp is None:
        sys.exit("нет активной композиции Fusion: открой клип на таймлайне и страницу "
                 "Fusion (клип → Fusion), затем повтори")
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
    plate = plate_arg or job.get("input") or ""
    if not Path(plate).is_file():
        sys.exit(f"нет исходника-плашки: {plate}")

    for line in plan(job, seqs, plate, bg):
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
        made = build_comp(comp, job, seqs, plate, bg)
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
