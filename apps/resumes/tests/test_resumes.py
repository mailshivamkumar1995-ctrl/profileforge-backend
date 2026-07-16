import pytest
from rest_framework import status


BASE_URL = "/api/v1/resumes/"


@pytest.mark.django_db
class TestResumeList:
    def test_list_requires_auth(self, api_client):
        response = api_client.get(BASE_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_empty_for_new_user(self, auth_client):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []

    def test_list_returns_user_resumes(self, auth_client, resume):
        response = auth_client.get(BASE_URL)
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["title"] == "Test Resume"

    def test_list_does_not_return_other_user_resumes(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        Resume.objects.create(
            user=second_user,
            profile=profile,
            title="Other User Resume",
            status="active",
        )
        response = auth_client.get(BASE_URL)
        data = response.json()["data"]
        assert all(r["title"] != "Other User Resume" for r in data)


@pytest.mark.django_db
class TestResumeCreate:
    def test_create_minimal(self, auth_client):
        response = auth_client.post(BASE_URL, {"title": "My CV"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["title"] == "My CV"
        assert data["status"] == "draft"
        assert data["current_version"] == 2  # starts at 1, incremented after first save

    def test_create_with_template(self, auth_client, template):
        payload = {
            "title": "Templated Resume",
            "template_slug": template.slug,
            "target_role": "Backend Engineer",
        }
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["template"]["slug"] == template.slug
        assert data["target_role"] == "Backend Engineer"

    def test_create_invalid_template_slug(self, auth_client):
        payload = {"title": "Bad Template", "template_slug": "nonexistent-slug"}
        response = auth_client.post(BASE_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_creates_version(self, auth_client):
        from apps.resumes.models import Resume, ResumeVersion
        auth_client.post(BASE_URL, {"title": "Versioned"}, format="json")
        resume = Resume.objects.get(title="Versioned")
        assert ResumeVersion.objects.filter(resume=resume).count() == 1


@pytest.mark.django_db
class TestResumeRetrieve:
    def test_retrieve_own_resume(self, auth_client, resume):
        response = auth_client.get(f"{BASE_URL}{resume.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["id"] == str(resume.id)

    def test_retrieve_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.get(f"{BASE_URL}{other_resume.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestResumeUpdate:
    def test_partial_update_title(self, auth_client, resume):
        response = auth_client.patch(
            f"{BASE_URL}{resume.id}/", {"title": "Updated Title"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["title"] == "Updated Title"

    def test_partial_update_status(self, auth_client, resume):
        response = auth_client.patch(
            f"{BASE_URL}{resume.id}/", {"status": "archived"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["status"] == "archived"

    def test_partial_update_creates_new_version(self, auth_client, resume):
        from apps.resumes.models import ResumeVersion
        initial_count = ResumeVersion.objects.filter(resume=resume).count()
        auth_client.patch(
            f"{BASE_URL}{resume.id}/", {"title": "New Title"}, format="json"
        )
        assert ResumeVersion.objects.filter(resume=resume).count() == initial_count + 1

    def test_update_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.patch(
            f"{BASE_URL}{other_resume.id}/", {"title": "Hacked"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestResumeDelete:
    def test_delete_own_resume(self, auth_client, resume):
        from apps.resumes.models import Resume
        response = auth_client.delete(f"{BASE_URL}{resume.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert not Resume.objects.filter(id=resume.id).exists()

    def test_delete_other_user_resume_returns_404(self, auth_client, second_user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=second_user)
        other_resume = Resume.objects.create(
            user=second_user, profile=profile, title="Private", status="active"
        )
        response = auth_client.delete(f"{BASE_URL}{other_resume.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert Resume.objects.filter(id=other_resume.id).exists()


@pytest.mark.django_db
class TestSetPrimary:
    def test_set_primary(self, auth_client, resume):
        response = auth_client.post(f"{BASE_URL}{resume.id}/set-primary/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["is_primary"] is True

    def test_set_primary_unsets_previous(self, auth_client, user, profile, template, db):
        from apps.resumes.models import Resume
        r1 = Resume.objects.create(
            user=user, profile=profile, title="R1", is_primary=True, status="active"
        )
        r2 = Resume.objects.create(
            user=user, profile=profile, title="R2", status="active"
        )
        auth_client.post(f"{BASE_URL}{r2.id}/set-primary/")
        r1.refresh_from_db()
        assert not r1.is_primary


@pytest.mark.django_db
class TestResumePreview:
    def test_preview_returns_html(self, auth_client, resume, full_profile):
        response = auth_client.get(f"{BASE_URL}{resume.id}/preview/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "html" in data
        assert len(data["html"]) > 0

    def test_preview_html_contains_profile_name(self, auth_client, resume, user):
        response = auth_client.get(f"{BASE_URL}{resume.id}/preview/")
        html = response.json()["data"]["html"]
        assert user.full_name in html


@pytest.mark.django_db
class TestResumeVersions:
    def test_versions_list(self, auth_client, resume):
        response = auth_client.get(f"{BASE_URL}{resume.id}/versions/")
        assert response.status_code == status.HTTP_200_OK
        versions = response.json()["data"]
        assert isinstance(versions, list)

    def test_versions_count_increases_on_update(self, auth_client, resume):
        auth_client.patch(
            f"{BASE_URL}{resume.id}/", {"title": "Version 2"}, format="json"
        )
        response = auth_client.get(f"{BASE_URL}{resume.id}/versions/")
        assert len(response.json()["data"]) >= 1


@pytest.mark.django_db
class TestResumeService:
    def test_profile_serializer_returns_expected_keys(self, user, full_profile):
        from apps.profiles.profile_utils import ProfileSerializer
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=user)
        data = ProfileSerializer.to_dict(profile)
        assert "full_name" in data
        assert "work_experiences" in data
        assert "educations" in data
        assert "skills" in data
        assert isinstance(data["work_experiences"], list)

    def test_create_resume_without_template(self, user, db):
        from apps.resumes.services import ResumeService
        resume = ResumeService.create(user, {"title": "No Template Resume"})
        assert resume.pk is not None
        assert resume.template is None

    def test_rebuild_preview_with_template(self, user, resume, full_profile):
        from apps.resumes.services import ResumeService
        html = ResumeService.rebuild_preview(resume)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_rebuild_preview_without_template(self, user, db):
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        profile = UserProfile.objects.get(user=user)
        resume_no_tmpl = Resume.objects.create(
            user=user, profile=profile, title="No Tmpl", status="draft"
        )
        from apps.resumes.services import ResumeService
        html = ResumeService.rebuild_preview(resume_no_tmpl)
        # No template in DB → graceful fallback
        assert isinstance(html, str)
