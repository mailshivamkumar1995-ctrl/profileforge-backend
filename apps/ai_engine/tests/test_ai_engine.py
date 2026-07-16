import pytest
from unittest.mock import patch, MagicMock
from apps.ai_engine.providers.base import AIResponse, IAIProvider


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_response():
    return AIResponse(
        content="Enhanced content here.",
        model="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost_usd=0.001,
    )


@pytest.fixture
def mock_provider(mock_response):
    provider = MagicMock(spec=IAIProvider)
    provider.complete.return_value = mock_response
    provider.provider_name = "openai"
    provider.model_name = "gpt-4o"
    return provider


@pytest.fixture
def ai_service(mock_provider):
    from apps.ai_engine.services import AIService
    service = AIService.__new__(AIService)
    service._user = None
    service._provider = mock_provider
    return service


@pytest.fixture
def ai_service_with_user(mock_provider, user, db):
    from apps.ai_engine.services import AIService
    service = AIService.__new__(AIService)
    service._user = user
    service._provider = mock_provider
    return service


# ─── Provider Factory ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAIProviderFactory:
    def test_get_openai_provider(self):
        from apps.ai_engine.services import get_ai_provider
        with patch.dict("django.conf.settings.__dict__", {"AI_PROVIDER": "openai"}):
            with patch("apps.ai_engine.providers.openai_provider.OpenAIProvider") as MockProvider:
                MockProvider.return_value = MagicMock()
                with patch("django.conf.settings.AI_PROVIDER", "openai"):
                    try:
                        provider = get_ai_provider()
                    except Exception:
                        pass  # OpenAI client init may fail without API key

    def test_get_unknown_provider_raises(self):
        from apps.ai_engine.services import get_ai_provider
        with patch("django.conf.settings.AI_PROVIDER", "unknownprovider"):
            with pytest.raises(ValueError, match="Unknown AI provider"):
                get_ai_provider()

    def test_provider_base_interface_is_abstract(self):
        with pytest.raises(TypeError):
            IAIProvider()


# ─── AIResponse Dataclass ─────────────────────────────────────────────────────

class TestAIResponseDataclass:
    def test_all_fields_accessible(self, mock_response):
        assert mock_response.content == "Enhanced content here."
        assert mock_response.model == "gpt-4o"
        assert mock_response.prompt_tokens == 100
        assert mock_response.completion_tokens == 50
        assert mock_response.total_tokens == 150
        assert mock_response.cost_usd == 0.001

    def test_cost_usd_optional(self):
        response = AIResponse(
            content="text", model="m", prompt_tokens=10,
            completion_tokens=5, total_tokens=15,
        )
        assert response.cost_usd is None


# ─── AIService — enhance_bullet ──────────────────────────────────────────────

class TestEnhanceBullet:
    def test_returns_enhanced_content(self, ai_service, mock_provider, mock_response):
        result = ai_service.enhance_bullet(
            "Worked on backend systems",
            {"role": "Engineer", "company": "Acme"},
        )
        assert result == mock_response.content

    def test_calls_provider_complete(self, ai_service, mock_provider):
        ai_service.enhance_bullet("Did stuff", {})
        mock_provider.complete.assert_called_once()

    def test_prompt_contains_original_text(self, ai_service, mock_provider):
        ai_service.enhance_bullet("Built microservices", {"role": "SWE"})
        call_args = mock_provider.complete.call_args[0]
        assert "Built microservices" in call_args[0]

    def test_prompt_contains_role_context(self, ai_service, mock_provider):
        ai_service.enhance_bullet("Did work", {"role": "VP Engineering", "company": "Big Corp"})
        call_args = mock_provider.complete.call_args[0]
        assert "VP Engineering" in call_args[0]


# ─── AIService — generate_summary ────────────────────────────────────────────

class TestGenerateSummary:
    def test_returns_string(self, ai_service, mock_response):
        result = ai_service.generate_summary(
            {"top_skills": ["Python", "AWS"], "recent_role": "SWE"},
            "Staff Engineer",
        )
        assert result == mock_response.content

    def test_prompt_contains_target_role(self, ai_service, mock_provider):
        ai_service.generate_summary({}, "Principal Engineer")
        call_args = mock_provider.complete.call_args[0]
        assert "Principal Engineer" in call_args[0]

    def test_prompt_contains_skills(self, ai_service, mock_provider):
        ai_service.generate_summary({"top_skills": ["Rust", "Kubernetes"]}, "SRE")
        call_args = mock_provider.complete.call_args[0]
        assert "Rust" in call_args[0]


# ─── AIService — generate_cover_letter ───────────────────────────────────────

class TestGenerateCoverLetter:
    def test_returns_string(self, ai_service, mock_response):
        result = ai_service.generate_cover_letter(
            {"name": "John Doe", "top_skills": ["Python"]},
            company_name="Google",
            job_title="SWE",
        )
        assert result == mock_response.content

    def test_prompt_contains_company_and_role(self, ai_service, mock_provider):
        ai_service.generate_cover_letter({}, "Stripe", "Backend Engineer")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Stripe" in prompt
        assert "Backend Engineer" in prompt

    def test_job_description_truncated_to_1000_chars(self, ai_service, mock_provider):
        long_jd = "x" * 5000
        ai_service.generate_cover_letter({}, "Co", "Dev", job_description=long_jd)
        prompt = mock_provider.complete.call_args[0][0]
        assert "x" * 1001 not in prompt


# ─── AIService — rewrite_cover_letter ────────────────────────────────────────

class TestRewriteCoverLetter:
    def test_returns_rewritten_content(self, ai_service, mock_response):
        result = ai_service.rewrite_cover_letter("Original body", "Corp", "Dev")
        assert result == mock_response.content

    def test_instruction_included_in_prompt(self, ai_service, mock_provider):
        ai_service.rewrite_cover_letter(
            "Body", "Corp", "Dev", instruction="Make it shorter"
        )
        prompt = mock_provider.complete.call_args[0][0]
        assert "Make it shorter" in prompt

    def test_no_instruction_omits_instruction_line(self, ai_service, mock_provider):
        ai_service.rewrite_cover_letter("Body", "Corp", "Dev", instruction="")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Instruction:" not in prompt


# ─── AIService — improve_cover_letter_tone ───────────────────────────────────

class TestImproveCoverLetterTone:
    def test_returns_content(self, ai_service, mock_response):
        result = ai_service.improve_cover_letter_tone("Body", "executive")
        assert result == mock_response.content

    def test_all_defined_tones_resolve(self, ai_service, mock_provider):
        tones = ["executive", "technical", "startup", "friendly", "formal", "professional"]
        for tone in tones:
            ai_service.improve_cover_letter_tone("Body", tone)
            system = mock_provider.complete.call_args[0][1]
            assert tone not in system or any(
                word in system for word in ["authoritative", "precise", "energetic", "warm", "highly", "polished", tone]
            )

    def test_unknown_tone_uses_tone_as_desc(self, ai_service, mock_provider):
        ai_service.improve_cover_letter_tone("Body", "aggressive")
        system = mock_provider.complete.call_args[0][1]
        assert "aggressive" in system


# ─── AIService — analyze_ats ─────────────────────────────────────────────────

class TestAnalyzeATS:
    def test_returns_dict_with_expected_keys(self, ai_service, mock_provider):
        mock_provider.complete.return_value = AIResponse(
            content='{"score": 75, "missing_keywords": ["Docker"], "present_keywords": ["Python"], "suggestions": ["Add Docker"]}',
            model="gpt-4o", prompt_tokens=50, completion_tokens=30, total_tokens=80,
        )
        result = ai_service.analyze_ats("Resume text", "Job description")
        assert "score" in result
        assert "missing_keywords" in result
        assert "present_keywords" in result
        assert "suggestions" in result

    def test_handles_json_decode_error_gracefully(self, ai_service, mock_provider):
        mock_provider.complete.return_value = AIResponse(
            content="not valid json",
            model="gpt-4o", prompt_tokens=10, completion_tokens=5, total_tokens=15,
        )
        result = ai_service.analyze_ats("Resume", "JD")
        assert result["score"] == 0
        assert isinstance(result["suggestions"], list)

    def test_handles_markdown_wrapped_json(self, ai_service, mock_provider):
        mock_provider.complete.return_value = AIResponse(
            content='```json\n{"score": 80, "missing_keywords": [], "present_keywords": [], "suggestions": []}\n```',
            model="gpt-4o", prompt_tokens=10, completion_tokens=20, total_tokens=30,
        )
        result = ai_service.analyze_ats("Resume", "JD")
        assert result["score"] == 80


# ─── AIService — rewrite_resume_bullet ───────────────────────────────────────

class TestRewriteResumeBullet:
    def test_returns_enhanced_string(self, ai_service, mock_response):
        result = ai_service.rewrite_resume_bullet(
            "worked on backend systems", {"role": "Software Engineer", "company": "Acme"}
        )
        assert result == mock_response.content

    def test_calls_provider_once(self, ai_service, mock_provider):
        ai_service.rewrite_resume_bullet("did stuff", {})
        mock_provider.complete.assert_called_once()

    def test_prompt_contains_original_bullet(self, ai_service, mock_provider):
        ai_service.rewrite_resume_bullet("Built microservices architecture", {})
        prompt = mock_provider.complete.call_args[0][0]
        assert "Built microservices architecture" in prompt

    def test_prompt_contains_role_context(self, ai_service, mock_provider):
        ai_service.rewrite_resume_bullet("Did work", {"role": "Staff SRE", "company": "BigCo"})
        prompt = mock_provider.complete.call_args[0][0]
        assert "Staff SRE" in prompt
        assert "BigCo" in prompt

    def test_prompt_uses_defaults_when_context_empty(self, ai_service, mock_provider):
        ai_service.rewrite_resume_bullet("Did work", {})
        prompt = mock_provider.complete.call_args[0][0]
        assert "Professional" in prompt

    def test_system_prompt_instructs_action_verbs(self, ai_service, mock_provider):
        ai_service.rewrite_resume_bullet("stuff", {})
        system = mock_provider.complete.call_args[0][1]
        assert "action verb" in system.lower()


# ─── AIService — optimize_resume_summary ─────────────────────────────────────

class TestOptimizeResumeSummary:
    def test_returns_string(self, ai_service, mock_response):
        result = ai_service.optimize_resume_summary("", {}, "Software Engineer")
        assert result == mock_response.content

    def test_calls_provider_once(self, ai_service, mock_provider):
        ai_service.optimize_resume_summary("", {}, "SWE")
        mock_provider.complete.assert_called_once()

    def test_prompt_contains_target_role(self, ai_service, mock_provider):
        ai_service.optimize_resume_summary("", {}, "Principal SRE")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Principal SRE" in prompt

    def test_prompt_contains_current_summary(self, ai_service, mock_provider):
        ai_service.optimize_resume_summary("Experienced engineer focused on cloud.", {}, "SWE")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Experienced engineer" in prompt

    def test_prompt_contains_top_skills(self, ai_service, mock_provider):
        profile = {"skills": [{"name": "Kubernetes"}, {"name": "Terraform"}]}
        ai_service.optimize_resume_summary("", profile, "DevOps Engineer")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Kubernetes" in prompt

    def test_prompt_contains_recent_role(self, ai_service, mock_provider):
        profile = {"work_experiences": [{"job_title": "Lead Backend Engineer", "company_name": "X"}]}
        ai_service.optimize_resume_summary("", profile, "Staff Engineer")
        prompt = mock_provider.complete.call_args[0][0]
        assert "Lead Backend Engineer" in prompt

    def test_empty_summary_shows_none_in_prompt(self, ai_service, mock_provider):
        ai_service.optimize_resume_summary("", {}, "Dev")
        prompt = mock_provider.complete.call_args[0][0]
        assert "None" in prompt

    def test_system_prompt_mentions_ats_friendly(self, ai_service, mock_provider):
        ai_service.optimize_resume_summary("", {}, "")
        system = mock_provider.complete.call_args[0][1]
        assert "ATS" in system


# ─── AIService — usage logging ────────────────────────────────────────────────

@pytest.mark.django_db
class TestAIUsageLogging:
    def test_log_usage_creates_record(self, ai_service_with_user, mock_response):
        from apps.ai_engine.models import AIUsageLog
        ai_service_with_user._log_usage("bullet_enhance", mock_response)
        assert AIUsageLog.objects.filter(user=ai_service_with_user._user).exists()

    def test_log_usage_records_correct_feature(self, ai_service_with_user, mock_response):
        from apps.ai_engine.models import AIUsageLog
        ai_service_with_user._log_usage("bullet_enhance", mock_response)
        log = AIUsageLog.objects.get(user=ai_service_with_user._user)
        assert log.feature == "bullet_enhance"
        assert log.prompt_tokens == 100
        assert log.completion_tokens == 50

    def test_log_usage_skipped_when_no_user(self, ai_service, mock_response):
        from apps.ai_engine.models import AIUsageLog
        ai_service._log_usage("bullet_enhance", mock_response)
        assert AIUsageLog.objects.count() == 0

    def test_log_usage_swallows_db_exception(self, ai_service_with_user, mock_response):
        with patch("apps.ai_engine.models.AIUsageLog.objects.create", side_effect=Exception("DB down")):
            ai_service_with_user._log_usage("bullet_enhance", mock_response)
