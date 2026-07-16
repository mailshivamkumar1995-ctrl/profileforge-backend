from rest_framework import serializers
from apps.resumes.models import Resume, ResumeVersion
from apps.templates_engine.serializers import TemplateSerializer


class ResumeVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeVersion
        fields = [
            "id", "version_number", "change_summary",
            "rendered_html", "export_pdf_path", "export_docx_path", "created_at",
        ]
        read_only_fields = fields


class ResumeListSerializer(serializers.ModelSerializer):
    template = TemplateSerializer(read_only=True)

    class Meta:
        model = Resume
        fields = [
            "id", "title", "template", "is_primary", "status",
            "target_role", "target_company", "ats_score", "current_version",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "current_version", "created_at", "updated_at"]


class ResumeDetailSerializer(serializers.ModelSerializer):
    template = TemplateSerializer(read_only=True)
    template_slug = serializers.SlugField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Resume
        fields = [
            "id", "title", "template", "template_slug", "template_settings",
            "custom_sections", "is_primary", "target_role", "target_company",
            "ats_score", "ats_analysis", "status", "current_version",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "template", "ats_score", "ats_analysis",
            "current_version", "created_at", "updated_at",
        ]


class ResumeCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    template_slug = serializers.SlugField(required=False, allow_blank=True)
    target_role = serializers.CharField(max_length=200, required=False, allow_blank=True)
    target_company = serializers.CharField(max_length=200, required=False, allow_blank=True)
    template_settings = serializers.DictField(required=False, default=dict)
    status = serializers.ChoiceField(
        choices=["draft", "active", "archived"], default="draft"
    )


class ResumeUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    template_slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True)
    target_role = serializers.CharField(max_length=200, required=False, allow_blank=True)
    target_company = serializers.CharField(max_length=200, required=False, allow_blank=True)
    template_settings = serializers.DictField(required=False)
    custom_sections = serializers.ListField(required=False)
    status = serializers.ChoiceField(
        choices=["draft", "active", "archived"], required=False
    )


class ATSAnalyzeSerializer(serializers.Serializer):
    job_description = serializers.CharField(required=False, allow_blank=True, default="")


class OptimizeSerializer(serializers.Serializer):
    job_description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=3000,
    )
