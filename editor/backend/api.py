"""REST API route handlers."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from fastapi import APIRouter

import config

from .schemas import (
    ConstantsSchema,
    RebuildResult,
    SaveResult,
    SpecPayload,
    ValidationResult,
)
from .validation import validate_spec
from .yaml_io import read_spec, write_spec

router = APIRouter()

CONSTANTS = ConstantsSchema(
    likelihoods=list(config.LIKELIHOODS),
    consequences=list(config.CONSEQUENCES),
)


@router.get("/spec")
def get_spec():
    """Load the entire spec from YAML files."""
    return read_spec(config.form_dir, CONSTANTS)


@router.put("/spec")
def put_spec(spec: SpecPayload) -> SaveResult:
    """Validate and write the spec to YAML files."""
    errors = validate_spec(spec)
    if errors:
        return SaveResult(ok=False, errors=errors)
    write_spec(config.form_dir, spec)
    return SaveResult(ok=True, errors=[])


@router.post("/validate")
def post_validate(spec: SpecPayload) -> ValidationResult:
    """Validate the spec without writing."""
    errors = validate_spec(spec)
    return ValidationResult(valid=len(errors) == 0, errors=errors)


@router.post("/rebuild")
def post_rebuild() -> RebuildResult:
    """Rebuild the static site."""
    try:
        import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            main.main()
        return RebuildResult(ok=True, message=buf.getvalue().strip())
    except Exception as e:
        return RebuildResult(ok=False, message=str(e))
