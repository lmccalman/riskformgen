# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. For project overview, YAML schema reference, risk model, and usage instructions, see `README.md`.

## Commands

```bash
# Build the static site into output/
uv run main.py

# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check .
uv run ruff format --check .

# Type check
uv run basedpyright

# Serve locally at http://localhost:8000
python -m http.server -d output

# Add a dependency
uv add <package>
```

**After any code change, run all four checks before considering work complete:**

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest tests/ -v
```

Use `uv run ruff check --fix .` and `uv run ruff format .` to auto-fix lint and formatting issues.

## Architecture

The build pipeline has three phases:

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Form structure is defined in YAML files under `form/` (see `README.md`), parsed by `parse.py` into frozen dataclasses from `models.py`. `render.py` converts them to dicts and renders `templates/page.html.j2` into static HTML.

2. **CSS (build time)** — `bulma.min.css` provides class-based styling (layout, typography, form controls, cards, tabs). `input.css` contains custom CSS for app-specific components (badges, risk grid, spacing stacks, etc.). Both are copied directly to `output/` — no compilation step needed.

3. **Alpine.js (runtime)** — A parent `<div>` holds the `x-data` scope shared by all section forms and the risks panel. It contains reactive `answers` state, Alpine.js getters for each risk (compiled from Python rules at build time), and tab navigation. Each section renders as its own `<form>` shown/hidden via `x-show`; sub-sections provide visual grouping within sections. Each question partial binds inputs via `x-model`. Risk getters re-evaluate automatically as answers change. Multi-select answers are initialised as `[]` (array); all others as `''` (empty string).

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths, risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), and `RISK_MATRIX` lookup table |
| `models.py` | Frozen dataclasses for questions, sections, risk rules, risks, controls, and visibility conditions |
| `parse.py` | YAML → dataclass parsing (one `load_*` function per YAML file) |
| `render.py` | Jinja2 environment setup, `prepare_sections()`, `prepare_risks()`, `prepare_controls()`, and `render_form()` |
| `main.py` | Build orchestrator — loads YAML, renders HTML, copies assets |
| `form/*.yaml` | Form definitions (see `README.md` for schema) |
| `templates/page.html.j2` | Page skeleton with Alpine.js state, dynamic section tabs, risk getters, and debug panel |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/*.html.j2` | Per-type partials (one file per question type) |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge |
| `input.css` | Custom CSS for app-specific components (tabs, badges, risk grid, spacing, etc.) |

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`parse.py`** — Add a `case` branch in `parse_question()` to construct the new dataclass from YAML dicts.
3. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
4. **`templates/page.html.j2`** — If the new type needs a non-string default (like `[]` for arrays), add a condition to the `x-data` initialiser alongside the existing `multiple_select` check.

No changes needed to `question.html.j2`, `subsection.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Adding a new risk or rule type

To add a new **risk**, add an entry to `form/risks.yaml` — see `README.md` for the schema and available rule types.

To add a new **rule type**:

1. **`models.py`** — Add a frozen dataclass with a `to_js()` method returning a JS expression (evaluates to a `{likelihood, consequence}` object or `null`). Use `_js_result()` helper and `json.dumps` for JS literals. Add the class to the `RiskRule` union.
2. **`parse.py`** — Add a `case` branch in `parse_rule()` to construct the new dataclass from YAML dicts.

No other changes needed — `prepare_risks()` and the template getter loop work generically.

### Form structure

Forms are organised into **Sections** (rendered as tabs) and **SubSections** (visual groupings within a section), defined in `form/sections.yaml`. Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs. The Risk Analysis tab is always present (right-aligned, red accent) and is not defined in the sections list.

### Bulma CSS conventions

Templates use Bulma's class-based styling:
- `.card` / `.card-header` / `.card-content` for risk cards
- `.box` for sub-section groupings
- `.tabs.is-boxed` for tab navigation (active state via `.is-active` on `<li>`)
- `.field` / `.label` / `.control` for form question layout
- `.radio` / `.checkbox` on labels for radio/checkbox inputs
- `.textarea` on `<textarea>` elements
- `.select` wrapper around `<select>` elements
- `.button.is-primary` / `.button.is-light` for action buttons
- `.title` / `.subtitle` / `.has-text-grey` for typography

Custom classes in `input.css` handle app-specific components: `.badge-{color}`, `.risk-grid`, `.control-row`, `.stack-{lg,md,sm}`, `.options-{row,col}`, `.assessed-row`, `.linked-answer`, `.debug-panel`.

### Gotcha: Jinja2 autoescape and Alpine.js

The Jinja2 environment uses `autoescape=True`. When rendering JS expressions inside `x-data="..."` attributes, **do NOT use `|safe`**. Autoescape produces HTML entities (`&#34;` for `"`, `&gt;` for `>`, `&#39;` for `'`) which the browser decodes back to the original characters when reading the attribute value — before Alpine evaluates the JS. Using `|safe` puts raw `"` into a `"`-delimited attribute, breaking HTML parsing.

### Output

All generated files go to `output/` (gitignored): `index.html`, `bulma.min.css`, `input.css`, `alpine3.15.8.min.js`.
