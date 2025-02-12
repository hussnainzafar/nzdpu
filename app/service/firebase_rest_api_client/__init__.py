"""Firebase REST API client."""

from .client import FirebaseRESTAPIClient
from .errors import (
    FirebaseRESTAPIClientException,
    UnhandledFirebaseRESTAPIClientException,
)

__all__ = (
    "FirebaseRESTAPIClient",
    "FirebaseRESTAPIClientException",
    "UnhandledFirebaseRESTAPIClientException",
)
