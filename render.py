from dataclasses import asdict

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from models import Question, Risk


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory."""
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(default=True),
    )


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


def render_form(questions: list[Question], risks: list[Risk]) -> str:
    """Render the form page HTML from a list of questions and risks."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    return template.render(
        questions=[asdict(q) for q in questions],
        risks=prepare_risks(risks),
    )
