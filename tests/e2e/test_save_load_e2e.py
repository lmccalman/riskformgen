import json
from datetime import datetime

import pytest
from playwright.sync_api import Page

from tests.e2e._helpers import (
    SCOPE,
    DialogRecorder,
    download_payload,
    eval_in_scope,
    get_scope_field,
    upload_payload,
    wait_for_answer,
    wait_for_effectiveness,
)

pytestmark = pytest.mark.e2e


class TestAnswersRoundtrip:
    def test_happy_path_roundtrip(self, app_page: Page) -> None:
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        assert len(question_ids) >= 2
        first, second = question_ids[0], question_ids[1]

        eval_in_scope(
            app_page,
            f"scope.answers[{json.dumps(first)}] = 'yes';"
            f"scope.answers[{json.dumps(second)}] = 'no';",
        )

        payload = download_payload(app_page, "Save answers", "riskformgen-answers.json")
        assert payload["format"] == "riskformgen-answers"
        assert payload["version"] == 1
        assert payload["answers"][first] == "yes"
        assert payload["answers"][second] == "no"

        eval_in_scope(
            app_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
        )
        assert get_scope_field(app_page, f"answers[{json.dumps(first)}]") == ""

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(app_page, first, "yes")
        wait_for_answer(app_page, second, "no")
        assert recorder.captured == []

    def test_silent_apply_when_ids_align(self, app_page: Page) -> None:
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        detail_ids: list[str] = get_scope_field(app_page, "_detailIds")
        payload = {
            "format": "riskformgen-answers",
            "version": 1,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": list(question_ids),
            "answers": {qid: "yes" for qid in question_ids},
            "detail_ids": list(detail_ids),
            "details": {did: "note" for did in detail_ids},
        }

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(app_page, question_ids[0], "yes")
        assert recorder.confirms() == []

    def test_invalid_json_shows_alert(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.answers[scope._questionIds[0]] = 'preset';")
        first: str = get_scope_field(app_page, "_questionIds[0]")

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', "not json{")
        recorder.wait_for_alerts()
        assert "Invalid JSON" in recorder.alerts()[0]["message"]
        assert get_scope_field(app_page, f"answers[{json.dumps(first)}]") == "preset"

    def test_wrong_format_shows_alert(self, app_page: Page) -> None:
        payload = {"format": "something-else", "version": 1, "question_ids": [], "answers": {}}
        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "riskformgen-answers" in msg
        assert "answers" in msg

    def test_wrong_version_shows_alert(self, app_page: Page) -> None:
        payload = {
            "format": "riskformgen-answers",
            "version": 99,
            "question_ids": [],
            "answers": {},
        }
        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "99" in msg
        assert "expected 1" in msg

    def test_added_ids_prompt_confirm_accept_applies_partial(self, app_page: Page) -> None:
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        assert len(question_ids) >= 3
        kept = question_ids[:2]
        payload = {
            "format": "riskformgen-answers",
            "version": 1,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": list(kept),
            "answers": {qid: "yes" for qid in kept},
            "detail_ids": [],
            "details": {},
        }

        eval_in_scope(
            app_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
        )

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(app_page, kept[0], "yes")

        assert len(recorder.confirms()) == 1
        msg = recorder.confirms()[0]["message"]
        assert "new since export" in msg
        assert str(len(question_ids) - len(kept)) in msg

        answers: dict[str, str] = get_scope_field(app_page, "answers")
        for qid in kept:
            assert answers[qid] == "yes"
        for qid in question_ids[2:]:
            assert answers[qid] == ""

    def test_removed_ids_prompt_confirm_shows_skipped_count(self, app_page: Page) -> None:
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        extra_id = "nonexistent_question_xyz"
        file_ids = [*question_ids, extra_id]
        payload = {
            "format": "riskformgen-answers",
            "version": 1,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": file_ids,
            "answers": {**{qid: "yes" for qid in question_ids}, extra_id: "yes"},
            "detail_ids": [],
            "details": {},
        }

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        wait_for_answer(app_page, question_ids[0], "yes")

        assert len(recorder.confirms()) == 1
        assert "skipped (removed)" in recorder.confirms()[0]["message"]

    def test_user_cancels_confirm_leaves_state_unchanged(self, app_page: Page) -> None:
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        first = question_ids[0]
        eval_in_scope(app_page, f"scope.answers[{json.dumps(first)}] = 'baseline';")
        payload = {
            "format": "riskformgen-answers",
            "version": 1,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "question_ids": question_ids[:1],
            "answers": {first: "should-not-apply"},
            "detail_ids": [],
            "details": {},
        }

        recorder = DialogRecorder(app_page, accept_confirm=False)
        upload_payload(app_page, 'input[x-ref="answersFile"]', payload)
        recorder.wait_for_confirms()

        assert get_scope_field(app_page, f"answers[{json.dumps(first)}]") == "baseline"


class TestAssessmentRoundtrip:
    @pytest.fixture(autouse=True)
    def _on_risks_tab(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.activeTab = 'risks';")

    def test_assessment_happy_path_roundtrip(self, app_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(app_page, "_riskIds")
        assert len(risk_ids) >= 1
        target = risk_ids[0]

        eval_in_scope(
            app_page,
            (
                f"scope.control_effectiveness[{json.dumps(target)}] = 'partial';"
                f"scope.residual_likelihood[{json.dumps(target)}] = 'rare';"
                f"scope.residual_consequence[{json.dumps(target)}] = 'minor';"
                f"scope.justifications[{json.dumps(target)}] = 'looks fine';"
            ),
        )

        payload = download_payload(app_page, "Save assessment", "riskformgen-assessment.json")
        assert payload["format"] == "riskformgen-assessment"
        assert payload["version"] == 2
        assert payload["control_effectiveness"][target] == "partial"
        assert payload["residual_likelihood"][target] == "rare"
        assert payload["residual_consequence"][target] == "minor"
        assert payload["justifications"][target] == "looks fine"

        eval_in_scope(
            app_page,
            "for (const id of scope._riskIds) {"
            "  scope.control_effectiveness[id] = '';"
            "  scope.residual_likelihood[id] = '';"
            "  scope.residual_consequence[id] = '';"
            "  scope.justifications[id] = '';"
            "}",
        )

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="assessmentFile"]', payload)
        wait_for_effectiveness(app_page, target, "partial")

        assert get_scope_field(app_page, f"residual_likelihood[{json.dumps(target)}]") == "rare"
        assert get_scope_field(app_page, f"residual_consequence[{json.dumps(target)}]") == "minor"
        assert get_scope_field(app_page, f"justifications[{json.dumps(target)}]") == "looks fine"
        assert recorder.confirms() == []

    def test_mandated_controls_filtered_to_current_build(self, app_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(app_page, "_riskIds")
        control_ids_by_risk: dict[str, list[str]] = get_scope_field(app_page, "_controlIds")
        target = next(r for r in risk_ids if control_ids_by_risk.get(r))
        real_ctrl = control_ids_by_risk[target][0]
        ghost_ctrl = "__ghost_control__"

        payload = {
            "format": "riskformgen-assessment",
            "version": 2,
            "exported_at": "2025-01-01T00:00:00.000Z",
            "risk_ids": list(risk_ids),
            "control_effectiveness": {r: "" for r in risk_ids},
            "residual_likelihood": {r: "" for r in risk_ids},
            "residual_consequence": {r: "" for r in risk_ids},
            "justifications": {r: "" for r in risk_ids},
            "mandated_controls": {target: {real_ctrl: True, ghost_ctrl: True}},
            "mandated_comments": {target: {real_ctrl: "real", ghost_ctrl: "ghost"}},
        }

        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="assessmentFile"]', payload)
        app_page.wait_for_function(
            f"{SCOPE}.mandated_controls[{json.dumps(target)}][{json.dumps(real_ctrl)}] === true"
        )

        mandated_ctrls: dict[str, bool] = get_scope_field(
            app_page, f"mandated_controls[{json.dumps(target)}]"
        )
        assert mandated_ctrls[real_ctrl] is True
        assert ghost_ctrl not in mandated_ctrls

        mandated_comments: dict[str, str] = get_scope_field(
            app_page, f"mandated_comments[{json.dumps(target)}]"
        )
        assert mandated_comments[real_ctrl] == "real"
        assert ghost_ctrl not in mandated_comments
        assert recorder.alerts() == []

    def test_assessment_wrong_version_shows_alert(self, app_page: Page) -> None:
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
        recorder = DialogRecorder(app_page)
        upload_payload(app_page, 'input[x-ref="assessmentFile"]', payload)
        recorder.wait_for_alerts()
        msg = recorder.alerts()[0]["message"]
        assert "got 1" in msg
        assert "expected 2" in msg


class TestDownloadShape:
    @pytest.mark.parametrize(
        ("button", "filename", "fmt", "version", "required_keys"),
        [
            (
                "Save answers",
                "riskformgen-answers.json",
                "riskformgen-answers",
                1,
                ["question_ids", "answers", "detail_ids", "details"],
            ),
            (
                "Save assessment",
                "riskformgen-assessment.json",
                "riskformgen-assessment",
                2,
                [
                    "risk_ids",
                    "control_effectiveness",
                    "residual_likelihood",
                    "residual_consequence",
                    "justifications",
                    "mandated_controls",
                    "mandated_comments",
                ],
            ),
        ],
    )
    def test_export_payload_shape(
        self,
        app_page: Page,
        button: str,
        filename: str,
        fmt: str,
        version: int,
        required_keys: list[str],
    ) -> None:
        if "assessment" in fmt:
            eval_in_scope(app_page, "scope.activeTab = 'risks';")

        payload = download_payload(app_page, button, filename)
        assert payload["format"] == fmt
        assert payload["version"] == version
        for key in required_keys:
            assert key in payload, f"missing {key} in payload"

        # ISO-8601 timestamp with trailing 'Z' (JS toISOString); datetime needs +00:00.
        datetime.fromisoformat(payload["exported_at"].replace("Z", "+00:00"))
