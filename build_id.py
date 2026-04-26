"""Compute a content-hash fingerprint of the form YAML.

The build identifier is the first 8 hex chars of SHA-256 over every
`form/*.yaml` file's bytes, concatenated in sorted-name order with a
length-prefixed framing so a rename never produces a collision against
an unrelated layout. See `CLAUDE.md` (Versioning) for the role this
plays — provenance only, never gates loading.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_build_id(form_dir: Path) -> str:
    """Hash the contents of every YAML file under `form_dir`.

    Files are walked in sorted-name order; each contribution is framed as
    `<utf8-name>\\0<bytes-len>\\0<bytes>` so a file rename or content
    move can't collide with an unrelated layout. Returns the first 8 hex
    chars of SHA-256 — short enough to print in a footer, long enough
    that an accidental collision across a single project is vanishingly
    unlikely.
    """
    h = hashlib.sha256()
    for path in sorted(form_dir.glob("*.yaml")):
        data = path.read_bytes()
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(data)).encode("ascii"))
        h.update(b"\0")
        h.update(data)
    return h.hexdigest()[:8]
