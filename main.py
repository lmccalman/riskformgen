import shutil
import subprocess

import config
from models import all_questions
from parse import load_controls, load_risks, load_sections
from render import render_form


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    config.output_dir.mkdir(exist_ok=True)


def write_html(sections, risks, controls) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(sections, risks, controls)
    (config.output_dir / "index.html").write_text(html)


def compile_css() -> None:
    """Compile Tailwind CSS from input.css into output/styles.css."""
    subprocess.run(
        [
            "tailwindcss",
            "--input", "input.css",
            "--output", "output/styles.css",
            "--minify",
        ],
        check=True,
        cwd=config.project_root,
    )


def copy_alpine() -> None:
    """Copy the Alpine.js bundle into the output directory."""
    shutil.copy2(config.alpine_src, config.output_dir / config.alpine_src.name)


def main() -> None:
    """Build the static form page."""
    sections = load_sections(config.form_dir / "sections.yaml")
    risks = load_risks(config.form_dir / "risks.yaml")
    controls = load_controls(config.form_dir / "controls.yaml")
    questions = all_questions(sections)
    ensure_output_dir()
    write_html(sections, risks, controls)
    compile_css()
    copy_alpine()
    print(
        f"Built form with {len(sections)} sections, {len(questions)} questions,"
        f" {len(risks)} risks and {len(controls)} controls"
        f" in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
