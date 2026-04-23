# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. For project overview and usage instructions, see `README.md`.

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

# Type check editor frontend
cd editor/frontend && npx tsc --noEmit

# Serve locally at http://localhost:8000
python -m http.server -d output

# Add a dependency
uv add <package>

# Run the spec editor (two terminals)
cd /path/to/riskformgen && uv run python run_editor.py   # Backend on :8000
cd editor/frontend && npm run dev                          # Frontend on :5173
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

3. **Alpine.js (runtime)** — The Alpine component is rendered from `templates/app.js.j2` into `output/app.js` (alongside `index.html`), which registers a factory via `Alpine.data('app', () => ({...}))` on the `alpine:init` event. The HTML carries only `<div x-data="app">`. The factory holds reactive `answers` state, computed property getters (`prop_*`), control getters (`ctrl_*`), and risk getters — all compiled from Python at build time. Each section renders as its own `<form>` shown/hidden via `x-show`. Question visibility is driven by the property DAG (questions are shown when their target properties are reachable). Risk getters re-evaluate automatically as answers change. Persisted state uses `Alpine.$persist(initial).as('_x_<field>')` so localStorage keys are stable across the component definition form.

### Core domain model

The system is built around a **property DAG** that decouples questions from risk logic:

- **Properties** (`form/properties.yaml`) — Boolean nodes forming a DAG. Each has an `id`, `description`, optional `parents`, and an `activation` mode (`"all"` or `"any"`). A property is `true` when its question is answered "yes" **and** its parent conditions are met. Properties with no parents are root nodes.

- **Questions** (`form/sections.yaml`) — Currently all `binary` (yes/no). Each question sets one or more properties via its `properties` field. Question visibility is derived automatically from the property DAG — a question is shown when at least one of its target properties is reachable (i.e. the property's parents satisfy the activation mode).

- **Risks** (`form/risks.yaml`) — Each risk has `conditions` (a list of `ConditionMapping`). Each condition checks a set of properties (via `mode: "any"` or `"all"`) and contributes a `{likelihood, consequence}` pair when the check passes. When multiple conditions fire, **worst-case-wins** per dimension independently. When no conditions fire, the risk level is `"not_applicable"`. Conditions are compiled to JS expressions at build time via `to_js()`.

- **Controls** (`form/controls.yaml`) — Safeguards linked to a single property. A control is "present" when its property is `true`. Each control has `effects` listing which risks it addresses (via `risk_id`). Controls do **not** automatically reduce risk — the assessor judges their collective effectiveness per risk at assessment time (see "Residual risk" below).

- **Residual risk** (assessor input at runtime) — For every risk where inherent level is not `not_applicable`, the assessor picks a **control effectiveness**: `ineffective` (default — residual equals inherent), `partial` (assessor picks residual likelihood and consequence independently; level is computed from the matrix), or `controlled` (residual level is the dedicated `controlled` level). A single "Residual Risk Justification" textarea captures the reasoning. State lives in `control_effectiveness`, `residual_likelihood`, `residual_consequence`, and `justifications` on the Alpine scope and is included in the assessment export.

The data flow is: **Questions → Properties → Risks / Controls**.

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths, risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), and `RISK_MATRIX` lookup table |
| `models.py` | Frozen dataclasses: `BinaryQuestion`, `Property`, `ConditionMapping`, `Risk`, `Control`, `ControlEffect`, `Section`, `SubSection` |
| `parse.py` | YAML → dataclass parsing (one `load_*` function per YAML file) plus validation functions |
| `render.py` | Jinja2 environment, `prepare_properties()`, `prepare_sections()`, `prepare_risks()`, `prepare_controls()`, `render_form()`, and `render_app_js()` |
| `main.py` | Build orchestrator — loads YAML, validates, renders HTML + `app.js`, copies assets |
| `form/*.yaml` | Form definitions: `sections.yaml`, `properties.yaml`, `risks.yaml`, `controls.yaml` |
| `templates/page.html.j2` | Page skeleton with tab navigation and Alpine bindings (`x-data="app"`, `x-show`, `x-model`); no component body |
| `templates/app.js.j2` | Alpine factory: `Alpine.data('app', () => ({...}))` with state, methods, and compiled property/control/risk getters |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/binary.html.j2` | Binary (yes/no) question partial |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge |
| `templates/save_load.html.j2` | Reusable save/load button bar partial |
| `input.css` | Custom CSS: tabs, badges, risk grid, spacing stacks, etc. |

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, `properties: tuple[str, ...]`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`parse.py`** — Add a `case` branch in `parse_question()` to construct the new dataclass from YAML dicts.
3. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
4. **`templates/app.js.j2`** — If the new type needs a non-string default (like `[]` for arrays), adjust the `answers` seed loop in the factory.

No changes needed to `question.html.j2`, `subsection.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Adding a new risk or control

To add a new **risk**, add an entry to `form/risks.yaml` with `id`, `description`, and `conditions` (each referencing properties by ID).

To add a new **control**, add an entry to `form/controls.yaml` with `id`, `description`, `property` (the property ID that activates it), and `effects` (the list of risks this control addresses, each as `{risk_id: ...}`).

New risks and controls automatically appear in the Risk Analysis tab — no code changes needed.

### Adding a new property

Add an entry to `form/properties.yaml` with `id`, `description`, and optionally `parents` (list of property IDs) and `activation` (`"all"` or `"any"`, default `"all"`). Then create a question in `form/sections.yaml` whose `properties` field includes the new property ID.

### Form structure

Forms are organised into **Sections** (rendered as tabs) and **SubSections** (visual groupings within a section), defined in `form/sections.yaml`. Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs. The Risk Analysis tab (red accent, right-aligned) is always present and not defined in the sections list.

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

### Output

All generated files go to `output/` (gitignored): `index.html`, `app.js`, `bulma.min.css`, `input.css`, `alpine3.15.8.min.js`, `alpine-persist.min.js`.

### Spec Editor

The spec editor (`editor/`) is a separate GUI tool for creating and editing the YAML specification files. It is a React + TypeScript frontend backed by a FastAPI Python backend.

| Directory | Purpose |
|---|---|
| `editor/backend/` | FastAPI API: reads/writes YAML, runs validation via `parse.py`, triggers rebuilds via `main.py` |
| `editor/frontend/` | React + TypeScript + Vite app with shadcn/ui and @xyflow/react for DAG visualisation |
| `run_editor.py` | Entry point — starts the uvicorn backend on port 8000 |

**API endpoints** (all under `/api`):
- `GET /spec` — load entire spec as JSON
- `PUT /spec` — validate then write YAML (rejects if invalid)
- `POST /validate` — validate without writing (used for real-time feedback)
- `POST /rebuild` — rebuild the static site

**Key design decisions**:
- All domain validation stays in Python — the backend wraps the existing `parse.py` validators. No client-side validation logic duplication.
- The entire spec is sent/received as a single JSON payload (bulk API) since cross-file references make per-entity validation meaningless.
- The DAG page uses `@xyflow/react` with `dagre` for auto-layout. It is read-only; clicking a node navigates to its edit form.
