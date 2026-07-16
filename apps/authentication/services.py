import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UserSession
from apps.profiles.models import UserProfile
from core.models import UserSettings

logger = logging.getLogger(__name__)

User = get_user_model()


class AuthService:

    @staticmethod
    def _generate_username(email: str) -> str:
        """Derive a unique username from the email local part (BD-017)."""
        import re
        base = re.sub(r"[^a-z0-9_]", "_", email.split("@")[0].lower())[:40]
        username = base
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}{suffix}"
            suffix += 1
        return username

    @staticmethod
    def register(validated_data: dict) -> dict:
        """Create user + profile + settings in a single transaction."""
        from django.db import transaction

        username = AuthService._generate_username(validated_data["email"])

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                **validated_data,
            )

            # Auto-create profile
            UserProfile.objects.create(user=user)

            # Auto-create settings
            UserSettings.objects.create(user=user)

            # Auto-create portfolio with user's username as slug
            from apps.portfolios.models import Portfolio
            Portfolio.objects.create(
                user=user,
                profile=user.profile,
                slug=user.username,
            )

        tokens = AuthService.generate_tokens(user)
        logger.info("New user registered", extra={"user_id": str(user.id)})
        return {"user": user, **tokens}

    @staticmethod
    def generate_tokens(user) -> dict:
        refresh = RefreshToken.for_user(user)
        return {
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
        }

    @staticmethod
    def logout(refresh_token_str: str) -> None:
        """Blacklist the refresh token."""
        try:
            token = RefreshToken(refresh_token_str)
            token.blacklist()
        except Exception:
            logger.warning("Failed to blacklist token during logout")

    @staticmethod
    def change_password(user, old_password: str, new_password: str) -> None:
        if not user.check_password(old_password):
            from core.exceptions import ValidationException
            raise ValidationException("Current password is incorrect.")
        user.set_password(new_password)
        # set_password() sets password_changed_at in memory (SEC-002).
        # Full save() required so auto_now (updated_at) and password_changed_at both persist.
        user.save()

        # FINDING-008: invalidate all outstanding refresh tokens after password change
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
            logger.info("Blacklisted %d tokens after password change", tokens.count(),
                        extra={"user_id": str(user.id)})
        except Exception:
            logger.warning("Failed to blacklist tokens after password change", exc_info=True)

        logger.info("Password changed", extra={"user_id": str(user.id)})
    
    @staticmethod
    def request_password_reset(email: str) -> None:
        """Send a password reset email if the account exists. No email enumeration —
        always succeeds from the caller's perspective regardless of whether the
        email matches a real account."""
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.info("Password reset requested for unknown email: %s", email)
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

        send_mail(
            subject="Reset your ProfileForge password",
            message=f"Click the link to reset your password: {reset_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        logger.info("Password reset email sent to user_id=%s", user.pk)

    @staticmethod
    def confirm_password_reset(uid: str, token: str, new_password: str) -> None:
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode
        from core.exceptions import InvalidResetTokenException

        try:
            user_pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise InvalidResetTokenException("Invalid or expired reset link.")

        if not default_token_generator.check_token(user, token):
            raise InvalidResetTokenException("Invalid or expired reset link.")

        user.set_password(new_password)
        user.save(update_fields=["password", "password_changed_at"])
        logger.info("Password reset completed for user_id=%s", user.pk)
