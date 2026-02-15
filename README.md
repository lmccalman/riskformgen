# riskformgen

A static-page generator for interactive risk assessment forms. Define your
questions, risks, and controls in YAML, then build a self-contained HTML page
that runs entirely in the browser — no server required.

Built with Jinja2 templates, [Bulma](https://bulma.io/), and
[Alpine.js](https://alpinejs.dev/) for client-side interactivity.

## Quick start

```bash
# Install dependencies (requires uv and Python 3.13+)
uv sync

# Build the static site into output/
uv run main.py

# Serve locally and open http://localhost:8000
python -m http.server -d output
```

The generated page lives in `output/index.html` with its CSS and JS assets.
Users interact with tabbed, multi-section forms, see their risk levels update
in real time, and can save/load their responses as JSON.

## Defining a form

Forms are defined in three YAML files under `form/`:

| File | Defines |
|---|---|
| `sections.yaml` | Sections, subsections, and questions |
| `risks.yaml` | Risks and the rules that assess them |
| `controls.yaml` | Controls (safeguards) that reduce risk |

The YAML files themselves contain inline comments documenting each feature — they
serve as living schema documentation.

### sections.yaml

The file is a list of **sections**, each rendered as a tab. Sections contain
**subsections** (visual groupings), which contain **questions**.

```yaml
- id: safety            # URL-safe slug, used as Alpine.js tab ID
  title: Safety         # Display name on the tab
  description: "..."    # Shown below the tab heading
  subsections:
    - title: General
      description: "..."
      questions:
        - type: yes_no
          id: has_plan          # Unique across all sections
          text: Do you have a safety plan?
          guidance: "Optional help text shown below the question."
```

#### Question types

| Type | Fields | Answer format |
|---|---|---|
| `yes_no` | `id`, `text` | `"yes"` or `"no"` |
| `free_text` | `id`, `text` | Free-form string |
| `multiple_choice` | `id`, `text`, `options` | One of the option strings |
| `multiple_select` | `id`, `text`, `options` | Array of selected option strings |

All question types accept optional `guidance` (help text) and `visible_when`
(conditional visibility — see below).

#### Visibility conditions

Questions and subsections can be shown or hidden based on other answers using
`visible_when`. Conditions can be nested arbitrarily.

| Condition | Syntax | True when |
|---|---|---|
| `equals` | `equals: { question_id: q1, value: yes }` | Answer to `q1` equals `"yes"` |
| `contains` | `contains: { question_id: q1, value: Swimming }` | Multi-select `q1` includes `"Swimming"` |
| `not` | `not: { equals: ... }` | Inner condition is false |
| `any` | `any: [cond1, cond2, ...]` | At least one child is true (OR) |
| `all` | `all: [cond1, cond2, ...]` | All children are true (AND) |

Example — show a subsection only when the user exercises rarely or never:

```yaml
visible_when:
  any:
    - equals: { question_id: exercise_frequency, value: Rarely }
    - equals: { question_id: exercise_frequency, value: Never }
```

### risks.yaml

Each risk is assessed on two independent dimensions — **likelihood** and
**consequence** — using a configurable set of rules. The overall risk level is
looked up from a matrix (see [Risk model](#risk-model) below).

```yaml
- id: sedentary_risk
  name: Sedentary Lifestyle
  description: Risk of a sedentary lifestyle based on activity levels.
  default_likelihood: likely       # Fallback when no rules fire
  default_consequence: medium      # (defaults: rare / minor if omitted)
  rules:
    - type: choice_map
      question_id: exercise_frequency
      mapping:
        Daily: { likelihood: rare, consequence: minor }
        Weekly: { likelihood: possible }    # Only sets likelihood
        Never: { likelihood: almost_certain, consequence: major }
```

#### Rule types

| Type | Key fields | Fires when |
|---|---|---|
| `any_yes` | `question_ids`, `likelihood`/`consequence` | Any listed yes/no question is `"yes"` |
| `count_yes` | `question_ids`, `threshold`, `likelihood`/`consequence` | At least `threshold` questions are `"yes"` |
| `choice_map` | `question_id`, `mapping` | Maps a multiple-choice answer to `{likelihood, consequence}` |
| `contains_any` | `question_id`, `values`, `likelihood`/`consequence` | Multi-select answer contains any of the listed values |

Every rule except `choice_map` requires at least one of `likelihood` or
`consequence`. A rule that only sets one dimension won't affect the other.

When multiple rules fire, the **worst case wins** per dimension — the highest
likelihood and highest consequence across all fired rules are used together to
look up the overall risk level from the matrix.

### controls.yaml

Controls are safeguards detected from question answers. When present, they
reduce the assessed likelihood or consequence of linked risks by one step.

```yaml
- id: safety_plan
  name: Has a safety plan
  question_id: has_plan       # The question that determines presence
  present_value: "yes"        # Answer value that means the control is present
  effects:
    - risk_id: sedentary_risk
      reduces_likelihood: true
    - risk_id: burnout_risk
      reduces_consequence: true
```

For multi-select questions, the control is present if `present_value` is among
the selected options.

## Risk model

Risk is decomposed into **likelihood** and **consequence**, with the overall
level computed via a 5×3 matrix (ISO 31000 style).

**Likelihood scale** (ascending severity):
`rare` → `unlikely` → `possible` → `likely` → `almost_certain`

**Consequence scale** (ascending severity):
`minor` → `medium` → `major`

**Risk matrix:**

| | Minor | Medium | Major |
|---|---|---|---|
| **Rare** | Low | Low | Medium |
| **Unlikely** | Low | Medium | Medium |
| **Possible** | Medium | Medium | High |
| **Likely** | Medium | High | High |
| **Almost certain** | High | High | High |

Scales and the matrix are defined in `config.py`.

## Worked example

Here's a minimal self-contained form with two questions, one risk, and one
control, showing how the pieces connect.

**sections.yaml:**

```yaml
- id: workplace
  title: Workplace
  description: Your work environment.
  subsections:
    - title: Setup
      description: How your workspace is arranged.
      questions:
        - type: yes_no
          id: has_ergonomic_chair
          text: Do you use an ergonomic chair?
        - type: multiple_choice
          id: hours_sitting
          text: How many hours per day do you sit?
          options: ["< 4", "4–8", "> 8"]
```

**risks.yaml:**

```yaml
- id: back_pain_risk
  name: Back Pain
  description: Risk of back pain from prolonged sitting.
  default_likelihood: possible
  default_consequence: medium
  rules:
    - type: choice_map
      question_id: hours_sitting
      mapping:
        "< 4": { likelihood: unlikely, consequence: minor }
        "4–8": { likelihood: possible, consequence: medium }
        "> 8": { likelihood: likely, consequence: major }
    - type: any_yes
      question_ids: [has_ergonomic_chair]
      likelihood: unlikely       # Ergonomic chair reduces likelihood
```

**controls.yaml:**

```yaml
- id: ergonomic_chair
  name: Ergonomic chair
  question_id: has_ergonomic_chair
  present_value: "yes"
  effects:
    - risk_id: back_pain_risk
      reduces_consequence: true   # Drops consequence by one step
```

How it works: if the user sits > 8 hours (likelihood: `likely`, consequence:
`major`) but has an ergonomic chair, the `any_yes` rule also fires with
likelihood `unlikely`. The worst-case-wins logic picks `likely` for likelihood
(worst of `likely` and `unlikely`) and `major` for consequence. The control then
reduces consequence by one step to `medium`, giving a final matrix lookup of
`likely` × `medium` = **High**.

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check .           # Check for lint errors
uv run ruff check --fix .     # Auto-fix lint errors
uv run ruff format --check .  # Check formatting
uv run ruff format .          # Auto-format

# Type check
uv run basedpyright

# Build
uv run main.py
```

Run all four checks before considering a change complete:

```bash
uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run pytest tests/ -v
```
