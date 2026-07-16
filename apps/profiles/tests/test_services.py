import pytest
from core.exceptions import NotFoundException

from apps.profiles.models import UserProfile, Skill
from apps.profiles.services import ProfileService


@pytest.mark.django_db
class TestProfileService:
    def test_get_basic_profile_success(self, user):
        profile = ProfileService.get_basic_profile(user)
        assert profile == user.profile
        assert isinstance(profile, UserProfile)

    def test_get_basic_profile_not_found(self, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Create user but explicitly delete profile to simulate missing profile
        u = User.objects.create_user(username="noprofile", email="no@profile.com", password="pwd")
        try:
            u.profile.delete()
        except User.profile.RelatedObjectDoesNotExist:
            pass

        with pytest.raises(NotFoundException):
            ProfileService.get_basic_profile(u)

    def test_bulk_upsert_skills_creates_new(self, user):
        skills_data = [
            {"name": "Python", "category": "programming", "proficiency_level": "expert"},
            {"name": "Django", "category": "framework", "proficiency_level": "advanced"},
        ]
        
        created_skills = ProfileService.bulk_upsert_skills(user, skills_data)
        
        assert len(created_skills) == 2
        assert Skill.objects.filter(profile=user.profile).count() == 2
        
        python_skill = Skill.objects.get(profile=user.profile, name="Python")
        assert python_skill.category == "programming"
        assert python_skill.proficiency_level == "expert"

    def test_bulk_upsert_skills_updates_existing(self, user):
        # Create initial skill
        Skill.objects.create(
            profile=user.profile,
            name="Python",
            category="other",
            proficiency_level="beginner"
        )
        
        skills_data = [
            {"name": "Python", "category": "programming", "proficiency_level": "expert"},
            {"name": "Django", "category": "framework", "proficiency_level": "advanced"},
        ]
        
        created_skills = ProfileService.bulk_upsert_skills(user, skills_data)
        
        assert len(created_skills) == 2
        assert Skill.objects.filter(profile=user.profile).count() == 2
        
        # Verify it updated the existing one instead of creating a duplicate
        python_skill = Skill.objects.get(profile=user.profile, name="Python")
        assert python_skill.category == "programming"
        assert python_skill.proficiency_level == "expert"
