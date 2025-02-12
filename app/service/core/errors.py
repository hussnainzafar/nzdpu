"""
SubmissionManager errors
"""

from enum import Enum


class SubmissionError(str, Enum):
    """
    Submission errors
    """

    SUBMISSION_CANT_READ = "User not allowed to read this submission."
    SUBMISSION_CANT_WRITE = "User not allowed to write this submission."
    SUBMISSION_NO_DATE = "Missing or invalid reporting date."
    SUBMISSION_NOT_EMPTY = (
        "Submission cannot be updated because it is not empty."
    )
    SUBMISSION_ALREADY_EXISTS = (
        "A submission already exists for this company and reporting year."
    )
    SUBMISSION_REVISION_CANT_WRITE = (
        "User not allowed to write this submission revision."
    )
    SUBMISSION_CANT_EDIT = (
        "Could not edit the current submission: it is not checked out."
    )
    SUBMISSION_USER_CANT_EDIT = (
        "Could not edit the current submission: it has been checked out from"
        " another user."
    )
    SUBMISSION_CANT_CHECK_OUT = (
        "Could not perform request: submission is already checked out."
    )
    SUBMISSION_CHECKED_OUT_BY_ANOTHER_USER = (
        "Not enough rights to check out the current (already checked out)"
        " submission."
    )
    SUBMISSION_CANT_CLEAR_ANOTHER_USER = (
        "Could not clear edit mode for current submission: it has been checked"
        " out by another user."
    )
    SUBMISSION_CANT_CLEAR_PERMISSION = (
        "Could not clear edit mode for current submission: not enough rights."
    )
    SUBMISSION_NOT_FOUND_MESSAGE = "Submission object not found."
    SUBMISSION_PREVIOUS_ACTIVE_NOT_FOUND_MESSAGE = (
        "Previous active Submission object not found."
    )
    SUBMISSION_ACTIVE_NOT_FOUND_MESSAGE = (
        "There is no active Submission object found."
    )
