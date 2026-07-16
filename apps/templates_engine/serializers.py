from rest_framework import serializers
from apps.templates_engine.models import Template


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = [
            "id", "slug", "name", "type", "category", "version",
            "is_ats_optimized", "is_single_page", "is_premium",
            "thumbnail_path", "description", "preview_data",
        ]
        read_only_fields = fields
