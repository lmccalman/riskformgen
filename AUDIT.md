# Audit — riskformgen (excluding `editor/`)

Scope: all Python, Jinja2, YAML, and tests under the project root except the
`editor/` tree. Read-only review — nothing was changed.

Findings are grouped by the five requested categories. Each item carries a
severity tag (⚠ high, ◑ medium, · low) and points at the file/line so they can
be picked off individually.

Each finding has a `**Status:**` line directly under its heading — `open` or
`resolved (YYYY-MM-DD)`. When an item is addressed, update its status line to
`resolved (YYYY-MM-DD)` (and optionally a short note or commit ref). To see
what is still outstanding: `grep -B1 "Status:\*\* open" AUDIT.md`.

---

## 1. Bugs and incorrect implementation

### 1.1 ⚠ Controls don't actually reduce risk — only displayed
**Status:** resolved (2026-04-23) — replaced auto-reduction with assessor-judged control effectiveness + residual risk (see `control_effectiveness` / `residual_likelihood` / `residual_consequence` state in `templates/page.html.j2`).
`templates/page.html.j2:241-254` computes the risk level purely from
`ConditionMapping` results and the `RISK_MATRIX` lookup. Controls never enter
the calculation.

Meanwhile:
- `README.md:138` states "Controls … reduce the assessed likelihood or
  consequence of linked risks by one step."
- `templates/risk_summary.html.j2:60-64` renders "↓ Likelihood", "↓ Consequence"
  next to each control, strongly implying the computed risk reflects them.
- `ControlEffect.reduces_likelihood / reduces_consequence` (`models.py:111-123`)
  exist only for the display label; they never affect numbers.

Either the reduction must be implemented (e.g. step-down the `_worst` result
per dimension when the control's `prop_*` getter is `true`), or the UI and
README need to be reframed so the reader doesn't think they reduce anything.
This is the single biggest source of user confusion in the codebase.

### 1.2 ◑ Follow-up questions appear before their parent is answered
**Status:** open
`render.py:_compile_question_visibility` uses `prop_{parent} !== false`
(`render.py:94, 97`). Before any answer is given, `prop_parent` returns `null`,
and `null !== false` is `true`, so the child question is visible.

Concretely, in the demo form the question "Do you exercise at least a few times
per week?" (`is_active` parent) is visible *before* the user answers "Do you
engage in regular physical activity?". The inline comment
(`render.py:81-83`) calls this "reachable", but the UX result is that all
questions on a tab appear at once. If the intent is "hide until parent is
answered affirmatively", change the check to `=== true`.

This is a semantic decision rather than a clear bug, but the current behaviour
is likely surprising given the emphasis on DAG-driven visibility in
`CLAUDE.md`.

### 1.3 ◑ `$persist` + schema migration produces phantom-missing keys
**Status:** open
`templates/page.html.j2:22-55` seeds `answers`, `details`, `assessed_risks`,
etc. with the current build's ID list, but `$persist` overwrites them from
`localStorage`. When a new question is added to `sections.yaml`, existing users
restore an object without the new key. `x-model` still works (Alpine writes
through), but:

- The Debug tab's `JSON.stringify(answers)` shows the key only after the user
  interacts with the new question.
- `exportAnswers()` (`page.html.j2:112-122`) emits whatever the object
  contains, so new-but-unanswered questions are silently omitted.

A one-time merge pass on startup (`for id of _questionIds: if (!(id in
answers)) answers[id] = ''`) would fix this and is the standard migration
pattern for persisted objects.

### 1.4 ◑ Output directory is never cleaned
**Status:** open
`main.py:ensure_output_dir` (line 22) only calls `mkdir(exist_ok=True)`. If a
previously-copied asset is renamed (or the editor shrinks), the old file
lingers in `output/`. Consider `shutil.rmtree(output_dir, ignore_errors=True)`
before rebuilding, or track copied files and delete stragglers.

### 1.5 ◑ No validation that IDs are valid JS identifiers
**Status:** open
`render.py` and `page.html.j2` generate identifiers like
`get prop_{{ prop.id }}()`, `get {{ risk.id }}()`, `x-model="answers.{{
question.id }}"`. If a YAML author writes `id: my-risk` or `id: 2fa_required`,
the emitted HTML will throw a silent JS syntax error at runtime. The only
guard is convention. Add a `_validate_id(str)` check in `parse.py` that
enforces `^[A-Za-z_][A-Za-z0-9_]*$`.

Related risk: no check prevents a risk, control, question, property, or detail
from colliding with each other or with reserved names in the Alpine state
(`answers`, `details`, `_worst`, `_questionIds`, …). Build-time collision
detection would catch these before they become ugly runtime bugs.

### 1.6 · Risk "n/a" fallback bypasses the scale tuples
**Status:** open
`page.html.j2:247` returns `{likelihood: 'n/a', consequence: 'n/a', level:
'not_applicable'}` when no condition fires. `'n/a'` isn't in `LIKELIHOODS` /
`CONSEQUENCES`, so `_worst` can't ever work on it, and it only appears because
of the short-circuit at line 247. The same condition is expressed with `null`
elsewhere (`_worst` filter). Two conventions for the same state are confusing;
pick one (`null` seems cleaner, and `risk_summary.html.j2:18,27` would then
need a `|| '—'` default).

### 1.7 · Import version field is declarative but not enforced
**Status:** open
`page.html.j2:115, 184` write `version: 1`. The importer
(`page.html.j2:123-153`) only checks `format`. A future v2 would load silently
into a v1 client. Add a version guard with a clear error message.

### 1.8 · `validate_property_dag` comment contradicts the code
**Status:** open
`parse.py:231` says "Edges point child→parent, so in-degree counts how many
children point to a node." The code then does `in_degree[p.id] += 1` (line 236)
— incrementing the *child's* in-degree (i.e. "how many parents I have"). The
topological sort is correct, but the comment describes the wrong direction.

### 1.9 · Dead: `_ensure_str`
**Status:** open
`parse.py:30-38` is only referenced by `tests/test_parse.py:18`. The function
was presumably introduced for an older YAML shape where boolean literals could
appear; nothing in the current parser uses it. Delete or wire it into
`parse_question` if bool answers in YAML are still supported.

### 1.10 · Dead: `_formatAnswer`
**Status:** open
`templates/page.html.j2:72-75`. Not referenced anywhere in the templates.
Likely a leftover from an older "export as Markdown" flow.

---

## 2. Simplicity and maintainability

### 2.1 ⚠ 240-line JS literal embedded in an HTML attribute
**Status:** open
`page.html.j2:20-256` is one enormous `x-data="{…}"` attribute containing
state, methods (`clearAll`, `exportAnswers`, `importAnswers`, `_importJson`,
`_worst`, `_formatAnswer`, `_downloadJson`), and a getter per property,
control, and risk.

Problems:
- Not reachable by any JS linter or formatter.
- The browser parses it as an HTML attribute first, so escaping bugs
  (the gotcha called out in `CLAUDE.md:140-148`) are easy to reintroduce.
- Hard to diff when either the template or the generated logic changes.
- Stack traces from browser devtools land inside `index.html`.

A big quality-of-life win would be to render a separate `output/app.js` from an
`app.js.j2` template, keep the HTML file minimal, and load it with
`<script defer src="app.js"></script>`. All the same Jinja substitutions still
work; the file just isn't an HTML attribute anymore.

### 2.2 ◑ Hand-built Jinja loops for JS object literals
**Status:** open
`page.html.j2:22-62` has dozens of lines of the form
```jinja
{% for q in questions %}
'{{ q.id }}': ''{% if not loop.last %},{% endif %}
{% endfor %}
```
replicated across `answers`, `details`, `assessed_risks`, `justifications`,
`mandated_controls`, `mandated_comments`, `_questionIds`, `_detailIds`,
`_riskIds`, `_controlIds`. All of these are equivalent to a dict/list passed
through `json.dumps()` in Python. `config.py`'s matrix and the scale tuples
already do exactly this (`render.py:303-307`). Extending that pattern would
delete ~50 lines of brittle comma-conditional Jinja.

### 2.3 ◑ `prepare_controls` mutates its argument
**Status:** open
`render.py:241-269` assigns `risk_dict["controls"] = []` into the caller's list
and appends to it. This is the only mutation-in-place function in the module
and forces call sites to know about the side effect. Return a new list of
risk dicts (or a parallel `controls_by_risk_id: dict[str, list[dict]]`).

### 2.4 ◑ String literals for closed enums
**Status:** open
- `Property.activation` ("all" | "any") — `models.py:163`
- `ConditionMapping.mode` ("all" | "any") — `models.py:86`
- `Question.type` ("binary" | "detail") — `models.py:20, 36`

Using `typing.Literal` would catch typos at parse time without any runtime
cost, and lets pyright/IDE help on conditional branches. Matches the pyright
override hassle in `parse.py:1`.

### 2.5 ◑ YAML fields are silently ignored if unknown
**Status:** open
`parse_*` functions pluck specific keys (`data["id"]`, `data.get("guidance")`,
…). A typo like `guidelines:` instead of `guidance:` will produce a valid
build with wrong content. A `pydantic` model or manual `unknown key` check
at parse time would catch these.

### 2.6 · `prepare_*` functions return untyped `dict`
**Status:** open
`render.py` builds dicts with string-typed keys returned as `list[dict]`. A
`TypedDict` per shape (question, risk, subsection) would make the template
contract explicit. Jinja2 is fine with either; the cost is low.

### 2.7 · Single `validate_all` entry point
**Status:** open
`main.py:64-71` has seven `validate_*` calls in sequence. A single
`parse.validate_all(sections, properties, risks, controls, details)` would
make the public surface smaller and give tests a single target.

### 2.8 · `clearAll` wipes everything regardless of which tab's button is clicked
**Status:** open
`page.html.j2:85-111` is wired into both save-bars (`answers` and
`assessment`). That's probably intentional, but the button still reads
"Clear all" in both places — a user on the Risks tab might expect it to clear
only assessments. Minor UX; confirm dialog covers the blast radius.

### 2.9 · Jinja autoescape gotcha is documented but easy to regress
**Status:** open
`CLAUDE.md:140-148` explains why `|tojson` is unsafe inside an `x-data`
attribute. If the `x-data` attribute is moved out into a script file
(§2.1), that gotcha disappears entirely.

---

## 3. Old or inconsistent documentation

### 3.1 ⚠ `README.md` is entirely wrong about the schema
**Status:** open
The README notes itself is "earlier version" (`README.md:3-6`), but then spends
~250 lines documenting a form schema that does not exist in the code:

| README says | Current code |
|---|---|
| `type: yes_no` | `type: binary` (only that + `detail`) |
| `type: free_text` / `multiple_choice` / `multiple_select` | Not implemented; `parse.py:147-148` explicitly rejects them |
| `visible_when: any/all/equals/contains/not` | Not implemented; visibility is derived from the property DAG |
| `risks:` with `name`, `default_likelihood`, `default_consequence`, `rules` | `id`, `description`, `conditions` only |
| Rule types `any_yes`, `count_yes`, `choice_map`, `contains_any` | Only `ConditionMapping` with `mode: any/all` |
| Controls with `question_id` / `present_value` | Controls key off a `property` |
| Controls "reduce by one step" | Not implemented (§1.1) |
| No mention of `details.yaml` / `DetailQuestion` | Exists |

A new user following the README will produce YAML that fails to parse with
`Unknown question type: 'yes_no'`. The README needs a full rewrite, or a
clear "deprecated, see CLAUDE.md" header and the old content removed.

### 3.2 ✓ `CLAUDE.md` still describes the removed graph visualisation — **resolved**
**Status:** resolved (2026-04-23)
Commit `f252325` ("remove graph visualisation for now") deleted `graph.py`,
`templates/graph.html.j2`, and `assets/panzoom.min.js`, and the dependency on
`grandalf` is gone from `pyproject.toml`. All corresponding references have
now been stripped from `CLAUDE.md`: the build-pipeline phase-1 mention,
key-files entries for `graph.py` and `templates/graph.html.j2`, the "panzoom
init" note on `page.html.j2`, the entire "Graph visualisation" section, the
node-colouring table, the `pyright` override for `graph.py`, the
`panzoom.min.js` output-asset entry, the `.modal` "graph node detail popups"
bullet, the `.graph-*` custom-class list in the Bulma conventions section,
the Graph-tab mention in "Form structure", and the "Graph tab" in the
`x-data` scope description. The "The Graph tab (and Debug tab —
undocumented) is present" sub-finding about the Debug tab is still open as
§3.3.

### 3.3 ◑ Debug tab exists but is undocumented
**Status:** open
`page.html.j2:270-272, 295-327` renders a Debug tab that dumps every piece of
state (`answers`, `details`, property states, risks, assessed risks,
justifications, mandated controls, mandated comments). Nothing in
`CLAUDE.md` mentions it; new contributors won't know it's there.

### 3.4 ◑ `details.yaml` / `DetailQuestion` absent from `CLAUDE.md`
**Status:** open
The Key Files table (`CLAUDE.md:74-90`) lists every form YAML except
`details.yaml`. "Adding a new question type" (`CLAUDE.md:103-109`) doesn't
reference `DetailQuestion` as a worked example. The property flow diagram
(`CLAUDE.md:66`) says "Questions → Properties → Risks / Controls" but
`DetailQuestion` actually copies properties from `Detail` and flows into
rendered detail text; the mental model is different.

### 3.5 · Misleading comment in `parse.py:231`
**Status:** open
See §1.8 — the in-degree direction is described backwards.

### 3.6 · `_ensure_str`'s docstring describes YAML bool coercion that's unused
**Status:** open
See §1.9 — the function and its comment are unreferenced.

---

## 4. Architecture and implementation improvements

### 4.1 Implement (or remove) the control-reduction semantics
**Status:** resolved (2026-04-23) — chose assessor-judged effectiveness rather than implementing auto-reduction or removing the display. See §1.1 note.
Pick one of:
- Implement: in the risk getter (`page.html.j2:241`), before the matrix
  lookup, step the worst likelihood/consequence down by one index per active
  control with `reduces_likelihood` / `reduces_consequence` set. Clamp at 0.
- Remove: drop `reduces_likelihood` / `reduces_consequence` from
  `ControlEffect`, and rename the risk-card section from "Controls" to
  "Related safeguards" (displayed but not applied). Update README.

§1.1 isn't an architecture issue *yet*, but the choice you make determines
whether the next few weeks of schema work will fight the codebase.

### 4.2 Extract the Alpine bundle out of the HTML attribute
**Status:** open
See §2.1. A sketch:

1. Add `templates/app.js.j2` that renders the entire Alpine component
   (state + methods + getters).
2. In `render.py`, render it to `output/app.js` alongside `index.html`.
3. Import it with `<script defer src="app.js"></script>` and change
   `x-data="app()"` in `page.html.j2`. Expose `window.app = () => ({…})` in
   `app.js`.
4. All current `json.dumps()` escaping (§2.2) stays — just moved to a context
   where `|tojson` is also safe.

### 4.3 Typed identifiers and collision check
**Status:** open
- `_validate_id(str) -> None` rejecting anything not `^[A-Za-z_]\w*$`.
- Call from every `parse_*` function that sees an `id` / `detail_id` /
  `risk_id`.
- Add a `validate_id_uniqueness_across_namespaces(sections, props, risks,
  controls, details)` that asserts disjoint sets (or at least prefixed
  disjoint sets).

### 4.4 Stop mutating in `prepare_controls`
**Status:** open
Have it return `dict[risk_id, list[ControlDisplay]]` and let `prepare_risks`
or `render_form` attach those to the outgoing dicts. Tests then don't need to
construct risk dicts and pass them in (`test_render.py:303-334`).

### 4.5 Collapse the dict-conversion layer
**Status:** open
Jinja2 is happy to traverse dataclasses via attribute access. The `prepare_*`
functions exist mostly to attach computed `visibility_js` strings and JSON
bodies. Those could live in a thin dataclass-to-context function that returns
typed records, or on the dataclasses themselves as cached properties. Saves a
~200-line module and the associated tests that mirror its shape.

### 4.6 Clean `output/` before each build
**Status:** open
See §1.4.

### 4.7 Consider a single-enum `ControlEffect.reduces`
**Status:** resolved (2026-04-23) — obsoleted by §1.1 resolution. `reduces_likelihood` / `reduces_consequence` removed entirely; `ControlEffect` now holds only `risk_id`.
Instead of two booleans with a `__post_init__` that forbids `(False, False)`
(`models.py:119-123`), a single `reduces: Literal["likelihood",
"consequence", "both"]` field is equally expressive and removes the
impossible-state class. Touch point: `parse_control_effect`
(`parse.py:149-155`) and the template's display label.

### 4.8 Add a JS-behaviour test layer
**Status:** open
Everything from `_compile_property_getter` through `prepare_risks.to_js()` is
string-building. The current tests check the strings, not the semantics. A
few options, roughly in ascending cost:

- Use `py-mini-racer` / `quickjs` to evaluate the generated getters against
  `answers` fixtures and assert the resulting `prop_*` / risk level. This
  would catch the §1.2 question-visibility concern, the cascading-null
  behaviour, the "n/a" vs `null` issue (§1.6), the risk-matrix fallback, and
  future regressions.
- Playwright end-to-end: build, open `output/index.html`, click through
  answers, snapshot the Debug-tab JSON. Higher value for catching
  persistence bugs (§1.3) and the radio-selected class behaviour.

### 4.9 Replace `print` in `main.py` with a logger
**Status:** open
Trivial, but useful once the editor backend calls into `main.main()` and
wants to surface build output.

---

## 5. Test coverage and correctness

### 5.1 ⚠ No tests exercise the generated JavaScript
**Status:** open
The heart of the product (parent-cascade null-propagation, worst-case-wins
aggregation, risk matrix lookup, control/detail reactivity) runs in the
browser. Every Python test of this logic asserts on the emitted *string*:

- `test_render.py:36-67` (property getter) — checks for `"'yes'"`,
  `"this.prop_p1 === false"`, `"parents.every(p => p === false)"`. A refactor
  that changes the compiled format silently, even if the semantics are
  preserved, will break these tests. Worse, a refactor that preserves the
  substrings but breaks semantics (say, flipping `false`/`null` branches)
  passes.
- `test_models.py:TestConditionMapping` — same substring style
  (`"this.prop_p1"`, `".some("`, `"likely"`).
- `test_render.py:TestRenderForm` — asserts `"prop_prop_a"` appears in the
  HTML, not that evaluating the form gives the right answer.

See §4.8. This is the single most important gap — nothing in CI currently
catches a regression in risk calculation.

### 5.2 ◑ `test_form_files.py` asserts on demo counts
**Status:** open
`tests/test_form_files.py:43, 67, 89, 115` hard-code the number of sections,
properties, risks, and controls in the demo form. Changing the demo (which is
intended behaviour — the form is illustrative) forces a test update.
Better: drop the counts and assert invariants (unique IDs, references resolve,
DAG valid). Even better: use a dedicated fixture YAML under `tests/fixtures/`
so the production form can evolve independently.

Note also the inconsistency: `TestDetails` (lines 146-162) does *not* assert
a specific detail count, unlike its siblings. Pick a side.

### 5.3 ◑ Module-level YAML loading
**Status:** open
`tests/test_form_files.py:22-33` loads every YAML at import time. A YAML
syntax error anywhere produces a test-collection failure with a pytest stack
trace that blames the test file, not the YAML. Move to fixtures with
`pytest.fixture(scope="module")` so a failure becomes a clean per-test error.

### 5.4 ◑ `main.py` has no tests
**Status:** open
`ensure_output_dir`, `write_html`, `copy_css`, `copy_alpine`, and the
orchestrating `main()` function (`main.py:22-82`) are uncovered. A smoke test
that runs `main()` into a tmpdir and asserts the expected files exist (and
that `index.html` is non-empty) would catch breakage in the wiring.

### 5.5 ◑ Export/import roundtrip is untested
**Status:** open
`page.html.j2:112-230` contains substantial logic (version-gated parsing,
added/removed ID diffs, mandate-control merging, error paths). All of it
lives in JS. There's no Python test, and the only render-side test is
`TestRenderFormSaveLoad` which verifies *strings appear*. A JS-behaviour test
harness (§4.8) or a Playwright test would close this.

### 5.6 ◑ Subsection visibility dominance rule is not tested
**Status:** open
`render.py:180` says: if any question in the subsection is always visible,
the subsection has no `visibility_js`. `test_render.py:TestPrepareSections`
exercises the "all conditional" case (`test_subsection_visibility`, line
189) but not the "mixed" case (conditional + always-visible) that triggers
the dominance rule. Add a test that constructs a subsection with one root
question and one child-of-child question and asserts no `visibility_js` key.

### 5.7 ◑ No tests for detail rendering in the final HTML
**Status:** open
`TestRenderForm::test_with_details` (line 396) only checks that `"details:"`
and `"det1"` appear. Nothing verifies the per-risk `relevant_details`
filtering is wired through to the template, the `show_js` conditional
renders, or that detail guidance appears beside the textarea. Given
`details.yaml` is the newest addition (commit `e28191d`), this is the area
most likely to drift.

### 5.8 · Validation tests only check messages, not that all errors are reported
**Status:** open
`test_parse.py:TestValidatePropertyDag` checks one error at a time. The
"`multiple_errors_reported`" pattern used elsewhere
(`test_parse.py:408, 509, 561`) is good — extend it to
`validate_property_dag` (e.g. duplicate ID + unknown parent + cycle
together).

### 5.9 · `test_old_types_raise` (test_parse.py:145) hard-codes old type names
**Status:** open
This is a defensive test that the old YAML types (`yes_no` etc.) are rejected.
It's correct, but its existence only makes sense in light of the README (see
§3.1) — it's effectively testing that the README is stale. Once the README
is rewritten, delete this test.

### 5.10 · `TestRenderFormMetadata` tests internal array names
**Status:** open
`test_render.py:434-442` asserts on `_riskIds: [` in the HTML. If §2.2 is
adopted (pass state as `json.dumps()`), the name or format changes and the
test becomes stale without surfacing an actual behavioural regression.

---

## Summary of highest-leverage follow-ups

1. **Decide on control semantics** (§1.1, §4.1) — either implement risk
   reduction or refactor the display. Everything downstream depends on this.
2. **Rewrite `README.md`** (§3.1) — the current file actively misleads. In the
   short term, replace the body with a pointer to `CLAUDE.md` and a one-page
   quickstart.
3. ~~**Prune `CLAUDE.md`** of all graph-visualisation references (§3.2)~~ —
   **done.**
4. **Add a JS-behaviour test layer** (§4.8, §5.1) — currently nothing in CI
   catches a regression in the actual risk calculation.
5. **Lift `x-data` out of the HTML attribute** (§2.1, §4.2) — unblocks
   linting, debugging, and makes §4.8 much easier.
6. **Tighten ID validation** (§1.5, §4.3) — cheap, closes a class of silent
   runtime bugs.
7. **Delete dead code** (§1.9, §1.10) — small but keeps the next reader from
   wondering why it's there.
