import shutil

import config
from models import Control, Detail, Property, Risk, Section, all_questions
from parse import (
    load_controls,
    load_details,
    load_properties,
    load_risks,
    load_sections,
    validate_control_properties,
    validate_control_risk_ids,
    validate_detail_properties,
    validate_detail_questions,
    validate_id_namespaces,
    validate_property_dag,
    validate_question_properties,
    validate_risk_properties,
)
from render import render_app_js, render_form


def ensure_output_dir() -> None:
    """Remove and recreate the output directory so stale files don't linger."""
    shutil.rmtree(config.output_dir, ignore_errors=True)
    config.output_dir.mkdir()


def write_html(
    sections: list[Section],
    risks: list[Risk],
    controls: list[Control],
    properties: list[Property],
    details: list[Detail],
) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(
        sections, risks=risks, controls=controls, properties=properties, details=details
    )
    (config.output_dir / "index.html").write_text(html)


def write_app_js(
    sections: list[Section],
    risks: list[Risk],
    controls: list[Control],
    properties: list[Property],
    details: list[Detail],
) -> None:
    """Render and write the Alpine component factory to output/app.js."""
    js = render_app_js(
        sections, risks=risks, controls=controls, properties=properties, details=details
    )
    (config.output_dir / "app.js").write_text(js)


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
    details_path = config.form_dir / "details.yaml"
    details = load_details(details_path) if details_path.exists() else []
    details_by_id = {d.id: d for d in details}

    sections = load_sections(config.form_dir / "sections.yaml", details_by_id)
    properties = load_properties(config.form_dir / "properties.yaml")
    risks = load_risks(config.form_dir / "risks.yaml")
    controls = load_controls(config.form_dir / "controls.yaml")

    validate_property_dag(properties)
    questions = all_questions(sections)
    validate_question_properties(questions, properties)
    validate_risk_properties(risks, properties)
    validate_control_properties(controls, properties)
    validate_control_risk_ids(controls, risks)
    validate_detail_properties(details, properties)
    validate_detail_questions(questions, details)
    validate_id_namespaces(sections, properties, risks, controls, details)

    ensure_output_dir()
    write_html(sections, risks, controls, properties, details)
    write_app_js(sections, risks, controls, properties, details)
    copy_css()
    copy_alpine()
    print(
        f"Built form with {len(sections)} sections, {len(questions)} questions,"
        f" {len(properties)} properties, {len(risks)} risks,"
        f" {len(controls)} controls, and {len(details)} details"
        f" in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
