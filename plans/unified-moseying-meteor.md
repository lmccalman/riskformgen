# Plan: Risk Model — Evaluation Engine

## Context

The form generator currently captures user answers but has no risk analysis.
We need to add a declarative risk model where risks are derived from answers
using typed rules, compiled to reactive Alpine.js at build time. This is the
core differentiator of the tool — without it, it's just a form builder.

**Design decisions made:**
- Rule combination: **worst-case wins** (all rules evaluated, highest severity returned)
- JS compilation: **Python `to_js()` methods** on each rule dataclass
- Scope: **risk evaluation only** (controls/mitigations deferred)

---

## Implementation

### 1. Add risk models to `models.py`

Add risk levels and four rule dataclasses, each with a `to_js()` method that
returns a JS expression evaluating to a risk level string or `null`:

```python
RISK_LEVELS = ("not_applicable", "low", "medium", "high")

# Rule types (all frozen dataclasses):
AnyYesRule(question_ids, level)         # any yes → level
CountYesRule(question_ids, threshold, level)  # N+ yes answers → level
ChoiceMapRule(question_id, mapping)     # choice → level via dict
ContainsAnyRule(question_id, values, level)   # multi-select contains any → level

RiskRule = AnyYesRule | CountYesRule | ChoiceMapRule | ContainsAnyRule

Risk(id, name, description, rules, default_level="not_applicable")
```

Each rule's `to_js()` returns a JS expression like:
- `AnyYesRule` → `['q1','q2'].some(id => this.answers[id] === 'yes') ? 'high' : null`
- `CountYesRule` → `[...].filter(id => this.answers[id] === 'yes').length >= 3 ? 'medium' : null`
- `ChoiceMapRule` → `{'a':'low','b':'high'}[this.answers['q1']] || null`
- `ContainsAnyRule` → `['v1'].some(v => (this.answers['q1'] || []).includes(v)) ? 'high' : null`

### 2. Update `render.py`

Add a `prepare_risks()` helper that converts Risk dataclasses to template-ready
dicts including pre-compiled JS expressions:

```python
def prepare_risks(risks: list[Risk]) -> list[dict]:
    return [{
        "id": risk.id,
        "name": risk.name,
        "description": risk.description,
        "default_level": risk.default_level,
        "rules_js": [rule.to_js() for rule in risk.rules],
    } for risk in risks]
```

Modify `render_form()` to accept and pass through risks.

### 3. Restructure `templates/page.html.j2`

- Lift `x-data` from the `<form>` to a parent `<div>` wrapping both tabs
- Add `activeTab` state and `_levels` severity lookup to `x-data`
- Add Alpine.js getters for each risk (compiled via Jinja2 loop):

```jinja
{% for risk in risks %}
get {{ risk.id }}() {
    const results = [
        {% for js in risk.rules_js %}({{ js }}),{% endfor %}
    ].filter(r => r !== null);
    if (results.length === 0) return '{{ risk.default_level }}';
    return results.reduce((w, r) => this._levels[r] > this._levels[w] ? r : w);
},
{% endfor %}
```

- Add tab navigation (Questions / Risks)
- Add risk display section using `x-show="activeTab === 'risks'"`

### 4. Create `templates/risk_summary.html.j2`

New partial for displaying a single risk: name, description, and a
colour-coded level badge that updates reactively.

Level colours (Tailwind):
- `not_applicable` → gray
- `low` → green
- `medium` → amber
- `high` → red

### 5. Update `main.py`

- Import new risk types
- Add `define_risks()` returning example risks that reference the existing questions
- Pass risks through to `render_form()`

---

## Files Modified

| File | Change |
|------|--------|
| `models.py` | Add `RISK_LEVELS`, 4 rule dataclasses, `RiskRule` union, `Risk` dataclass |
| `render.py` | Add `prepare_risks()`, update `render_form()` signature |
| `templates/page.html.j2` | Lift x-data, add tabs, add risk getters, add risk display section |
| `templates/risk_summary.html.j2` | **New** — risk card partial |
| `main.py` | Add `define_risks()`, wire through to render |

## Verification

1. `uv run main.py` — builds without errors
2. `python -m http.server -d output` — serve locally
3. Fill in questions on the Questions tab
4. Switch to Risks tab — verify levels update reactively as answers change
5. Verify worst-case-wins: when multiple rules match, the highest severity shows
