# Plan: Form Sections and Sub-sections

## Context

Currently all questions live in a single "Questions" tab alongside a "Risks" tab.
As forms grow, this becomes an undifferentiated wall of questions. We need:

1. **Major sections** — each rendered as its own tab (visually distinct from the Risk Analysis tab)
2. **Sub-sections** — visual groupings within each section tab, with headings

## Data Model (`models.py`)

Add two new frozen dataclasses after the `Question` union:

```python
@dataclass(frozen=True)
class SubSection:
    title: str
    questions: tuple[Question, ...]

@dataclass(frozen=True)
class Section:
    id: str        # slug for Alpine.js tab switching
    title: str     # display name on the tab
    subsections: tuple[SubSection, ...]
```

Add a helper to flatten sections back to a question list (needed for `answers` init and the debug panel):

```python
def all_questions(sections: Sequence[Section]) -> list[Question]:
    return [q for s in sections for sub in s.subsections for q in sub.questions]
```

## Rendering (`render.py`)

- Add `prepare_sections()` to convert `Section` dataclasses to template dicts (nested: section → subsections → question dicts).
- Change `render_form(questions, risks)` → `render_form(sections, risks)`.
- Pass **both** `sections` (for tab/subsection rendering) and the flat `questions` list (for `answers` init) to the template.

## Template Changes

### `page.html.j2`

**`x-data` block** — minimal change:
- `activeTab` initialises to `'{{ sections[0].id }}'` instead of `'questions'`
- `answers` init and risk getters stay exactly the same (they use the flat `questions` list)

**Tab bar** — replace two hardcoded buttons with:
- A Jinja2 loop over `sections` generating indigo-accented tabs (left-aligned)
- The "Risk Analysis" tab pushed right via `ml-auto`, using red accent colours for visual separation

**Section content panels** — replace the single `<form>` with a loop:
```
{% for section in sections %}
<form x-show="activeTab === '{{ section.id }}'" class="space-y-8">
  {% for subsection in section.subsections %}
  {% include "subsection.html.j2" %}
  {% endfor %}
</form>
{% endfor %}
```

**Debug panel** — move outside the section forms, visible on any section tab (`x-show="activeTab !== 'risks'"`).

### New: `templates/subsection.html.j2`

Renders a sub-section heading + its questions:
```
<div class="space-y-4">
  <h2 class="text-lg font-semibold ...">{{ subsection.title }}</h2>
  {% for question in subsection.questions %}
  {% include "question.html.j2" %}
  {% endfor %}
</div>
```

The `space-y-8` on the parent form gives wider gaps between sub-sections; `space-y-4` within keeps questions tight.

### No changes to

- `question.html.j2` (dispatcher)
- `questions/*.html.j2` (per-type partials)
- `risk_summary.html.j2`

## `main.py`

Replace `define_questions()` with `define_sections()` returning a `list[Section]`. Update `write_html()` and `main()` accordingly.

### Example form content

Three sections with sub-sections to demonstrate the features:

**Section: "Personal" (`personal`)**
- Sub-section "About You" — name (free text), favourite memory (free text)
- Sub-section "Preferences" — favourite season (multiple choice), morning person (yes/no)

**Section: "Activities" (`activities`)**
- Sub-section "Exercise & Sport" — likes swimming (yes/no), exercise frequency (multiple choice), active hobbies (multiple select)
- Sub-section "Indoor Interests" — enjoys coding (yes/no), indoor hobbies (multiple select)

**Section: "Environment" (`environment`)**
- Sub-section "Living Situation" — commute method (multiple choice), outdoor access (yes/no)
- Sub-section "Social" — social frequency (multiple choice), group activities (multiple select)

Existing risks and rules will be updated to reference the new question IDs.

## Files Modified

| File | Change |
|------|--------|
| `models.py` | Add `SubSection`, `Section`, `all_questions()` |
| `render.py` | Add `prepare_sections()`; change `render_form()` signature |
| `templates/page.html.j2` | Dynamic tabs, looped section panels, relocated debug panel |
| `templates/subsection.html.j2` | **New** — sub-section partial |
| `main.py` | `define_sections()` replaces `define_questions()`; richer example data |
| `CLAUDE.md` | Update architecture docs to reflect sections |

## Verification

1. `uv run main.py` — builds without errors
2. `python -m http.server -d output` — serve and check:
   - Multiple section tabs appear, Risk Analysis tab is visually separated (right-aligned, red accent)
   - Clicking tabs switches content
   - Sub-sections show headings with grouped questions
   - Answering questions across sections updates risks correctly
   - Debug panel shows all answers regardless of active section tab
