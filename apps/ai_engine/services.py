import logging
from django.conf import settings
from apps.ai_engine.providers.base import IAIProvider, AIResponse
from apps.ai_engine.models import AIFeature

logger = logging.getLogger(__name__)


def get_ai_provider() -> IAIProvider:
    """Factory: returns configured AI provider."""
    provider_name = getattr(settings, "AI_PROVIDER", "openai")
    if provider_name == "openai":
        from apps.ai_engine.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "anthropic":
        from apps.ai_engine.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif provider_name == "gemini":
        from apps.ai_engine.providers.gemini_provider import GeminiProvider
        return GeminiProvider()
    raise ValueError(f"Unknown AI provider: {provider_name}")


class AIService:
    """Facade over all AI features. Logs usage after each call."""

    def __init__(self, user=None):
        self._user = user
        self._provider = get_ai_provider()

    def _call(self, prompt: str, system_prompt: str, feature: str, max_tokens: int = 2000) -> str:
        response = self._provider.complete(prompt, system_prompt, max_tokens)
        self._log_usage(feature, response)
        return response.content

    def _log_usage(self, feature: str, response: AIResponse) -> None:
        if not self._user:
            return
        try:
            from apps.ai_engine.models import AIUsageLog
            AIUsageLog.objects.create(
                user=self._user,
                feature=feature,
                provider=self._provider.provider_name,
                model_name=self._provider.model_name,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
            )
        except Exception:
            logger.warning("Failed to log AI usage", exc_info=True)

    def enhance_bullet(self, original: str, context: dict) -> str:
        system = (
            "You are an expert resume writer. Enhance the given bullet point to be "
            "more impactful, using strong action verbs and quantifiable results where possible. "
            "Return ONLY the enhanced bullet point, nothing else."
        )
        prompt = (
            f"Role: {context.get('role', 'Professional')}\n"
            f"Company: {context.get('company', 'a company')}\n"
            f"Original: {original}"
        )
        return self._call(prompt, system, AIFeature.BULLET_ENHANCE, max_tokens=200)

    def generate_summary(self, profile_data: dict, target_role: str) -> str:
        system = (
            "You are an expert resume writer. Generate a compelling 3-4 sentence professional "
            "summary for the given profile targeting the specified role. "
            "Be specific, use industry keywords, and make it ATS-friendly."
        )
        prompt = (
            f"Target Role: {target_role}\n"
            f"Years Experience: {profile_data.get('years_experience', 'N/A')}\n"
            f"Top Skills: {', '.join(profile_data.get('top_skills', []))}\n"
            f"Recent Role: {profile_data.get('recent_role', 'N/A')}"
        )
        return self._call(prompt, system, AIFeature.SUMMARY_GENERATE, max_tokens=300)

    def generate_cover_letter(
        self, profile_data: dict, company_name: str, job_title: str,
        job_description: str = "", tone: str = "professional"
    ) -> str:
        system = (
            f"You are an expert cover letter writer. Write a {tone} cover letter. "
            "Use the profile data to personalize it. Include relevant accomplishments. "
            "Keep it to 3-4 paragraphs. Return ONLY plain text body paragraphs, "
            "no salutation, closing, Markdown, bullets, or formatting markers."
        )
        experiences = profile_data.get("work_experiences", [])
        current_role = experiences[0].get("job_title", "") if experiences else ""
        top_skills = [s.get("name", "") if isinstance(s, dict) else s for s in profile_data.get("skills", [])[:8]]
        raw_achievements = profile_data.get("achievements", [])
        achievement_titles = [
            a.get("title", "") if isinstance(a, dict) else a for a in raw_achievements[:3]
        ]
        prompt = (
            f"Company: {company_name}\n"
            f"Role: {job_title}\n"
            f"Job Description: {job_description[:1000] if job_description else 'Not provided'}\n"
            f"Candidate Name: {profile_data.get('full_name', '')}\n"
            f"Current Role: {current_role}\n"
            f"Top Skills: {', '.join(top_skills)}\n"
            f"Key Achievements: {'; '.join(achievement_titles)}"
        )
        return self._call(prompt, system, AIFeature.COVER_LETTER_GENERATE, max_tokens=800)

    def rewrite_cover_letter(
        self, body_content: str, company_name: str, job_title: str,
        tone: str = "professional", instruction: str = ""
    ) -> str:
        instruction_line = f"Instruction: {instruction}\n" if instruction else ""
        system = (
            f"You are an expert cover letter writer. Rewrite the provided cover letter body "
            f"maintaining a {tone} tone for {job_title} at {company_name}. "
            "Improve clarity, impact, and flow. "
            "Return ONLY plain text rewritten body paragraphs, no salutation, closing, "
            "Markdown, bullets, or formatting markers."
        )
        prompt = (
            f"{instruction_line}"
            f"Original Cover Letter:\n{body_content[:2000]}"
        )
        return self._call(prompt, system, AIFeature.COVER_LETTER_REWRITE, max_tokens=800)

    def improve_cover_letter_tone(self, body_content: str, target_tone: str) -> str:
        tone_guides = {
            "executive": "authoritative, strategic, and results-driven with C-suite gravitas",
            "technical": "precise, detail-oriented, highlighting technical depth and methodology",
            "startup": "energetic, mission-driven, collaborative, and growth-oriented",
            "friendly": "warm, personable, enthusiastic, and conversational",
            "formal": "highly professional, structured, and respectful of conventions",
            "professional": "polished, confident, and achievement-focused",
        }
        tone_desc = tone_guides.get(target_tone, target_tone)
        system = (
            f"You are an expert cover letter writer. Rewrite the cover letter body to be "
            f"{tone_desc}. Preserve all factual content but adjust language, structure, and tone. "
            "Return ONLY plain text rewritten body paragraphs, no Markdown, bullets, or formatting markers."
        )
        prompt = f"Cover Letter:\n{body_content[:2000]}"
        return self._call(prompt, system, AIFeature.COVER_LETTER_IMPROVE_TONE, max_tokens=800)

    def improve_cover_letter_ats(
        self, body_content: str, job_description: str = "", job_title: str = ""
    ) -> str:
        system = (
            "You are an ATS optimization expert and cover letter writer. "
            "Rewrite the cover letter to improve ATS keyword alignment with the job description. "
            "Naturally incorporate relevant keywords, action verbs, and quantifiable achievements. "
            "Return ONLY plain text improved body paragraphs, no Markdown, bullets, or formatting markers."
        )
        jd_section = f"Job Description:\n{job_description[:1500]}" if job_description else f"Role: {job_title}"
        prompt = (
            f"{jd_section}\n\n"
            f"Current Cover Letter:\n{body_content[:2000]}"
        )
        return self._call(prompt, system, AIFeature.COVER_LETTER_IMPROVE_ATS, max_tokens=800)

    def rewrite_resume_bullet(self, original: str, context: dict) -> str:
        system = (
            "You are an expert resume writer. Rewrite the bullet point to be more impactful "
            "using a strong action verb and a quantifiable result. "
            "Keep it concise (40–200 characters). "
            "Return ONLY the rewritten bullet point, nothing else."
        )
        prompt = (
            f"Role: {context.get('role', 'Professional')}\n"
            f"Company: {context.get('company', 'a company')}\n"
            f"Original bullet: {original}"
        )
        return self._call(prompt, system, AIFeature.RESUME_BULLET_REWRITE, max_tokens=150)

    def optimize_resume_summary(
        self, current_summary: str, profile_data: dict, target_role: str = ""
    ) -> str:
        system = (
            "You are an expert resume writer. Write or improve a professional summary. "
            "It should be 3–4 sentences, ATS-friendly, and highlight key skills and experience. "
            "Return ONLY the summary text, nothing else."
        )
        exps = profile_data.get("work_experiences") or []
        recent_role = exps[0].get("job_title", "") if exps else ""
        skills_raw = profile_data.get("skills") or []
        skill_names = [
            s["name"] if isinstance(s, dict) else s for s in skills_raw[:6]
        ]
        prompt = (
            f"Target Role: {target_role or 'Professional'}\n"
            f"Recent Role: {recent_role}\n"
            f"Top Skills: {', '.join(skill_names)}\n"
            f"Current Summary: {current_summary or 'None'}"
        )
        return self._call(prompt, system, AIFeature.RESUME_SUMMARY_OPTIMIZE, max_tokens=250)

    def analyze_ats(self, resume_text: str, job_description: str = "") -> dict:
        system = (
            "You are an ATS (Applicant Tracking System) expert. Analyze the resume and provide: "
            "1. An ATS score (0-100), "
            "2. Missing keywords, "
            "3. Present keywords, "
            "4. Specific improvement suggestions. "
            "Return JSON with keys: score, missing_keywords, present_keywords, suggestions."
        )
        prompt = (
            f"Resume:\n{resume_text[:3000]}\n\n"
            f"Job Description:\n{job_description[:1000] if job_description else 'Generic professional role'}"
        )
        import json
        raw = self._call(prompt, system, AIFeature.ATS_ANALYZE, max_tokens=500)
        try:
            # Strip markdown code fences if present
            clean = raw.strip().strip("```json").strip("```").strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            return {"score": 0, "missing_keywords": [], "present_keywords": [], "suggestions": [raw]}
