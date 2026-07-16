"""
Resume match scoring engine — algorithm v2.

Pure Python: no I/O, no ORM, no side effects.
All functions accept SimpleNamespace stubs or Django model instances.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from apps.career_hub.services.scoring import (
    _PROFICIENCY_WEIGHTS,
    _skill_matches_job,
    location_score,
    normalize_skill,
    salary_overlap_score,
    tokenize,
)

if TYPE_CHECKING:
    pass

MATCH_ALGORITHM_VERSION = "v2"

MATCH_WEIGHTS: dict[str, float] = {
    "skill": 0.30,
    "experience": 0.20,
    "keyword": 0.20,
    "title": 0.15,
    "education": 0.05,
    "certification": 0.05,
    "location": 0.03,
    "salary": 0.02,
}

_TECHNOLOGY_WEIGHT = 0.3

_SENIORITY_YEARS: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "associate": 1,
    "mid": 2,
    "senior": 4,
    "sr": 4,
    "lead": 6,
    "staff": 6,
    "principal": 8,
    "architect": 8,
    "director": 10,
    "head": 10,
    "vp": 12,
}

SECONDARY_ALIASES: frozenset[str] = frozenset({
    "ssc", "hsc", "10th", "12th", "secondary", "higher secondary",
    "intermediate", "hs", "matriculation", "high school",
    "class 10", "class 12", "std 10", "std 12", "grade 10", "grade 12",
    "x", "xii",
})

DIPLOMA_ALIASES: frozenset[str] = frozenset({
    "diploma", "polytechnic", "iti", "certificate", "vocational",
    "pgdca", "advanced diploma", "associate degree", "associate",
    "d.pharm", "dpharm",
})

BACHELOR_ALIASES: frozenset[str] = frozenset({
    "b.tech", "be", "b.e", "b.e.", "b.tech.", "btech",
    "bsc", "b.sc", "b.sc.", "ba", "bcom", "b.com", "b.com.",
    "bba", "bca", "bachelor", "undergraduate", "ug",
    "bachelor of technology", "bachelor of engineering",
    "bachelor of science", "bachelor of arts", "bachelor of commerce",
    "bachelor of computer applications", "bachelor of business administration",
    "b.arch", "barch", "llb", "mbbs", "b.pharm", "bpharm",
})

MASTER_ALIASES: frozenset[str] = frozenset({
    "m.tech", "me", "m.e", "m.e.", "m.tech.", "mtech",
    "msc", "m.sc", "m.sc.", "ma", "mcom", "m.com", "m.com.",
    "mba", "pgdm", "mca", "master", "masters", "postgraduate", "pg",
    "ms", "m.s", "m.s.",
    "master of technology", "master of engineering",
    "master of science", "master of arts", "master of commerce",
    "master of computer applications", "master of business administration",
    "m.arch", "march", "llm", "m.pharm", "mpharm",
    "post graduate", "post-graduate",
})

DOCTORATE_ALIASES: frozenset[str] = frozenset({
    "phd", "ph.d", "ph.d.", "doctorate", "doctoral", "dba",
    "d.sc", "d.litt", "doctor of philosophy",
    "doctor of business administration", "d.phil", "dphil",
})

_DEGREE_LEVELS: list[tuple[int, frozenset[str]]] = [
    (5, DOCTORATE_ALIASES),
    (4, MASTER_ALIASES),
    (3, BACHELOR_ALIASES),
    (2, DIPLOMA_ALIASES),
    (1, SECONDARY_ALIASES),
]

_CERT_REQUIRED_KEYWORDS: frozenset[str] = frozenset({
    "pmp", "cissp", "ceh", "ccna", "ccnp", "ccie", "comptia",
    "cpa", "cfa", "cma", "acca", "frm", "cfp", "cism", "cisa",
    "itil", "prince2", "togaf", "pmi",
    "certification", "certified", "licensure",
})

_TECH_VOCAB: frozenset[str] = frozenset({
    "python", "java", "javascript", "typescript", "ruby", "php", "swift",
    "kotlin", "go", "rust", "scala", "dart", "flutter", "c",
    "react", "angular", "vue", "nextjs", "nodejs", "django", "flask",
    "fastapi", "spring", "rails", "laravel", "express",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "kafka", "rabbitmq", "graphql", "grpc", "rest",
    "tensorflow", "pytorch", "scikit", "pandas", "spark", "hadoop",
    "git", "jenkins", "gitlab", "github",
    "linux", "bash", "powershell",
})

_SOFT_SKILL_VOCAB: frozenset[str] = frozenset({
    "leadership", "mentoring", "mentorship", "coaching",
    "ownership", "teamwork", "collaboration", "communication",
    "empathy", "facilitation", "negotiation", "persuasion", "networking",
    "initiative", "accountability", "adaptability", "resilience",
    "creativity", "innovation", "proactive",
    "agile", "scrum", "kanban",
    "stakeholder", "delegation", "prioritization",
    "analytical", "storytelling", "presentation", "feedback",
    "entrepreneurial", "strategic", "collaborative",
    "multitasking", "influential", "motivating", "empowering",
    "interpersonal", "consensus", "conflict",
})

_GAP_EXCLUSIONS: frozenset[str] = frozenset({
    "experience", "work", "team", "strong", "good", "knowledge",
    "skills", "ability", "must", "should", "required", "preferred",
    "years", "working", "including", "using", "well", "such",
    "also", "more", "other", "about", "into", "than", "who",
    "they", "them", "been", "both", "each", "those", "through",
    "during", "before", "after", "above", "below", "so", "if",
    "no", "up", "out", "new", "one", "two", "may", "need",
    "would", "like", "make", "time", "over", "just", "very",
    "use", "build", "develop", "design", "implement", "manage",
    "support", "ensure", "provide", "role", "join", "help",
    "based", "across", "within",
    "applications", "application", "services", "service",
    "systems", "system", "solutions", "solution", "product",
    "products", "data", "business", "software", "development",
    "engineering", "technologies", "technology", "tools", "tool",
    "processes", "process", "best", "practices", "practice",
    "platform", "platforms", "environments", "environment",
    "security", "performance", "quality", "code", "testing",
    "production", "deployment", "infrastructure", "architecture",
    "requirements", "requirement", "documentation",
    "management", "understanding",
    "proficiency", "expertise", "plus", "bonus", "nice",
    "minimum", "maximum", "least", "per", "day", "week", "month",
    "full", "part", "time", "location", "office", "remote", "hybrid",
    "salary", "compensation", "benefits", "package",
    "join", "grow", "learn", "opportunity", "position", "job",
    "candidate", "applicant", "hire", "hiring",
})


@dataclass
class MatchExplanation:
    total: Decimal
    breakdown: dict[str, float]
    skill_gaps: dict[str, list[str]]
    algorithm_version: str = field(default=MATCH_ALGORITHM_VERSION)

    def to_dict(self) -> dict:
        return {
            "total": str(self.total),
            "breakdown": self.breakdown,
            "skill_gaps": self.skill_gaps,
            "algorithm_version": self.algorithm_version,
        }


def score_to_display(score: Decimal) -> int:
    """Convert a 0.000–1.000 score to a 0–100 integer for UI display."""
    return int((score * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalize_degree_text(raw: str) -> str:
    """Lowercase, strip possessives, collapse whitespace."""
    text = (raw or "").lower().strip()
    text = text.replace("'s", "").replace("'", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_degree(raw: str) -> int | None:
    """Map a degree string to a 1–5 level (1=Secondary … 5=Doctorate).

    Two-pass: exact alias lookup (high→low priority), then substring containment
    (returning the highest level found). Returns None when no alias matches.
    """
    text = _normalize_degree_text(raw)
    if not text:
        return None

    for level, aliases in _DEGREE_LEVELS:
        if text in aliases:
            return level

    found_levels: list[int] = []
    for level, aliases in _DEGREE_LEVELS:
        for alias in aliases:
            if re.search(r"\b" + re.escape(alias) + r"\b", text):
                found_levels.append(level)
                break

    return max(found_levels) if found_levels else None


def _extract_required_degree_level(text: str) -> int | None:
    """Find the minimum required degree level mentioned in job text.

    Returns the lowest (most permissive) level found; None if no degree signal.
    """
    normalized = _normalize_degree_text(text)
    found_levels: list[int] = []
    for level, aliases in _DEGREE_LEVELS:
        for alias in aliases:
            if re.search(r"\b" + re.escape(alias) + r"\b", normalized):
                found_levels.append(level)
                break
    return min(found_levels) if found_levels else None


def _compute_years_of_experience(work_experiences, today: date) -> float:
    """Sum total years across all work experiences.

    Missing end_date is treated as still-current (uses today).
    Entries with no start_date are skipped. Overlapping periods are not deduplicated.
    """
    total_days = 0
    for we in (work_experiences or []):
        start = getattr(we, "start_date", None)
        if start is None:
            continue
        end = getattr(we, "end_date", None) or today
        if end > start:
            total_days += (end - start).days
    return total_days / 365.25


def _extract_required_years(job_title: str, job_description: str) -> int | None:
    """Extract the minimum years of experience from job text.

    Matches patterns like "3+ years", "5 years of experience", "2-4 years".
    Ignores values outside the range [1, 30].
    """
    text = f"{job_title} {job_description}".lower()
    matches = re.findall(
        r"(\d+)\s*(?:\+|–|-|to)?\s*\d*\s*years?(?:\s+of\s+experience)?",
        text,
    )
    if not matches:
        return None
    values = [int(m) for m in matches if 1 <= int(m) <= 30]
    return min(values) if values else None


def _job_requires_certification(job_tokens: set[str]) -> bool:
    """Return True if the job description signals a certification requirement."""
    return bool(job_tokens & _CERT_REQUIRED_KEYWORDS)


def skills_score(
    skills,
    work_experience_technologies,
    project_technologies,
    job_text: str,
) -> float:
    """Weighted proportion of user skills and technologies found in job text.

    Named skills use proficiency weights. Technologies from WE/projects receive
    _TECHNOLOGY_WEIGHT when not already counted as a named skill.
    """
    job_text_lower = job_text.lower()
    job_tokens = tokenize(job_text)

    weighted_found = 0.0
    weighted_total = 0.0
    seen_normalized: set[str] = set()

    for skill in (skills or []):
        norm = normalize_skill(skill.name)
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        weight = _PROFICIENCY_WEIGHTS.get(getattr(skill, "proficiency_level", None) or "", 0.5)
        weighted_total += weight
        if _skill_matches_job(norm, job_text_lower, job_tokens):
            weighted_found += weight

    for tech in (work_experience_technologies or []):
        norm = normalize_skill(tech)
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        weighted_total += _TECHNOLOGY_WEIGHT
        if _skill_matches_job(norm, job_text_lower, job_tokens):
            weighted_found += _TECHNOLOGY_WEIGHT

    for tech in (project_technologies or []):
        norm = normalize_skill(tech)
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        weighted_total += _TECHNOLOGY_WEIGHT
        if _skill_matches_job(norm, job_text_lower, job_tokens):
            weighted_found += _TECHNOLOGY_WEIGHT

    if weighted_total == 0.0:
        return 0.0

    return min(weighted_found / weighted_total, 1.0)


def experience_score(
    work_experiences,
    job_title: str,
    job_description: str,
    today: date | None = None,
) -> float:
    """Score based on how well user's total experience meets the job requirement.

    Infers required years from explicit patterns or seniority keywords in title.
    Returns 0.7 when no requirement can be detected (neutral, no penalty).
    """
    today = today or date.today()
    user_years = _compute_years_of_experience(work_experiences, today)
    required_years = _extract_required_years(job_title, job_description)

    if required_years is None:
        title_lower = job_title.lower()
        for kw, yrs in _SENIORITY_YEARS.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
                required_years = yrs
                break

    if required_years is None:
        return 0.7

    if user_years >= required_years:
        return 1.0

    gap = required_years - user_years
    if gap <= 1:
        return 0.8
    if gap <= 2:
        return 0.6
    if gap <= 4:
        return 0.4
    return 0.2


def keyword_coverage_score(
    professional_summary: str,
    ats_keywords: list[str],
    work_experience_texts: list[str],
    project_texts: list[str],
    custom_section_texts: list[str],
    job_description: str,
) -> float:
    """Proportion of job description tokens covered by the user's profile text.

    Sources: professional summary, ATS keywords, WE descriptions, project descriptions,
    and custom profile sections.
    """
    user_tokens: set[str] = set()

    if professional_summary:
        user_tokens.update(tokenize(professional_summary))
    for kw in (ats_keywords or []):
        user_tokens.update(tokenize(kw))
    for text in (work_experience_texts or []):
        user_tokens.update(tokenize(text))
    for text in (project_texts or []):
        user_tokens.update(tokenize(text))
    for text in (custom_section_texts or []):
        user_tokens.update(tokenize(text))

    if not user_tokens:
        return 0.0

    job_tokens = tokenize(job_description)
    if not job_tokens:
        return 0.0

    return min(len(user_tokens & job_tokens) / len(job_tokens), 1.0)


def title_score(
    headline: str,
    current_titles: list[str],
    target_role: str,
    job_title: str,
) -> float:
    """Token overlap between user's career identity and job title.

    Career identity = headline + current role titles + target role.
    Precision is measured on job title tokens.
    """
    candidate_tokens: set[str] = set()

    if headline:
        candidate_tokens.update(tokenize(headline))
    for t in (current_titles or []):
        candidate_tokens.update(tokenize(t))
    if target_role:
        candidate_tokens.update(tokenize(target_role))

    if not candidate_tokens:
        return 0.0

    job_tokens = tokenize(job_title)
    if not job_tokens:
        return 0.0

    return min(len(candidate_tokens & job_tokens) / len(job_tokens), 1.0)


def education_score(
    educations,
    job_title: str,
    job_description: str,
) -> float:
    """Score based on how the user's highest degree meets the job requirement.

    Returns 0.7 when no degree data or no requirement can be inferred (neutral).
    """
    if not educations:
        return 0.7

    user_levels: list[int] = []
    for edu in educations:
        degree_text = getattr(edu, "degree", "") or ""
        level = normalize_degree(degree_text)
        if level is not None:
            user_levels.append(level)

    if not user_levels:
        return 0.7

    user_level = max(user_levels)
    required_level = _extract_required_degree_level(f"{job_title} {job_description}")

    if required_level is None:
        return 0.7

    gap = required_level - user_level
    if gap <= 0:
        return 1.0
    if gap == 1:
        return 0.7
    if gap == 2:
        return 0.4
    return 0.1


def certification_score(
    certifications,
    job_text: str,
    today: date | None = None,
) -> float:
    """Score based on whether user's certifications meet job requirements.

    Returns 0.5 (neutral) when the job gives no certification signal.
    Returns 0.2 when certifications are required but user has none or all expired.
    """
    today = today or date.today()
    job_tokens = tokenize(job_text)
    job_requires_cert = _job_requires_certification(job_tokens)

    if not certifications:
        return 0.2 if job_requires_cert else 0.5

    valid_certs = [
        c for c in certifications
        if (
            getattr(c, "expiry_date", None) is None
            or getattr(c, "expiry_date") >= today
        )
    ]

    valid_cert_tokens: set[str] = set()
    for c in valid_certs:
        valid_cert_tokens.update(tokenize(getattr(c, "name", "") or ""))

    overlap = valid_cert_tokens & job_tokens

    if job_requires_cert:
        if overlap:
            return 1.0
        if valid_certs:
            return 0.5
        return 0.2

    return 0.8 if overlap else 0.5


def salary_score(
    expected_min: Decimal | None,
    expected_max: Decimal | None,
    job_salary_min: Decimal | None,
    job_salary_max: Decimal | None,
) -> float:
    """Thin wrapper around salary_overlap_score from scoring.py."""
    return salary_overlap_score(expected_min, expected_max, job_salary_min, job_salary_max)


def extract_skill_gaps(
    *,
    skills,
    work_experience_technologies,
    project_technologies,
    certifications,
    job_description: str,
) -> dict[str, list[str]]:
    """Identify skills/technologies in the job description absent from user's profile.

    Returns four tiers:
      critical — tokens in a curated technology vocabulary (_TECH_VOCAB)
      moderate — tokens ≥5 chars appearing ≥2 times in job description, not tech or soft
      soft     — interpersonal/methodology tokens in _SOFT_SKILL_VOCAB
      low      — remaining unmatched tokens
    """
    user_normalized: set[str] = set()

    for skill in (skills or []):
        user_normalized.add(normalize_skill(skill.name))
    for tech in (work_experience_technologies or []):
        user_normalized.add(normalize_skill(tech))
    for tech in (project_technologies or []):
        user_normalized.add(normalize_skill(tech))
    for cert in (certifications or []):
        cert_name = getattr(cert, "name", "") or ""
        user_normalized.update(tokenize(cert_name))

    if not job_description:
        return {"critical": [], "moderate": [], "soft": [], "low": []}

    raw_tokens = re.findall(r"[a-z][a-z0-9+#.]*", job_description.lower())
    token_freq: dict[str, int] = {}
    for t in raw_tokens:
        if len(t) >= 2:
            token_freq[t] = token_freq.get(t, 0) + 1

    gaps = {
        t for t in token_freq
        if t not in user_normalized and t not in _GAP_EXCLUSIONS
    }

    critical = sorted(g for g in gaps if g in _TECH_VOCAB)
    soft = sorted(
        g for g in gaps
        if g not in _TECH_VOCAB and g in _SOFT_SKILL_VOCAB
    )
    moderate = sorted(
        g for g in gaps
        if g not in _TECH_VOCAB and g not in _SOFT_SKILL_VOCAB
        and len(g) >= 5 and token_freq.get(g, 0) >= 2
    )
    low = sorted(
        g for g in gaps
        if g not in _TECH_VOCAB and g not in _SOFT_SKILL_VOCAB
        and not (len(g) >= 5 and token_freq.get(g, 0) >= 2)
    )

    return {"critical": critical, "moderate": moderate, "soft": soft, "low": low}


def compute_resume_match_score(
    *,
    skills,
    work_experiences,
    educations,
    certifications,
    projects,
    headline: str,
    professional_summary: str,
    ats_keywords: list[str],
    target_role: str,
    custom_section_texts: list[str],
    user_city: str,
    expected_salary_min: Decimal | None,
    expected_salary_max: Decimal | None,
    job,
    today: date | None = None,
) -> MatchExplanation:
    """Compute the full resume-match score for a (profile, job) pair.

    Returns a MatchExplanation with total (Decimal 3dp), per-dimension breakdown,
    skill gaps, and algorithm version. All dimension weights sum to 1.0.
    """
    today = today or date.today()

    job_text = f"{job.title} {job.description}"

    we_technologies: list[str] = []
    we_texts: list[str] = []
    for we in (work_experiences or []):
        we_technologies.extend(getattr(we, "technologies", None) or [])
        desc = getattr(we, "description", "") or ""
        if desc:
            we_texts.append(desc)

    project_technologies: list[str] = []
    project_texts: list[str] = []
    for proj in (projects or []):
        project_technologies.extend(getattr(proj, "technologies", None) or [])
        desc = getattr(proj, "description", "") or ""
        if desc:
            project_texts.append(desc)

    current_titles: list[str] = [
        we.job_title
        for we in (work_experiences or [])
        if getattr(we, "is_current", False) and getattr(we, "job_title", None)
    ]

    s_skill = skills_score(skills, we_technologies, project_technologies, job_text)
    s_experience = experience_score(work_experiences, job.title, job.description, today)
    s_keyword = keyword_coverage_score(
        professional_summary,
        ats_keywords,
        we_texts,
        project_texts,
        custom_section_texts or [],
        job.description,
    )
    s_title = title_score(headline, current_titles, target_role, job.title)
    s_education = education_score(educations, job.title, job.description)
    s_certification = certification_score(certifications, job_text, today)
    s_location = location_score(user_city, job.city or "", job.work_type)
    s_salary = salary_overlap_score(
        expected_salary_min,
        expected_salary_max,
        job.salary_min,
        job.salary_max,
    )

    total = (
        MATCH_WEIGHTS["skill"] * s_skill
        + MATCH_WEIGHTS["experience"] * s_experience
        + MATCH_WEIGHTS["keyword"] * s_keyword
        + MATCH_WEIGHTS["title"] * s_title
        + MATCH_WEIGHTS["education"] * s_education
        + MATCH_WEIGHTS["certification"] * s_certification
        + MATCH_WEIGHTS["location"] * s_location
        + MATCH_WEIGHTS["salary"] * s_salary
    )
    total = max(0.0, min(1.0, total))
    total_decimal = Decimal(str(total)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    skill_gaps = extract_skill_gaps(
        skills=skills,
        work_experience_technologies=we_technologies,
        project_technologies=project_technologies,
        certifications=certifications,
        job_description=job.description,
    )

    return MatchExplanation(
        total=total_decimal,
        breakdown={
            "skill": round(s_skill, 4),
            "experience": round(s_experience, 4),
            "keyword": round(s_keyword, 4),
            "title": round(s_title, 4),
            "education": round(s_education, 4),
            "certification": round(s_certification, 4),
            "location": round(s_location, 4),
            "salary": round(s_salary, 4),
        },
        skill_gaps=skill_gaps,
    )
