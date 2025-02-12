"""Validation Exception Handler."""

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    validation hanlding method
    """
    error_messages = []
    for error in exc.errors():
        loc = error["loc"]
        msg = error["msg"]
        error_msg = {
            "field": ".".join([str(el) for el in loc]),
            "message": msg,
        }
        error_messages.append(error_msg)

    response_content = {
        "error": "Validation Error",
        "detail": error_messages,
    }

    return JSONResponse(
        status_code=422,  # Unprocessable Entity
        content=response_content,
    )
