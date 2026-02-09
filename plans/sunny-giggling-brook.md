# Plan: Hello World Skeleton for FormGen

## Context

FormGen is in its scaffold phase — `main.py` just prints a greeting, there are no
dependencies, templates, or dataclasses. This plan delivers a minimal end-to-end example
that proves out the core pipeline: **Python dataclass → Jinja2 template → static HTML**
with TailwindCSS styling and Alpine.js interactivity.

The output is a working form page with two yes/no radio-button questions and a live JSON
debug panel showing the current answers.

---

## Key discovery: Tailwind CSS v4

The system has **tailwindcss v4.1.18** (not v3). This changes the setup:
- `input.css` uses `@import "tailwindcss"` (not the old `@tailwind` directives)
- No `tailwind.config.js` needed
- v4 auto-scans all non-gitignored text files from `cwd` for class names, so `.j2`
  templates are picked up automatically

---

## Files to create/modify

### 1. `.gitignore` — append `output/`

Add `output/` so generated artefacts aren't tracked (and Tailwind skips scanning them).

### 2. `models.py` (new) — YesNoQuestion dataclass

```python
@dataclass(frozen=True)
class YesNoQuestion:
    id: str    # HTML name attribute + Alpine.js state key
    text: str  # The question label
```

Two example instances defined in `main.py`:
- `YesNoQuestion(id="likes_swimming", text="Do you enjoy swimming?")`
- `YesNoQuestion(id="enjoys_coding", text="Do you enjoy coding?")`

### 3. `render.py` (new) — Jinja2 rendering

- `create_environment()` — sets up Jinja2 with `FileSystemLoader("templates/")` and
  `autoescape=True`
- `render_form(questions)` — converts dataclasses to dicts via `asdict()`, renders
  `page.html.j2`, returns HTML string

### 4. `templates/page.html.j2` (new) — page skeleton

- HTML boilerplate referencing `styles.css` and `alpine3.15.8.min.js` (`defer`)
- `<form x-data="{ answers: { ... } }">` initialises Alpine.js state with each question
  id as a key (empty string default)
- Loops over questions with `{% include "question.html.j2" %}` for each
- Debug `<pre>` block showing `JSON.stringify(answers, null, 2)` via `x-text`

### 5. `templates/question.html.j2` (new) — question partial

- `<fieldset>` + `<legend>` for accessibility
- Two radio `<input>`s (Yes/No) with `x-model="answers.{{ question.id }}"` binding
- TailwindCSS utility classes for styling

### 6. `input.css` (new) — Tailwind v4 entry point

Single line: `@import "tailwindcss";`

### 7. `pyproject.toml` — add jinja2 dependency

Via `uv add jinja2`.

### 8. `main.py` — rewrite as orchestrator

Small, named functions for each build step:
1. `define_questions()` — returns the two example questions
2. `ensure_output_dir()` — `mkdir(exist_ok=True)`
3. `write_html(questions)` — calls `render_form()`, writes to `output/index.html`
4. `compile_css()` — runs `tailwindcss --input input.css --output output/styles.css
   --minify` via `subprocess.run(check=True, cwd=PROJECT_ROOT)`
5. `copy_alpine()` — `shutil.copy2` Alpine.js into `output/`
6. `main()` — calls steps 1–5, prints summary

---

## How Alpine.js state management works

The `<form>` element's `x-data` creates reactive state:
```js
{ answers: { likes_swimming: '', enjoys_coding: '' } }
```

Each question partial's radio inputs use `x-model="answers.<question_id>"` to two-way
bind. When a user clicks "Yes" on `likes_swimming`, Alpine sets
`answers.likes_swimming = "yes"` and the JSON debug panel updates reactively.

Jinja2 processes first (build-time), Alpine.js processes second (browser runtime) — the
`{{ }}` delimiters never conflict because they operate at different times.

---

## Verification

```bash
uv add jinja2
uv run main.py
# → "Built form with 2 questions in .../output/"

ls output/
# → index.html  styles.css  alpine3.15.8.min.js

xdg-open output/index.html
# → Styled page with two radio-button questions and live JSON panel
```

Manual check: click Yes/No on both questions, confirm the JSON panel updates correctly.
