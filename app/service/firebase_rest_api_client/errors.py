"""Firebase REST API errors."""

from enum import Enum

from fastapi import status
from httpx import Response


class FirebaseRESTAPIClientException(Exception):
    """
    Exception for handled Firebase REST API error codes.
    """

    def __init__(self, status_code, detail):
        self.detail = detail
        self.status_code = status_code


class UnhandledFirebaseRESTAPIClientException(Exception):
    """
    Exception for unhandled Firebase REST API error codes.
    """

    def __init__(self, message: str, status_code: int, url: str):
        """
        Inits the instance of this class.
        """
        self.message = message
        self.status_code = status_code
        self.url = url


class FirebaseRESTAPIErrorCodes(str, Enum):
    """
    Enumerator for Firebase REST API error codes.
    """

    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_ID_TOKEN = "INVALID_ID_TOKEN"
    INVALID_REFRESH_TOKEN = "INVALID_REFRESH_TOKEN"
    INVALID_GRANT_TYPE = "INVALID_GRANT_TYPE"
    MISSING_REFRESH_TOKEN = "MISSING_REFRESH_TOKEN"
    CREDENTIAL_TOO_OLD_LOGIN_AGAIN = "CREDENTIAL_TOO_OLD_LOGIN_AGAIN"
    EMAIL_NOT_FOUND = "EMAIL_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    EMAIL_EXISTS = "EMAIL_EXISTS"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    TOO_MANY_ATTEMPTS_TRY_LATER = "TOO_MANY_ATTEMPTS_TRY_LATER"
    USER_DISABLED = "USER_DISABLED"
    EXPIRED_OOB_CODE = "EXPIRED_OOB_CODE"
    INVALID_OOB_CODE = "INVALID_OOB_CODE"
    INVALID_LOGIN_CREDENTIALS = "INVALID_LOGIN_CREDENTIALS"


def get_error(response: Response, message: str, url: str):
    match message:
        case (
            FirebaseRESTAPIErrorCodes.TOKEN_EXPIRED
            | FirebaseRESTAPIErrorCodes.INVALID_ID_TOKEN
            | FirebaseRESTAPIErrorCodes.CREDENTIAL_TOO_OLD_LOGIN_AGAIN
        ):
            status_code = status.HTTP_401_UNAUTHORIZED
            detail = {
                "token": (
                    "The user's credential is no longer valid."
                    " The user must sign in again."
                )
            }
        case (
            FirebaseRESTAPIErrorCodes.EMAIL_NOT_FOUND
            | FirebaseRESTAPIErrorCodes.USER_NOT_FOUND
        ):
            status_code = status.HTTP_404_NOT_FOUND
            detail = {
                "email": (
                    "There is no user record corresponding to this"
                    " identifier. The user may have been deleted."
                )
            }
        case FirebaseRESTAPIErrorCodes.INVALID_PASSWORD:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "password": "Incorrect password. Please try again or reset your password."
            }
        case FirebaseRESTAPIErrorCodes.INVALID_LOGIN_CREDENTIALS:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "password": "Incorrect email or password. Please try again or reset your password."
            }
        case FirebaseRESTAPIErrorCodes.WEAK_PASSWORD:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "password": "The password must be 6 characters long or more."
            }
        case FirebaseRESTAPIErrorCodes.EMAIL_EXISTS:
            status_code = status.HTTP_409_CONFLICT
            detail = {
                "email": (
                    "This email is already associated with another account."
                    " Please check spelling, or log in with this email."
                )
            }
        case FirebaseRESTAPIErrorCodes.OPERATION_NOT_ALLOWED:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "password": "Password sign-in is disabled for this project."
            }
        case FirebaseRESTAPIErrorCodes.USER_DISABLED:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "global": (
                    "The user account has been disabled by an administrator."
                )
            }
        case FirebaseRESTAPIErrorCodes.EXPIRED_OOB_CODE:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {"oobCode": "The action code has expired."}
        case FirebaseRESTAPIErrorCodes.INVALID_OOB_CODE:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {
                "oobCode": (
                    "The action code is invalid. This can happen if"
                    " the code is malformed, expired, or has already"
                    " been used."
                )
            }
        case FirebaseRESTAPIErrorCodes.INVALID_REFRESH_TOKEN:
            status_code = status.HTTP_401_UNAUTHORIZED
            detail = {"refresh_token": "An invalid refresh token is provided."}
        case FirebaseRESTAPIErrorCodes.INVALID_GRANT_TYPE:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {"grant_type": "The grant type specified is invalid."}
        case FirebaseRESTAPIErrorCodes.MISSING_REFRESH_TOKEN:
            status_code = status.HTTP_400_BAD_REQUEST
            detail = {"refresh_token": "No refresh token provided."}
        case (
            _
        ) if FirebaseRESTAPIErrorCodes.TOO_MANY_ATTEMPTS_TRY_LATER in message:
            # Currently there is a Firebase bug that makes the message for this error different from other errors.
            status_code = status.HTTP_401_UNAUTHORIZED
            detail = {
                "password": (
                    "Your account has been temporarily locked due to too many failed login attempts. "
                    "Please try again later, or reset your password."
                ),
                "blocked_by_firebase": True,
            }
        case _:
            # unhandled cases have a different error format
            # attempting to provide more information
            raise UnhandledFirebaseRESTAPIClientException(
                status_code=response.status_code,
                message=response.json(),
                url=url,
            )
    return FirebaseRESTAPIClientException(
        status_code=status_code, detail=detail
    )
