"""
Exam loader for the RHCSA Examination Platform.
Reads exam definitions from JSON files in the exams/ directory.
"""
import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXAMS_DIR = Path(__file__).parent / "exams"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_exam(exam_id: str) -> dict:
    """
    Parse and return the exam definition for the given exam_id.
    Raises FileNotFoundError if the exam JSON does not exist.
    """
    exam_path = EXAMS_DIR / f"{exam_id}.json"
    if not exam_path.is_file():
        raise FileNotFoundError(f"Exam '{exam_id}' not found at {exam_path}")
    with exam_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_exams() -> list:
    """
    Return a summary list of all exams found in EXAMS_DIR.
    Each entry contains: { id, title, description, scenario, task_count }.
    """
    if not EXAMS_DIR.is_dir():
        return []
    exams = []
    for exam_path in sorted(EXAMS_DIR.glob("*.json")):
        try:
            data = json.loads(exam_path.read_text(encoding="utf-8"))
            exams.append({
                "id":          exam_path.stem,
                "title":       data.get("title", ""),
                "description": data.get("description", ""),
                "scenario":    data.get("scenario", "standard"),
                "task_count":  len(data.get("tasks", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return exams


def get_active_exam() -> dict:
    """
    Load the exam specified by the ACTIVE_EXAM env var (default: 'exam-1').
    Raises FileNotFoundError if that exam does not exist.
    """
    exam_id = os.environ.get("ACTIVE_EXAM", "exam-1")
    return load_exam(exam_id)
