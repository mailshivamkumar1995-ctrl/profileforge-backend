from rest_framework import serializers
from apps.exports.models import ExportJob, ExportResourceType, ExportFormat


class ExportJobListSerializer(serializers.ModelSerializer):
    template_slug = serializers.SerializerMethodField()
    resource_title = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()

    class Meta:
        model = ExportJob
        fields = [
            "id", "resource_type", "resource_id", "format",
            "template_slug", "resource_title", "filename", "status", "file_size",
            "created_at", "completed_at",
        ]
        read_only_fields = fields

    def get_template_slug(self, obj):
        return obj.template.slug if obj.template else None

    def get_resource_title(self, obj):
        from apps.exports.services import ExportService
        return ExportService.get_resource_title(obj)

    def get_filename(self, obj):
        from apps.exports.services import ExportService
        return ExportService.get_download_filename(obj)


class ExportJobDetailSerializer(serializers.ModelSerializer):
    template_slug = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    resource_title = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()

    class Meta:
        model = ExportJob
        fields = [
            "id", "resource_type", "resource_id", "format",
            "template_slug", "resource_title", "filename", "status", "file_size",
            "download_url", "url_expires_at",
            "error_message", "created_at", "completed_at",
        ]
        read_only_fields = fields

    def get_template_slug(self, obj):
        return obj.template.slug if obj.template else None

    def get_resource_title(self, obj):
        from apps.exports.services import ExportService
        return ExportService.get_resource_title(obj)

    def get_filename(self, obj):
        from apps.exports.services import ExportService
        return ExportService.get_download_filename(obj)

    def get_download_url(self, obj):
        from apps.exports.services import ExportService
        from apps.exports.models import ExportStatus
        if obj.status != ExportStatus.COMPLETED or not obj.file_path:
            return None
        try:
            return ExportService.get_download_url(obj)
        except Exception:
            return obj.download_url


class ExportRequestSerializer(serializers.Serializer):
    resource_type = serializers.ChoiceField(choices=ExportResourceType.choices)
    resource_id = serializers.UUIDField()
    format = serializers.ChoiceField(choices=ExportFormat.choices)
    template_slug = serializers.CharField(required=False, allow_blank=True, default="")
