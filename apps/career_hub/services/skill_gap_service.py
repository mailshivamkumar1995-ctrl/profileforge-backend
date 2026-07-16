from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.cache import cache

from apps.career_hub.models import ResumeMatchScore
from apps.career_hub.services.match_resources import get_resource_for_skill, get_resources_for_gaps
from apps.career_hub.services.match_scoring import score_to_display

_SUMMARY_TTL = 900
_MAX_CRS_SCORES = 10
_MAX_TOP_CRITICAL = 10
_MAX_TOP_OTHERS = 5

VALID_RECOMMENDATION_TIERS = frozenset({"critical", "moderate", "soft", "all"})


def _cache_key_summary(user_id: object) -> str:
    return f"skill_gap:summary:{user_id}"


@dataclass
class SkillGapEntry:
    token: str
    job_count: int
    display_name: str | None = None
    category: str | None = None
    description: str | None = None
    resource_type: str | None = None
    url: str | None = None
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class SkillGapSummary:
    career_readiness_score: int | None
    total_jobs_scored: int
    top_critical_gaps: list[SkillGapEntry]
    top_moderate_gaps: list[SkillGapEntry]
    top_soft_gaps: list[SkillGapEntry]
    gap_counts: dict[str, int]


@dataclass
class JobSkillGap:
    job_id: str
    job_title: str
    job_company: str
    overall_score: Decimal
    score_display: int
    critical_gaps: list[dict]
    moderate_gaps: list[dict]
    soft_gaps: list[dict]
    low_gaps: list[dict]


def _enrich_entry(token: str, job_count: int) -> SkillGapEntry:
    descriptor = get_resource_for_skill(token)
    if descriptor is not None:
        return SkillGapEntry(
            token=token,
            job_count=job_count,
            display_name=descriptor.display_name,
            category=descriptor.category,
            description=descriptor.description,
            resource_type=descriptor.resource_type,
            url=descriptor.url,
            prerequisites=list(descriptor.prerequisites),
        )
    return SkillGapEntry(token=token, job_count=job_count)


def _normalize_resource_dict(item: dict) -> dict:
    return {
        "token": item.get("token", ""),
        "display_name": item.get("display_name"),
        "category": item.get("category"),
        "description": item.get("description"),
        "resource_type": item.get("resource_type"),
        "url": item.get("url"),
        "prerequisites": item.get("prerequisites", []),
    }


def _compute_summary(user: object) -> SkillGapSummary:
    rows = list(
        ResumeMatchScore.objects
        .filter(user=user)
        .order_by("-overall_score")
        .values("overall_score", "skill_gaps")
    )
    total = len(rows)

    if total == 0:
        return SkillGapSummary(
            career_readiness_score=None,
            total_jobs_scored=0,
            top_critical_gaps=[],
            top_moderate_gaps=[],
            top_soft_gaps=[],
            gap_counts={"critical": 0, "moderate": 0, "soft": 0, "low": 0},
        )

    top_scores = [row["overall_score"] for row in rows[:_MAX_CRS_SCORES]]
    crs = round(float(sum(top_scores) / len(top_scores)) * 100)

    critical_counter: Counter = Counter()
    moderate_counter: Counter = Counter()
    soft_counter: Counter = Counter()
    low_counter: Counter = Counter()

    for row in rows:
        gaps = row["skill_gaps"] or {}
        critical_counter.update(gaps.get("critical", []))
        moderate_counter.update(gaps.get("moderate", []))
        soft_counter.update(gaps.get("soft", []))
        low_counter.update(gaps.get("low", []))

    top_critical = [
        _enrich_entry(token, count)
        for token, count in critical_counter.most_common(_MAX_TOP_CRITICAL)
    ]
    top_moderate = [
        _enrich_entry(token, count)
        for token, count in moderate_counter.most_common(_MAX_TOP_OTHERS)
    ]
    top_soft = [
        _enrich_entry(token, count)
        for token, count in soft_counter.most_common(_MAX_TOP_OTHERS)
    ]

    return SkillGapSummary(
        career_readiness_score=crs,
        total_jobs_scored=total,
        top_critical_gaps=top_critical,
        top_moderate_gaps=top_moderate,
        top_soft_gaps=top_soft,
        gap_counts={
            "critical": len(critical_counter),
            "moderate": len(moderate_counter),
            "soft": len(soft_counter),
            "low": len(low_counter),
        },
    )


def get_skill_gap_summary(user: object) -> SkillGapSummary:
    key = _cache_key_summary(user.id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _compute_summary(user)
    cache.set(key, result, _SUMMARY_TTL)
    return result


def get_skill_gap_recommendations(user: object, tier: str = "critical") -> list[dict]:
    summary = get_skill_gap_summary(user)

    tier_map: dict[str, list[SkillGapEntry]] = {
        "critical": summary.top_critical_gaps,
        "moderate": summary.top_moderate_gaps,
        "soft": summary.top_soft_gaps,
    }

    if tier == "all":
        entries_with_tier = (
            [(e, "critical") for e in summary.top_critical_gaps]
            + [(e, "soft") for e in summary.top_soft_gaps]
            + [(e, "moderate") for e in summary.top_moderate_gaps]
        )
        entries_with_tier.sort(key=lambda pair: -pair[0].job_count)
    else:
        entries_with_tier = [(e, tier) for e in tier_map.get(tier, [])]

    return [
        {
            "token": entry.token,
            "tier": entry_tier,
            "job_count": entry.job_count,
            "display_name": entry.display_name,
            "category": entry.category,
            "description": entry.description,
            "resource_type": entry.resource_type,
            "url": entry.url,
            "prerequisites": entry.prerequisites,
        }
        for entry, entry_tier in entries_with_tier
    ]


def get_job_skill_gap(user: object, job_id: object) -> JobSkillGap:
    score = (
        ResumeMatchScore.objects
        .select_related("job")
        .get(user=user, job_id=job_id)
    )

    gaps = score.skill_gaps or {}
    enriched = get_resources_for_gaps(gaps)

    return JobSkillGap(
        job_id=str(score.job_id),
        job_title=score.job.title,
        job_company=score.job.company,
        overall_score=score.overall_score,
        score_display=score_to_display(score.overall_score),
        critical_gaps=[_normalize_resource_dict(x) for x in enriched.get("critical", [])],
        moderate_gaps=[_normalize_resource_dict(x) for x in enriched.get("moderate", [])],
        soft_gaps=[_normalize_resource_dict(x) for x in enriched.get("soft", [])],
        low_gaps=[_normalize_resource_dict(x) for x in enriched.get("low", [])],
    )
