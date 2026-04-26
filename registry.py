"""Load and validate committed system records for the registry view.

Each system lives in its own folder under `registry/<slug>/`:

    questionnaire.json   # required, format `riskformgen-answers` v2
    assessment.json      # optional — system in progress if missing
    meta.yaml            # required, supplies the display name (and owner/notes)

Registry rendering is a pure read of these files: the JSON exports already
carry the resolved property states and per-risk inherent values so the
loader does not re-evaluate the property DAG. Unknown ids (questions,
risks, controls, properties present in the JSON but no longer in the YAML
form) emit a build-time warning rather than failing — this is the small
concession the spec asks for around form evolution; the full versioning
TODO will tighten it later.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

import config
from models import Control, Property, Risk, Section, all_questions

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class SystemMeta:
    name: str
    owner: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SystemRecord:
    """One committed system: meta, questionnaire JSON, optional assessment JSON.

    Both JSON payloads are kept as dicts so templates can render them
    directly. Validation has already verified format/version and warned on
    unknown ids; downstream code can trust the basic shape.
    """

    slug: str
    meta: SystemMeta
    questionnaire: dict[str, Any]
    assessment: dict[str, Any] | None

    @property
    def exported_at(self) -> str:
        """ISO timestamp used for sorting and the 'Last assessed' column."""
        if self.assessment is not None:
            return str(self.assessment.get("exported_at", ""))
        return str(self.questionnaire.get("exported_at", ""))


def _parse_meta(path: Path) -> SystemMeta:
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{path}: 'name' is required and must be a non-empty string")
    return SystemMeta(
        name=name,
        owner=raw.get("owner"),
        notes=raw.get("notes"),
    )


def _parse_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level value must be a JSON object")
    return data


def _check_format_version(
    data: dict[str, Any], expected_format: str, expected_version: int, path: Path
) -> None:
    fmt = data.get("format")
    if fmt != expected_format:
        raise ValueError(f"{path}: wrong format {fmt!r}, expected {expected_format!r}")
    version = data.get("version")
    if version != expected_version:
        raise ValueError(
            f"{path}: incompatible version {version!r}, expected {expected_version}. "
            f"Re-export from a matching build."
        )


def _warn_unknown_ids(slug: str, kind: str, payload_ids: Sequence[str], known: set[str]) -> None:
    unknown = [pid for pid in payload_ids if pid not in known]
    if unknown:
        logger.warning(
            "[%s] %s: %d unknown id(s) skipped on render: %s",
            slug,
            kind,
            len(unknown),
            ", ".join(sorted(unknown)),
        )


def _load_system(
    folder: Path,
    *,
    question_ids: set[str],
    risk_ids: set[str],
    control_ids: set[str],
    property_ids: set[str],
) -> SystemRecord:
    slug = folder.name
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid system slug {slug!r} — must match {_SLUG_RE.pattern} "
            f"(lowercase letters, digits, hyphens; start with letter or digit)"
        )

    meta_path = folder / "meta.yaml"
    if not meta_path.exists():
        raise ValueError(f"Missing {meta_path} for system {slug!r}")
    meta = _parse_meta(meta_path)

    q_path = folder / "questionnaire.json"
    if not q_path.exists():
        raise ValueError(f"Missing {q_path} for system {slug!r}")
    questionnaire = _parse_json(q_path)
    _check_format_version(
        questionnaire,
        config.QUESTIONNAIRE_FORMAT,
        config.QUESTIONNAIRE_VERSION,
        q_path,
    )

    _warn_unknown_ids(slug, "question", questionnaire.get("question_ids", []), question_ids)
    _warn_unknown_ids(slug, "property", questionnaire.get("property_ids", []), property_ids)

    a_path = folder / "assessment.json"
    assessment: dict[str, Any] | None = None
    if a_path.exists():
        assessment = _parse_json(a_path)
        _check_format_version(
            assessment,
            config.ASSESSMENT_FORMAT,
            config.ASSESSMENT_VERSION,
            a_path,
        )
        _warn_unknown_ids(slug, "risk", assessment.get("risk_ids", []), risk_ids)
        # Warn on mandated-control ids that no longer exist in the form
        seen_controls: set[str] = set()
        for ctrls in (assessment.get("mandated_controls") or {}).values():
            if isinstance(ctrls, dict):
                seen_controls.update(ctrls.keys())
        _warn_unknown_ids(slug, "control", sorted(seen_controls), control_ids)

    return SystemRecord(slug=slug, meta=meta, questionnaire=questionnaire, assessment=assessment)


def load_registry(
    registry_dir: Path,
    *,
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control],
    properties: Sequence[Property],
) -> list[SystemRecord]:
    """Walk `registry_dir`, load each system, return records sorted newest-first.

    Returns an empty list if `registry_dir` does not exist (no systems
    committed yet). Hard-fails on format/version mismatch or malformed
    files so the build catches problems before they reach the registry.
    """
    if not registry_dir.exists():
        return []

    question_ids = {q.id for q in all_questions(sections)}
    risk_ids = {r.id for r in risks}
    control_ids = {c.id for c in controls}
    property_ids = {p.id for p in properties}

    records: list[SystemRecord] = []
    for entry in sorted(registry_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        records.append(
            _load_system(
                entry,
                question_ids=question_ids,
                risk_ids=risk_ids,
                control_ids=control_ids,
                property_ids=property_ids,
            )
        )

    records.sort(key=lambda r: r.exported_at, reverse=True)
    return records


def aggregate_residual_level(record: SystemRecord, risk_levels: Sequence[str]) -> str:
    """Return the assessor's aggregate pick when set, else the computed worst.

    The aggregate residual level is the assessor's overall judgement for the
    system. When they leave it empty (no override), we fall back to the
    worst per-risk residual — the same value the assessment UI shows as
    `Suggested:`.
    """
    if record.assessment is None:
        return "not_applicable"
    pick = record.assessment.get("aggregate_residual_level")
    if isinstance(pick, str) and pick:
        return pick
    return worst_residual_level(record, risk_levels)


def worst_residual_level(record: SystemRecord, risk_levels: Sequence[str]) -> str:
    """Highest-severity residual level across the system's risks.

    Uses the assessment's per-risk residual L/C combined with control
    effectiveness to derive each risk's residual level, then picks the
    worst by `risk_levels` ordering. Returns `not_applicable` when there
    is no assessment or no risk fires.
    """
    if record.assessment is None:
        return "not_applicable"

    inherent = record.assessment.get("inherent") or {}
    effectiveness = record.assessment.get("control_effectiveness") or {}

    severity = {lvl: idx for idx, lvl in enumerate(risk_levels)}
    worst_idx = severity.get("not_applicable", 0)
    worst = "not_applicable"

    for rid, inh in inherent.items():
        level = _residual_level_for_risk(rid, inh, effectiveness, record.assessment)
        idx = severity.get(level)
        if idx is not None and idx > worst_idx:
            worst_idx = idx
            worst = level
    return worst


def _residual_level_for_risk(
    risk_id: str,
    inherent: dict[str, Any],
    effectiveness: dict[str, str],
    assessment: dict[str, Any],
) -> str:
    """Derive the residual level for a single risk, mirroring the JS getter."""
    inh_level = inherent.get("level", "not_applicable")
    if inh_level == "not_applicable":
        return "not_applicable"
    eff = effectiveness.get(risk_id) or "ineffective"
    if eff == "ineffective":
        return inh_level
    if eff == "controlled":
        return "controlled"
    # partial
    res_l = (assessment.get("residual_likelihood") or {}).get(risk_id)
    res_c = (assessment.get("residual_consequence") or {}).get(risk_id)
    if not res_l or not res_c:
        return inh_level
    return config.RISK_MATRIX.get(res_l, {}).get(res_c, "not_applicable")
