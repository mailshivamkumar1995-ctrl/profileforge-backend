import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.authentication.serializers import (
    RegisterSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    UpdateProfileSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from apps.authentication.services import AuthService
from core.mixins import SuccessResponseMixin
from core.throttles import LoginRateThrottle, RegistrationRateThrottle, PasswordResetRateThrottle

logger = logging.getLogger(__name__)
User = get_user_model()


def _set_auth_cookies(response, access_token, refresh_token):
    secure = not settings.DEBUG
    response.set_cookie(
        "access_token",
        access_token,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=secure,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=secure,
        path="/api/v1/auth/refresh/",
    )


class RegisterView(SuccessResponseMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]
    serializer_class = RegisterSerializer

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AuthService.register(serializer.validated_data)
        
        response = self.success_response(
            data={"user": UserSerializer(result["user"]).data},
            status_code=status.HTTP_201_CREATED,
        )
        _set_auth_cookies(response, result["access_token"], result["refresh_token"])
        return response


class LoginView(SuccessResponseMixin, TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        response = self.success_response(data={"user": data["user"]})
        _set_auth_cookies(response, data["access"], data["refresh"])
        return response


class CookieTokenRefreshView(SuccessResponseMixin, TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "Refresh token not found."}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Inject refresh token into data
        data = request.data.copy()
        data["refresh"] = refresh_token
        
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        new_access = serializer.validated_data.get("access")
        new_refresh = serializer.validated_data.get("refresh", refresh_token)
        
        response = self.success_response(data={"message": "Token refreshed"})
        _set_auth_cookies(response, new_access, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token:
            AuthService.logout(refresh_token)
            
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token", path="/api/v1/auth/refresh/")
        return response


class MeView(SuccessResponseMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self.success_response(data=UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=UserSerializer(request.user).data)


class ChangePasswordView(SuccessResponseMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.change_password(
            request.user,
            serializer.validated_data["old_password"],
            serializer.validated_data["new_password"],
        )
        return self.success_response(data={"message": "Password updated successfully"})


class PasswordResetRequestView(SuccessResponseMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.request_password_reset(serializer.validated_data["email"])
        return self.success_response(data={"message": "Password reset email sent if account exists."})


class PasswordResetConfirmView(SuccessResponseMixin, APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.confirm_password_reset(
            serializer.validated_data["uid"],
            serializer.validated_data["token"],
            serializer.validated_data["new_password"],
        )
        return self.success_response(data={"message": "Password reset successful."})
