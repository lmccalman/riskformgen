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

3. **Alpine.js (runtime)** — The `<form>` element's `x-data` holds reactive state for all question answers. Each question partial binds inputs via `x-model`. A debug `<pre>` panel shows the live JSON state. Multi-select answers are initialised as `[]` (array); all others as `''` (empty string).

### Key files

| File | Purpose |
|---|---|
| `models.py` | Question dataclasses (`YesNoQuestion`, `FreeTextQuestion`, `MultipleChoiceQuestion`, `MultipleSelectQuestion`) and `Question` union type |
| `render.py` | Jinja2 environment setup and `render_form()` |
| `templates/page.html.j2` | Page skeleton with Alpine.js state and debug panel |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/*.html.j2` | Per-type partials (one file per question type) |
| `input.css` | Tailwind v4 entry point |
| `main.py` | Build orchestrator |

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
3. **`templates/page.html.j2`** — If the new type needs a non-string default (like `[]` for arrays), add a condition to the `x-data` initialiser alongside the existing `multiple_select` check.
4. **`main.py`** — Import the new class and add an example to `define_questions()`.

No changes needed to `question.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Output

All generated files go to `output/` (gitignored): `index.html`, `styles.css`, `alpine3.15.8.min.js`.
