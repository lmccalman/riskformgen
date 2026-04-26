"""E2E tests for live-page user flows: landing navigation, question
visibility, localStorage persistence across reload, and the clear buttons.

These complement `test_save_load_e2e.py` (which focuses on JSON
import/export). The flows here can only be exercised in a real browser:
visibility goes through Alpine `x-show` → CSS `display:none`; persistence
goes through the `$persist` plugin → real `localStorage`; clear buttons
trigger native `confirm` dialogs.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.e2e._helpers import (
    DialogRecorder,
    eval_in_scope,
    get_scope_field,
    scope_selector,
)

pytestmark = pytest.mark.e2e

QUESTIONNAIRE = scope_selector("questionnaire")
ASSESSMENT = scope_selector("assessment")


# ---------------------------------------------------------------------------
# Landing → tool navigation
# ---------------------------------------------------------------------------


class TestLandingNavigation:
    """The landing page links to the three tool surfaces. Pins that the
    links are present, navigable, and that each lands on the page whose
    Alpine factory the tool exposes."""

    def test_landing_has_three_tool_links(self, landing_page: Page) -> None:
        assert landing_page.locator('a[href="questionnaire.html"]').count() >= 1
        assert landing_page.locator('a[href="assessment.html"]').count() >= 1
        assert landing_page.locator('a[href="registry.html"]').count() >= 1

    def test_questionnaire_link_loads_questionnaire_factory(self, landing_page: Page) -> None:
        landing_page.locator('a[href="questionnaire.html"]').first.click()
        landing_page.wait_for_url("**/questionnaire.html")
        landing_page.wait_for_function(
            "() => !!document.querySelector('[x-data=questionnaire]')?._x_dataStack?.[0]"
        )

    def test_assessment_link_loads_assessment_factory(self, landing_page: Page) -> None:
        landing_page.locator('a[href="assessment.html"]').first.click()
        landing_page.wait_for_url("**/assessment.html")
        landing_page.wait_for_function(
            "() => !!document.querySelector('[x-data=assessment]')?._x_dataStack?.[0]"
        )

    def test_registry_link_loads_placeholder(self, landing_page: Page) -> None:
        landing_page.locator('a[href="registry.html"]').first.click()
        landing_page.wait_for_url("**/registry.html")
        # Placeholder copy is present.
        body_text = landing_page.text_content("body") or ""
        assert "Registry" in body_text


# ---------------------------------------------------------------------------
# State isolation between tools (per-tool localStorage prefix)
# ---------------------------------------------------------------------------


class TestPerToolStorageIsolation:
    """SPEC §Workflow makes the three tools distinct; the
    `_x_q_*` / `_x_a_*` prefix split is what stops state from bleeding
    between them. Pin that an answer entered on the questionnaire does
    not surface in the assessment view's loaded answers."""

    def test_questionnaire_answer_does_not_appear_in_assessment(
        self, page: Page, site_url: str
    ) -> None:
        # Fresh start: clear any prior storage from this site origin.
        page.goto(site_url + "/questionnaire.html")
        page.wait_for_function(
            "() => !!document.querySelector('[x-data=questionnaire]')?._x_dataStack?.[0]"
        )
        page.evaluate("localStorage.clear();")
        page.reload()
        page.wait_for_function(
            "() => !!document.querySelector('[x-data=questionnaire]')?._x_dataStack?.[0]"
        )

        question_ids: list[str] = page.evaluate(f"{QUESTIONNAIRE}._questionIds")
        assert question_ids
        target = question_ids[0]
        eval_in_scope(
            page,
            f"scope.answers['{target}'] = 'yes';",
            scope=QUESTIONNAIRE,
        )

        # Now switch to the assessment view; its answers must be untouched.
        page.goto(site_url + "/assessment.html")
        page.wait_for_function(
            "() => !!document.querySelector('[x-data=assessment]')?._x_dataStack?.[0]"
        )
        loaded_answer = page.evaluate(f"{ASSESSMENT}.answers['{target}']")
        assert loaded_answer == "", "Assessment answers should not inherit questionnaire state"


# ---------------------------------------------------------------------------
# Question visibility through the DOM (SPEC §Concepts → Questionnaire)
# ---------------------------------------------------------------------------


class TestVisibilityViaDom:
    """Pins the closed loop between Alpine state and DOM `x-show` for child
    questions. The substring layer confirms `x-show` is emitted with the
    right expression; the harness layer confirms the expression evaluates
    correctly. Only Playwright can verify Alpine actually toggles the DOM
    element when state changes.

    Form structure under test (form/sections.yaml + form/properties.yaml):
        - `q_is_active` is a root question that sets `physically_active`.
        - `q_exercises_often` is gated by `physically_active` (its target
          property `exercises_frequently` has parent `physically_active`).
        Both live in the Activity & Movement section, General Activity
        subsection.
    """

    @staticmethod
    def _radio_label(page: Page, question_id: str, value: str):
        return page.locator(f'label.radio:has(input[name="{question_id}"][value="{value}"])')

    @staticmethod
    def _wrapper_displayed(page: Page, question_id: str) -> str:
        return (
            f"window.getComputedStyle("
            f"document.querySelector('input[name=\"{question_id}\"]')"
            f".closest('[x-show]')"
            f").display"
        )

    def test_child_hidden_when_parent_unanswered(self, questionnaire_page: Page) -> None:
        eval_in_scope(questionnaire_page, "scope.activeTab = 'activity';", scope=QUESTIONNAIRE)
        # Reset answers — session-scoped built site can't pre-populate
        # localStorage, but persistence within a session can carry state
        # from prior tests.
        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )
        display = self._wrapper_displayed(questionnaire_page, "q_exercises_often")
        questionnaire_page.wait_for_function(f'{display} === "none"')

    def test_child_appears_after_parent_yes(self, questionnaire_page: Page) -> None:
        eval_in_scope(questionnaire_page, "scope.activeTab = 'activity';", scope=QUESTIONNAIRE)
        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )
        display = self._wrapper_displayed(questionnaire_page, "q_exercises_often")
        questionnaire_page.wait_for_function(f'{display} === "none"')
        self._radio_label(questionnaire_page, "q_is_active", "yes").click()
        questionnaire_page.wait_for_function(f'{display} !== "none"')

    def test_child_hidden_after_parent_no(self, questionnaire_page: Page) -> None:
        eval_in_scope(questionnaire_page, "scope.activeTab = 'activity';", scope=QUESTIONNAIRE)
        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )
        display = self._wrapper_displayed(questionnaire_page, "q_exercises_often")
        self._radio_label(questionnaire_page, "q_is_active", "yes").click()
        questionnaire_page.wait_for_function(f'{display} !== "none"')
        self._radio_label(questionnaire_page, "q_is_active", "no").click()
        questionnaire_page.wait_for_function(f'{display} === "none"')


# ---------------------------------------------------------------------------
# localStorage persistence across reload (SPEC §Workflow point 3)
# ---------------------------------------------------------------------------


class TestPersistenceAcrossReload:
    """SPEC §Workflow.3: 'the site saves their state locally as they go so
    they don't lose their work when they refresh the page or come back
    later.' Pins that Alpine's `$persist` actually round-trips through real
    `localStorage` and that `init()` re-hydration on the second load
    preserves the user's prior answers."""

    def test_questionnaire_answers_persist_across_reload(self, questionnaire_page: Page) -> None:
        eval_in_scope(
            questionnaire_page,
            "for (const id of scope._questionIds) scope.answers[id] = '';",
            scope=QUESTIONNAIRE,
        )
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        first, second = question_ids[0], question_ids[1]

        eval_in_scope(
            questionnaire_page,
            f"scope.answers['{first}'] = 'yes';scope.answers['{second}'] = 'no';",
            scope=QUESTIONNAIRE,
        )

        questionnaire_page.reload()
        questionnaire_page.wait_for_function(
            "() => !!document.querySelector('[x-data=questionnaire]')?._x_dataStack?.[0]"
        )

        assert (
            get_scope_field(questionnaire_page, f"answers['{first}']", scope=QUESTIONNAIRE)
            == "yes"
        )
        assert (
            get_scope_field(questionnaire_page, f"answers['{second}']", scope=QUESTIONNAIRE)
            == "no"
        )

    def test_assessment_persists_across_reload(self, assessment_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(assessment_page, "_riskIds", scope=ASSESSMENT)
        target = risk_ids[0]
        eval_in_scope(
            assessment_page,
            f"scope.control_effectiveness['{target}'] = 'partial';"
            f"scope.residual_likelihood['{target}'] = 'rare';"
            f"scope.justifications['{target}'] = 'looks fine';",
            scope=ASSESSMENT,
        )

        assessment_page.reload()
        assessment_page.wait_for_function(
            "() => !!document.querySelector('[x-data=assessment]')?._x_dataStack?.[0]"
        )

        assert (
            get_scope_field(
                assessment_page, f"control_effectiveness['{target}']", scope=ASSESSMENT
            )
            == "partial"
        )
        assert (
            get_scope_field(assessment_page, f"residual_likelihood['{target}']", scope=ASSESSMENT)
            == "rare"
        )
        assert (
            get_scope_field(assessment_page, f"justifications['{target}']", scope=ASSESSMENT)
            == "looks fine"
        )


# ---------------------------------------------------------------------------
# clearAnswers / clearAssessment via the buttons + native confirm dialog
# ---------------------------------------------------------------------------


class TestClearButtonsAndConfirm:
    """The clear buttons trigger native `confirm()`. The harness-layer tests
    in test_js_behaviour.py override `confirm` directly; only Playwright
    drives the real browser dialog and therefore verifies the wiring from
    button click → confirm → state reset."""

    def test_clear_answers_accept_resets_state(self, questionnaire_page: Page) -> None:
        eval_in_scope(questionnaire_page, "scope.activeTab = 'activity';", scope=QUESTIONNAIRE)
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        first = question_ids[0]
        eval_in_scope(
            questionnaire_page,
            f"scope.answers['{first}'] = 'yes';",
            scope=QUESTIONNAIRE,
        )

        recorder = DialogRecorder(questionnaire_page)
        questionnaire_page.get_by_role("button", name="Clear all").first.click()
        recorder.wait_for_confirms()
        questionnaire_page.wait_for_function(f"{QUESTIONNAIRE}.answers['{first}'] === ''")
        assert (
            get_scope_field(questionnaire_page, f"answers['{first}']", scope=QUESTIONNAIRE) == ""
        )

    def test_clear_answers_cancel_keeps_state(self, questionnaire_page: Page) -> None:
        eval_in_scope(questionnaire_page, "scope.activeTab = 'activity';", scope=QUESTIONNAIRE)
        question_ids: list[str] = get_scope_field(
            questionnaire_page, "_questionIds", scope=QUESTIONNAIRE
        )
        first = question_ids[0]
        eval_in_scope(
            questionnaire_page,
            f"scope.answers['{first}'] = 'yes';",
            scope=QUESTIONNAIRE,
        )

        recorder = DialogRecorder(questionnaire_page, accept_confirm=False)
        questionnaire_page.get_by_role("button", name="Clear all").first.click()
        recorder.wait_for_confirms()
        assert (
            get_scope_field(questionnaire_page, f"answers['{first}']", scope=QUESTIONNAIRE)
            == "yes"
        )

    def test_clear_assessment_keeps_loaded_answers(self, assessment_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(assessment_page, "_riskIds", scope=ASSESSMENT)
        if not risk_ids:
            pytest.skip("no risks in current build — clearAssessment not exercised")
        target = risk_ids[0]
        question_ids: list[str] = get_scope_field(
            assessment_page, "_questionIds", scope=ASSESSMENT
        )
        first = question_ids[0]
        eval_in_scope(
            assessment_page,
            f"scope.answers['{first}'] = 'yes';"
            f"scope.control_effectiveness['{target}'] = 'partial';"
            f"scope.justifications['{target}'] = 'note';",
            scope=ASSESSMENT,
        )

        recorder = DialogRecorder(assessment_page)
        assessment_page.get_by_role("button", name="Clear assessment").click()
        recorder.wait_for_confirms()
        assessment_page.wait_for_function(f"{ASSESSMENT}.control_effectiveness['{target}'] === ''")
        # Assessment cleared, but the loaded answers stay (they're loaded
        # data, not assessor input).
        assert get_scope_field(assessment_page, f"answers['{first}']", scope=ASSESSMENT) == "yes"
        assert (
            get_scope_field(
                assessment_page, f"control_effectiveness['{target}']", scope=ASSESSMENT
            )
            == ""
        )
