"""
Custom JWT authentication backend.

SEC-002: PasswordAwareJWTAuthentication rejects access tokens that were
issued before the user's most recent password change. This closes the
15-minute window where a stolen access token remains valid after the
victim changes their password.

How it works
------------
1. User.set_password() records timezone.now() in User.password_changed_at.
2. simplejwt encodes the token's issued-at time as the 'iat' claim.
3. This backend validates that iat >= password_changed_at.
   If the token was issued before the password change, authentication fails
   immediately regardless of signature validity.
"""
import logging
from datetime import datetime, timezone as dt_timezone

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class PasswordAwareJWTAuthentication(JWTAuthentication):
    """
    Extends JWTAuthentication to invalidate access tokens issued before
    the user's most recent password change, and supports HTTP-Only cookies.
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            raw_token = request.COOKIES.get("access_token")
            if raw_token is None:
                return None
            try:
                # Need to convert string token to bytes for simplejwt
                raw_token = raw_token.encode("utf-8")
            except AttributeError:
                pass
        else:
            raw_token = self.get_raw_token(header)
            if raw_token is None:
                return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not user.password_changed_at:
            return user

        # 'iat' is seconds since epoch (integer) per RFC 7519.
        token_iat_raw = validated_token.get("iat")
        if token_iat_raw is None:
            # No iat claim — token cannot be trusted for post-password-change sessions.
            logger.warning(
                "JWT has no 'iat' claim for user %s; rejecting after password change.",
                user.id,
            )
            raise AuthenticationFailed(
                "Token is invalid after a password change. Please log in again.",
                code="token_invalidated",
            )

        token_issued_at = datetime.fromtimestamp(int(token_iat_raw), tz=dt_timezone.utc)

        # Ensure password_changed_at is timezone-aware for comparison
        pw_changed = user.password_changed_at
        if pw_changed.tzinfo is None:
            from django.utils import timezone
            pw_changed = timezone.make_aware(pw_changed)

        # JWT iat is in whole seconds; truncate pw_changed to the same precision
        # so a token issued in the same second as set_password() is not wrongly rejected.
        pw_changed = pw_changed.replace(microsecond=0)

        if token_issued_at < pw_changed:
            logger.info(
                "Rejected token for user %s: issued at %s, password changed at %s",
                user.id,
                token_issued_at.isoformat(),
                pw_changed.isoformat(),
            )
            raise AuthenticationFailed(
                "Token is invalid after a password change. Please log in again.",
                code="token_invalidated",
            )

        return user
