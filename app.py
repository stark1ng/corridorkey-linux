#!/usr/bin/env python3
"""CorridorKey 2.0 desktop shell (PySide6 + QtWebEngine).

Окно-приложение загружает локальный интерфейс из демона (ui/ на :8129) в
QtWebEngineView, а нативный слой закрывает то, что браузеру недоступно:
drag&drop локальных файлов, системные диалоги выбора, «открыть папку» и
импорт в DaVinci Resolve.

Запуск:  .venv/bin/python app.py            (поднимет демон, если он не отвечает)
         .venv/bin/python app.py --browser  (открыть тот же UI в браузере по умолчанию)
         .venv/bin/python app.py --shot f.png  (отрендерить окно в PNG и выйти)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
API = "http://127.0.0.1:8129"
VENV_PY = ROOT / ".venv" / "bin" / "python"
UI = ROOT / "ui"

from PySide6.QtCore import QObject, QUrl, Qt, Slot, QMetaObject, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QFileDialog, QHeaderView, QLabel, QMainWindow, QSplitter, QTreeView,
)

MEDIA = "Медиа (*.mp4 *.mov *.mkv *.mxf *.avi)"
BG_FILES = "Фон: картинка или видео (*.png *.jpg *.jpeg *.tif *.tiff *.exr *.mp4 *.mov *.mkv)"

# Resolve-скрипты требуют системный python3.12 и fusionscript: venv-питон модуль
# DaVinciResolveScript не видит, поэтому запускать только так.
SYS_PY = Path("/usr/bin/python3.12")
RESOLVE_ENV = {
    "RESOLVE_SCRIPT_LIB": "/opt/resolve/libs/Fusion/fusionscript.so",
    "PYTHONPATH": "/opt/resolve/Developer/Scripting/Modules",
}

# QFileDialog — отдельное окно Qt, поэтому его тёмную тему задаём явно:
# палитра + QSS (иначе системная светлая палитра на чёрном фоне даёт чёрный текст).
DIALOG_QSS = """
QFileDialog { background: #0d0b14; }
QFileDialog QWidget { color: #e8e3f7; }
QFileDialog QLabel { color: #b9b2cf; background: transparent; }
QFileDialog QCheckBox { color: #b9b2cf; }
QFileDialog QLineEdit, QFileDialog QComboBox {
    background: #141020; color: #f4f1ff;
    border: 1px solid rgba(164,132,215,0.35); border-radius: 8px;
    padding: 5px 9px; selection-background-color: #7b39fc;
}
QFileDialog QLineEdit:focus, QFileDialog QComboBox:focus { border-color: #7b39fc; }
QFileDialog QComboBox::drop-down { border: 0; width: 20px; }
QFileDialog QComboBox QAbstractItemView {
    background: #141020; color: #f4f1ff; outline: 0;
    border: 1px solid rgba(164,132,215,0.35);
    selection-background-color: #7b39fc; selection-color: #ffffff;
}
QFileDialog QListView, QFileDialog QTreeView {
    background: #0f0c18; color: #e8e3f7; outline: 0;
    border: 1px solid rgba(164,132,215,0.22); border-radius: 10px;
}
QFileDialog QListView::item, QFileDialog QTreeView::item { padding: 5px 4px; border-radius: 6px; }
QFileDialog QListView::item:hover, QFileDialog QTreeView::item:hover { background: rgba(255,255,255,0.06); }
QFileDialog QListView::item:selected, QFileDialog QTreeView::item:selected {
    background: rgba(123,57,252,0.55); color: #ffffff;
}
QFileDialog QHeaderView::section {
    background: #141020; color: #9d97b5; border: 0;
    border-bottom: 1px solid rgba(164,132,215,0.22); padding: 5px 8px;
}
QFileDialog QPushButton {
    background: #2b2344; color: #e6e0f7;
    border: 1px solid rgba(164,132,215,0.35); border-radius: 8px;
    padding: 6px 16px; min-width: 84px;
}
QFileDialog QPushButton:hover { background: #352b54; border-color: rgba(164,132,215,0.6); }
QFileDialog QPushButton:default { background: #7b39fc; color: #0b0713; border-color: #7b39fc; }
QFileDialog QPushButton:default:hover { background: #6a2ce0; }
QFileDialog QToolButton {
    background: rgba(255,255,255,0.07); border: 1px solid rgba(164,132,215,0.22);
    border-radius: 6px; padding: 4px;
}
QFileDialog QToolButton:hover { background: rgba(123,57,252,0.28); border-color: rgba(164,132,215,0.45); }
QFileDialog QSplitter::handle { background: rgba(164,132,215,0.14); }
QFileDialog QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QFileDialog QScrollBar::handle:vertical { background: rgba(164,132,215,0.3); border-radius: 5px; min-height: 28px; }
QFileDialog QScrollBar::add-line, QFileDialog QScrollBar::sub-line { height: 0; }
QFileDialog QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QFileDialog QScrollBar::handle:horizontal { background: rgba(164,132,215,0.3); border-radius: 5px; min-width: 28px; }
"""


def dark_dialog(parent, title: str, start: str, name_filter: str,
                mode: QFileDialog.FileMode = QFileDialog.FileMode.ExistingFile) -> QFileDialog:
    """Тёмный диалог выбора файла/папки в стиле приложения."""
    dlg = QFileDialog(parent, title, start, name_filter)
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dlg.setFileMode(mode)
    if mode == QFileDialog.FileMode.Directory:
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dlg.setViewMode(QFileDialog.ViewMode.Detail)
    dlg.resize(1020, 680)
    dlg.setSidebarUrls([
        QUrl.fromLocalFile(str(ROOT)),
        QUrl.fromLocalFile(str(ROOT / "renders")),
        QUrl.fromLocalFile(str(Path.home())),
        QUrl.fromLocalFile(str(ROOT.parent)),
    ])
    pal = dlg.palette()
    for role, color in (
        (QPalette.ColorRole.Window, "#0d0b14"),
        (QPalette.ColorRole.WindowText, "#e8e3f7"),
        (QPalette.ColorRole.Base, "#0f0c18"),
        (QPalette.ColorRole.AlternateBase, "#141020"),
        (QPalette.ColorRole.Text, "#e8e3f7"),
        (QPalette.ColorRole.Button, "#2b2344"),
        (QPalette.ColorRole.ButtonText, "#e6e0f7"),
        (QPalette.ColorRole.Highlight, "#7b39fc"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.ToolTipBase, "#141020"),
        (QPalette.ColorRole.ToolTipText, "#f4f1ff"),
        (QPalette.ColorRole.PlaceholderText, "#6f6885"),
        (QPalette.ColorRole.Mid, "#2b2344"),
        (QPalette.ColorRole.Dark, "#08060d"),
        (QPalette.ColorRole.Shadow, "#000000"),
    ):
        pal.setColor(role, QColor(color))
    dlg.setPalette(pal)
    dlg.setStyleSheet(DIALOG_QSS)
    # две подписи Qt не переведены в qt_ru.qm — правим руками
    labels = {"&Look in:": "&Папка:", "Look in:": "Папка:",
              "Files of &type:": "&Тип файлов:", "Files of type:": "Тип файлов:"}
    for lbl in dlg.findChildren(QLabel):
        if lbl.text() in labels:
            lbl.setText(labels[lbl.text()])
    # шире колонка ярлыков, иначе «corrridor»/«renders» обрезаются
    for sp in dlg.findChildren(QSplitter):
        sp.setSizes([200, 620])
    # имя файла растягиваем — иначе «Размер» уезжает под горизонтальный скролл
    for tv in dlg.findChildren(QTreeView):
        hdr = tv.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return dlg


def ensure_qwebchannel() -> None:
    """qwebchannel.js лежит внутри Qt — вытаскиваем в ui/ при первом запуске."""
    target = UI / "qwebchannel.js"
    if target.exists():
        return
    from PySide6.QtCore import QFile, QIODevice

    src = QFile(":/qtwebchannel/qwebchannel.js")
    if src.open(QIODevice.OpenModeFlag.ReadOnly):
        target.write_bytes(bytes(src.readAll()))
        src.close()


def attach_ru(app: QApplication) -> None:
    """Русские строки внутри Qt-диалогов (Открыть, Отмена, Папка…)."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    tr = QTranslator(app)
    path = str(Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath)))
    if tr.load("qt_ru", path):
        app.installTranslator(tr)
        app._ru_translator = tr  # держим ссылку, иначе сборщик уберёт переводчик


def last_dir(kind: str) -> str:
    default = ROOT / ("renders" if kind == "output" else "test")
    return QSettings("CorridorKey", "UI").value(f"dir/{kind}", str(default), type=str)


def remember_dir(kind: str, path: str) -> None:
    if path:
        QSettings("CorridorKey", "UI").setValue(f"dir/{kind}", str(Path(path).parent))


def app_icon() -> QIcon:
    """Иконка приложения во всех размерах (иначе X11 не ставит _NET_WM_ICON)."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        path = ROOT / "ui" / f"icon-{size}.png"
        if path.is_file():
            icon.addFile(str(path))
    return icon


def gpu_label() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip().splitlines()[0]
        name, mb = [p.strip() for p in out.split(",")[:2]]
        name = name.replace("NVIDIA ", "").replace("GeForce ", "")
        return f"{name} · {round(int(mb) / 1024)} GB"
    except Exception:  # noqa: BLE001
        return "локальная GPU"


def daemon_alive(timeout: float = 0.6) -> bool:
    try:
        return requests.get(API + "/health", timeout=timeout).ok
    except requests.RequestException:
        return False


def start_daemon() -> bool:
    """Поднять демон в фоне и подождать /health."""
    if daemon_alive():
        return True
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = open(logs / "daemon.log", "a", buffering=1)  # noqa: SIM115
    subprocess.Popen(
        [str(VENV_PY), str(ROOT / "daemon.py")],
        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
        start_new_session=True,
    )
    for _ in range(60):
        if daemon_alive(0.4):
            return True
        time.sleep(0.3)
    return False


class Bridge(QObject):
    """Тонкий мост JS <-> Python для нативных действий."""

    def __init__(self, window: "Window") -> None:
        super().__init__()
        self.window = window

    @Slot(result=str)
    def gpuInfo(self) -> str:  # noqa: N802 (JS-имя)
        return self.window.gpu

    @Slot(str, result=str)
    def browseVideo(self, title: str = "") -> str:  # noqa: N802
        dlg = dark_dialog(self.window, title or "Клип для кеинга", last_dir("video"), MEDIA)
        path = dlg.selectedFiles()[0] if dlg.exec() and dlg.selectedFiles() else ""
        remember_dir("video", path)
        return path

    @Slot(str, result=str)
    def browseHint(self, title: str = "") -> str:  # noqa: N802
        dlg = dark_dialog(self.window, title or "Маска (хинт) первого кадра",
                          last_dir("hint"), "PNG (*.png)")
        path = dlg.selectedFiles()[0] if dlg.exec() and dlg.selectedFiles() else ""
        remember_dir("hint", path)
        return path

    @Slot(str, result=str)
    def browseOutputDir(self, title: str = "") -> str:  # noqa: N802
        dlg = dark_dialog(self.window, title or "Папка для результатов",
                          last_dir("output"), "", QFileDialog.FileMode.Directory)
        path = dlg.selectedFiles()[0] if dlg.exec() and dlg.selectedFiles() else ""
        if path:
            QSettings("CorridorKey", "UI").setValue("dir/output", path)
        return path

    @Slot(str, result=str)
    def browseBackground(self, title: str = "") -> str:  # noqa: N802
        dlg = dark_dialog(self.window, title or "Фон для композа", last_dir("bg"), BG_FILES)
        path = dlg.selectedFiles()[0] if dlg.exec() and dlg.selectedFiles() else ""
        remember_dir("bg", path)
        return path

    @Slot(str, result=str)
    def openFolder(self, path: str) -> str:  # noqa: N802
        p = Path(path)
        if p.is_file():
            p = p.parent
        if not p.exists():
            return "missing"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        return "ok"

    @Slot(result=str)
    def importResolve(self) -> str:  # noqa: N802
        client = ROOT / "resolve_client.py"
        if not client.exists():
            return "resolve_client.py не найден"
        env = os.environ.copy()
        env.update(RESOLVE_ENV)
        log = open(ROOT / "logs" / "resolve.log", "a", buffering=1)  # noqa: SIM115
        subprocess.Popen(
            [str(SYS_PY), str(client)], stdout=log, stderr=subprocess.STDOUT,
            cwd=ROOT, env=env, start_new_session=True,
        )
        return "Импорт запущен — нужен открытый Resolve Studio"

    @Slot(str, str, result=str)
    def composeResolve(self, job_id: str = "", bg: str = "") -> str:  # noqa: N802
        """Собрать Fusion-композ работы: субъект из `cutout`/fg+alpha поверх фона."""
        script = ROOT / "resolve_compose.py"
        if not script.exists():
            return "resolve_compose.py не найден"
        job_id = (job_id or "").strip()
        if not job_id:
            return "не выбрана работа — нажми на готовую в очереди"
        if not bg:
            return "не выбран фон — укажи картинку или видео"
        if not Path(bg).is_file():
            return f"фон не найден: {bg}"
        if not SYS_PY.exists():
            return "нет /usr/bin/python3.12 — Resolve-скрипты не запустятся"
        env = os.environ.copy()
        env.update(RESOLVE_ENV)
        log = open(ROOT / "logs" / "resolve.log", "a", buffering=1)  # noqa: SIM115
        subprocess.Popen(
            [str(SYS_PY), str(script), "--job", job_id, "--bg", bg],
            stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env,
            start_new_session=True,
        )
        return ("Композ собирается — Resolve должен быть запущен. "
                "Ход и ошибки: logs/resolve.log")

    @Slot(str, result=str)
    def openUrl(self, url: str) -> str:  # noqa: N802
        if url.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(url))
            return "ok"
        return "blocked"


class View(QWebEngineView):
    """WebEngine-вью с нативным drag&drop локальных файлов."""

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def _paths(self, event) -> list[str]:
        if not event.mimeData().hasUrls():
            return []
        return [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]

    def dragEnterEvent(self, event):  # noqa: N802
        if self._paths(event):
            event.acceptProposedAction()
            self.page().runJavaScript("window.ck && window.ck.drag(true)")
        else:
            super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):  # noqa: N802
        self.page().runJavaScript("window.ck && window.ck.drag(false)")
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        paths = self._paths(event)
        if paths:
            event.acceptProposedAction()
            payload = json.dumps(paths, ensure_ascii=False)
            self.page().runJavaScript(f"window.ck && window.ck.onDrop({payload})")
        else:
            super().dropEvent(event)


class Window(QMainWindow):
    def __init__(self, shot: str | None = None, size: str | None = None) -> None:
        super().__init__()
        self.gpu = gpu_label()
        self.shot = shot
        self.setWindowTitle("CorridorKey 2.0 — AI keying")
        icon = app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        w, h = 1380, 900
        if size and "x" in size:
            try:
                w, h = (int(v) for v in size.lower().split("x", 1))
            except ValueError:
                pass
        self.resize(w, h)
        self.setMinimumSize(900, 620)
        # Никакого setStyleSheet на окне: QSS каскадом уходит в дочерние диалоги
        # (QFileDialog становился чёрным с невидимым текстом). Фон задаём странице.
        self.view = View()
        self.view.page().setBackgroundColor(QColor("#000000"))
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        self.setCentralWidget(self.view)

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)

        self.channel = QWebChannel(self.view.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("ck", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # полноэкранный просмотр из плеера (Fullscreen API)
        self.view.page().fullScreenRequested.connect(self._fullscreen)

        self.view.load(QUrl(API + "/"))
        self.scroll = int(os.environ.get("CK_SCROLL", "0") or 0)
        if shot:
            QTimer.singleShot(4200, self._grab)

    def _fullscreen(self, request) -> None:
        request.accept()
        if request.toggleOn():
            self.showFullScreen()
        else:
            self.showNormal()

    def _grab(self) -> None:
        if self.scroll:
            self.view.page().runJavaScript(f"window.scrollTo(0,{self.scroll})")
            QTimer.singleShot(700, self._grab2)
            return
        self._grab2()

    def _grab2(self) -> None:
        pix = self.view.grab()
        pix.save(self.shot)
        print("shot:", self.shot, pix.width(), pix.height())
        QApplication.quit()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_F5:
            self.view.reload()
        elif event.matches(event.StandardKey.Quit):
            self.close()
        else:
            super().keyPressEvent(event)


def main() -> int:
    args = sys.argv[1:]

    if "--browser" in args:
        if not start_daemon():
            print("демон не поднялся, смотрите logs/daemon.log")
            return 1
        QDesktopServices.openUrl  # noqa: B018
        subprocess.Popen(["xdg-open", API + "/"])
        return 0

    ok = start_daemon()
    ensure_qwebchannel()
    sys.argv += ["-name", "corridorkey"]  # WM_CLASS для иконки в панели задач
    app = QApplication(sys.argv)
    app.setApplicationName("CorridorKey")
    app.setDesktopFileName("corridorkey")
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    attach_ru(app)
    shot = None
    if "--shot" in args:
        shot = args[args.index("--shot") + 1] if len(args) > args.index("--shot") + 1 else "ui.png"
    size = args[args.index("--size") + 1] if "--size" in args and len(args) > args.index("--size") + 1 else None
    win = Window(shot=shot, size=size)
    win.show()
    if not ok:
        print("демон не отвечает: интерфейс откроется без данных (logs/daemon.log)")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
