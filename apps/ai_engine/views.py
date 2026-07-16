import logging
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from core.mixins import SuccessResponseMixin

logger = logging.getLogger(__name__)


class TailorView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/ai/tailor/
    Body: { "job_description": "..." }

    Parses the JD, rewrites the user's resume content to match it,
    generates a tailored cover letter, and persists both as named drafts.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_description = request.data.get("job_description", "").strip()
        if not job_description:
            return Response(
                {"detail": "job_description is required and cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(job_description) < 50:
            return Response(
                {"detail": "Please provide a more complete job description (at least 50 characters)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.ai_engine.jd_tailoring_service import JDTailoringService
            service = JDTailoringService(user=request.user)
            result = service.tailor(job_description)
            return self.success_response(data=result)
        except Exception as e:
            logger.error("JD tailoring failed for user %s", request.user.id, exc_info=True)
            return Response(
                {"detail": f"AI tailoring failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AIAssistantChatView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/ai/assistant/chat/
    Body: { "messages": [{"role": "user", "content": "..."}] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        messages = request.data.get("messages", [])
        if not messages or not isinstance(messages, list):
            return Response(
                {"detail": "messages array is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.ai_engine.assistant_service import AIAssistantService
            service = AIAssistantService(user=request.user)
            response_text = service.chat(messages)
            return self.success_response(data={"content": response_text})
        except Exception as e:
            logger.error("AI Assistant chat failed for user %s", request.user.id, exc_info=True)
            return Response(
                {"detail": f"Chat failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
