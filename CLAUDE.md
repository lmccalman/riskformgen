# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**riskformgen** is a static-page form generator for risk analysis. It renders
Python dataclass-based form definitions into static HTML pages using Jinja2
templates, Pico CSS (jade theme), and Alpine.js for interactivity. Users interact with
tabbed, multi-section forms that support conditional logic, and can download
their responses as JSON. There is a risk model that converts the users answers
to risk levels across a given set of risks, and modifies these with controls
and mitigations.

Status: early development (questions and risk evaluation working).

## Tech Stack

- Python 3.13, managed with uv
- Jinja2 for HTML templating
- Pico CSS v2 (jade theme) for classless/semantic styling (vendored as `pico.jade.min.css`)
- Alpine.js for client-side interactivity (vendored as `alpine3.15.8.min.js`)

## Commands

```bash
# Build the static site into output/
uv run main.py

# Run tests
uv run pytest tests/ -v

# Serve locally at http://localhost:8000
python -m http.server -d output

# Add a dependency
uv add <package>
```

**Always run `uv run pytest tests/ -v` after implementing a new feature or fixing a bug to verify correctness.** Tests should pass before considering work complete.

## Architecture

The build pipeline has three phases:

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Dataclasses in `models.py` define form structure declaratively. `render.py` converts them to dicts and renders `templates/page.html.j2` (which includes `templates/question.html.j2` per question) into static HTML.

2. **CSS (build time)** — `pico.jade.min.css` provides classless/semantic base styling. `input.css` contains custom CSS for app-specific components (tabs, badges, risk grid, spacing stacks, etc.). Both are copied directly to `output/` — no compilation step needed.

3. **Alpine.js (runtime)** — A parent `<div>` holds the `x-data` scope shared by all section forms and the risks panel. It contains reactive `answers` state, Alpine.js getters for each risk (compiled from Python rules at build time), and tab navigation. Each section renders as its own `<form>` shown/hidden via `x-show`; sub-sections provide visual grouping within sections. Each question partial binds inputs via `x-model`. Risk getters re-evaluate automatically as answers change. Multi-select answers are initialised as `[]` (array); all others as `''` (empty string).

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths (including `pico_src`), risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), and `RISK_MATRIX` lookup table |
| `models.py` | Question dataclasses, `Question` union, `SubSection`/`Section` dataclasses, `all_questions()` helper, risk rule dataclasses (`AnyYesRule`, `CountYesRule`, `ChoiceMapRule`, `ContainsAnyRule`), `RiskRule` union, and `Risk` dataclass |
| `render.py` | Jinja2 environment setup, `prepare_sections()`, `prepare_risks()`, and `render_form()` |
| `templates/page.html.j2` | Page skeleton with Alpine.js state, dynamic section tabs, risk getters, and debug panel |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/*.html.j2` | Per-type partials (one file per question type) |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge |
| `input.css` | Custom CSS for app-specific components (tabs, badges, risk grid, spacing, etc.) |
| `main.py` | Build orchestrator |

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
3. **`templates/page.html.j2`** — If the new type needs a non-string default (like `[]` for arrays), add a condition to the `x-data` initialiser alongside the existing `multiple_select` check.
4. **`main.py`** — Import the new class and add an example to the appropriate `SubSection` in `define_sections()`.

No changes needed to `question.html.j2`, `subsection.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Form structure: Sections and sub-sections

Forms are organised into **Sections** (rendered as tabs) and **SubSections** (visual groupings within a section). In `main.py`, `define_sections()` returns a `list[Section]`, where each `Section` contains a tuple of `SubSection`s, each containing a tuple of `Question`s.

- To add a new section, create a `Section(id="slug", title="Display Name", subsections=(...))` in `define_sections()`.
- To add a sub-section, add a `SubSection(title="Heading", questions=(...))` to an existing section's `subsections` tuple.
- Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs.
- The Risk Analysis tab is always present (right-aligned, red accent) and is not defined in the sections list.

### Risk model: Likelihood × Consequence

Risk is decomposed into two independent dimensions — **likelihood** and **consequence** — with the overall risk level computed via a configurable **risk matrix** (ISO 31000 style). The scales and matrix are defined in `config.py`. Each rule can set one or both dimensions; a rule with only `likelihood` set won't affect the consequence reduction, and vice versa. The `_worst` helper on the JS side uses `scale.indexOf()` for ordering — the position in the configured tuple defines severity.

Risk getters return `{likelihood, consequence, level}` objects. The `level` is looked up from the matrix using the worst-case likelihood and consequence across all fired rules.

### Adding a new risk

1. **`models.py`** — Create a `Risk` with an `id`, `name`, `description`, and a tuple of rules. Available rule types:
   - `AnyYesRule(question_ids, likelihood=, consequence=)` — fires if any listed yes/no question is "yes" (at least one dimension required)
   - `CountYesRule(question_ids, threshold, likelihood=, consequence=)` — fires if ≥ threshold yes answers
   - `ChoiceMapRule(question_id, mapping)` — maps a multiple-choice answer to `{"likelihood": ..., "consequence": ...}` via dict (either key optional per entry)
   - `ContainsAnyRule(question_id, values, likelihood=, consequence=)` — fires if a multi-select answer contains any of the values
2. **`main.py`** — Add the `Risk` to the list returned by `define_risks()`. Set `default_likelihood` and `default_consequence` for the fallback when no rules fire.

No template changes needed. Each rule's `to_js()` method compiles to a JS expression that returns a `{likelihood, consequence}` object or `null`. The page template loops over risks and generates Alpine.js getters that reduce results per dimension (worst-case-wins) and look up the overall level from the risk matrix.

### Adding a new rule type

1. **`models.py`** — Add a frozen dataclass with a `to_js()` method returning a JS expression (evaluates to a `{likelihood, consequence}` object or `null`). Use `_js_result()` helper and `json.dumps` for JS literals. Add the class to the `RiskRule` union.

No other changes needed — `prepare_risks()` and the template getter loop work generically.

### Semantic HTML and Pico CSS

Templates use semantic HTML elements that Pico styles automatically:
- `<article>` for risk cards (Pico renders as bordered card with padding/shadow)
- `<section>` for sub-section groupings
- `<nav>` for tab navigation
- `<details>` for the collapsible debug panel (`data-theme="dark"` for per-element theming)
- `<fieldset>` / `<legend>` for questions (Pico styles natively)
- `<label><input/> Text</label>` pattern for radio/checkbox (Pico expects input-first)

Custom classes in `input.css` handle app-specific components: `.tabs`, `.badge-{color}`, `.risk-grid`, `.control-row`, `.stack-{lg,md,sm}`, `.options-{row,col}`, `.assessed-row`, `.linked-answer`.

### Gotcha: Jinja2 autoescape and Alpine.js

The Jinja2 environment uses `autoescape=True`. When rendering JS expressions inside `x-data="..."` attributes, **do NOT use `|safe`**. Autoescape produces HTML entities (`&#34;` for `"`, `&gt;` for `>`, `&#39;` for `'`) which the browser decodes back to the original characters when reading the attribute value — before Alpine evaluates the JS. Using `|safe` puts raw `"` into a `"`-delimited attribute, breaking HTML parsing.

### Output

All generated files go to `output/` (gitignored): `index.html`, `pico.jade.min.css`, `input.css`, `alpine3.15.8.min.js`.
