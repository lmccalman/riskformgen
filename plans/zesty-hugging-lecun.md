# Plan: Show Contributing Questions Under Each Risk

## Context

On the Risk Analysis tab, each risk card currently shows only its name, description,
and computed level badge. There's no visibility into *which* question answers are
driving the risk level. This makes it hard for users to understand why a risk is
rated the way it is, or which questions they still need to answer.

The goal is to display, under each risk card, the questions whose answers feed into
that risk's evaluation — along with the user's current answer to each.

## Approach

Show **all questions referenced** by a risk's rules (not only the ones whose rules
currently fire). This is simpler (pure build-time data, no runtime JS filtering) and
more useful — unanswered questions show "Not answered", prompting the user to go back
and fill them in.

## Changes

### 1. `models.py` — Add `referenced_question_ids()` to each rule type

Each rule dataclass gets a trivial method returning the question IDs it references:

- `AnyYesRule` / `CountYesRule` → return `self.question_ids`
- `ChoiceMapRule` / `ContainsAnyRule` → return `(self.question_id,)`

### 2. `render.py` — Enrich risk dicts with question metadata

- Change `prepare_risks(risks)` → `prepare_risks(risks, questions)`
- Build a `{question_id: question_text}` lookup from the flat question list
- For each risk, collect unique question IDs across all its rules (preserving order,
  deduplicating via `dict.fromkeys`)
- Add a `"questions": [{"id": ..., "text": ...}, ...]` list to each risk dict

### 3. `templates/page.html.j2` — Add `_formatAnswer()` helper to x-data

```javascript
_formatAnswer(val) {
  if (Array.isArray(val)) return val.length ? val.join(', ') : 'Not answered';
  return val || 'Not answered';
},
```

Follows the existing `_levels` convention for internal helpers.

### 4. `templates/risk_summary.html.j2` — Render questions under each risk card

Below the description, add a separator and a list of contributing questions.
Each shows the question text on the left and the live answer on the right.
Unanswered questions render in muted italic ("Not answered"); answered ones
in dark text. Uses the `_formatAnswer()` helper for display.

## Files touched

| File | Change |
|---|---|
| `models.py` | Add `referenced_question_ids()` to 4 rule dataclasses |
| `render.py` | Add helper + modify `prepare_risks()` signature/body + update call site |
| `templates/page.html.j2` | Add `_formatAnswer` method to x-data scope |
| `templates/risk_summary.html.j2` | Add contributing questions section to risk card |

No changes to `main.py`, `config.py`, question templates, or any other files.

## Verification

1. `uv run main.py` — builds without errors
2. `python -m http.server -d output` → open Risk Analysis tab
3. All risk cards show their contributing questions with "Not answered"
4. Fill in some answers on other tabs → answers update live on Risk Analysis
5. Check multi-select answers display as comma-separated list
6. Check `likes_swimming` appears only once under Sedentary Lifestyle (deduplication)
