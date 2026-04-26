import logging
import shutil

import config
from models import Control, Detail, Property, Risk, Section, all_questions
from parse import (
    load_controls,
    load_details,
    load_properties,
    load_risks,
    load_sections,
    validate_all,
)
from registry import SystemRecord, load_registry
from render import (
    render_assessment,
    render_assessment_app_js,
    render_landing,
    render_questionnaire,
    render_questionnaire_app_js,
    render_registry_index,
    render_registry_system,
)

logger = logging.getLogger(__name__)


def ensure_output_dir() -> None:
    """Remove and recreate the output directory so stale files don't linger."""
    shutil.rmtree(config.output_dir, ignore_errors=True)
    config.output_dir.mkdir()


def write_pages(
    sections: list[Section],
    risks: list[Risk],
    controls: list[Control],
    properties: list[Property],
    details: list[Detail],
    registry_records: list[SystemRecord],
) -> None:
    """Render and write the static HTML pages and two Alpine factories."""
    (config.output_dir / "index.html").write_text(render_landing())
    (config.output_dir / "questionnaire.html").write_text(
        render_questionnaire(sections, properties=properties, details=details)
    )
    (config.output_dir / "assessment.html").write_text(
        render_assessment(
            sections, risks=risks, controls=controls, properties=properties, details=details
        )
    )
    (config.output_dir / "registry.html").write_text(render_registry_index(registry_records))
    if registry_records:
        registry_out = config.output_dir / "registry"
        registry_out.mkdir(exist_ok=True)
        for record in registry_records:
            (registry_out / f"{record.slug}.html").write_text(
                render_registry_system(record, sections, risks, controls, properties, details)
            )
    (config.output_dir / "app-questionnaire.js").write_text(
        render_questionnaire_app_js(sections, properties=properties, details=details)
    )
    (config.output_dir / "app-assessment.js").write_text(
        render_assessment_app_js(
            sections, risks=risks, controls=controls, properties=properties, details=details
        )
    )


def copy_css() -> None:
    """Copy Bulma CSS and custom styles into the output directory."""
    shutil.copy2(config.bulma_src, config.output_dir / config.bulma_src.name)
    shutil.copy2(config.project_root / "input.css", config.output_dir / "input.css")


def copy_alpine() -> None:
    """Copy the Alpine.js bundle and persist plugin into the output directory."""
    shutil.copy2(config.persist_src, config.output_dir / config.persist_src.name)
    shutil.copy2(config.alpine_src, config.output_dir / config.alpine_src.name)


def main() -> None:
    """Build the static site — landing page plus three per-tool pages."""
    details_path = config.form_dir / "details.yaml"
    details = load_details(details_path) if details_path.exists() else []
    details_by_id = {d.id: d for d in details}

    sections = load_sections(config.form_dir / "sections.yaml", details_by_id)
    properties = load_properties(config.form_dir / "properties.yaml")
    risks = load_risks(config.form_dir / "risks.yaml")
    controls = load_controls(config.form_dir / "controls.yaml")

    validate_all(sections, properties, risks, controls, details)

    registry_records = load_registry(
        config.registry_dir,
        sections=sections,
        risks=risks,
        controls=controls,
        properties=properties,
    )

    ensure_output_dir()
    write_pages(sections, risks, controls, properties, details, registry_records)
    copy_css()
    copy_alpine()
    questions = all_questions(sections)
    logger.info(
        "Built site with %d sections, %d questions, %d properties,"
        " %d risks, %d controls, %d details, and %d registered systems in %s/",
        len(sections),
        len(questions),
        len(properties),
        len(risks),
        len(controls),
        len(details),
        len(registry_records),
        config.output_dir.resolve(),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
