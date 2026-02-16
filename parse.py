# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false
"""Parse YAML form definitions into model dataclass instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from models import (
    AnyYesRule,
    BinaryQuestion,
    ChoiceMapRule,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
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
# Questions
# ---------------------------------------------------------------------------


def parse_question(data: YamlDict) -> Question:
    """Parse a question dict into a BinaryQuestion dataclass."""
    qtype = data["type"]
    if qtype != "binary":
        raise ValueError(f"Unknown question type: {qtype!r}")
    return BinaryQuestion(
        id=data["id"],
        text=data["text"],
        properties=tuple(data.get("properties", [])),
        guidance=data.get("guidance"),
    )


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------


def parse_subsection(data: YamlDict) -> SubSection:
    """Parse a sub-section dict into a SubSection dataclass."""
    return SubSection(
        title=data["title"],
        description=data["description"],
        questions=tuple(parse_question(q) for q in data["questions"]),
    )


def parse_section(data: YamlDict) -> Section:
    """Parse a section dict into a Section dataclass."""
    return Section(
        id=data["id"],
        title=data["title"],
        description=data["description"],
        subsections=tuple(parse_subsection(s) for s in data["subsections"]),
    )


# ---------------------------------------------------------------------------
# Risk rules
# ---------------------------------------------------------------------------


def parse_rule(data: YamlDict) -> AnyYesRule | CountYesRule | ChoiceMapRule | ContainsAnyRule:
    """Parse a rule dict into a RiskRule dataclass, dispatching on 'type'."""
    rtype = data["type"]

    match rtype:
        case "any_yes":
            return AnyYesRule(
                question_ids=tuple(data["question_ids"]),
                likelihood=data.get("likelihood"),
                consequence=data.get("consequence"),
            )
        case "count_yes":
            return CountYesRule(
                question_ids=tuple(data["question_ids"]),
                threshold=data["threshold"],
                likelihood=data.get("likelihood"),
                consequence=data.get("consequence"),
            )
        case "choice_map":
            return ChoiceMapRule(
                question_id=data["question_id"],
                mapping=data["mapping"],
            )
        case "contains_any":
            return ContainsAnyRule(
                question_id=data["question_id"],
                values=tuple(_ensure_str(v) for v in data["values"]),
                likelihood=data.get("likelihood"),
                consequence=data.get("consequence"),
            )
        case _:
            raise ValueError(f"Unknown rule type: {rtype!r}")


def parse_risk(data: YamlDict) -> Risk:
    """Parse a risk dict into a Risk dataclass."""
    kwargs: dict[str, Any] = {
        "id": data["id"],
        "name": data["name"],
        "description": data["description"],
        "rules": tuple(parse_rule(r) for r in data["rules"]),
    }
    if "default_likelihood" in data:
        kwargs["default_likelihood"] = data["default_likelihood"]
    if "default_consequence" in data:
        kwargs["default_consequence"] = data["default_consequence"]
    return Risk(**kwargs)


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
        name=data["name"],
        question_id=data["question_id"],
        present_value=_ensure_str(data["present_value"]),
        effects=tuple(parse_control_effect(e) for e in data["effects"]),
    )


# ---------------------------------------------------------------------------
# Top-level loaders
# ---------------------------------------------------------------------------


def load_sections(path: Path) -> list[Section]:
    """Load sections from a YAML file."""
    data = yaml.safe_load(path.read_text())
    return [parse_section(s) for s in data]


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
    questions: list[BinaryQuestion], properties: list[Property]
) -> None:
    """Validate question→property references: all exist, each set by at most one question."""
    prop_ids = {p.id for p in properties}
    errors: list[str] = []

    # Check all referenced properties exist
    for q in questions:
        for pid in q.properties:
            if pid not in prop_ids:
                errors.append(f"Question {q.id!r} references unknown property {pid!r}")

    # Check each property is set by at most one question
    setters: dict[str, str] = {}
    for q in questions:
        for pid in q.properties:
            if pid in setters:
                errors.append(f"Property {pid!r} is set by both {setters[pid]!r} and {q.id!r}")
            else:
                setters[pid] = q.id

    if errors:
        raise ValueError("Invalid question→property references:\n  " + "\n  ".join(errors))
