/* superocr web dashboard — vanilla JS, no external assets.
 * Every OCR call goes to POST /api/ocr, which runs the SAME shared pipeline
 * as the CLI (typer.recognise -> reader.read_chain). Nothing here re-implements
 * recognition; this file is display + capture + bookkeeping only. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function jget(url) {
  const r = await fetch(url);
  return r.json();
}

function fmtTs(ts) {
  if (!ts) return "";
  return String(ts).replace("T", " ").slice(0, 16);
}

function nowClock() {
  return new Date().toTimeString().slice(0, 8);
}

async function blobToB64(blob) {
  const buf = await blob.arrayBuffer();
  let s = "";
  const u8 = new Uint8Array(buf);
  for (let i = 0; i < u8.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

/* ================================================================ tabs */
const tabHooks = {};
$$("#tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (tabHooks[btn.dataset.tab]) tabHooks[btn.dataset.tab]();
  });
});

/* ================================================================ health */
async function refreshHealth() {
  try {
    const h = await jget("/api/health");
    const el = $("#health");
    const av = h.app_version && h.app_version.bundle
      ? ` · bundle ${h.app_version.bundle}` : "";
    el.textContent =
      `v${h.version} · ${h.git_commit}${av} · fonts ${h.fonts ?? "?"}/8` +
      ` · models ${Object.keys(h.models).length}` +
      ` · suites ${h.suites_configured.length}` +
      ` · bus ${h.bus_enabled ? "on" : "off"} · board ${h.board_enabled ? "on" : "off"}`;
    // W2: 0 font faces was the silent garbage-read failure mode — make it loud
    el.classList.toggle("bad", (h.fonts ?? 8) < 8);
  } catch (e) {
    $("#health").textContent = "server unreachable";
  }
}
refreshHealth();
setInterval(refreshHealth, 30000);

/* ================================================================ OCR call */
async function ocr(b64, family, detail, route) {
  const t0 = performance.now();
  const r = await fetch("/api/ocr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image: b64, family: family || "auto",
                           detail: !!detail, route: route || "typer" }),
  });
  const d = await r.json();
  d.e2e_ms = Math.round(performance.now() - t0);
  if (!r.ok) throw new Error(d.error || "http-" + r.status);
  return d;
}

function currentRoute() {
  const el = $("#route");
  return el ? el.value : "typer";
}

function addHistory(source, d, label) {
  const tbody = $("#history tbody");
  const tr = document.createElement("tr");
  let extra = "";
  if (label !== undefined && label !== null) {
    const ok = d.text === label;
    extra = ok ? ' <span class="pill ok">=label</span>'
               : ` <span class="pill bad">label: ${escapeHtml(label)}</span>`;
  }
  const raw = d.text_raw
    ? `<br><span class="dim">pre-lex: ${escapeHtml(d.text_raw)}</span>` : "";
  tr.innerHTML =
    `<td>${nowClock()}</td><td>${escapeHtml(source)}</td>` +
    `<td><b>${escapeHtml(d.text || "")}</b>${extra}${raw}</td>` +
    `<td>${escapeHtml(d.route || "")}${d.route === "lex" ? "" : " / " + escapeHtml(d.family || "")}</td>` +
    `<td>${d.avg_confidence ?? ""}</td>` +
    `<td>${d.server_ms ?? ""}</td><td>${d.e2e_ms ?? ""}</td>`;
  tbody.prepend(tr);
  while (tbody.rows.length > 200) tbody.deleteRow(tbody.rows.length - 1);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ================================================================ live OCR */
let stream = null;
let timer = null;
let region = null; /* {x0,y0,x1,y1} in video-native pixels */

async function startCapture(kind, constraints, label) {
  stopCapture();
  try {
    // W2 fix (t-20261013-b411): "Share screen" used getUserMedia — the
    // CAMERA — so the screen button never actually captured the screen.
    // Screen sharing is getDisplayMedia (browser picker: screen/window/tab).
    stream = kind === "screen"
      ? await navigator.mediaDevices.getDisplayMedia(constraints)
      : await navigator.mediaDevices.getUserMedia(constraints);
  } catch (e) {
    alert(label + " failed: " + e.message +
          (kind === "screen" && !window.isSecureContext
            ? "\n\nScreen capture needs a secure context — open the app via http://127.0.0.1:PORT (the launcher does this automatically), not a LAN IP or file://."
            : ""));
    return;
  }
  // the browser's own "Stop sharing" chip ends the track — reflect that
  stream.getVideoTracks().forEach((t) =>
    t.addEventListener("ended", () => stopCapture()));
  const v = $("#video");
  v.srcObject = stream;
  $("#stage").hidden = false;
  $("#btn-stop").disabled = false;
  $("#btn-snap").disabled = false;
  scheduleTimer();
}

function stopCapture() {
  if (timer) { clearInterval(timer); timer = null; }
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  $("#stage").hidden = true;
  $("#btn-stop").disabled = true;
  $("#btn-snap").disabled = true;
  $("#region").classList.remove("active");
  $("#overlay").classList.remove("active");
  region = null;
}

function scheduleTimer() {
  if (timer) { clearInterval(timer); timer = null; }
  const ms = parseInt($("#interval").value, 10);
  if (ms > 0 && stream) timer = setInterval(() => snapCapture("screen"), ms);
}

function captureFrame() {
  const v = $("#video");
  if (!stream || !v.videoWidth) return null;
  const c = $("#scratch");
  const r = region || { x0: 0, y0: 0, x1: v.videoWidth, y1: v.videoHeight };
  const w = Math.max(8, Math.round(r.x1 - r.x0));
  const h = Math.max(8, Math.round(r.y1 - r.y0));
  c.width = w; c.height = h;
  c.getContext("2d").drawImage(v, r.x0, r.y0, w, h, 0, 0, w, h);
  return c.toDataURL("image/png").split(",")[1];
}

async function snapCapture(source) {
  const b64 = captureFrame();
  if (!b64) return;
  const overlay = $("#overlay");
  overlay.classList.add("active");
  overlay.innerHTML = '<span class="ms">reading…</span>';
  try {
    const d = await ocr(b64, $("#family").value, false, currentRoute());
    overlay.innerHTML =
      `<b>${escapeHtml(d.text)}</b><br><span class="ms">${escapeHtml(d.route === "lex" ? "floor+lex" : d.family)} · ` +
      `conf ${d.avg_confidence} · ${d.server_ms} ms server / ${d.e2e_ms} ms e2e</span>` +
      (d.text_raw ? `<br><span class="ms">pre-lex: ${escapeHtml(d.text_raw)}</span>` : "");
    addHistory(source, d);
  } catch (e) {
    overlay.innerHTML = `<span class="ms bad">${escapeHtml(e.message)}</span>`;
  }
}

$("#btn-screen").addEventListener("click", () =>
  startCapture("screen", { video: { frameRate: 5 }, audio: false }, "screen share"));
$("#btn-cam").addEventListener("click", () =>
  startCapture("camera", { video: { facingMode: "environment" }, audio: false }, "webcam"));
$("#btn-stop").addEventListener("click", stopCapture);
$("#btn-snap").addEventListener("click", () => snapCapture("manual"));
$("#interval").addEventListener("change", scheduleTimer);

/* region selection: drag on the video */
(function regionSelect() {
  const stage = $("#stage");
  const box = $("#region");
  let drag = null;
  stage.addEventListener("mousedown", (e) => {
    if (!stream) return;
    const rect = $("#video").getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right ||
        e.clientY < rect.top || e.clientY > rect.bottom) return;
    drag = { sx: e.clientX - rect.left, sy: e.clientY - rect.top, rect };
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const x = Math.min(Math.max(e.clientX - drag.rect.left, 0), drag.rect.width);
    const y = Math.min(Math.max(e.clientY - drag.rect.top, 0), drag.rect.height);
    const left = Math.min(drag.sx, x), top = Math.min(drag.sy, y);
    const w = Math.abs(x - drag.sx), h = Math.abs(y - drag.sy);
    box.style.left = (drag.rect.left - stage.getBoundingClientRect().left + left) + "px";
    box.style.top = (drag.rect.top - stage.getBoundingClientRect().top + top) + "px";
    box.style.width = w + "px"; box.style.height = h + "px";
    box.classList.add("active");
    drag.cur = { left, top, w, h };
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    const cur = drag.cur;
    const rect = drag.rect;
    drag = null;
    if (!cur || cur.w < 12 || cur.h < 12) return;
    const v = $("#video");
    const sx = v.videoWidth / rect.width, sy = v.videoHeight / rect.height;
    region = { x0: cur.left * sx, y0: cur.top * sy,
               x1: (cur.left + cur.w) * sx, y1: (cur.top + cur.h) * sy };
  });
})();

/* file drop / pick */
const drop = $("#drop");
drop.addEventListener("click", () => $("#file").click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files.length) readFile(e.dataTransfer.files[0]);
});
$("#file").addEventListener("change", () => {
  if ($("#file").files.length) readFile($("#file").files[0]);
});
async function readFile(f) {
  const url = URL.createObjectURL(f);
  const img = $("#preview");
  img.src = url; img.hidden = false;
  const b64 = await blobToB64(f);
  try {
    const d = await ocr(b64, $("#family").value, true, currentRoute());
    addHistory("file:" + f.name, d);
  } catch (e) {
    addHistory("file:" + f.name, { text: "ERROR " + e.message, e2e_ms: "" });
  }
}

/* ================================================================ suites */
let suiteData = null;
let suiteItems = [];
let probeAbort = false;

tabHooks.suites = loadSuites;

async function loadSuites() {
  const d = await jget("/api/suites");
  suiteData = d.suites || [];
  const pick = $("#suite-pick");
  pick.innerHTML = suiteData.length
    ? suiteData.map((s) => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join("")
    : '<option value="">(none — pass --suites to the server)</option>';
  if (suiteData.length) { fillSplits(); }
  $("#suite-stats").textContent = suiteData.length ? "" :
    "start the server with --suites /path/to/suite[,/path/to/other]";
}

function fillSplits() {
  const s = suiteData.find((x) => x.name === $("#suite-pick").value);
  const pick = $("#split-pick");
  pick.innerHTML = s ? Object.keys(s.splits)
    .map((k) => `<option value="${escapeHtml(k)}">${escapeHtml(k)} (${s.splits[k].total})</option>`).join("") : "";
  loadSuiteItems();
}

async function loadSuiteItems() {
  const suite = $("#suite-pick").value, split = $("#split-pick").value;
  if (!suite || !split) return;
  const d = await jget(`/api/suite-items?suite=${encodeURIComponent(suite)}&split=${encodeURIComponent(split)}`);
  suiteItems = d.items || [];
  const s = (suiteData.find((x) => x.name === suite) || {}).splits?.[split] || {};
  $("#suite-stats").textContent =
    `${suiteItems.length} items · families: ` +
    Object.entries(s.families || {}).map(([k, v]) => `${k} ${v}`).join(", ");
  renderSuiteList();
}

function renderSuiteList() {
  const el = $("#suite-list");
  el.innerHTML = "";
  const suite = $("#suite-pick").value, split = $("#split-pick").value;
  suiteItems.slice(0, 300).forEach((it) => {
    const div = document.createElement("div");
    div.className = "item";
    div.id = "item-" + it.id;
    div.innerHTML =
      `<img loading="lazy" src="/api/suite-image?suite=${encodeURIComponent(suite)}` +
      `&split=${encodeURIComponent(split)}&id=${encodeURIComponent(it.id)}" alt="">` +
      `<div class="meta"><b>${escapeHtml(it.id)}</b> ` +
      `<span class="pill">${escapeHtml(it.family)}</span><br>` +
      `<span class="dim">label:</span> <code>${escapeHtml(it.label)}</code>` +
      `<div class="got"></div></div>`;
    const btn = document.createElement("button");
    btn.textContent = "OCR";
    btn.addEventListener("click", () => probeItem(it, div));
    div.appendChild(btn);
    el.appendChild(div);
  });
}

async function fetchItemB64(it) {
  const suite = $("#suite-pick").value, split = $("#split-pick").value;
  const r = await fetch(`/api/suite-image?suite=${encodeURIComponent(suite)}` +
    `&split=${encodeURIComponent(split)}&id=${encodeURIComponent(it.id)}`);
  const b64 = await blobToB64(await r.blob());
  return b64;
}

async function probeItem(it, rowEl) {
  const got = rowEl.querySelector(".got");
  got.textContent = "reading…";
  try {
    const b64 = await fetchItemB64(it);
    const d = await ocr(b64, "auto", false, currentRoute());
    const ok = d.text === it.label;
    got.innerHTML = `<span class="pill ${ok ? "ok" : "bad"}">${ok ? "EXACT" : "MISS"}</span> ` +
      `got: <code>${escapeHtml(d.text)}</code> <span class="dim">${d.server_ms} ms</span>`;
    addHistory("suite:" + it.id, d, it.label);
    return ok;
  } catch (e) {
    got.innerHTML = `<span class="pill bad">ERROR ${escapeHtml(e.message)}</span>`;
    return false;
  }
}

$("#suite-pick").addEventListener("change", fillSplits);
$("#split-pick").addEventListener("change", loadSuiteItems);

$("#btn-probe").addEventListener("click", async () => {
  const btn = $("#btn-probe"), stop = $("#btn-probe-stop");
  btn.disabled = true; stop.disabled = false; probeAbort = false;
  const todo = suiteItems.filter((it) => !it._done).slice(0, 10);
  let ok = 0, n = 0;
  $("#probe-bar").hidden = false;
  for (const it of todo) {
    if (probeAbort) break;
    const row = document.getElementById("item-" + it.id);
    if (!row) continue;
    row.scrollIntoView({ block: "nearest" });
    const good = await probeItem(it, row);
    it._done = true; n++; ok += good ? 1 : 0;
    $("#probe-fill").style.width = Math.round((n / todo.length) * 100) + "%";
    $("#probe-status").textContent = `probe: ${ok}/${n} exact so far`;
  }
  $("#probe-status").textContent = `probe done: ${ok}/${n} exact`;
  btn.disabled = false; stop.disabled = true;
});
$("#btn-probe-stop").addEventListener("click", () => { probeAbort = true; });

/* ================================================================ reports */
tabHooks.reports = loadReports;

async function loadReports() {
  const d = await jget("/api/reports");
  const tbody = $("#reports-table tbody");
  tbody.innerHTML = "";
  (d.reports || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.className = "clickable";
    const splitCell = (name) => {
      const s = r.splits[name];
      if (!s) return '<td class="dim">—</td>';
      const cls = s.passed ? "stat" : (s.bar ? "warn" : "");
      return `<td class="${cls}">${s.correct}/${s.total} (bar ${s.bar})</td>`;
    };
    tr.innerHTML = `<td>${escapeHtml(r.run_id)}<br><span class="dim">${fmtTs(r.started_ts)}</span></td>` +
      `<td>${escapeHtml(r.reader)}</td><td>${r.seed}</td><td><code>${escapeHtml(r.git_commit)}</code></td>` +
      splitCell("easy") + splitCell("hard") +
      `<td>${r.passed ? '<span class="pill ok">PASS</span>' : '<span class="pill bad">FAIL</span>'}</td>`;
    tr.addEventListener("click", async () => {
      const raw = await jget("/api/report?file=" + encodeURIComponent(r.file));
      const pre = $("#report-raw");
      pre.hidden = false;
      pre.textContent = JSON.stringify(raw, null, 1).slice(0, 100000);
      pre.scrollIntoView({ block: "nearest" });
    });
    tbody.appendChild(tr);
  });
}
$("#btn-reports-refresh").addEventListener("click", loadReports);

/* ================================================================ bus */
let busTimer = null;
tabHooks.bus = loadBus;

async function loadBus() {
  const ch = $("#bus-channel").value || "general";
  const lim = $("#bus-limit").value;
  const d = await jget(`/api/bus?channel=${encodeURIComponent(ch)}&limit=${lim}`);
  if (!d.enabled) {
    $("#bus-status").textContent = d.hint || "bus disabled";
    $("#bus-msgs").innerHTML = "";
    return;
  }
  const sel = $("#bus-channel");
  if ((d.channels || []).length && sel.options.length !== d.channels.length) {
    sel.innerHTML = d.channels.map((c) =>
      `<option value="${escapeHtml(c)}"${c === ch ? " selected" : ""}>${escapeHtml(c)}</option>`).join("");
  }
  $("#bus-status").textContent = `${d.total} total · showing last ${d.messages.length}`;
  const el = $("#bus-msgs");
  el.innerHTML = "";
  d.messages.slice().reverse().forEach((m) => {
    const div = document.createElement("div");
    div.className = "msg type-" + (m.type || "status");
    div.innerHTML = `<span class="ts">${escapeHtml(fmtTs(m.ts))}</span>` +
      `<span class="who">${escapeHtml(m.from)}</span> ` +
      `<span class="type">${escapeHtml(m.type || "")}${m.ref ? " · " + escapeHtml(m.ref) : ""}</span>` +
      `<pre>${escapeHtml(m.text)}</pre>`;
    el.appendChild(div);
  });
}

$("#bus-channel").addEventListener("change", loadBus);
$("#bus-limit").addEventListener("change", loadBus);
$("#btn-bus-refresh").addEventListener("click", loadBus);
$("#bus-auto").addEventListener("change", (e) => {
  if (busTimer) { clearInterval(busTimer); busTimer = null; }
  if (e.target.checked) busTimer = setInterval(loadBus, 5000);
});

/* ================================================================ tasks */
let taskTimer = null;
tabHooks.tasks = loadTasks;

async function loadTasks() {
  const d = await jget("/api/tasks");
  if (!d.enabled) {
    $("#task-stats").textContent = d.hint || "board disabled";
    $("#task-list").innerHTML = "";
  } else {
    $("#task-stats").textContent = `${d.total} tasks · ` +
      Object.entries(d.by_status).map(([k, v]) => `${k} ${v}`).join(" · ");
    const el = $("#task-list");
    el.innerHTML = "";
    d.tasks.forEach((t) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `<div class="meta"><b>${escapeHtml(t.id)}</b> ` +
        `<span class="pill status-${escapeHtml(t.status)}">${escapeHtml(t.status)}</span>` +
        (t.pr ? ` <a href="${escapeHtml(t.pr)}" target="_blank" rel="noreferrer">PR</a>` : "") +
        `<br>${escapeHtml(t.title)}<br><span class="dim">owner ${escapeHtml(t.owner || "—")} · ` +
        `p${t.priority ?? "?"} · ${fmtTs(t.updated_ts)}</span></div>`;
      el.appendChild(div);
    });
  }
  /* agent activity: last bus lines grouped by sender */
  try {
    const b = await jget("/api/bus?channel=general&limit=200");
    if (b.enabled) {
      const agg = {};
      b.messages.forEach((m) => {
        const k = m.from || "?";
        agg[k] = agg[k] || { n: 0, last: "", lastText: "" };
        agg[k].n++;
        if (m.ts > agg[k].last) { agg[k].last = m.ts; agg[k].lastText = m.text; }
      });
      const el = $("#activity");
      el.innerHTML = "";
      Object.entries(agg).sort((a, b2) => b2[1].last.localeCompare(a[1].last)).forEach(([k, v]) => {
        const div = document.createElement("div");
        div.className = "msg";
        div.innerHTML = `<span class="ts">${escapeHtml(fmtTs(v.last))}</span>` +
          `<span class="who">${escapeHtml(k)}</span> <span class="type">${v.n} msgs in last 200</span>` +
          `<pre>${escapeHtml(String(v.lastText).slice(0, 300))}</pre>`;
        el.appendChild(div);
      });
    }
  } catch (e) { /* activity is best-effort */ }
}

$("#btn-tasks-refresh").addEventListener("click", loadTasks);
$("#tasks-auto").addEventListener("change", (e) => {
  if (taskTimer) { clearInterval(taskTimer); taskTimer = null; }
  if (e.target.checked) taskTimer = setInterval(loadTasks, 10000);
});
