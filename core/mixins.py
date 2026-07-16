from rest_framework.response import Response
from rest_framework import status


class SuccessResponseMixin:
    """Wraps serialized data in the standard success envelope."""

    def success_response(self, data=None, status_code=status.HTTP_200_OK, message=None):
        from django.utils import timezone
        import uuid

        body = {
            "success": True,
            "data": data,
            "meta": {
                "request_id": getattr(self.request, "request_id", str(uuid.uuid4())),
                "timestamp": timezone.now().isoformat(),
                "version": "v1",
            },
        }
        if message:
            body["message"] = message
        return Response(body, status=status_code)


class OwnershipMixin:
    """Restricts queryset to objects owned by the current user."""

    owner_field = "user"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(**{self.owner_field: self.request.user})
