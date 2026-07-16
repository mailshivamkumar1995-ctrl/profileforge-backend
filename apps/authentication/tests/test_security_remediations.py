"""
Regression tests for security remediations.

SEC-001: OAuth token encryption
SEC-002: Access token invalidation after password change
"""
import time
from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


# ─── Fixtures ─────────────────────────────────────────────────────────────────

ENCRYPTION_KEY = "kPF3eqbIk0bJqNH1WJ_gu75MTlPdJa00CWwmqQNMuWo="  # test key only


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_payload():
    return {
        "email": "sectest@example.com",
        "username": "sectest",
        "first_name": "Sec",
        "last_name": "Test",
        "password": "SecurePass123!",
        "password_confirm": "SecurePass123!",
    }


@pytest.fixture
def registered_user(api_client, user_payload):
    resp = api_client.post("/api/v1/auth/register/", user_payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    return resp.json()["data"]


# ─── SEC-001: OAuth token encryption ──────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthTokenEncryption:

    @pytest.fixture(autouse=True)
    def set_encryption_key(self, settings):
        settings.FIELD_ENCRYPTION_KEY = ENCRYPTION_KEY

    def test_encrypt_decrypt_roundtrip(self):
        """Fernet encrypt/decrypt is lossless."""
        from core.crypto import encrypt_value, decrypt_value

        plaintext = "ya29.a0AfH6SM_test_google_access_token_abc123"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_ciphertext_is_not_plaintext(self):
        """Encrypted value never equals the original."""
        from core.crypto import encrypt_value

        token = "github_pat_secret_12345"
        assert encrypt_value(token) != token

    def test_encrypted_field_stores_ciphertext(self):
        """OAuthAccount.access_token is stored as ciphertext, not plaintext."""
        from apps.authentication.models import OAuthAccount, User

        user = User.objects.create_user(
            email="oauthtest@example.com",
            username="oauthtest",
            first_name="OAuth",
            last_name="Test",
            password="Pass123!",
        )
        raw_token = "ya29.plaintext_google_token"
        account = OAuthAccount.objects.create(
            user=user,
            provider="google",
            provider_user_id="goog_123",
            access_token=raw_token,
        )
        account.refresh_from_db()

        # Python property returns decrypted value
        assert account.access_token == raw_token

        # DB raw value should be ciphertext (starts with Fernet prefix 'gAAAAA')
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "SELECT access_token FROM oauth_accounts WHERE id = %s", [account.id.hex]
            )
            raw_db = cur.fetchone()[0]
        assert raw_db != raw_token
        assert raw_db.startswith("gAAAAA")

    def test_missing_encryption_key_raises(self):
        """Encryption without FIELD_ENCRYPTION_KEY raises RuntimeError."""
        with override_settings(FIELD_ENCRYPTION_KEY=""):
            from core.crypto import encrypt_value
            with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY is not set"):
                encrypt_value("some_token")

    def test_encrypt_empty_string_returns_empty(self):
        """Empty token is stored as empty string (not encrypted empty)."""
        from core.crypto import encrypt_value
        assert encrypt_value("") == ""

    def test_decrypt_empty_string_returns_empty(self):
        from core.crypto import decrypt_value
        assert decrypt_value("") == ""


# ─── SEC-002: Access token invalidation after password change ─────────────────


@pytest.mark.django_db
class TestPasswordChangeTokenInvalidation:

    register_url = "/api/v1/auth/register/"
    change_password_url = "/api/v1/auth/change-password/"
    me_url = "/api/v1/auth/me/"

    def test_access_token_rejected_after_password_change(self, api_client, user_payload):
        """
        An access token issued before a password change must be rejected by
        PasswordAwareJWTAuthentication even if it has not yet expired.
        """
        # Register and obtain initial token
        resp = api_client.post(self.register_url, user_payload, format="json")
        old_access = resp.json()["data"]["access_token"]

        # Confirm token works before password change
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        assert api_client.get(self.me_url).status_code == status.HTTP_200_OK

        # Change password (a small sleep ensures password_changed_at > token iat)
        time.sleep(1)
        api_client.post(
            self.change_password_url,
            {"old_password": "SecurePass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )

        # Old token must now be rejected
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        response = api_client.get(self.me_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_new_token_after_password_change_is_valid(self, api_client, user_payload):
        """A token obtained after a password change must be accepted."""
        reg_resp = api_client.post(self.register_url, user_payload, format="json")
        old_access = reg_resp.json()["data"]["access_token"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        time.sleep(1)
        api_client.post(
            "/api/v1/auth/change-password/",
            {"old_password": "SecurePass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        login_resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": "sectest@example.com", "password": "NewPass456!"},
            format="json",
        )
        new_access = login_resp.json()["data"]["access_token"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        assert api_client.get(self.me_url).status_code == status.HTTP_200_OK

    def test_set_password_records_timestamp(self):
        """User.set_password() must update password_changed_at."""
        from apps.authentication.models import User

        user = User.objects.create_user(
            email="ts@example.com", username="tsuser",
            first_name="TS", last_name="User", password="OldPass123!",
        )
        assert user.password_changed_at is not None  # set by create_user → set_password

        before = user.password_changed_at
        time.sleep(0.01)
        user.set_password("NewPass456!")
        user.save()

        assert user.password_changed_at > before

    def test_token_without_iat_rejected_after_password_change(self):
        """
        A JWT without an 'iat' claim must be rejected when the user has a
        password_changed_at timestamp.
        """
        from core.authentication import PasswordAwareJWTAuthentication
        from rest_framework_simplejwt.exceptions import AuthenticationFailed
        from apps.authentication.models import User
        from django.utils import timezone

        user = User.objects.create_user(
            email="noiat@example.com", username="noiat",
            first_name="No", last_name="IAT", password="Pass123!",
        )
        user.password_changed_at = timezone.now()
        user.save()

        auth = PasswordAwareJWTAuthentication()
        # Fake validated_token without 'iat' claim
        token = MagicMock()
        token.get.return_value = None  # iat is None
        token.__getitem__ = MagicMock(return_value=str(user.id))

        with patch.object(auth.__class__.__bases__[0], "get_user", return_value=user):
            with pytest.raises(AuthenticationFailed, match="password change"):
                auth.get_user(token)
