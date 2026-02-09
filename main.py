import shutil
import subprocess

import config
from models import (
    Any,
    AnyYesRule,
    ChoiceMapRule,
    ContainsAnyRule,
    CountYesRule,
    Equals,
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Not,
    Risk,
    Section,
    SubSection,
    YesNoQuestion,
    all_questions,
)
from render import render_form


def define_sections() -> list[Section]:
    """Define the example form sections with sub-sections and questions."""
    return [
        Section(
            id="personal",
            title="Personal",
            description="Tell us a bit about yourself — who you are and what makes you tick.",
            subsections=(
                SubSection(
                    title="About You",
                    description="Some basics so we know who we're talking to.",
                    questions=(
                        FreeTextQuestion(id="name", text="What is your name?"),
                        FreeTextQuestion(
                            id="favourite_memory",
                            text="What is your favourite memory?",
                        ),
                    ),
                ),
                SubSection(
                    title="Preferences",
                    description="Your general likes and daily rhythms.",
                    questions=(
                        MultipleChoiceQuestion(
                            id="favourite_season",
                            text="What is your favourite season?",
                            options=("Spring", "Summer", "Autumn", "Winter"),
                        ),
                        YesNoQuestion(
                            id="morning_person",
                            text="Are you a morning person?",
                        ),
                    ),
                ),
            ),
        ),
        Section(
            id="activities",
            title="Activities",
            description="What you do with your time — both active pursuits and quieter interests.",
            subsections=(
                SubSection(
                    title="Exercise & Sport",
                    description="How you move your body and stay active.",
                    questions=(
                        YesNoQuestion(
                            id="likes_swimming",
                            text="Do you enjoy swimming?",
                        ),
                        MultipleChoiceQuestion(
                            id="exercise_frequency",
                            text="How often do you exercise?",
                            options=("Daily", "A few times a week", "Weekly", "Rarely", "Never"),
                        ),
                        MultipleSelectQuestion(
                            id="active_hobbies",
                            text="Which active hobbies do you enjoy?",
                            options=("Swimming", "Cycling", "Running", "Hiking", "Team sports"),
                            visible_when=Not(Equals("exercise_frequency", "Never")),
                        ),
                    ),
                ),
                SubSection(
                    title="Indoor Interests",
                    description="The things you enjoy when you're staying in.",
                    visible_when=Any((
                        Equals("exercise_frequency", "Rarely"),
                        Equals("exercise_frequency", "Never"),
                    )),
                    questions=(
                        YesNoQuestion(
                            id="enjoys_coding",
                            text="Do you enjoy coding?",
                        ),
                        MultipleSelectQuestion(
                            id="indoor_hobbies",
                            text="Which indoor hobbies do you enjoy?",
                            options=("Reading", "Cooking", "Gaming", "Music", "Crafts"),
                        ),
                    ),
                ),
            ),
        ),
        Section(
            id="environment",
            title="Environment",
            description="Your surroundings and how you connect with the people around you.",
            subsections=(
                SubSection(
                    title="Living Situation",
                    description="Your daily environment and access to the outdoors.",
                    questions=(
                        MultipleChoiceQuestion(
                            id="commute_method",
                            text="How do you usually commute?",
                            options=("Walk", "Cycle", "Public transport", "Drive", "Work from home"),
                        ),
                        YesNoQuestion(
                            id="outdoor_access",
                            text="Do you have easy access to outdoor spaces?",
                        ),
                    ),
                ),
                SubSection(
                    title="Social",
                    description="How often and in what ways you spend time with others.",
                    questions=(
                        MultipleChoiceQuestion(
                            id="social_frequency",
                            text="How often do you socialise?",
                            options=("Daily", "A few times a week", "Weekly", "Rarely"),
                        ),
                        MultipleSelectQuestion(
                            id="group_activities",
                            text="Which group activities do you participate in?",
                            options=("Team sports", "Book clubs", "Volunteering", "Classes", "Social dining"),
                        ),
                    ),
                ),
            ),
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
                    question_id="active_hobbies",
                    values=("Swimming", "Cycling", "Running"),
                    level="low",
                ),
                ChoiceMapRule(
                    question_id="exercise_frequency",
                    mapping={
                        "Daily": "low",
                        "A few times a week": "low",
                        "Weekly": "medium",
                        "Rarely": "high",
                        "Never": "high",
                    },
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
                    question_id="indoor_hobbies",
                    values=("Reading", "Gaming"),
                    level="medium",
                ),
                ContainsAnyRule(
                    question_id="active_hobbies",
                    values=("Swimming", "Cycling", "Hiking"),
                    level="low",
                ),
                AnyYesRule(
                    question_ids=("outdoor_access",),
                    level="low",
                ),
            ),
        ),
        Risk(
            id="isolation_risk",
            name="Social Isolation",
            description="Risk of social isolation based on socialising habits.",
            rules=(
                ChoiceMapRule(
                    question_id="social_frequency",
                    mapping={
                        "Daily": "low",
                        "A few times a week": "low",
                        "Weekly": "medium",
                        "Rarely": "high",
                    },
                ),
                ContainsAnyRule(
                    question_id="group_activities",
                    values=("Team sports", "Volunteering", "Social dining"),
                    level="low",
                ),
            ),
            default_level="high",
        ),
    ]


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    config.output_dir.mkdir(exist_ok=True)


def write_html(sections: list[Section], risks: list[Risk]) -> None:
    """Render and write the form HTML to output/index.html."""
    html = render_form(sections, risks)
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
    sections = define_sections()
    risks = define_risks()
    questions = all_questions(sections)
    ensure_output_dir()
    write_html(sections, risks)
    compile_css()
    copy_alpine()
    print(
        f"Built form with {len(sections)} sections, {len(questions)} questions"
        f" and {len(risks)} risks in {config.output_dir.resolve()}/"
    )


if __name__ == "__main__":
    main()
