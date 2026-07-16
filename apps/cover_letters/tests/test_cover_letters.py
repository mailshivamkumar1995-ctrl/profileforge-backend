import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status

BASE_URL = "/api/v1/cover-letters/"


@pytest.mark.django_db
class TestCoverLetterList:
    def test_list_requires_auth(self, api_client):
        response = api_client.get(BASE_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_empty_for_new_user(self, auth_client):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []

    def test_list_returns_user_cover_letters(self, auth_client, cover_letter):
        response = auth_client.get(BASE_URL)
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["title"] == "Google SWE Cover Letter"

    def test_list_does_not_return_other_user_letters(self, auth_client, second_user, db):
        from apps.cover_letters.models import CoverLetter
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        CoverLetter.objects.create(
            user=second_user, profile=profile,
            title="Private Letter", company_name="ACME", job_title="Dev", status="active",
        )
        response = auth_client.get(BASE_URL)
        data = response.json()["data"]
        assert all(item["title"] != "Private Letter" for item in data)

    def test_list_contains_expected_fields(self, auth_client, cover_letter):
        response = auth_client.get(BASE_URL)
        item = response.json()["data"][0]
        assert "id" in item
        assert "title" in item
        assert "company_name" in item
        assert "job_title" in item
        assert "tone" in item
        assert "status" in item


@pytest.mark.django_db
class TestCoverLetterCreate:
    def test_create_minimal(self, auth_client):
        payload = {
            "title": "My Cover Letter",
            "company_name": "Startup Inc",
            "job_title": "Python Developer",
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["title"] == "My Cover Letter"
        assert data["company_name"] == "Startup Inc"
        assert data["status"] == "draft"
        assert data["current_version"] == 2

    def test_create_with_tone(self, auth_client):
        payload = {
            "title": "Executive Letter",
            "company_name": "Corp",
            "job_title": "VP Engineering",
            "tone": "executive",
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["tone"] == "executive"

    def test_create_with_template(self, auth_client, cover_letter_template):
        payload = {
            "title": "Templated Letter",
            "company_name": "Corp",
            "job_title": "Engineer",
            "template_slug": cover_letter_template.slug,
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["template"]["slug"] == cover_letter_template.slug

    def test_create_invalid_template_slug(self, auth_client):
        payload = {
            "title": "Bad Template",
            "company_name": "Corp",
            "job_title": "Dev",
            "template_slug": "nonexistent-slug",
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_with_resume_link(self, auth_client, resume):
        payload = {
            "title": "Linked Letter",
            "company_name": "Corp",
            "job_title": "Dev",
            "resume_id": str(resume.id),
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_creates_version(self, auth_client):
        from apps.cover_letters.models import CoverLetter, CoverLetterVersion
        auth_client.post(
            BASE_URL,
            {"title": "Versioned", "company_name": "Corp", "job_title": "Dev"},
            format="json",
        )
        cl = CoverLetter.objects.get(title="Versioned")
        assert CoverLetterVersion.objects.filter(cover_letter=cl).count() == 1

    def test_create_missing_required_fields(self, auth_client):
        response = auth_client.post(BASE_URL, {"title": "Only Title"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_all_tones_accepted(self, auth_client):
        tones = ["professional", "executive", "friendly", "technical", "startup", "formal"]
        for tone in tones:
            response = auth_client.post(
                BASE_URL,
                {"title": f"Letter {tone}", "company_name": "Corp", "job_title": "Dev", "tone": tone},
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED, f"Failed for tone: {tone}"


@pytest.mark.django_db
class TestCoverLetterRetrieve:
    def test_retrieve_own_letter(self, auth_client, cover_letter):
        response = auth_client.get(f"{BASE_URL}{cover_letter.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["id"] == str(cover_letter.id)

    def test_retrieve_contains_body_content(self, auth_client, cover_letter):
        response = auth_client.get(f"{BASE_URL}{cover_letter.id}/")
        data = response.json()["data"]
        assert "body_content" in data

    def test_retrieve_other_user_letter_returns_404(self, auth_client, second_user, db):
        from apps.cover_letters.models import CoverLetter
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_letter = CoverLetter.objects.create(
            user=second_user, profile=profile,
            title="Private", company_name="Corp", job_title="Dev", status="active",
        )
        response = auth_client.get(f"{BASE_URL}{other_letter.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_nonexistent_returns_404(self, auth_client):
        import uuid
        response = auth_client.get(f"{BASE_URL}{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCoverLetterUpdate:
    def test_partial_update_title(self, auth_client, cover_letter):
        response = auth_client.patch(
            f"{BASE_URL}{cover_letter.id}/", {"title": "Updated Title"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["title"] == "Updated Title"

    def test_partial_update_body_content(self, auth_client, cover_letter):
        new_body = "Updated body content here."
        response = auth_client.patch(
            f"{BASE_URL}{cover_letter.id}/", {"body_content": new_body}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["body_content"] == new_body

    def test_partial_update_tone(self, auth_client, cover_letter):
        response = auth_client.patch(
            f"{BASE_URL}{cover_letter.id}/", {"tone": "startup"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["tone"] == "startup"

    def test_partial_update_creates_new_version(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetterVersion
        initial = CoverLetterVersion.objects.filter(cover_letter=cover_letter).count()
        auth_client.patch(
            f"{BASE_URL}{cover_letter.id}/", {"title": "Version 2"}, format="json"
        )
        assert CoverLetterVersion.objects.filter(cover_letter=cover_letter).count() == initial + 1

    def test_update_other_user_letter_returns_404(self, auth_client, second_user, db):
        from apps.cover_letters.models import CoverLetter
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = CoverLetter.objects.create(
            user=second_user, profile=profile,
            title="Private", company_name="Corp", job_title="Dev",
        )
        response = auth_client.patch(
            f"{BASE_URL}{other.id}/", {"title": "Hacked"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCoverLetterDelete:
    def test_delete_own_letter(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetter
        response = auth_client.delete(f"{BASE_URL}{cover_letter.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert not CoverLetter.objects.filter(id=cover_letter.id).exists()

    def test_delete_other_user_letter_returns_404(self, auth_client, second_user, db):
        from apps.cover_letters.models import CoverLetter
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other = CoverLetter.objects.create(
            user=second_user, profile=profile,
            title="Private", company_name="Corp", job_title="Dev",
        )
        response = auth_client.delete(f"{BASE_URL}{other.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert CoverLetter.objects.filter(id=other.id).exists()


@pytest.mark.django_db
class TestCoverLetterDuplicate:
    def test_duplicate_creates_copy(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetter
        response = auth_client.post(f"{BASE_URL}{cover_letter.id}/duplicate/")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert "(Copy)" in data["title"]
        assert data["id"] != str(cover_letter.id)
        assert CoverLetter.objects.filter(user=cover_letter.user).count() == 2

    def test_duplicate_copy_is_draft(self, auth_client, cover_letter):
        response = auth_client.post(f"{BASE_URL}{cover_letter.id}/duplicate/")
        assert response.json()["data"]["status"] == "draft"

    def test_duplicate_preserves_content(self, auth_client, cover_letter):
        response = auth_client.post(f"{BASE_URL}{cover_letter.id}/duplicate/")
        data = response.json()["data"]
        assert data["company_name"] == cover_letter.company_name
        assert data["job_title"] == cover_letter.job_title


@pytest.mark.django_db
class TestCoverLetterArchive:
    def test_archive_letter(self, auth_client, cover_letter):
        response = auth_client.post(f"{BASE_URL}{cover_letter.id}/archive/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["status"] == "archived"

    def test_archive_persisted_to_db(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetter
        auth_client.post(f"{BASE_URL}{cover_letter.id}/archive/")
        cover_letter.refresh_from_db()
        assert cover_letter.status == "archived"


@pytest.mark.django_db
class TestCoverLetterPreview:
    def test_preview_returns_html(self, auth_client, cover_letter, full_profile):
        response = auth_client.get(f"{BASE_URL}{cover_letter.id}/preview/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "html" in data
        assert len(data["html"]) > 0

    def test_preview_without_template_returns_fallback(self, auth_client, user, profile, db):
        from apps.cover_letters.models import CoverLetter
        letter = CoverLetter.objects.create(
            user=user, profile=profile,
            title="No Template", company_name="Corp", job_title="Dev",
        )
        response = auth_client.get(f"{BASE_URL}{letter.id}/preview/")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestCoverLetterVersions:
    def test_versions_list(self, auth_client, cover_letter):
        response = auth_client.get(f"{BASE_URL}{cover_letter.id}/versions/")
        assert response.status_code == status.HTTP_200_OK
        versions = response.json()["data"]
        assert isinstance(versions, list)

    def test_versions_count_increases_on_update(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetterVersion
        initial = CoverLetterVersion.objects.filter(cover_letter=cover_letter).count()
        auth_client.patch(
            f"{BASE_URL}{cover_letter.id}/", {"title": "Version 2"}, format="json"
        )
        assert CoverLetterVersion.objects.filter(cover_letter=cover_letter).count() == initial + 1

    def test_version_snapshot_contains_body(self, auth_client, cover_letter):
        versions = auth_client.get(f"{BASE_URL}{cover_letter.id}/versions/").json()["data"]
        # Most recent version was created with cover_letter fixture body
        if versions:
            assert "content_snapshot" in versions[0]


@pytest.mark.django_db
class TestCoverLetterAI:
    def test_generate_calls_ai_service(self, auth_client, cover_letter, full_profile):
        with patch("apps.ai_engine.services.AIService.generate_cover_letter") as mock_gen:
            mock_gen.return_value = (
                "I am excited to apply for this role because my experience aligns with "
                "the team's reliability, delivery, and automation goals.\n\n"
                "Across cloud platforms, CI/CD, and infrastructure operations, I have "
                "helped teams ship dependable systems while improving collaboration."
            )
            response = auth_client.post(
                f"{BASE_URL}{cover_letter.id}/generate/",
                {"tone": "professional", "job_description": "Build scalable APIs"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["ai_generated"] is True
        assert data["body_content"].startswith("I am excited to apply")

    def test_rewrite_calls_ai_service(self, auth_client, cover_letter):
        with patch("apps.ai_engine.services.AIService.rewrite_cover_letter") as mock_rw:
            mock_rw.return_value = (
                "I am enthusiastic about this opportunity because it matches my "
                "experience building reliable engineering systems.\n\n"
                "My background in software delivery, operational improvement, and "
                "cross-functional collaboration would help the team meet its goals."
            )
            response = auth_client.post(
                f"{BASE_URL}{cover_letter.id}/rewrite/",
                {"instruction": "Make it more concise"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["body_content"].startswith("I am enthusiastic")

    def test_improve_tone_calls_ai_service(self, auth_client, cover_letter):
        with patch("apps.ai_engine.services.AIService.improve_cover_letter_tone") as mock_tone:
            mock_tone.return_value = (
                "I am pursuing this opportunity because it aligns with my record of "
                "leading practical engineering improvements.\n\n"
                "My experience coordinating delivery, strengthening systems, and "
                "supporting measurable outcomes would help the organization execute "
                "with clarity and confidence."
            )
            response = auth_client.post(
                f"{BASE_URL}{cover_letter.id}/improve-tone/",
                {"tone": "executive"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["tone"] == "executive"

    def test_improve_ats_calls_ai_service(self, auth_client, cover_letter):
        with patch("apps.ai_engine.services.AIService.improve_cover_letter_ats") as mock_ats:
            mock_ats.return_value = (
                "I am excited to apply for this role because my experience includes "
                "cloud infrastructure, CI/CD, monitoring, and automation.\n\n"
                "These strengths align with the job requirements and would help the "
                "team deliver reliable systems with measurable operational impact."
            )
            response = auth_client.post(f"{BASE_URL}{cover_letter.id}/improve-ats/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["ai_generated"] is True

    def test_improve_ats_falls_back_when_ai_body_is_incomplete(self, auth_client, cover_letter):
        from apps.cover_letters.models import CoverLetterVersion

        cover_letter.body_content = (
            "I am excited to apply for this role because my DevOps experience "
            "aligns with the platform reliability needs. I have delivered Kubernetes, "
            "Docker, CI/CD, monitoring, and cloud infrastructure improvements."
        )
        cover_letter.job_description = "Requires Kubernetes, Docker, CI/CD, monitoring, and cloud operations."
        cover_letter.current_version = 3
        cover_letter.save()
        initial_versions = CoverLetterVersion.objects.filter(cover_letter=cover_letter).count()

        with patch("apps.ai_engine.services.AIService.improve_cover_letter_ats") as mock_ats:
            mock_ats.return_value = (
                "...your imperative for seamless development, robust infrastructure, "
                "and efficient operations. My extensive hands-on experience directly aligns "
                "with your requirements, particularly in"
            )
            response = auth_client.post(f"{BASE_URL}{cover_letter.id}/improve-ats/")

        assert response.status_code == status.HTTP_200_OK
        cover_letter.refresh_from_db()
        assert not cover_letter.body_content.startswith("...")
        assert cover_letter.body_content.endswith(".")
        assert "measurable engineering quality" in cover_letter.body_content
        assert cover_letter.current_version == 4
        assert CoverLetterVersion.objects.filter(cover_letter=cover_letter).count() == initial_versions + 1

    def test_improve_ats_strips_markdown_markers(self, auth_client, cover_letter):
        with patch("apps.ai_engine.services.AIService.improve_cover_letter_ats") as mock_ats:
            mock_ats.return_value = (
                "My experience with **Kubernetes**, **Docker**, and CI/CD directly "
                "supports the reliability goals for this role.\n\n"
                "I have delivered cloud infrastructure improvements that align with "
                "monitoring, automation, and operational excellence requirements."
            )
            response = auth_client.post(f"{BASE_URL}{cover_letter.id}/improve-ats/")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()["data"]["body_content"]
        assert "**" not in body
        assert "Kubernetes" in body

    def test_generate_with_invalid_tone_returns_400(self, auth_client, cover_letter):
        response = auth_client.post(
            f"{BASE_URL}{cover_letter.id}/generate/",
            {"tone": "not-a-valid-tone"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_improve_tone_with_invalid_tone_returns_400(self, auth_client, cover_letter):
        response = auth_client.post(
            f"{BASE_URL}{cover_letter.id}/improve-tone/",
            {"tone": "aggressive"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCoverLetterService:
    def test_create_sets_profile_from_user(self, user, db):
        from apps.cover_letters.services import CoverLetterService
        cl = CoverLetterService.create(user, {
            "title": "Service Test", "company_name": "Corp", "job_title": "Dev",
        })
        assert cl.profile is not None
        assert cl.profile.user == user

    def test_duplicate_preserves_all_fields(self, user, cover_letter, db):
        from apps.cover_letters.services import CoverLetterService
        copy = CoverLetterService.duplicate(cover_letter, user)
        assert copy.company_name == cover_letter.company_name
        assert copy.job_title == cover_letter.job_title
        assert copy.tone == cover_letter.tone
        assert copy.body_content == cover_letter.body_content
        assert copy.id != cover_letter.id

    def test_archive_changes_status(self, cover_letter):
        from apps.cover_letters.services import CoverLetterService
        result = CoverLetterService.archive(cover_letter)
        assert result.status == "archived"

    def test_list_for_user_ordered_by_updated_at(self, user, profile, db):
        from apps.cover_letters.models import CoverLetter
        from apps.cover_letters.services import CoverLetterService
        CoverLetter.objects.create(user=user, profile=profile, title="A", company_name="C", job_title="D")
        CoverLetter.objects.create(user=user, profile=profile, title="B", company_name="C", job_title="D")
        letters = list(CoverLetterService.list_for_user(user))
        assert letters[0].title == "B"

    def test_rebuild_preview_returns_string(self, cover_letter, full_profile):
        from apps.cover_letters.services import CoverLetterService
        html = CoverLetterService.rebuild_preview(cover_letter)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_ai_body_validation_rejects_truncated_fragments(self):
        from core.exceptions import AIProviderException
        from apps.cover_letters.services import CoverLetterService

        with pytest.raises(AIProviderException):
            CoverLetterService._validate_ai_body(
                "...your imperative for seamless development, robust infrastructure, "
                "and efficient operations. My extensive experience directly aligns "
                "with your requirements, particularly in"
            )

    def test_ai_body_validation_rejects_missing_terminal_punctuation(self):
        from core.exceptions import AIProviderException
        from apps.cover_letters.services import CoverLetterService

        with pytest.raises(AIProviderException):
            CoverLetterService._validate_ai_body(
                "My decision to engage with ProfileForge Validation Labs regarding "
                "the DevOps Engineer function is predicated on a clear strategic "
                "alignment with your imperative for seamless development, robust infrastructure,"
            )

    def test_ai_body_validation_accepts_complete_paragraphs(self):
        from apps.cover_letters.services import CoverLetterService

        body = CoverLetterService._validate_ai_body(
            "I am excited to apply for the DevOps Engineer role because my experience "
            "aligns with your reliability and automation goals.\n\n"
            "Across Kubernetes, Docker, CI/CD, monitoring, and cloud operations, I have "
            "helped teams improve delivery speed while keeping infrastructure stable."
        )

        assert body.startswith("I am excited")

    def test_ai_body_validation_strips_markdown_formatting(self):
        from apps.cover_letters.services import CoverLetterService

        body = CoverLetterService._validate_ai_body(
            "My experience with **Kubernetes**, _Docker_, and `CI/CD` directly "
            "supports this DevOps Engineer role.\n\n"
            "- I have improved cloud infrastructure, monitoring, automation, and "
            "reliability outcomes for engineering teams."
        )

        assert "**" not in body
        assert "_Docker_" not in body
        assert "`CI/CD`" not in body
        assert body.startswith("My experience")

    def test_ats_fallback_adds_missing_keywords_and_complete_sentence(self):
        from apps.cover_letters.services import CoverLetterService

        body = CoverLetterService._build_ats_fallback_body(
            body_content=(
                "I am excited to apply for the DevOps Engineer role. My experience "
                "across Kubernetes and Docker supports reliable delivery."
            ),
            job_description=(
                "Requires CI/CD, monitoring, cloud infrastructure, automation, "
                "and efficient operations."
            ),
            job_title="DevOps Engineer",
        )

        assert "CI/CD" in body
        assert "monitoring" in body
        assert "cloud infrastructure" in body
        assert body.endswith(".")
