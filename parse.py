# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false
"""Parse YAML form definitions into model dataclass instances."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

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
)

# Type aliases for readability
type YamlDict = dict[str, Any]


def _ensure_str(value: object) -> str:
    """Convert YAML booleans back to 'yes'/'no' strings; pass strings through."""
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, str):
        return value
    raise TypeError(f"Expected str or bool, got {type(value).__name__}: {value!r}")


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


def parse_detail(data: YamlDict) -> Detail:
    """Parse a detail dict into a Detail dataclass."""
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
            return BinaryQuestion(
                id=data["id"],
                text=data["text"],
                properties=tuple(data.get("properties", [])),
                guidance=data.get("guidance"),
            )
        case "detail":
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
    return SubSection(
        title=data["title"],
        description=data["description"],
        questions=tuple(parse_question(q, details_by_id) for q in data["questions"]),
    )


def parse_section(data: YamlDict, details_by_id: dict[str, Detail] | None = None) -> Section:
    """Parse a section dict into a Section dataclass."""
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
    return ConditionMapping(
        properties=tuple(data["properties"]),
        mode=data.get("mode", "all"),
        likelihood=data["likelihood"],
        consequence=data["consequence"],
    )


def parse_risk(data: YamlDict) -> Risk:
    """Parse a risk dict into a Risk dataclass."""
    return Risk(
        id=data["id"],
        description=data["description"],
        conditions=tuple(parse_condition_mapping(c) for c in data["conditions"]),
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def parse_control_effect(data: YamlDict) -> ControlEffect:
    """Parse a control effect dict into a ControlEffect dataclass."""
    return ControlEffect(
        risk_id=data["risk_id"],
        reduces_likelihood=data.get("reduces_likelihood", False),
        reduces_consequence=data.get("reduces_consequence", False),
    )


def parse_control(data: YamlDict) -> Control:
    """Parse a control dict into a Control dataclass."""
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
    return Property(
        id=data["id"],
        description=data["description"],
        parents=tuple(data.get("parents", [])),
        activation=data.get("activation", "all"),
    )


def load_properties(path: Path) -> list[Property]:
    """Load properties from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_property(p) for p in data]


def validate_property_dag(properties: list[Property]) -> None:
    """Validate properties form a valid DAG: no duplicate IDs, all parents exist, no cycles."""
    ids = [p.id for p in properties]

    # Check for duplicate IDs
    seen: set[str] = set()
    for pid in ids:
        if pid in seen:
            raise ValueError(f"Duplicate property ID: {pid!r}")
        seen.add(pid)

    # Check all parent references resolve
    id_set = set(ids)
    for p in properties:
        for parent in p.parents:
            if parent not in id_set:
                raise ValueError(f"Property {p.id!r} references unknown parent {parent!r}")

    # Cycle detection via Kahn's algorithm (topological sort)
    # Edges point child→parent, so in-degree counts how many children point to a node
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
        raise ValueError("Property DAG contains a cycle")


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
            for pid in cond.properties:
                if pid not in prop_ids:
                    errors.append(
                        f"Risk {risk.id!r} condition references unknown property {pid!r}"
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
