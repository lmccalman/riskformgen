# riskformgen spec file

!!! AI agents should never edit this file without permission!!!

## Purpose

A tool to author risk assessment forms to be filled in by users and then
assessed. Define your questions, risks, and controls in YAML, then build
a self-contained static pages that run entirely in the browser, no server
required.


## Workflow

riskformgen produces a single static site with three distinct *views* — the
questionnaire, the assessment, and the registry — each playing a different
role for a different persona. They share a build pipeline, theme, and form
definitions, but the user-facing surface of each is visually separated so the
persona always knows which view they are in.

1. Risk manager defines, in YAML files:
    - risk properties that systems have or don't have, relevant to the risk assessment
    - risks expressed as conditions over those properties, with associated
      likelihood and consequence (see §Concepts → Risks)
    - controls that the assessor can use as evidence when judging residual
      risk
    - questions that form a questionnaire for system owners, which determine
      what properties hold for a system and hence what risks and controls
      are relevant
    - the levels of likelihood and consequence and the matrix that maps
      `(likelihood, consequence)` pairs to risk levels.
2. Riskformgen uses these files to compile a static site. The same build
   produces three views:
    - **Questionnaire view** — for the system owner to fill out, with the
      relevant risks and controls growing/shrinking as they answer.
    - **Assessment view** — for the assessor, presenting the system owner's
      answers, the inherent risks they imply, and inputs for residual risk.
    - **Registry view** — for executives, listing all systems' completed
      questionnaires and assessments.
3. System owners open the questionnaire view, fill out the form, and export
   their answers as a JSON payload. The site saves their state locally as they
   go so they don't lose their work when they refresh the page or come back
   later. When ready, the system owner emails the JSON to the risk manager.
4. The risk manager opens the assessment view of the same site and loads the
   questionnaire JSON. The assessment view allows an assessor to:
   - view all the risks and already-implemented controls relevant to the
     system based on the questionnaire answers.
   - judge the effectiveness of the already-implemented controls
   - specify residual likelihood and consequence levels for each risk
   - mandate or recommend additional controls
   - provide textual explanation for their reasoning
   - assign the system an aggregate risk level based on their judgement and
     the residual risks of the system.
5. When completed, the assessment view exports an assessment JSON.
6. The risk manager adds both the questionnaire JSON and the assessment JSON
   to the registry view, which lets executives or board members browse all
   systems' questionnaire answers ('system card') and the risk assessments of
   their systems.
7. Some time later, when the system owner makes changes to their system, they
   load their old JSON into the questionnaire view and update it. This
   produces a new JSON. The assessor loads both the old and new JSON into the
   assessment view, which does a 'change assessment': explicitly looking only
   at the differences in the form and the different risks and controls
   implied. They then assess these differences.
8. The new change assessment and updates to the system card are added to the
   registry.


## Concepts

These are not definitions, but rather, how these (well-known) concepts are
being applied in the project.

### System
This is the entity being assessed for risk.

### Properties

Systems have DAGs of properties, which are modelled with three
states: present (the system under study has that property), absent (it does
not) or unset (the user has yet to provide the information needed to
determine). 

For nodes with a single parent, if the parent is absent then
the child and all its decendents are automatically absent. If the parent is
present, the value of the child is unset unless specified by the user directly.

Properties with an attached question are never automatically present: they are
either absent due to the condition of their parents, or they need to be answered
by the user. Example: is_hatchback is the
child of is_car -- if is_car is false, is_hatchback must be false. But if
is_car is true, the car may or may not be a hatchback so the property will be
unset unless specified directly as present or absent.

Some properties name a pure aggregation over their parents and have no
question attached. Such properties are *derived*: they are automatically
present when their parent activation is satisfied (and absent when forced
absent by the cascade), with no separate user input. This lets a property
express e.g. `well_rounded_fitness = does_strength_training AND
does_cardio_training` directly in the DAG, without forcing the user to
answer the conjunction.

To deal with children that have multiple parent properties, properties are
either "all_depends" or "any_depends": for all_depends children, they are
absent if any single parent is absent (ie all parents must be not absent). For
any_depends children, they are only set to absent if all their parents are set
to absent (ie any parents being not absent is sufficient for its value to be
undetrmined by parent state)>

### Risks

Risks are nodes attached to the property DAG. Unlike properties, they are not
present/absent/unset — they have a **level** drawn from a defined scale, and
that level is computed automatically from property state.

#### Likelihood, consequence, and the matrix

Three ordered scales are defined in a configuration file:

- a **likelihood** scale (an ordered, finite list of severity levels)
- a **consequence** scale (an ordered, finite list of severity levels)
- a **risk-level** scale (an ordered, finite list of risk levels)

A **risk matrix**, also configured, maps each `(likelihood, consequence)`
pair to a risk level. Two distinguished risk levels do not appear in the
matrix and are reached only via the paths described below: `not_applicable`
(no condition fires) and `controlled` (the residual-risk path).

#### Conditions

A risk owns a list of **conditions**. Each condition is a triple:

    (property, likelihood, consequence)

A condition **fires** when its `property` is `true`. (Only `true` satisfies;
an unset/`null` property never does — unanswered questions cannot push a
risk's level up prematurely.)

This is intentionally the simplest possible shape: each condition contributes
one `(L, C)` pair when one property holds. Richer logic — "this risk fires
only when properties A *and* B both hold" — is expressed by introducing an
intermediate property in the property DAG (with `activation: "all"` over
A and B) and then writing a condition against that intermediate property.
The DAG is the place where conjunctions live; risks just enumerate the
single-property triggers that contribute to them.

#### Aggregating firing conditions: worst-case wins, per dimension

Given the set of conditions that fire for a risk:

- The risk's **likelihood** is the highest-severity likelihood among them
  (using the configured likelihood ordering as severity).
- The risk's **consequence** is the highest-severity consequence among them
  (using the configured consequence ordering as severity).
- The two are picked **independently** — the worst likelihood and the worst
  consequence may come from different firing conditions, not necessarily as
  a paired `(L, C)` tuple.

#### Computing the inherent level

- If no conditions fire → `level = not_applicable`.
- Otherwise → `level = matrix(likelihood, consequence)`.

This is the **inherent** risk level — the level before considering any
controls.

#### Residual risk

For each risk where the *inherent* level is not `not_applicable`, the
assessor picks a `control_effectiveness`:

- `ineffective` (default) — residual likelihood, consequence, and level
  equal the inherent ones.
- `partial` — the assessor picks residual likelihood and consequence
  independently from the configured scales; the residual level is then
  derived from the risk matrix.
- `controlled` — the residual level is the dedicated `controlled` level
  (likelihood and consequence are kept from inherent for display).

A single "Residual Risk Justification" textarea per risk captures the
reasoning behind the chosen effectiveness and any L/C overrides.

### Controls

A control is bound to a single property and is *present* when that property
is `true`. Each control declares the risks it addresses via its `effects`
list. Because the control's presence simply tracks its property, DAG
behaviour is inherited from the property — the control concept itself does
not introduce new DAG nodes.

Controls do **not** automatically reduce risk. The assessor judges their
collective effectiveness per risk at assessment time (see "Residual risk"
above).

#### Mandating controls

For any risk where a linked control is *not* currently present, the
assessment view surfaces, on the risk card:

- a **"mandate this control"** checkbox (per risk, per control), and
- a free-text **"how should it be implemented"** comment (per risk, per
  control).

Both pieces of state are included in the assessment JSON export, so the
registry shows both the assessor's appraisal of existing controls and any
controls they have required or recommended for the system going forward.

### Details

Details are contextual topics defined alongside properties, risks, and
controls. Each detail has an `id`, a `description`, and a list of
`properties` it relates to. A detail's value is free text, supplied by the
system owner via a *detail question* (see Questionnaire).

That free text is then surfaced in a "Context" panel on any risk card whose
conditions touch one of the detail's properties. This means contextual notes
follow the property graph rather than being hard-wired to a specific risk:
notes the system owner provides about, say, a particular data source or a
third-party integration appear automatically on every risk that depends on
the same properties.


### Aggregate residual risk
The risk assessor assigns an overall risk level to the system based on their
judgement of the set of residual risk levels of the risks after all controls
are applied. This is not nessecarily the maximum of the individual risk levels.

### Questionnaire

The questionnaire is divided into sections, that correspond to different
aspects of the system. Each section is further divided into subsections, that
group related questions together. Sections and subsections have explanatory
text. If all the questions in a section or subsection are hidden, then that
section or subsection should be hidden.

Questions come in two types:

- **Binary** questions present yes/no inputs and set one or more properties
  (yes makes them `true`).
- **Detail** questions present a free-text input that writes into a
  `Detail` referenced by `detail_id`. They do not set property state; the
  text they capture is shown back on risk cards via the linked detail.

Question visibility is derived automatically from the property DAG: a
question is shown when the parents of at least one of its target properties
are satisfied (i.e. that property is *reachable*). Once shown, a question
stays visible — the user can change their answer at any time. For detail
questions the same rule applies, using the referenced detail's properties.

## Personas

Risk manager: the person running the riskformgen tool, deciding the risks and
controls that are relevant and maintaining the register.
System owner: the person filling out the questionnaire and in charge of the
system under study
Assessor: The person who conducts a risk asssesment of a system based on the
answers provided by the system owner to the questionnaire
Executive: The person who desires oversight of all the systems and assessments
done by the tool.

## Key design goals and contraints

- Code is Python, as simple as possible with the goal of maximum
  introspectability and maintainability. Limited amounts of JS or templating
  langugaes okay but only if it results in simpler code.
- The golden state of answered questionnaires and system assessments should be
  the registry, which should be git version-controlled.
- Builds should always result in a static site that can be deployed on github
  pages or similar -- client-side JS is fine but there can't be a server to
  call back to -- no dynamically generated content.
- The configuration of the builds, however, can use dynamic web interfaces if
  needed -- for example to help risk managers create JSON files
- Dependencies to non-python libraries should be kept to a minimum, though are
  okay if they enable important functionality. If practical, they should be
  optional (for example, like Playwright for frontend and end-to-end testing.
- Risks, controls, questionnaire questions and properties must be able to
  evolve:
  - a user should be able to come back to a half-completed form with their json
    and fill it out, even if the questionnaire has changed since they did their
    export.
  - The registry should be able to properly render and handle the evolution of
    the properties risk etc over time -- older system assessments and
    questiionnaire answers should not break.
  - It's okay to require constraints on the risk managers to make this
    versioning simpler to implement in the code.
