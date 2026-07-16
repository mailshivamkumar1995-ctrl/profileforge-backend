from rest_framework import serializers
from apps.cover_letters.models import CoverLetter, CoverLetterVersion, CoverLetterTone
from apps.templates_engine.serializers import TemplateSerializer


class CoverLetterVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoverLetterVersion
        fields = [
            "id", "version_number", "content_snapshot",
            "rendered_html", "change_summary", "created_at",
        ]
        read_only_fields = fields


class CoverLetterListSerializer(serializers.ModelSerializer):
    template = TemplateSerializer(read_only=True)

    class Meta:
        model = CoverLetter
        fields = [
            "id", "title", "template", "company_name", "job_title",
            "tone", "status", "ai_generated", "current_version",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "current_version", "created_at", "updated_at"]


class CoverLetterDetailSerializer(serializers.ModelSerializer):
    template = TemplateSerializer(read_only=True)
    template_slug = serializers.SlugField(write_only=True, required=False, allow_blank=True)
    resume_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = CoverLetter
        fields = [
            "id", "title", "template", "template_slug", "resume_id",
            "company_name", "job_title", "hiring_manager_name", "hiring_manager_title",
            "company_address", "tone", "body_content", "job_description",
            "ai_generated", "status", "current_version",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "template", "ai_generated", "current_version", "created_at", "updated_at",
        ]


class CoverLetterCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    company_name = serializers.CharField(max_length=200)
    job_title = serializers.CharField(max_length=200)
    template_slug = serializers.SlugField(required=False, allow_blank=True)
    resume_id = serializers.UUIDField(required=False, allow_null=True)
    hiring_manager_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    hiring_manager_title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    company_address = serializers.DictField(required=False, default=dict)
    tone = serializers.ChoiceField(
        choices=CoverLetterTone.values, default=CoverLetterTone.PROFESSIONAL
    )
    body_content = serializers.CharField(required=False, allow_blank=True, default="")
    job_description = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["draft", "active", "archived"], default="draft")


class CoverLetterUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    company_name = serializers.CharField(max_length=200, required=False)
    job_title = serializers.CharField(max_length=200, required=False)
    template_slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True)
    resume_id = serializers.UUIDField(required=False, allow_null=True)
    hiring_manager_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    hiring_manager_title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    company_address = serializers.DictField(required=False)
    tone = serializers.ChoiceField(choices=CoverLetterTone.values, required=False)
    body_content = serializers.CharField(required=False, allow_blank=True)
    job_description = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=["draft", "active", "archived"], required=False)


class CoverLetterGenerateSerializer(serializers.Serializer):
    tone = serializers.ChoiceField(
        choices=CoverLetterTone.values, default=CoverLetterTone.PROFESSIONAL
    )
    job_description = serializers.CharField(required=False, allow_blank=True, default="")


class CoverLetterRewriteSerializer(serializers.Serializer):
    instruction = serializers.CharField(
        max_length=1000, required=False, allow_blank=True,
        help_text="Optional instruction for how to rewrite (e.g. 'more concise', 'add quantifiable impact')"
    )


class CoverLetterImproveToneSerializer(serializers.Serializer):
    tone = serializers.ChoiceField(choices=CoverLetterTone.values)
