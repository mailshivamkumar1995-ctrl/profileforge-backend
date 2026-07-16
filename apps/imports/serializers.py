from rest_framework import serializers
from apps.imports.models import ImportJob


class ImportJobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = [
            "id", "original_filename", "file_type", "file_size",
            "status", "created_at", "updated_at", "applied_at",
        ]
        read_only_fields = fields


class ImportJobDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = [
            "id", "original_filename", "file_type", "file_size",
            "status", "parsed_data", "mapping_review", "confidence_scores",
            "error_message", "created_at", "updated_at", "applied_at",
        ]
        read_only_fields = fields


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ApplyMappingSerializer(serializers.Serializer):
    """Carries the user-approved field mappings to apply to the profile."""

    personal = serializers.DictField(required=False, default=dict)
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    work_experiences = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    educations = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    skills = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    projects = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    certifications = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    achievements = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
