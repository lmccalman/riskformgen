# pyright: reportOperatorIssue=false, reportArgumentType=false
"""Tests for the YAML content-hash build identifier and how it surfaces.

Covers:
- `compute_build_id()` semantics: deterministic over content; sensitive to
  any content or filename change; insensitive to file ordering on disk.
- The build_id reaches every rendered HTML page footer and both Alpine
  factory `_buildId` slots.
- Exports embed `build_id`; the importer treats it as provenance only —
  loads silently when IDs align even if `build_id` differs.
- Schema-version mismatch routes through the existing confirmation dialog
  (no longer hard-rejects), and the dialog message includes the version
  delta line.
- The registry stale-build banner renders when a record's `build_id`
  differs from the current build (and no banner when they match).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from py_mini_racer import MiniRacer

from build_id import compute_build_id
from models import BinaryQuestion, Property, Section, SubSection
from registry import SystemRecord
from render import (
    render_assessment,
    render_assessment_app_js,
    render_landing,
    render_questionnaire,
    render_questionnaire_app_js,
    render_registry_index,
    render_registry_system,
)
from tests.js_harness import _BOOTSTRAP_JS

# ---------------------------------------------------------------------------
# Build-id computation
# ---------------------------------------------------------------------------


class TestComputeBuildId:
    def _seed(self, dir_: Path, files: dict[str, str]) -> None:
        for name, content in files.items():
            (dir_ / name).write_text(content)

    def test_deterministic(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n", "b.yaml": "y: 2\n"})
        assert compute_build_id(tmp_path) == compute_build_id(tmp_path)

    def test_changes_when_content_changes(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n"})
        before = compute_build_id(tmp_path)
        (tmp_path / "a.yaml").write_text("x: 2\n")
        assert compute_build_id(tmp_path) != before

    def test_changes_when_file_renamed(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n"})
        before = compute_build_id(tmp_path)
        (tmp_path / "a.yaml").rename(tmp_path / "renamed.yaml")
        assert compute_build_id(tmp_path) != before

    def test_changes_when_file_added(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n"})
        before = compute_build_id(tmp_path)
        (tmp_path / "b.yaml").write_text("y: 2\n")
        assert compute_build_id(tmp_path) != before

    def test_ignores_non_yaml_files(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n"})
        before = compute_build_id(tmp_path)
        (tmp_path / "scratch.txt").write_text("ignored content")
        (tmp_path / "notes.md").write_text("# also ignored")
        assert compute_build_id(tmp_path) == before

    def test_short_hex(self, tmp_path: Path) -> None:
        self._seed(tmp_path, {"a.yaml": "x: 1\n"})
        out = compute_build_id(tmp_path)
        assert len(out) == 8
        int(out, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# Build-id surfaced in rendered output
# ---------------------------------------------------------------------------


class TestBuildIdSurfacing:
    def test_landing_footer_has_build_id(self) -> None:
        html = render_landing(build_id="abc12345")
        assert "abc12345" in html
        assert "Build" in html

    def test_questionnaire_footer_has_build_id(self, sample_sections, sample_properties) -> None:
        html = render_questionnaire(
            sample_sections, properties=sample_properties, build_id="abc12345"
        )
        assert "abc12345" in html

    def test_assessment_footer_has_build_id(self, sample_sections, sample_properties) -> None:
        html = render_assessment(
            sample_sections, [], properties=sample_properties, build_id="abc12345"
        )
        assert "abc12345" in html

    def test_registry_index_footer_has_build_id(self) -> None:
        html = render_registry_index([], build_id="abc12345")
        assert "abc12345" in html

    def test_questionnaire_factory_carries_build_id(
        self, sample_sections, sample_properties
    ) -> None:
        js = render_questionnaire_app_js(
            sample_sections, properties=sample_properties, build_id="abc12345"
        )
        assert "_buildId: 'abc12345'" in js
        assert "build_id: this._buildId" in js

    def test_assessment_factory_carries_build_id(self, sample_sections, sample_properties) -> None:
        js = render_assessment_app_js(
            sample_sections, [], properties=sample_properties, build_id="abc12345"
        )
        assert "_buildId: 'abc12345'" in js
        assert "build_id: this._buildId" in js

    def test_no_footer_when_build_id_empty(self) -> None:
        # Default `build_id=""` (used by old test paths) must not produce a
        # broken or noisy footer — we suppress the section entirely.
        html = render_landing()
        assert "page-footer" not in html


# ---------------------------------------------------------------------------
# Stale-build banner
# ---------------------------------------------------------------------------


def _make_record(build_id_value: str | None) -> SystemRecord:
    """A minimal SystemRecord. `build_id_value=None` simulates a legacy
    record that predates build_id embedding (no field at all)."""
    questionnaire: dict[str, Any] = {
        "format": "riskformgen-answers",
        "version": 3,
        "exported_at": "2026-04-01T08:00:00Z",
        "system_name": "Demo",
        "system_owner": "Demo Owner",
        "question_ids": [],
        "answers": {},
        "detail_ids": [],
        "details": {},
        "property_ids": [],
        "properties": {},
    }
    if build_id_value is not None:
        questionnaire["build_id"] = build_id_value
    return SystemRecord(
        slug="demo",
        questionnaire=questionnaire,
        assessment=None,
    )


class TestStaleBuildBanner:
    def test_index_no_banner_when_build_ids_match(self) -> None:
        rec = _make_record("abc12345")
        html = render_registry_index([rec], build_id="abc12345")
        assert "Stale build" not in html

    def test_index_banner_when_build_ids_differ(self) -> None:
        rec = _make_record("oldhash1")
        html = render_registry_index([rec], build_id="newhash2")
        assert "Stale build" in html

    def test_index_banner_when_record_has_no_build_id(self) -> None:
        # Legacy record predating versioning should be flagged stale so the
        # operator knows to re-export when convenient.
        rec = _make_record(None)
        html = render_registry_index([rec], build_id="newhash2")
        assert "Stale build" in html

    def test_system_page_no_banner_when_match(self, sample_sections, sample_properties) -> None:
        rec = _make_record("abc12345")
        html = render_registry_system(
            rec,
            sample_sections,
            [],
            [],
            sample_properties,
            details=[],
            build_id="abc12345",
        )
        assert "stale-build-banner" not in html

    def test_system_page_banner_when_mismatch(self, sample_sections, sample_properties) -> None:
        rec = _make_record("oldhash1")
        html = render_registry_system(
            rec,
            sample_sections,
            [],
            [],
            sample_properties,
            details=[],
            build_id="newhash2",
        )
        assert "stale-build-banner" in html
        assert "oldhash1" in html
        assert "newhash2" in html


# ---------------------------------------------------------------------------
# Importer behaviour around build_id and version
# ---------------------------------------------------------------------------


def _section() -> Section:
    return Section(
        id="s1",
        title="S",
        description="",
        subsections=(
            SubSection(
                title="t",
                description="",
                questions=(BinaryQuestion(id="q1", text="", properties=("p1",)),),
            ),
        ),
    )


def _properties() -> list[Property]:
    return [Property(id="p1", description="")]


_IMPORT_HARNESS_JS = """
// Capture the message from confirm() / alert() and let tests pre-set the
// confirm() return value. Then stub FileReader so reader.onload fires
// synchronously with whatever payload was set on the prototype.
let __importMessage = null;
const __confirmDecision = { value: true };
confirm = (msg) => { __importMessage = msg; return __confirmDecision.value; };
alert = (msg) => { __importMessage = msg; };
class FileReader {
  readAsText(_file) {
    this.result = FileReader.__payload;
    if (this.onload) this.onload({});
  }
}
function __doImport(payload, fnName) {
  __importMessage = null;
  FileReader.__payload = JSON.stringify(payload);
  const fakeEvent = {
    target: {
      files: [{ name: 'x.json' }],
      value: '',
    },
  };
  scope[fnName](fakeEvent);
  return __importMessage;
}
"""


def _build_questionnaire_with_build_id(build_id_str: str) -> MiniRacer:
    """Compile the questionnaire factory at a given build_id and return the
    raw mini-racer context so tests can drive `_importJson` against it."""
    js = render_questionnaire_app_js([_section()], properties=_properties(), build_id=build_id_str)
    ctx = MiniRacer()
    ctx.eval(_BOOTSTRAP_JS)
    ctx.eval(js)
    ctx.eval("var scope = __state.factory();")
    ctx.eval("if (typeof scope.init === 'function') scope.init();")
    ctx.eval(_IMPORT_HARNESS_JS)
    return ctx


def _payload(
    *, version: int = 3, build_id_value: str | None = "abc12345", answer: str = "yes"
) -> dict[str, Any]:
    p: dict[str, Any] = {
        "format": "riskformgen-answers",
        "version": version,
        "exported_at": "2026-04-01T08:00:00Z",
        "system_name": "Test System",
        "system_owner": "Test Owner",
        "question_ids": ["q1"],
        "answers": {"q1": answer},
        "detail_ids": [],
        "details": {},
        "property_ids": ["p1"],
        "properties": {"p1": True},
    }
    if build_id_value is not None:
        p["build_id"] = build_id_value
    return p


class TestImporterBuildIdAndVersion:
    def test_clean_load_silent_when_everything_matches(self) -> None:
        ctx = _build_questionnaire_with_build_id("abc12345")
        msg = ctx.eval(
            f"__doImport({json.dumps(_payload(build_id_value='abc12345'))}, 'importAnswers')"
        )
        # confirm() never invoked — IDs align, version matches, build matches.
        assert msg is None
        assert ctx.eval("scope.answers") == {"q1": "yes"}

    def test_silent_load_when_only_build_id_differs(self) -> None:
        # With ID-merge, a build_id mismatch alone doesn't justify a popup.
        ctx = _build_questionnaire_with_build_id("newhash2")
        msg = ctx.eval(
            f"__doImport({json.dumps(_payload(build_id_value='oldhash1'))}, 'importAnswers')"
        )
        assert msg is None
        assert ctx.eval("scope.answers") == {"q1": "yes"}

    def test_version_mismatch_routes_through_dialog_and_loads(self) -> None:
        # Schema version differs — dialog is shown, user confirms (default
        # True), and answers still load by ID.
        ctx = _build_questionnaire_with_build_id("abc12345")
        msg = ctx.eval(f"__doImport({json.dumps(_payload(version=99))}, 'importAnswers')")
        assert msg is not None
        assert "Schema version was 99" in msg
        # Apply happened despite version mismatch.
        assert ctx.eval("scope.answers") == {"q1": "yes"}

    def test_version_mismatch_with_user_cancel_does_not_apply(self) -> None:
        ctx = _build_questionnaire_with_build_id("abc12345")
        ctx.eval("__confirmDecision.value = false;")
        msg = ctx.eval(f"__doImport({json.dumps(_payload(version=99))}, 'importAnswers')")
        assert "Schema version was 99" in msg
        # User cancelled — answer state untouched (still default empty).
        assert ctx.eval("scope.answers") == {"q1": ""}

    def test_dialog_includes_build_id_line_when_other_mismatches_force_it(self) -> None:
        # Removed-id forces the dialog; the build_id line should ride along.
        ctx = _build_questionnaire_with_build_id("newhash2")
        payload = _payload(build_id_value="oldhash1")
        # Add an id present in the file but missing from current form so
        # the "removed" branch fires.
        payload["question_ids"] = ["q1", "q_gone"]
        payload["answers"]["q_gone"] = "yes"
        msg = ctx.eval(f"__doImport({json.dumps(payload)}, 'importAnswers')")
        assert msg is not None
        assert "Exported from build oldhash1" in msg
        assert "current: newhash2" in msg

    def test_format_mismatch_still_hard_rejects(self) -> None:
        # Format is the only remaining hard gate — wrong format means wrong
        # tool, which can never be salvaged by ID-merge.
        ctx = _build_questionnaire_with_build_id("abc12345")
        bad = _payload()
        bad["format"] = "something-else"
        msg = ctx.eval(f"__doImport({json.dumps(bad)}, 'importAnswers')")
        # alert(), not confirm(), and nothing loaded.
        assert msg is not None
        assert "not a answers file" in msg or "Expected format" in msg
        assert ctx.eval("scope.answers") == {"q1": ""}
