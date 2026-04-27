"""Promote a new questionnaire/assessment pair into a system's registry folder.

Replaces the system's "current" `questionnaire.json` and (optionally)
`assessment.json` with the new pair, moving any existing current files
into `history/` first — the side-car convention the registry loader
expects (see `registry.py` module docstring).

Usage:

    uv run python scripts/add_to_registry.py <slug> \
        --questionnaire path/to/new-q.json \
        [--assessment path/to/new-a.json]

The pair is validated against the current build's format/version checks
before any filesystem changes. If `--assessment` is provided and lacks
`questionnaire_exported_at`, the script fills it in from the matching
questionnaire (failing loudly if it disagrees with what the JSON already
contains).

A new system folder is created if `<slug>` does not exist yet (subject to
the same `_SLUG_RE` validation the registry loader applies).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Allow `uv run python scripts/add_to_registry.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from registry import (
    _SLUG_RE,
    _check_format_version,
    _parse_json,
)


def _safe_name(timestamp: str) -> str:
    """Filesystem-safe filename prefix derived from an ISO timestamp."""
    return timestamp.replace(":", "-")


def _validate_pair(q_path: Path, a_path: Path | None) -> tuple[dict, dict | None]:
    questionnaire = _parse_json(q_path)
    _check_format_version(
        questionnaire,
        config.QUESTIONNAIRE_FORMAT,
        config.QUESTIONNAIRE_VERSION,
        q_path,
    )
    assessment: dict | None = None
    if a_path is not None:
        assessment = _parse_json(a_path)
        _check_format_version(
            assessment,
            config.ASSESSMENT_FORMAT,
            config.ASSESSMENT_VERSION,
            a_path,
        )
    return questionnaire, assessment


def _reconcile_questionnaire_link(
    questionnaire: dict,
    assessment: dict,
    a_path: Path,
) -> None:
    """Ensure assessment.questionnaire_exported_at matches the questionnaire.

    The assessor's UI fills this in automatically, but legacy or
    hand-crafted exports may lack it. We fill from the questionnaire
    when missing, and refuse to silently overwrite a disagreeing value.
    """
    declared = assessment.get("questionnaire_exported_at")
    expected = questionnaire.get("exported_at")
    if not declared:
        if expected:
            assessment["questionnaire_exported_at"] = expected
        return
    if declared != expected:
        raise ValueError(
            f"{a_path}: questionnaire_exported_at {declared!r} disagrees with "
            f"the supplied questionnaire's exported_at {expected!r}. Re-export the "
            f"assessment against the right questionnaire, or hand-correct the field."
        )


def _move_to_history(folder: Path, *, source_name: str, kind: str) -> Path | None:
    """Move folder/<source_name> into folder/history/ keyed by its exported_at.

    Returns the destination path, or None if the source did not exist.
    """
    src = folder / source_name
    if not src.exists():
        return None
    history_dir = folder / "history"
    history_dir.mkdir(exist_ok=True)
    payload = _parse_json(src)
    timestamp = str(payload.get("exported_at") or "unknown")
    dst = history_dir / f"{_safe_name(timestamp)}-{kind}.json"
    if dst.exists():
        raise ValueError(f"{dst} already exists; refusing to overwrite an existing history entry.")
    shutil.move(str(src), str(dst))
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="Registry slug (folder name under registry/).")
    parser.add_argument(
        "--questionnaire", required=True, type=Path, help="Path to the new questionnaire JSON."
    )
    parser.add_argument(
        "--assessment", type=Path, help="Path to the new assessment JSON (optional)."
    )
    args = parser.parse_args()

    if not _SLUG_RE.match(args.slug):
        parser.error(
            f"Invalid slug {args.slug!r}: must match {_SLUG_RE.pattern} "
            "(lowercase letters, digits, hyphens; start with letter or digit)."
        )

    if not args.questionnaire.exists():
        parser.error(f"--questionnaire {args.questionnaire} does not exist")
    if args.assessment is not None and not args.assessment.exists():
        parser.error(f"--assessment {args.assessment} does not exist")

    questionnaire, assessment = _validate_pair(args.questionnaire, args.assessment)
    if assessment is not None:
        assert args.assessment is not None  # narrow for the type checker
        _reconcile_questionnaire_link(questionnaire, assessment, args.assessment)

    name = questionnaire.get("system_name")
    if not isinstance(name, str) or not name.strip():
        print(
            f"warning: {args.questionnaire} has no system_name — the registry "
            f"will display the slug ({args.slug!r}) as the system's name.",
            file=sys.stderr,
        )

    target = config.registry_dir / args.slug
    target.mkdir(parents=True, exist_ok=True)

    moved_q = _move_to_history(target, source_name="questionnaire.json", kind="questionnaire")
    moved_a = _move_to_history(target, source_name="assessment.json", kind="assessment")

    (target / "questionnaire.json").write_text(json.dumps(questionnaire, indent=2) + "\n")
    if assessment is not None:
        (target / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n")

    parts = [f"Promoted {args.slug}: wrote new questionnaire"]
    if assessment is not None:
        parts.append("and assessment")
    if moved_q or moved_a:
        moved = []
        if moved_q:
            moved.append(moved_q.name)
        if moved_a:
            moved.append(moved_a.name)
        parts.append(f"(history → {', '.join(moved)})")
    print(" ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
