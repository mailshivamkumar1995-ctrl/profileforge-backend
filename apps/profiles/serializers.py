from rest_framework import serializers
from apps.profiles.models import (
    UserProfile, WorkExperience, Education, Skill,
    Project, Certification, Achievement, Publication,
)


class WorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkExperience
        fields = [
            "id", "company_name", "job_title", "employment_type",
            "location", "start_date", "end_date", "is_current",
            "description", "achievements", "technologies", "display_order",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        if attrs.get("is_current") and attrs.get("end_date"):
            raise serializers.ValidationError(
                {"end_date": "A current position cannot have an end date."}
            )
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "End date must be after start date."}
            )
        return attrs


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = [
            "id", "institution", "degree", "field_of_study",
            "start_date", "end_date", "gpa", "description",
            "achievements", "display_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            "id", "name", "category", "category_label", "proficiency_level",
            "years_of_experience", "display_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id", "title", "description", "role", "technologies",
            "live_url", "repo_url", "start_date", "end_date",
            "highlights", "display_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CertificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certification
        fields = [
            "id", "name", "issuing_organization", "issue_date",
            "expiry_date", "credential_id", "credential_url",
            "display_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = [
            "id", "title", "description", "date",
            "issuer", "display_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PublicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publication
        fields = [
            "id", "title", "publisher", "publication_date",
            "url", "description", "display_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class UserProfileSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    work_experiences = WorkExperienceSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    certifications = CertificationSerializer(many=True, read_only=True)
    achievements = AchievementSerializer(many=True, read_only=True)
    publications = PublicationSerializer(many=True, read_only=True)

    def get_user(self, obj):
        u = obj.user
        return {
            "id": str(u.id),
            "email": u.email,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }

    class Meta:
        model = UserProfile
        fields = [
            "id", "user_id", "user", "headline", "professional_summary",
            "phone", "location", "website_url", "linkedin_url",
            "github_url", "twitter_url", "eportfolio_url", "portfolio_preferences",
            "ats_keywords", "onboarding_complete", "work_experiences",
            "educations", "skills", "projects", "certifications",
            "achievements", "publications", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user_id", "created_at", "updated_at"]


class ReorderSerializer(serializers.Serializer):
    section = serializers.ChoiceField(choices=[
        "experience", "education", "skills", "projects",
        "certifications", "achievements", "publications",
    ])
    items = serializers.ListField(child=serializers.UUIDField(), min_length=1)
