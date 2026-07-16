from django.contrib import admin
from .models import (
    UserProfile,
    WorkExperience,
    Education,
    Skill,
    Project,
    Certification,
    Achievement,
    Publication,
)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'headline', 'onboarding_complete', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'headline')
    list_filter = ('onboarding_complete',)

@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ('profile', 'job_title', 'company_name', 'start_date', 'is_current')
    search_fields = ('company_name', 'job_title', 'profile__user__email')

@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'degree', 'institution', 'start_date')
    search_fields = ('institution', 'degree', 'profile__user__email')

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('profile', 'name', 'category', 'proficiency_level')
    search_fields = ('name', 'profile__user__email')
    list_filter = ('category', 'proficiency_level')

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'role', 'start_date')
    search_fields = ('title', 'profile__user__email')

@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'name', 'issuing_organization', 'issue_date')
    search_fields = ('name', 'issuing_organization', 'profile__user__email')

@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'issuer', 'date')
    search_fields = ('title', 'issuer', 'profile__user__email')

@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'publisher', 'publication_date')
    search_fields = ('title', 'publisher', 'profile__user__email')
