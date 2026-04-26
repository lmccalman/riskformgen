"""E2E tests for live-page user flows: question visibility, localStorage
persistence across reload, and the clear buttons.

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
)

pytestmark = pytest.mark.e2e


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
        - `is_active` is a root question that sets `physically_active`.
        - `exercises_often` is gated by `physically_active` (its target
          property `exercises_frequently` has parent `physically_active`).
        Both live in the Personal section, Activity Level subsection.
    """

    @staticmethod
    def _radio_label(page: Page, question_id: str, value: str):
        # The actual <input type="radio"> is visually hidden by CSS
        # (opacity:0; width:0). The wrapping <label> is what receives clicks
        # in the browser, and clicking it updates the bound input via
        # x-model (label-for-input semantics).
        return page.locator(f'label.radio:has(input[name="{question_id}"][value="{value}"])')

    @staticmethod
    def _wrapper_displayed(page: Page, question_id: str) -> str:
        return (
            f"window.getComputedStyle("
            f"document.querySelector('input[name=\"{question_id}\"]')"
            f".closest('[x-show]')"
            f").display"
        )

    def test_child_hidden_when_parent_unanswered(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.activeTab = 'personal';")
        # Reset answers so the parent really is unanswered (the session-scoped
        # built site can't pre-populate localStorage, but persistence within
        # a test session can carry state from prior tests).
        eval_in_scope(app_page, "for (const id of scope._questionIds) scope.answers[id] = '';")
        display = self._wrapper_displayed(app_page, "exercises_often")
        app_page.wait_for_function(f'{display} === "none"')

    def test_child_appears_after_parent_yes(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.activeTab = 'personal';")
        eval_in_scope(app_page, "for (const id of scope._questionIds) scope.answers[id] = '';")
        display = self._wrapper_displayed(app_page, "exercises_often")
        # Sanity: child wrapper hidden before clicking.
        app_page.wait_for_function(f'{display} === "none"')
        self._radio_label(app_page, "is_active", "yes").click()
        # x-model updates scope.answers.is_active → prop_physically_active
        # flips true → child's x-show expression flips true → Alpine
        # toggles display.
        app_page.wait_for_function(f'{display} !== "none"')

    def test_child_hidden_after_parent_no(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.activeTab = 'personal';")
        eval_in_scope(app_page, "for (const id of scope._questionIds) scope.answers[id] = '';")
        display = self._wrapper_displayed(app_page, "exercises_often")
        # Click "yes" first to reveal the child, then "no" to hide it again.
        self._radio_label(app_page, "is_active", "yes").click()
        app_page.wait_for_function(f'{display} !== "none"')
        self._radio_label(app_page, "is_active", "no").click()
        app_page.wait_for_function(f'{display} === "none"')


# ---------------------------------------------------------------------------
# localStorage persistence across reload (SPEC §Workflow point 3)
# ---------------------------------------------------------------------------


class TestPersistenceAcrossReload:
    """SPEC §Workflow.3: 'the site saves their state locally as they go so
    they don't lose their work when they refresh the page or come back
    later.' Pins that Alpine's `$persist` actually round-trips through real
    `localStorage` and that `init()` re-hydration on the second load
    preserves the user's prior answers."""

    def test_answers_persist_across_reload(self, app_page: Page) -> None:
        # Reset baseline.
        eval_in_scope(app_page, "for (const id of scope._questionIds) scope.answers[id] = '';")
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        first, second = question_ids[0], question_ids[1]

        eval_in_scope(
            app_page,
            f"scope.answers['{first}'] = 'yes';scope.answers['{second}'] = 'no';",
        )

        app_page.reload()
        app_page.wait_for_function(
            "() => !!document.querySelector('[x-data=app]')?._x_dataStack?.[0]"
        )

        assert get_scope_field(app_page, f"answers['{first}']") == "yes"
        assert get_scope_field(app_page, f"answers['{second}']") == "no"

    def test_assessment_persists_across_reload(self, app_page: Page) -> None:
        eval_in_scope(app_page, "scope.activeTab = 'risks';")
        risk_ids: list[str] = get_scope_field(app_page, "_riskIds")
        target = risk_ids[0]
        eval_in_scope(
            app_page,
            f"scope.control_effectiveness['{target}'] = 'partial';"
            f"scope.residual_likelihood['{target}'] = 'rare';"
            f"scope.justifications['{target}'] = 'looks fine';",
        )

        app_page.reload()
        app_page.wait_for_function(
            "() => !!document.querySelector('[x-data=app]')?._x_dataStack?.[0]"
        )

        assert get_scope_field(app_page, f"control_effectiveness['{target}']") == "partial"
        assert get_scope_field(app_page, f"residual_likelihood['{target}']") == "rare"
        assert get_scope_field(app_page, f"justifications['{target}']") == "looks fine"


# ---------------------------------------------------------------------------
# clearAnswers / clearAssessment via the buttons + native confirm dialog
# ---------------------------------------------------------------------------


class TestClearButtonsAndConfirm:
    """The clear buttons trigger native `confirm()`. The harness-layer tests
    in test_js_behaviour.py override `confirm` directly; only Playwright
    drives the real browser dialog and therefore verifies the wiring from
    button click → confirm → state reset."""

    def _populate(self, page: Page) -> None:
        eval_in_scope(page, "scope.activeTab = 'personal';")
        question_ids: list[str] = get_scope_field(page, "_questionIds")
        risk_ids: list[str] = get_scope_field(page, "_riskIds")
        eval_in_scope(
            page,
            f"scope.answers['{question_ids[0]}'] = 'yes';"
            + (
                f"scope.control_effectiveness['{risk_ids[0]}'] = 'partial';"
                f"scope.justifications['{risk_ids[0]}'] = 'note';"
                if risk_ids
                else ""
            ),
        )

    def test_clear_answers_accept_resets_state(self, app_page: Page) -> None:
        self._populate(app_page)
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        first = question_ids[0]
        recorder = DialogRecorder(app_page)
        # The "Clear all" button lives inside the answers save/load bar.
        # Two such bars exist in the page (one per section's bar plus one in
        # risks). Use first() since we're on the questionnaire side.
        app_page.get_by_role("button", name="Clear all").first.click()
        recorder.wait_for_confirms()
        # confirm accepted ⇒ state wiped to defaults.
        app_page.wait_for_function(
            f"document.querySelector('[x-data=app]')._x_dataStack[0].answers['{first}'] === ''"
        )
        assert get_scope_field(app_page, f"answers['{first}']") == ""

    def test_clear_answers_cancel_keeps_state(self, app_page: Page) -> None:
        self._populate(app_page)
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        first = question_ids[0]
        recorder = DialogRecorder(app_page, accept_confirm=False)
        app_page.get_by_role("button", name="Clear all").first.click()
        recorder.wait_for_confirms()
        # confirm cancelled ⇒ state untouched.
        assert get_scope_field(app_page, f"answers['{first}']") == "yes"

    def test_clear_assessment_keeps_answers(self, app_page: Page) -> None:
        risk_ids: list[str] = get_scope_field(app_page, "_riskIds")
        if not risk_ids:
            pytest.skip("no risks in current build — clearAssessment not exercised")
        self._populate(app_page)
        question_ids: list[str] = get_scope_field(app_page, "_questionIds")
        first = question_ids[0]
        target = risk_ids[0]
        eval_in_scope(app_page, "scope.activeTab = 'risks';")
        recorder = DialogRecorder(app_page)
        app_page.get_by_role("button", name="Clear assessment").click()
        recorder.wait_for_confirms()
        app_page.wait_for_function(
            f"document.querySelector('[x-data=app]')._x_dataStack[0]"
            f".control_effectiveness['{target}'] === ''"
        )
        # Assessment cleared, but answers preserved.
        assert get_scope_field(app_page, f"answers['{first}']") == "yes"
        assert get_scope_field(app_page, f"control_effectiveness['{target}']") == ""
