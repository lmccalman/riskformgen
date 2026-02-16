import shutil

import config
from models import Property, Section, all_questions
from parse import (
    load_properties,
    load_sections,
    validate_property_dag,
    validate_question_properties,
)
from render import render_form


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    config.output_dir.mkdir(exist_ok=True)


def write_html(sections: list[Section], properties: list[Property]) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(sections, risks=[], controls=[], properties=properties)
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
    properties = load_properties(config.form_dir / "properties.yaml")
    validate_property_dag(properties)
    questions = all_questions(sections)
    validate_question_properties(questions, properties)
    ensure_output_dir()
    write_html(sections, properties)
    copy_css()
    copy_alpine()
    print(
        f"Built form with {len(sections)} sections, {len(questions)} questions,"
        f" and {len(properties)} properties"
        f" in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
