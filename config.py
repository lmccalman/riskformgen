from pathlib import Path

project_root = Path(__file__).parent
output_dir = project_root / "output"
templates_dir = project_root / "templates"
alpine_src = project_root / "alpine3.15.8.min.js"
pico_src = project_root / "pico.jade.min.css"
form_dir = project_root / "form"

# ---------------------------------------------------------------------------
# Risk scales and matrix (order = ascending severity)
# ---------------------------------------------------------------------------

LIKELIHOODS = ("rare", "unlikely", "possible", "likely", "almost_certain")
CONSEQUENCES = ("minor", "medium", "major")
RISK_LEVELS = ("not_applicable", "low", "medium", "high")

RISK_MATRIX: dict[str, dict[str, str]] = {
    "rare":            {"minor": "low",    "medium": "low",    "major": "medium"},
    "unlikely":        {"minor": "low",    "medium": "medium", "major": "medium"},
    "possible":        {"minor": "medium", "medium": "medium", "major": "high"},
    "likely":          {"minor": "medium", "medium": "high",   "major": "high"},
    "almost_certain":  {"minor": "high",   "medium": "high",   "major": "high"},
}
