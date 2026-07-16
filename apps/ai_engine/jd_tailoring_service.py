"""
JD Tailoring Service — the core feature of ProfileForge.

Given a job description, this service:
1. Parses the JD to extract company name, role title, and key requirements
2. Tailors the user's resume content (summary, bullets) to match the JD
3. Generates a full cover letter personalised to the JD
4. Creates Resume and CoverLetter draft records named after the company

All heavy work is done in a single structured AI prompt chain.
"""
import json
import logging
import re
from typing import Optional

from apps.ai_engine.services import AIService
from apps.profiles.services import ProfileService

logger = logging.getLogger(__name__)


class JDTailoringService:
    """Orchestrates JD parsing → resume tailoring → cover letter generation."""

    def __init__(self, user):
        self._user = user
        self._ai = AIService(user=user)

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def tailor(self, job_description: str) -> dict:
        """
        Full pipeline.
        Returns a dict with:
          - company_name
          - role_title
          - tailored_summary
          - tailored_bullets   (list of bullet strings)
          - cover_letter_body  (plain text paragraphs)
          - resume_id          (created Resume draft UUID)
          - cover_letter_id    (created CoverLetter draft UUID)
          - keywords_matched   (list of JD keywords found in profile)
          - keywords_missing   (list of JD keywords NOT found in profile)
        """
        profile_data = self._get_profile_data()

        # Step 1 — Parse JD
        jd_meta = self._parse_jd(job_description)
        company_name = jd_meta.get("company_name", "Unknown Company")
        role_title = jd_meta.get("role_title", "Unknown Role")
        requirements = jd_meta.get("requirements", [])
        keywords = jd_meta.get("keywords", [])

        logger.info("JD parsed: company=%s role=%s keywords=%d", company_name, role_title, len(keywords))

        # Step 2 — Tailor resume
        tailoring = self._tailor_resume(profile_data, job_description, company_name, role_title, requirements)
        tailored_summary = tailoring.get("tailored_summary", "")
        tailored_bullets = tailoring.get("tailored_bullets", [])
        keywords_matched = tailoring.get("keywords_matched", [])
        keywords_missing = tailoring.get("keywords_missing", [])

        # Step 3 — Generate cover letter
        cover_letter_body = self._generate_cover_letter(
            profile_data, job_description, company_name, role_title
        )

        # Step 4 — Persist draft documents
        draft_title = f"{company_name} — {role_title}"
        resume_id = self._create_resume_draft(draft_title, tailored_summary, tailored_bullets)
        cover_letter_id = self._create_cover_letter_draft(draft_title, company_name, role_title, cover_letter_body)

        return {
            "company_name": company_name,
            "role_title": role_title,
            "tailored_summary": tailored_summary,
            "tailored_bullets": tailored_bullets,
            "cover_letter_body": cover_letter_body,
            "resume_id": str(resume_id) if resume_id else None,
            "cover_letter_id": str(cover_letter_id) if cover_letter_id else None,
            "keywords_matched": keywords_matched,
            "keywords_missing": keywords_missing,
            "draft_title": draft_title,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1 — Parse JD
    # ──────────────────────────────────────────────────────────────────────────

    def _parse_jd(self, jd: str) -> dict:
        system = (
            "You are a recruitment analyst. Extract structured information from the provided job description. "
            "Return ONLY valid JSON with keys: "
            "company_name (string), role_title (string), requirements (list of strings, max 10), "
            "keywords (list of important technical/domain keywords, max 20). "
            "If company name is not mentioned, use 'Unknown Company'."
        )
        prompt = f"Job Description:\n{jd[:3000]}"
        raw = self._ai._call(prompt, system, feature="jd_parse", max_tokens=600)
        return self._parse_json(raw, {
            "company_name": "Unknown Company",
            "role_title": "Unknown Role",
            "requirements": [],
            "keywords": [],
        })

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2 — Tailor resume content
    # ──────────────────────────────────────────────────────────────────────────

    def _tailor_resume(self, profile_data: dict, jd: str, company: str, role: str, requirements: list) -> dict:
        experiences = profile_data.get("work_experiences", [])
        exp_summaries = []
        for exp in experiences[:5]:
            exp_summaries.append(
                f"- {exp.get('job_title')} at {exp.get('company_name')}: {exp.get('description', '')[:300]}"
            )

        skills = [s.get("name", "") if isinstance(s, dict) else s for s in profile_data.get("skills", [])[:20]]
        achievements = profile_data.get("achievements", [])
        ach_list = [a.get("title", "") if isinstance(a, dict) else a for a in achievements[:5]]

        system = (
            "You are an expert resume writer and ATS optimization specialist. "
            "Given a candidate's profile and a job description, produce: "
            "1. A tailored professional summary (3-4 sentences, ATS-optimized). "
            "2. 5-8 powerful resume bullet points that match the JD requirements using STAR format. "
            "3. A list of JD keywords that match the candidate's background. "
            "4. A list of JD keywords the candidate should address. "
            "Return ONLY valid JSON with keys: tailored_summary (string), tailored_bullets (list of strings), "
            "keywords_matched (list), keywords_missing (list)."
        )
        prompt = (
            f"Target Company: {company}\n"
            f"Target Role: {role}\n"
            f"Key Requirements: {', '.join(requirements[:8])}\n\n"
            f"Candidate Skills: {', '.join(skills)}\n"
            f"Key Achievements: {'; '.join(ach_list)}\n\n"
            f"Work Experience:\n{''.join(exp_summaries)}\n\n"
            f"Current Summary: {profile_data.get('professional_summary', '')[:500]}\n\n"
            f"Job Description (excerpt):\n{jd[:2000]}"
        )
        raw = self._ai._call(prompt, system, feature="jd_tailor_resume", max_tokens=1500)
        return self._parse_json(raw, {
            "tailored_summary": "",
            "tailored_bullets": [],
            "keywords_matched": [],
            "keywords_missing": [],
        })

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3 — Generate cover letter
    # ──────────────────────────────────────────────────────────────────────────

    def _generate_cover_letter(self, profile_data: dict, jd: str, company: str, role: str) -> str:
        return self._ai.generate_cover_letter(
            profile_data=profile_data,
            company_name=company,
            job_title=role,
            job_description=jd,
            tone="professional",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4 — Persist drafts
    # ──────────────────────────────────────────────────────────────────────────

    def _create_resume_draft(self, title: str, tailored_summary: str, tailored_bullets: list) -> Optional[str]:
        try:
            from apps.resumes.services import ResumeService
            # Store tailored bullets as a custom_section so they render in the resume template
            custom_sections = []
            if tailored_bullets:
                custom_sections = [{
                    "type": "tailored_bullets",
                    "title": "Key Achievements (JD-Tailored)",
                    "items": tailored_bullets,
                }]
            resume = ResumeService.create(self._user, {
                "title": title,
                "target_role": "",
                "target_company": "",
                "custom_sections": custom_sections,
            })
            return resume.id
        except Exception:
            logger.warning("Failed to create resume draft for JD tailor", exc_info=True)
            return None

    def _create_cover_letter_draft(self, title: str, company: str, role: str, body: str) -> Optional[str]:
        try:
            from apps.cover_letters.services import CoverLetterService
            cl = CoverLetterService.create(self._user, {
                "title": title,
                "company_name": company,
                "job_title": role,
                "body_content": body,
                "tone": "professional",
                "ai_generated": True,
            })
            return cl.id
        except Exception:
            logger.warning("Failed to create cover letter draft for JD tailor", exc_info=True)
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_profile_data(self) -> dict:
        try:
            profile = ProfileService.get_profile(self._user)
            exps = []
            for exp in profile.work_experiences.all()[:5]:
                exps.append({
                    "job_title": exp.job_title,
                    "company_name": exp.company_name,
                    "description": exp.description,
                    "is_current": exp.is_current,
                })
            skills = [{"name": s.name, "category": s.category} for s in profile.skills.all()]
            achievements = [{"title": a.title, "issuer": a.issuer} for a in profile.achievements.all()]
            return {
                "full_name": f"{profile.user.first_name} {profile.user.last_name}".strip(),
                "professional_summary": profile.professional_summary or "",
                "work_experiences": exps,
                "skills": skills,
                "achievements": achievements,
            }
        except Exception:
            logger.warning("Could not load profile for JD tailoring", exc_info=True)
            return {}

    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        """Strip markdown fences and parse JSON, falling back to default."""
        try:
            clean = raw.strip()
            # Remove ```json ... ``` fences
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
            return json.loads(clean.strip())
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse AI JSON response: %s", raw[:200])
            return default
