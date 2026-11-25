// SpectrumAnalyzer のブラウザ版の画面。
// 計算（読み込み・平滑化・積分・FWHM や面積などの派生値・フィッティング）は
// worker.js の Python（core/）が行う。
// 曲線の描画だけは応答を速くするため JS で計算する（core/math_utils.py の pseudo_voigt と
// calc_k_alpha2_shift と同じ式。ピークの fwhm と g_ratio は Python 側で求めた値を使う）。

// ---------------------------------------------------------------- worker
const worker = new Worker("worker.js");
let reqId = 0;
const pending = new Map();
let engineReady = false;

worker.onmessage = (ev) => {
  const m = ev.data;
  if (m.type === "ready") {
    engineReady = true;
    setEngineStatus("ready", "Calculation engine ready (runs in this browser; data is not uploaded)");
    if (queuedFile) { const f = queuedFile; queuedFile = null; loadFile(f); }
  } else if (m.type === "init_error") {
    setEngineStatus("error", "Failed to load calculation engine: " + m.error);
  } else if (m.type === "progress") {
    $("progress").max = m.max || 1;
    $("progress").value = m.step;
    $("progress-text").textContent = `${m.step} / ${m.max}`;
  } else if (m.type === "result") {
    const p = pending.get(m.id);
    pending.delete(m.id);
    if (!p) return;
    m.ok ? p.resolve(m.result) : p.reject(new Error(m.error));
  }
};

function call(cmd, args, transfer = []) {
  const id = ++reqId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, cmd, args }, transfer);
  });
}

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
function setEngineStatus(cls, text) { const e = $("engine-status"); e.className = "engine " + cls; e.textContent = text; }
function toast(text, ms = 2500) { const t = $("toast"); t.textContent = text; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms); }
const fmt = (v, d = 4) => (Number.isFinite(v) ? v.toFixed(d) : String(v));
const arrMin = (a) => a.reduce((m, v) => (v < m ? v : m), Infinity);
const arrMax = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity);

const COLORS = ["#fb756c", "#a7a923", "#0eba72", "#21b4fa", "#e96bf5", "#9977cc", "#5300ed"];

// core/math_utils.py pseudo_voigt と同じ式（G と L で FWHM 共通）
const LN2 = Math.log(2);
function pseudoVoigt(x, a, x0, fwhm, g) {
  fwhm = Math.max(fwhm, 1e-6);
  const G = new Array(x.length), L = new Array(x.length), T = new Array(x.length);
  for (let i = 0; i < x.length; i++) {
    const d2 = ((x[i] - x0) / fwhm) ** 2;
    const gg = g * a * Math.exp(-4 * LN2 * d2);
    const ll = (1 - g) * a / (1 + 4 * d2);
    G[i] = gg; L[i] = ll; T[i] = gg + ll;
  }
  return { total: T, g: G, l: L };
}
// core/math_utils.py calc_k_alpha2_shift と同じ式
function ka2Shift(x0) {
  const th = (x0 / 2) * (Math.PI / 180);
  return 2 * Math.tan(th) * (0.0038 / 1.5406) * (180 / Math.PI);
}
function baselineY(x, pts) {
  if (!pts) return x.map(() => 0);
  const [x0, y0, x1, y1] = pts;
  if (x1 === x0) return x.map(() => y0);
  const m = (y1 - y0) / (x1 - x0), c = y0 - m * x0;
  return x.map((v) => m * v + c);
}
function adjustLightness(hex, amount) {
  let r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h /= 6;
  }
  l = amount > 1 ? l + (1 - l) * Math.min(1, amount - 1) : l * amount;
  l = Math.max(0, Math.min(1, l));
  const hue = (p, q, t) => { if (t < 0) t += 1; if (t > 1) t -= 1; if (t < 1 / 6) return p + (q - p) * 6 * t; if (t < 1 / 2) return q; if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6; return p; };
  if (s === 0) r = g = b = l;
  else { const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q; r = hue(p, q, h + 1 / 3); g = hue(p, q, h); b = hue(p, q, h - 1 / 3); }
  return `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
}

// ---------------------------------------------------------------- state (state.py)
const S = {
  filename: "", rawX: [], rawY: [], x: [], y: [], smoothed: false,
  bminX: null, bmaxX: null, baselinePts: null, peaks: [],
  mode: "none", showFit: true, xRange: null, yRange: null,
  integral: null, busy: false,
  profile: "pv",   // "pv": FWHM 共通（標準） / "tch": G と L の幅を別々（上級者向け）
};

// state.py の Peak と同じ項目。fwhm = 0 は「FWHM 未指定」（曲線を描かない）
function newPeak(id, x0, y0) {
  return { id, x0, y0, fwhm: 0, a: 0, g_ratio: 0.8, fwhm_g: 0, fwhm_l: 0, area: 0,
    has_k_alpha2: false, show_gl_curves: false,
    lock_x0: false, lock_a: false, lock_g_ratio: false, lock_fwhm: false,
    lock_fwhm_g: false, lock_fwhm_l: false, lock_all: false };
}
// core/fitter.py の関数で派生値を計算し直す（op: refresh / convert / set_width）
async function peaksOp(op, extra = {}) {
  const r = await call("peaks_op", { op, profile: S.profile, peaks: S.peaks, ...extra });
  S.peaks = r.peaks;
}
function renumber() { S.peaks.sort((a, b) => a.x0 - b.x0); S.peaks.forEach((p, i) => (p.id = i + 1)); }
function clipped() {
  if (S.bminX === null || S.bmaxX === null) return { x: S.x, y: S.y };
  const x = [], y = [];
  for (let i = 0; i < S.x.length; i++) if (S.x[i] >= S.bminX && S.x[i] <= S.bmaxX) { x.push(S.x[i]); y.push(S.y[i]); }
  return { x, y };
}
function fitRequest(extra) {
  return { x: S.x, y: S.y, baseline_min_x: S.bminX, baseline_max_x: S.bmaxX, baseline_pts: S.baselinePts, ...extra };
}

// ---------------------------------------------------------------- loading (drag_drop_window.py)
let queuedFile = null;
const dz = $("dropzone");
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", (e) => {
  e.preventDefault(); dz.classList.remove("over");
  const f = e.dataTransfer.files[0];
  if (f) loadFile(f);
});
$("fileinput").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) loadFile(f); e.target.value = ""; });
$("btn-forward").addEventListener("click", showMain);

async function loadFile(file) {
  // 拡張子では断らない（.xy・.dat なども2列の数値なら読める）。数値が無ければ parse がエラーを返す
  if (!engineReady) { queuedFile = file; toast("Waiting for the calculation engine…"); return; }
  try {
    const bytes = await file.arrayBuffer();
    const r = await call("parse", { bytes }, [bytes]);
    S.filename = file.name; S.rawX = r.x; S.rawY = r.y; S.x = r.x.slice(); S.y = r.y.slice();
    S.smoothed = false; S.bminX = arrMin(r.x); S.bmaxX = arrMax(r.x); S.baselinePts = null; S.peaks = [];
    $("btn-forward").textContent = `Forward to ${file.name} →`;
    $("btn-forward").hidden = false;
    resetMainUi();
    showMain();
    resetView();
  } catch (e) {
    alert("Failed to parse file:\n" + e.message);
  }
}

function showMain() {
  $("loader").hidden = true; $("main").hidden = false;
  $("filename").textContent = S.filename;
  document.title = `SpectrumAnalyzer - ${S.filename}`;
  redraw(); rebuildTable();
  Plotly.Plots.resize($("plot"));
}

function resetMainUi() {
  setMode("none");
  $("btn-smooth").classList.remove("on");
  S.showFit = true; $("btn-showfit").classList.add("on");
  $("mse").textContent = "MSE: N/A";
  S.integral = null;
}

$("btn-back").addEventListener("click", () => {
  // go_back: ベースライン・積分表示・モードを初期化して読み込み画面へ
  S.baselinePts = null; S.integral = null;
  S.x = S.rawX.slice(); S.y = S.rawY.slice(); S.smoothed = false;
  if (S.x.length) { S.bminX = arrMin(S.x); S.bmaxX = arrMax(S.x); }
  resetMainUi();
  $("main").hidden = true; $("loader").hidden = false;
});

// ---------------------------------------------------------------- view
function autoY(xmin, xmax) {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < S.x.length; i++) if (S.x[i] >= xmin && S.x[i] <= xmax) { lo = Math.min(lo, S.y[i]); hi = Math.max(hi, S.y[i]); }
  if (!Number.isFinite(lo)) return;
  let m = (hi - lo) * 0.1; if (m === 0) m = 1;
  S.yRange = [lo - m, hi + m];
}
function setXZoom(xmin, xmax) { S.xRange = [xmin, xmax]; autoY(xmin, xmax); redraw(); }
function resetView() {
  if (!S.x.length) return;
  const a = arrMin(S.x), b = arrMax(S.x);
  setXZoom(a, b);
  $("xmin").value = a.toFixed(3); $("xmax").value = b.toFixed(3);
}

function setMode(mode) {
  S.mode = mode;
  document.querySelectorAll("button.mode").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  $("plot").className = "mode-" + mode;
}
document.querySelectorAll("button.mode").forEach((b) =>
  b.addEventListener("click", () => setMode(S.mode === b.dataset.mode ? "none" : b.dataset.mode)));

$("btn-orig").addEventListener("click", () => { resetView(); setMode("none"); });
for (const id of ["xmin", "xmax"]) {
  $(id).addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const a = parseFloat($("xmin").value), b = parseFloat($("xmax").value);
    if (Number.isFinite(a) && Number.isFinite(b)) { setXZoom(a, b); setMode("baseline"); }
  });
}

$("btn-smooth").addEventListener("click", async () => {
  const on = !S.smoothed;
  if (on) { const r = await call("smooth", { y: S.rawY }); S.y = r.y; }
  else S.y = S.rawY.slice();
  S.smoothed = on; $("btn-smooth").classList.toggle("on", on);
  redraw();
});

$("btn-showfit").addEventListener("click", () => {
  S.showFit = !S.showFit; $("btn-showfit").classList.toggle("on", S.showFit); redraw();
});

$("btn-integral").addEventListener("click", async () => {
  if (!S.baselinePts) return;
  const r = await call("integral", fitRequest({}));
  S.integral = r; redraw();
  try { await navigator.clipboard.writeText(String(r.area)); } catch (_) { /* clipboard may be unavailable */ }
  clearTimeout(S._intTimer);
  S._intTimer = setTimeout(() => { S.integral = null; redraw(); }, 2000);
});

// ---------------------------------------------------------------- plot (plot_canvas.py)
const plotEl = $("plot");
let plotInited = false;

function buildTraces() {
  const traces = [{ x: S.x, y: S.y, mode: "markers", type: "scatter", name: "data",
    marker: { symbol: "circle-open", size: 5, color: "rgba(0,0,0,0.7)" } }];

  if (S.baselinePts) {
    const [x0, y0, x1, y1] = S.baselinePts;
    traces.push({ x: [x0, x1], y: [y0, y1], mode: "lines", line: { color: "red", width: 2 }, name: "baseline" });
  }

  if (S.integral) {
    const { x, y, base_y, area } = S.integral;
    const step = Math.max(1, Math.floor(x.length / 1000));
    const lx = [], ly = [];
    for (let i = 0; i < x.length; i += step) { lx.push(x[i], x[i], null); ly.push(base_y[i], y[i], null); }
    traces.push({ x: lx, y: ly, mode: "lines", line: { color: "rgba(255,0,0,0.5)", width: 0.5 }, name: `Area = ${area.toFixed(2)}` });
  }

  const { x: cx } = clipped();
  if (!cx.length) return traces;
  const lo = arrMin(cx), hi = arrMax(cx);
  const n = Math.max(cx.length * 2, 1000);
  const xp = Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1));
  const bp = baselineY(xp, S.baselinePts);
  const ytop = S.yRange ? S.yRange[1] : 0;

  S.peaks.forEach((p, i) => {
    const color = COLORS[i % COLORS.length];
    traces.push({ x: [p.x0, p.x0], y: [p.y0, p.y0 + ytop * 0.05], mode: "lines", line: { color, width: 2 }, name: `Peak #${p.id}` });
    if (p.fwhm > 0) {
      const pv = pseudoVoigt(xp, p.a, p.x0, p.fwhm, p.g_ratio);
      traces.push({ x: xp, y: pv.total.map((v, k) => v + bp[k]), mode: "lines", line: { color, width: 2 }, name: `Peak #${p.id}` });
      if (p.show_gl_curves) {
        traces.push({ x: xp, y: pv.g.map((v, k) => v + bp[k]), mode: "lines", line: { color: adjustLightness(color, 1.4), width: 1.5, dash: "dot" }, name: `#${p.id} G` });
        traces.push({ x: xp, y: pv.l.map((v, k) => v + bp[k]), mode: "lines", line: { color: adjustLightness(color, 0.6), width: 1.5, dash: "dot" }, name: `#${p.id} L` });
      }
      if (p.has_k_alpha2) {
        const k2 = pseudoVoigt(xp, p.a * 0.5, p.x0 + ka2Shift(p.x0), p.fwhm, p.g_ratio);
        traces.push({ x: xp, y: k2.total.map((v, k) => v + bp[k]), mode: "lines", line: { color, width: 2, dash: "dash" }, name: `#${p.id} K-a2` });
      }
    }
  });

  if (S.showFit && S.peaks.length) {
    const tot = bp.slice();
    for (const p of S.peaks) {
      if (!(p.fwhm > 0)) continue;
      const pv = pseudoVoigt(xp, p.a, p.x0, p.fwhm, p.g_ratio).total;
      for (let k = 0; k < n; k++) tot[k] += pv[k];
      if (p.has_k_alpha2) {
        const k2 = pseudoVoigt(xp, p.a * 0.5, p.x0 + ka2Shift(p.x0), p.fwhm, p.g_ratio).total;
        for (let k = 0; k < n; k++) tot[k] += k2[k];
      }
    }
    traces.push({ x: xp, y: tot, mode: "lines", line: { color: "black", width: 2 }, name: "Total fit" });
  }
  return traces;
}

function buildLayout(shapes = []) {
  const ann = S.integral ? [{ xref: "paper", yref: "paper", x: 0.5, y: 0.95, showarrow: false,
    text: `Area = ${S.integral.area.toFixed(2)}`, bgcolor: "rgba(255,255,255,0.8)", bordercolor: "#999" }] : [];
  return {
    margin: { l: 60, r: 20, t: 20, b: 45 },
    xaxis: { range: S.xRange, title: { text: "2θ" }, zeroline: false },
    yaxis: { range: S.yRange, title: { text: "Intensity" }, zeroline: false },
    showlegend: false, dragmode: false, hovermode: false, shapes, annotations: ann,
  };
}

function redraw(shapes) {
  if ($("main").hidden) return;
  const config = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"] };
  Plotly.react(plotEl, buildTraces(), buildLayout(shapes), config);
  plotInited = true;
}

// pixel → data 座標
function evToData(ev) {
  const fl = plotEl._fullLayout; if (!fl) return null;
  const xa = fl.xaxis, ya = fl.yaxis, r = plotEl.getBoundingClientRect();
  const px = ev.clientX - r.left - xa._offset, py = ev.clientY - r.top - ya._offset;
  return { x: xa.p2l(px), y: ya.p2l(py), inside: px >= 0 && px <= xa._length && py >= 0 && py <= ya._length };
}

// ドラッグ中の仮の線・範囲は、グラフを描き直さずに重ね描き用キャンバスへ直接描く
const overlay = $("overlay");
const octx = overlay.getContext("2d");
function prepareOverlay() {
  const r = overlay.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  overlay.width = Math.round(r.width * dpr); overlay.height = Math.round(r.height * dpr);
  octx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function clearOverlay() { octx.clearRect(0, 0, overlay.width, overlay.height); }
function drawOverlay(startEv, ev) {
  const fl = plotEl._fullLayout; if (!fl) return;
  const xa = fl.xaxis, ya = fl.yaxis, r = overlay.getBoundingClientRect();
  const L = xa._offset, T = ya._offset, W = xa._length, H = ya._length;
  const clampX = (v) => Math.max(L, Math.min(L + W, v)), clampY = (v) => Math.max(T, Math.min(T + H, v));
  const sx = clampX(startEv.clientX - r.left), sy = clampY(startEv.clientY - r.top);
  const ex = clampX(ev.clientX - r.left), ey = clampY(ev.clientY - r.top);
  clearOverlay();
  octx.lineWidth = 2;
  if (S.mode === "baseline") {
    octx.strokeStyle = "red"; octx.beginPath(); octx.moveTo(sx, sy); octx.lineTo(ex, ey); octx.stroke();
  } else if (S.mode === "fwhm") {
    octx.strokeStyle = "green"; octx.beginPath(); octx.moveTo(sx, sy); octx.lineTo(ex, sy); octx.stroke();
  } else {
    octx.fillStyle = "rgba(0,0,255,0.2)"; octx.fillRect(Math.min(sx, ex), T, Math.abs(ex - sx), H);
  }
}

let drag = null;
plotEl.addEventListener("mousedown", (ev) => {
  if (ev.button !== 0 || S.busy) return;
  const d = evToData(ev);
  if (!d || !d.inside) return;
  ev.preventDefault();
  drag = { x0: d.x, y0: d.y, ev };
  prepareOverlay();
});
window.addEventListener("mousemove", (ev) => {
  if (drag) drawOverlay(drag.ev, ev);
});
window.addEventListener("mouseup", (ev) => {
  if (!drag) return;
  const start = drag; drag = null;
  const d = evToData(ev);
  clearOverlay();
  if (!d || !d.inside) return;
  if (S.mode === "baseline") finalizeBaseline(start.x0, start.y0, d.x, d.y);
  else if (S.mode === "peak_select") finalizePeakSelect(start.x0, d.x);
  else if (S.mode === "fwhm") finalizeFwhm(start.x0, d.x);
  else if (S.mode === "none") finalizeZoom(start.x0, d.x);
});

function finalizeZoom(x0, x1) {
  const a = Math.min(x0, x1), b = Math.max(x0, x1);
  if (Math.abs(b - a) <= 1e-4) return;
  setXZoom(a, b);
  $("xmin").value = a.toFixed(3); $("xmax").value = b.toFixed(3);
  setMode("baseline");
}

function finalizeBaseline(x0, y0, x1, y1) {
  if (x0 > x1) [x0, y0, x1, y1] = [x1, y1, x0, y0];
  S.baselinePts = [x0, y0, x1, y1];
  S.bminX = x0; S.bmaxX = x1;
  redraw();
  setMode("peak_select");
}

function finalizePeakSelect(x0, x1) {
  const a = Math.min(x0, x1), b = Math.max(x0, x1);
  const { x, y } = clipped();
  const xr = [], yr = [];
  for (let i = 0; i < x.length; i++) if (x[i] >= a && x[i] <= b) { xr.push(x[i]); yr.push(y[i]); }
  if (!xr.length) return;
  const base = baselineY(xr, S.baselinePts);
  let best = 0;
  for (let i = 1; i < xr.length; i++) if (yr[i] - base[i] > yr[best] - base[best]) best = i;
  const p = newPeak(Math.max(0, ...S.peaks.map((q) => q.id)) + 1, xr[best], yr[best]);
  p.a = yr[best] - base[best];
  S.peaks.push(p); renumber();
  redraw(); rebuildTable();
  setMode("fwhm");
}

async function finalizeFwhm(x0, x1) {
  if (!S.peaks.length) return;
  const width = Math.abs(x1 - x0), center = (x0 + x1) / 2;
  let peak = S.peaks[0];
  for (const p of S.peaks) if (Math.abs(p.x0 - center) < Math.abs(peak.x0 - center)) peak = p;
  // FWHM 共通ならドラッグした幅がそのまま FWHM。TCH なら全体の FWHM がこの幅になる G/L の幅を求める
  await peaksOp("set_width", { index: S.peaks.indexOf(peak), fwhm: width, g_ratio: peak.g_ratio });
  rebuildTable(); redraw();
  setMode("peak_select");
}

// ---------------------------------------------------------------- fitting
async function runFit(kind, index) {
  const { x } = clipped();
  if (!x.length) return;
  if (kind === "global" && !S.peaks.length) return;
  setBusy(true);
  $("progress").value = 0; $("progress").removeAttribute("value"); $("progress-text").textContent = "";
  try {
    const r = await call("fit", fitRequest({ kind, index, peaks: S.peaks, method: $("algo").value, profile: S.profile }));
    S.peaks = r.peaks;
    if (r.mse !== null && !r.timeout) {
      $("mse").textContent = (kind === "global" ? "G-MSE: " : "MSE: ") + r.mse.toFixed(4);
      $("progress").value = $("progress").max;
    }
    rebuildTable(); redraw();
    if (r.timeout) { $("progress").value = 0; alert(`${kind === "global" ? "Global fitting" : "Fitting"} exceeded 45 seconds and was aborted. Results may be incomplete.`); }
  } catch (e) {
    alert("Fitting failed:\n" + e.message);
  } finally {
    setBusy(false);
  }
}
function setBusy(b) {
  S.busy = b;
  document.querySelectorAll("#btn-allfit, #peaks button, #btn-clear").forEach((e) => (e.disabled = b));
}
$("btn-allfit").addEventListener("click", () => runFit("global"));
$("btn-clear").addEventListener("click", () => { S.peaks = []; rebuildTable(); redraw(); });

// ---------------------------------------------------------------- G/L
$("global-g").addEventListener("input", (e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) $("global-l").value = (1 - v).toFixed(2); });
$("global-l").addEventListener("input", (e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) $("global-g").value = (1 - v).toFixed(2); });
$("btn-apply-gl").addEventListener("click", async () => {
  const g = parseFloat($("global-g").value);
  if (!Number.isFinite(g)) return;
  // TCH では全体の FWHM を保ったまま、この割合になる G/L の幅に直す
  await peaksOp("set_width", { g_ratio: Math.max(0, Math.min(1, g)) });
  rebuildTable(); redraw();
});

$("profile").addEventListener("change", async (e) => {
  S.profile = e.target.value;
  await peaksOp("convert");   // 各ピークの形（全体の FWHM と G Frac）を保って切り替える
  $("mse").textContent = "MSE: N/A";
  rebuildTable(); redraw();
});

// ---------------------------------------------------------------- table (ui/peak_table.py と同じ列)
// [種類, 見出し, 項目]  num: 編集できる値 / ro: 派生値（表示のみ） / lock: ロック
const LOCK = "\u{1F512}";
const HEAD = [["del", "Del"], ["lock_all", "Lock All"], ["id", "Peak #"],
  ["num", "X (x0)", "x0"], ["lock", LOCK, "lock_x0"], ["num", "A", "a"], ["lock", LOCK, "lock_a"]];
const TAIL = [["ro", "Area", "area"], ["ka2", "K-a2"], ["fit", "Fit"], ["gl", "G/L"]];
const COLUMNS = {
  pv: [...HEAD,
    ["num", "G Frac", "g_ratio"], ["num", "L Frac", "l_ratio"], ["lock", LOCK, "lock_g_ratio"],
    ["num", "FWHM", "fwhm"], ["lock", LOCK, "lock_fwhm"], ...TAIL],
  tch: [...HEAD,
    ["num", "FWHM_G", "fwhm_g"], ["lock", LOCK, "lock_fwhm_g"],
    ["num", "FWHM_L", "fwhm_l"], ["lock", LOCK, "lock_fwhm_l"],
    ["ro", "G Frac", "g_ratio"], ["ro", "L Frac", "l_ratio"], ["ro", "FWHM", "fwhm"], ...TAIL],
};
const valueOf = (p, field) => (field === "l_ratio" ? 1 - p.g_ratio : p[field]);

async function onCellEdit(p, field, v) {
  if (field === "g_ratio") p.g_ratio = Math.max(0, Math.min(1, v));
  else if (field === "l_ratio") p.g_ratio = 1 - Math.max(0, Math.min(1, v));
  else if (["fwhm", "fwhm_g", "fwhm_l"].includes(field)) p[field] = Math.max(0, v);
  else p[field] = v;
  await peaksOp("refresh");   // 面積や、TCH の FWHM・G Frac を計算し直す
  rebuildTable(); redraw();
}

function rebuildTable() {
  const cols = COLUMNS[S.profile];
  const head = document.querySelector("#peaks thead tr");
  head.innerHTML = "";
  for (const [, h] of cols) { const th = document.createElement("th"); th.textContent = h; head.appendChild(th); }

  const tb = document.querySelector("#peaks tbody");
  tb.innerHTML = "";
  S.peaks.forEach((p, row) => {
    const tr = document.createElement("tr");
    const td = (el) => { const c = document.createElement("td"); if (el instanceof Node) c.appendChild(el); else c.textContent = el; tr.appendChild(c); return c; };
    const btn = (label, fn) => { const b = document.createElement("button"); b.textContent = label; b.disabled = S.busy; b.onclick = fn; return b; };
    const cb = (prop, label = "") => {
      const l = document.createElement("label"); const c = document.createElement("input");
      c.type = "checkbox"; c.checked = p[prop];
      c.onchange = () => { p[prop] = c.checked; redraw(); };
      l.appendChild(c); if (label) l.append(" " + label); return l;
    };
    const num = (field) => {
      const i = document.createElement("input"); i.type = "text"; i.value = fmt(valueOf(p, field));
      i.onchange = () => {
        const v = parseFloat(i.value);
        if (!Number.isFinite(v)) { i.value = fmt(valueOf(p, field)); return; }
        onCellEdit(p, field, v);
      };
      return i;
    };

    for (const [kind, , field] of cols) {
      if (kind === "del") td(btn("\u{1F5D1}️", () => { S.peaks.splice(row, 1); renumber(); rebuildTable(); redraw(); }));
      else if (kind === "lock_all") td(cb("lock_all", LOCK));
      else if (kind === "id") td(`Peak #${p.id}`);
      else if (kind === "num") td(num(field));
      else if (kind === "ro") td(fmt(valueOf(p, field))).className = "ro";
      else if (kind === "lock") td(cb(field));
      else if (kind === "ka2") td(cb("has_k_alpha2", "K-α2"));
      else if (kind === "fit") td(btn("Fit", () => runFit("individual", row)));
      else if (kind === "gl") td(cb("show_gl_curves", "G/L"));
    }
    tb.appendChild(tr);
  });
}
rebuildTable();

window.addEventListener("resize", () => { if (plotInited && !$("main").hidden) Plotly.Plots.resize(plotEl); });
