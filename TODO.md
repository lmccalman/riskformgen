# TODO — riskformgen (outstanding AUDIT.md items)

Scope: only items from `AUDIT.md` still marked `**Status:** open`. Numbering is
preserved from `AUDIT.md` so cross-references stay stable; category headings
are kept even where they now contain only a handful of items.

Severity tags: ⚠ high, ◑ medium, · low. When an item is addressed, update its
status line in `AUDIT.md` to `resolved (YYYY-MM-DD)` and drop it from this
file.

---

## 1. Bugs and incorrect implementation

_All open bugs in this section have been resolved. See `AUDIT.md` for the
historical record._

---

## 2. Simplicity and maintainability

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

_All open items in this section have been resolved. See `AUDIT.md` for the
historical record._
