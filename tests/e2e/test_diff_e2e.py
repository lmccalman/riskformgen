"""End-to-end tests for the assessment view's prior-version diff overlay.

The unit + behaviour tests pin the diff *logic*; this layer pins the
parts those can't reach: the multi-file picker, the FileReader pipeline,
and the round-trip of `questionnaire_exported_at` /
`prior_assessment_exported_at` through `download` / `set_input_files`.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.e2e._helpers import (
    DialogRecorder,
    download_payload,
    eval_in_scope,
    get_scope_field,
    scope_selector,
    upload_payload,
)

pytestmark = pytest.mark.e2e

ASSESSMENT = scope_selector("assessment")


def _build_questionnaire_payload(question_ids, detail_ids, property_ids, *, exported_at):
    return {
        "format": "riskformgen-answers",
        "version": 3,
        "build_id": "abcd1234",
        "exported_at": exported_at,
        "system_name": "Test System",
        "system_owner": "Test Owner",
        "question_ids": list(question_ids),
        "answers": {qid: "" for qid in question_ids},
        "detail_ids": list(detail_ids),
        "details": {did: "" for did in detail_ids},
        "property_ids": list(property_ids),
        "properties": {pid: None for pid in property_ids},
    }


def _build_assessment_payload(
    risk_ids,
    property_ids,
    *,
    exported_at,
    questionnaire_exported_at,
    effectiveness=None,
    justification_text=None,
    aggregate_level="",
):
    eff = effectiveness or {}
    return {
        "format": "riskformgen-assessment",
        "version": 5,
        "build_id": "abcd1234",
        "exported_at": exported_at,
        "questionnaire_exported_at": questionnaire_exported_at,
        "system_name": "Test System",
        "system_owner": "Test Owner",
        "risk_ids": list(risk_ids),
        "property_ids": list(property_ids),
        "properties": {pid: None for pid in property_ids},
        "inherent": {
            rid: {
                "likelihood": None,
                "consequence": None,
                "level": "not_applicable",
                "firing_conditions": [],
            }
            for rid in risk_ids
        },
        "control_effectiveness": {rid: eff.get(rid, "") for rid in risk_ids},
        "residual_likelihood": {rid: "" for rid in risk_ids},
        "residual_consequence": {rid: "" for rid in risk_ids},
        "justifications": {rid: justification_text or "" for rid in risk_ids},
        "mandated_controls": {rid: {} for rid in risk_ids},
        "mandated_comments": {rid: {} for rid in risk_ids},
        "aggregate_residual_level": aggregate_level,
        "aggregate_residual_justification": "Prior aggregate." if aggregate_level else "",
    }


class TestPriorLoadAndDiff:
    def test_loading_prior_pair_engages_diff_mode_and_carries_state_forward(
        self, assessment_page: Page
    ) -> None:
        recorder = DialogRecorder(assessment_page)

        question_ids = get_scope_field(assessment_page, "_questionIds", scope=ASSESSMENT)
        detail_ids = get_scope_field(assessment_page, "_detailIds", scope=ASSESSMENT)
        property_ids = get_scope_field(assessment_page, "_propertyIds", scope=ASSESSMENT)
        risk_ids = get_scope_field(assessment_page, "_riskIds", scope=ASSESSMENT)
        build_id = get_scope_field(assessment_page, "_buildId", scope=ASSESSMENT)
        assert risk_ids, "Form has no risks — diff overlay test cannot run."

        # Load the current questionnaire first (so the assessor's normal entry
        # path is exercised).
        cur_q = _build_questionnaire_payload(
            question_ids, detail_ids, property_ids, exported_at="2026-04-01T08:00:00Z"
        )
        cur_q["build_id"] = build_id
        upload_payload(assessment_page, 'input[x-ref="answersFile"]', cur_q)
        assessment_page.wait_for_function(
            f"{ASSESSMENT}.loaded_questionnaire_at === '2026-04-01T08:00:00Z'"
        )

        # Now load the prior pair via the multi-file picker. Order shouldn't
        # matter — set_input_files takes a list, the JS routes by `format`.
        prior_q = _build_questionnaire_payload(
            question_ids, detail_ids, property_ids, exported_at="2026-01-15T10:00:00Z"
        )
        prior_q["build_id"] = build_id
        prior_a = _build_assessment_payload(
            risk_ids,
            property_ids,
            exported_at="2026-01-15T11:00:00Z",
            questionnaire_exported_at="2026-01-15T10:00:00Z",
            effectiveness={risk_ids[0]: "partial"},
            justification_text="Prior call.",
            aggregate_level="medium",
        )
        prior_a["build_id"] = build_id
        assessment_page.locator('input[x-ref="priorFiles"]').set_input_files(
            files=[
                {
                    "name": "prior-q.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(prior_q).encode(),
                },
                {
                    "name": "prior-a.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(prior_a).encode(),
                },
            ]
        )

        # diffMode flips on; lineage timestamp and prior payloads land.
        assessment_page.wait_for_function(f"{ASSESSMENT}.diffMode === true")
        assert (
            get_scope_field(assessment_page, "prior_assessment_at", scope=ASSESSMENT)
            == "2026-01-15T11:00:00Z"
        )
        # Carry-forward: live state picks up the prior assessment's calls.
        assert (
            get_scope_field(
                assessment_page,
                f"control_effectiveness[{json.dumps(risk_ids[0])}]",
                scope=ASSESSMENT,
            )
            == "partial"
        )
        assert (
            get_scope_field(
                assessment_page,
                f"justifications[{json.dumps(risk_ids[0])}]",
                scope=ASSESSMENT,
            )
            == "Prior call."
        )
        assert (
            get_scope_field(assessment_page, "aggregate_residual_level", scope=ASSESSMENT)
            == "medium"
        )
        # No spurious dialogs along the way.
        assert recorder.captured == []

    def test_export_includes_lineage_pointers(self, assessment_page: Page) -> None:
        DialogRecorder(assessment_page)
        question_ids = get_scope_field(assessment_page, "_questionIds", scope=ASSESSMENT)
        detail_ids = get_scope_field(assessment_page, "_detailIds", scope=ASSESSMENT)
        property_ids = get_scope_field(assessment_page, "_propertyIds", scope=ASSESSMENT)

        cur_q = _build_questionnaire_payload(
            question_ids, detail_ids, property_ids, exported_at="2026-04-01T08:00:00Z"
        )
        upload_payload(assessment_page, 'input[x-ref="answersFile"]', cur_q)
        # Pretend a prior assessment was loaded — set the lineage slot directly so
        # we don't need to drive the file picker for this assertion.
        eval_in_scope(
            assessment_page,
            "scope.prior_assessment_at = '2026-01-15T11:00:00Z';",
            scope=ASSESSMENT,
        )
        payload = download_payload(
            assessment_page, "Save assessment", "riskformgen-assessment.json"
        )
        assert payload["questionnaire_exported_at"] == "2026-04-01T08:00:00Z"
        assert payload["prior_assessment_exported_at"] == "2026-01-15T11:00:00Z"

    def test_clear_prior_drops_back_to_no_diff_mode(self, assessment_page: Page) -> None:
        recorder = DialogRecorder(assessment_page)
        question_ids = get_scope_field(assessment_page, "_questionIds", scope=ASSESSMENT)
        detail_ids = get_scope_field(assessment_page, "_detailIds", scope=ASSESSMENT)
        property_ids = get_scope_field(assessment_page, "_propertyIds", scope=ASSESSMENT)

        prior_q = _build_questionnaire_payload(
            question_ids, detail_ids, property_ids, exported_at="2026-01-15T10:00:00Z"
        )
        assessment_page.locator('input[x-ref="priorFiles"]').set_input_files(
            files=[
                {
                    "name": "prior-q.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(prior_q).encode(),
                }
            ]
        )
        assessment_page.wait_for_function(f"{ASSESSMENT}.diffMode === true")

        # Click "Clear prior" — the confirm dialog is auto-accepted by the recorder.
        assessment_page.get_by_role("button", name="Clear prior").click()
        assessment_page.wait_for_function(f"{ASSESSMENT}.diffMode === false")
        assert get_scope_field(assessment_page, "prior_assessment_at", scope=ASSESSMENT) == ""
        assert any(d["type"] == "confirm" for d in recorder.captured)
