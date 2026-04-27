"""Take a tour of the built site and save PNGs of each surface for visual debugging.

Usage:
    uv run python scripts/screenshot.py [--out DIR]

Builds the site into a temp dir, serves it on a random localhost port, then
drives a headless Chromium (via Playwright) to capture each visual surface:
landing, questionnaire (empty / filled / debug), assessment (empty / loaded /
single risk card / answers tab), and the registry (index + the example-system
page). PNGs land in ``--out`` (default ``tmp/screenshots/``), where Claude can
read them directly with the Read tool.

The "filled" states inject the committed ``registry/example-system`` JSONs
directly into the live Alpine scope — no file-upload roundtrip — so the live
shots reflect the same data the static registry pages already render.

Requires Chromium to be installed for Playwright once:
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402
import main as main_module  # noqa: E402
from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "tmp" / "screenshots"
EXAMPLE_DIR = REPO_ROOT / "registry" / "example-system"
VIEWPORT = {"width": 1280, "height": 900}


@contextmanager
def serve(directory: Path) -> Iterator[str]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def build_site(target: Path) -> None:
    original = config.output_dir
    config.output_dir = target
    try:
        main_module.main()
    finally:
        config.output_dir = original


def _scope(name: str) -> str:
    return f"document.querySelector('[x-data={name}]')._x_dataStack[0]"


def wait_for_factory(page: Page, name: str) -> None:
    page.wait_for_function(
        f"() => !!document.querySelector('[x-data={name}]')?._x_dataStack?.[0]"
    )


def shot(out: Path, name: str, page: Page, *, locator: str | None = None) -> None:
    path = out / f"{name}.png"
    if locator is not None:
        el = page.locator(locator).first
        el.scroll_into_view_if_needed()
        el.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=True)
    print(f"  -> {path.relative_to(REPO_ROOT)}")


SEED_QUESTIONNAIRE_JS = """
(scope, q) => {
  Object.assign(scope.answers, q.answers || {});
  Object.assign(scope.details, q.details || {});
  if (typeof q.system_name === 'string') scope.system_name = q.system_name;
  if (typeof q.system_owner === 'string') scope.system_owner = q.system_owner;
}
"""

SEED_ASSESSMENT_JS = """
(scope, a) => {
  Object.assign(scope.control_effectiveness, a.control_effectiveness || {});
  Object.assign(scope.residual_likelihood, a.residual_likelihood || {});
  Object.assign(scope.residual_consequence, a.residual_consequence || {});
  Object.assign(scope.justifications, a.justifications || {});
  for (const r in (a.mandated_controls || {})) {
    scope.mandated_controls[r] = scope.mandated_controls[r] || {};
    Object.assign(scope.mandated_controls[r], a.mandated_controls[r]);
  }
  for (const r in (a.mandated_comments || {})) {
    scope.mandated_comments[r] = scope.mandated_comments[r] || {};
    Object.assign(scope.mandated_comments[r], a.mandated_comments[r]);
  }
  if (typeof a.aggregate_residual_level === 'string') {
    scope.aggregate_residual_level = a.aggregate_residual_level;
  }
  if (typeof a.aggregate_residual_justification === 'string') {
    scope.aggregate_residual_justification = a.aggregate_residual_justification;
  }
}
"""


def seed_questionnaire(page: Page, factory: str, qjson: dict) -> None:
    page.evaluate(
        f"(q) => ({SEED_QUESTIONNAIRE_JS})({_scope(factory)}, q)",
        qjson,
    )


def seed_assessment(page: Page, ajson: dict) -> None:
    page.evaluate(
        f"(a) => ({SEED_ASSESSMENT_JS})({_scope('assessment')}, a)",
        ajson,
    )


def capture(browser: Browser, site_url: str, out: Path) -> None:
    qjson = json.loads((EXAMPLE_DIR / "questionnaire.json").read_text())
    ajson = json.loads((EXAMPLE_DIR / "assessment.json").read_text())

    # 1. Landing
    print("Landing")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/index.html")
    page.wait_for_load_state("networkidle")
    shot(out, "01-landing", page)
    shot(out, "02-landing-tool-cards", page, locator="section.tool-cards")
    ctx.close()

    # 2. Questionnaire (empty)
    print("Questionnaire (empty)")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/questionnaire.html")
    wait_for_factory(page, "questionnaire")
    shot(out, "03-questionnaire-empty", page)
    page.evaluate(f"{_scope('questionnaire')}.activeTab = 'debug'")
    page.wait_for_timeout(100)
    shot(out, "04-questionnaire-debug", page)
    ctx.close()

    # 3. Questionnaire (filled)
    print("Questionnaire (filled)")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/questionnaire.html")
    wait_for_factory(page, "questionnaire")
    seed_questionnaire(page, "questionnaire", qjson)
    page.wait_for_timeout(150)
    shot(out, "05-questionnaire-filled", page)
    ctx.close()

    # 4. Assessment (empty)
    print("Assessment (empty)")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/assessment.html")
    wait_for_factory(page, "assessment")
    shot(out, "06-assessment-empty", page)
    ctx.close()

    # 5. Assessment (loaded)
    print("Assessment (loaded)")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/assessment.html")
    wait_for_factory(page, "assessment")
    seed_questionnaire(page, "assessment", qjson)
    seed_assessment(page, ajson)
    page.wait_for_timeout(200)
    shot(out, "07-assessment-loaded", page)
    shot(
        out,
        "08-assessment-risk-card",
        page,
        locator=".card.mb-4:not(.aggregate-residual-card)",
    )
    page.evaluate(f"{_scope('assessment')}.activeTab = 'answers'")
    page.wait_for_timeout(100)
    shot(out, "09-assessment-answers-tab", page)
    ctx.close()

    # 6. Registry index
    print("Registry index")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/registry.html")
    page.wait_for_load_state("networkidle")
    shot(out, "10-registry-index", page)
    ctx.close()

    # 7. Registry system page
    print("Registry system (example-system)")
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    page.goto(f"{site_url}/registry/example-system.html")
    page.wait_for_load_state("networkidle")
    shot(out, "11-registry-system", page)
    ctx.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory for PNGs (default: {DEFAULT_OUT.relative_to(REPO_ROOT)})",
    )
    args = parser.parse_args()

    out: Path = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    build_dir = REPO_ROOT / "tmp" / "screenshot-build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    print(f"Building site -> {build_dir.relative_to(REPO_ROOT)}")
    build_site(build_dir)

    try:
        with serve(build_dir) as url:
            print(f"Serving {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    capture(browser, url, out)
                finally:
                    browser.close()
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
    print(f"\nDone. Screenshots in {out.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
