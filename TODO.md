# TODO.md

Outstanding features to implement and bugs to fix. Each entry carries an
effort tag (**small** or **large**), and may carry an optional status label
(**needs design** = open questions to resolve before coding; **unapproved**
= Claude added proactively, awaiting user review). No status label = ready
to work on.

`small` items use a lightweight one-paragraph format; `large` items use the
fuller **Spec ref / Context / To do** template.

When an item is implemented, delete it from this file in the same commit
that completes the work — git history is the record.

---

## Aggregate residual risk — **large**

**Spec ref:** §Concepts → Aggregate residual risk.

**Context:** "The risk assessor assigns an overall risk level to the system
based on their judgement of the set of residual risk levels of the risks
after all controls are applied. This is not necessarily the maximum of the
individual risk levels."

Currently the code has per-risk residual levels but no UI for the assessor
to pick an aggregate level for the whole system, and no field for it in the
assessment JSON.

**To do:**
- Add an aggregate-residual-risk picker (one of `RISK_LEVELS`, probably
  excluding `not_applicable`) to the assessment surface. Default: the worst
  per-risk residual level, but freely overridable by the assessor.
- Add a justification textarea for the aggregate decision (separate from
  per-risk justifications).
- Include both fields in the assessment JSON export (and load them back on
  import). Bump the assessment-format version and add migration code so old
  assessment JSONs (without the aggregate field) still import cleanly.

---

## Versioning across form evolution — **large**, **needs design**

**Spec ref:** §Key design goals → "Risks, controls, questionnaire questions
and properties must be able to evolve" + the constraint that older
assessments and questionnaire answers should not break.

**Context:** Some basics already exist: `init()` back-fills new IDs; JSON
exports carry `format` + `version` fields; import shows added/removed counts
with a confirmation dialog. But there's no formal record of *which build*
the JSON came from beyond the integer version, no migration path, and no
guarantees about how the registry handles assessments produced against older
versions of the form.

**Update (2026-04-26):** Both export formats now carry the resolved
property states and per-risk inherent values (questionnaire `properties`,
assessment `inherent`). The registry renders these directly without
re-deriving against the current form, so historical assessments are
stable across form changes. The versioning work narrows to: build-
identifier embedding, migration of older-version JSONs on import, and
stale-build warnings on the registry.

**To do:** Design and implement a versioning strategy. Likely shape:
- Embed a build identifier (e.g. a hash of the YAML + a human-friendly
  version string) into both the built site and into every exported JSON.
- Decide which constraints to impose on risk managers to keep things
  tractable — e.g. "IDs are immutable; semantics behind an ID can change but
  IDs are never reused." Document the rules in `CLAUDE.md`.
- Make the registry able to load assessments from older builds and show them
  meaningfully (even if the form has since changed). At minimum, surface a
  warning when the assessment's build differs from the current build, and
  show which fields are stale / missing / new.
- Stretch: a "change assessment" mode (per spec workflow point 8) that loads
  old + new questionnaire JSONs and surfaces only the diff. This is
  effectively a registry feature on top of solid versioning, so build
  versioning first.

---

## Rename property/condition combinator: `all` / `any` → `all_depends` / `any_depends` — **small**

The spec (§Concepts → Properties) uses the more descriptive `all_depends` /
`any_depends`; the YAML and code use `all` / `any`. Update YAML in
`form/properties.yaml` and `form/risks.yaml`, `_parse_combinator` in
`parse.py` (reject the old names — no backwards-compat shim, this is a
hand-edited format), the literal types in `models.py` (`Property.activation`,
`ConditionMapping.mode`), the `== "all"` checks in `render.py`, and tests
(`tests/test_parse.py`, `tests/test_models.py`, `tests/test_render.py`,
`tests/test_form_files.py`, `tests/test_js_behaviour.py`) plus the
`CLAUDE.md` description.

---

## Hide section tabs when all subsections inside are hidden — **small**

Per §Concepts → Questionnaire ("If all the questions in a section or
subsection are hidden, then that section or subsection should be hidden"),
sections rendered as tabs in `templates/page.html.j2` should disappear when
empty. Subsections already hide via `subsection.visibility_js` in
`render.py`, but sections are always shown. In `_build_section_views`,
derive a `visibility_js` per `SectionView` as the OR of its subsections'
expressions, then gate both the tab `<li>` and the `<form>` body on it via
`x-show` (or skip the markup when the expression is the always-true
sentinel). Switch `activeTab` to the first visible section in `init()` (and
on any change) if the current tab becomes hidden. Add a behaviour test in
`tests/test_js_behaviour.py` covering both directions (becomes hidden;
reappears).

---

## Remove dead `editor/` references — **small**

The `editor/` directory and `run_editor.py` shim are leftover from a removed
FastAPI/React experiment. Delete the `### Spec editor (removed)` section at
the bottom of `CLAUDE.md`, delete `run_editor.py` and the empty `editor/`
directory (check first that nothing useful remains), and grep for any other
lingering mentions (README, tests, etc.) to clean up.

---

## Add coverage configuration — **small**, **unapproved**

Add `[tool.coverage.run]` / `[tool.coverage.report]` sections to
`pyproject.toml` (excluding `tests/`), pull in `pytest-cov` as a dev
dependency, and document `uv run pytest --cov` in `CLAUDE.md` as a
diagnostic step (not a CI gate). Goal is to surface untested branches in
`models.py` / `parse.py` / `render.py` mechanically rather than reading the
spec by hand. Came up during a test-suite review on 2026-04-26.

---

## Grow the test-corpus DAG depth — **small**, **unapproved**

The real `form/properties.yaml` has no DAG deeper than 2 levels and only
one `activation: any` property (`team_sport_player`). The behaviour tests
in `tests/test_js_behaviour.py` and the integration tests in
`tests/test_form_files.py` inherit that shallow shape, so deep-cascade
regressions wouldn't surface in CI. Either grow the real form (judgment
about content) or add synthetic fixtures — at minimum a 3+ level deep DAG
and a multi-`any`-parent case — under `tests/test_parse.py` and
`tests/test_js_behaviour.py`. Came up during a test-suite review on
2026-04-26.

---

## Replace compiler-shape tests with behaviour tests where possible — **small**, **unapproved**

The substring tests in `tests/test_render.py`
(`TestCompilePropertyGetter`, `TestCompileQuestionVisibility`) and a few
in `tests/test_models.py` pin internal JS shape rather than externally
visible contracts. A refactor of `_compile_property_getter` or
`_compile_question_visibility` (extracting a helper, reordering parent
checks, swapping `===` for a strict-helper) breaks them without changing
behaviour. The mini-racer harness in `tests/js_harness.py` already covers
the same semantics. Prune the shape tests to a minimum — keep the genuine
contracts (autoescape leaks, the `"true"` always-visible sentinel) and
migrate the rest into the behaviour layer or delete if duplicated. Came
up during a test-suite review on 2026-04-26.

---

## Hypothesis property tests for cascade and aggregation — **large**, **needs design**, **unapproved**

**Spec ref:** §Concepts → Properties; §Concepts → Risks.

**Context:** The deterministic behaviour tests in
`tests/test_js_behaviour.py` cover the SPEC-stated cases for
`all_depends` / `any_depends` cascades and worst-per-dimension
aggregation, but only with hand-picked DAG shapes (≤ 2 levels) and small
condition sets. Property-based testing with Hypothesis would generate
random DAG topologies + answer states and assert invariants the
deterministic tests don't reach — particularly useful around the edges
of `_worst()` and the `null`-vs-`false` cascade rules. Came up during a
test-suite review on 2026-04-26.

**To do:**
- Decide whether to take Hypothesis as a dev dependency
  (`uv add --dev hypothesis`).
- Sketch generator strategies — likely `@st.composite` for valid DAGs
  (root + parent-pointer construction with cycle avoidance), condition
  sets, and answer maps over the generated questions.
- Pin the right invariants. Candidates:
  - `prop_X ∈ {true, false, null}` for any answer state.
  - `all`-mode: any parent `false` ⇒ child `false`; any parent `null`
    with no parent `false` and own answer `yes` ⇒ child `null`.
  - `any`-mode: all parents `false` ⇒ child `false`; some parent `true`
    ⇒ child rides own answer.
  - Worst-per-dimension monotone: adding a firing condition with
    strictly worse L/C never lowers the aggregate's level index.
- Choose where the tests live (new `tests/test_property_hypothesis.py`,
  or extend `tests/test_js_behaviour.py`).
- Pick example/seed budgets so CI runtime stays bounded.
