from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app.core.config import Settings
from app.services.alert_service import AlertWorkflowError
from app.services.transaction_service import TransactionNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    origins = Settings().cors_origins

    @app.exception_handler(Exception)
    async def unexpected_failure(request: Request, _error: Exception):
        # ServerErrorMiddleware sits outside user middleware; apply headers here too.
        headers = {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
        if correlation := getattr(request.state, "correlation_id", None):
            headers["X-Correlation-ID"] = correlation
        if request.url.scheme == "https":
            headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.headers.get("origin") in origins:
            headers["Access-Control-Allow-Origin"] = request.headers["origin"]
            headers["Vary"] = "Origin"
            headers["Access-Control-Expose-Headers"] = "X-Correlation-ID"
        return JSONResponse(
            status_code=500,
            headers=headers,
            content={
                "error": {"code": "internal_error", "message": "The request could not be completed"}
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": f"http_{error.status_code}", "message": str(error.detail)}},
            headers=error.headers,
        )

    @app.exception_handler(IntegrityError)
    async def conflict(_request: Request, _error: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "data_conflict",
                    "message": "The request conflicts with stored data",
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(RedisError)
    async def dependency_failure(_request: Request, _error: Exception):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "dependency_unavailable",
                    "message": "A required service is temporarily unavailable",
                }
            },
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(AlertWorkflowError)
    async def alert_workflow_error(_request: Request, error: AlertWorkflowError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(TransactionNotFoundError)
    async def transaction_not_found(
        _request: Request, error: TransactionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "transaction_not_found",
                    "message": f"Transaction {error.transaction_id} was not found",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": details,
                }
            },
        )
