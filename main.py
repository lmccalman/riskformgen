import shutil
import subprocess

import config
from models import (
    AnyYesRule,
    ChoiceMapRule,
    ContainsAnyRule,
    CountYesRule,
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Question,
    Risk,
    YesNoQuestion,
)
from render import render_form


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


def define_risks() -> list[Risk]:
    """Define example risks that reference the form questions."""
    return [
        Risk(
            id="sedentary_risk",
            name="Sedentary Lifestyle",
            description="Risk of an overly sedentary lifestyle based on activity preferences.",
            rules=(
                AnyYesRule(
                    question_ids=("likes_swimming",),
                    level="low",
                ),
                ContainsAnyRule(
                    question_id="hobbies",
                    values=("Swimming", "Cycling"),
                    level="low",
                ),
                CountYesRule(
                    question_ids=("likes_swimming", "enjoys_coding"),
                    threshold=2,
                    level="medium",
                ),
            ),
            default_level="high",
        ),
        Risk(
            id="seasonal_mood_risk",
            name="Seasonal Mood Impact",
            description="Potential mood impact based on seasonal preference.",
            rules=(
                ChoiceMapRule(
                    question_id="favourite_season",
                    mapping={
                        "Spring": "low",
                        "Summer": "low",
                        "Autumn": "medium",
                        "Winter": "high",
                    },
                ),
            ),
        ),
        Risk(
            id="burnout_risk",
            name="Burnout",
            description="Risk of burnout from an indoor-heavy lifestyle.",
            rules=(
                AnyYesRule(
                    question_ids=("enjoys_coding",),
                    level="medium",
                ),
                ContainsAnyRule(
                    question_id="hobbies",
                    values=("Reading", "Cooking"),
                    level="medium",
                ),
                ContainsAnyRule(
                    question_id="hobbies",
                    values=("Swimming", "Cycling"),
                    level="low",
                ),
            ),
        ),
    ]


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    config.output_dir.mkdir(exist_ok=True)


def write_html(questions: list[Question], risks: list[Risk]) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(questions, risks)
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
    questions = define_questions()
    risks = define_risks()
    ensure_output_dir()
    write_html(questions, risks)
    compile_css()
    copy_alpine()
    print(
        f"Built form with {len(questions)} questions"
        f" and {len(risks)} risks in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
