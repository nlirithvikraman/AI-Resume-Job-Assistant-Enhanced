from pathlib import Path

from src import tracker
from src.matcher import match, score_resume
from src.parser import parse_resume
from src.skills import extract_skills

S = Path(__file__).resolve().parent.parent / "sample"
RESUME = (S / "resume.txt").read_text()
JOB = (S / "job.txt").read_text()


def test_skill_extraction_word_boundaries():
    assert "java" not in extract_skills("I love javascript")
    assert "c++" in extract_skills("Experienced in C++ and Python")


def test_parser_fields():
    p = parse_resume(RESUME)
    assert p.name == "Priya Sharma"
    assert p.email == "priya.sharma@example.com"
    assert "python" in p.skills
    assert {"experience", "education", "projects"} <= set(p.sections)
    assert p.links


def test_matcher_finds_gaps():
    r = match(RESUME, JOB)
    assert "python" in r.matched_skills
    assert "docker" in r.missing_skills
    assert 0 <= r.score <= 100


def test_scorer():
    s, tips = score_resume(parse_resume(RESUME))
    assert 0 < s <= 100


def test_tracker(tmp_path):
    db = tmp_path / "t.db"
    tracker.add("Acme", "ML Eng", match_score=70, path=db)
    rid = tracker.list_all(db)[0][0]
    tracker.update_status(rid, "Applied", path=db)
    assert tracker.list_all(db)[0][3] == "Applied"
    tracker.delete(rid, path=db)
    assert tracker.list_all(db) == []
