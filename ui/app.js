/* CorridorKey UI — queue, settings, live preview, player. Talks to the local daemon on :8129. */
(() => {
  "use strict";

  const API = location.protocol.startsWith("http") ? location.origin : "http://127.0.0.1:8129";
  const LSK = "ck.settings.v3";
  const LSL = "ck.lang";
  const $ = (s) => document.querySelector(s);

  /* ── i18n ───────────────────────────────────────────────────────────── */
  const I18N = {
    en: {
      nav_queue: "Queue", nav_settings: "Settings", nav_log: "Log", nav_resolve: "Resolve",
      hero_badge: "Subject tracking from a first-frame hint",
      hero_h1: "Precise mattes.",
      hero_lede: "CorridorKey 2.0 computes alpha and foreground on your own GPU: green or blue screen without manual keying, EXR sequences for compositing, and import into DaVinci Resolve.",
      btn_add: "Add clip", btn_add_short: "Add", btn_resolve: "Build comp in Resolve",
      btn_compose: "Build comp in Resolve", f_bg: "Background", f_bg_ph: "image or video",
      ck_status: "Comp goes to the clip under the playhead of the open timeline.",
      btn_choose: "Choose clip", btn_start: "Start", btn_import: "Import finished jobs",
      meta_model: "Model", meta_vram: "VRAM peak", meta_license: "License",
      st_connecting: "connecting…", st_online: "daemon online", st_rendering: "rendering", st_offline: "daemon offline",
      queue_title: "Job queue", log_title: "Log", log_none: "no active job", log_empty: "— inference output appears here —",
      empty_title: "Queue is empty",
      empty_text: "Drop a clip into the window or pick a file — then press Start.",
      settings_title: "Advanced", run_title: "Render",
      run_hint: "Pick clips first, then press Start — nothing renders until you do.",
      f_clip: "Clip", f_clip_ph: "no clip selected",
      f_output: "Output folder", f_output_ph: "default: renders/",
      f_outputs: "Outputs", out_af: "alpha + fg", out_all: "alpha + fg + checker + cutout",
      f_hint: "First-frame hint", f_hint_ph: "subject matte, frame 1",
      f_profile: "VRAM profile",
      prof_auto: "Auto — measure free VRAM",
      prof_720: "720p — hann 80/40",
      prof_1080: "1080p — hann 48/24 · low VRAM",
      prof_1440: "1440p — hann 24/12 · low VRAM",
      prof_4k: "4K — hann 8/4 · low VRAM",
      prof_custom: "Custom — Low VRAM flag only",
      prof_hint_auto: "auto: 720p → 80/40, 1080p → 48/24 low VRAM, 4K → 8/4 low VRAM",
      prof_hint_720: "720p · 80/40 — peak ~7.5 GB (measured)",
      prof_hint_1080: "1080p · 48/24 + low VRAM — needs >16 GB for bigger windows",
      prof_hint_1440: "1440p · 24/12 + low VRAM — short windows, good consistency",
      prof_hint_4k: "4K · 8/4 + low VRAM — slowest, smallest window",
      prof_hint_custom: "low VRAM staging from the checkbox, window auto-selected",
      f_hint_q: "Hint quality", f_despill: "Despill",
      f_frames: "Frames (test)", f_frames_hint: "0 = all", f_frames_ph: "all",
      resolve_text: "Builds a Fusion comp for the selected finished job — cutout (RGBA) over your background, four nodes. Resolve must be running with <b>External scripting = Local</b>.",
      kv_renders: "renders", kv_manifest: "manifest",
      foot_note: "Results may be used commercially · reselling the tool is not allowed · 2026",
      drop_title: "Drop to add a clip",
      pv_title: "PREVIEW", pv_idle: "No clip in the preview",
      pv_idle_hint: "Pick a clip, press Start — frames appear here live.",
      k_source: "Source",
      title_pick_clip: "Pick clip", title_pick_hint: "Pick PNG", title_pick_dir: "Pick folder", title_stop: "Stop",
      title_fs: "Fullscreen", title_cancel: "Cancel job", title_delete: "Remove from queue",
      hero_drop: "Drag a video into this area — or click to choose a file",
      pv_prep: "preparing preview", pv_prep_fail: "Could not prepare the preview",
      t_deleted: "Removed from the queue", t_delete_err: "Could not remove: {e}",
      dlg_clip: "Clip to key", dlg_hint: "First-frame hint matte", dlg_out: "Output folder",
      dlg_bg: "Background for the comp", title_pick_bg: "Pick background",
      s_queued: "queued", s_running: "rendering", s_done: "done", s_failed: "failed", s_cancelled: "cancelled",
      s_interrupted: "interrupted",
      title_retry: "Run again", t_retried: "Queued again: {n}", t_retry_err: "Retry failed: {e}",
      pv_live_alpha: "ALPHA · live matte", pv_live_source: "SOURCE · live",
      t_added: "Added: {n}", t_exists: "Already in the list: {n}",
      t_need_clip: "Add a clip first", t_queued: "{n} job(s) queued",
      t_bad_file: "Need a video file: mp4, mov, mkv, mxf",
      t_cancel: "Cancelling…", t_cancel_err: "Cancel failed: {e}",
      t_submit_err: "Could not start: {e}", t_hint: "Hint: {n}", t_out: "Output folder: {n}",
      t_import: "Import started — Resolve must be open",
      t_compose: "Building the comp — Resolve must be open",
      t_no_job: "Pick a finished job in the queue first",
      t_no_bg: "Pick a background first",
      t_bg: "Background: {n}",
      t_no_bridge: "Available in the desktop app",
      t_frame: "frame {i} / {n}", t_pct: "{p}%",
      pv_live: "live", pv_result: "RESULT", pv_no_result: "no alpha/fg result yet",
      hint_warn: "No hint: the model may lock onto the background instead of the subject.",
      pv_meta: "{w}×{h} · {fps} fps · {d}s",
      lang: "Language",
    },
    ru: {
      nav_queue: "Очередь", nav_settings: "Настройки", nav_log: "Журнал", nav_resolve: "Resolve",
      hero_badge: "Отслеживание субъекта по хинту кадра",
      hero_h1: "Точная матовка.",
      hero_lede: "CorridorKey 2.0 считает альфу и foreground прямо на вашей GPU: грин- и блюскрин без ручной настройки ключей, EXR-секвенции для композа и импорт в DaVinci Resolve.",
      btn_add: "Добавить клип", btn_add_short: "Добавить", btn_resolve: "Композ в Resolve",
      btn_compose: "Собрать композ в Resolve", f_bg: "Фон", f_bg_ph: "картинка или видео",
      ck_status: "Композ ставится на клип под плейхедом открытого таймлайна.",
      btn_choose: "Выбрать клип", btn_start: "Старт", btn_import: "Импортировать готовые",
      meta_model: "Модель", meta_vram: "VRAM пик", meta_license: "Лицензия",
      st_connecting: "подключение…", st_online: "демон online", st_rendering: "рендер идёт", st_offline: "демон offline",
      queue_title: "Очередь задач", log_title: "Журнал", log_none: "нет активной задачи", log_empty: "— вывод инференса появится здесь —",
      empty_title: "Очередь пуста",
      empty_text: "Перетащите клип в окно или выберите файл — затем нажмите «Старт».",
      settings_title: "Дополнительно", run_title: "Запуск",
      run_hint: "Сначала добавьте клипы, потом нажмите «Старт» — без нажатия рендер не начнётся.",
      f_clip: "Клип", f_clip_ph: "клип не выбран",
      f_output: "Папка результата", f_output_ph: "по умолчанию: renders/",
      f_outputs: "Выходы", out_af: "alpha + fg", out_all: "alpha + fg + checker + cutout",
      f_hint: "Хинт первого кадра", f_hint_ph: "маска субъекта, кадр 1",
      f_profile: "Профиль VRAM",
      prof_auto: "Авто — по свободной VRAM",
      prof_720: "720p — hann 80/40",
      prof_1080: "1080p — hann 48/24 · low VRAM",
      prof_1440: "1440p — hann 24/12 · low VRAM",
      prof_4k: "4K — hann 8/4 · low VRAM",
      prof_custom: "Свой — только флаг Low VRAM",
      prof_hint_auto: "авто: 720p → 80/40, 1080p → 48/24 low VRAM, 4K → 8/4 low VRAM",
      prof_hint_720: "720p · 80/40 — пик ~7.5 ГБ (замерено)",
      prof_hint_1080: "1080p · 48/24 + low VRAM — окно больше требует >16 ГБ",
      prof_hint_1440: "1440p · 24/12 + low VRAM — короткие окна, стабильно",
      prof_hint_4k: "4K · 8/4 + low VRAM — медленнее всего, окно минимальное",
      prof_hint_custom: "low VRAM из чекбокса, окно подберётся автоматически",
      f_hint_q: "Качество хинта", f_despill: "Despill",
      f_frames: "Кадров (тест)", f_frames_hint: "0 = все", f_frames_ph: "все",
      resolve_text: "Собирает Fusion-композ для выбранной готовой работы: cutout (RGBA) поверх фона, четыре ноды. Нужен запущенный Resolve и <b>External scripting = Local</b>.",
      kv_renders: "рендеров", kv_manifest: "манифест",
      foot_note: "Результаты можно использовать коммерчески · перепродажа тула запрещена · 2026",
      drop_title: "Отпустите, чтобы добавить клип",
      pv_title: "ПРЕДПРОСМОТР", pv_idle: "Клип не выбран",
      pv_idle_hint: "Выберите клип и нажмите «Старт» — кадры появятся здесь в реальном времени.",
      k_source: "Исходник",
      title_pick_clip: "Выбрать клип", title_pick_hint: "Выбрать PNG", title_pick_dir: "Выбрать папку", title_stop: "Стоп",
      title_fs: "На весь экран", title_cancel: "Отменить задачу", title_delete: "Убрать из очереди",
      hero_drop: "Перетащите видео в эту область — или нажмите, чтобы выбрать файл",
      pv_prep: "готовлю предпросмотр", pv_prep_fail: "Не удалось подготовить предпросмотр",
      t_deleted: "Убрано из очереди", t_delete_err: "Не удалось убрать: {e}",
      dlg_clip: "Клип для кеинга", dlg_hint: "Маска (хинт) первого кадра", dlg_out: "Папка для результатов",
      dlg_bg: "Фон для композа", title_pick_bg: "Выбрать фон",
      s_queued: "в очереди", s_running: "рендер", s_done: "готово", s_failed: "ошибка", s_cancelled: "отменено",
      s_interrupted: "прервано",
      title_retry: "Запустить снова", t_retried: "Снова в очереди: {n}", t_retry_err: "Повтор не удался: {e}",
      pv_live_alpha: "АЛЬФА · живая маска", pv_live_source: "ИСХОДНИК · live",
      t_added: "Добавлено: {n}", t_exists: "Уже в списке: {n}",
      t_need_clip: "Сначала добавьте клип", t_queued: "В очереди задач: {n}",
      t_bad_file: "Нужен видеофайл: mp4, mov, mkv, mxf",
      t_cancel: "Отменяю…", t_cancel_err: "Отмена не удалась: {e}",
      t_submit_err: "Не удалось запустить: {e}", t_hint: "Хинт: {n}", t_out: "Папка результата: {n}",
      t_import: "Импорт запущен — Resolve должен быть открыт",
      t_compose: "Композ собирается — Resolve должен быть открыт",
      t_no_job: "Сначала выбери готовую работу в очереди",
      t_no_bg: "Сначала выбери фон",
      t_bg: "Фон: {n}",
      t_no_bridge: "Доступно в приложении",
      t_frame: "кадр {i} / {n}", t_pct: "{p}%",
      pv_live: "в процессе", pv_result: "РЕЗУЛЬТАТ", pv_no_result: "результата alpha/fg пока нет",
      hint_warn: "Без хинта модель может зацепиться за фон вместо субъекта.",
      pv_meta: "{w}×{h} · {fps} fps · {d} с",
      lang: "Язык",
    },
  };

  let lang = localStorage.getItem(LSL) || "en";
  const t = (k, vars) => {
    let s = (I18N[lang] && I18N[lang][k]) || (I18N.en[k] || k);
    if (vars) for (const [kk, vv] of Object.entries(vars)) s = s.replaceAll("{" + kk + "}", vv);
    return s;
  };

  function applyI18n() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => (el.innerHTML = t(el.dataset.i18n)));
    document.querySelectorAll("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const v = t(el.dataset.i18nTitle);
      el.title = v;
      if (el.hasAttribute("aria-label")) el.setAttribute("aria-label", v);
    });
    $("#lang").value = lang;
    renderPending();
    renderJobs(true);
    refreshPreview(true);
    if (typeof syncProfile === "function") syncProfile();
  }

  /* ── state ──────────────────────────────────────────────────────────── */
  const state = {
    pending: [],
    jobs: [],
    selected: null,
    bridge: null,
    stats: null,
    pv: { jobId: null, mode: "idle", kind: "alpha", result: null, timer: 0, poll: 0, lastFrame: -1, home: null, next: null },
    nodes: new Map(),
    sig: "",
    lastClip: "",
  };

  const $video = $("#pv-video");
  const $img = $("#pv-img");
  const $seek = $("#pv-seek");

  /* ── helpers ────────────────────────────────────────────────────────── */
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const ICON_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  const ICON_TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M10 4h4"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M10 11v6M14 11v6"/></svg>';
  const ICON_RETRY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3.2-6.9"/><path d="M21 4v5h-5"/></svg>';
  const base = (p) => String(p || "").split(/[\\/]/).filter(Boolean).pop() || String(p || "");
  const gb = (mib) => (mib / 1024).toFixed(1);

  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "toast" + (kind === "err" ? " err" : "");
    el.innerHTML = "<i></i><span></span>";
    el.querySelector("span").textContent = msg;
    $("#toasts").appendChild(el);
    const kill = () => { el.classList.add("out"); setTimeout(() => el.remove(), 260); };
    setTimeout(kill, kind === "err" ? 5200 : 3200);
    el.addEventListener("click", kill);
  }

  async function api(path, opts) {
    const r = await fetch(API + path, Object.assign({ cache: "no-store" }, opts || {}));
    const txt = await r.text();
    let data = null;
    try { data = txt ? JSON.parse(txt) : null; } catch (_) { data = txt; }
    if (!r.ok) throw new Error((data && data.detail) || txt || "HTTP " + r.status);
    return data;
  }

  function call(fn, ...args) {
    return new Promise((resolve, reject) => {
      try {
        const ret = fn(...args, (v) => resolve(v));
        if (ret && typeof ret.then === "function") ret.then(resolve, reject);
      } catch (e) { reject(e); }
    });
  }

  /* ── settings ───────────────────────────────────────────────────────── */
  const S = {
    profile: $("#profile"),
    outputs: $("#outputs"),
    hint: $("#hint"),
    hintQ: $("#hint-q"),
    despill: $("#despill"),
    frames: $("#num-frames"),
    exr: $("#exr"),
    lowVram: $("#low-vram"),
    outdir: $("#outdir"),
    bg: $("#ck-bg"),
  };

  /* профили из таблицы upstream «Long Clips And Low VRAM» (16 ГБ: 720p 80/40,
     1080p 48/24 low-VRAM, 1440p 24/12 low-VRAM, 4K 8/4 low-VRAM) */
  const PROFILES = {
    auto: {},
    "720": { hann_chunk: 80, hann_stride: 40 },
    "1080": { hann_chunk: 48, hann_stride: 24, low_vram: true },
    "1440": { hann_chunk: 24, hann_stride: 12, low_vram: true },
    "4k": { hann_chunk: 8, hann_stride: 4, low_vram: true },
  };

  function syncProfile() {
    const p = S.profile.value;
    const preset = PROFILES[p];
    const lock = !!preset;
    S.lowVram.disabled = lock;
    if (preset) S.lowVram.checked = !!preset.low_vram;
    $("#profile-hint").textContent = t("prof_hint_" + (p === "4k" ? "4k" : p));
  }

  function readSettings() {
    return {
      profile: S.profile.value,
      outputs: S.outputs.value,
      hint: S.hint.value.trim(),
      hint_quality: parseFloat(S.hintQ.value),
      despill: parseFloat(S.despill.value),
      num_frames: parseInt(S.frames.value, 10) || 0,
      exr: S.exr.checked,
      low_vram: S.lowVram.checked,
      output_dir: S.outdir.value.trim(),
      bg: S.bg.value.trim(),
      lang,
    };
  }

  const saveSettings = () => { try { localStorage.setItem(LSK, JSON.stringify(readSettings())); } catch (_) {} };

  function loadSettings() {
    let v = null;
    try { v = JSON.parse(localStorage.getItem(LSK) || "null"); } catch (_) {}
    if (!v) return;
    if (v.outputs) S.outputs.value = v.outputs;
    if (v.profile && PROFILES[v.profile] !== undefined) S.profile.value = v.profile;
    if (v.hint) S.hint.value = v.hint;
    if (typeof v.hint_quality === "number") S.hintQ.value = v.hint_quality;
    if (typeof v.despill === "number") S.despill.value = v.despill;
    if (v.num_frames) S.frames.value = v.num_frames;
    if (v.output_dir) S.outdir.value = v.output_dir;
    if (v.bg) S.bg.value = v.bg;
    S.exr.checked = !!v.exr;
    S.lowVram.checked = !!v.low_vram;
  }

  function syncHintWarn() {
    $("#hint-warn").hidden = !!S.hint.value.trim();
  }

  function syncSliders() {
    $("#hint-q-out").textContent = (+S.hintQ.value).toFixed(2);
    $("#despill-out").textContent = (+S.despill.value).toFixed(2);
    for (const r of [S.hintQ, S.despill]) {
      const pct = ((+r.value - +r.min) / (+r.max - +r.min)) * 100;
      r.style.setProperty("--fill", pct + "%");
    }
  }

  /* ── pending clips ──────────────────────────────────────────────────── */
  function renderPending() {
    const host = $("#pending");
    host.innerHTML = "";
    state.pending.forEach((p, i) => {
      const chip = document.createElement("span");
      chip.className = "pchip mono";
      chip.innerHTML = `<span class="pname"></span><button class="px" aria-label="remove">×</button>`;
      chip.querySelector(".pname").textContent = base(p);
      chip.querySelector(".px").addEventListener("click", (e) => {
        e.preventDefault();
        state.pending.splice(i, 1);
        renderPending();
      });
      host.appendChild(chip);
    });
    const clipInput = $("#clip");
    clipInput.value = state.pending.length
      ? `${state.pending.length} × ${base(state.pending[0])}`
      : (state.lastClip ? base(state.lastClip) : "");
    $("#btn-start").disabled = state.pending.length === 0;
  }

  function addClip(path) {
    if (!path) return;
    if (!/\.(mp4|mov|mkv|mxf|avi)$/i.test(path)) return toast(t("t_bad_file"), "err");
    if (state.pending.includes(path)) return toast(t("t_exists", { n: base(path) }), "err");
    state.pending.push(path);
    renderPending();
    toast(t("t_added", { n: base(path) }));
  }

  /* ── jobs ───────────────────────────────────────────────────────────── */
  function jobNode(j) {
    const el = document.createElement("div");
    el.className = "job";
    el.setAttribute("role", "listitem");
    el.dataset.id = j.id;
    el.innerHTML = `
      <span class="dot" aria-hidden="true"></span>
      <div class="job-main">
        <div class="name"></div>
        <div class="meta"></div>
      </div>
      <div class="progress"><div class="bar"><i></i></div></div>
      <div class="pct">0%</div>
      <div class="job-actions">
        <button class="mini retry" data-act="retry" hidden aria-label="retry"></button>
        <button class="mini" data-act="folder" aria-label="open folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        </button>
        <button class="mini kill" data-act="kill" data-kill="cancel" aria-label="cancel"></button>
      </div>`;
    el.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (btn) {
        e.stopPropagation();
        if (btn.dataset.act === "kill") {
          if (btn.dataset.kill === "delete") deleteJob(j.id); else cancelJob(j.id);
        } else if (btn.dataset.act === "retry") {
          retryJob(j.id);
        } else openFolder(j.output_dir);
        return;
      }
      state.selected = j.id;
      renderJobs(true);
      refreshPreview(true);
    });
    return el;
  }

  function updateJobNode(el, j) {
    el.dataset.status = j.status;
    el.querySelector(".name").textContent = base(j.input);
    const outs = (j.outputs || []).join("+") || "alpha";
    const stamp = j.finished_at ? new Date(j.finished_at * 1000).toLocaleTimeString(lang === "ru" ? "ru-RU" : "en-US") : "";
    el.querySelector(".meta").textContent = `${t("s_" + j.status)} · ${outs}` + (stamp ? ` · ${stamp}` : "");
    const pct = Math.max(0, Math.min(100, j.progress || 0));
    const indet = j.status === "running" && pct < 1;
    el.dataset.indet = indet ? "1" : "0";
    el.querySelector(".bar > i").style.width = indet ? "34%" : pct.toFixed(1) + "%";
    el.querySelector(".pct").textContent = Math.round(pct) + "%";
    el.querySelector('[data-act="folder"]').style.opacity = j.status === "done" ? "1" : ".3";
    const kill = el.querySelector('[data-act="kill"]');
    const finished = j.status === "done" || j.status === "failed" ||
      j.status === "cancelled" || j.status === "interrupted";
    kill.dataset.kill = finished ? "delete" : "cancel";
    kill.title = finished ? t("title_delete") : t("title_cancel");
    kill.setAttribute("aria-label", kill.title);
    kill.innerHTML = finished ? ICON_TRASH : ICON_X;
    const retry = el.querySelector('[data-act="retry"]');
    retry.hidden = !(j.status === "failed" || j.status === "cancelled" || j.status === "interrupted");
    if (!retry.hidden && !retry.innerHTML) {
      retry.innerHTML = ICON_RETRY;
      retry.title = t("title_retry");
      retry.setAttribute("aria-label", retry.title);
    }
  }

  function renderJobs(force) {
    const host = $("#jobs");
    $("#job-count").textContent = String(state.jobs.length);
    $("#kv-done").textContent = String(state.jobs.filter((j) => j.status === "done").length);

    if (!state.jobs.length) {
      host.innerHTML = "";
      state.nodes.clear();
      $("#empty").hidden = false;
      $("#log-target").textContent = t("log_none");
      $("#log-body").textContent = t("log_empty");
      return;
    }
    $("#empty").hidden = true;

    const seen = new Set();
    let prev = null;
    for (const j of state.jobs) {
      seen.add(j.id);
      let el = state.nodes.get(j.id);
      if (!el) { el = jobNode(j); state.nodes.set(j.id, el); }
      updateJobNode(el, j);
      const want = prev ? prev.nextSibling : host.firstChild;
      if (el !== want) host.insertBefore(el, want || null);
      prev = el;
    }
    for (const [id, el] of state.nodes) if (!seen.has(id)) { el.remove(); state.nodes.delete(id); }

    if (!state.selected || !seen.has(state.selected)) {
      state.selected = (state.jobs.find((j) => j.status === "running") || state.jobs[0]).id;
    }
    for (const [id, el] of state.nodes) el.classList.toggle("sel", id === state.selected);
    renderLog(force);
  }

  /* выбранная работа в очереди (её id держит state.selected) */
  const selJob = () => state.jobs.find((x) => x.id === state.selected) || null;

  function renderLog(force) {
    const j = state.jobs.find((x) => x.id === state.selected);
    const body = $("#log-body");
    if (!j) { $("#log-target").textContent = t("log_none"); return; }
    $("#log-target").textContent = `${j.id} · ${t("s_" + j.status)}`;
    const lines = (j.log_tail || []).slice(-14);
    const txt = lines.length ? lines.join("\n") : t("log_empty");
    if (body.textContent !== txt || force) {
      body.textContent = txt;
      body.scrollTop = body.scrollHeight;
    }
  }

  /* ── preview ────────────────────────────────────────────────────────── */
  function selectedJob() {
    return state.jobs.find((j) => j.id === state.selected) || null;
  }

  function showIdle(badge) {
    stopLive();
    state.pv.mode = "idle";
    state.pv.jobId = null;
    if ($img.dataset.url) { URL.revokeObjectURL($img.dataset.url); $img.dataset.url = ""; }
    $img.removeAttribute("src");
    $("#pv-idle").hidden = false;
    $img.hidden = true;
    $video.pause();
    $video.hidden = true;
    $video.removeAttribute("src");
    $("#pv-controls").hidden = true;
    $("#pv-stage").classList.remove("paused");
    exitCinema();
    $("#pv-title").textContent = t("pv_title");
    $("#pv-chip-res").textContent = "—";
    $("#pv-chip-fmt").textContent = "—";
    $("#pv-meta").textContent = "—";
    $("#pv-dir").textContent = "";
    const b = $("#pv-badge");
    if (badge) { b.hidden = false; b.textContent = badge; } else { b.hidden = true; }
  }

  function stopLive() {
    if (state.pv.timer) { clearInterval(state.pv.timer); state.pv.timer = 0; }
    if (state.pv.poll) { clearInterval(state.pv.poll); state.pv.poll = 0; }
  }

  function startLive(job) {
    if (state.pv.mode === "live" && state.pv.jobId === job.id && state.pv.timer) return;
    stopLive();
    state.pv = Object.assign(state.pv, { mode: "live", jobId: job.id, result: null });
    if ($img.dataset.url) { URL.revokeObjectURL($img.dataset.url); $img.dataset.url = ""; }
    $("#pv-idle").hidden = true;
    $video.pause();
    $video.hidden = true;
    $("#pv-img").hidden = false;
    $("#pv-controls").hidden = true;
    $("#pv-stage").classList.remove("paused");
    $("#pv-title").textContent = "LIVE · " + base(job.input);
    const m = job.media || {};
    $("#pv-chip-res").textContent = m.width ? `${m.width}×${m.height}` : "—";
    $("#pv-chip-fmt").textContent = "source";
    $("#pv-dir").textContent = "";
    const tick = async () => {
      const cur = state.jobs.find((x) => x.id === job.id) || job;
      if (cur.status !== "running" && cur.status !== "queued") { stopLive(); return refreshPreview(); }
      const fps = (cur.media && cur.media.fps) || 25;
      const frames = (cur.media && cur.media.frames) || 0;
      const frame = cur.frame || 0;
      const time = frame / fps;
      const b = $("#pv-badge");
      const meta = $("#pv-meta");
      try {
        const r = await fetch(`${API}/jobs/${cur.id}/live?t=${time.toFixed(3)}&w=880`, { cache: "no-store" });
        if (!r.ok || state.pv.mode !== "live" || state.pv.jobId !== cur.id) return;
        const kind = r.headers.get("X-CK-Kind") || "source";
        const url = URL.createObjectURL(await r.blob());
        if ($img.dataset.url) URL.revokeObjectURL($img.dataset.url);
        $img.dataset.url = url;
        $img.src = url;
        $("#pv-chip-fmt").textContent = kind === "alpha" ? "alpha" : "source";
        b.hidden = false;
        b.textContent = `${Math.round(cur.progress || 0)}% · ${t("t_frame", { i: frame, n: frames })}`;
        meta.textContent = `${fps.toFixed(2)} fps · ${t(kind === "alpha" ? "pv_live_alpha" : "pv_live_source")}`;
      } catch (_) {
        /* демон занят — следующий тик повторит */
      }
    };
    tick();
    state.pv.timer = setInterval(tick, 1200);
  }

  async function startPlayer(job) {
    stopLive();
    state.pv.mode = "player";
    state.pv.jobId = job.id;
    state.pv.result = null;
    $("#pv-idle").hidden = true;
    $img.hidden = true;
    $video.hidden = true;
    $("#pv-controls").hidden = true;
    $("#pv-stage").classList.remove("paused");
    $("#pv-title").textContent = `${t("pv_result")} · ${base(job.input)}`;
    $("#pv-badge").hidden = false;
    $("#pv-badge").textContent = "…";
    let r;
    try { r = await api(`/jobs/${job.id}/result`); } catch (e) {
      if (state.pv.jobId === job.id) showIdle(t("pv_no_result"));
      return;
    }
    // пока грузили результат, могли выбрать другой клип или запустить новый рендер
    if (state.pv.mode !== "player" || state.pv.jobId !== job.id) return;
    state.pv.result = r;
    const avail = Object.keys(r.files || {});
    if (!avail.length) {
      showIdle(r.exr ? "EXR" : t("pv_no_result"));
      return;
    }
    const kind = r.files[state.pv.kind] ? state.pv.kind : avail[0];
    $("#pv-controls").hidden = false;
    $("#pv-chip-res").textContent = r.width ? `${r.width}×${r.height}` : "—";
    $("#pv-chip-fmt").textContent = (r.exr ? "EXR" : "mp4");
    $("#pv-dir").textContent = base(r.output_dir);
    $("#pv-meta").textContent = t("pv_meta", {
      w: r.width || "?", h: r.height || "?", fps: (r.fps || 0).toFixed(2), d: (r.duration || 0).toFixed(1),
    });
    setKind(kind);
  }

  function setKind(kind) {
    const r = state.pv.result;
    if (!r) return;
    const files = r.files || {};
    if (kind !== "source" && !files[kind]) kind = Object.keys(files)[0] || "source";
    state.pv.kind = kind;
    document.querySelectorAll("#pv-kinds button").forEach((b) => {
      b.classList.toggle("on", b.dataset.kind === kind);
      b.disabled = b.dataset.kind !== "source" && !files[b.dataset.kind];
    });
    const id = state.pv.jobId;
    $video.hidden = false;
    $img.hidden = true;
    // Chromium в QtWebEngine без H.264: играем WebM/VP9, который готовит демон
    $video.poster = `${API}/jobs/${id}/frame?kind=${kind}&t=0&w=880`;
    $video.removeAttribute("src");
    $video.load();
    const fps = r.fps || 25;
    const frames = r.frames || 0;
    $seek.max = String(Math.max(0, frames - 1));
    $seek.value = "0";
    $seek.style.setProperty("--fill", "0%");
    $("#pv-time").textContent = t("t_frame", { i: 0, n: frames });
    $("#pv-badge").hidden = false;
    $("#pv-badge").textContent = t("pv_prep") + " …";
    updateStagePaused();

    if (state.pv.poll) clearInterval(state.pv.poll);
    const tick = async () => {
      try {
        const s = await api(`/jobs/${id}/preview/status?kind=${kind}`);
        if (state.pv.jobId !== id || state.pv.kind !== kind) return;
        if (s.status === "ready") {
          clearInterval(state.pv.poll);
          state.pv.poll = 0;
          $video.src = `${API}/jobs/${id}/preview?kind=${kind}&r=${Date.now()}`;
          $video.load();
          $("#pv-badge").hidden = true;
        } else if (s.status === "error") {
          clearInterval(state.pv.poll);
          state.pv.poll = 0;
          $("#pv-badge").hidden = true;
          toast(t("pv_prep_fail"), "err");
        } else {
          $("#pv-badge").hidden = false;
          $("#pv-badge").textContent = `${t("pv_prep")} ${s.progress || 0}%`;
        }
      } catch (e) {
        clearInterval(state.pv.poll);
        state.pv.poll = 0;
        toast(String(e.message || e), "err");
      }
    };
    tick();
    state.pv.poll = setInterval(tick, 1200);
  }

  function updateStagePaused() {
    const paused = state.pv.mode === "player" && $video.paused;
    $("#pv-stage").classList.toggle("paused", paused);
  }

  async function refreshPreview(force) {
    const j = selectedJob();
    if (!j) return showIdle();

    if (j.status === "running") { startLive(j); return; }
    if (j.status === "queued") { showIdle(t("s_queued")); return; }
    if (j.status === "done") {
      if (state.pv.mode === "player" && state.pv.jobId === j.id && !force) return;
      startPlayer(j);
      return;
    }
    showIdle(t("s_" + j.status));
  }

  /* ── fullscreen ─────────────────────────────────────────────────────── */
  async function toggleFullscreen() {
    const stage = $("#pv-stage");
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
      return;
    }
    if (stage.classList.contains("cinema")) return exitCinema();
    if (!state.pv.result) return;  // в LIVE полноэкранный режим не нужен
    try {
      await stage.requestFullscreen();
    } catch (_) {
      enterCinema();
    }
  }

  // запасной путь: вынимаем сцену из карточки (у .glass backdrop-filter,
  // он ломает position:fixed у вложенных элементов)
  function enterCinema() {
    const stage = $("#pv-stage");
    state.pv.home = stage.parentNode;
    state.pv.next = stage.nextSibling;
    document.body.appendChild(stage);
    stage.classList.add("cinema");
    $("#pv-close").hidden = false;
    $("#pv-fs").classList.add("on");
  }

  function exitCinema() {
    const stage = $("#pv-stage");
    if (!stage.classList.contains("cinema")) return;
    stage.classList.remove("cinema");
    if (state.pv.home) state.pv.home.insertBefore(stage, state.pv.next || null);
    state.pv.home = null;
    $("#pv-close").hidden = true;
    $("#pv-fs").classList.remove("on");
  }

  /* ── polling ────────────────────────────────────────────────────────── */
  async function poll() {
    try {
      const [list, health, stats] = await Promise.all([api("/jobs"), api("/health"), api("/stats")]);
      state.jobs = Array.isArray(list) ? list : [];
      const st = $("#status");
      st.classList.remove("off");
      st.classList.add("on");
      st.querySelector("span").textContent = health && health.current ? t("st_rendering") : t("st_online");
      updateStats(stats);
      const sig = state.jobs.map((j) => `${j.id}:${j.status}:${Math.round((j.progress || 0) * 2)}:${(j.log_tail || []).length}:${j.frame || 0}`).join("|");
      if (sig !== state.sig) {
        state.sig = sig;
        renderJobs();
        refreshPreview();
      }
      const running = state.jobs.some((j) => j.status === "running" || j.status === "queued");
      $("#btn-stop").disabled = !running;
    } catch (e) {
      const st = $("#status");
      st.classList.remove("on");
      st.classList.add("off");
      st.querySelector("span").textContent = t("st_offline");
    }
  }

  function updateStats(s) {
    if (!s) return;
    const set = (id, pct, label) => {
      const v = $(id);
      v.textContent = label;
      const bar = $(id.replace("m-", "mb-"));
      if (bar) bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
    };
    set("#m-cpu", s.cpu, `${Math.round(s.cpu)}%`);
    const ramPct = s.ram.total ? (100 * s.ram.used) / s.ram.total : 0;
    set("#m-ram", ramPct, `${gb(s.ram.used)}/${gb(s.ram.total)}G`);
    const vPct = s.gpu.total ? (100 * s.gpu.used) / s.gpu.total : 0;
    set("#m-vram", vPct, `${gb(s.gpu.used)}/${gb(s.gpu.total)}G`);
    $("#meters").title = `GPU ${s.gpu.util}% · ${s.gpu.temp}°C`;
  }

  /* ── actions ────────────────────────────────────────────────────────── */
  function payloadFor(path) {
    const s = readSettings();
    const p = {
      input: path,
      outputs: s.outputs.split(/\s+/),
      hint_quality: s.hint_quality,
      despill: s.despill,
      exr: s.exr,
      low_vram: s.low_vram,
    };
    const preset = PROFILES[s.profile];
    if (preset && preset.hann_chunk) {
      p.hann_chunk = preset.hann_chunk;
      p.hann_stride = preset.hann_stride;
      p.low_vram = !!preset.low_vram;
    }
    if (s.hint) p.hint_first_frame = s.hint;
    if (s.num_frames > 0) p.num_frames = s.num_frames;
    if (s.output_dir) p.output_dir = s.output_dir;
    return p;
  }

  async function startRender() {
    if (!state.pending.length) return toast(t("t_need_clip"), "err");
    const clips = state.pending.slice();
    const ids = [];
    for (const p of clips) {
      try {
        const r = await api("/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payloadFor(p)),
        });
        if (r && r.id) ids.push(r.id);
      } catch (e) {
        toast(t("t_submit_err", { e: e.message }), "err");
      }
    }
    if (!ids.length) return;
    state.lastClip = clips[clips.length - 1];
    state.pending = [];
    renderPending();
    state.selected = ids[0];
    state.pv.mode = "idle";
    state.sig = "";
    toast(t("t_queued", { n: ids.length }));
    await poll();
    refreshPreview(true);
    document.querySelector("#preview").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function cancelJob(id) {
    try {
      await api(`/jobs/${id}/cancel`, { method: "POST" });
      toast(t("t_cancel"));
      state.sig = "";
      poll();
    } catch (e) {
      toast(t("t_cancel_err", { e: e.message }), "err");
    }
  }

  async function deleteJob(id) {
    try {
      await api(`/jobs/${id}`, { method: "DELETE" });
      if (state.selected === id) state.selected = null;
      toast(t("t_deleted"));
      state.sig = "";
      poll();
    } catch (e) {
      toast(t("t_delete_err", { e: e.message }), "err");
    }
  }

  async function retryJob(id) {
    const j = state.jobs.find((x) => x.id === id);
    try {
      await api(`/jobs/${id}/retry`, { method: "POST" });
      if (j) toast(t("t_retried", { n: base(j.input) }));
      state.selected = id;
      state.sig = "";
      await poll();
      refreshPreview(true);
    } catch (e) {
      toast(t("t_retry_err", { e: e.message }), "err");
    }
  }

  async function stopCurrent() {
    const j = state.jobs.find((x) => x.status === "running") || state.jobs.find((x) => x.status === "queued");
    if (j) return cancelJob(j.id);
    toast(t("t_cancel_err", { e: "—" }), "err");
  }

  async function openFolder(path) {
    if (!path) return;
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const r = await call(state.bridge.openFolder, path);
    if (r !== "ok") toast(path, "err");
  }

  async function pickVideo() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const p = await call(state.bridge.browseVideo, t("dlg_clip"));
    if (p) addClip(p);
  }

  async function pickHint() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const p = await call(state.bridge.browseHint, t("dlg_hint"));
    if (p) { S.hint.value = p; saveSettings(); toast(t("t_hint", { n: base(p) })); }
  }

  async function pickOutDir() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const p = await call(state.bridge.browseOutputDir, t("dlg_out"));
    if (p) { S.outdir.value = p; saveSettings(); toast(t("t_out", { n: base(p) })); }
  }

  async function importResolve() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const r = await call(state.bridge.importResolve);
    toast(r || t("t_import"));
  }

  async function pickBg() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const p = await call(state.bridge.browseBackground, t("dlg_bg"));
    if (p) { S.bg.value = p; saveSettings(); toast(t("t_bg", { n: base(p) })); }
  }

  async function composeResolve() {
    if (!state.bridge) return toast(t("t_no_bridge"), "err");
    const job = selJob();
    if (!job || job.status !== "done") return toast(t("t_no_job"), "err");
    const bg = S.bg.value.trim();
    if (!bg) return toast(t("t_no_bg"), "err");
    $("#ck-status").textContent = t("t_compose");
    const r = await call(state.bridge.composeResolve, job.id, bg);
    $("#ck-status").textContent = r || t("t_compose");
    toast(r || t("t_compose"));
  }

  /* ── Qt drag & drop ─────────────────────────────────────────────────── */
  window.ck = {
    drag(active) {
      $("#drop").classList.toggle("on", !!active);
      const hero = $("#hero-drop");
      if (hero) hero.classList.toggle("dropping", !!active);
    },
    onDrop(paths) {
      $("#drop").classList.remove("on");
      (paths || []).forEach(addClip);
    },
  };

  /* ── web channel ────────────────────────────────────────────────────── */
  function initBridge() {
    if (typeof QWebChannel === "undefined" || !window.qt || !qt.webChannelTransport) return;
    new QWebChannel(qt.webChannelTransport, (ch) => {
      state.bridge = ch.objects.ck;
      if (!state.bridge) return;
      call(state.bridge.gpuInfo).then((info) => {
        if (info) $("#gpu-badge").innerHTML = `<span class="tag">LOCAL</span>${esc(info)}`;
      }).catch(() => {});
    });
  }

  /* ── background ─────────────────────────────────────────────────────── */
  function initCanvas() {
    const cv = $("#bg");
    const ctx = cv.getContext("2d", { alpha: true });
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, pts = [], raf = 0;

    function size() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = cv.clientWidth; h = cv.clientHeight;
      cv.width = Math.floor(w * dpr); cv.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.round(Math.min(74, Math.max(28, (w * h) / 26000)));
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.16, vy: (Math.random() - 0.5) * 0.16,
        r: Math.random() * 1.3 + 0.5, warm: Math.random() < 0.12,
      }));
    }

    function frame() {
      ctx.clearRect(0, 0, w, h);
      const reach = Math.min(190, Math.max(120, w * 0.14));
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i];
        if (!reduce) { a.x += a.vx; a.y += a.vy; }
        if (a.x < -20) a.x = w + 20; if (a.x > w + 20) a.x = -20;
        if (a.y < -20) a.y = h + 20; if (a.y > h + 20) a.y = -20;
        for (let k = i + 1; k < pts.length; k++) {
          const b = pts[k];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < reach) {
            ctx.strokeStyle = `rgba(123,57,252,${((1 - d / reach) * 0.3).toFixed(3)})`;
            ctx.lineWidth = 0.7;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
        ctx.beginPath();
        ctx.fillStyle = a.warm ? "rgba(248,123,82,.55)" : "rgba(164,132,215,.65)";
        ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    }

    size();
    addEventListener("resize", size);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) cancelAnimationFrame(raf);
      else if (!reduce) raf = requestAnimationFrame(frame);
    });
    frame();
  }

  function reveal() {
    document.querySelectorAll(".reveal").forEach((el, i) => {
      el.style.animationDelay = `${120 + i * 120}ms`;
      el.classList.add("revealed");
    });
  }

  /* ── bind ───────────────────────────────────────────────────────────── */
  function bind() {
    ["#btn-add", "#btn-add-2", "#btn-add-3", "#btn-clip"].forEach((s) => $(s).addEventListener("click", pickVideo));
    $("#btn-hint").addEventListener("click", pickHint);
    $("#btn-outdir").addEventListener("click", pickOutDir);
    $("#btn-start").addEventListener("click", startRender);
    $("#hero-drop").addEventListener("click", (e) => { if (!e.target.closest("button, a")) pickVideo(); });
    $("#pv-fs").addEventListener("click", toggleFullscreen);
    $("#pv-close").addEventListener("click", exitCinema);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") exitCinema(); });
    $("#btn-stop").addEventListener("click", stopCurrent);
    $("#btn-resolve").addEventListener("click", composeResolve);
    $("#btn-compose").addEventListener("click", composeResolve);
    $("#btn-import").addEventListener("click", importResolve);
    $("#btn-bg").addEventListener("click", pickBg);
    S.bg.addEventListener("change", saveSettings);

    [S.hintQ, S.despill].forEach((r) => r.addEventListener("input", () => { syncSliders(); saveSettings(); }));
    [S.outputs, S.exr, S.lowVram, S.frames, S.outdir].forEach((el) => el.addEventListener("change", saveSettings));
    S.hint.addEventListener("change", () => { saveSettings(); syncHintWarn(); });
    S.hint.addEventListener("input", syncHintWarn);

    S.profile.addEventListener("change", () => { syncProfile(); saveSettings(); });

    $("#lang").addEventListener("change", (e) => {
      lang = e.target.value;
      localStorage.setItem(LSL, lang);
      saveSettings();
      applyI18n();
      state.sig = "";
    });

    // player
    $("#pv-kinds").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-kind]");
      if (b && !b.disabled) setKind(b.dataset.kind);
    });
    $("#pv-stage").addEventListener("click", () => {
      if (state.pv.mode !== "player" || !state.pv.result) return;
      if ($video.paused) $video.play().catch(() => {}); else $video.pause();
    });
    $video.addEventListener("play", updateStagePaused);
    $video.addEventListener("pause", updateStagePaused);
    const showFrame = (idx) => {
      const r = state.pv.result;
      if (!r) return;
      const span = Math.max(1, +(r.frames || 1) - 1);
      $seek.style.setProperty("--fill", ((idx / span) * 100).toFixed(2) + "%");
      $("#pv-time").textContent = t("t_frame", { i: idx, n: r.frames || 0 });
    };
    ["timeupdate", "seeked"].forEach((ev) =>
      $video.addEventListener(ev, () => {
        const r = state.pv.result;
        if (!r) return;
        const fps = r.fps || 25;
        const idx = Math.round($video.currentTime * fps);
        if (document.activeElement !== $seek) $seek.value = String(idx);
        showFrame(idx);
      })
    );
    $seek.addEventListener("input", () => {
      const r = state.pv.result;
      if (!r) return;
      const fps = r.fps || 25;
      const idx = +$seek.value;
      $video.currentTime = idx / fps;
      showFrame(idx);  // не ждём timeupdate: на паузе он может не прийти
    });

    document.querySelectorAll('a[href^="#"]').forEach((a) => {
      a.addEventListener("click", (e) => {
        const tgt = document.querySelector(a.getAttribute("href"));
        if (tgt) { e.preventDefault(); tgt.scrollIntoView({ behavior: "smooth", block: "start" }); }
      });
    });
  }

  /* ── boot ───────────────────────────────────────────────────────────── */
  loadSettings();
  if (!localStorage.getItem(LSL)) localStorage.setItem(LSL, lang);
  applyI18n();
  syncProfile();
  syncSliders();
  bind();
  syncHintWarn();
  initCanvas();
  reveal();
  initBridge();
  poll();
  setInterval(poll, 1500);
})();
