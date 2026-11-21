# CorridorKey 2.0 для Linux: апп + плагин DaVinci Resolve Studio

Локальный комплекс поверх бесплатного инференса [CorridorKey2.0](https://github.com/nikopueringer/CorridorKey2.0)
(веса+код от Corridor Digital, CC BY-NC-SA + доп. условия: коммерческое использование
РЕЗУЛЬТАТОВ разрешено; перепродажа тула и платный инференс-сервис — нет;
форки публичны и бесплатны — этот проект им соответствует).

## Состав

- `daemon.py` — демон на FastAPI (`:8129`): очередь задач, запуск `infer.py`,
  прогресс, манифест готовых работ, health. Дополнительно: `/stats` (CPU/RAM/VRAM),
  `/jobs/{id}/frame` (JPEG-кадр для живого превью), `/jobs/{id}/result`,
  `/jobs/{id}/media/{file}` (готовые файлы с поддержкой Range) и `/jobs/{id}/source`.
- `app.py` — окно приложения (PySide6 + QtWebEngine): загружает локальный
  интерфейс из демона, добавляет нативный drag&drop файлов, системные диалоги,
  «открыть папку» и запуск импорта в Resolve (мост QWebChannel).
- `ui/` — интерфейс (HTML/CSS/JS, RU) в стиле Datacore: тёмная тема, фиолетовый
  акцент, стеклянные бейджи, живой фон-сеть частиц. Все шрифты (Manrope, Inter,
  Instrument Serif, JetBrains Mono) лежат локально в `ui/fonts`, интернет не нужен.
  Открывается и просто в браузере: http://127.0.0.1:8129/
- `resolve_client.py` — импорт готовой работы в DaVinci Resolve Studio через
  официальный Scripting API (нужен Preferences → System → General →
  **External scripting using = Local**).
- `CorridorKey2.0/` — официальный рантайм (клон), веса в `weights/`, `vfms/`.

## Установка (уже выполнена)

```bash
cd corridorkey-linux
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install torch==2.9.1 torchvision==0.24.1 \
  --index-url https://download.pytorch.org/whl/cu128
VIRTUAL_ENV=.venv uv pip install -r CorridorKey2.0/requirements.txt
VIRTUAL_ENV=.venv uv pip install fastapi "uvicorn[standard]" PySide6 requests
(cd CorridorKey2.0 && ../.venv/bin/python scripts/download_weights.py)
```

## Запуск

```bash
./run.sh              # демон (если не запущен) + окно приложения
.venv/bin/python app.py --browser   # тот же интерфейс в браузере по умолчанию
```

или раздельно:

```bash
.venv/bin/python daemon.py          # демон :8129
.venv/bin/python app.py             # GUI
```

Стартовые промпты для следующей сессии — `NEXT_SESSION.md`.

## Как работает интерфейс

1. **Клип** — «Добавить клип» / drag&drop только складывают файлы в список (чипы),
   ничего не запускается.
2. **Папка результата** — необязательная; рендер ляжет в `<папка>/<клип>_<jobid>/`
   (по умолчанию `renders/<клип>_<jobid>/`).
3. **Старт** — большая кнопка запускает все выбранные клипы; рядом «Стоп» отменяет
   текущую задачу. Пока клип не выбран, «Старт» неактивен.
4. **Превью** — во время рендера показывает кадр исходника в реальном времени
   (обновление ~1.2 с по мере прохождения окон модели), после завершения
   превращается в плеер: Alpha / FG / Source, перемотка по кадрам.
5. **Язык** — переключатель EN/RU в шапке; по умолчанию **английский**.
6. **Ресурсы** — CPU / RAM / VRAM с полосками в шапке (обновление 1.5 с).
7. **Drag&drop** — работает по всему окну и по области с заголовком (подсвечивается),
   клик по ней открывает выбор файла.
8. **Полный экран** — кнопка в плеере: настоящий Fullscreen API, при отказе
   (нет user gesture) — «кинорежим» поверх окна с крестиком/Esc.
9. **Очередь** — у активных задач кнопка ✕ отменяет задачу, у завершённых/отменённых
   она превращается в корзину и убирает запись из очереди и `manifest.json`
   (файлы на диске остаются).
10. **Иконка** — `ui/icon*.png` + ярлык `~/.local/share/applications/corridorkey.desktop`
    (WM_CLASS `corridorkey`), значок в панели совпадает с логотипом в шапке.

- Без хинта первого кадра модель на реальном фоне часто цепляется за задний план —
  в настройках об этом висит предупреждение.
- QtWebEngine собран **без H.264**, поэтому mp4 в `<video>` не играет. Демон по
  запросу перекодирует результат в WebM/VP9 (`/jobs/{id}/preview?kind=alpha|fg|source`,
  720p, кэш в папке задачи), и плеер играет уже его; статус/прогресс — `/jobs/{id}/preview/status`.

## Проверено

- Новый интерфейс: очередь, карточка запуска, настройки, журнал; выбор клипа
  без автостарта, кнопки «Старт»/«Стоп», папка результата, живое превью и плеер
  (Alpha/FG/Source, перемотка по кадрам), переключатель EN/RU (дефолт EN),
  метрики CPU/RAM/VRAM.
- Проверено прогоном: drag&drop нативным событием Qt, постановка в очередь по
  «Старт», живой кадр во время рендера, плеер после завершения (кадр 12/24),
  отмена задачи, импорт в Resolve, перезапуск демона подхватывает историю из
  `renders/manifest.json`.
- Прогресс теперь растёт: `infer.py` запускается с `-u` и `PYTHONUNBUFFERED=1`,
  строки «window i/N» видны сразу (на однооконных тестах полоса идёт как
  indeterminate, поэтому она анимирована).
- `scripts/smoke_test_runtime.py` — чекпоинт валиден.
- E2E: синтетический гринскрин 1280x720, 12 кадров, hint первого кадра →
  альфа с отслеживанием движения (bbox 200→419). VRAM пик ~7.5 ГБ из 16.

## Ограничения /Known issues

- No-hint режим на однотонном гринскрине может не выбрать субъект —
  это поведение модели, используйте хинт первого кадра.
- Resolve: импорт требует запущенного Resolve Studio и «External scripting = Local».
- Модель по умолчанию бержет VRAM у Resolve: запускайте рендер плагина,
  когда очередь демона пуста.

## Backup policy

Перед любыми изменениями кода: `cp <file> backups/<file>.YYYY-MM-DD.bak`
(плоско в `backups/`). Перед крупными переделками — полная копия папки
в `backups/full-project/YYYY-MM-DD/`.

## Что добавлено 21.11 (вторая половина дня)

- **Живая очередь**: `renders/queue.json` пишется на каждом переходе статуса
  (`_save_queue`), при старте `_load_queue` возвращает незавершённые задачи как
  `interrupted` с сохранённым `cmd`; `POST /jobs/{id}/retry` перезапускает их тем же
  `cmd`. Демон регистрирует `atexit`-хук и гасит свой инференс при выходе — иначе
  осиротевший процесс держит VRAM и следующий запуск падает по OOM.
- **Живая маска**: `infer_live.py` подменяет `write_many` у
  `corridorkey.video_io.ThreadedVideoWriter`/`ExrSequenceWriter` (клон апстрима не
  правится) и кладёт `_live_alpha.jpg` (880 px, tmp+rename) после каждого окна;
  демон запускает `infer_live.py` вместо `infer.py` и отдаёт кадр через
  `GET /jobs/{id}/live` (заголовок `X-CK-Kind: alpha|source`), UI берёт его через
  `fetch` → blob, иначе `<img>` с blob-URL течёт.
- **Профили VRAM** в UI: Auto / 720p 80/40 / 1080p 48/24 low / 1440p 24/12 low /
  4K 8/4 low / Custom; пресет блокирует чекбокс Low VRAM и уходит в payload как
  `hann_chunk`/`hann_stride` (+`low_vram`).
- **`resolve_compose.py`**: авто-сборка композа в Fusion через Resolve Scripting API
  (Loader плашки + Loader cutout/fg/alpha + Merge + MatteControl → MediaOut),
  `--bg` для нового фона, `--dry-run`, самопроверка связей.

## Грабли Resolve / Fusion API (проверено на 21.1)

- `tool.GetInput("Background")` возвращает **None даже при рабочей связи** — судить
  только по `INPB_Connected` у объекта входа (`GetInputList()`).
- `SetInput` для картиночных входов работает, но вложенные имена (`Garbage.Matte`)
  надо ставить именно через `SetInput`, а простые (`Background`) можно и атрибутом.
- `EffectMask` у Merge маскирует **весь** результат, включая фон: маску на вход
  ставить нельзя, только на сам foreground (MatteControl).
- У MatteControl «Garbage Matte» снимает то, что **внутри** маски → нужен
  `Garbage.MaskInverted = 1`; премультиплай — `PostMultiplyImage = 1`.
  `MultiplyGarbageMatte` гасит субъект в ноль, не использовать.
- `comp.Save(path)` **переименовывает** композицию по имени файла — как проверку
  не использовать.
- Одиночная картинка в Loader живёт только на кадре 0 (GlobalEnd=1): статичный фон
  превращать в короткий клип (`-loop 1 -t <длительность плашки>`), иначе кадры за
  первым — чёрные.
- Resolve пишет рендер только в разрешённые папки (`/mnt/Purple/Projects`), чужой
  `TargetDir` в `SetRenderSettings` молча игнорируется.
- Композиция клипа создаётся только после `resolve.OpenPage("fusion")` при активном
  клипе таймлайна; до этого `fusion.GetCurrentComp()` возвращает None.

