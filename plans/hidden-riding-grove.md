# Plan: Add New Question Types

## Context

The form generator currently supports only `YesNoQuestion`. We need three new question types to make forms useful for real-world data collection: free text input, single-select from multiple options, and multi-select from multiple options.

## Approach

### 1. Add a `type` discriminator and new dataclasses (`models.py`)

Add a `type: str` field with a class-specific default to every question dataclass. This flows through `asdict()` into template context naturally, letting templates branch on `question.type`.

New dataclasses:
- **`FreeTextQuestion`** — `id`, `text`, `type="free_text"`
- **`MultipleChoiceQuestion`** — `id`, `text`, `options: tuple[str, ...]`, `type="multiple_choice"`
- **`MultipleSelectQuestion`** — `id`, `text`, `options: tuple[str, ...]`, `type="multiple_select"`

Add a `Question` union type alias for use in type hints.

### 2. Split templates into per-type partials

Replace the monolithic `question.html.j2` with a one-line dispatcher:

```
templates/
  question.html.j2                    # {% include "questions/" ~ question.type ~ ".html.j2" %}
  questions/
    yes_no.html.j2                    # existing markup, moved here
    free_text.html.j2                 # <textarea> with x-model
    multiple_choice.html.j2           # radio loop over question.options
    multiple_select.html.j2           # checkbox loop over question.options
```

### 3. Update Alpine.js initial state (`page.html.j2`)

`multiple_select` answers need `[]` (array) instead of `''` (string) so Alpine.js checkbox binding works correctly. Add a conditional in the `x-data` initialiser.

### 4. Update type hints (`render.py`)

Change `YesNoQuestion` → `Question` in the import and `render_form()` signature.

### 5. Add example questions (`main.py`)

Update imports and add one example of each new type to `define_questions()`.

## Files to modify

| File | Change |
|---|---|
| `models.py` | Add `type` field to `YesNoQuestion`; add 3 new dataclasses; add `Question` alias |
| `render.py` | Import and type hint: `YesNoQuestion` → `Question` |
| `main.py` | New imports, `Question` type hints, example questions |
| `templates/page.html.j2` | Conditional default (`[]` vs `''`) in `x-data` |
| `templates/question.html.j2` | Replace with single-line type dispatcher |
| `templates/questions/yes_no.html.j2` | **New** — existing yes/no markup moved here |
| `templates/questions/free_text.html.j2` | **New** — textarea partial |
| `templates/questions/multiple_choice.html.j2` | **New** — radio button loop |
| `templates/questions/multiple_select.html.j2` | **New** — checkbox loop |

## Verification

```bash
uv run main.py                          # build
python -m http.server -d output         # serve
```

Then open `http://localhost:8000` and verify:
- Yes/no questions still render and work
- Free text textarea accepts input and updates debug JSON
- Multiple choice radios allow exactly one selection
- Multiple select checkboxes allow multiple selections, debug JSON shows an array
