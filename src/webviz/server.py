# webviz/server.py
from __future__ import annotations

import io
import os
import tempfile
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

from .ansi import ansi_to_html, parse_metrics, FrameSource, ansi_to_image

# ---------- App & static ----------
app = FastAPI(title="Wildfire Log Viewer")
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ---------- Session ----------
class LoadReq(BaseModel):
    ans_path: str
    index_jsonl: Optional[str] = None
    meta_json: Optional[str] = None
    agent_status_path: Optional[str] = None


class ExportReq(BaseModel):
    # Range is 1-based inclusive
    start: Optional[int] = None
    end: Optional[int] = None
    fps: float = 2.0
    font_size: int = 14
    bg_color: str = "#111111"


class Session:
    def __init__(self):
        self.source: Optional[FrameSource] = None
        self.metrics: dict = {}
        self.agent_status: List[List[str]] = []


SESSION = Session()


# ---------- Utils ----------
def _read_text(path: str) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_agent_status(txt: str) -> List[List[str]]:
    steps: List[List[str]] = []
    acc: List[str] = []
    for line in txt.splitlines():
        t = line.strip()
        if t.lower().startswith("step "):
            if acc:
                steps.append(acc);
                acc = []
        elif t:
            acc.append(t)
    if acc:
        steps.append(acc)
    return steps


# ---------- Routes ----------
@app.get("/")
def index():
    path = os.path.join(static_dir, "index.html")
    return HTMLResponse(_read_text(path))


@app.post("/api/load")
def api_load(req: LoadReq):
    # Fallback: if index_jsonl not given, try <ans>.index.jsonl in same dir
    index_path = req.index_jsonl
    if not index_path:
        base, ext = os.path.splitext(req.ans_path)
        candidate = base + ".index.jsonl"
        if os.path.isfile(candidate):
            index_path = candidate

    try:
        src = FrameSource(req.ans_path, index_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {req.ans_path}")
    if len(src) == 0:
        raise HTTPException(status_code=400, detail="No frames detected in file")

    # Precompute HTML frames only on demand in /api/frame; keep memory light
    # But compute metrics once (requires all frames). For large files, you may
    # swap this to incremental (or use meta.json if it already contains arrays).
    frames = [src.get(k) for k in range(1, len(src) + 1)]
    metrics = parse_metrics(frames)

    SESSION.source = src
    SESSION.metrics = metrics

    # optional agent status
    SESSION.agent_status = []
    if req.agent_status_path:
        try:
            SESSION.agent_status = _parse_agent_status(_read_text(req.agent_status_path))
        except FileNotFoundError:
            SESSION.agent_status = []

    return JSONResponse({
        "ok": True,
        "num_frames": len(src),
        "metrics": metrics,
        "has_agent_status": bool(SESSION.agent_status),
    })


@app.get("/api/frame/{k}")
def api_frame(k: int):
    if SESSION.source is None:
        raise HTTPException(status_code=400, detail="No file loaded")
    n = len(SESSION.source)
    if k < 1 or k > n:
        raise HTTPException(status_code=400, detail=f"Frame index out of range 1..{n}")
    raw = SESSION.source.get(k)
    html = ansi_to_html(raw)
    payload = {
        "index": k,
        "html": html,
        "agent_status": SESSION.agent_status[k - 1] if 0 <= (k - 1) < len(SESSION.agent_status) else [],
        "burning": SESSION.metrics.get("burning_cells", [None] * n)[k - 1],
        "natural": SESSION.metrics.get("natural_burnouts", [None] * n)[k - 1],
        "ext": SESSION.metrics.get("extinguished_cum", [None] * n)[k - 1],
    }
    return JSONResponse(payload)


@app.post("/api/export/gif")
def api_export_gif(cfg: ExportReq):
    if SESSION.source is None:
        raise HTTPException(status_code=400, detail="No file loaded")

    n = len(SESSION.source)
    start = max(1, min(cfg.start or 1, n))
    end   = max(start, min(cfg.end or n, n))

    frames = []
    for k in range(start, end + 1):
        raw = SESSION.source.get(k)
        img = ansi_to_image(raw, font_size=cfg.font_size, bg_color=cfg.bg_color)
        # ✅ Quantize with an adaptive 256-color palette
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=256))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gif")
    ms_per_frame = int(1000.0 / max(cfg.fps, 0.1))

    # ✅ Save with Pillow, preserving palette
    frames[0].save(
        tmp.name,
        save_all=True,
        append_images=frames[1:],
        duration=ms_per_frame,
        loop=0,
        optimize=False,
        disposal=2,  # avoid trails in some viewers
    )

    return FileResponse(tmp.name, media_type="image/gif", filename="wildfire_replay.gif")



@app.post("/api/export/pngzip")
def api_export_pngzip(cfg: ExportReq):
    """
    Render frames to PNG files and return a ZIP archive.
    """
    import zipfile
    if SESSION.source is None:
        raise HTTPException(status_code=400, detail="No file loaded")

    n = len(SESSION.source)
    start = cfg.start or 1
    end = cfg.end or n
    start = max(1, min(start, n))
    end = max(start, min(end, n))

    tmpzip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmpzip.name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for k in range(start, end + 1):
            raw = SESSION.source.get(k)
            img = ansi_to_image(raw, font_size=cfg.font_size, bg_color=cfg.bg_color)
            # write into zip
            io_bytes = io.BytesIO()
            img.save(io_bytes, format="PNG")
            zf.writestr(f"frame_{k:05d}.png", io_bytes.getvalue())
    return FileResponse(tmpzip.name, media_type="application/zip", filename="wildfire_frames.zip")


def run(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
