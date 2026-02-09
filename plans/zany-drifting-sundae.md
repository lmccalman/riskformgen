# Plan: Conditional Visibility for Questions and SubSections

## Context

Form authors need to show/hide individual questions or entire subsections based
on the user's answers to other questions. For example: "if the user answers 'yes'
to question 1, hide question 2" or "only show the 'Indoor Interests' subsection
when exercise frequency is 'Rarely' or 'Never'."

The existing risk rule system already establishes a pattern for this: frozen
dataclasses with `to_js()` methods that compile Python expressions into JS at
build time. Conditions follow the same pattern, but produce boolean JS
expressions for use in Alpine.js `x-show` attributes.

## Design: Condition Dataclasses

Five new frozen dataclasses in `models.py`, each with a `to_js() -> str` method:

| Class | Purpose | Example JS output |
|-------|---------|-------------------|
| `Equals(question_id, value)` | True when answer equals value | `answers["q1"] === "yes"` |
| `Contains(question_id, value)` | True when multi-select includes value | `(answers["q1"] \|\| []).includes("opt")` |
| `All(conditions)` | Logical AND | `(expr1) && (expr2)` |
| `Any(conditions)` | Logical OR | `(expr1) \|\| (expr2)` |
| `Not(condition)` | Negation | `!(expr)` |

Union type: `Condition = Equals | Contains | All | Any | Not`

Conditions use `answers[...]` (no `this.` prefix) since they're evaluated in
`x-show` context where Alpine.js provides direct property access.

## Design: `visible_when` Field

Add `visible_when: Condition | None = None` to all four question types and to
`SubSection`. Hidden elements retain their answer state (matching existing
`x-show` tab behaviour — simple, no surprise data loss).

## Changes by File

### 1. `models.py`

- Add `from __future__ import annotations` (enables forward references for
  recursive `Condition` type)
- Add new "Visibility conditions" section with the five condition classes and
  `Condition` union — placed before the Questions section (dependency order)
- Add `visible_when: Condition | None = None` field to: `YesNoQuestion`,
  `FreeTextQuestion`, `MultipleChoiceQuestion`, `MultipleSelectQuestion`,
  `SubSection` — as the last `init=True` field on each

### 2. `render.py`

- Extract `_prepare_question(q)` helper: calls `asdict(q)`, pops
  `visible_when`, adds `visible_when_js` key (the compiled JS string) when
  condition is present
- Extract `_prepare_subsection(sub)` helper: builds subsection dict, adds
  `visible_when_js` when condition is present
- Refactor `prepare_sections()` to use `_prepare_subsection`
- Update `render_form()` to use `_prepare_question` for the flattened question
  list

### 3. `templates/question.html.j2`

Wrap the include in a conditional `x-show` div:

```jinja2
{% if question.visible_when_js is defined %}
<div x-show="{{ question.visible_when_js }}">
{% endif %}
{% include "questions/" ~ question.type ~ ".html.j2" %}
{% if question.visible_when_js is defined %}
</div>
{% endif %}
```

### 4. `templates/subsection.html.j2`

Add `x-show` directly to the existing root `<div>` (no extra wrapper):

```jinja2
<div class="space-y-4"{% if subsection.visible_when_js is defined %} x-show="{{ subsection.visible_when_js }}"{% endif %}>
```

### 5. `main.py`

- Import condition classes (`Equals`, `Not`, `Any`, etc.)
- Add example `visible_when` usage to at least one question and one subsection
  in `define_sections()`

## Verification

1. `uv run main.py` — build succeeds
2. `python -m http.server -d output` — serve and open in browser
3. Verify: conditional questions/subsections appear/disappear reactively as
   triggering answers change
4. Verify: toggling visibility off and back on retains previously entered answers
5. Verify: risk levels still evaluate correctly for hidden questions
