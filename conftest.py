"""
Root conftest.py — shared pytest fixtures for all apps.

Fixtures defined here are available to every test in the project
without any import.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient


# ─── API Client ───────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    """An API client pre-authenticated as a standard user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """An API client pre-authenticated as an admin user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


# ─── User Factories ────────────────────────────────────────────────────────────

@pytest.fixture
def user_data():
    return {
        "email": "test@example.com",
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "password": "SecurePass123!",
    }


@pytest.fixture
def user(db, user_data):
    """A standard registered user with profile + portfolio."""
    from django.contrib.auth import get_user_model
    from apps.profiles.models import UserProfile
    from apps.portfolios.models import Portfolio
    from core.models import UserSettings

    User = get_user_model()
    u = User.objects.create_user(**user_data)
    UserProfile.objects.get_or_create(user=u)
    Portfolio.objects.get_or_create(user=u, profile=u.profile, defaults={"slug": u.username})
    UserSettings.objects.get_or_create(user=u)
    return u


@pytest.fixture
def second_user(db):
    """A second user for ownership/isolation tests."""
    from django.contrib.auth import get_user_model
    from apps.profiles.models import UserProfile
    from apps.portfolios.models import Portfolio

    User = get_user_model()
    u = User.objects.create_user(
        email="other@example.com",
        username="otheruser",
        first_name="Other",
        last_name="User",
        password="SecurePass123!",
    )
    profile = UserProfile.objects.create(user=u)
    Portfolio.objects.create(user=u, profile=profile, slug="otheruser")
    return u


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_superuser(
        email="admin@example.com",
        username="admin",
        first_name="Admin",
        last_name="User",
        password="AdminPass123!",
    )


# ─── Profile Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def profile(user):
    return user.profile


@pytest.fixture
def profile_with_experience(profile, db):
    from apps.profiles.models import WorkExperience
    WorkExperience.objects.create(
        profile=profile,
        company_name="Acme Corp",
        job_title="Software Engineer",
        employment_type="full_time",
        start_date="2022-01-01",
        is_current=True,
        achievements=["Reduced latency by 40%"],
        technologies=["Python", "Django"],
        display_order=0,
    )
    return profile


@pytest.fixture
def profile_with_education(profile, db):
    from apps.profiles.models import Education
    Education.objects.create(
        profile=profile,
        institution="State University",
        degree="Bachelor of Science",
        field_of_study="Computer Science",
        start_date="2018-09-01",
        end_date="2022-05-15",
        gpa=3.8,
        display_order=0,
    )
    return profile


@pytest.fixture
def profile_with_skills(profile, db):
    from apps.profiles.models import Skill
    skills_data = [
        {"name": "Python", "category": "programming", "proficiency_level": "expert"},
        {"name": "Django", "category": "framework", "proficiency_level": "expert"},
        {"name": "PostgreSQL", "category": "database", "proficiency_level": "advanced"},
    ]
    for i, skill in enumerate(skills_data):
        Skill.objects.create(profile=profile, display_order=i, **skill)
    return profile


@pytest.fixture
def full_profile(profile_with_experience, profile_with_education, profile_with_skills):
    """A profile with all sections populated."""
    return profile_with_experience


# ─── Resume Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def template(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="modern-ats",
        defaults={
            "name": "Modern ATS",
            "type": "resume",
            "category": "ats",
            "is_ats_optimized": True,
            "is_single_page": True,
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def resume(user, profile, template, db):
    from apps.resumes.models import Resume
    return Resume.objects.create(
        user=user,
        profile=profile,
        title="Test Resume",
        template=template,
        template_settings={
            "primary_color": "#2563eb",
            "font_family": "Inter",
            "spacing": "comfortable",
            "section_order": ["summary", "experience", "education", "skills"],
            "hidden_sections": [],
        },
        status="active",
    )


# ─── Cover Letter Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def cover_letter_template(db):
    from apps.templates_engine.models import Template
    t, _ = Template.objects.get_or_create(
        slug="software-engineer",
        defaults={
            "name": "Software Engineer",
            "type": "cover_letter",
            "category": "professional",
            "is_active": True,
        },
    )
    return t


@pytest.fixture
def cover_letter(user, profile, cover_letter_template, db):
    from apps.cover_letters.models import CoverLetter
    return CoverLetter.objects.create(
        user=user,
        profile=profile,
        title="Google SWE Cover Letter",
        template=cover_letter_template,
        company_name="Google",
        job_title="Senior Software Engineer",
        tone="professional",
        body_content="I am excited to apply for this position...",
        status="draft",
    )


# ─── Import Job Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def import_job(user, db):
    from apps.imports.models import ImportJob
    return ImportJob.objects.create(
        user=user,
        original_filename="resume.pdf",
        file_type="pdf",
        file_path="uploads/test-user/imports/resume.pdf",
        status="pending",
    )


# ─── Celery ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,
        "task_eager_propagates": True,
    }


# ─── Freeze time ─────────────────────────────────────────────────────────────

@pytest.fixture
def freeze_time_now(freezer):
    """Use freezegun to control time in tests."""
    return freezer
