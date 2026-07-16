from rest_framework import serializers
from apps.portfolios.models import Portfolio, PortfolioVersion, AnalyticsProvider
from apps.templates_engine.serializers import TemplateSerializer


class PortfolioVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioVersion
        fields = [
            "id", "version_number", "theme_slug", "section_settings",
            "rendered_html", "change_summary", "created_at",
        ]
        read_only_fields = fields


class PortfolioListSerializer(serializers.ModelSerializer):
    theme = TemplateSerializer(read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            "id", "slug", "theme", "is_published", "is_public",
            "seo_title", "custom_domain", "current_version",
            "published_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "current_version", "published_at", "created_at", "updated_at"]


class PortfolioDetailSerializer(serializers.ModelSerializer):
    theme = TemplateSerializer(read_only=True)
    theme_slug = serializers.SlugField(write_only=True, required=False, allow_blank=True)
    public_url = serializers.SerializerMethodField()
    section_settings = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = [
            "id", "slug", "theme", "theme_slug", "theme_settings",
            "section_settings", "custom_domain", "is_published", "is_public",
            "seo_title", "seo_description", "seo_keywords", "og_image_path",
            "analytics_provider", "analytics_id",
            "published_at", "last_generated_at", "current_version",
            "public_url", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "theme", "is_published", "published_at",
            "last_generated_at", "current_version", "public_url",
            "created_at", "updated_at",
        ]

    def get_public_url(self, obj: Portfolio) -> str:
        return obj.public_url

    def get_section_settings(self, obj: Portfolio) -> dict:
        return obj.get_section_settings()


class PortfolioCreateSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=100)
    theme_slug = serializers.SlugField(required=False, allow_blank=True)
    seo_title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    seo_description = serializers.CharField(required=False, allow_blank=True)

    def validate_slug(self, value: str) -> str:
        if Portfolio.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This slug is already taken.")
        return value


class PortfolioUpdateSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=100, required=False)
    theme_slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True)
    theme_settings = serializers.DictField(required=False)
    section_settings = serializers.DictField(required=False)
    is_public = serializers.BooleanField(required=False)
    custom_domain = serializers.CharField(max_length=255, required=False, allow_blank=True)
    seo_title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    seo_description = serializers.CharField(required=False, allow_blank=True)
    seo_keywords = serializers.CharField(max_length=500, required=False, allow_blank=True)
    analytics_provider = serializers.ChoiceField(choices=AnalyticsProvider.values, required=False)
    analytics_id = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_slug(self, value: str) -> str:
        instance_id = self.context.get("portfolio_id")
        qs = Portfolio.objects.filter(slug=value)
        if instance_id:
            qs = qs.exclude(id=instance_id)
        if qs.exists():
            raise serializers.ValidationError("This slug is already taken.")
        return value


class PublicPortfolioSerializer(serializers.ModelSerializer):
    """Minimal read-only serializer for public portfolio data."""
    theme = TemplateSerializer(read_only=True)
    section_settings = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            "id", "slug", "username", "theme", "theme_settings",
            "section_settings", "seo_title", "seo_description",
            "seo_keywords", "og_image_path", "analytics_provider", "analytics_id",
            "published_at",
        ]

    def get_section_settings(self, obj: Portfolio) -> dict:
        return obj.get_section_settings()
