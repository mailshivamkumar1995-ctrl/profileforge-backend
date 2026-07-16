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
