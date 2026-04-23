# TODO — riskformgen (outstanding AUDIT.md items)

Scope: only items from `AUDIT.md` still marked `**Status:** open`. Numbering is
preserved from `AUDIT.md` so cross-references stay stable; category headings
are kept even where they now contain only a handful of items.

Severity tags: ⚠ high, ◑ medium, · low. When an item is addressed, update its
status line in `AUDIT.md` to `resolved (YYYY-MM-DD)` and drop it from this
file.

---

## 1. Bugs and incorrect implementation

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

Current behaviour is now pinned by `TestQuestionVisibility` in
`tests/test_js_behaviour.py` (see §4.8); flipping to `=== true` requires a
deliberate test update.

### 1.4 ◑ Output directory is never cleaned
**Status:** open
`main.py:ensure_output_dir` (line 22) only calls `mkdir(exist_ok=True)`. If a
previously-copied asset is renamed (or the editor shrinks), the old file
lingers in `output/`. Consider `shutil.rmtree(output_dir, ignore_errors=True)`
before rebuilding, or track copied files and delete stragglers.

### 1.6 · Risk "n/a" fallback bypasses the scale tuples
**Status:** open
`page.html.j2:247` returns `{likelihood: 'n/a', consequence: 'n/a', level:
'not_applicable'}` when no condition fires. `'n/a'` isn't in `LIKELIHOODS` /
`CONSEQUENCES`, so `_worst` can't ever work on it, and it only appears because
of the short-circuit at line 247. The same condition is expressed with `null`
elsewhere (`_worst` filter). Two conventions for the same state are confusing;
pick one (`null` seems cleaner, and `risk_summary.html.j2:18,27` would then
need a `|| '—'` default).

Current behaviour (`'n/a'` string literal for the short-circuit) is now
pinned by `TestRiskAggregation::test_no_conditions_fire_is_not_applicable`
in `tests/test_js_behaviour.py` (see §4.8); switching to `null` requires a
deliberate test update.

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

---

## 3. Old or inconsistent documentation

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

### 4.9 Replace `print` in `main.py` with a logger
**Status:** open
Trivial, but useful once the editor backend calls into `main.main()` and
wants to surface build output.

---

## 5. Test coverage and correctness

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
