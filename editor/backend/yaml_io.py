"""Read and write YAML spec files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import (
    ConstantsSchema,
    ControlSchema,
    DetailSchema,
    PropertySchema,
    RiskSchema,
    SectionSchema,
    SpecPayload,
    SpecResponse,
)

# Avoid YAML anchors/aliases in output
yaml.Dumper.ignore_aliases = lambda self, data: True  # type: ignore[assignment]


def _read_yaml(path: Path) -> list[dict[str, Any]]:
    """Read a YAML file, returning an empty list if the file doesn't exist."""
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    return data if data else []


def _write_yaml(path: Path, data: list[dict[str, Any]]) -> None:
    """Write a list of dicts to a YAML file."""
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None values for cleaner YAML output."""
    return {k: v for k, v in d.items() if v is not None}


def _question_to_dict(q: dict[str, Any]) -> dict[str, Any]:
    """Convert a question schema dict to YAML-friendly format."""
    result: dict[str, Any] = {"type": q["type"], "id": q["id"], "text": q["text"]}
    if q["type"] == "binary":
        result["properties"] = q.get("properties", [])
    elif q["type"] == "detail":
        result["detail_id"] = q["detail_id"]
    if q.get("guidance"):
        result["guidance"] = q["guidance"]
    return result


def read_spec(form_dir: Path, constants: ConstantsSchema) -> SpecResponse:
    """Read all YAML spec files into a SpecResponse."""
    properties = [PropertySchema(**p) for p in _read_yaml(form_dir / "properties.yaml")]
    risks = [RiskSchema(**r) for r in _read_yaml(form_dir / "risks.yaml")]
    controls = [ControlSchema(**c) for c in _read_yaml(form_dir / "controls.yaml")]
    details = [DetailSchema(**d) for d in _read_yaml(form_dir / "details.yaml")]
    sections = [SectionSchema(**s) for s in _read_yaml(form_dir / "sections.yaml")]

    return SpecResponse(
        properties=properties,
        sections=sections,
        risks=risks,
        controls=controls,
        details=details,
        constants=constants,
    )


def write_spec(form_dir: Path, spec: SpecPayload) -> None:
    """Write a SpecPayload back to YAML files."""
    _write_yaml(
        form_dir / "properties.yaml",
        [_strip_none(p.model_dump()) for p in spec.properties],
    )

    _write_yaml(
        form_dir / "risks.yaml",
        [r.model_dump() for r in spec.risks],
    )

    _write_yaml(
        form_dir / "controls.yaml",
        [c.model_dump() for c in spec.controls],
    )

    _write_yaml(
        form_dir / "details.yaml",
        [d.model_dump() for d in spec.details],
    )

    # Sections need special handling for questions (omit irrelevant fields per type)
    sections_data = []
    for section in spec.sections:
        s = section.model_dump()
        for subsection in s["subsections"]:
            subsection["questions"] = [_question_to_dict(q) for q in subsection["questions"]]
        sections_data.append(s)
    _write_yaml(form_dir / "sections.yaml", sections_data)
