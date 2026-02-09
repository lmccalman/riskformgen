import shutil
import subprocess
from pathlib import Path

from models import (
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Question,
    YesNoQuestion,
)
from render import render_form

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
ALPINE_SRC = PROJECT_ROOT / "alpine3.15.8.min.js"


def define_questions() -> list[Question]:
    """Define the example form questions."""
    return [
        YesNoQuestion(id="likes_swimming", text="Do you enjoy swimming?"),
        YesNoQuestion(id="enjoys_coding", text="Do you enjoy coding?"),
        FreeTextQuestion(id="favourite_memory", text="What is your favourite memory?"),
        MultipleChoiceQuestion(
            id="favourite_season",
            text="What is your favourite season?",
            options=("Spring", "Summer", "Autumn", "Winter"),
        ),
        MultipleSelectQuestion(
            id="hobbies",
            text="Which hobbies do you enjoy?",
            options=("Swimming", "Cycling", "Reading", "Cooking", "Music"),
        ),
    ]


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(exist_ok=True)


def write_html(questions: list[Question]) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(questions)
    (OUTPUT_DIR / "index.html").write_text(html)


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
        cwd=PROJECT_ROOT,
    )


def copy_alpine() -> None:
    """Copy the Alpine.js bundle into the output directory."""
    shutil.copy2(ALPINE_SRC, OUTPUT_DIR / ALPINE_SRC.name)


def main() -> None:
    """Build the static form page."""
    questions = define_questions()
    ensure_output_dir()
    write_html(questions)
    compile_css()
    copy_alpine()
    print(f"Built form with {len(questions)} questions in {OUTPUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
