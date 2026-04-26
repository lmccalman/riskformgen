"""Shared helpers for e2e tests.

The e2e test files share a small surface for poking at the live Alpine scope,
uploading/downloading JSON, and capturing dialogs. They live here rather than
in `conftest.py` so they can be imported by name (pytest's fixture discovery
doesn't fit dialog/scope helpers, which aren't fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Dialog, Page

SCOPE = "document.querySelector('[x-data=app]')._x_dataStack[0]"


def get_scope_field(page: Page, field: str) -> Any:
    return page.evaluate(f"{SCOPE}.{field}")


def eval_in_scope(page: Page, body: str) -> None:
    page.evaluate(f"const scope = {SCOPE}; {body}")


def upload_payload(
    page: Page, selector: str, payload: dict | str, *, filename: str = "import.json"
) -> None:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    page.locator(selector).set_input_files(
        files=[
            {
                "name": filename,
                "mimeType": "application/json",
                "buffer": raw.encode(),
            }
        ]
    )


def download_payload(page: Page, button_name: str, expected_filename: str) -> dict:
    with page.expect_download() as info:
        page.get_by_role("button", name=button_name).click()
    download = info.value
    assert download.suggested_filename == expected_filename
    path = download.path()
    assert path is not None
    return json.loads(Path(path).read_text())


class DialogRecorder:
    """Attach to page.on('dialog'). Captures dialogs and applies a per-type policy.

    Default policy: accept confirms and alerts. Tests that need to exercise
    "user clicks cancel" set ``accept_confirm=False``.

    Wait helpers pump Playwright's event queue via ``page.wait_for_timeout``
    so dialog events are actually delivered — a plain ``time.sleep`` would
    leave events stuck in the client-side queue.
    """

    def __init__(self, page: Page, *, accept_confirm: bool = True) -> None:
        self.captured: list[dict[str, str]] = []
        self._page = page
        self._accept_confirm = accept_confirm
        page.on("dialog", self._handle)

    def _handle(self, dialog: Dialog) -> None:
        self.captured.append({"type": dialog.type, "message": dialog.message})
        if dialog.type == "confirm" and not self._accept_confirm:
            dialog.dismiss()
        else:
            dialog.accept()

    def confirms(self) -> list[dict[str, str]]:
        return [d for d in self.captured if d["type"] == "confirm"]

    def alerts(self) -> list[dict[str, str]]:
        return [d for d in self.captured if d["type"] == "alert"]

    def wait_for_alerts(self, count: int = 1, timeout_ms: int = 5000) -> None:
        self._wait_for(lambda: len(self.alerts()) >= count, timeout_ms)

    def wait_for_confirms(self, count: int = 1, timeout_ms: int = 5000) -> None:
        self._wait_for(lambda: len(self.confirms()) >= count, timeout_ms)

    def _wait_for(self, predicate, timeout_ms: int) -> None:
        elapsed = 0
        step = 20
        while elapsed < timeout_ms:
            if predicate():
                return
            self._page.wait_for_timeout(step)
            elapsed += step
        raise AssertionError("dialog did not arrive within timeout")


def wait_for_answer(page: Page, question_id: str, expected: str) -> None:
    page.wait_for_function(
        f"{SCOPE}.answers[{json.dumps(question_id)}] === {json.dumps(expected)}"
    )


def wait_for_effectiveness(page: Page, risk_id: str, expected: str) -> None:
    page.wait_for_function(
        f"{SCOPE}.control_effectiveness[{json.dumps(risk_id)}] === {json.dumps(expected)}"
    )
