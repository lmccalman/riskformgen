# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**formgen** is a static-page form generator. It renders Python dataclass-based form definitions into static HTML pages using Jinja2 templates, TailwindCSS, and Alpine.js for interactivity. Users interact with tabbed, multi-section forms that support conditional logic, and can download their responses as JSON.

Status: early development (hello-world skeleton working).

## Tech Stack

- Python 3.13, managed with uv
- Jinja2 for HTML templating
- TailwindCSS v4 for styling (compiled via `tailwindcss` CLI)
- Alpine.js for client-side interactivity (vendored as `alpine3.15.8.min.js`)

## Commands

```bash
# Build the static site into output/
uv run main.py

# Serve locally at http://localhost:8000
python -m http.server -d output

# Add a dependency
uv add <package>
```

## Architecture

The build pipeline has three phases:

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Dataclasses in `models.py` define form structure declaratively. `render.py` converts them to dicts and renders `templates/page.html.j2` (which includes `templates/question.html.j2` per question) into static HTML.

2. **TailwindCSS (build time)** — `input.css` is the v4 entry point (`@import "tailwindcss"`). The `tailwindcss` CLI scans all non-gitignored text files for class names and compiles only the used utilities into `output/styles.css`. No `tailwind.config.js` needed.

3. **Alpine.js (runtime)** — The `<form>` element's `x-data` holds reactive state for all question answers. Each question partial binds radio inputs via `x-model`. A debug `<pre>` panel shows the live JSON state.

### Key files

| File | Purpose |
|---|---|
| `models.py` | Form question dataclasses (e.g. `YesNoQuestion`) |
| `render.py` | Jinja2 environment setup and `render_form()` |
| `templates/page.html.j2` | Page skeleton with Alpine.js state and debug panel |
| `templates/question.html.j2` | Question partial (fieldset with radio inputs) |
| `input.css` | Tailwind v4 entry point |
| `main.py` | Build orchestrator |

### Output

All generated files go to `output/` (gitignored): `index.html`, `styles.css`, `alpine3.15.8.min.js`.
