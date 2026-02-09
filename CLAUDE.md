# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**riskformgen** is a static-page form generator for risk analysis. It renders
Python dataclass-based form definitions into static HTML pages using Jinja2
templates, TailwindCSS, and Alpine.js for interactivity. Users interact with
tabbed, multi-section forms that support conditional logic, and can download
their responses as JSON. There is a risk model that converts the users answers
to risk levels across a given set of risks, and modifies these with controls
and mitigations.

Status: early development (questions and risk evaluation working).

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

3. **Alpine.js (runtime)** — A parent `<div>` holds the `x-data` scope shared by both the questions form and the risks panel. It contains reactive `answers` state, Alpine.js getters for each risk (compiled from Python rules at build time), and tab navigation. Each question partial binds inputs via `x-model`. Risk getters re-evaluate automatically as answers change. Multi-select answers are initialised as `[]` (array); all others as `''` (empty string).

### Key files

| File | Purpose |
|---|---|
| `models.py` | Question dataclasses, `Question` union, risk rule dataclasses (`AnyYesRule`, `CountYesRule`, `ChoiceMapRule`, `ContainsAnyRule`), `RiskRule` union, and `Risk` dataclass |
| `render.py` | Jinja2 environment setup, `prepare_risks()`, and `render_form()` |
| `templates/page.html.j2` | Page skeleton with Alpine.js state, tab navigation, risk getters, and debug panel |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/*.html.j2` | Per-type partials (one file per question type) |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge |
| `input.css` | Tailwind v4 entry point |
| `main.py` | Build orchestrator |

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
3. **`templates/page.html.j2`** — If the new type needs a non-string default (like `[]` for arrays), add a condition to the `x-data` initialiser alongside the existing `multiple_select` check.
4. **`main.py`** — Import the new class and add an example to `define_questions()`.

No changes needed to `question.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Adding a new risk

1. **`models.py`** — Create a `Risk` with an `id`, `name`, `description`, and a tuple of rules. Available rule types:
   - `AnyYesRule(question_ids, level)` — fires if any listed yes/no question is "yes"
   - `CountYesRule(question_ids, threshold, level)` — fires if ≥ threshold yes answers
   - `ChoiceMapRule(question_id, mapping)` — maps a multiple-choice answer to a level via dict
   - `ContainsAnyRule(question_id, values, level)` — fires if a multi-select answer contains any of the values
2. **`main.py`** — Add the `Risk` to the list returned by `define_risks()`.

No template changes needed. Each rule's `to_js()` method compiles to a JS expression that returns a risk level string or `null`. The page template loops over risks and generates Alpine.js getters that evaluate all rules and return the worst-case (highest severity) result.

### Adding a new rule type

1. **`models.py`** — Add a frozen dataclass with a `to_js()` method returning a JS expression (evaluates to a level string or `null`). Use `json.dumps` for JS literals. Add the class to the `RiskRule` union.

No other changes needed — `prepare_risks()` and the template getter loop work generically.

### Gotcha: Jinja2 autoescape and Alpine.js

The Jinja2 environment uses `autoescape=True`. When rendering JS expressions inside `x-data="..."` attributes, **do NOT use `|safe`**. Autoescape produces HTML entities (`&#34;` for `"`, `&gt;` for `>`, `&#39;` for `'`) which the browser decodes back to the original characters when reading the attribute value — before Alpine evaluates the JS. Using `|safe` puts raw `"` into a `"`-delimited attribute, breaking HTML parsing.

### Output

All generated files go to `output/` (gitignored): `index.html`, `styles.css`, `alpine3.15.8.min.js`.
