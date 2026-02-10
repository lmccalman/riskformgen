# Plan: Likelihood × Consequence Risk Model

## Context

The current risk model assigns a single severity level per risk (not_applicable / low / medium / high). Each rule's `to_js()` method returns a level string or null, and a worst-case-wins reduce picks the final level.

The goal is to decompose risk into two independent dimensions — **likelihood** and **consequence** — with the overall risk level computed via a configurable **risk matrix**. This is a standard risk management approach (AS/NZS ISO 31000 style) that gives assessors more granular insight into *why* a risk is rated the way it is.

## Configuration (in `config.py`)

```python
LIKELIHOODS = ("rare", "unlikely", "possible", "likely", "almost_certain")
CONSEQUENCES = ("minor", "medium", "major")
RISK_LEVELS = ("not_applicable", "low", "medium", "high")

RISK_MATRIX = {
    "rare":            {"minor": "low",    "medium": "low",    "major": "medium"},
    "unlikely":        {"minor": "low",    "medium": "medium", "major": "medium"},
    "possible":        {"minor": "medium", "medium": "medium", "major": "high"},
    "likely":          {"minor": "medium", "medium": "high",   "major": "high"},
    "almost_certain":  {"minor": "high",   "medium": "high",   "major": "high"},
}
```

All four constants are configurable — change the tuples and matrix dict to reshape the scales.

## Changes by file

### 1. `config.py` — add scales and matrix
Add `LIKELIHOODS`, `CONSEQUENCES`, `RISK_LEVELS`, `RISK_MATRIX` as shown above.

### 2. `models.py` — refactor rules and Risk dataclass

- **Delete** `RISK_LEVELS` constant (now lives in config).
- **Add** helper `_js_result(likelihood, consequence)` → JS object literal string.
- **AnyYesRule, CountYesRule, ContainsAnyRule**: replace `level: str` with `likelihood: str | None = None` and `consequence: str | None = None` (at least one required, validated in `__post_init__`). Update `to_js()` to return `{likelihood: ..., consequence: ...}` object or `null`.
- **ChoiceMapRule**: change `mapping: dict[str, str]` → `mapping: dict[str, dict[str, str]]`. Each answer maps to `{"likelihood": "...", "consequence": "..."}` (either key optional). `to_js()` normalises each entry to include both keys (missing → `null`) to avoid undefined-vs-null issues.
- **Risk**: replace `default_level: str` with `default_likelihood: str` and `default_consequence: str`.

### 3. `render.py` — pass config to templates

- `prepare_risks()`: emit `default_likelihood` / `default_consequence` instead of `default_level`.
- `render_form()`: pass `likelihoods`, `consequences`, `risk_levels`, `risk_matrix` (from config) to the template context.

### 4. `templates/page.html.j2` — rewrite Alpine.js risk getters

Replace the `_levels` severity map with:
- `_likelihoods`, `_consequences` — scale arrays (from `tojson`)
- `_risk_matrix` — nested dict (from `tojson`)
- `_worst(results, dimension, scale)` — helper that extracts a dimension from results, filters nulls, and reduces to worst-case using `scale.indexOf()` for ordering

Each risk getter becomes:
```javascript
get risk_id() {
  const results = [ /* compiled rules */ ].filter(r => r !== null);
  const likelihood = this._worst(results, 'likelihood', this._likelihoods)
    || '{{ risk.default_likelihood }}';
  const consequence = this._worst(results, 'consequence', this._consequences)
    || '{{ risk.default_consequence }}';
  return {
    likelihood, consequence,
    level: (this._risk_matrix[likelihood] || {})[consequence] || 'not_applicable'
  };
}
```

Getters now return `{likelihood, consequence, level}` objects instead of bare strings.

Update debug panel references (they'll auto-show the richer objects via `JSON.stringify`).

### 5. `templates/risk_summary.html.j2` — display both dimensions

Replace the current single "Modelled Risk" badge with three badges in a row:
- **Likelihood** — accessed via `{{ risk.id }}.likelihood`
- **Consequence** — accessed via `{{ risk.id }}.consequence`
- **Modelled Risk** — accessed via `{{ risk.id }}.level` (colour-coded as before)

Assessed risk dropdown and justification unchanged (single overall level override).
Generate dropdown options from `risk_levels` variable instead of hardcoding.

### 6. `main.py` — update example risk data

Refactor all rules in `define_risks()` to use `likelihood=`/`consequence=` instead of `level=`. Update `ChoiceMapRule` mappings to use `{"likelihood": ..., "consequence": ...}` dicts. Replace `default_level=` with `default_likelihood=`/`default_consequence=`.

### 7. `CLAUDE.md` — update architecture docs

Update rule signatures, `to_js()` contract, and "adding a risk/rule" instructions.

## Key design decisions

- **Rules can set one or both dimensions** — a rule with only `likelihood` set will not affect the consequence reduction, and vice versa. This allows modelling "this question tells us about how likely it is" separately from "this question tells us about how bad it would be".
- **`_worst` uses `scale.indexOf()`** for ordering — the position in the configured tuple defines severity. This works with any scale size without hardcoding numeric mappings.
- **Assessed risk stays as a single overall level** — the user sees the modelled L×C breakdown but makes a single assessed judgment.

## Verification

1. `uv run main.py` — build succeeds
2. `python -m http.server -d output` — serve and check:
   - Risk cards show likelihood, consequence, and overall level badges
   - Values update reactively as answers change
   - Debug panel shows `{likelihood, consequence, level}` objects
   - Assessed risk dropdown works
   - Default values produce valid matrix lookups when no rules fire
