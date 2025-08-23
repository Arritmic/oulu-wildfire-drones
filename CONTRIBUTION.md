# Contribution Guide

Thank you for improving **oulu-wildfire-drones**. This guide explains how to set up the environment, propose changes, and keep results reproducible.

## Scope for contributions
- Task allocation strategies (heuristics, auction variants, RL baselines).
- Fire/spread modeling and wind field variants.
- Metrics, evaluation scripts, and experiment presets.
- Viewer and replay tooling.
- Tests, documentation, and small demo datasets.

## Environment
```bash
git clone https://github.com/Arritmic/oulu-wildfire-drones.git
cd oulu-wildfire-drones
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
pre-commit install
