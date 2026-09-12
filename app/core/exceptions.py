from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    code = "app_error"
    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class PollClosedError(AppError):
    code = "poll_closed"
    status_code = 409


class AlreadyAnsweredError(AppError):
    code = "already_answered"
    status_code = 409


class InvalidOptionError(AppError):
    code = "invalid_option"
    status_code = 422


class RateLimitedError(AppError):
    code = "rate_limited"
    status_code = 429


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
