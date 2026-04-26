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

## Working with SPEC.md

`SPEC.md` captures the high-level design decisions that explain the purpose and function of the code — the kind of context a new contributor needs that isn't obvious from reading the source.

**As you add features or make design decisions, keep `SPEC.md` in sync.** When a change introduces, alters, or invalidates a design decision important to understanding the system, update `SPEC.md` to reflect it. Don't mirror low-level implementation details that the code already makes clear — focus on the intent, structure, and trade-offs.

**Never edit `SPEC.md` without first checking the proposed edits with the user.** Show the user the change you intend to make (diff or summary) and wait for explicit approval before writing. This applies even in auto/continuous modes.

**`SPEC.md` updates ride along with the same commit that completes the work**, after everything is implemented, working, and tested. Don't pre-edit `SPEC.md` while implementation is in flight, and don't push the spec update to a follow-up commit. (Approval is still required before writing — propose the diff at the end of the task, then commit the spec change together with the code change.)

## Working with TODO.md

`TODO.md` is the running list of features to implement and bugs to fix. It is the canonical place to record outstanding work — not a journal, not a changelog.

**Each entry must carry an effort tag:**
- **small** — a mechanical or self-contained change (e.g. rename, single-file fix, minor template tweak). Roughly: one focused PR, no design decisions.
- **large** — anything that touches multiple subsystems or has non-trivial implementation work.

When in doubt between the two, mark it **large**.

**Entries may also carry an optional status label** alongside the effort tag:
- **needs design** — the item has open design questions that must be resolved with the user before any code is written. In auto mode, draft a proposal rather than starting to code.
- **unapproved** — Claude added this item proactively (e.g. noticed during unrelated work) and the user has not yet reviewed it. Don't start work on `unapproved` items until the user confirms; they may be reworded, deferred, or removed.

If no status label is present, the item is approved and ready to work on.

**You can add new items proactively** when you notice bugs, gaps, or follow-ups during unrelated work. Tag them `unapproved` with a one-line note about how they came up, and surface them to the user at a natural break point.

**Entry format depends on the effort tag:**
- **large** items use the full template — title (with tags), `**Spec ref:**`, `**Context:**`, `**To do:**`.
- **small** items use a lightweight form — title (with tags) plus a one-paragraph description that inlines whatever context is needed (file paths, spec ref, key files to touch). No section headers required.

**When an item is implemented, delete it from `TODO.md`** in the same commit that completes the work. Do not leave a "done" marker, do not move it to a history section, do not strike it through. The git history is the record of what changed; `TODO.md` should always reflect only what is still outstanding.

## Architecture

### Build pipeline

The build pipeline has three phases:

1. **Python/Jinja2 (build time)** — `main.py` orchestrates the build. Form structure is defined in YAML files under `form/`, parsed by `parse.py` into frozen dataclasses from `models.py`. `render.py` produces six output files: a landing page (`index.html`), three per-tool pages (`questionnaire.html`, `assessment.html`, `registry.html`), and two Alpine factories (`app-questionnaire.js`, `app-assessment.js`). The landing page links to the three tools but has no Alpine; the registry is a placeholder for now.

2. **CSS (build time)** — `bulma.min.css` provides class-based styling (layout, typography, form controls, cards, tabs). `input.css` contains custom CSS for app-specific components (badges, risk grid, spacing stacks, persona accents, landing-page tool cards, read-only answers summary). Both are copied directly to `output/` — no compilation step needed.

3. **Alpine.js (runtime)** — Two Alpine factories are emitted, each registering a separate component via `Alpine.data(name, () => ({...}))` on the `alpine:init` event:
   - **`app-questionnaire.js`** registers `'questionnaire'`. Carries `answers`, `details`, `activeTab`, and `prop_*` getters (for question visibility cascade). Persisted state lives under `_x_q_*` keys (e.g. `_x_q_answers`).
   - **`app-assessment.js`** registers `'assessment'`. Carries `answers` + `details` (loaded from a questionnaire JSON), the assessment state (`control_effectiveness`, `residual_*`, `justifications`, `mandated_*`), plus `prop_*`, `ctrl_*`, risk, and residual getters. Persisted state lives under `_x_a_*` keys (e.g. `_x_a_control_effectiveness`).

   The per-tool prefixes guarantee that questionnaire and assessment state never collide in the same browser. Each factory's `init()` hook back-fills any newly-added question/detail/risk/control IDs whose persisted state predates them. Risk getters re-evaluate automatically as answers change. Each section in the questionnaire renders as its own `<form>` shown/hidden via `x-show`; question visibility is driven by the property DAG.

### Core domain model

The system is built around a **property DAG** that decouples questions from risk logic:

- **Properties** (`form/properties.yaml`) — Boolean nodes forming a DAG. Each has an `id`, `description`, optional `parents`, and an `activation` mode (`"all"` or `"any"`). A property is `true` when its question is answered "yes" **and** its parent conditions are met. Properties with no parents are root nodes.

- **Questions** (`form/sections.yaml`) — Two types are supported. **Binary** questions (yes/no) set one or more properties via their `properties` field. **Detail** questions (`type: detail`) reference a `Detail` by `detail_id` and store free-text input in `details[detail_id]` — they don't set property state, but their visibility tracks the referenced detail's properties (copied at parse time). Question visibility is derived automatically from the property DAG — a question is shown when at least one of its target properties is reachable (i.e. the property's parents satisfy the activation mode).

- **Details** (`form/details.yaml`) — Contextual topics keyed by id, each linked to one or more properties. A `DetailQuestion` writes the user's free-text input to `details[detail_id]`; the value is then surfaced in any risk card whose conditions touch one of the detail's properties (under the "Context" section), so contextual notes follow the property graph rather than being hard-wired to a specific risk.

- **Risks** (`form/risks.yaml`) — Each risk has `conditions` (a list of `ConditionMapping`). Each condition references a single property and contributes a `{likelihood, consequence}` pair when that property is `true`. Conjunctions or disjunctions over multiple properties are expressed in the property DAG (via `activation: "all" | "any"` on an intermediate property), not on the risk side. When multiple conditions fire, **worst-case-wins** per dimension independently. When no conditions fire, the risk level is `"not_applicable"`. Conditions are compiled to JS expressions at build time via `to_js()`.

- **Controls** (`form/controls.yaml`) — Safeguards linked to a single property. A control is "present" when its property is `true`. Each control has `effects` listing which risks it addresses (via `risk_id`). Controls do **not** automatically reduce risk — the assessor judges their collective effectiveness per risk at assessment time (see "Residual risk" below). For risks where a control is *not* currently present, the risk card surfaces a "Mandate Controls" checkbox and free-text comment so the assessor can record that the control should be implemented and how.

- **Residual risk** (assessor input at runtime) — For every risk where inherent level is not `not_applicable`, the assessor picks a **control effectiveness**: `ineffective` (default — residual equals inherent), `partial` (assessor picks residual likelihood and consequence independently; level is computed from the matrix), or `controlled` (residual level is the dedicated `controlled` level). A single "Residual Risk Justification" textarea captures the reasoning. State lives in `control_effectiveness`, `residual_likelihood`, `residual_consequence`, `justifications`, `mandated_controls`, and `mandated_comments` on the Alpine scope and is included in the assessment export.

- **Aggregate residual risk** (assessor input at runtime) — In addition to the per-risk residual call, the assessor records an overall residual level for the system as a whole. State lives in `aggregate_residual_level` (string, `''` = follow the suggested worst per-risk; otherwise one of `RISK_LEVELS \ {not_applicable}`) and `aggregate_residual_justification` (string) on the Alpine scope. Both fields are persisted, exported in the assessment JSON, and surfaced on the registry. The `aggregate_residual_level_default` getter computes the suggested worst-per-risk value used as the live `Suggested:` caption beside the picker. Server-side, `registry.aggregate_residual_level(record, ...)` returns the assessor's pick when set, else falls back to `worst_residual_level()`.

The data flow is: **Questions → Properties → Risks / Controls / Details**.

### Key files

| File | Purpose |
|---|---|
| `config.py` | Project paths, risk scales (`LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`), `RISK_LEVEL_COLOURS`, and `RISK_MATRIX` lookup table |
| `models.py` | Frozen dataclasses: `BinaryQuestion`, `DetailQuestion`, `Property`, `ConditionMapping`, `Risk`, `Control`, `ControlEffect`, `Detail`, `Section`, `SubSection` |
| `parse.py` | YAML → dataclass parsing (one `load_*` function per YAML file), id/combinator validation, and `validate_all()` orchestrator |
| `render.py` | Jinja2 environment, view dataclasses (`SectionView`, `RiskView`, `DetailView`, …), `_compile_property_getter`, `_compile_question_visibility`, `_build_template_context`, and the per-tool render functions: `render_landing()`, `render_questionnaire()`, `render_assessment()`, `render_registry()`, `render_questionnaire_app_js()`, `render_assessment_app_js()` |
| `main.py` | Build orchestrator — loads YAML, validates, renders the four pages and two factories, copies assets |
| `form/*.yaml` | Form definitions: `sections.yaml`, `properties.yaml`, `risks.yaml`, `controls.yaml`, `details.yaml` |
| `templates/landing.html.j2` | Landing page (`index.html`): intro copy plus three tool cards. No Alpine. |
| `templates/questionnaire.html.j2` | Questionnaire page skeleton with section tabs + Debug. `x-data="questionnaire"`. |
| `templates/assessment.html.j2` | Assessment page skeleton: load-questionnaire bar, risk cards, read-only answers summary, Debug. `x-data="assessment"`. |
| `templates/registry.html.j2` | Registry placeholder page — no Alpine, no form data. |
| `templates/answers_summary.html.j2` | Read-only walk over the section/subsection/question tree, used inside the assessment page to surface the loaded answers. Inherits visibility from the questionnaire. |
| `templates/app-questionnaire.js.j2` | Alpine factory for the questionnaire view: state, save/load helpers, `init()` migration pass, and compiled `prop_*` getters. |
| `templates/app-assessment.js.j2` | Alpine factory for the assessment view: questionnaire state plus assessment state, save/load helpers, and `prop_*` / `ctrl_*` / risk / residual getters. |
| `templates/subsection.html.j2` | Sub-section partial — heading + question loop |
| `templates/question.html.j2` | Dispatcher — includes `questions/{type}.html.j2` |
| `templates/questions/binary.html.j2` | Binary (yes/no) question partial |
| `templates/questions/detail.html.j2` | Free-text question partial (binds to `details[detail_id]`) |
| `templates/risk_summary.html.j2` | Risk card partial with colour-coded level badge, controls, mandated-control checkboxes, context, and residual-risk inputs |
| `templates/save_load.html.j2` | Reusable save/load button bar partial |
| `input.css` | Custom CSS: tabs, badges, risk grid, spacing stacks, persona accents, landing-page tool cards, answers-summary list. |

### Adding a new question type

The existing `binary` and `detail` question types illustrate the pattern; use them as references.

1. **`models.py`** — Add a frozen dataclass with `id: str`, `text: str`, `properties: tuple[str, ...]`, any type-specific fields, and a `type: Literal["my_type"] = field(default="my_type", init=False)` discriminator. Add the class to the `Question` union type alias.
2. **`parse.py`** — Add a `case` branch in `parse_question()` (with an `_check_unknown_keys` guard listing the allowed YAML keys) to construct the new dataclass.
3. **`templates/questions/my_type.html.j2`** — Create a Jinja2 partial for the new type. Bind to whatever Alpine state the type writes (`answers.<id>` for binary-style, `details[<detail_id>]` for the detail type, etc.).
4. **`render.py`** — If the new type carries fields the templates need beyond `id`/`text`/`type`/`guidance`, add them to `QuestionView` and `_build_question_view`. Also extend `_build_template_context` if the type contributes to property state (see how `BinaryQuestion` is filtered into `question_for_prop`).
5. **`templates/app-questionnaire.js.j2` and `templates/app-assessment.js.j2`** — If the new type needs a non-string default or a separate state map (like `details`), seed it in both factories and back-fill it in their `init()` hooks. Both factories carry `answers` and `details`, so type-specific seeding usually applies to both.
6. **`templates/answers_summary.html.j2`** — Add a branch to display the new question type's answer (read-only) inside the assessment view's loaded-answers panel. The existing `binary` and `detail` branches show the pattern.

No changes needed to `question.html.j2` or `subsection.html.j2` — the dispatcher works generically off the question's `type` field.

### Adding a new risk or control

To add a new **risk**, add an entry to `form/risks.yaml` with `id`, `description`, and `conditions` (each referencing properties by ID).

To add a new **control**, add an entry to `form/controls.yaml` with `id`, `description`, `property` (the property ID that activates it), and `effects` (the list of risks this control addresses, each as `{risk_id: ...}`).

New risks and controls automatically appear in the assessment view — no code changes needed.

### Adding a new property

Add an entry to `form/properties.yaml` with `id`, `description`, and optionally `parents` (list of property IDs) and `activation` (`"all"` or `"any"`, default `"all"`). Then create a question in `form/sections.yaml` whose `properties` field includes the new property ID.

### Adding a new detail

Add an entry to `form/details.yaml` with `id`, `description`, and `properties` (list of property IDs that gate when the detail is shown in risk cards). Then add a `type: detail` question to `form/sections.yaml` referencing it via `detail_id`.

### Form structure

Forms are organised into **Sections** (rendered as tabs in the questionnaire view) and **SubSections** (visual groupings within a section), defined in `form/sections.yaml`. Section `id` values are used as Alpine.js tab identifiers — keep them as simple slugs. The Debug tab is always present in the questionnaire and assessment views and is not defined in the sections list. Risk content lives on the assessment view, not as a tab inside the questionnaire.

### Bulma CSS conventions

Templates use Bulma's class-based styling:
- `.card` / `.card-header` / `.card-content` for risk cards
- `.box` for sub-section groupings
- `.tabs.is-boxed` for tab navigation (active state via `.is-active` on `<li>`)
- `.field` / `.label` / `.control` for form question layout
- `.radio` / `.checkbox` on labels for radio/checkbox inputs
- `.button.is-primary` / `.button.is-light` for action buttons
- `.title` / `.subtitle` / `.has-text-grey` for typography

Custom classes in `input.css` handle app-specific components: `.badge-{color}`, `.risk-grid`, `.control-row`, `.stack-{lg,md,sm}`, `.options-{row,col}`, `.assessed-row`, `.linked-answer`, `.debug-panel`, `.tool-card`, `.persona-{landing,questionnaire,assessment,registry}`, `.answers-summary*`, `.load-questionnaire-bar`.

### Gotcha: Jinja2 autoescape and JS templates

`create_environment()` in `render.py` enables autoescape for `.html` / `.html.j2` / `.htm` / `.xml` templates and disables it everywhere else (including `.js.j2`). This lets the `app-questionnaire.js.j2` and `app-assessment.js.j2` templates emit compiled JS directly without HTML entities creeping in. If you ever inline JS expressions back into an HTML attribute (anywhere outside the `.js.j2` templates), you still cannot use `|tojson` / `|safe` there — pre-serialise with `json.dumps()` in Python and pass as plain string context variables, same pattern as `likelihoods_js` in `render.py`.

### Gotcha: pyright and untyped libraries

YAML parsing boundaries lack type stubs. Files that interact heavily with these use per-file pyright comment overrides:
- `parse.py`: `# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false`
- `tests/js_harness.py`: `# pyright: reportReturnType=false, reportCallIssue=false, reportArgumentType=false` (mini-racer's `ctx.eval` returns a very broad union)

### Testing

Three test layers coexist:

- **Compiler-shape tests** — `tests/test_render.py` and `tests/test_models.py` assert on the substrings emitted by `_compile_property_getter`, `ConditionMapping.to_js`, and friends. They pin the generated code's *form*.
- **Behaviour tests** — `tests/test_js_behaviour.py` uses `tests/js_harness.py` to evaluate the real `render_questionnaire_app_js()` / `render_assessment_app_js()` output inside an embedded V8 context (`mini-racer`). Stubs for `Alpine.data` / `Alpine.$persist` / `document.addEventListener` capture either factory so `prop_*`, `ctrl_*`, risk and residual getters can be driven against in-memory `answers` / `details` / `control_effectiveness` fixtures. The harness exposes `build_questionnaire_scope()` and `build_assessment_scope()`; tests pick whichever surface they need (the assessment factory is a strict superset). They pin the generated code's *semantics*.
- **End-to-end tests** — `tests/e2e/` uses Playwright to drive real Chromium against a built copy of the site served over `http.server`. Each per-tool page has its own fixture (`landing_page`, `questionnaire_page`, `assessment_page`, `registry_page`); `scope_selector("questionnaire" | "assessment")` returns the JS expression that picks the live Alpine scope on whichever page the test is currently driving. Covers save/load (Blob downloads, FileReader imports, confirm/alert dialogs) and landing → tool navigation, which mini-racer can't stub. Marked `@pytest.mark.e2e`; run `uv run playwright install chromium` once after installing dev deps. Skip during tight dev loops with `-m "not e2e"`.

The layers are complementary: a refactor that preserves semantics but changes the emitted format breaks the first layer only; a refactor that preserves the format but flips a branch breaks the second only; a refactor to the save/load HTML wiring or browser-API usage breaks the third only. Write new tests in whichever layer matches what you're protecting against.

### Output

All generated files go to `output/` (gitignored): `index.html` (landing), `questionnaire.html`, `assessment.html`, `registry.html`, `app-questionnaire.js`, `app-assessment.js`, `bulma.min.css`, `input.css`, `alpine3.15.8.min.js`, `alpine-persist.min.js`.

### Versioning and form evolution

Two distinct identifiers, two distinct jobs:

- **`version` (per-format integer)** — JSON *shape* version. Bumped only when the keys/structure of the export change (e.g. a field is renamed or a new top-level block is added). Lives in `config.py` as `QUESTIONNAIRE_VERSION` / `ASSESSMENT_VERSION`. Migrators are written if and when this is bumped.
- **`build_id` (8-char content hash)** — fingerprint of the form YAML at the build that produced an artifact. Computed in `build_id.py` from every `form/*.yaml` file. Embedded in every exported JSON, every rendered HTML page footer, and both Alpine factories' `_buildId` slot. Used as provenance only — it never gates loading.

The registry compares each record's `build_id` to the current build and renders a "Stale build" badge / banner on mismatch. Records made before this scheme have no `build_id` field and are surfaced as stale by default. The numbers shown for an old record still come from its own baked-in `properties` and `inherent` snapshot, so they don't shift when the form changes.

The in-flight questionnaire reload accepts mismatched `build_id` silently (when IDs all align) and routes mismatched `version` through the existing add/removed-confirmation dialog with a "Schema version was X (current: Y)" line. Format mismatch is the only remaining hard reject.

**Discipline rules (not enforced by code; documented for risk managers):**

1. **IDs are immutable.** Renaming an id is a *delete plus an add*. Never reuse a deleted id.
2. **Semantic changes earn a new id.** Rewording a question or risk description is fine; changing *what counts as* the property/risk (different conditions, swapped L/C, parent rewiring, activation flip) means assigning a new id and treating the old one as deprecated. Description rewrites will appear on historical registry entries — the stale-build banner is the cue to interpret with care.
3. **Bump `version` only for JSON shape changes**, not form-content changes. The vast majority of form edits leave `version` unchanged; only the JSON keys/structure bump it.

When `version` does bump, write the migrator alongside this section (none exist yet).

### Spec editor (removed)

There is an `editor/` directory and a `run_editor.py` shim left over from a previous spec-editor experiment, but the editor's source files (FastAPI backend and React frontend) have been removed. `run_editor.py` will not run as-is. Treat the directory as dormant; YAML is currently hand-edited.
