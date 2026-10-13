from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.transaction_service import TransactionNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
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
