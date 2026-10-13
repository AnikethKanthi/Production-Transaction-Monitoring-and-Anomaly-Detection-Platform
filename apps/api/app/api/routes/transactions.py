from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import TransactionServiceDependency
from app.schemas.transaction import (
    ErrorResponse,
    PaginationMeta,
    TransactionCreate,
    TransactionFilters,
    TransactionList,
    TransactionRead,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

not_found_response = {
    "model": ErrorResponse,
    "description": "Transaction not found",
    "content": {
        "application/json": {
            "example": {
                "error": {
                    "code": "transaction_not_found",
                    "message": "Transaction 2b32f5ce-13d1-45d8-8aac-d9867bd6ea21 was not found",
                }
            }
        }
    },
}
validation_response = {"model": ErrorResponse, "description": "Request validation failed"}


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: validation_response},
    summary="Create a transaction",
)
def create_transaction(
    payload: TransactionCreate, service: TransactionServiceDependency
) -> TransactionRead:
    return TransactionRead.model_validate(service.create(payload))


@router.get(
    "",
    response_model=TransactionList,
    responses={422: validation_response},
    summary="List and filter transactions",
)
def list_transactions(
    filters: Annotated[TransactionFilters, Query()],
    service: TransactionServiceDependency,
) -> TransactionList:
    items, total = service.list(**filters.model_dump())
    return TransactionList(
        items=[TransactionRead.model_validate(item) for item in items],
        pagination=PaginationMeta(limit=filters.limit, offset=filters.offset, total=total),
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionRead,
    responses={404: not_found_response, 422: validation_response},
    summary="Get transaction details",
)
def get_transaction(
    transaction_id: Annotated[UUID, Path(description="Transaction UUID")],
    service: TransactionServiceDependency,
) -> TransactionRead:
    return TransactionRead.model_validate(service.get(transaction_id))
