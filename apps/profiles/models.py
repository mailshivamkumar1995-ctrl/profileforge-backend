import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full Time"
    PART_TIME = "part_time", "Part Time"
    CONTRACT = "contract", "Contract"
    FREELANCE = "freelance", "Freelance"
    INTERNSHIP = "internship", "Internship"
    VOLUNTEER = "volunteer", "Volunteer"


class SkillCategory(models.TextChoices):
    PROGRAMMING = "programming", "Programming"
    FRAMEWORK = "framework", "Framework"
    DATABASE = "database", "Database"
    CLOUD = "cloud", "Cloud"
    DEVOPS = "devops", "DevOps"
    TOOL = "tool", "Tool"
    LANGUAGE = "language", "Language"
    SOFT_SKILL = "soft_skill", "Soft Skill"
    OTHER = "other", "Other"


class ProficiencyLevel(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"
    EXPERT = "expert", "Expert"


class UserProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    headline = models.CharField(max_length=200, blank=True)
    professional_summary = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    location = models.JSONField(default=dict, blank=True)
    website_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    eportfolio_url = models.URLField(blank=True)  # e.g. mygreatlearning.com/eportfolio/...
    portfolio_preferences = models.JSONField(default=dict, blank=True)
    ats_keywords = models.JSONField(default=list, blank=True)
    onboarding_complete = models.BooleanField(default=False)
    active_draft_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"

    def __str__(self):
        return f"Profile of {self.user.full_name}"


class WorkExperience(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="work_experiences"
    )
    company_name = models.CharField(max_length=200)
    job_title = models.CharField(max_length=200)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    location = models.JSONField(default=dict, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    achievements = models.JSONField(default=list, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "work_experiences"
        ordering = ["display_order", "-start_date"]
        indexes = [
            models.Index(fields=["profile", "display_order"]),
        ]

    def __str__(self):
        return f"{self.job_title} at {self.company_name}"


class Education(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="educations"
    )
    institution = models.CharField(max_length=200)
    degree = models.CharField(max_length=200)
    field_of_study = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    description = models.TextField(blank=True)
    achievements = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "educations"
        ordering = ["display_order", "-start_date"]

    def __str__(self):
        return f"{self.degree} at {self.institution}"


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="skills"
    )
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20, choices=SkillCategory.choices, default=SkillCategory.OTHER
    )
    proficiency_level = models.CharField(
        max_length=20, choices=ProficiencyLevel.choices, default=ProficiencyLevel.INTERMEDIATE
    )
    years_of_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    category_label = models.CharField(max_length=100, blank=True, default="")  # custom label when category=other
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "skills"
        ordering = ["display_order", "category", "name"]
        indexes = [
            models.Index(fields=["profile", "category"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_proficiency_level_display()})"


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    role = models.CharField(max_length=200, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    live_url = models.URLField(blank=True)
    repo_url = models.URLField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    highlights = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects"
        ordering = ["display_order", "-start_date"]

    def __str__(self):
        return self.title


class Certification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=200)
    issuing_organization = models.CharField(max_length=200)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    credential_id = models.CharField(max_length=200, blank=True)
    credential_url = models.URLField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "certifications"
        ordering = ["display_order", "-issue_date"]

    def __str__(self):
        return f"{self.name} — {self.issuing_organization}"


class Achievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="achievements"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    issuer = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "achievements"
        ordering = ["display_order", "-date"]

    def __str__(self):
        return self.title


class Publication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="publications"
    )
    title = models.CharField(max_length=300)
    publisher = models.CharField(max_length=200)
    publication_date = models.DateField(null=True, blank=True)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "publications"
        ordering = ["display_order", "-publication_date"]

    def __str__(self):
        return self.title
