import pytest
from rest_framework import status

BASE_URL = "/api/v1/profiles/"
ME_URL = f"{BASE_URL}me/"
EXP_URL = f"{BASE_URL}me/experience/"
EDU_URL = f"{BASE_URL}me/education/"
SKILLS_URL = f"{BASE_URL}me/skills/"
PROJECTS_URL = f"{BASE_URL}me/projects/"
CERTS_URL = f"{BASE_URL}me/certifications/"
ACH_URL = f"{BASE_URL}me/achievements/"
PUBS_URL = f"{BASE_URL}me/publications/"
REORDER_URL = f"{BASE_URL}me/reorder/"


# ─── Profile Core ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfileGet:
    def test_requires_auth(self, api_client):
        response = api_client.get(ME_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_own_profile(self, auth_client, user):
        response = auth_client.get(ME_URL)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["user"]["email"] == user.email

    def test_response_envelope(self, auth_client):
        response = auth_client.get(ME_URL)
        body = response.json()
        assert body["success"] is True
        assert "data" in body

    def test_profile_contains_expected_fields(self, auth_client):
        response = auth_client.get(ME_URL)
        data = response.json()["data"]
        for field in ["headline", "professional_summary", "phone", "location",
                      "website_url", "linkedin_url", "github_url", "work_experiences",
                      "educations", "skills", "projects", "certifications",
                      "achievements", "publications"]:
            assert field in data

    def test_nested_sections_are_lists(self, auth_client, full_profile):
        response = auth_client.get(ME_URL)
        data = response.json()["data"]
        assert isinstance(data["work_experiences"], list)
        assert isinstance(data["educations"], list)
        assert isinstance(data["skills"], list)


@pytest.mark.django_db
class TestProfileUpdate:
    def test_update_headline(self, auth_client):
        response = auth_client.patch(ME_URL, {"headline": "Senior Engineer"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["headline"] == "Senior Engineer"

    def test_update_professional_summary(self, auth_client):
        summary = "10 years building distributed systems."
        response = auth_client.patch(ME_URL, {"professional_summary": summary}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["professional_summary"] == summary

    def test_update_phone(self, auth_client):
        response = auth_client.patch(ME_URL, {"phone": "+1-555-0100"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["phone"] == "+1-555-0100"

    def test_update_linkedin_url(self, auth_client):
        url = "https://linkedin.com/in/testuser"
        response = auth_client.patch(ME_URL, {"linkedin_url": url}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["linkedin_url"] == url

    def test_update_persists_to_db(self, auth_client, user):
        from apps.profiles.models import UserProfile
        auth_client.patch(ME_URL, {"headline": "Persisted"}, format="json")
        profile = UserProfile.objects.get(user=user)
        assert profile.headline == "Persisted"

    def test_partial_update_does_not_clear_other_fields(self, auth_client, user):
        from apps.profiles.models import UserProfile
        auth_client.patch(ME_URL, {"headline": "First"}, format="json")
        auth_client.patch(ME_URL, {"phone": "555-1234"}, format="json")
        profile = UserProfile.objects.get(user=user)
        assert profile.headline == "First"
        assert profile.phone == "555-1234"


@pytest.mark.django_db
class TestOnboardingComplete:
    def test_onboarding_complete_default_false(self, auth_client):
        response = auth_client.get(ME_URL)
        assert response.status_code == 200
        assert response.json()["data"]["onboarding_complete"] is False

    def test_onboarding_complete_present_in_response(self, auth_client):
        response = auth_client.get(ME_URL)
        assert "onboarding_complete" in response.json()["data"]

    def test_patch_sets_onboarding_complete_true(self, auth_client, user):
        from apps.profiles.models import UserProfile
        response = auth_client.patch(ME_URL, {"onboarding_complete": True}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["onboarding_complete"] is True
        profile = UserProfile.objects.get(user=user)
        assert profile.onboarding_complete is True

    def test_patch_onboarding_complete_does_not_clear_other_fields(self, auth_client, user):
        from apps.profiles.models import UserProfile
        auth_client.patch(ME_URL, {"headline": "Engineer"}, format="json")
        auth_client.patch(ME_URL, {"onboarding_complete": True}, format="json")
        profile = UserProfile.objects.get(user=user)
        assert profile.headline == "Engineer"
        assert profile.onboarding_complete is True

    def test_onboarding_complete_not_read_only(self, auth_client):
        response = auth_client.patch(ME_URL, {"onboarding_complete": True}, format="json")
        assert response.status_code == 200

    def test_onboarding_complete_requires_auth(self, api_client):
        response = api_client.patch(ME_URL, {"onboarding_complete": True}, format="json")
        assert response.status_code == 401


# ─── Work Experience ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestWorkExperience:
    def test_list_empty_initially(self, auth_client):
        response = auth_client.get(EXP_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []

    def test_create_experience(self, auth_client):
        payload = {
            "company_name": "Acme Corp",
            "job_title": "Software Engineer",
            "employment_type": "full_time",
            "start_date": "2022-01-01",
            "is_current": True,
        }
        response = auth_client.post(EXP_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["company_name"] == "Acme Corp"
        assert data["job_title"] == "Software Engineer"

    def test_create_experience_with_achievements(self, auth_client):
        payload = {
            "company_name": "Corp",
            "job_title": "Dev",
            "start_date": "2021-06-01",
            "is_current": False,
            "end_date": "2023-01-01",
            "achievements": ["Reduced latency by 40%", "Led team of 5"],
        }
        response = auth_client.post(EXP_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["achievements"] == ["Reduced latency by 40%", "Led team of 5"]

    def test_update_experience(self, auth_client, profile_with_experience):
        exp = profile_with_experience.work_experiences.first()
        response = auth_client.patch(
            f"{EXP_URL}{exp.id}/",
            {"job_title": "Senior Engineer"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["job_title"] == "Senior Engineer"

    def test_delete_experience(self, auth_client, profile_with_experience):
        from apps.profiles.models import WorkExperience
        exp = profile_with_experience.work_experiences.first()
        response = auth_client.delete(f"{EXP_URL}{exp.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert not WorkExperience.objects.filter(id=exp.id).exists()

    def test_cannot_access_other_user_experience(self, auth_client, second_user, db):
        from apps.profiles.models import WorkExperience, UserProfile
        profile = UserProfile.objects.get(user=second_user)
        exp = WorkExperience.objects.create(
            profile=profile, company_name="Secret Co",
            job_title="Dev", start_date="2022-01-01", is_current=True,
        )
        response = auth_client.get(f"{EXP_URL}{exp.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_only_returns_own_experiences(self, auth_client, profile_with_experience, second_user, db):
        from apps.profiles.models import WorkExperience, UserProfile
        other_profile = UserProfile.objects.get(user=second_user)
        WorkExperience.objects.create(
            profile=other_profile, company_name="Other Corp",
            job_title="Dev", start_date="2022-01-01", is_current=True,
        )
        response = auth_client.get(EXP_URL)
        names = [e["company_name"] for e in response.json()["data"]]
        assert "Other Corp" not in names


# ─── Education ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEducation:
    def test_create_education(self, auth_client):
        payload = {
            "institution": "MIT",
            "degree": "Bachelor of Science",
            "field_of_study": "Computer Science",
            "start_date": "2018-09-01",
            "end_date": "2022-05-15",
        }
        response = auth_client.post(EDU_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["institution"] == "MIT"
        assert data["degree"] == "Bachelor of Science"

    def test_create_education_with_gpa(self, auth_client):
        payload = {
            "institution": "Stanford",
            "degree": "Master of Science",
            "field_of_study": "AI",
            "start_date": "2022-09-01",
            "end_date": "2024-06-01",
            "gpa": 3.9,
        }
        response = auth_client.post(EDU_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["gpa"] == "3.90"

    def test_update_education(self, auth_client, profile_with_education):
        edu = profile_with_education.educations.first()
        response = auth_client.patch(f"{EDU_URL}{edu.id}/", {"gpa": 3.95}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_delete_education(self, auth_client, profile_with_education):
        from apps.profiles.models import Education
        edu = profile_with_education.educations.first()
        auth_client.delete(f"{EDU_URL}{edu.id}/")
        assert not Education.objects.filter(id=edu.id).exists()


# ─── Skills ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSkills:
    def test_create_skill(self, auth_client):
        payload = {"name": "Python", "category": "programming", "proficiency_level": "expert"}
        response = auth_client.post(SKILLS_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["name"] == "Python"

    def test_list_skills(self, auth_client, profile_with_skills):
        response = auth_client.get(SKILLS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["data"]) >= 3

    def test_bulk_upsert_skills(self, auth_client):
        skills = [
            {"name": "Python", "category": "programming", "proficiency_level": "expert"},
            {"name": "Docker", "category": "devops", "proficiency_level": "advanced"},
        ]
        response = auth_client.post(f"{SKILLS_URL}bulk/", {"skills": skills}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["data"]) == 2

    def test_bulk_upsert_is_idempotent(self, auth_client):
        from apps.profiles.models import Skill
        skills = [{"name": "Go", "category": "programming", "proficiency_level": "advanced"}]
        auth_client.post(f"{SKILLS_URL}bulk/", {"skills": skills}, format="json")
        auth_client.post(f"{SKILLS_URL}bulk/", {"skills": skills}, format="json")
        count = Skill.objects.filter(name="Go").count()
        assert count == 1

    def test_delete_skill(self, auth_client, profile_with_skills):
        from apps.profiles.models import Skill
        skill = profile_with_skills.skills.first()
        auth_client.delete(f"{SKILLS_URL}{skill.id}/")
        assert not Skill.objects.filter(id=skill.id).exists()


# ─── Projects ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProjects:
    def test_create_project(self, auth_client):
        payload = {
            "title": "ProfileForge",
            "description": "AI-powered resume builder",
            "technologies": ["Django", "React", "PostgreSQL"],
            "start_date": "2024-01-01",
        }
        response = auth_client.post(PROJECTS_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["title"] == "ProfileForge"
        assert data["technologies"] == ["Django", "React", "PostgreSQL"]

    def test_update_project(self, auth_client, profile, db):
        from apps.profiles.models import Project
        project = Project.objects.create(
            profile=profile, title="Old", description="Old desc", start_date="2023-01-01",
        )
        response = auth_client.patch(
            f"{PROJECTS_URL}{project.id}/", {"title": "Updated"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["title"] == "Updated"

    def test_delete_project(self, auth_client, profile, db):
        from apps.profiles.models import Project
        project = Project.objects.create(
            profile=profile, title="Temp", description="x", start_date="2023-01-01",
        )
        auth_client.delete(f"{PROJECTS_URL}{project.id}/")
        assert not Project.objects.filter(id=project.id).exists()


# ─── Certifications ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCertifications:
    def test_create_certification(self, auth_client):
        payload = {
            "name": "AWS Solutions Architect",
            "issuing_organization": "Amazon",
            "issue_date": "2023-06-01",
        }
        response = auth_client.post(CERTS_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["name"] == "AWS Solutions Architect"

    def test_list_certifications(self, auth_client, profile, db):
        from apps.profiles.models import Certification
        Certification.objects.create(
            profile=profile, name="CKA", issuing_organization="CNCF", issue_date="2022-01-01",
        )
        response = auth_client.get(CERTS_URL)
        assert len(response.json()["data"]) == 1


# ─── Achievements ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAchievements:
    def test_create_achievement(self, auth_client):
        payload = {"title": "1st Place Hackathon", "description": "Won internal hackathon"}
        response = auth_client.post(ACH_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["title"] == "1st Place Hackathon"


# ─── Publications ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPublications:
    def test_create_publication(self, auth_client):
        payload = {
            "title": "Distributed Systems Paper",
            "publisher": "ACM",
            "published_date": "2023-11-01",
            "url": "https://acm.org/paper",
        }
        response = auth_client.post(PUBS_URL, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["title"] == "Distributed Systems Paper"


# ─── Reorder ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReorder:
    def test_reorder_skills(self, auth_client, profile_with_skills):
        skills = list(profile_with_skills.skills.order_by("display_order"))
        new_order = [str(s.id) for s in reversed(skills)]
        response = auth_client.post(
            REORDER_URL,
            {"section": "skills", "items": new_order},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_reorder_invalid_section_returns_400(self, auth_client):
        response = auth_client.post(
            REORDER_URL,
            {"section": "nonexistent", "items": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reorder_updates_display_order_in_db(self, auth_client, profile_with_skills):
        from apps.profiles.models import Skill
        skills = list(profile_with_skills.skills.order_by("display_order"))
        reversed_ids = [str(s.id) for s in reversed(skills)]
        auth_client.post(REORDER_URL, {"section": "skills", "items": reversed_ids}, format="json")
        for i, sid in enumerate(reversed_ids):
            skill = Skill.objects.get(id=sid)
            assert skill.display_order == i


# ─── Profile Service Layer ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfileService:
    def test_get_profile_returns_profile(self, user, profile):
        from apps.profiles.services import ProfileService
        result = ProfileService.get_profile(user)
        assert result.user == user

    def test_update_profile_persists(self, user, profile):
        from apps.profiles.services import ProfileService
        ProfileService.update_profile(user, {"headline": "Data Engineer"})
        profile.refresh_from_db()
        assert profile.headline == "Data Engineer"

    def test_reorder_section_atomic(self, user, profile_with_skills):
        from apps.profiles.services import ProfileService
        from apps.profiles.models import Skill
        skills = list(profile_with_skills.skills.order_by("display_order"))
        new_order = [str(s.id) for s in reversed(skills)]
        ProfileService.reorder_section(user, "skills", new_order)
        for i, sid in enumerate(new_order):
            assert Skill.objects.get(id=sid).display_order == i
