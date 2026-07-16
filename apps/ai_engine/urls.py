from django.urls import path
from apps.ai_engine.views import TailorView, AIAssistantChatView

urlpatterns = [
    path("tailor/", TailorView.as_view(), name="ai-tailor"),
    path("assistant/chat/", AIAssistantChatView.as_view(), name="ai-assistant-chat"),
]
