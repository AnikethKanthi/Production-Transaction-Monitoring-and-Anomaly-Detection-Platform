from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.repositories.transactions import TransactionRepository
from app.db.session import get_session
from app.services.transaction_service import TransactionService

DatabaseSession = Annotated[Session, Depends(get_session, scope="function")]


def get_transaction_service(session: DatabaseSession) -> TransactionService:
    return TransactionService(TransactionRepository(session))


TransactionServiceDependency = Annotated[TransactionService, Depends(get_transaction_service)]
