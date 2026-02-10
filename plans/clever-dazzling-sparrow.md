# Plan: Load form definitions from YAML files

## Context

The form structure (sections, questions, risks, controls) is currently defined
as Python dataclass instantiations inside `main.py`. This works, but mixes data
with build logic. Moving the definitions to YAML files gives them an input-data
flavour: easier to read, edit, and hand to non-developers — without touching the
models, renderer, or templates.

## File layout

```
form/
  sections.yaml    # sections > subsections > questions (with conditions)
  risks.yaml       # risks with rule lists
  controls.yaml    # controls with effect lists
```

## Changes

### 1. `uv add pyyaml`

### 2. `config.py` — add one line

```python
form_dir = project_root / "form"
```

### 3. `form/` — three new YAML files

**Condition syntax** (recursive, single-key-dict discriminator):

```yaml
# Simple
visible_when:
  equals: { question_id: exercise_frequency, value: Never }

# Negation
visible_when:
  not:
    equals: { question_id: exercise_frequency, value: Never }

# Logical OR
visible_when:
  any:
    - equals: { question_id: exercise_frequency, value: Rarely }
    - equals: { question_id: exercise_frequency, value: Never }
```

**Question schema** (`type` field discriminator):

```yaml
- type: yes_no | free_text | multiple_choice | multiple_select
  id: <slug>
  text: <question text>
  guidance: <optional>
  visible_when: <optional condition>
  options: [...]            # multiple_choice / multiple_select only
```

**Risk rule schema** (`type` field discriminator):

```yaml
- type: any_yes
  question_ids: [q1, q2]
  likelihood: unlikely        # at least one dimension required
- type: count_yes
  question_ids: [q1, q2]
  threshold: 2
  likelihood: possible
- type: choice_map
  question_id: exercise_frequency
  mapping:
    Daily: { likelihood: rare, consequence: minor }
    Never: { likelihood: almost_certain, consequence: major }
- type: contains_any
  question_id: active_hobbies
  values: [Swimming, Cycling]
  consequence: minor
```

**Control schema**:

```yaml
- id: outdoor_access
  name: Access to outdoor spaces
  question_id: outdoor_access
  present_value: "yes"       # quoted — YAML 1.1 parses bare yes as True
  effects:
    - risk_id: burnout_risk
      reduces_consequence: true
```

### 4. `parse.py` — new module (~120 lines)

Small, focused parse functions that convert YAML dicts to dataclass instances:

| Function | Dispatches on | Produces |
|---|---|---|
| `_ensure_str(value)` | — | Converts YAML bools (`True`→`"yes"`, `False`→`"no"`) |
| `parse_condition(data)` | Single-key dict (`equals`, `contains`, `not`, `any`, `all`) | `Condition` |
| `parse_question(data)` | `type` field | `Question` |
| `parse_subsection(data)` | — | `SubSection` |
| `parse_section(data)` | — | `Section` |
| `parse_rule(data)` | `type` field | `RiskRule` |
| `parse_risk(data)` | — | `Risk` |
| `parse_control_effect(data)` | — | `ControlEffect` |
| `parse_control(data)` | — | `Control` |
| `load_sections(path)` | — | `list[Section]` |
| `load_risks(path)` | — | `list[Risk]` |
| `load_controls(path)` | — | `list[Control]` |

Key design choices:
- `_ensure_str` applied surgically (condition values, `present_value`,
  `ContainsAnyRule.values`) — not globally, to avoid masking type errors
- YAML lists → `tuple()` at each parse boundary
- Dataclass `__post_init__` validators (e.g. "at least one dimension") still
  fire, so no duplicate validation needed

### 5. `main.py` — simplify

- Delete `define_sections()`, `define_risks()`, `define_controls()` (~270 lines)
- Replace with three `load_*()` calls in `main()`:

```python
sections = load_sections(config.form_dir / "sections.yaml")
risks = load_risks(config.form_dir / "risks.yaml")
controls = load_controls(config.form_dir / "controls.yaml")
```

- Trim imports to what's still used

### Unchanged files

- `models.py` — parser produces the same dataclass instances
- `render.py` — consumes dataclass instances as before
- All templates — no change

## YAML gotcha: `yes`/`no` as booleans

PyYAML (YAML 1.1) parses bare `yes`/`no` as `True`/`False`. The `_ensure_str`
helper in `parse.py` converts them back to `"yes"`/`"no"` where string values
are expected. Defence in depth: quote `"yes"` in the YAML files too.

## Verification

1. Before changes: `uv run main.py` and save `output/index.html`
2. After changes: `uv run main.py` and diff against saved copy
3. Output should be identical — same dataclass instances, same render pipeline
4. Serve with `python -m http.server -d output` and verify the form works
