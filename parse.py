# pyright: reportArgumentType=false, reportIndexIssue=false, reportGeneralTypeIssues=false
"""Parse YAML form definitions into model dataclass instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from models import (
    All,
    AnyYesRule,
    ChoiceMapRule,
    Contains,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
    Equals,
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Not,
    Risk,
    Section,
    SubSection,
    YesNoQuestion,
)
from models import (
    Any as AnyCondition,
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
# Conditions
# ---------------------------------------------------------------------------


def parse_condition(data: YamlDict) -> Equals | Contains | All | AnyCondition | Not:
    """Parse a single-key condition dict into a Condition dataclass."""
    if len(data) != 1:
        raise ValueError(f"Condition must have exactly one key, got: {list(data.keys())}")

    key, value = next(iter(data.items()))

    match key:
        case "equals":
            d = value
            return Equals(question_id=d["question_id"], value=_ensure_str(d["value"]))
        case "contains":
            d = value
            return Contains(question_id=d["question_id"], value=_ensure_str(d["value"]))
        case "not":
            return Not(condition=parse_condition(value))
        case "any":
            return AnyCondition(conditions=tuple(parse_condition(c) for c in value))
        case "all":
            return All(conditions=tuple(parse_condition(c) for c in value))
        case _:
            raise ValueError(f"Unknown condition type: {key!r}")


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def parse_question(data: YamlDict):
    """Parse a question dict into a Question dataclass, dispatching on 'type'."""
    qtype = data["type"]
    common = {
        "id": data["id"],
        "text": data["text"],
        "guidance": data.get("guidance"),
        "visible_when": parse_condition(data["visible_when"]) if "visible_when" in data else None,
    }

    match qtype:
        case "yes_no":
            return YesNoQuestion(**common)
        case "free_text":
            return FreeTextQuestion(**common)
        case "multiple_choice":
            return MultipleChoiceQuestion(**common, options=tuple(data["options"]))
        case "multiple_select":
            return MultipleSelectQuestion(**common, options=tuple(data["options"]))
        case _:
            raise ValueError(f"Unknown question type: {qtype!r}")


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------


def parse_subsection(data: YamlDict) -> SubSection:
    """Parse a sub-section dict into a SubSection dataclass."""
    return SubSection(
        title=data["title"],
        description=data["description"],
        questions=tuple(parse_question(q) for q in data["questions"]),
        visible_when=parse_condition(data["visible_when"]) if "visible_when" in data else None,
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
