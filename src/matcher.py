"""Stage 2: Resume-to-Job matcher (ATS-style) + resume scorer."""
import re
import os
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .skills import extract_skills

_model = None


def _semantic_similarity(a: str, b: str):
    """Embedding similarity (0-1) if sentence-transformers is installed, else None."""
    global _model
    if os.getenv("RESUME_AI_EMBEDDINGS", "0") != "1":
        return None
    try:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        ea, eb = _model.encode([a, b], normalize_embeddings=True)
        return float(max(0.0, ea @ eb))
    except Exception:
        return None


def _tfidf_similarity(a: str, b: str) -> float:
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    try:
        m = vec.fit_transform([a, b])
    except ValueError:
        return 0.0
    return float(cosine_similarity(m[0], m[1])[0][0])


def _missing_keywords(resume: str, jd: str, k: int = 15) -> list[str]:
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=300)
    try:
        m = vec.fit_transform([jd])
    except ValueError:
        return []
    terms = vec.get_feature_names_out()
    ranked = sorted(zip(terms, m.toarray()[0]), key=lambda x: -x[1])
    low = resume.lower()
    return [t for t, _ in ranked if t not in low and not t.isdigit()][:k]


@dataclass
class MatchResult:
    score: int
    skill_coverage: float
    similarity: float
    matched_skills: list
    missing_skills: list
    missing_keywords: list
    method: str


def match(resume_text: str, jd_text: str) -> MatchResult:
    if not resume_text.strip() or not jd_text.strip():
        return MatchResult(0, 0.0, 0.0, [], [], [], "tf-idf")
    jd_skills = extract_skills(jd_text)
    res_skills = set(extract_skills(resume_text))
    matched = [s for s in jd_skills if s in res_skills]
    missing = [s for s in jd_skills if s not in res_skills]
    coverage = len(matched) / len(jd_skills) if jd_skills else 0.0

    sem = _semantic_similarity(resume_text, jd_text)
    sim, method = (sem, "embeddings") if sem is not None else (_tfidf_similarity(resume_text, jd_text), "tf-idf")
    # TF-IDF scores run low; stretch so the number is comparable.
    sim_norm = min(1.0, sim * (1.0 if sem is not None else 2.0))

    score = round(100 * (0.6 * coverage + 0.4 * sim_norm)) if jd_skills else round(100 * sim_norm)
    return MatchResult(score, coverage, sim, matched, missing, _missing_keywords(resume_text, jd_text), method)


def score_resume(parsed) -> tuple[int, list[str]]:
    """Score a resume out of 100 on completeness and quality, with suggestions."""
    score, tips = 0, []
    checks = [
        (bool(parsed.email), 10, "Add a professional email address."),
        (bool(parsed.phone), 5, "Add a phone number."),
        (bool(parsed.links), 5, "Add LinkedIn/GitHub links."),
        ("summary" in parsed.sections, 10, "Add a 2-3 line professional summary."),
        ("experience" in parsed.sections, 15, "Add an Experience section (internships count)."),
        ("education" in parsed.sections, 10, "Add an Education section."),
        ("projects" in parsed.sections, 10, "Add 2-3 projects with outcomes."),
        (len(parsed.skills) >= 8, 10, "List at least 8 relevant skills."),
    ]
    for ok, pts, tip in checks:
        score += pts if ok else 0
        if not ok:
            tips.append(tip)
    words = len(parsed.raw_text.split())
    if 300 <= words <= 800:
        score += 10
    else:
        tips.append(f"Length is {words} words; aim for 300-800 (one page for early career).")
    if len(re.findall(r"\d+%|\$\d+|\b\d{2,}\b", parsed.raw_text)) >= 3:
        score += 15
    else:
        tips.append("Quantify achievements (e.g. 'reduced load time by 30%').")
    return score, tips
