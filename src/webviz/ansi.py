# webviz/ansi.py
from __future__ import annotations
import html
import io
import json
import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ========= ANSI parsing =========
# Accepts SGR sequences like:
#  - "\x1b[0m" reset
#  - "\x1b[1m" bold
#  - "\x1b[34m" fg basic
#  - "\x1b[107m" bg bright
#  - "\x1b[38;5;178m" fg 256-color
#  - "\x1b[48;5;52m"  bg 256-color

SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# Basic 16-color FG/BG mapping
BASIC_COLORS = {
    30: "#000000", 31: "#b22222", 32: "#228b22", 33: "#b8860b",
    34: "#1e90ff", 35: "#9932cc", 36: "#20b2aa", 37: "#bfbfbf",
    90: "#808080", 91: "#ff4d4d", 92: "#59c659", 93: "#ffd24d",
    94: "#4d88ff", 95: "#cc66ff", 96: "#33cccc", 97: "#ffffff"
}
BASIC_BG = {c + 10: col for c, col in BASIC_COLORS.items()}
# Add bright backgrounds 100–107
BASIC_BG.update({
    100: "#555555", 101: "#ff6b6b", 102: "#6bd36b", 103: "#ffe27a",
    104: "#7aa7ff", 105: "#da8cff", 106: "#66e0e0", 107: "#f7f7f7"
})

def xterm_256_to_hex(n: int) -> str:
    """Convert xterm-256 color code (0..255) to hex string."""
    # 0..15: system colors (approx)
    if n < 16:
        # simple fallback using BASIC_COLORS palette for common cases
        # map a few frequently used (e.g., 8..15 are brights)
        LUT = {
            0:"#000000", 1:"#800000", 2:"#008000", 3:"#808000",
            4:"#000080", 5:"#800080", 6:"#008080", 7:"#c0c0c0",
            8:"#808080", 9:"#ff0000", 10:"#00ff00", 11:"#ffff00",
            12:"#0000ff", 13:"#ff00ff", 14:"#00ffff", 15:"#ffffff",
        }
        return LUT.get(n, "#cccccc")
    # 16..231: 6x6x6 color cube
    if 16 <= n <= 231:
        n -= 16
        r = (n // 36) % 6
        g = (n // 6) % 6
        b = n % 6
        to_255 = lambda v: 0 if v == 0 else 55 + v * 40
        return f"#{to_255(r):02x}{to_255(g):02x}{to_255(b):02x}"
    # 232..255: grayscale ramp
    if 232 <= n <= 255:
        v = 8 + (n - 232) * 10
        return f"#{v:02x}{v:02x}{v:02x}"
    return "#cccccc"

@dataclass
class Style:
    bold: bool = False
    fg: Optional[str] = None
    bg: Optional[str] = None

@dataclass
class Span:
    text: str
    style: Style

def parse_ansi_to_spans(s: str) -> List[Span]:
    """Parse ANSI SGR codes into text spans with styles."""
    spans: List[Span] = []
    i = 0
    cur = Style()
    buf: List[str] = []

    def flush():
        if buf:
            spans.append(Span("".join(buf), Style(cur.bold, cur.fg, cur.bg)))
            buf.clear()

    for m in SGR_RE.finditer(s):
        # plaintext before this code
        chunk = s[i:m.start()]
        if chunk:
            buf.append(chunk)
        codes = m.group(1)
        if codes == "" or codes == "0":
            # reset
            flush()
            cur = Style()
        else:
            parts = [int(p) for p in codes.split(";") if p.isdigit()]
            # interpret in sequence
            j = 0
            while j < len(parts):
                c = parts[j]
                if c == 0:
                    flush(); cur = Style()
                elif c == 1:
                    flush(); cur.bold = True
                elif 30 <= c <= 37 or 90 <= c <= 97:
                    flush(); cur.fg = BASIC_COLORS.get(c, cur.fg)
                elif 40 <= c <= 47 or 100 <= c <= 107:
                    flush(); cur.bg = BASIC_BG.get(c, cur.bg)
                elif c == 38 and j + 2 < len(parts) and parts[j+1] == 5:
                    # 38;5;n
                    flush(); cur.fg = xterm_256_to_hex(parts[j+2]); j += 2
                elif c == 48 and j + 2 < len(parts) and parts[j+1] == 5:
                    # 48;5;n
                    flush(); cur.bg = xterm_256_to_hex(parts[j+2]); j += 2
                else:
                    # ignore other SGR codes
                    pass
                j += 1
        i = m.end()
    # trailing text
    if i < len(s):
        buf.append(s[i:])
    flush()
    return spans

# ========= HTML rendering =========

def ansi_to_html(s: str) -> str:
    """Convert ANSI text to HTML (spans with inline styles)."""
    lines = s.splitlines()
    out_lines: List[str] = []
    for line in lines:
        spans = parse_ansi_to_spans(line)
        parts: List[str] = []
        for sp in spans:
            txt = html.escape(sp.text)
            style_bits = []
            if sp.style.fg:
                style_bits.append(f"color:{sp.style.fg}")
            if sp.style.bg:
                style_bits.append(f"background-color:{sp.style.bg}")
            if sp.style.bold:
                style_bits.append("font-weight:bold")
            style_attr = f' style="{";".join(style_bits)}"' if style_bits else ""
            parts.append(f"<span{style_attr}>{txt}</span>")
        out_lines.append("".join(parts) or "&nbsp;")
    return "<br/>".join(out_lines)

# ========= Frame splitting / metrics =========

STEP_HDR_VARIANTS = [
    # Variant A (RL demo): "Step k: Burning cells = X"
    re.compile(r"^(?:\x1b\[1m)?Step\s+(\d+)\x1b\[0m?:\s*Burning\s*cells\s*=\s*(\d+)", re.I),
    # Variant B (save_log_files): "Step k: Burning=..., Extinguished=..., Natural Burnouts=..."
    re.compile(r"^(?:\x1b\[1m)?Step\s+(\d+)\x1b\[0m?:\s*Burning\s*=\s*(\d+)", re.I),
]

def is_step_header(line: str) -> Optional[Tuple[int, int]]:
    for rx in STEP_HDR_VARIANTS:
        m = rx.match(line.strip())
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except Exception:
                return None
    return None

def split_frames_by_headers(raw_text: str) -> List[str]:
    lines = raw_text.splitlines()
    idx = [i for i, l in enumerate(lines) if is_step_header(l)]
    if not idx:
        return []
    idx.append(len(lines))
    frames = []
    for s, e in zip(idx[:-1], idx[1:]):
        block = "\n".join(lines[s:e]).rstrip()
        if block:
            frames.append(block)
    return frames

def parse_metrics(frames: List[str]) -> dict:
    burning, natural, extinguished = [], [], []
    for block in frames:
        lines = block.splitlines()
        # header: try both variants
        b = None
        if lines:
            hdr = is_step_header(lines[0])
            if hdr:
                b = hdr[1]
        # scan rest of block for natural / extinguished in both formats
        nb, ex = None, None
        for ln in lines[1:6]:
            s = ln.strip().lower()
            # Variant A lines
            if s.startswith("natural burnouts"):
                m = re.search(r"(\d+)", s); nb = int(m.group(1)) if m else nb
            if s.startswith("extinguished by agents"):
                m = re.search(r"(\d+)", s); ex = int(m.group(1)) if m else ex
            # Variant B inline
            if "extinguished=" in s:
                m = re.search(r"extinguished\s*=\s*(\d+)", s); ex = int(m.group(1)) if m else ex
            if "natural burnouts" in s or "natural=" in s:
                m = re.search(r"(?:natural|natural burnouts)\s*=?\s*(\d+)", s); nb = int(m.group(1)) if m else nb
        burning.append(b)
        natural.append(nb)
        extinguished.append(ex)
    return {
        "burning_cells": burning,
        "natural_burnouts": natural,
        "extinguished_cum": extinguished
    }

# ========= Indexed reader =========

@dataclass
class IndexEntry:
    offset: int
    length: int

def load_index_jsonl(path: str) -> List[IndexEntry]:
    entries: List[IndexEntry] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            off = obj.get("offset") or obj.get("start") or 0
            ln = obj.get("length") or obj.get("len")
            if ln is None and "end" in obj:
                ln = obj["end"] - off
            if isinstance(off, int) and isinstance(ln, int):
                entries.append(IndexEntry(off, ln))
    return entries

class FrameSource:
    """
    Unified access to frames:
      - If index.jsonl is provided, uses byte offsets (no full-file split).
      - Else splits by "Step ..." headers.
    """
    def __init__(self, ans_path: str, index_jsonl: Optional[str] = None):
        self.ans_path = ans_path
        self._indexed = False
        self._frames: List[str] = []
        self._entries: List[IndexEntry] = []
        if index_jsonl and os.path.isfile(index_jsonl):
            self._entries = load_index_jsonl(index_jsonl)
            self._indexed = len(self._entries) > 0
        if not self._indexed:
            raw = self._read_text(ans_path)
            self._frames = split_frames_by_headers(raw)

    @staticmethod
    def _read_text(path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def __len__(self) -> int:
        return len(self._entries) if self._indexed else len(self._frames)

    def get(self, k: int) -> str:
        """
        1-based index.
        """
        if self._indexed:
            ent = self._entries[k - 1]
            with open(self.ans_path, "rb") as f:
                f.seek(ent.offset)
                data = f.read(ent.length)
            return data.decode("utf-8", errors="replace")
        else:
            return self._frames[k - 1]

# ========= Image rendering (ANSI -> PNG) =========

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except Exception:
    PIL_OK = False

DEFAULT_FONT = None  # try to pick a monospaced font if available

def _load_font(point_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    global DEFAULT_FONT
    if DEFAULT_FONT is not None:
        return DEFAULT_FONT
    # Try DejaVuSansMono if present; fallback to PIL default
    try:
        DEFAULT_FONT = ImageFont.truetype("DejaVuSansMono.ttf", point_size)
    except Exception:
        DEFAULT_FONT = ImageFont.load_default()
    return DEFAULT_FONT

def ansi_to_image(
    text: str,
    font_size: int = 14,
    bg_color: str = "#111111",
    pad: Tuple[int, int] = (8, 8),
) -> "Image.Image":
    """
    Render ANSI text into a raster image. Each line is parsed into spans with fg/bg/bold.
    """
    if not PIL_OK:
        raise RuntimeError("Pillow not installed. Install pillow to use image export.")

    font = _load_font(font_size)
    lines = text.splitlines() or [""]
    # Measure character cell (approx using 'M')
    cell_w, cell_h = font.getlength("M"), font_size + 2
    # Determine max visible line length (strip ANSI for width)
    from .ansi import SGR_RE as _SGR_RE  # reuse
    def visual_len(s: str) -> int:
        return len(_SGR_RE.sub("", s))
    max_cols = max(visual_len(ln) for ln in lines)
    width = int(pad[0]*2 + cell_w * max_cols)
    height = int(pad[1]*2 + cell_h * len(lines))
    img = Image.new("RGB", (width, height), bg_color)
    drw = ImageDraw.Draw(img)

    y = pad[1]
    for line in lines:
        x = pad[0]
        spans = parse_ansi_to_spans(line)
        for sp in spans:
            txt = sp.text
            if not txt:
                continue
            # background rectangle (optional)
            if sp.style.bg:
                w = int(font.getlength(txt))
                drw.rectangle([x, y, x + w, y + cell_h], fill=sp.style.bg)
            # draw text
            fill = sp.style.fg or "#dddddd"
            # emulate bold by drawing twice with 1px offset if font lacks bold
            if sp.style.bold:
                drw.text((x+1, y), txt, fill=fill, font=font)
            drw.text((x, y), txt, fill=fill, font=font)
            x += int(font.getlength(txt))
        y += cell_h
    return img
