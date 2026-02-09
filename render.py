from dataclasses import asdict

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from models import Question


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory."""
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(default=True),
    )


def render_form(questions: list[Question]) -> str:
    """Render the form page HTML from a list of questions."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    return template.render(questions=[asdict(q) for q in questions])
