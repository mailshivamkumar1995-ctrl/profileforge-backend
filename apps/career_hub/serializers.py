from decimal import Decimal

from rest_framework import serializers

from apps.career_hub.models import Draft, Job, JobRecommendation, ResumeMatchScore, UserJob, WorkType


class JobListSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "source_name", "title", "company", "city", "work_type",
            "salary_min", "salary_max", "salary_currency",
            "posted_at", "is_active", "is_private",
        ]
        read_only_fields = fields


class JobDetailSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "source_name", "title", "company", "description",
            "apply_url", "city", "work_type",
            "salary_min", "salary_max", "salary_currency",
            "posted_at", "is_active", "is_private", "fetched_at",
        ]
        read_only_fields = fields


class UserJobSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)

    class Meta:
        model = UserJob
        fields = [
            "id", "job", "status", "notes", "applied_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "job", "created_at", "updated_at"]


class UserJobCreateSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=UserJob.Status.choices, default=UserJob.Status.SAVED
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    applied_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_applied_at(self, value):
        from django.utils import timezone
        if value is not None and value > timezone.now():
            raise serializers.ValidationError("applied_at cannot be in the future.")
        return value

    def validate(self, attrs):
        if attrs.get("status") == UserJob.Status.APPLIED and not attrs.get("applied_at"):
            raise serializers.ValidationError(
                {"applied_at": "applied_at is required when status is 'applied'."}
            )
        return attrs


class DraftListSerializer(serializers.ModelSerializer):
    target_job = serializers.SerializerMethodField()

    class Meta:
        model = Draft
        fields = [
            "id", "title", "draft_type", "target_job_id",
            "target_job", "profile_snapshot_hash",
            "deleted_at", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_target_job(self, obj):
        if not obj.target_job_id:
            return None
        return {
            "id": str(obj.target_job.id),
            "title": obj.target_job.title,
            "company": obj.target_job.company,
        }


class DraftSerializer(serializers.ModelSerializer):
    target_job = JobListSerializer(read_only=True)
    target_job_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = Draft
        fields = [
            "id", "title", "draft_type",
            "target_job", "target_job_id",
            "content", "profile_snapshot_hash",
            "deleted_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "target_job", "profile_snapshot_hash",
            "deleted_at", "created_at", "updated_at",
        ]

    def validate_target_job_id(self, value):
        if value is None:
            return value
        if not Job.objects.filter(id=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError("Job not found or has been removed.")
        return value


class JobRecommendationSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)

    class Meta:
        model = JobRecommendation
        fields = [
            "id", "job", "score", "score_breakdown", "algorithm_version",
            "generated_at", "expires_at", "is_dismissed",
        ]
        read_only_fields = [
            "id", "job", "score", "score_breakdown", "algorithm_version",
            "generated_at", "expires_at",
        ]


class JobRecommendationDetailSerializer(serializers.ModelSerializer):
    job = JobDetailSerializer(read_only=True)

    class Meta:
        model = JobRecommendation
        fields = [
            "id", "job", "score", "score_breakdown", "algorithm_version",
            "generated_at", "expires_at", "is_dismissed",
        ]
        read_only_fields = [
            "id", "job", "score", "score_breakdown", "algorithm_version",
            "generated_at", "expires_at",
        ]


class RecommendationFilterSerializer(serializers.Serializer):
    dismissed = serializers.BooleanField(required=False, default=False)


class ResumeMatchScoreSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)
    score_display = serializers.SerializerMethodField()

    class Meta:
        model = ResumeMatchScore
        fields = [
            "id", "job",
            "overall_score", "score_display",
            "skill_score", "experience_score", "keyword_score",
            "title_score", "education_score", "certification_score",
            "location_score", "salary_score",
            "skill_gaps", "scoring_version",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_score_display(self, obj) -> int:
        from apps.career_hub.services.match_scoring import score_to_display
        return score_to_display(obj.overall_score)


class MatchScoreGenerateSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()

    def validate_job_id(self, value):
        if not Job.objects.filter(pk=value, is_active=True, deleted_at__isnull=True).exists():
            raise serializers.ValidationError("Job not found or is no longer active.")
        return value


class MatchScoreBulkGenerateSerializer(serializers.Serializer):
    job_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50,
    )


class JobSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    city = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    work_type = serializers.ChoiceField(
        choices=WorkType.choices, required=False, allow_null=True, default=None
    )
    source = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True, default=None
    )
    salary_min = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    salary_max = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    sort = serializers.ChoiceField(
        choices=["newest", "oldest", "salary_high", "salary_low"],
        required=False,
        default="newest",
    )
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(
        required=False, default=20, min_value=1, max_value=100
    )

    def validate(self, attrs):
        salary_min = attrs.get("salary_min")
        salary_max = attrs.get("salary_max")
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError(
                {"salary_max": "salary_max must be >= salary_min."}
            )
        return attrs


class SkillGapEntrySerializer(serializers.Serializer):
    token = serializers.CharField()
    job_count = serializers.IntegerField()
    display_name = serializers.CharField(allow_null=True, default=None)
    category = serializers.CharField(allow_null=True, default=None)
    description = serializers.CharField(allow_null=True, default=None)
    resource_type = serializers.CharField(allow_null=True, default=None)
    url = serializers.CharField(allow_null=True, default=None)
    prerequisites = serializers.ListField(child=serializers.CharField(), default=list)


class SkillGapSummarySerializer(serializers.Serializer):
    career_readiness_score = serializers.IntegerField(allow_null=True)
    total_jobs_scored = serializers.IntegerField()
    top_critical_gaps = SkillGapEntrySerializer(many=True)
    top_moderate_gaps = SkillGapEntrySerializer(many=True)
    top_soft_gaps = SkillGapEntrySerializer(many=True)
    gap_counts = serializers.DictField(child=serializers.IntegerField())


class SkillGapRecommendationSerializer(serializers.Serializer):
    token = serializers.CharField()
    tier = serializers.CharField()
    job_count = serializers.IntegerField()
    display_name = serializers.CharField(allow_null=True, default=None)
    category = serializers.CharField(allow_null=True, default=None)
    description = serializers.CharField(allow_null=True, default=None)
    resource_type = serializers.CharField(allow_null=True, default=None)
    url = serializers.CharField(allow_null=True, default=None)
    prerequisites = serializers.ListField(child=serializers.CharField(), default=list)


class JobSkillGapResourceSerializer(serializers.Serializer):
    token = serializers.CharField()
    display_name = serializers.CharField(allow_null=True, default=None)
    category = serializers.CharField(allow_null=True, default=None)
    description = serializers.CharField(allow_null=True, default=None)
    resource_type = serializers.CharField(allow_null=True, default=None)
    url = serializers.CharField(allow_null=True, default=None)
    prerequisites = serializers.ListField(child=serializers.CharField(), default=list)


class JobSkillGapSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    job_title = serializers.CharField()
    job_company = serializers.CharField()
    overall_score = serializers.DecimalField(max_digits=4, decimal_places=3)
    score_display = serializers.IntegerField()
    critical_gaps = JobSkillGapResourceSerializer(many=True)
    moderate_gaps = JobSkillGapResourceSerializer(many=True)
    soft_gaps = JobSkillGapResourceSerializer(many=True)
    low_gaps = JobSkillGapResourceSerializer(many=True)


class SkillGapTierFilterSerializer(serializers.Serializer):
    tier = serializers.ChoiceField(
        choices=["critical", "moderate", "soft", "all"],
        default="critical",
    )
