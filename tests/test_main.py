"""Smoke test for main.py — end-to-end build into a tmpdir."""

from __future__ import annotations

from pathlib import Path

import config
import main


def test_main_builds_expected_files(tmp_path: Path, monkeypatch):
    """main() produces a non-empty output directory with all expected assets."""
    monkeypatch.setattr(config, "output_dir", tmp_path / "output")

    main.main()

    out = tmp_path / "output"
    index = out / "index.html"
    app_js = out / "app.js"
    bulma = out / "bulma.min.css"
    input_css = out / "input.css"
    alpine = out / config.alpine_src.name
    persist = out / config.persist_src.name

    for f in (index, app_js, bulma, input_css, alpine, persist):
        assert f.exists(), f"Expected {f.name} in output"
        assert f.stat().st_size > 0, f"{f.name} is empty"

    html = index.read_text()
    assert '<div x-data="app">' in html
    js = app_js.read_text()
    assert "Alpine.data('app'" in js
