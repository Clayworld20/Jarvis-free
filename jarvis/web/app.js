/* JARVIS-free dashboard: talks to the local API (same origin) and listens to /api/events. */
(() => {
  "use strict";

  const I18N = {
    ru: {
      nav_home: "Главная", nav_chat: "Чат", nav_logs: "Журнал", nav_commands: "Команды", nav_settings: "Настройки",
      chat_title: "Чат", chat_placeholder: "Введите команду…", send: "Отправить",
      logs_title: "Журнал", all: "Все", commands_title: "Команды", reload_scripts: "Перезагрузить сценарии",
      intents: "Голосовые команды", scripts: "Сценарии", settings_title: "Настройки", save: "Сохранить",
      s_general: "Основные", s_language: "Язык", s_wake_ru: "Слова активации (RU)", s_wake_en: "Слова активации (EN)",
      s_timeout: "Ожидание команды, сек", s_confirm: "Подтверждать выключение/перезагрузку",
      s_delay: "Задержка выключения, сек", s_any_app: "Запускать любые программы по имени",
      s_search: "Адрес поиска ({query})", s_audio: "Микрофон и шумы", s_device: "Микрофон",
      s_noise: "Шумоподавление (фильтр + шлюз)", s_highpass: "Фильтр низких частот, Гц", s_gate: "Порог шлюза, дБ",
      s_voice: "Голос", s_tts: "Озвучивать ответы", s_rate: "Скорость речи", s_volume: "Громкость",
      s_voice_name: "Голос (часть названия, необязательно)", s_apps: "Приложения и сайты",
      apps_hint: "По одной записи в строке: «название = программа или https://адрес».",
      say: "Скажи «{w}»", listening: "Слушаю…", processing: "Обрабатываю…", speaking: "Говорю…",
      idle: "Скажи «{w}»", error: "Ошибка", saved: "Сохранено", save_failed: "Не сохранено: ",
      restart_needed: "Сохранено. Перезапустите приложение, чтобы применить адрес/порт.",
      mic_on: "Микрофон: работает", mic_off: "Микрофон: нет", tts_on: "Голос: готов", tts_off: "Голос: недоступен",
      state_idle: "ожидание", state_listening: "слушаю", state_processing: "обработка", state_error: "ошибка",
      no_history: "История пуста. Скажите команду или напишите её в чате.", you: "Вы", jarvis: "JARVIS",
      no_logs: "Журнала пока нет.", last_cmd: "Последняя команда:", reply: "Ответ:",
      no_scripts: "Сценариев нет. Добавьте JSON-файл в resources/scripts.", triggers: "Фразы:",
      steps: "шагов", try_it: "Нажмите на фразу, чтобы вставить её в чат.", stop_btn: "Стоп",
    },
    en: {
      nav_home: "Home", nav_chat: "Chat", nav_logs: "Log", nav_commands: "Commands", nav_settings: "Settings",
      chat_title: "Chat", chat_placeholder: "Type a command…", send: "Send",
      logs_title: "Log", all: "All", commands_title: "Commands", reload_scripts: "Reload scripts",
      intents: "Voice commands", scripts: "Scripts", settings_title: "Settings", save: "Save",
      s_general: "General", s_language: "Language", s_wake_ru: "Wake words (RU)", s_wake_en: "Wake words (EN)",
      s_timeout: "Command timeout, sec", s_confirm: "Confirm shutdown/restart",
      s_delay: "Shutdown delay, sec", s_any_app: "Launch any program by name",
      s_search: "Search URL ({query})", s_audio: "Microphone & noise", s_device: "Microphone",
      s_noise: "Noise reduction (filter + gate)", s_highpass: "High-pass cutoff, Hz", s_gate: "Gate margin, dB",
      s_voice: "Voice", s_tts: "Speak replies", s_rate: "Speech rate", s_volume: "Volume",
      s_voice_name: "Voice name fragment (optional)", s_apps: "Apps and sites",
      apps_hint: "One entry per line: \"name = program or https://address\".",
      say: "Say “{w}”", listening: "Listening…", processing: "Processing…", speaking: "Speaking…",
      idle: "Say “{w}”", error: "Error", saved: "Saved", save_failed: "Not saved: ",
      restart_needed: "Saved. Restart the app to apply the address/port.",
      mic_on: "Mic: active", mic_off: "Mic: off", tts_on: "Voice: ready", tts_off: "Voice: unavailable",
      state_idle: "idle", state_listening: "listening", state_processing: "processing", state_error: "error",
      no_history: "No history yet. Speak a command or type it in the chat.", you: "You", jarvis: "JARVIS",
      no_logs: "No log entries yet.", last_cmd: "Last command:", reply: "Reply:",
      no_scripts: "No scripts. Add a JSON file to resources/scripts.", triggers: "Phrases:",
      steps: "steps", try_it: "Click a phrase to put it into the chat.", stop_btn: "Stop",
    },
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

  const ui = { lang: "ru", status: {}, settings: null, level: 0, levelTarget: 0, bubbles: 0 };
  const t = (key, vars = {}) => {
    let s = (I18N[ui.lang] && I18N[ui.lang][key]) || I18N.ru[key] || key;
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
    return s;
  };
  const wakeWord = () => (ui.settings && ui.settings.wake_words && ui.settings.wake_words[ui.lang] || ["jarvis"])[0];

  function applyI18n() {
    document.documentElement.lang = ui.lang;
    $$("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
    $$("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
    $$("#page-settings [data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  }

  // ----- navigation -----------------------------------------------------
  function showPage(name) {
    $$(".nav-btn[data-page]").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${name}`));
    if (name === "commands") loadCommands();
    if (name === "settings") loadSettings();
    if (name === "logs") scrollLogs();
  }
  $$(".nav-btn[data-page]").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
  $("#toggle-sidebar").addEventListener("click", () => {
    const sb = $("#sidebar");
    sb.classList.toggle("open");
    $("#toggle-sidebar").title = sb.classList.contains("open") ? "Свернуть" : "Развернуть";
  });

  // ----- sphere ---------------------------------------------------------
  const canvas = $("#orb");
  const ctx2d = canvas.getContext("2d");
  const POINTS = [];
  const N = 320;
  for (let i = 0; i < N; i++) { // Fibonacci sphere
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const phi = i * Math.PI * (3 - Math.sqrt(5));
    POINTS.push([Math.cos(phi) * r, y, Math.sin(phi) * r, Math.random()]);
  }
  let angle = 0;
  function speedFor(state) {
    return { listening: 0.012, processing: 0.02, speaking: 0.008 }[state] || 0.0035;
  }
  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener("resize", resize);
  function drawSphere() {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width, h = rect.height;
    if (!w || !h) { requestAnimationFrame(drawSphere); return; }
    ui.level += (ui.levelTarget - ui.level) * 0.2;
    const state = ui.status.state || "idle";
    const speaking = !!ui.status.speaking;
    angle += speedFor(speaking ? "speaking" : state);
    const pulse = 1 + (speaking ? ui.level * 0.25 : 0) + (state === "listening" ? 0.04 * Math.sin(Date.now() / 180) : 0);
    const R = Math.min(w, h) * 0.36 * pulse;
    const cx = w / 2, cy = h / 2;
    ctx2d.clearRect(0, 0, w, h);
    const glow = ctx2d.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.6);
    glow.addColorStop(0, "rgba(40,110,150,0.22)");
    glow.addColorStop(1, "rgba(4,8,12,0)");
    ctx2d.fillStyle = glow;
    ctx2d.fillRect(0, 0, w, h);
    const ca = Math.cos(angle), sa = Math.sin(angle), tilt = 0.35, ct = Math.cos(tilt), st = Math.sin(tilt);
    const brightBase = state === "listening" ? 0.85 : state === "processing" ? 0.7 : 0.55;
    const projected = POINTS.map(([x, y, z, seed]) => {
      const x1 = x * ca + z * sa, z1 = -x * sa + z * ca;      // rotate around Y
      const y2 = y * ct - z1 * st, z2 = y * st + z1 * ct;      // tilt around X
      return [x1, y2, z2, seed];
    }).sort((a, b) => a[2] - b[2]);
    for (const [x, y, z, seed] of projected) {
      const depth = (z + 1) / 2;                                 // 0 (back) .. 1 (front)
      const persp = 0.85 + 0.25 * depth;
      const px = cx + x * R * persp, py = cy + y * R * persp;
      const alpha = Math.min(1, (0.12 + 0.88 * depth) * brightBase + (seed > 0.9 ? 0.25 : 0));
      const size = (0.7 + 1.5 * depth) * (state === "processing" ? 1.1 : 1);
      ctx2d.fillStyle = `rgba(${170 + 60 * depth | 0},${200 + 40 * depth | 0},255,${alpha.toFixed(3)})`;
      ctx2d.beginPath();
      ctx2d.arc(px, py, size, 0, Math.PI * 2);
      ctx2d.fill();
    }
    requestAnimationFrame(drawSphere);
  }

  // ----- status ---------------------------------------------------------
  const STATE_KEYS = { idle: "state_idle", listening: "state_listening", processing: "state_processing", error: "state_error" };
  function renderStatus() {
    const s = ui.status || {};
    if (s.language && s.language !== ui.lang) { ui.lang = s.language; applyI18n(); }
    let state = s.state || "idle";
    let prompt = t("idle", { w: wakeWord() });
    let sub = "";
    if (s.error) { prompt = t("error"); sub = s.error; }
    else if (s.speaking) prompt = t("speaking");
    else if (state === "listening") prompt = t("listening");
    else if (state === "processing") prompt = t("processing");
    $("#prompt").textContent = prompt;
    $("#sub").textContent = sub;
    const chipState = $("#chip-state");
    chipState.textContent = t(STATE_KEYS[state] || "state_idle");
    chipState.className = "chip " + (state === "error" ? "err" : state === "idle" ? "" : "ok");
    const mic = $("#chip-mic");
    mic.textContent = s.mic_active ? t("mic_on") : t("mic_off");
    mic.className = "chip " + (s.mic_active ? "ok" : "warn");
    const tts = $("#chip-tts");
    tts.textContent = s.tts_available ? t("tts_on") : t("tts_off");
    tts.className = "chip " + (s.tts_available ? "ok" : "warn");
  }

  function setLast(entry) {
    const box = $("#last");
    box.innerHTML = "";
    if (!entry) return;
    box.append(el("div", "", t("last_cmd") + " "), el("b", "", entry.input || ""));
    box.append(el("div", "", t("reply") + " " + (entry.reply || "")));
  }

  $("#btn-stop").addEventListener("click", () => {
    fetch("/api/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  });

  // ----- chat & logs ----------------------------------------------------
  function addBubble(role, text, meta, fail) {
    const chat = $("#chat");
    if (ui.bubbles === 0) chat.innerHTML = "";
    ui.bubbles++;
    const b = el("div", `bubble ${role}${fail ? " fail" : ""}`, text);
    if (meta) b.append(el("span", "meta", meta));
    chat.append(b);
    chat.scrollTop = chat.scrollHeight;
  }
  function addHistory(entry) {
    const time = new Date(entry.time * 1000).toLocaleTimeString(ui.lang === "ru" ? "ru-RU" : "en-US", { hour: "2-digit", minute: "2-digit" });
    addBubble("user", entry.input || "", `${t("you")} · ${time}${entry.source === "voice" ? " · 🎙" : ""}`);
    addBubble("jarvis", entry.reply || "", `${t("jarvis")}${entry.intent ? " · " + entry.intent : ""}`, entry.ok === false);
    setLast(entry);
  }
  function renderLog(entry) {
    const filter = $("#log-level").value;
    const row = el("div", `log ${entry.level}`);
    row.dataset.level = entry.level;
    row.append(el("span", "t", new Date(entry.time * 1000).toLocaleTimeString("ru-RU")));
    row.append(el("span", "lv", entry.level));
    row.append(el("span", "m", entry.message));
    if (filter && entry.level !== filter && !(filter === "WARNING" && entry.level === "ERROR")) row.style.display = "none";
    const box = $("#logs");
    if (box.querySelector(".empty")) box.innerHTML = "";
    box.append(row);
    while (box.childElementCount > 400) box.firstElementChild.remove();
    scrollLogs();
  }
  function scrollLogs() { const box = $("#logs"); box.scrollTop = box.scrollHeight; }
  $("#log-level").addEventListener("change", () => {
    const f = $("#log-level").value;
    $$("#logs .log").forEach((r) => { r.style.display = !f || r.dataset.level === f || (f === "WARNING" && r.dataset.level === "ERROR") ? "" : "none"; });
  });

  $("#chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("#chat-text");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    try {
      await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    } catch (err) {
      addBubble("jarvis", String(err), t("error"), true);
    }
  });

  // ----- commands -------------------------------------------------------
  async function loadCommands() {
    const data = await (await fetch("/api/commands")).json();
    const intents = $("#intent-cards");
    intents.innerHTML = "";
    for (const i of data.intents) {
      const card = el("div", "card");
      card.append(el("div", "title", i.id));
      for (const p of i.patterns) {
        const chip = el("button", "pat", p);
        chip.type = "button";
        chip.addEventListener("click", () => { $("#chat-text").value = p; showPage("chat"); $("#chat-text").focus(); });
        card.append(chip);
      }
      intents.append(card);
    }
    const scripts = $("#script-cards");
    scripts.innerHTML = "";
    if (!data.scripts.length) scripts.append(el("div", "hint", t("no_scripts")));
    for (const s of data.scripts) {
      const card = el("div", "card");
      card.append(el("div", "title", s.name));
      card.append(el("div", "desc", s.description || ""));
      card.append(el("div", "desc", `${t("triggers")} ${s.triggers.join(", ") || "—"} · ${s.steps} ${t("steps")}`));
      scripts.append(card);
    }
    $("#script-errors").textContent = data.script_errors.join("\n");
  }
  $("#reload-scripts").addEventListener("click", async () => {
    await fetch("/api/scripts/reload", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    loadCommands();
  });

  // ----- settings -------------------------------------------------------
  const FORM_MAP = {
    language: (s) => s.language, wake_ru: (s) => s.wake_words.ru.join(", "), wake_en: (s) => s.wake_words.en.join(", "),
    listen_timeout_sec: (s) => s.listen_timeout_sec, confirm_power_actions: (s) => s.confirm_power_actions,
    power_delay_sec: (s) => s.power_delay_sec, allow_any_app: (s) => s.allow_any_app, search_url: (s) => s.search_url,
    noise_filter: (s) => s.audio.noise_filter, highpass_hz: (s) => s.audio.highpass_hz, gate_margin_db: (s) => s.audio.gate_margin_db,
    tts_enabled: (s) => s.tts.enabled, tts_rate: (s) => s.tts.rate, tts_volume: (s) => s.tts.volume, tts_voice: (s) => s.tts.voice,
    apps: (s) => Object.entries(s.apps).map(([k, v]) => `${k} = ${v}`).join("\n"),
  };
  const CHECKBOX = new Set(["confirm_power_actions", "allow_any_app", "noise_filter", "tts_enabled"]);

  async function loadSettings() {
    const [settings, devices] = await Promise.all([
      fetch("/api/settings").then((r) => r.json()),
      fetch("/api/devices").then((r) => r.json()).catch(() => []),
    ]);
    ui.settings = settings;
    const form = $("#settings-form");
    for (const [name, get] of Object.entries(FORM_MAP)) {
      const input = form.elements[name];
      if (!input) continue;
      const value = get(settings);
      if (CHECKBOX.has(name)) input.checked = !!value; else input.value = value;
    }
    $("#rate-out").textContent = form.elements.tts_rate.value;
    $("#vol-out").textContent = Number(form.elements.tts_volume.value).toFixed(2);
    const sel = form.elements.input_device;
    sel.innerHTML = "";
    sel.append(new Option(ui.lang === "ru" ? "По умолчанию (системный)" : "System default", ""));
    for (const d of devices) sel.append(new Option(d.name, String(d.index)));
    sel.value = settings.audio.input_device == null ? "" : String(settings.audio.input_device);
  }
  $("#settings-form").addEventListener("input", (e) => {
    if (e.target.name === "tts_rate") $("#rate-out").textContent = e.target.value;
    if (e.target.name === "tts_volume") $("#vol-out").textContent = Number(e.target.value).toFixed(2);
  });
  $("#settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target.elements;
    const splitWords = (v) => v.split(",").map((w) => w.trim()).filter(Boolean);
    const apps = {};
    for (const line of f.apps.value.split("\n")) {
      const idx = line.indexOf("=");
      if (idx > 0) { const k = line.slice(0, idx).trim(); const v = line.slice(idx + 1).trim(); if (k && v) apps[k] = v; }
    }
    const dev = f.input_device.value;
    const patch = {
      language: f.language.value,
      wake_words: { ru: splitWords(f.wake_ru.value), en: splitWords(f.wake_en.value) },
      listen_timeout_sec: Number(f.listen_timeout_sec.value),
      confirm_power_actions: f.confirm_power_actions.checked,
      power_delay_sec: Number(f.power_delay_sec.value),
      allow_any_app: f.allow_any_app.checked,
      search_url: f.search_url.value,
      audio: {
        input_device: dev === "" ? null : Number(dev),
        noise_filter: f.noise_filter.checked,
        highpass_hz: Number(f.highpass_hz.value),
        gate_margin_db: Number(f.gate_margin_db.value),
      },
      tts: { enabled: f.tts_enabled.checked, rate: Number(f.tts_rate.value), volume: Number(f.tts_volume.value), voice: f.tts_voice.value },
      apps,
    };
    const msg = $("#settings-msg");
    const res = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings: patch }) });
    const data = await res.json();
    if (!res.ok) { msg.className = "msg err"; msg.textContent = t("save_failed") + (data.error || res.status); return; }
    ui.settings = data.settings;
    ui.lang = data.settings.language;
    msg.className = "msg";
    msg.textContent = data.restart_required ? t("restart_needed") : t("saved");
    applyI18n();
  });

  // ----- live events ----------------------------------------------------
  function connect() {
    const es = new EventSource("/api/events");
    es.onmessage = (msg) => {
      let ev;
      try { ev = JSON.parse(msg.data); } catch { return; }
      switch (ev.type) {
        case "status": ui.status = ev; renderStatus(); break;
        case "level": ui.levelTarget = ev.value; break;
        case "history": addHistory(ev); break;
        case "log": renderLog(ev); break;
        case "settings": ui.settings = ev.settings; break;
      }
    };
  }

  async function init() {
    applyI18n();
    resize();
    const [status, history, logs] = await Promise.all([
      fetch("/api/status").then((r) => r.json()).catch(() => ({})),
      fetch("/api/history").then((r) => r.json()).catch(() => []),
      fetch("/api/logs").then((r) => r.json()).catch(() => []),
    ]);
    ui.status = status;
    if (status.language) ui.lang = status.language;
    applyI18n();
    renderStatus();
    if (history.length) history.forEach(addHistory);
    else $("#chat").innerHTML = `<div class="hint">${t("no_history")}</div>`;
    if (logs.length) logs.forEach(renderLog);
    else $("#logs").innerHTML = `<div class="empty hint">${t("no_logs")}</div>`;
    connect();
    requestAnimationFrame(drawSphere);
  }
  init();
})();
