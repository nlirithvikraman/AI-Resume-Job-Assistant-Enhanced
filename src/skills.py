"""Skill vocabulary + extraction. Extend SKILLS freely for your target domain."""
import re

SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "sql", "r", "scala", "kotlin", "swift", "php", "bash",
    "html", "css", "react", "angular", "vue", "node.js", "next.js", "django", "flask", "fastapi", "spring boot", "streamlit",
    "machine learning", "deep learning", "nlp", "natural language processing", "computer vision", "data analysis", "statistics",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras", "spacy", "nltk", "hugging face", "transformers",
    "langchain", "llm", "prompt engineering", "rag", "embeddings", "faiss", "chromadb",
    "postgresql", "mysql", "mongodb", "sqlite", "redis", "elasticsearch", "snowflake", "bigquery",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd", "jenkins", "github actions", "linux", "git",
    "rest api", "graphql", "microservices", "spark", "hadoop", "airflow", "kafka", "etl", "power bi", "tableau", "excel",
    "agile", "scrum", "jira", "unit testing", "pytest", "selenium", "devops", "mlops",
    "communication", "leadership", "teamwork", "problem solving", "project management",
]

_ALIASES = {"nlp": "natural language processing", "k8s": "kubernetes", "js": "javascript", "ml": "machine learning", "react.js": "react", "reactjs": "react", "nodejs": "node.js", "postgres": "postgresql", "rest apis": "rest api", "restful": "rest api", "html5": "html", "css3": "css", "problem-solving": "problem solving"}


def _pattern(skill: str) -> re.Pattern:
    return re.compile(r"(?<![\w+#.])" + re.escape(skill) + r"(?![\w+#])", re.IGNORECASE)


_PATTERNS = {s: _pattern(s) for s in SKILLS}


def extract_skills(text: str) -> list[str]:
    """Return skills found in text (deduplicated, in vocabulary order)."""
    found = [s for s, p in _PATTERNS.items() if p.search(text)]
    for alias, canon in _ALIASES.items():
        if canon in SKILLS and canon not in found and _pattern(alias).search(text):
            found.append(canon)
    return list(dict.fromkeys(_ALIASES.get(s, s) for s in found))
