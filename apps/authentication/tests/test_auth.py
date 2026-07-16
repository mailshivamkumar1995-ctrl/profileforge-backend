import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def register_payload():
    # 3-field registration form (FV-012, BD-017, BD-018):
    # username auto-generated, last_name optional
    return {
        "email": "test@example.com",
        "first_name": "Test",
        "password": "SecurePass123!",
        "password_confirm": "SecurePass123!",
    }


@pytest.mark.django_db
class TestRegister:
    url = "/api/v1/auth/register/"

    def test_register_success(self, api_client, register_payload):
        response = api_client.post(self.url, register_payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["user"]["email"] == "test@example.com"

    def test_register_creates_profile(self, api_client, register_payload):
        from apps.profiles.models import UserProfile
        from apps.authentication.models import User

        api_client.post(self.url, register_payload, format="json")
        user = User.objects.get(email="test@example.com")
        assert UserProfile.objects.filter(user=user).exists()

    def test_register_creates_portfolio(self, api_client, register_payload):
        from apps.portfolios.models import Portfolio
        from apps.authentication.models import User

        api_client.post(self.url, register_payload, format="json")
        user = User.objects.get(email="test@example.com")
        portfolio = Portfolio.objects.get(user=user)
        # slug = auto-generated username derived from email local part "test"
        assert portfolio.slug == user.username

    def test_register_username_auto_generated(self, api_client, register_payload):
        from apps.authentication.models import User
        api_client.post(self.url, register_payload, format="json")
        user = User.objects.get(email="test@example.com")
        assert user.username  # not empty
        assert "test" in user.username  # derived from email local part

    def test_register_without_last_name(self, api_client):
        payload = {
            "email": "nolastname@example.com",
            "first_name": "Solo",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = api_client.post(self.url, payload, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["user"]["last_name"] == ""

    def test_register_with_optional_last_name(self, api_client):
        payload = {
            "email": "withlast@example.com",
            "first_name": "With",
            "last_name": "LastName",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = api_client.post(self.url, payload, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["user"]["last_name"] == "LastName"

    def test_register_duplicate_username_gets_suffix(self, api_client):
        # Two users with same email local part ("twin") get unique usernames
        for i, tld in enumerate(["@a.com", "@b.com"]):
            api_client.post(self.url, {
                "email": f"twin{tld}",
                "first_name": "Twin",
                "password": "SecurePass123!",
                "password_confirm": "SecurePass123!",
            }, format="json")
        from apps.authentication.models import User
        usernames = list(User.objects.filter(first_name="Twin").values_list("username", flat=True))
        assert len(set(usernames)) == 2  # both unique

    def test_register_duplicate_email(self, api_client, register_payload):
        api_client.post(self.url, register_payload, format="json")
        response = api_client.post(self.url, register_payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["success"] is False

    def test_register_password_mismatch(self, api_client, register_payload):
        register_payload["password_confirm"] = "WrongPassword!"
        response = api_client.post(self.url, register_payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_weak_password(self, api_client, register_payload):
        register_payload["password"] = "123"
        register_payload["password_confirm"] = "123"
        response = api_client.post(self.url, register_payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:
    register_url = "/api/v1/auth/register/"
    login_url = "/api/v1/auth/login/"

    def _create_user(self, api_client, payload):
        api_client.post(self.register_url, payload, format="json")

    def test_login_success(self, api_client, register_payload):
        self._create_user(api_client, register_payload)
        response = api_client.post(
            self.login_url,
            {"email": "test@example.com", "password": "SecurePass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_login_wrong_password(self, api_client, register_payload):
        self._create_user(api_client, register_payload)
        response = api_client.post(
            self.login_url,
            {"email": "test@example.com", "password": "WrongPassword!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        response = api_client.post(
            self.login_url,
            {"email": "nobody@example.com", "password": "SomePass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMe:
    register_url = "/api/v1/auth/register/"
    me_url = "/api/v1/auth/me/"

    def test_me_requires_auth(self, api_client):
        response = api_client.get(self.me_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_returns_user(self, api_client, register_payload):
        reg_response = api_client.post(self.register_url, register_payload, format="json")
        token = reg_response.json()["data"]["access_token"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get(self.me_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["email"] == "test@example.com"


@pytest.mark.django_db
class TestLogout:
    register_url = "/api/v1/auth/register/"
    logout_url = "/api/v1/auth/logout/"

    def test_logout_success(self, api_client, register_payload):
        reg_response = api_client.post(self.register_url, register_payload, format="json")
        tokens = reg_response.json()["data"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
        response = api_client.post(
            self.logout_url, {"refresh_token": tokens["refresh_token"]}, format="json"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
class TestPasswordReset:
    reset_url = "/api/v1/auth/password/reset/"
    confirm_url = "/api/v1/auth/password/reset/confirm/"

    def _make_reset_link(self, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token

    def test_reset_request_known_email_returns_200(self, api_client, user):
        response = api_client.post(self.reset_url, {"email": user.email}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_reset_request_unknown_email_returns_200(self, api_client):
        # No email-enumeration — always 200
        response = api_client.post(self.reset_url, {"email": "nobody@example.com"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_reset_request_invalid_email_returns_400(self, api_client):
        response = api_client.post(self.reset_url, {"email": "not-an-email"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_confirm_valid_token_changes_password(self, api_client, user):
        uid, token = self._make_reset_link(user)
        response = api_client.post(self.confirm_url, {
            "uid": uid,
            "token": token,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("NewSecurePass456!")

    def test_reset_confirm_invalid_token_returns_400(self, api_client, user):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = api_client.post(self.confirm_url, {
            "uid": uid,
            "token": "invalid-token-value",
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"

    def test_reset_confirm_invalid_uid_returns_400(self, api_client, user):
        _, token = self._make_reset_link(user)
        response = api_client.post(self.confirm_url, {
            "uid": "notvalidbase64==",
            "token": token,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_confirm_password_mismatch_returns_400(self, api_client, user):
        uid, token = self._make_reset_link(user)
        response = api_client.post(self.confirm_url, {
            "uid": uid,
            "token": token,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "DifferentPass789!",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_confirm_token_invalidated_after_use(self, api_client, user):
        uid, token = self._make_reset_link(user)
        # First use — succeeds
        api_client.post(self.confirm_url, {
            "uid": uid, "token": token,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }, format="json")
        # Second use with same token — fails (password changed = HMAC input changed)
        response = api_client.post(self.confirm_url, {
            "uid": uid, "token": token,
            "new_password": "AnotherPass789!",
            "new_password_confirm": "AnotherPass789!",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_confirm_sets_password_changed_at(self, api_client, user):
        uid, token = self._make_reset_link(user)
        api_client.post(self.confirm_url, {
            "uid": uid, "token": token,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }, format="json")
        user.refresh_from_db()
        assert user.password_changed_at is not None

    def test_reset_public_endpoint_no_auth_required(self, api_client, user):
        # Confirm neither endpoint requires authentication
        response = api_client.post(self.reset_url, {"email": user.email}, format="json")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
