import json
from datetime import datetime

import pytest
from playwright.sync_api import Page

from tests.e2e._helpers import (
    DialogRecorder,
    download_payload,
    eval_in_scope,
    get_scope_field,
    scope_selector,
    upload_payload,
    wait_for_answer,
    wait_for_effectiveness,
)

pytestmark = pytest.mark.e2e

QUESTIONNAIRE = scope_selector("questionnaire")
ASSESSMENT = scope_selector("assessment")


class TestAnswersRoundtripQuestionnaire:
    """Answers export/import is the questionnaire view's responsibility —
    that's where the system owner's input lives. Pins SPEC §Workflow.3."""

    def test_happy_path_roundtrip(self, questionnaire_page: Page) -> None:
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        assert len(question_ids) >= 2
        first, second = question_ids[0], question_ids[1]

        eval_in_scope(
            questionnaire_page,
            f"scope.answers[{json.dumps(first)}] = 'yes';"
            f"scope.answers[{json.dumps(second)}] = 'no';",
            scope=QUESTIONNAIRE,
        )

        payload = download_payload(questionnaire_page, "Save answers", "riskformgen-answers.json")
        assert payload["format"] == "riskformgen-answers"
        assert payload["version"] == 2
        # Properties snapshot is baked into the export so the registry can
        # render without re-evaluating the cascade.
        assert payload["properties"][payload["property_ids"][0]] in (True, False, None)
        assert payload["answers"][first] == "yes"
        assert payload["answers"][second] == "no"

        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )
        assert (
            get_scope_field(
                questionnaire_page, f"answers[{json.dumps(first)}]", scope=QUESTIONNAIRE
            )
            == ""
        )

        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(questionnaire_page, first, "yes", scope=QUESTIONNAIRE)
        wait_for_answer(questionnaire_page, second, "no", scope=QUESTIONNAIRE)
        assert recorder.captured == []

    def test_silent_apply_when_ids_align(self, questionnaire_page: Page) -> None:
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        detail_ids: list[str] = get_scope_field(
            questionnaire_page, "_detailIds", scope=QUESTIONNAIRE
        )
        payload = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": list(question_ids),
            "answers": {qid: "yes" for qid in question_ids},
            "detail_ids": list(detail_ids),
            "details": {did: "note" for did in detail_ids},
            "property_ids": [],
            "properties": {},
        }

        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(questionnaire_page, question_ids[0], "yes", scope=QUESTIONNAIRE)
        assert recorder.confirms() == []

    def test_invalid_json_shows_alert(self, questionnaire_page: Page) -> None:
        eval_in_scope(
            questionnaire_page,
            "scope.answers[scope._questionIds[0]] = 'preset';",
            scope=QUESTIONNAIRE,
        )
        first: str = get_scope_field(questionnaire_page, "_questionIds[0]", scope=QUESTIONNAIRE)

        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', "not json{")
        recorder.wait_for_alerts()
        assert "Invalid JSON" in recorder.alerts()[0]["message"]
        assert (
            get_scope_field(
                questionnaire_page, f"answers[{json.dumps(first)}]", scope=QUESTIONNAIRE
            )
            == "preset"
        )

    def test_wrong_format_shows_alert(self, questionnaire_page: Page) -> None:
        payload = {"format": "something-else", "version": 2, "question_ids": [], "answers": {}}
        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "riskformgen-answers" in msg
        assert "answers" in msg

    def test_wrong_version_shows_alert(self, questionnaire_page: Page) -> None:
        payload = {
            "format": "riskformgen-answers",
            "version": 99,
            "question_ids": [],
            "answers": {},
        }
        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "99" in msg
        assert "expected 2" in msg

    def test_added_ids_prompt_confirm_accept_applies_partial(
        self, questionnaire_page: Page
    ) -> None:
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        assert len(question_ids) >= 3
        kept = question_ids[:2]
        payload = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": list(kept),
            "answers": {qid: "yes" for qid in kept},
            "detail_ids": [],
            "details": {},
            "property_ids": [],
            "properties": {},
        }

        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )

        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(questionnaire_page, kept[0], "yes", scope=QUESTIONNAIRE)

        assert len(recorder.confirms()) == 1
        msg = recorder.confirms()[0]["message"]
        assert "new since export" in msg
        assert str(len(question_ids) - len(kept)) in msg

        answers: dict[str, str] = get_scope_field(
            questionnaire_page, "answers", scope=QUESTIONNAIRE
        )
        for qid in kept:
            assert answers[qid] == "yes"
        for qid in question_ids[2:]:
            assert answers[qid] == ""

    def test_removed_ids_prompt_confirm_shows_skipped_count(
        self, questionnaire_page: Page
    ) -> None:
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        extra_id = "nonexistent_question_xyz"
        file_ids = [*question_ids, extra_id]
        payload = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": file_ids,
            "answers": {**{qid: "yes" for qid in question_ids}, extra_id: "yes"},
            "detail_ids": [],
            "details": {},
            "property_ids": [],
            "properties": {},
        }

        recorder = DialogRecorder(questionnaire_page)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(questionnaire_page, question_ids[0], "yes", scope=QUESTIONNAIRE)

        assert len(recorder.confirms()) == 1
        assert "skipped (removed)" in recorder.confirms()[0]["message"]

    def test_user_cancels_confirm_leaves_state_unchanged(self, questionnaire_page: Page) -> None:
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        first = question_ids[0]
        eval_in_scope(
            questionnaire_page,
            f"scope.answers[{json.dumps(first)}] = 'baseline';",
            scope=QUESTIONNAIRE,
        )
        payload = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": question_ids[:1],
            "answers": {first: "should-not-apply"},
            "detail_ids": [],
            "details": {},
            "property_ids": [],
            "properties": {},
        }

        recorder = DialogRecorder(questionnaire_page, accept_confirm=False)
        upload_payload(questionnaire_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_confirms()

        assert (
            get_scope_field(
                questionnaire_page, f"answers[{json.dumps(first)}]", scope=QUESTIONNAIRE
            )
            == "baseline"
        )


class TestAssessmentImportsQuestionnaireJson:
    """The assessment view ingests questionnaire JSON via its 'Load
    questionnaire' button. Confirm the same import surface works on the
    assessment factory."""

    def test_assessment_loads_questionnaire_json(self, assessment_page: Page) -> None:
        question_ids: list[str] = get_scope_field(
            assessment_page, "_questionIds", scope=ASSESSMENT
        )
        first = question_ids[0]
        payload = {
            "format": "riskformgen-answers",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": list(question_ids),
            "answers": {qid: ("yes" if qid == first else "") for qid in question_ids},
            "detail_ids": [],
            "details": {},
            "property_ids": [],
            "properties": {},
        }

        # Reset the assessment scope's answers first so the import has work to do.
        eval_in_scope(
            assessment_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=ASSESSMENT,
        )

        recorder = DialogRecorder(assessment_page)
        upload_payload(assessment_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(assessment_page, first, "yes", scope=ASSESSMENT)
        # Aligned IDs should produce no dialogs.
        assert recorder.confirms() == []


class TestAssessmentRoundtrip:
    def test_assessment_happy_path_roundtrip(self, assessment_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(assessment_page, "_riskIds", scope=ASSESSMENT)
        assert len(risk_ids) >= 1
        target = risk_ids[0]

        eval_in_scope(
            assessment_page,
            (
                f"scope.control_effectiveness[{json.dumps(target)}] = 'partial';"
                f"scope.residual_likelihood[{json.dumps(target)}] = 'rare';"
                f"scope.residual_consequence[{json.dumps(target)}] = 'minor';"
                f"scope.justifications[{json.dumps(target)}] = 'looks fine';"
            ),
            scope=ASSESSMENT,
        )

        payload = download_payload(
            assessment_page, "Save assessment", "riskformgen-assessment.json"
        )
        assert payload["format"] == "riskformgen-assessment"
        assert payload["version"] == 3
        assert payload["control_effectiveness"][target] == "partial"
        assert payload["residual_likelihood"][target] == "rare"
        assert payload["residual_consequence"][target] == "minor"
        assert payload["justifications"][target] == "looks fine"
        # Inherent block carries baked-in values for the registry to render.
        assert "inherent" in payload
        assert payload["inherent"][target]["level"] in (
            "low",
            "medium",
            "high",
            "controlled",
            "not_applicable",
        )

        eval_in_scope(
            assessment_page,
            "for (const id of scope._riskIds) {"
            "  scope.control_effectiveness[id] = '';"
            "  scope.residual_likelihood[id] = '';"
            "  scope.residual_consequence[id] = '';"
            "  scope.justifications[id] = '';"
            "}",
            scope=ASSESSMENT,
        )

        recorder = DialogRecorder(assessment_page)
        upload_payload(assessment_page, 'input[x-ref="assessmentFile"]', payload)
        wait_for_effectiveness(assessment_page, target, "partial", scope=ASSESSMENT)

        assert (
            get_scope_field(
                assessment_page,
                f"residual_likelihood[{json.dumps(target)}]",
                scope=ASSESSMENT,
            )
            == "rare"
        )
        assert (
            get_scope_field(
                assessment_page,
                f"residual_consequence[{json.dumps(target)}]",
                scope=ASSESSMENT,
            )
            == "minor"
        )
        assert (
            get_scope_field(
                assessment_page,
                f"justifications[{json.dumps(target)}]",
                scope=ASSESSMENT,
            )
            == "looks fine"
        )
        assert recorder.confirms() == []

    def test_mandated_controls_filtered_to_current_build(self, assessment_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(assessment_page, "_riskIds", scope=ASSESSMENT)
        control_ids_by_risk: dict[str, list[str]] = get_scope_field(
            assessment_page, "_controlIds", scope=ASSESSMENT
        )
        target = next(r for r in risk_ids if control_ids_by_risk.get(r))
        real_ctrl = control_ids_by_risk[target][0]
        ghost_ctrl = "__ghost_control__"

        payload = {
            "format": "riskformgen-assessment",
            "version": 3,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "risk_ids": list(risk_ids),
            "property_ids": [],
            "properties": {},
            "inherent": {r: {} for r in risk_ids},
            "control_effectiveness": {r: "" for r in risk_ids},
            "residual_likelihood": {r: "" for r in risk_ids},
            "residual_consequence": {r: "" for r in risk_ids},
            "justifications": {r: "" for r in risk_ids},
            "mandated_controls": {target: {real_ctrl: True, ghost_ctrl: True}},
            "mandated_comments": {target: {real_ctrl: "real", ghost_ctrl: "ghost"}},
        }

        recorder = DialogRecorder(assessment_page)
        upload_payload(assessment_page, 'input[x-ref="assessmentFile"]', payload)
        assessment_page.wait_for_function(
            f"{ASSESSMENT}.mandated_controls"
            f"[{json.dumps(target)}][{json.dumps(real_ctrl)}] === true"
        )

        mandated_ctrls: dict[str, bool] = get_scope_field(
            assessment_page, f"mandated_controls[{json.dumps(target)}]", scope=ASSESSMENT
        )
        assert mandated_ctrls[real_ctrl] is True
        assert ghost_ctrl not in mandated_ctrls

        mandated_comments: dict[str, str] = get_scope_field(
            assessment_page, f"mandated_comments[{json.dumps(target)}]", scope=ASSESSMENT
        )
        assert mandated_comments[real_ctrl] == "real"
        assert ghost_ctrl not in mandated_comments
        assert recorder.alerts() == []

    def test_assessment_wrong_version_shows_alert(self, assessment_page: Page) -> None:
        payload = {
            "format": "riskformgen-assessment",
            "version": 1,
            "risk_ids": [],
            "control_effectiveness": {},
            "residual_likelihood": {},
            "residual_consequence": {},
            "justifications": {},
            "mandated_controls": {},
            "mandated_comments": {},
        }
        recorder = DialogRecorder(assessment_page)
        upload_payload(assessment_page, 'input[x-ref="assessmentFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "got 1" in msg
        assert "expected 3" in msg


class TestDownloadShape:
    def test_questionnaire_export_shape(self, questionnaire_page: Page) -> None:
        payload = download_payload(questionnaire_page, "Save answers", "riskformgen-answers.json")
        assert payload["format"] == "riskformgen-answers"
        assert payload["version"] == 2
        for key in (
            "question_ids",
            "answers",
            "detail_ids",
            "details",
            "property_ids",
            "properties",
        ):
            assert key in payload, f"missing {key} in payload"
        # ISO-8601 timestamp with trailing 'Z' (JS toISOString); datetime needs +00:00.
        datetime.fromisoformat(payload["exported_at"].replace("Z", "+00:00"))

    def test_assessment_export_shape(self, assessment_page: Page) -> None:
        payload = download_payload(
            assessment_page, "Save assessment", "riskformgen-assessment.json"
        )
        assert payload["format"] == "riskformgen-assessment"
        assert payload["version"] == 3
        for key in (
            "risk_ids",
            "property_ids",
            "properties",
            "inherent",
            "control_effectiveness",
            "residual_likelihood",
            "residual_consequence",
            "justifications",
            "mandated_controls",
            "mandated_comments",
        ):
            assert key in payload, f"missing {key} in payload"
        datetime.fromisoformat(payload["exported_at"].replace("Z", "+00:00"))
