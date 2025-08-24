// webviz/static/app.js
let NUM_FRAMES = 0;
let playing = false;
let frameIdx = 1;
let timer = null;
let METRICS = { burning_cells: [], natural_burnouts: [], extinguished_cum: [] };

const $ = (id) => document.getElementById(id);

function setFrameRange(n) {
  $("frame").max = String(n);
  $("nframes").textContent = String(n);
  $("end").value = String(n);
}

function setFrameIndicator(k) {
  $("frame").value = String(k);
  $("frameval").textContent = String(k);
}

async function loadFiles() {
  const ans = $("ans").value.trim();
  const status = $("status").value.trim();
  const index_jsonl = $("index_jsonl").value.trim() || null;
  $("loadmsg").textContent = "Loading...";
  try {
    const resp = await fetch("/api/load", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        ans_path: ans,
        index_jsonl,
        agent_status_path: status || null
      })
    });
    if (!resp.ok) {
      const e = await resp.json();
      throw new Error(e.detail || resp.statusText);
    }
    const data = await resp.json();
    NUM_FRAMES = data.num_frames;
    METRICS = data.metrics || METRICS;
    setFrameRange(NUM_FRAMES);
    setFrameIndicator(1);
    $("loadmsg").textContent = `Loaded ${NUM_FRAMES} frames`;
    await showFrame(1);
    renderMetricsTable();
    drawCharts();
  } catch (err) {
    $("loadmsg").textContent = "Error: " + err.message;
    console.error(err);
  }
}

async function showFrame(k) {
  const resp = await fetch(`/api/frame/${k}`);
  if (!resp.ok) return;
  const data = await resp.json();
  $("grid").innerHTML = data.html;
  setFrameIndicator(k);
  const lines = data.agent_status || [];
  $("agent-status").textContent = lines.length ? lines.join("\n") : "(no agent status)";
}

function play() {
  if (playing || NUM_FRAMES === 0) return;
  playing = true;
  scheduleNext();
}

function pause() {
  playing = false;
  if (timer) { clearTimeout(timer); timer = null; }
}

function scheduleNext() {
  const fps = parseFloat($("fps").value) || 2.0;
  const delay = Math.max(40, 1000.0 / fps);
  timer = setTimeout(async () => {
    if (!playing) return;
    frameIdx = (frameIdx % NUM_FRAMES) + 1;
    await showFrame(frameIdx);
    scheduleNext();
  }, delay);
}

function renderMetricsTable() {
  const n = NUM_FRAMES;
  const b = METRICS.burning_cells || [];
  const nb = METRICS.natural_burnouts || [];
  const ex = METRICS.extinguished_cum || [];
  let html = "<table><thead><tr><th>k</th><th>Burning</th><th>Natural</th><th>Extinguished</th></tr></thead><tbody>";
  for (let i = 0; i < n; i++) {
    html += `<tr><td>${i+1}</td><td>${b[i] ?? ""}</td><td>${nb[i] ?? ""}</td><td>${ex[i] ?? ""}</td></tr>`;
  }
  html += "</tbody></table>";
  $("metrics-table").innerHTML = html;
}

function drawSeries(ctx, arr) {
  // draw in auto color (no hard-coded); pick canvas default stroke
  const w = ctx.canvas.width, h = ctx.canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle = "#aaa"; ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(40, 10); ctx.lineTo(40, h-20); ctx.lineTo(w-10, h-20); ctx.stroke();

  const n = arr.length; if (!n) return;
  const maxV = Math.max(...arr.map(v => (v ?? 0)), 1);
  const plotW = w - 50, plotH = h - 30;

  ctx.beginPath();
  for (let i=0;i<n;i++){
    const v = arr[i] ?? 0;
    const x = 40 + (plotW * i) / Math.max(1, n-1);
    const y = (h-20) - (plotH * v) / maxV;
    if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  }
  ctx.stroke();
}

function drawCharts() {
  drawSeries($("chart-burning").getContext("2d"), METRICS.burning_cells || []);
  drawSeries($("chart-ext").getContext("2d"), METRICS.extinguished_cum || []);
  drawSeries($("chart-natural").getContext("2d"), METRICS.natural_burnouts || []);
}

// UI wiring
$("load").addEventListener("click", async () => {
  pause();
  frameIdx = 1;
  await loadFiles();
});
$("play").addEventListener("click", () => { if (NUM_FRAMES > 0) play(); });
$("pause").addEventListener("click", pause);

$("frame").addEventListener("input", async (e) => {
  pause();
  frameIdx = Math.max(1, Math.min(NUM_FRAMES, parseInt(e.target.value, 10) || 1));
  await showFrame(frameIdx);
});

// keyboard: arrows and space
window.addEventListener("keydown", async (e) => {
  if (NUM_FRAMES === 0) return;
  if (e.key === "ArrowRight") {
    pause(); frameIdx = Math.min(NUM_FRAMES, frameIdx + 1); await showFrame(frameIdx);
  } else if (e.key === "ArrowLeft") {
    pause(); frameIdx = Math.max(1, frameIdx - 1); await showFrame(frameIdx);
  } else if (e.key === " ") {
    if (playing) pause(); else play();
  }
});

// live font/bg changes (affects HTML span rendering in server on next fetch)
$("fontsize").addEventListener("input", () => {
  $("grid").style.setProperty("--viewer-font-size", `${parseInt($("fontsize").value, 10)}px`);
});
$("bg").addEventListener("input", () => {
  $("grid").style.background = $("bg").value;
});

// Export controls
async function postAndDownload(url, payload, filename) {
  $("exportmsg").textContent = "Rendering...";
  const resp = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  if (!resp.ok) {
    const e = await resp.json().catch(() => ({}));
    $("exportmsg").textContent = "Error: " + (e.detail || resp.statusText);
    return;
  }
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  $("exportmsg").textContent = "Done.";
}

$("export-gif").addEventListener("click", async () => {
  const payload = {
    start: parseInt($("start").value, 10) || 1,
    end: parseInt($("end").value, 10) || NUM_FRAMES,
    fps: parseFloat($("xfps").value) || 2,
    font_size: parseInt($("xfont").value, 10) || 14,
    bg_color: $("xbg").value || "#111111"
  };
  await postAndDownload("/api/export/gif", payload, "wildfire_replay.gif");
});

$("export-png").addEventListener("click", async () => {
  const payload = {
    start: parseInt($("start").value, 10) || 1,
    end: parseInt($("end").value, 10) || NUM_FRAMES,
    font_size: parseInt($("xfont").value, 10) || 14,
    bg_color: $("xbg").value || "#111111"
  };
  await postAndDownload("/api/export/pngzip", payload, "wildfire_frames.zip");
});
