# Plan: Guidance text, assessed risk & justification

## Context

The form currently shows questions without explanatory context, and risks display
only the computed (modelled) level with no way for a human assessor to record
their own judgement. We're adding three features:

1. Optional **guidance text** on questions — subtle helper text below the question
2. **Assessed risk** selector — a per-risk dropdown for the assessor's judgement,
   shown alongside the renamed "Modelled Risk" badge
3. **Justification textarea** — per-risk free-text field for the assessor's reasoning

## Changes

### 1. `models.py` — add `guidance` field

Add `guidance: str | None = None` to all four question dataclasses, placed after
`text` (for YesNo/FreeText) or after `options` (for MultipleChoice/MultipleSelect),
before `visible_when`.

No changes to `render.py` — `asdict()` automatically includes the new field.

### 2. `templates/questions/*.html.j2` — render guidance

In all four type partials, insert between `</legend>` and the first `<div>`:

```html
{% if question.guidance %}
<p class="mt-1 px-2 text-sm text-gray-500 italic">{{ question.guidance }}</p>
{% endif %}
```

Files: `yes_no.html.j2`, `free_text.html.j2`, `multiple_choice.html.j2`,
`multiple_select.html.j2`

### 3. `main.py` — populate example guidance

Add `guidance=` to 2–3 existing questions, e.g.:

- `name`: "Your full legal name, or the name you prefer to go by."
- `exercise_frequency`: "Include both structured workouts and informal activity like walking."
- `outdoor_access`: "Parks, gardens, or open areas within a 10-minute walk count."

### 4. `templates/page.html.j2` — add Alpine.js state

Add two new objects to the `x-data` scope, after `answers` and before `_levels`:

```
assessed_risks: { {% for risk in risks %}'{{ risk.id }}': ''{% if not loop.last %},{% endif %}{% endfor %} },
justifications: { {% for risk in risks %}'{{ risk.id }}': ''{% if not loop.last %},{% endif %}{% endfor %} },
```

Also add debug output for both objects in the debug panel.

### 5. `templates/risk_summary.html.j2` — redesigned risk card

Replace the current single-badge layout with:

- **Header**: risk name + description (badge removed from here)
- **Two-column row**: "Modelled Risk" (read-only badge) | "Assessed Risk" (dropdown + badge)
- **Justification**: labelled textarea bound to `justifications.{{ risk.id }}`
- **Linked answers**: unchanged

The assessed risk badge only appears once a selection is made. Uses Australian
spelling: "Modelled".

## Files modified

| File | Change |
|---|---|
| `models.py` | Add `guidance` field to 4 question dataclasses |
| `templates/questions/yes_no.html.j2` | Add guidance `<p>` |
| `templates/questions/free_text.html.j2` | Add guidance `<p>` |
| `templates/questions/multiple_choice.html.j2` | Add guidance `<p>` |
| `templates/questions/multiple_select.html.j2` | Add guidance `<p>` |
| `templates/page.html.j2` | Add `assessed_risks`, `justifications` to x-data + debug |
| `templates/risk_summary.html.j2` | Rewrite with modelled/assessed split + justification |
| `main.py` | Add guidance text to 2–3 example questions |

## Verification

1. `uv run main.py` — build succeeds
2. `python -m http.server -d output` — open in browser
3. Confirm guidance text appears below populated questions, absent on others
4. On Risk Analysis tab: modelled risk badge displays, assessed risk dropdown works,
   colour badge appears on selection, justification textarea is editable
5. Debug panel shows `assessed_risks` and `justifications` state updating
