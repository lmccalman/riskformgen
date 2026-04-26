# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. For project overview and usage instructions, see `README.md`.

## Commands

```bash
# Build the static site into output/
uv run main.py

# Run tests
uv run pytest tests/ -v

# Run only fast tests (skip browser-based E2E)
uv run pytest tests/ -v -m "not e2e"

# Run only E2E tests (needs: uv run playwright install chromium)
uv run pytest tests/ -v -m e2e

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

### Build pipeline

The build pipeline has three phases:

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Form structure is defined in YAML files under `form/`, parsed by `parse.py` into frozen dataclasses from `models.py`. `render.py` converts them to dicts and renders `templates/page.html.j2` into static HTML.

2. **CSS (build time)** — `bulma.min.css` provides class-based styling (layout, typography, form controls, cards, tabs). `input.css` contains custom CSS for app-specific components (badges, risk grid, spacing stacks, etc.). Both are copied directly to `output/` — no compilation step needed.

3. **Alpine.js (runtime)** — The Alpine component is rendered from `templates/app.js.j2` into `output/app.js` (alongside `index.html`), which registers a factory via `Alpine.data('app', () => ({...}))` on the `alpine:init` event. The HTML carries only `<div x-data="app">`. The factory holds reactive `answers` / `details` / assessment state, computed property getters (`prop_*`), control getters (`ctrl_*`), and per-risk inherent and `<id>_residual` getters — all compiled from Python at build time. Each section renders as its own `<form>` shown/hidden via `x-show`. Question visibility is driven by the property DAG (questions are shown when their target properties are reachable). Risk getters re-evaluate automatically as answers change. Persisted state uses `Alpine.$persist(initial).as('_x_<field>')` so localStorage keys are stable across the component definition form. The factory's `init()` hook back-fills any newly-added question/detail/risk/control IDs whose persisted state predates them.

### Core domain model

The system is built around a **property DAG** that decouples questions from risk logic:

- **Properties** (`form/properties.yaml`) — Boolean nodes forming a DAG. Each has an `id`, `description`, optional `parents`, and an `activation` mode (`"all"` or `"any"`). A property is `true` when its question is answered "yes" **and** its parent conditions are met. Properties with no parents are root nodes.

- **Questions** (`form/sections.yaml`) — Two types are supported. **Binary** questions (yes/no) set one or more properties via their `properties` field. **Detail** questions (`type: detail`) reference a `Detail` by `detail_id` and store free-text input in `details[detail_id]` — they don't set property state, but their visibility tracks the referenced detail's properties (copied at parse time). Question visibility is derived automatically from the property DAG — a question is shown when at least one of its target properties is reachable (i.e. the property's parents satisfy the activation mode).

- **Details** (`form/details.yaml`) — Contextual topics keyed by id, each linked to one or more properties. A `DetailQuestion` writes the user's free-text input to `details[detail_id]`; the value is then surfaced in any risk card whose conditions touch one of the detail's properties (under the "Context" section), so contextual notes follow the property graph rather than being hard-wired to a specific risk.

- **Risks** (`form/risks.yaml`) — Each risk has `conditions` (a list of `ConditionMapping`). Each condition checks a set of properties (via `mode: "any"` or `"all"`) and contributes a `{likelihood, consequence}` pair when the check passes. When multiple conditions fire, **worst-case-wins** per dimension independently. When no conditions fire, the risk level is `"not_applicable"`. Conditions are compiled to JS expressions at build time via `to_js()`.

- **Controls** (`form/controls.yaml`) — Safeguards linked to a single property. A control is "present" when its property is `true`. Each control has `effects` listing which risks it addresses (via `risk_id`). Controls do **not** automatically reduce risk — the assessor judges their collective effectiveness per risk at assessment time (see "Residual risk" below). For risks where a control is *not* currently present, the risk card surfaces a "Mandate Controls" checkbox and free-text comment so the assessor can record that the control should be implemented and how.

- **Residual risk** (assessor input at runtime) — For every risk where inherent level is not `not_applicable`, the assessor picks a **control effectiveness**: `ineffective` (default — residual equals inherent), `partial` (assessor picks residual likelihood and consequence independently; level is computed from the matrix), or `controlled` (residual level is the dedicated `controlled` level). A single "Residual Risk Justification" textarea captures the reasoning. State lives in `control_effectiveness`, `residual_likelihood`, `residual_consequence`, `justifications`, `mandated_controls`, and `mandated_comments` on the Alpine scope and is included in the assessment export.

The data flow is: **Questions → Properties → Risks / Controls / Details**.

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths, risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), `RISK_LEVEL_COLOURS`, and `RISK_MATRIX` lookup table |
| `models.py` | Frozen dataclasses: `BinaryQuestion`, `DetailQuestion`, `Property`, `ConditionMapping`, `Risk`, `Control`, `ControlEffect`, `Detail`, `Section`, `SubSection` |
| `parse.py` | YAML → dataclass parsing (one `load_*` function per YAML file), id/combinator validation, and `validate_all()` orchestrator |
| `render.py` | Jinja2 environment, view dataclasses (`SectionView`, `RiskView`, `DetailView`, …), `_compile_property_getter`, `_compile_question_visibility`, `_build_template_context`, `render_form()`, and `render_app_js()` |
| `main.py` | Build orchestrator — loads YAML, validates, renders HTML + `app.js`, copies assets |
| `form/*.yaml` | Form definitions: `sections.yaml`, `properties.yaml`, `risks.yaml`, `controls.yaml`, `details.yaml` |
| `templates/page.html.j2` | Page skeleton with tab navigation (sections + Risk Analysis + Debug), Alpine bindings (`x-data="app"`, `x-show`, `x-model`); no component body |
| `templates/app.js.j2` | Alpine factory: `Alpine.data('app', () => ({...}))` with state, save/load helpers, `init()` migration pass, and compiled property/control/risk getters |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/binary.html.j2` | Binary (yes/no) question partial |
| `templates/questions/detail.html.j2` | Free-text question partial (binds to `details[detail_id]`) |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge, controls, mandated-control checkboxes, context, and residual-risk inputs |
| `templates/save_load.html.j2` | Reusable save/load button bar partial |
| `input.css` | Custom CSS: tabs, badges, risk grid, spacing stacks, etc. |

### Adding a new question type

The existing `binary` and `detail` question types illustrate the pattern; use them as references.

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, `properties: tuple[str, ...]`, any type-specific fields, and a `type: Literal["my_type"] = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`parse.py`** — Add a `case` branch in `parse_question()` (with an `_check_unknown_keys` guard listing the allowed YAML keys) to construct the new dataclass.
3. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Bind to whatever Alpine state the type writes (`answers.<id>` for binary-style, `details[<detail_id>]` for the detail type, etc.).
4. **`render.py`** — If the new type carries fields the templates need beyond `id`/`text`/`type`/`guidance`, add them to `QuestionView` and `_build_question_view`. Also extend `_build_template_context` if the type contributes to property state (see how `BinaryQuestion` is filtered into `question_for_prop`).
5. **`templates/app.js.j2`** — If the new type needs a non-string default or a separate state map (like `details`), seed it in the factory and back-fill it in `init()`.

No changes needed to `question.html.j2` or `subsection.html.j2` — the dispatcher works generically off the question's `type` field.

### Adding a new risk or control

To add a new **risk**, add an entry to `form/risks.yaml` with `id`, `description`, and `conditions` (each referencing properties by ID).

To add a new **control**, add an entry to `form/controls.yaml` with `id`, `description`, `property` (the property ID that activates it), and `effects` (the list of risks this control addresses, each as `{risk_id: ...}`).

New risks and controls automatically appear in the Risk Analysis tab — no code changes needed.

### Adding a new property

Add an entry to `form/properties.yaml` with `id`, `description`, and optionally `parents` (list of property IDs) and `activation` (`"all"` or `"any"`, default `"all"`). Then create a question in `form/sections.yaml` whose `properties` field includes the new property ID.

### Adding a new detail

Add an entry to `form/details.yaml` with `id`, `description`, and `properties` (list of property IDs that gate when the detail is shown in risk cards). Then add a `type: detail` question to `form/sections.yaml` referencing it via `detail_id`.

### Form structure

Forms are organised into **Sections** (rendered as tabs) and **SubSections** (visual groupings within a section), defined in `form/sections.yaml`. Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs. The Risk Analysis tab (right-aligned) and Debug tab are always present and not defined in the sections list.

### Bulma CSS conventions

Templates use Bulma's class-based styling:
- `.card` / `.card-header` / `.card-content` for risk cards
- `.box` for sub-section groupings
- `.tabs.is-boxed` for tab navigation (active state via `.is-active` on `<li>`)
- `.field` / `.label` / `.control` for form question layout
- `.radio` / `.checkbox` on labels for radio/checkbox inputs
- `.button.is-primary` / `.button.is-light` for action buttons
- `.title` / `.subtitle` / `.has-text-grey` for typography

Custom classes in `input.css` handle app-specific components: `.badge-{color}`, `.risk-grid`, `.control-row`, `.stack-{lg,md,sm}`, `.options-{row,col}`, `.assessed-row`, `.linked-answer`, `.debug-panel`.

### Gotcha: Jinja2 autoescape and JS templates

`create_environment()` in `render.py` enables autoescape for `.html` / `.html.j2` / `.htm` / `.xml` templates and disables it everywhere else (including `.js.j2`). This lets `app.js.j2` emit compiled JS directly without HTML entities creeping in. If you ever inline JS expressions back into an HTML attribute (anywhere outside `app.js.j2`), you still cannot use `|tojson` / `|safe` there — pre-serialise with `json.dumps()` in Python and pass as plain string context variables, same pattern as `likelihoods_js` in `render.py`.

### Gotcha: pyright and untyped libraries

YAML parsing boundaries lack type stubs. Files that interact heavily with these use per-file pyright comment overrides:
- `parse.py`: `# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false`
- `tests/js_harness.py`: `# pyright: reportReturnType=false, reportCallIssue=false, reportArgumentType=false` (mini-racer's `ctx.eval` returns a very broad union)

### Testing

Three test layers coexist:

- **Compiler-shape tests** — `tests/test_render.py` and `tests/test_models.py` assert on the substrings emitted by `_compile_property_getter`, `ConditionMapping.to_js`, and friends. They pin the generated code's *form*.
- **Behaviour tests** — `tests/test_js_behaviour.py` uses `tests/js_harness.py` to evaluate the real `render_app_js()` output inside an embedded V8 context (`mini-racer`). Stubs for `Alpine.data` / `Alpine.$persist` / `document.addEventListener` capture the factory so `prop_*`, `ctrl_*`, risk and residual getters can be driven against in-memory `answers` / `details` / `control_effectiveness` fixtures. They pin the generated code's *semantics*.
- **End-to-end tests** — `tests/e2e/` uses Playwright to drive real Chromium against a built copy of the site served over `http.server`. Covers save/load (Blob downloads, FileReader imports, confirm/alert dialogs) which mini-racer can't stub. Marked `@pytest.mark.e2e`; run `uv run playwright install chromium` once after installing dev deps. Skip during tight dev loops with `-m "not e2e"`.

The layers are complementary: a refactor that preserves semantics but changes the emitted format breaks the first layer only; a refactor that preserves the format but flips a branch breaks the second only; a refactor to the save/load HTML wiring or browser-API usage breaks the third only. Write new tests in whichever layer matches what you're protecting against.

### Output

All generated files go to `output/` (gitignored): `index.html`, `app.js`, `bulma.min.css`, `input.css`, `alpine3.15.8.min.js`, `alpine-persist.min.js`.

### Spec editor (removed)

There is an `editor/` directory and a `run_editor.py` shim left over from a previous spec-editor experiment, but the editor's source files (FastAPI backend and React frontend) have been removed. `run_editor.py` will not run as-is. Treat the directory as dormant; YAML is currently hand-edited.
