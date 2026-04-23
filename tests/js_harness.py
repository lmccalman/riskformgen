# pyright: reportReturnType=false, reportCallIssue=false, reportArgumentType=false
"""Test harness that evaluates the compiled Alpine factory in-process.

`render_app_js()` emits a standalone JS file that registers the Alpine
component factory via `Alpine.data('app', factory)` inside an `alpine:init`
event listener. This harness stubs `Alpine` and `document.addEventListener`
so the factory is captured, then invokes it to obtain a plain scope object
whose `prop_*`, `ctrl_*`, and risk getters can be exercised directly against
the `answers` / `details` / `control_effectiveness` state.

The substring-based tests in `test_render.py` and `test_models.py` pin the
compiler shape; this module lets tests assert on what the compiled code
*does* at runtime.
"""

from __future__ import annotations

import json
import re
from typing import Any

from py_mini_racer import MiniRacer

from models import Control, Detail, Property, Risk, Section
from render import render_app_js

_BOOTSTRAP_JS = """
const __state = { factory: null };
const __persistedState = {};
const Alpine = {
    $persist: (initial) => ({
        as: (key) => (key in __persistedState) ? __persistedState[key] : initial
    }),
    data: (_name, factory) => { __state.factory = factory; }
};
const document = {
    addEventListener: (event, cb) => { if (event === 'alpine:init') cb(); }
};
const alert = () => {};
const confirm = () => true;
"""

# Visibility / show expressions emitted by the renderer use bare identifiers
# (`prop_foo`, `ctrl_bar`) because Alpine evaluates them with the component
# scope bound as `this` via `with`. To evaluate the same expressions from
# outside the component, we rewrite bare references to `scope.<name>`.
_BARE_REF = re.compile(r"\b(prop_|ctrl_)\w+\b")


def _qualify(expr: str) -> str:
    return _BARE_REF.sub(lambda m: f"scope.{m.group(0)}", expr)


class Scope:
    """Handle on a live Alpine scope evaluated inside a V8 context."""

    def __init__(self, ctx: MiniRacer) -> None:
        self._ctx = ctx

    # --- writers ---------------------------------------------------------

    def set_answer(self, qid: str, val: str) -> None:
        self._ctx.eval(f"scope.answers[{json.dumps(qid)}] = {json.dumps(val)};")

    def set_detail(self, did: str, val: str) -> None:
        self._ctx.eval(f"scope.details[{json.dumps(did)}] = {json.dumps(val)};")

    def set_effectiveness(self, rid: str, val: str) -> None:
        self._ctx.eval(f"scope.control_effectiveness[{json.dumps(rid)}] = {json.dumps(val)};")

    def set_residual(self, rid: str, likelihood: str, consequence: str) -> None:
        self._ctx.eval(f"scope.residual_likelihood[{json.dumps(rid)}] = {json.dumps(likelihood)};")
        self._ctx.eval(
            f"scope.residual_consequence[{json.dumps(rid)}] = {json.dumps(consequence)};"
        )

    # --- readers ---------------------------------------------------------

    def prop(self, pid: str) -> bool | None:
        return self._ctx.eval(f"scope.prop_{pid}")

    def ctrl(self, cid: str) -> bool:
        return self._ctx.eval(f"scope.ctrl_{cid}")

    def risk(self, rid: str) -> dict[str, Any]:
        return dict(self._ctx.eval(f"scope.{rid}"))

    def residual(self, rid: str) -> dict[str, Any]:
        return dict(self._ctx.eval(f"scope.{rid}_residual"))

    def visibility(self, expr: str) -> bool:
        """Evaluate a `visibility_js` / `show_js` expression against the scope."""
        return self._ctx.eval(_qualify(expr))

    def eval(self, expr: str) -> Any:
        """Escape hatch: evaluate an arbitrary JS expression in the same context."""
        return self._ctx.eval(expr)


def build_scope(
    sections: list[Section],
    properties: list[Property],
    risks: list[Risk],
    controls: list[Control] | None = None,
    details: list[Detail] | None = None,
    persisted_state: dict[str, object] | None = None,
) -> Scope:
    """Compile the Alpine factory for the given form and return a live Scope.

    `persisted_state` maps `$persist` keys (e.g. `'_x_answers'`) to the value
    that would be restored from `localStorage`. Unset keys fall back to the
    factory seed. After the scope is constructed, `scope.init()` is invoked
    so the post-hydration migration pass runs before readers see state.
    """
    app_js = render_app_js(sections, risks, controls, properties, details)
    ctx = MiniRacer()
    ctx.eval(_BOOTSTRAP_JS)
    if persisted_state is not None:
        ctx.eval(f"Object.assign(__persistedState, {json.dumps(persisted_state)});")
    ctx.eval(app_js)
    ctx.eval("var scope = __state.factory();")
    ctx.eval("if (typeof scope.init === 'function') scope.init();")
    return Scope(ctx)
