"""
Python wrapper client for Firebase REST API.

The client is able to switch from requests to Firebase's servers to an
eventual local Firebase emulator, dependng on whether the
FIREBASE_AUTH_EMULATOR_HOST variable is set.
"""

import httpx
from fastapi import status

from app import settings

from .errors import get_error
from .models import (
    GetAccountInfoResponseModel,
    SendEmailVerificationResponseModel,
    SendPasswordResetEmailResponseModel,
    SignInWithEmailPasswordResponseModel,
    UpdateResponseModel,
    VerifyPasswordResetResponseModel,
)


def check_response(
    response: httpx.Response,
    status_code: int,
    url: str,
) -> dict:
    """
    Inner decorator function, calls the FirebaseRESTAPIClient method
    and examines its response, to raise error or return value.

    Raises:
        UnhandledFirebaseRESTAPIClientException: Unhandled
            FirebaseRESTAPIClient exception.
        FirebaseRESTAPIClientException: Handlded
            FirebaseRESTAPIClient exception

    Returns:
        dict: The response as JSON.
    """
    if response.status_code != status_code:
        err = response.json()
        message = err["error"]["message"]
        raise get_error(response, message, url)
    return response.json()


class FirebaseRESTAPIClient:
    """
    Simple client to wrap Firebase REST API calls.
    """

    def __init__(self, api_key: str):
        """
        Creates an instance of this class.
        """
        self.api_key = api_key
        self.base_url = settings.fb.api_url

    def get_account_info(self, token: str) -> GetAccountInfoResponseModel:
        """
        Wraps https://firebase.google.com/docs/reference/rest/auth#section-get-account-info

        Args:
            token (str): The Firebase ID token of the account.

        Returns:
            dict: The account associated with the given Firebase ID token.
        """
        url = f"{self.base_url}/accounts:lookup"
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json={"idToken": token},
        )

        expected_status = status.HTTP_200_OK

        return GetAccountInfoResponseModel(
            **check_response(response, expected_status, url)
        )

    def sign_in_with_email_and_password(
        self, email: str, password: str
    ) -> SignInWithEmailPasswordResponseModel:
        """
        Wraps https://firebase.google.com/docs/reference/rest/auth#section-sign-in-email-password

        Args:
            email (str): The email the user is signing in with.
            password (str): The password for the account.

        Returns:
            dict: A dictionary containing the token and other info.
        """
        url = f"{self.base_url}/accounts:signInWithPassword"
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )

        expected_status = status.HTTP_200_OK

        return SignInWithEmailPasswordResponseModel(
            **check_response(response, expected_status, url)
        )

    def send_email_verification(
        self, token: str
    ) -> SendEmailVerificationResponseModel:
        """
        Wraps https://firebase.google.com/docs/reference/rest/auth#section-send-email-verification

        Args:
            token (str): The Firebase ID token of the user to verify.

        Returns:
            dict: A dict containing the email of the account.
        """
        url = f"{self.base_url}/accounts:sendOobCode?key={self.api_key}"
        response = httpx.post(
            url=url, json={"idToken": token, "requestType": "VERIFY_EMAIL"}
        )

        expected_status = status.HTTP_200_OK

        return SendEmailVerificationResponseModel(
            **check_response(response, expected_status, url)
        )

    def send_password_reset_email(
        self, email: str
    ) -> SendPasswordResetEmailResponseModel:
        """
        Wraps https://firebase.google.com/docs/reference/rest/auth#section-send-password-reset-email

        Args:
            email (str): User's email address.

        Returns:
            dict: A dict containing the user's email address.
        """
        url = f"{self.base_url}/accounts:sendOobCode"
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json={"email": email, "requestType": "PASSWORD_RESET"},
        )

        expected_status = status.HTTP_200_OK

        return SendPasswordResetEmailResponseModel(
            **check_response(response, expected_status, url)
        )

    def verify_password_reset_code(
        self, oob_code: str
    ) -> VerifyPasswordResetResponseModel:
        url = f"{self.base_url}/accounts:resetPassword"
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json={"oobCode": oob_code},
        )

        expected_status = status.HTTP_200_OK

        return VerifyPasswordResetResponseModel(
            **check_response(response, expected_status, url)
        )

    def update(
        self,
        oob_code: str | None = None,
        id_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        display_name: str | None = None,
        photo_url: str | None = None,
        delete_attribute: list[str] | None = None,
        delete_provider: list[str] | None = None,
        return_secure_token: bool = False,
    ) -> UpdateResponseModel:
        """
        Wraps requests to the `accounts:update` endpoint.

        This covers:
         - 'Confirm email verification'
         - 'Change email'
         - 'Change password'
         - 'Update profile'
         - 'Link with email/password'
         - 'Unlink provider'

        Args:
            oob_code (str | None, optional): The action code sent to
                user's email for email verification. Defaults to None.
            id_token (str | None, optional): A Firebase Auth ID token for
                the user. Defaults to None.
            email (str | None, optional): The user's new email. Defaults
                to None.
            password (str | None, optional): User's new password.
                Defaults to None.
            display_name (str | None, optional): User's new display name.
                Defaults to None.
            photo_url (str | None, optional): User's new photo url.
                Defaults to None.
            delete_attribute (list[str] | None, optional): List of
                attributes to delete, "DISPLAY_NAME" or "PHOTO_URL".
                Defaults to None.
            delete_provider (list[str] | None, optional): The list of
                provider IDs to unlink, eg: 'google.com', 'password',
                etc. Defaults to None.
            return_secure_token (bool, optional): Whether or not to return
                an ID and refresh token. Defaults to False.

        Returns:
            dict: The response payload containing the user's information
                and eventually new ID and refresh tokens.
        """
        url = f"{self.base_url}/accounts:update"
        # construt request
        request: dict = {"returnSecureToken": return_secure_token}
        if oob_code:
            request.update({"oobCode": oob_code})
        else:  # send only oobCode when oobCode present
            if id_token:
                request.update({"idToken": id_token})
            if email:
                request.update({"email": email})
            if password:
                request.update({"password": password})
            if display_name:
                request.update({"displayName": display_name})
            if photo_url:
                request.update({"photoUrl": photo_url})
            if delete_attribute:
                request.update({"deleteAttribute": delete_attribute})
            if delete_provider:
                request.update({"deleteProvider": delete_provider})

        # send request
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json=request,
        )

        expected_status = status.HTTP_200_OK

        return UpdateResponseModel(
            **check_response(response, expected_status, url)
        )

    def get_id_token_from_refresh_token(self, refresh_token: str) -> dict:
        """
        Wraps requests to https://securetoken.googleapis.com/v1/token


        """
        base_url = (
            "https://securetoken.googleapis.com/v1"
            if not settings.fb.auth_emulator_host
            else (
                f"http://{settings.fb.auth_emulator_host}"
                "/securetoken.googleapis.com/v1"
            )
        )
        # we are not using `self.base_url` here because the base url
        # for this request is different
        url = f"{base_url}/token"
        response = httpx.post(
            url=url,
            params={"key": self.api_key},
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

        expected_status = status.HTTP_200_OK

        return check_response(response, expected_status, url)
