# Plan: Risk Controls (visual indicators)

## Context

The risk panel currently shows modelled risk (computed from rules) and lets the assessor enter an assessed risk with justification. There's no way to show what **controls** (mitigations, safeguards) are in place that might influence the assessor's judgement. Controls should appear as visual indicators between the modelled risk and the assessed risk — showing whether each control is present or absent, and which dimension(s) it would reduce — without modifying the computed risk.

## Data model

### New dataclasses in `models.py`

```python
@dataclass(frozen=True)
class ControlEffect:
    risk_id: str
    reduces_likelihood: bool = False
    reduces_consequence: bool = False

@dataclass(frozen=True)
class Control:
    id: str
    name: str
    question_id: str          # which question determines presence
    present_value: str        # answer value that means "present" (e.g. "yes")
    effects: tuple[ControlEffect, ...]

    def presence_js(self) -> str:
        """JS expression evaluating to true/false for control presence."""
        # Handles both string answers (===) and array answers (includes)
```

- One question per control (single `question_id` + `present_value`)
- Effects are a tuple of `ControlEffect`, each linking to a `risk_id` with dimension flags
- `presence_js()` follows the existing `to_js()` pattern on rule dataclasses
- Validation: at least one of `reduces_likelihood` / `reduces_consequence` must be true

## Files to modify

### 1. `models.py` — add `ControlEffect` and `Control` dataclasses
- Add after the `Risk` dataclass
- `Control.presence_js()` compiles to: `Array.isArray(a[qid]) ? a[qid].includes(val) : a[qid] === val`
- Add `__post_init__` validation on `ControlEffect` (at least one dimension true)

### 2. `render.py` — add `prepare_controls()`, update `render_form()`
- `prepare_controls(controls)` returns:
  - `control_getters`: list of `{id, js}` dicts for page template x-data getters
  - Attaches a `controls` list to each risk dict (grouped by `risk_id`)
- `render_form()` gains a `controls: list[Control]` parameter
- Pass `control_getters` to the template context

### 3. `templates/page.html.j2` — add control getters to x-data
- Add a getter for each control in the Alpine.js scope:
  ```js
  get ctrl_id() { return <presence_js>; },
  ```
- These are simple boolean getters (no reduction logic needed)

### 4. `templates/risk_summary.html.j2` — show controls between modelled and assessed risk
- New section: "Controls" (only shown if the risk has controls)
- For each control affecting this risk, one row showing:
  - Present/absent icon (bound to the control getter via `:class` or `x-show`)
  - Control name
  - Dimension indicator: "↓ Likelihood", "↓ Consequence", or "↓ Likelihood & Consequence"
- Green styling when present, muted/grey when absent

### 5. `main.py` — add `define_controls()`, wire into build
- New `define_controls()` function returning example controls
- Pass controls to `render_form()` alongside sections and risks
- Update build summary print to include control count

## Verification
1. `uv run main.py` — builds without errors
2. `python -m http.server -d output` — serve and check:
   - Controls appear under each risk they affect
   - Toggling the linked question answer updates presence indicator reactively
   - Dimension labels (↓ Likelihood, etc.) display correctly
   - Controls shown between modelled risk and assessed risk sections
