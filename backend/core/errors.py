from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from backend.core.logging import get_logger

logger = get_logger("ThothErrorHandler")

class ThothBaseException(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class AuthenticationError(ThothBaseException):
    def __init__(self, message: str = "Invalid or missing credentials", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="UNAUTHORIZED", status_code=status.HTTP_401_UNAUTHORIZED, details=details)

class RateLimitExceededError(ThothBaseException):
    def __init__(self, message: str = "Rate limit quota exceeded", retry_after: float = 60.0):
        super().__init__(message=message, code="RATE_LIMITED", status_code=status.HTTP_429_TOO_MANY_REQUESTS, details={"retry_after": retry_after})

class ResourceNotFoundError(ThothBaseException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(message=f"{resource} '{identifier}' not found", code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND)

class ResearchPipelineError(ThothBaseException):
    def __init__(self, message: str, stage: str = "orchestration", details: Optional[Dict[str, Any]] = None):
        det = details or {}
        det["stage"] = stage
        super().__init__(message=message, code="PIPELINE_ERROR", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, details=det)

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ThothBaseException)
    async def handle_thoth_exception(request: Request, exc: ThothBaseException):
        logger.warning(f"Handled application exception [{exc.code}]: {exc.message} (Path: {request.url.path})")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception):
        logger.error(f"Unhandled server error on {request.url.path}: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred during research execution.",
                "details": {"exception": type(exc).__name__}
            }
        )
