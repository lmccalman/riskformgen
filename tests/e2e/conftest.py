import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Page

import config
import main as main_module


@pytest.fixture(scope="session")
def _session_monkeypatch() -> Iterator[pytest.MonkeyPatch]:
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def built_site_dir(
    tmp_path_factory: pytest.TempPathFactory,
    _session_monkeypatch: pytest.MonkeyPatch,
) -> Path:
    site_dir = tmp_path_factory.mktemp("site")
    _session_monkeypatch.setattr(config, "output_dir", site_dir)
    main_module.main()
    return site_dir


@pytest.fixture(scope="session")
def site_url(built_site_dir: Path) -> Iterator[str]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(built_site_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, "accept_downloads": True}


def _wait_for_factory(page: Page, name: str) -> None:
    page.wait_for_function(f"() => !!document.querySelector('[x-data={name}]')?._x_dataStack?.[0]")


@pytest.fixture
def landing_page(page: Page, site_url: str) -> Page:
    page.goto(f"{site_url}/index.html")
    return page


@pytest.fixture
def questionnaire_page(page: Page, site_url: str) -> Page:
    page.goto(f"{site_url}/questionnaire.html")
    _wait_for_factory(page, "questionnaire")
    return page


@pytest.fixture
def assessment_page(page: Page, site_url: str) -> Page:
    page.goto(f"{site_url}/assessment.html")
    _wait_for_factory(page, "assessment")
    return page


@pytest.fixture
def registry_page(page: Page, site_url: str) -> Page:
    page.goto(f"{site_url}/registry.html")
    return page
