import shutil

import config
from models import Control, Risk, Section, all_questions
from parse import load_controls, load_risks, load_sections
from render import render_form


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    config.output_dir.mkdir(exist_ok=True)


def write_html(sections: list[Section], risks: list[Risk], controls: list[Control]) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(sections, risks, controls)
    (config.output_dir / "index.html").write_text(html)


def copy_css() -> None:
    """Copy Bulma CSS and custom styles into the output directory."""
    shutil.copy2(config.bulma_src, config.output_dir / config.bulma_src.name)
    shutil.copy2(config.project_root / "input.css", config.output_dir / "input.css")


def copy_alpine() -> None:
    """Copy the Alpine.js bundle and persist plugin into the output directory."""
    shutil.copy2(config.persist_src, config.output_dir / config.persist_src.name)
    shutil.copy2(config.alpine_src, config.output_dir / config.alpine_src.name)


def main() -> None:
    """Build the static form page."""
    sections = load_sections(config.form_dir / "sections.yaml")
    risks = load_risks(config.form_dir / "risks.yaml")
    controls = load_controls(config.form_dir / "controls.yaml")
    questions = all_questions(sections)
    ensure_output_dir()
    write_html(sections, risks, controls)
    copy_css()
    copy_alpine()
    print(
        f"Built form with {len(sections)} sections, {len(questions)} questions,"
        f" {len(risks)} risks and {len(controls)} controls"
        f" in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
