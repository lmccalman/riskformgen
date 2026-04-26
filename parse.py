# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false
"""Parse YAML form definitions into model dataclass instances."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

import yaml

import config
from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Detail,
    DetailQuestion,
    Property,
    Question,
    Risk,
    Section,
    SubSection,
    all_questions,
)

# Type aliases for readability
type YamlDict = dict[str, Any]


# ---------------------------------------------------------------------------
# Unknown-key guard
# ---------------------------------------------------------------------------
#
# YAML files are hand-edited; without this check a typo like `guidelines:`
# instead of `guidance:` would be silently dropped and produce a wrong build.


def _check_unknown_keys(data: YamlDict, allowed: set[str], context: str) -> None:
    extras = set(data.keys()) - allowed
    if extras:
        raise ValueError(
            f"Unknown key(s) in {context}: {sorted(extras)}. Allowed: {sorted(allowed)}"
        )


# ---------------------------------------------------------------------------
# Combinator validation
# ---------------------------------------------------------------------------
#
# `Property.activation` takes the boolean combinators "all" / "any". Validating
# here — rather than relying on downstream code silently treating unknown
# values as "any" (see render.py `== "all"` checks) — catches YAML typos like
# `activation: al` at parse time.


def _parse_combinator(value: object, *, field_name: str, owner: str) -> Literal["all", "any"]:
    if value not in ("all", "any"):
        raise ValueError(f"Invalid {field_name} on {owner}: {value!r} — must be 'all' or 'any'")
    return cast(Literal["all", "any"], value)


# ---------------------------------------------------------------------------
# ID validation
# ---------------------------------------------------------------------------
#
# IDs are emitted directly into generated JavaScript (see templates/app.js.j2
# and render.py). Property and control getters are prefixed (`prop_*`,
# `ctrl_*`), but risk getters are unprefixed (`get {risk.id}()`), and all IDs
# appear as object keys in dot-accessed expressions like `answers.{id}`.
# Invalid identifiers or reserved-name collisions cause silent JS runtime
# errors, so we reject them at parse time.

_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ECMAScript reserved words that would produce syntax errors if used as
# identifiers (getter names) or dot-accessed property keys emitted verbatim
# into JS source.
_JS_RESERVED: frozenset[str] = frozenset(
    {
        "break", "case", "catch", "class", "const", "continue", "debugger",
        "default", "delete", "do", "else", "enum", "export", "extends",
        "false", "finally", "for", "function", "if", "import", "in",
        "instanceof", "new", "null", "return", "super", "switch", "this",
        "throw", "true", "try", "typeof", "var", "void", "while", "with",
        "yield", "let", "static",
    }
)  # fmt: skip

# Top-level names on the Alpine scope declared in templates/app.js.j2. Risk
# getters are emitted unprefixed, so a risk whose id equals one of these
# would silently shadow the state field / helper.
_ALPINE_RESERVED: frozenset[str] = frozenset(
    {
        # $persist-backed state fields
        "activeTab",
        "answers",
        "details",
        "control_effectiveness",
        "residual_likelihood",
        "residual_consequence",
        "justifications",
        "mandated_controls",
        "mandated_comments",
        # Internal data arrays/maps
        "_questionIds",
        "_detailIds",
        "_propertyIds",
        "_riskIds",
        "_controlIds",
        "_riskConditions",
        "_likelihoods",
        "_consequences",
        "_risk_matrix",
        # Helper methods
        "_worst",
        "_downloadJson",
        "_importJson",
        "_propertySnapshot",
        "_inherentSnapshot",
        "clearAnswers",
        "clearAssessment",
        "exportAnswers",
        "importAnswers",
        "exportAssessment",
        "importAssessment",
    }
)


def _validate_id(value: object, *, kind: str, owner: str | None = None) -> None:
    """Reject IDs that aren't safe to emit into generated JS.

    `kind` labels the entity type in the error ("property", "risk", ...).
    `owner` optionally names the containing item for context (e.g. the
    section id when validating a question id).
    """
    where = f" on {kind} {owner!r}" if owner else f" for {kind}"
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(
            f"Invalid id{where}: {value!r} — must match "
            f"{_ID_RE.pattern} (letters, digits, underscore; no leading digit)"
        )
    if value in _JS_RESERVED:
        raise ValueError(f"Invalid id{where}: {value!r} — cannot be a JavaScript reserved word")


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


def parse_detail(data: YamlDict) -> Detail:
    """Parse a detail dict into a Detail dataclass."""
    _check_unknown_keys(data, {"id", "description", "properties"}, f"detail {data.get('id')!r}")
    _validate_id(data["id"], kind="detail")
    return Detail(
        id=data["id"],
        description=data["description"],
        properties=tuple(data.get("properties", [])),
    )


def load_details(path: Path) -> list[Detail]:
    """Load details from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_detail(d) for d in data]


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def parse_question(data: YamlDict, details_by_id: dict[str, Detail] | None = None) -> Question:
    """Parse a question dict into a typed Question dataclass."""
    qtype = data["type"]
    match qtype:
        case "binary":
            _check_unknown_keys(
                data,
                {"type", "id", "text", "properties", "guidance"},
                f"binary question {data.get('id')!r}",
            )
            _validate_id(data["id"], kind="question")
            return BinaryQuestion(
                id=data["id"],
                text=data["text"],
                properties=tuple(data.get("properties", [])),
                guidance=data.get("guidance"),
            )
        case "detail":
            # DetailQuestions derive properties from the referenced Detail, so
            # `properties:` on the question itself would be silently ignored.
            _check_unknown_keys(
                data,
                {"type", "id", "text", "detail_id", "guidance"},
                f"detail question {data.get('id')!r}",
            )
            _validate_id(data["id"], kind="question")
            did = data["detail_id"]
            resolved = details_by_id or {}
            if did not in resolved:
                raise ValueError(
                    f"DetailQuestion {data['id']!r} references unknown detail {did!r}"
                )
            detail = resolved[did]
            return DetailQuestion(
                id=data["id"],
                text=data["text"],
                detail_id=did,
                properties=detail.properties,
                guidance=data.get("guidance"),
            )
        case _:
            raise ValueError(f"Unknown question type: {qtype!r}")


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------


def parse_subsection(data: YamlDict, details_by_id: dict[str, Detail] | None = None) -> SubSection:
    """Parse a sub-section dict into a SubSection dataclass."""
    _check_unknown_keys(
        data,
        {"title", "description", "questions"},
        f"subsection {data.get('title')!r}",
    )
    return SubSection(
        title=data["title"],
        description=data["description"],
        questions=tuple(parse_question(q, details_by_id) for q in data["questions"]),
    )


def parse_section(data: YamlDict, details_by_id: dict[str, Detail] | None = None) -> Section:
    """Parse a section dict into a Section dataclass."""
    _check_unknown_keys(
        data,
        {"id", "title", "description", "subsections"},
        f"section {data.get('id')!r}",
    )
    _validate_id(data["id"], kind="section")
    return Section(
        id=data["id"],
        title=data["title"],
        description=data["description"],
        subsections=tuple(parse_subsection(s, details_by_id) for s in data["subsections"]),
    )


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


def parse_condition_mapping(data: YamlDict) -> ConditionMapping:
    """Parse a condition mapping dict into a ConditionMapping dataclass."""
    _check_unknown_keys(
        data,
        {"property", "likelihood", "consequence"},
        "condition mapping",
    )
    likelihood = data["likelihood"]
    consequence = data["consequence"]
    prop = data.get("property")
    if likelihood not in config.LIKELIHOODS:
        raise ValueError(
            f"Invalid likelihood {likelihood!r} on condition for property {prop!r} "
            f"— must be one of {list(config.LIKELIHOODS)}"
        )
    if consequence not in config.CONSEQUENCES:
        raise ValueError(
            f"Invalid consequence {consequence!r} on condition for property {prop!r} "
            f"— must be one of {list(config.CONSEQUENCES)}"
        )
    return ConditionMapping(
        property=data["property"],
        likelihood=likelihood,
        consequence=consequence,
    )


def parse_risk(data: YamlDict) -> Risk:
    """Parse a risk dict into a Risk dataclass."""
    _check_unknown_keys(
        data,
        {"id", "description", "conditions", "guidance"},
        f"risk {data.get('id')!r}",
    )
    _validate_id(data["id"], kind="risk")
    return Risk(
        id=data["id"],
        description=data["description"],
        conditions=tuple(parse_condition_mapping(c) for c in data["conditions"]),
        guidance=data.get("guidance"),
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def parse_control_effect(data: YamlDict) -> ControlEffect:
    """Parse a control effect dict into a ControlEffect dataclass."""
    _check_unknown_keys(data, {"risk_id"}, "control effect")
    return ControlEffect(risk_id=data["risk_id"])


def parse_control(data: YamlDict) -> Control:
    """Parse a control dict into a Control dataclass."""
    _check_unknown_keys(
        data,
        {"id", "description", "property", "effects"},
        f"control {data.get('id')!r}",
    )
    _validate_id(data["id"], kind="control")
    return Control(
        id=data["id"],
        description=data["description"],
        property=data["property"],
        effects=tuple(parse_control_effect(e) for e in data["effects"]),
    )


# ---------------------------------------------------------------------------
# Top-level loaders
# ---------------------------------------------------------------------------


def load_sections(path: Path, details_by_id: dict[str, Detail] | None = None) -> list[Section]:
    """Load sections from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_section(s, details_by_id) for s in data]


def load_risks(path: Path) -> list[Risk]:
    """Load risks from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_risk(r) for r in data]


def load_controls(path: Path) -> list[Control]:
    """Load controls from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_control(c) for c in data]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def parse_property(data: YamlDict) -> Property:
    """Parse a property dict into a Property dataclass."""
    _check_unknown_keys(
        data,
        {"id", "description", "parents", "activation"},
        f"property {data.get('id')!r}",
    )
    _validate_id(data["id"], kind="property")
    return Property(
        id=data["id"],
        description=data["description"],
        parents=tuple(data.get("parents", [])),
        activation=_parse_combinator(
            data.get("activation", "all"),
            field_name="activation",
            owner=f"property {data.get('id')!r}",
        ),
    )


def load_properties(path: Path) -> list[Property]:
    """Load properties from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_property(p) for p in data]


def validate_property_dag(properties: list[Property]) -> None:
    """Validate properties form a valid DAG: no duplicate IDs, all parents exist, no cycles."""
    ids = [p.id for p in properties]
    errors: list[str] = []

    # Duplicate IDs — report each duplicate once, not per extra occurrence
    seen: set[str] = set()
    flagged_dupes: set[str] = set()
    for pid in ids:
        if pid in seen and pid not in flagged_dupes:
            errors.append(f"Duplicate property ID: {pid!r}")
            flagged_dupes.add(pid)
        seen.add(pid)

    # Unknown parent references
    id_set = set(ids)
    for p in properties:
        for parent in p.parents:
            if parent not in id_set:
                errors.append(f"Property {p.id!r} references unknown parent {parent!r}")

    # Cycle detection via Kahn's algorithm (topological sort).
    # In-degree of a node = number of parents it has. Roots (no parents) start
    # at 0 and seed the queue; Kahn's peels layers outward and anything left
    # with in-degree > 0 at the end is part of a cycle. Skip if the graph is
    # already known to be ill-formed (dupes or unknown parents) — Kahn's would
    # misreport otherwise.
    if not errors:
        in_degree: dict[str, int] = {pid: 0 for pid in ids}
        children: dict[str, list[str]] = {pid: [] for pid in ids}
        for p in properties:
            for parent in p.parents:
                in_degree[p.id] += 1
                children[parent].append(p.id)

        queue = [pid for pid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for child in children[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if visited != len(ids):
            errors.append("Property DAG contains a cycle")

    if errors:
        raise ValueError("Invalid property DAG:\n  " + "\n  ".join(errors))


def validate_question_properties(
    questions: Sequence[Question], properties: list[Property]
) -> None:
    """Validate question→property references: all exist, each set by at most one BinaryQuestion."""
    prop_ids = {p.id for p in properties}
    errors: list[str] = []

    # Check all referenced properties exist (both question types)
    for q in questions:
        for pid in q.properties:
            if pid not in prop_ids:
                errors.append(f"Question {q.id!r} references unknown property {pid!r}")

    # Exclusive-setter check — BinaryQuestion only (DetailQuestion uses properties for visibility)
    setters: dict[str, str] = {}
    for q in questions:
        if not isinstance(q, BinaryQuestion):
            continue
        for pid in q.properties:
            if pid in setters:
                errors.append(f"Property {pid!r} is set by both {setters[pid]!r} and {q.id!r}")
            else:
                setters[pid] = q.id

    if errors:
        raise ValueError("Invalid question→property references:\n  " + "\n  ".join(errors))


def validate_risk_properties(risks: list[Risk], properties: list[Property]) -> None:
    """Validate all property references in risk conditions exist."""
    prop_ids = {p.id for p in properties}
    errors: list[str] = []
    for risk in risks:
        for cond in risk.conditions:
            if cond.property not in prop_ids:
                errors.append(
                    f"Risk {risk.id!r} condition references unknown property {cond.property!r}"
                )
    if errors:
        raise ValueError("Invalid risk→property references:\n  " + "\n  ".join(errors))


def validate_control_properties(controls: list[Control], properties: list[Property]) -> None:
    """Validate all control→property references exist."""
    prop_ids = {p.id for p in properties}
    errors: list[str] = []
    for ctrl in controls:
        if ctrl.property not in prop_ids:
            errors.append(f"Control {ctrl.id!r} references unknown property {ctrl.property!r}")
    if errors:
        raise ValueError("Invalid control→property references:\n  " + "\n  ".join(errors))


def validate_control_risk_ids(controls: list[Control], risks: list[Risk]) -> None:
    """Validate all control effect→risk references exist."""
    risk_ids = {r.id for r in risks}
    errors: list[str] = []
    for ctrl in controls:
        for effect in ctrl.effects:
            if effect.risk_id not in risk_ids:
                errors.append(
                    f"Control {ctrl.id!r} effect references unknown risk {effect.risk_id!r}"
                )
    if errors:
        raise ValueError("Invalid control→risk references:\n  " + "\n  ".join(errors))


def validate_detail_properties(details: list[Detail], properties: list[Property]) -> None:
    """Validate all property IDs referenced by details exist."""
    prop_ids = {p.id for p in properties}
    errors: list[str] = []
    for detail in details:
        for pid in detail.properties:
            if pid not in prop_ids:
                errors.append(f"Detail {detail.id!r} references unknown property {pid!r}")
    if errors:
        raise ValueError("Invalid detail→property references:\n  " + "\n  ".join(errors))


def validate_detail_questions(questions: Sequence[Question], details: list[Detail]) -> None:
    """Validate all detail_ids referenced by DetailQuestions exist."""
    detail_ids = {d.id for d in details}
    errors: list[str] = []
    for q in questions:
        if isinstance(q, DetailQuestion) and q.detail_id not in detail_ids:
            errors.append(f"DetailQuestion {q.id!r} references unknown detail {q.detail_id!r}")
    if errors:
        raise ValueError("Invalid DetailQuestion→detail references:\n  " + "\n  ".join(errors))


def validate_id_namespaces(
    sections: Sequence[Section],
    properties: list[Property],
    risks: list[Risk],
    controls: list[Control],
    details: list[Detail],
) -> None:
    """Validate IDs don't collide with Alpine scope names or across namespaces.

    Risk IDs in particular are emitted as unprefixed getter names on the
    Alpine scope (`get {risk.id}()` and `get {risk.id}_residual()`), so they
    must not collide with state fields, internal arrays, helper methods, or
    with another risk's id / `<id>_residual` pairing.
    """
    errors: list[str] = []

    # Risk getters live on the Alpine scope unprefixed. Reject collisions
    # with state/helper names, and with another risk's derived `_residual`
    # getter.
    risk_ids = {r.id for r in risks}
    risk_getters: set[str] = set()
    for r in risks:
        for name in (r.id, f"{r.id}_residual"):
            if name in _ALPINE_RESERVED:
                errors.append(
                    f"Risk id {r.id!r} produces getter {name!r} which "
                    f"collides with a reserved Alpine scope name"
                )
            if name in risk_getters:
                other = name[: -len("_residual")] if name.endswith("_residual") else None
                if other and other in risk_ids and other != r.id:
                    errors.append(
                        f"Risk id {r.id!r} collides with {other!r}_residual; rename one."
                    )
                else:
                    errors.append(f"Duplicate risk getter name {name!r}")
            risk_getters.add(name)

    # Cross-namespace uniqueness: within-namespace duplicates are caught
    # elsewhere (e.g. validate_property_dag); this catches e.g. a property
    # and a control sharing an id, which would confuse humans and tools
    # even if JS doesn't strictly require uniqueness.
    buckets: dict[str, set[str]] = {
        "property": {p.id for p in properties},
        "risk": risk_ids,
        "control": {c.id for c in controls},
        "detail": {d.id for d in details},
        "question": {q.id for sec in sections for sub in sec.subsections for q in sub.questions},
        "section": {s.id for s in sections},
    }
    seen: dict[str, str] = {}
    for kind, ids in buckets.items():
        for i in sorted(ids):
            if i in seen:
                errors.append(
                    f"ID {i!r} is used as both a {seen[i]} and a {kind}; "
                    f"IDs must be unique across namespaces"
                )
            else:
                seen[i] = kind

    if errors:
        raise ValueError("Invalid ID usage:\n  " + "\n  ".join(errors))


def validate_all(
    sections: Sequence[Section],
    properties: list[Property],
    risks: list[Risk],
    controls: list[Control],
    details: list[Detail],
) -> None:
    """Run every validator in dependency order, raising on the first failure."""
    validate_property_dag(properties)
    questions = all_questions(sections)
    validate_question_properties(questions, properties)
    validate_risk_properties(risks, properties)
    validate_control_properties(controls, properties)
    validate_control_risk_ids(controls, risks)
    validate_detail_properties(details, properties)
    validate_detail_questions(questions, details)
    validate_id_namespaces(sections, properties, risks, controls, details)
