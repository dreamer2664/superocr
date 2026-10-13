"use strict";
const $ = (id) => document.getElementById(id);
let cfg = null;
let current = null;   // last generated item
let ocrBusy = false;

async function api(path, payload) {
  const opt = payload === undefined
    ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify(payload) };
  const r = await fetch(path, opt);
  return r.json();
}

function fillSeverities() {
  const dtype = $("dtype").value;
  const spec = cfg.degradations[dtype];
  $("severity").innerHTML = spec.severities
    .map(s => `<option>${s}</option>`).join("");
  $("ovlfam").innerHTML = (spec.families || cfg.degradations.overlay.families)
    .map(f => `<option>${f}</option>`).join("");
  $("ovlfam-row").classList.toggle("hidden", dtype !== "overlay");
}

async function generate(delta) {
  $("gen").disabled = true;
  try {
    if (delta) $("seed").value = String(parseInt($("seed").value || "1", 10) + delta);
    const payload = {
      degradation_type: $("dtype").value,
      severity: $("severity").value,
      overlay_family: $("ovlfam").value,
      seed: parseInt($("seed").value || "1", 10),
      salt: $("salt").value || "studio",
    };
    const it = await api("/api/generate", payload);
    if (it.error) { alert(it.error + (it.hint ? " — " + it.hint : "")); return; }
    current = it;
    drawItem(it);
    $("ocrResult").classList.add("hidden");
  } finally {
    $("gen").disabled = false;
  }
}

function drawItem(it) {
  const w = $("canvasWrap");
  w.innerHTML = "";
  const img = document.createElement("img");
  img.src = "data:image/png;base64," + it.png_b64;
  img.alt = "captcha";
  w.appendChild(img);
  const m = $("meta");
  m.classList.remove("hidden");
  const typeTxt = it.degradation_type === "combined" ? "combined" : it.degradation_type;
  m.innerHTML =
    `<div><b>type:</b> ${typeTxt} · <b>severity:</b> ${it.severity}` +
    (it.degradation_type === "overlay" ? ` · <b>family:</b> ${it.overlay_family}` : "") +
    (it.rotation_deg ? ` · <b>rotation:</b> ${it.rotation_deg}°` : "") +
    ` · <b>seed:</b> ${it.seed} · <b>salt:</b> ${it.salt} · ${it.render_ms} ms</div>` +
    `<div id="gt"><b>ground truth:</b> <code>${it.label}</code>
      <a href="data:image/png;base64,${it.png_b64}" download="captcha-${it.seed}.png">download png</a></div>`;
  $("gt").style.display = $("showLabel").checked ? "" : "none";
  $("ocr").disabled = false;
}

async function runOCR() {
  if (!current || ocrBusy) return;
  ocrBusy = true;
  $("ocr").textContent = "Reading… (a few seconds)";
  try {
    const out = await api("/api/ocr", { image: current.png_b64 });
    const box = $("ocrResult");
    box.classList.remove("hidden");
    if (out.error) { box.innerHTML = `<span class="miss">error: ${out.error}</span>`; return; }
    const exact = out.text === current.label;
    box.innerHTML =
      `<div class="${exact ? "exact" : "miss"}"><b>${exact ? "EXACT" : "MISS"}</b></div>` +
      `<div><b>ocr:</b> <code>${out.text}</code></div>` +
      (exact ? "" : `<div><b>truth:</b> <code>${current.label}</code></div>`) +
      `<div class="hint">${out.route} · ${out.reader_ms} ms</div>`;
  } finally {
    ocrBusy = false;
    $("ocr").textContent = "Read this image";
  }
}

async function runSelftest() {
  $("selftest").disabled = true;
  try {
    const rep = await api("/api/selftest");
    const pre = $("selftestOut");
    pre.classList.remove("hidden");
    pre.textContent = rep.checks
      .map(c => `${c.ok ? "PASS" : "FAIL"}  ${c.name}${c.detail ? "  — " + c.detail : ""}`)
      .join("\n") + `\n\noverall: ${rep.ok ? "PASS" : "FAIL"} (${rep.selftest_s}s)`;
  } finally {
    $("selftest").disabled = false;
  }
}

(async function init() {
  cfg = await api("/api/config");
  $("engine").textContent =
    `${cfg.engine} · python ${cfg.python}, Pillow ${cfg.pillow}, ` +
    `numpy ${cfg.numpy}, FreeType ${cfg.freetype} · ${cfg.fonts.length} bundled faces`;
  $("dtype").innerHTML = Object.entries(cfg.degradations)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  fillSeverities();
  $("dtype").addEventListener("change", fillSeverities);
  $("gen").addEventListener("click", () => generate(0));
  $("again").addEventListener("click", () => generate(1));
  $("ocr").addEventListener("click", runOCR);
  $("selftest").addEventListener("click", runSelftest);
  $("showLabel").addEventListener("change", () => {
    const gt = $("gt"); if (gt) gt.style.display = $("showLabel").checked ? "" : "none";
  });
})();
