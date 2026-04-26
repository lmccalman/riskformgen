# riskformgen spec file

!!! This is a human-edited file only: AI agents should never edit this file !!!

## Purpose

A tool to author risk assessment forms to be filled in by users and then
assessed. Define your questions, risks, and controls in YAML, then build
a self-contained static pages that run entirely in the browser, no server
required.


## Workflow

1. Risk manager defines, in YAML files:
    - risk properties that systems have or don't have, relevant to the risk assessment
    - risks that are present or absent as a function of what properties
      a system has
    - controls that modify risks' likelihood and/or consquence if they're present
    - questions that form a questionnaire for system owners, which determine
      what properies are present for a system and hence what risks and controls
      are relevant
    - The different levels of likelihood and consquence for risks, and how
      these translate into risk levels.
2. Riskformgen uses these files to compile a static website designed for the
   system owner. The site contains:
    - The questionnaire for them to fill out about their system
    - A description of the relevant risks and controls for their system that
      grows / shrinks as they fill out the form
3. System owners fill out their form, which the site provides as a JSON payload
   for them. The form saves their state locally as they go so they don't lose
   their work when they refresh the page or come back later. When ready, the system 
   owner emails the JSON to the risk manager.
5. The risk manager enters the form into another riskformgen tool that provides
   an interface for risk asssessment. The risk assessment interface allows an
   assessor to:
   - view all the risks and already-implented controls relevant to the system
     based on the questionnaire answers.
   - judge the effectiveness of the already-implemented controls
   - specify residual likelihood and consequence levels for each risk
   - require or recommend additional controls 
   - provide textual explanation for their reasoning
   - Assign the system an aggregate risk level based on their judgement and the
     residual risks of the system.
6. When completed, the riskformgen assessment tool outputs a json containing
   the information for the assessment.
7. Next, the risk manager adds both the questionnaire json and the assessment
   json to the riskformgen registry tool. This tool enables an executive or
   board member to view all systems' questionnaire answers ('system card') and
   also the risk assessments of their systems.
8. Some time later, when the system owner makes changes to their system, they
   load their old json into the questionnaire and make any updates required.
   This provides a new json. The assessor loads both the old and new json into
   the assessment tool which does a 'change assessment': explicitly looking
   only at the differences in the form and the different risks and controls
   implied. They then assess these differences.
9. New change assessment and the updates to the system card are added to the registry.


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

Properties are never automatically present: they are either absent due to the
condition of their parents or they need to be set. Example: is_hatchback is the
child of is_car -- if is_car is false, is_hatchback must be false. But if
is_car is true, the car may or may not be a hatchback so the property will be
unset unless specified directly as present or absent.

To deal with children that have multiple parent properties, properties are
either "all_depends" or "any_depends": for all_depends children, they are
absent if any single parent is absent (ie all parents must be not absent). For
any_depends children, they are only set to absent if all their parents are set
to absent (ie any parents being not absent is sufficient for its value to be
undetrmined by parent state)>

### Risks

Risks are special nodes on the DAG of properties, Like risks they are either
present, absent or unset. Similarly, they are either "all_needed" or
"any_needed" with respect to their parent relationships. However, 
UNLIKE properties, they are not set directly by the questionnare but are
completely determined by the state of their parent properties.
"all_needed" risks are:
- unset if any parent is unset
- present if all parents are present
- absent if at least one parent is absent
"any_needed" risks are:
- present if any parent is present
- unset if no parents are present but at least 1 is unset
- absent if all parents are absent

**Residual risk** (assessor input at runtime) — For every risk where inherent
level is not `not_applicable`, the assessor picks a **control effectiveness**:
`ineffective` (default — residual equals inherent), `partial` (assessor picks
residual likelihood and consequence independently; level is computed from the
matrix), or `controlled` (residual level is the dedicated `controlled` level).
A single "Residual Risk Justification" textarea captures the reasoning. 

### Controls

Controls are a special kind of property: it has effects listing which risks it
addresses. Otherwise it is identical in behaviour to a plain property. Controls
do **not** automatically reduce risk — the assessor judges their collective
effectiveness per risk at assessment time (see "Residual risk" below).


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

Questions: These are binary. Each question sets one or more properties.
Question visibility is derived automatically from the property DAG: Only
questions which influence unset properties should be shown.

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
