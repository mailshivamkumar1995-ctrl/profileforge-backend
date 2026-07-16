"""
Pure-Python deterministic resume optimization engine.

No I/O, no ORM, no side effects. All public methods accept plain dicts
(output of ProfileSerializer.to_dict()) and return dataclass instances.
"""
from __future__ import annotations

import itertools
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from types import SimpleNamespace

from django.utils import timezone


# ── Suggestion type constants ─────────────────────────────────────────────────

class SuggestionType:
    STRENGTHEN_BULLET = "STRENGTHEN_BULLET"
    EXPAND_SUMMARY = "EXPAND_SUMMARY"
    ADD_ACHIEVEMENTS = "ADD_ACHIEVEMENTS"
    ADD_SKILLS = "ADD_SKILLS"
    COMPLETE_CONTACT = "COMPLETE_CONTACT"
    ADD_SECTION = "ADD_SECTION"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class Suggestion:
    id: str
    type: str
    priority: int
    guidance: str
    target: dict
    original: str = ""
    rewrite: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "priority": self.priority,
            "guidance": self.guidance,
            "target": self.target,
            "original": self.original,
            "rewrite": self.rewrite,
        }


@dataclass
class KeywordGap:
    token: str
    tier: str
    priority_score: float
    suggested_section: str

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "tier": self.tier,
            "priority_score": self.priority_score,
            "suggested_section": self.suggested_section,
        }


@dataclass
class SectionReport:
    name: str
    current_pts: int
    max_pts: int
    opportunity: int
    suggestions: list[Suggestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "current_pts": self.current_pts,
            "max_pts": self.max_pts,
            "opportunity": self.opportunity,
            "suggestions": [s.to_dict() for s in self.suggestions],
        }


@dataclass
class OptimizationReport:
    current_score: int
    potential_score: int
    sections: list[SectionReport]
    keyword_gaps: list[KeywordGap]
    generated_at: str
    job_description_provided: bool = False

    def to_dict(self) -> dict:
        return {
            "current_score": self.current_score,
            "potential_score": self.potential_score,
            "sections": [s.to_dict() for s in self.sections],
            "keyword_gaps": [kg.to_dict() for kg in self.keyword_gaps],
            "generated_at": self.generated_at,
            "job_description_provided": self.job_description_provided,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptimizationReport":
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        sections = []
        for sd in data.get("sections", []):
            suggestions = [Suggestion(**sg) for sg in sd.get("suggestions", [])]
            sections.append(SectionReport(
                name=sd["name"],
                current_pts=sd["current_pts"],
                max_pts=sd["max_pts"],
                opportunity=sd["opportunity"],
                suggestions=suggestions,
            ))
        keyword_gaps = [KeywordGap(**kg) for kg in data.get("keyword_gaps", [])]
        return cls(
            current_score=data["current_score"],
            potential_score=data["potential_score"],
            sections=sections,
            keyword_gaps=keyword_gaps,
            generated_at=data.get("generated_at", ""),
            job_description_provided=data.get("job_description_provided", False),
        )


# ── Analyzer ──────────────────────────────────────────────────────────────────

class OptimizationAnalyzer:

    _SECTION_MAX: dict[str, int] = {
        "contact": 15,
        "summary": 10,
        "experience": 30,
        "education": 20,
        "skills": 15,
        "additional": 10,
    }

    # education = 0.0: retroactively earning a degree is not a resume edit
    _ACTIONABILITY: dict[str, float] = {
        "contact": 0.8,
        "summary": 1.0,
        "experience": 1.0,
        "education": 0.0,
        "skills": 0.9,
        "additional": 0.5,
    }

    _CONTACT_FIELDS: list[str] = ["full_name", "email", "phone", "location"]

    _CONTACT_LABELS: dict[str, str] = {
        "full_name": "full name",
        "email": "email address",
        "phone": "phone number",
        "location": "location (city or region)",
    }

    _ACTION_VERBS: frozenset[str] = frozenset({
        "achieved", "accelerated", "analyzed", "architected", "automated",
        "boosted", "built",
        "championed", "coached", "collaborated", "configured", "coordinated",
        "created", "cut",
        "debugged", "decreased", "defined", "delivered", "deployed", "designed",
        "developed", "directed", "drove",
        "eliminated", "engineered", "enhanced", "established", "evaluated",
        "exceeded", "executed",
        "facilitated", "founded",
        "generated", "grew", "guided",
        "headed", "hired",
        "identified", "implemented", "improved", "increased", "integrated",
        "investigated",
        "launched", "led",
        "managed", "mentored", "migrated",
        "negotiated",
        "optimized", "orchestrated", "oversaw",
        "partnered", "planned", "prioritized", "programmed",
        "reduced", "refactored", "released", "researched",
        "saved", "scaled", "shipped", "simplified", "spearheaded",
        "streamlined", "supervised",
        "trained", "transformed", "troubleshot",
        "upgraded",
    })

    # Matches numbers paired with a unit that signals quantification
    _QUANTIFICATION_RE = re.compile(
        r"\b\d+\s*%"
        r"|\b\d+\s*x\b"
        r"|\$\s*\d+"
        r"|\b\d+\s*(?:k|m|b)\b"
        r"|\b\d+\s+(?:users?|customers?|engineers?|members?|people|teams?)"
        r"|\b\d+\s+(?:hours?|days?|weeks?|months?|years?|minutes?|mins?)"
        r"|\b\d+\s+(?:times?|points?|requests?|transactions?|services?|apis?)",
        re.IGNORECASE,
    )

    # ── Public entry point ────────────────────────────────────────────────────

    @classmethod
    def analyze(
        cls,
        profile_data: dict,
        ats_result: dict,
        job_description: str = "",
    ) -> OptimizationReport:
        breakdown = ats_result.get("breakdown", {})
        current_score = ats_result.get("score", 0)

        sections = cls._analyze_sections(profile_data, breakdown)
        keyword_gaps = cls._analyze_keywords(profile_data, job_description) if job_description else []
        potential_score = cls._compute_potential(current_score, breakdown)

        return OptimizationReport(
            current_score=current_score,
            potential_score=potential_score,
            sections=sections,
            keyword_gaps=keyword_gaps,
            generated_at=timezone.now().isoformat(),
            job_description_provided=bool(job_description),
        )

    # ── Section analysis ──────────────────────────────────────────────────────

    @classmethod
    def _analyze_sections(cls, profile_data: dict, breakdown: dict) -> list[SectionReport]:
        priority_counter = itertools.count(1)
        sections = []

        for name in ("contact", "summary", "experience", "skills", "additional"):
            current_pts = breakdown.get(name, 0)
            max_pts = cls._SECTION_MAX[name]
            suggestions = cls._dispatch_suggestions(name, profile_data, current_pts, priority_counter)
            sections.append(SectionReport(
                name=name,
                current_pts=current_pts,
                max_pts=max_pts,
                opportunity=max_pts - current_pts,
                suggestions=suggestions,
            ))

        sections.sort(key=lambda s: (-s.opportunity, s.name))
        return sections

    @classmethod
    def _dispatch_suggestions(
        cls, name: str, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        dispatch = {
            "contact": cls._contact_suggestions,
            "summary": cls._summary_suggestions,
            "experience": cls._experience_suggestions,
            "skills": cls._skills_suggestions,
            "additional": cls._additional_suggestions,
        }
        handler = dispatch.get(name)
        return handler(profile_data, current_pts, counter) if handler else []

    @classmethod
    def _contact_suggestions(
        cls, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        if current_pts >= 15:
            return []
        missing = [f for f in cls._CONTACT_FIELDS if not profile_data.get(f)]
        if not missing:
            return []
        labels = " and ".join(cls._CONTACT_LABELS[f] for f in missing)
        return [Suggestion(
            id=str(uuid.uuid4()),
            type=SuggestionType.COMPLETE_CONTACT,
            priority=next(counter),
            guidance=f"Add your {labels} to complete your contact information.",
            target={"section": "contact", "missing_fields": missing},
            original="",
        )]

    @classmethod
    def _summary_suggestions(
        cls, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        if current_pts >= 10:
            return []
        summary = profile_data.get("professional_summary") or ""
        length = len(summary)
        if length == 0:
            guidance = (
                "Write a professional summary of 3-4 sentences. "
                "Highlight your top skills, years of experience, and what makes you unique."
            )
        else:
            guidance = (
                f"Your summary is {length} characters. "
                "Expand it to at least 100 characters with specific skills, achievements, and a target role."
            )
        return [Suggestion(
            id=str(uuid.uuid4()),
            type=SuggestionType.EXPAND_SUMMARY,
            priority=next(counter),
            guidance=guidance,
            target={"section": "summary"},
            original=summary,
        )]

    @classmethod
    def _experience_suggestions(
        cls, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        exps = profile_data.get("work_experiences") or []
        if not exps:
            return []

        suggestions: list[Suggestion] = []

        for i, exp in enumerate(exps):
            achievements = exp.get("achievements") or []
            company = exp.get("company_name") or "this company"

            if len(achievements) < 2:
                need = 2 - len(achievements)
                suggestions.append(Suggestion(
                    id=str(uuid.uuid4()),
                    type=SuggestionType.ADD_ACHIEVEMENTS,
                    priority=next(counter),
                    guidance=(
                        f"Add {need} achievement bullet{'s' if need > 1 else ''} to your role at {company}. "
                        "Start each with an action verb and quantify the impact."
                    ),
                    target={"section": "experience", "experience_index": i, "company": company},
                    original=achievements[0] if achievements else "",
                ))
            else:
                for j, bullet in enumerate(achievements):
                    if cls._bullet_impact_score(bullet) < 0.50:
                        suggestions.append(Suggestion(
                            id=str(uuid.uuid4()),
                            type=SuggestionType.STRENGTHEN_BULLET,
                            priority=next(counter),
                            guidance=(
                                "Strengthen with a strong action verb, a measurable metric "
                                "(%, $, count, or time), and a clear outcome."
                            ),
                            target={
                                "section": "experience",
                                "experience_index": i,
                                "bullet_index": j,
                                "company": company,
                            },
                            original=bullet,
                        ))

        return suggestions

    @classmethod
    def _skills_suggestions(
        cls, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        if current_pts >= 15:
            return []
        skill_count = len(profile_data.get("skills") or [])
        if skill_count == 0:
            guidance = (
                "Add at least 8 relevant skills. "
                "Include both technical and soft skills relevant to your target role."
            )
        else:
            needed = max(0, 8 - skill_count)
            guidance = (
                f"Add {needed} more skill{'s' if needed != 1 else ''} to reach 8+. "
                "Focus on technologies and competencies mentioned in job descriptions you are targeting."
            )
        return [Suggestion(
            id=str(uuid.uuid4()),
            type=SuggestionType.ADD_SKILLS,
            priority=next(counter),
            guidance=guidance,
            target={"section": "skills", "current_count": skill_count, "target_count": 8},
            original="",
        )]

    @classmethod
    def _additional_suggestions(
        cls, profile_data: dict, current_pts: int, counter
    ) -> list[Suggestion]:
        if current_pts >= 10:
            return []
        has_certs = bool(profile_data.get("certifications"))
        has_projects = bool(profile_data.get("projects"))
        suggestions: list[Suggestion] = []

        if not has_certs:
            suggestions.append(Suggestion(
                id=str(uuid.uuid4()),
                type=SuggestionType.ADD_SECTION,
                priority=next(counter),
                guidance=(
                    "Add relevant certifications (e.g., AWS, Google Cloud, PMP) to strengthen your profile. "
                    "Even in-progress certifications are worth including."
                ),
                target={"section": "certifications"},
                original="",
            ))

        if not has_projects:
            suggestions.append(Suggestion(
                id=str(uuid.uuid4()),
                type=SuggestionType.ADD_SECTION,
                priority=next(counter),
                guidance=(
                    "Add 1-2 portfolio projects that demonstrate your skills. "
                    "Include the tech stack and a brief description of the impact."
                ),
                target={"section": "projects"},
                original="",
            ))

        return suggestions

    # ── Keyword gap analysis ──────────────────────────────────────────────────

    @classmethod
    def _analyze_keywords(cls, profile_data: dict, job_description: str) -> list[KeywordGap]:
        from apps.career_hub.services.match_scoring import extract_skill_gaps

        skills = [SimpleNamespace(name=s["name"]) for s in (profile_data.get("skills") or [])]
        we_tech: list[str] = []
        for we in (profile_data.get("work_experiences") or []):
            we_tech.extend(we.get("technologies") or [])
        proj_tech: list[str] = []
        for proj in (profile_data.get("projects") or []):
            proj_tech.extend(proj.get("technologies") or [])
        certs = [SimpleNamespace(name=c["name"]) for c in (profile_data.get("certifications") or [])]

        gaps = extract_skill_gaps(
            skills=skills,
            work_experience_technologies=we_tech,
            project_technologies=proj_tech,
            certifications=certs,
            job_description=job_description,
        )

        raw = re.findall(r"[a-z][a-z0-9+#.]*", job_description.lower())
        token_freq = Counter(raw)
        max_freq = max(token_freq.values()) if token_freq else 1

        tier_weights = {"critical": 1.0, "moderate": 0.6, "soft": 0.4, "low": 0.1}

        keyword_gaps: list[KeywordGap] = []
        for tier, tokens in gaps.items():
            for token in tokens:
                freq_norm = token_freq.get(token, 0) / max_freq
                priority_score = round(
                    0.5 * tier_weights.get(tier, 0.1) + 0.3 * freq_norm + 0.2,
                    4,
                )
                keyword_gaps.append(KeywordGap(
                    token=token,
                    tier=tier,
                    priority_score=priority_score,
                    suggested_section=cls._keyword_suggested_section(token, tier),
                ))

        keyword_gaps.sort(key=lambda kg: (-kg.priority_score, kg.token))
        return keyword_gaps[:15]

    # ── Potential score ───────────────────────────────────────────────────────

    @classmethod
    def _compute_potential(cls, current_score: int, breakdown: dict) -> int:
        gain = 0.0
        for section, max_pts in cls._SECTION_MAX.items():
            opportunity = max_pts - breakdown.get(section, 0)
            if opportunity > 0:
                gain += opportunity * cls._ACTIONABILITY.get(section, 0.5)
        potential = min(95, int(current_score + gain))
        return max(current_score, potential)

    # ── Per-bullet helpers ────────────────────────────────────────────────────

    @classmethod
    def _bullet_impact_score(cls, bullet: str) -> float:
        if not bullet or not bullet.strip():
            return 0.0

        stripped = bullet.strip()
        score = 0.0

        words = stripped.split()
        if words:
            first_word = re.sub(r"[^a-z]", "", words[0].lower())
            if first_word in cls._ACTION_VERBS:
                score += 0.35

        if cls._QUANTIFICATION_RE.search(stripped):
            score += 0.35

        if 40 <= len(stripped) <= 200:
            score += 0.30

        return round(score, 2)

    @classmethod
    def _keyword_suggested_section(cls, token: str, tier: str) -> str:
        if tier == "critical":
            return "skills"
        if tier == "soft":
            return "summary"
        return "experience"
