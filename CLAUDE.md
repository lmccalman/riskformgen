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

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Form structure is defined in YAML files under `form/`, parsed by `parse.py` into frozen dataclasses from `models.py`. `render.py` converts them to dicts and renders `templates/page.html.j2` into static HTML. `graph.py` computes a Sugiyama layered layout of the property/risk/control DAG using `grandalf`.

2. **CSS (build time)** — `bulma.min.css` provides class-based styling (layout, typography, form controls, cards, tabs). `input.css` contains custom CSS for app-specific components (badges, risk grid, graph styles, spacing stacks, etc.). Both are copied directly to `output/` — no compilation step needed.

3. **Alpine.js (runtime)** — A parent `<div>` holds the `x-data` scope shared by all section forms, the risks panel, and the graph tab. It contains reactive `answers` state, computed property getters (`prop_*`), control getters (`ctrl_*`), and risk getters — all compiled from Python at build time. Each section renders as its own `<form>` shown/hidden via `x-show`. Question visibility is driven by the property DAG (questions are shown when their target properties are reachable). Risk getters re-evaluate automatically as answers change.

### Core domain model

The system is built around a **property DAG** that decouples questions from risk logic:

- **Properties** (`form/properties.yaml`) — Boolean nodes forming a DAG. Each has an `id`, `description`, optional `parents`, and an `activation` mode (`"all"` or `"any"`). A property is `true` when its question is answered "yes" **and** its parent conditions are met. Properties with no parents are root nodes.

- **Questions** (`form/sections.yaml`) — Currently all `binary` (yes/no). Each question sets one or more properties via its `properties` field. Question visibility is derived automatically from the property DAG — a question is shown when at least one of its target properties is reachable (i.e. the property's parents satisfy the activation mode).

- **Risks** (`form/risks.yaml`) — Each risk has `conditions` (a list of `ConditionMapping`). Each condition checks a set of properties (via `mode: "any"` or `"all"`) and contributes a `{likelihood, consequence}` pair when the check passes. When multiple conditions fire, **worst-case-wins** per dimension independently. When no conditions fire, the risk level is `"not_applicable"`. Conditions are compiled to JS expressions at build time via `to_js()`.

- **Controls** (`form/controls.yaml`) — Safeguards linked to a single property. A control is "present" when its property is `true`. Each control has `effects` listing which risks it reduces and in which dimension (`reduces_likelihood`, `reduces_consequence`).

The data flow is: **Questions → Properties → Risks / Controls**. This is the DAG that the graph visualisation renders.

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths, risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), and `RISK_MATRIX` lookup table |
| `models.py` | Frozen dataclasses: `BinaryQuestion`, `Property`, `ConditionMapping`, `Risk`, `Control`, `ControlEffect`, `Section`, `SubSection` |
| `parse.py` | YAML → dataclass parsing (one `load_*` function per YAML file) plus validation functions |
| `render.py` | Jinja2 environment, `prepare_properties()`, `prepare_sections()`, `prepare_risks()`, `prepare_controls()`, `prepare_graph()`, and `render_form()` |
| `graph.py` | DAG layout computation using `grandalf` Sugiyama layout — produces `GraphNode`, `GraphEdge`, `GraphLayout` |
| `main.py` | Build orchestrator — loads YAML, validates, renders HTML, copies assets |
| `form/*.yaml` | Form definitions: `sections.yaml`, `properties.yaml`, `risks.yaml`, `controls.yaml` |
| `templates/page.html.j2` | Page skeleton with Alpine.js state, tab navigation, property/risk/control getters, panzoom init |
| `templates/graph.html.j2` | SVG DAG visualisation with Alpine.js `:class` bindings for reactive colouring and Bulma modal for node details |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/binary.html.j2` | Binary (yes/no) question partial |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge |
| `templates/save_load.html.j2` | Reusable save/load button bar partial |
| `input.css` | Custom CSS: tabs, badges, risk grid, graph styles, spacing stacks, etc. |

### Graph visualisation

The Graph tab renders the property/risk/control DAG as an interactive SVG:

- **Layout** is computed at build time by `graph.py` using `grandalf` (pure Python Sugiyama layered layout). The layout flows left-to-right by computing top-to-bottom then swapping x/y coordinates.
- **Rendering** is an SVG emitted by `templates/graph.html.j2` with Alpine.js `:class` bindings for reactive node/edge colouring.
- **Pan/zoom** is provided by the vendored `panzoom` library, lazily initialised when the Graph tab is first visited.
- **Node detail modal** uses a Bulma `.modal` triggered by `@click` on SVG nodes, showing type, description, current state, and connections.

Node colouring by state:
- **Property**: green (true), grey (false), amber (unknown/null)
- **Risk**: green (low), amber (medium), red (high), grey (not applicable)
- **Control**: blue (active), grey (inactive)

Edge colouring: solid when the source node is active; dashed grey when inactive.

### Adding a new question type

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, `properties: tuple[str, ...]`, any type-specific fields, and a `type: str = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`parse.py`** — Add a `case` branch in `parse_question()` to construct the new dataclass from YAML dicts.
3. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Use `x-model="answers.{{ question.id }}"` to bind to Alpine.js state.
4. **`templates/page.html.j2`** — If the new type needs a non-string default (like `[]` for arrays), add a condition to the `x-data` initialiser.

No changes needed to `question.html.j2`, `subsection.html.j2`, `render.py`, or the build pipeline — the dispatcher and renderer work generically.

### Adding a new risk or control

To add a new **risk**, add an entry to `form/risks.yaml` with `id`, `description`, and `conditions` (each referencing properties by ID).

To add a new **control**, add an entry to `form/controls.yaml` with `id`, `description`, `property` (the property ID that activates it), and `effects` (which risks it reduces).

New risks and controls automatically appear in the Risk Analysis tab and the Graph tab — no code changes needed.

### Adding a new property

Add an entry to `form/properties.yaml` with `id`, `description`, and optionally `parents` (list of property IDs) and `activation` (`"all"` or `"any"`, default `"all"`). Then create a question in `form/sections.yaml` whose `properties` field includes the new property ID.

### Form structure

Forms are organised into **Sections** (rendered as tabs) and **SubSections** (visual groupings within a section), defined in `form/sections.yaml`. Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs. The Graph tab (blue accent) and Risk Analysis tab (red accent, right-aligned) are always present and not defined in the sections list.

### Bulma CSS conventions

Templates use Bulma's class-based styling:
- `.card` / `.card-header` / `.card-content` for risk cards
- `.box` for sub-section groupings
- `.tabs.is-boxed` for tab navigation (active state via `.is-active` on `<li>`)
- `.field` / `.label` / `.control` for form question layout
- `.radio` / `.checkbox` on labels for radio/checkbox inputs
- `.button.is-primary` / `.button.is-light` for action buttons
- `.title` / `.subtitle` / `.has-text-grey` for typography
- `.modal` / `.modal-card` for graph node detail popups

Custom classes in `input.css` handle app-specific components: `.badge-{color}`, `.risk-grid`, `.graph-container`, `.graph-fill-*`, `.graph-edge-*`, `.graph-node`, `.graph-label`, `.control-row`, `.stack-{lg,md,sm}`, `.options-{row,col}`, `.assessed-row`, `.linked-answer`, `.debug-panel`.

### Gotcha: Jinja2 autoescape and Alpine.js

The Jinja2 environment uses `autoescape=True`. When rendering JS expressions inside `x-data="..."` attributes, **do NOT use `|safe` or `|tojson`**. Autoescape produces HTML entities (`&#34;` for `"`, `&gt;` for `>`, `&#39;` for `'`) which the browser decodes back to the original characters when reading the attribute value — before Alpine evaluates the JS. Using `|safe` or `|tojson` (which marks output as `Markup`) puts raw `"` into a `"`-delimited attribute, breaking HTML parsing. Instead, pre-serialise to JSON strings in Python with `json.dumps()` and pass as plain string template variables.

### Gotcha: pyright and untyped libraries

`grandalf` and YAML parsing boundaries lack type stubs. Files that interact heavily with these use per-file pyright comment overrides:
- `graph.py`: `# pyright: reportAttributeAccessIssue=false`
- `parse.py`: `# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false`

### Output

All generated files go to `output/` (gitignored): `index.html`, `bulma.min.css`, `input.css`, `alpine3.15.8.min.js`, `alpine-persist.min.js`, `panzoom.min.js`.
