"""
Deterministic job recommendation scoring engine — algorithm v1.

All public functions are pure: no I/O, no side effects, no Django ORM calls.
Tests can call them directly with SimpleNamespace stubs.
"""
from __future__ import annotations

import re
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.career_hub.models import Job
    from apps.profiles.models import Skill

ALGORITHM_VERSION = "v1"

# Dimension weights — must sum to 1.0
SCORE_WEIGHTS: dict[str, float] = {
    "skill": 0.35,
    "title": 0.25,
    "location": 0.20,
    "saved": 0.15,
    "salary": 0.05,
}

_PROFICIENCY_WEIGHTS: dict[str, float] = {
    "expert": 1.0,
    "advanced": 0.8,
    "intermediate": 0.5,
    "beginner": 0.2,
}

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "of", "in", "at", "to",
    "is", "with", "on", "as", "by", "be", "we", "are", "you", "it",
    "this", "that", "not", "but", "from", "have", "has", "had",
    "will", "can", "do", "all", "any", "its", "our", "your",
})

MIN_SAVED_FOR_SIMILARITY = 3


def normalize_skill(name: str) -> str:
    """Lowercase and strip trailing version numbers.

    Examples: "Python 3" → "python", "Django 4.2" → "django", "React.js" → "react.js"
    """
    name = name.lower().strip()
    # Remove trailing version numbers separated by whitespace: "Python 3", "Django 4.2.1"
    name = re.sub(r"\s+\d+(\.\d+)*\s*$", "", name).strip()
    return name


def tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens, filtering stopwords and short tokens.

    Keeps alphanumeric clusters plus common tech suffixes: .js, c++, c#
    """
    if not text:
        return set()
    # Match runs of [a-z0-9] plus selected punctuation that appears in tech names
    raw = re.findall(r"[a-z][a-z0-9+#.]*", text.lower())
    return {t for t in raw if len(t) >= 2 and t not in _STOPWORDS}


def _skill_matches_job(normalized_name: str, job_text_lower: str, job_tokens: set[str]) -> bool:
    """Return True if a skill name appears in the job text.

    Single-word skills use token matching (prevents "java" matching "javascript").
    Multi-word skills use word-boundary regex against the full lowercased job text.
    """
    if " " not in normalized_name:
        return normalized_name in job_tokens
    return bool(re.search(r"\b" + re.escape(normalized_name) + r"\b", job_text_lower))


def skill_score(skills, job_text: str) -> float:
    """Weighted proportion of user skills found in job text.

    Weight per skill is determined by proficiency level. Expert skills contribute
    more than beginner skills. Returns 0.0 when no skills are provided.
    """
    if not skills:
        return 0.0

    job_text_lower = job_text.lower()
    job_tokens = tokenize(job_text)

    weighted_found = 0.0
    weighted_total = 0.0

    for skill in skills:
        weight = _PROFICIENCY_WEIGHTS.get(skill.proficiency_level, 0.5)
        weighted_total += weight
        if _skill_matches_job(normalize_skill(skill.name), job_text_lower, job_tokens):
            weighted_found += weight

    if weighted_total == 0.0:
        return 0.0

    return min(weighted_found / weighted_total, 1.0)


def title_score(headline: str, current_titles: list[str], job_title: str) -> float:
    """Token overlap between user's career identity (headline + current role) and job title.

    Precision is measured on the job title: what fraction of the job title tokens
    appear in the user's career identity? Returns 0.0 when no identity signals exist.
    """
    candidate_tokens: set[str] = set()

    if headline:
        candidate_tokens.update(tokenize(headline))

    for title in current_titles:
        candidate_tokens.update(tokenize(title))

    if not candidate_tokens:
        return 0.0

    job_tokens = tokenize(job_title)

    if not job_tokens:
        return 0.0

    return len(candidate_tokens & job_tokens) / len(job_tokens)


def location_score(user_city: str, job_city: str, job_work_type: str) -> float:
    """Geographic fit between user location and job location.

    Remote jobs always score 1.0. Unknown cities score 0.5 (neutral, no penalty).
    City matching uses substring containment to handle abbreviations and suffixes
    (e.g., "Bangalore" matches "Bangalore, Karnataka").
    """
    if job_work_type == "remote":
        return 1.0

    u = (user_city or "").lower().strip()
    j = (job_city or "").lower().strip()

    if not u or not j:
        return 0.5  # unknown — do not penalise

    if u in j or j in u:
        return 1.0

    return 0.0


def saved_similarity_score(
    saved_job_titles: list[str],
    candidate_job_title: str,
) -> float:
    """Token-frequency similarity between candidate title and saved job titles.

    Returns 0.0 when the user has saved fewer than MIN_SAVED_FOR_SIMILARITY jobs —
    not enough data to produce a reliable signal.
    """
    if len(saved_job_titles) < MIN_SAVED_FOR_SIMILARITY:
        return 0.0

    saved_counter: Counter[str] = Counter()
    for title in saved_job_titles:
        saved_counter.update(tokenize(title))

    candidate_tokens = tokenize(candidate_job_title)

    if not candidate_tokens or not saved_counter:
        return 0.0

    total = sum(saved_counter.values())
    if total == 0:
        return 0.0

    overlap = sum(saved_counter[t] for t in candidate_tokens if t in saved_counter)
    return min(overlap / total, 1.0)


def salary_overlap_score(
    expected_min: Decimal | None,
    expected_max: Decimal | None,
    job_salary_min: Decimal | None,
    job_salary_max: Decimal | None,
) -> float:
    """Overlap between user's expected salary range and job's salary range.

    Returns 0.5 (neutral) when either the job or user has no salary data —
    missing salary information should not penalise an otherwise good match.
    Returns 1.0 when the ranges overlap, 0.0 when they do not.
    """
    if job_salary_min is None and job_salary_max is None:
        return 0.5

    if expected_min is None and expected_max is None:
        return 0.5

    e_min = float(expected_min) if expected_min is not None else 0.0
    e_max = float(expected_max) if expected_max is not None else float("inf")
    j_min = float(job_salary_min) if job_salary_min is not None else 0.0
    j_max = float(job_salary_max) if job_salary_max is not None else float("inf")

    return 1.0 if max(e_min, j_min) <= min(e_max, j_max) else 0.0


def compute_score(
    *,
    skills,
    headline: str,
    current_titles: list[str],
    user_city: str,
    saved_job_titles: list[str],
    expected_salary_min: Decimal | None,
    expected_salary_max: Decimal | None,
    job,
) -> dict:
    """Compute the weighted recommendation score for a single (user signals, job) pair.

    Returns a dict with:
      total       — Decimal to 3 decimal places, range [0.000, 1.000]
      breakdown   — per-dimension sub-scores (float, 4dp) for explanation UI
    """
    job_text = f"{job.title} {job.description}"

    s_skill = skill_score(skills, job_text)
    s_title = title_score(headline, current_titles, job.title)
    s_loc = location_score(user_city, job.city or "", job.work_type)
    s_saved = saved_similarity_score(saved_job_titles, job.title)
    s_salary = salary_overlap_score(
        expected_salary_min, expected_salary_max,
        job.salary_min, job.salary_max,
    )

    total = (
        SCORE_WEIGHTS["skill"] * s_skill
        + SCORE_WEIGHTS["title"] * s_title
        + SCORE_WEIGHTS["location"] * s_loc
        + SCORE_WEIGHTS["saved"] * s_saved
        + SCORE_WEIGHTS["salary"] * s_salary
    )
    total = max(0.0, min(1.0, total))

    return {
        "total": Decimal(str(total)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "breakdown": {
            "skill": round(s_skill, 4),
            "title": round(s_title, 4),
            "location": round(s_loc, 4),
            "saved": round(s_saved, 4),
            "salary": round(s_salary, 4),
        },
    }
