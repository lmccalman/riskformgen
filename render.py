from dataclasses import asdict

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from models import Risk, Section, all_questions


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory."""
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(default=True),
    )


def prepare_sections(sections: list[Section]) -> list[dict]:
    """Convert Section dataclasses to template-ready nested dicts."""
    return [
        {
            "id": section.id,
            "title": section.title,
            "description": section.description,
            "subsections": [
                {
                    "title": sub.title,
                    "description": sub.description,
                    "questions": [asdict(q) for q in sub.questions],
                }
                for sub in section.subsections
            ],
        }
        for section in sections
    ]


def prepare_risks(risks: list[Risk]) -> list[dict]:
    """Convert Risk dataclasses to template-ready dicts with compiled JS expressions."""
    return [
        {
            "id": risk.id,
            "name": risk.name,
            "description": risk.description,
            "default_level": risk.default_level,
            "rules_js": [rule.to_js() for rule in risk.rules],
        }
        for risk in risks
    ]


def render_form(sections: list[Section], risks: list[Risk]) -> str:
    """Render the form page HTML from sections and risks."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    return template.render(
        sections=prepare_sections(sections),
        questions=[asdict(q) for q in all_questions(sections)],
        risks=prepare_risks(risks),
    )
