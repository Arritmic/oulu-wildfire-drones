# Changelog
All notable changes to this project are documented here.  
This project follows [Semantic Versioning](https://semver.org/) and the format of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Added
- Simulation core (cellular automata fire model, drone agents, heuristic/auction/RL strategies) and experiment runner.  
- Paper reproduction metrics and experiment presets (scalability, wind, complexity).  
- Documentation for experiments and research usage.

### Changed
- TBD

### Fixed
- TBD

---

## [0.1.0] - 2025-08-24
### Added
- **Web replay viewer** (`src/webviz/`): FastAPI backend with a lightweight HTML/JS UI for playing ANSI logs.
  - Endpoints: `/api/load`, `/api/frame/{k}`, `/api/export/gif`, `/api/export/pngzip`.
  - Loads `.ansi` (or `.ans`) logs; optional `*.index.jsonl` and agent status text.
  - Playback controls: play/pause, frame slider, FPS control, keyboard navigation.
  - Metrics panel: per-step table (burning, natural burnouts, extinguished) and simple line charts.
  - Export:
    - Animated GIF (color-preserving).
    - PNG frames as a ZIP archive.
- **ANSI rendering utilities**:
  - ANSI → HTML for in-browser viewing.
  - ANSI → image (Pillow) for export.
- **Project scaffolding**:
  - `src/` layout with package imports.
  - Static assets (`src/webviz/static/`).
  - Launch script `scripts/server_webviz.py`.
  - Editable install via `pyproject.toml`.
- **Basic README** with setup and viewer usage instructions.

### Known limitations
- ANSI parsing is scoped to the subset used by this project’s logs.
- Large exports can be memory-intensive; video export and streaming are planned.
