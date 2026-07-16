from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from apps.templates_engine.models import Template
from apps.templates_engine.serializers import TemplateSerializer
from core.mixins import SuccessResponseMixin


class TemplateViewSet(SuccessResponseMixin, ReadOnlyModelViewSet):
    serializer_class = TemplateSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(data=serializer.data)

    def get_queryset(self):
        qs = Template.objects.filter(is_active=True)
        template_type = self.request.query_params.get("type")
        category = self.request.query_params.get("category")
        if template_type:
            qs = qs.filter(type=template_type)
        if category:
            qs = qs.filter(category=category)
        return qs.order_by("category", "name")
