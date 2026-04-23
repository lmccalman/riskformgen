# riskformgen

A static-page generator for interactive risk assessment forms. Define your
questions, risks, and controls in YAML, then build a self-contained HTML page
that runs entirely in the browser — no server required.

Built with Jinja2 templates, [Bulma](https://bulma.io/), and
[Alpine.js](https://alpinejs.dev/) for client-side interactivity.

## Quick start

```bash
# Install dependencies (requires uv and Python 3.13+)
uv sync

# Build the static site into output/
uv run main.py

# Serve locally and open http://localhost:8000
python -m http.server -d output
```

The generated page lives in `output/index.html` with its CSS and JS assets.
Users interact with tabbed, multi-section forms, see their risk levels update
in real time, and can save/load their responses as JSON.

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check .           # Check for lint errors
uv run ruff check --fix .     # Auto-fix lint errors
uv run ruff format --check .  # Check formatting
uv run ruff format .          # Auto-format

# Type check
uv run basedpyright

# Build
uv run main.py
```

Run all four checks before considering a change complete:

```bash
uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run pytest tests/ -v
```

