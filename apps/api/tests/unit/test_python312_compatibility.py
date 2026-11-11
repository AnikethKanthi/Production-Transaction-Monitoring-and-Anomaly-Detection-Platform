from app.db.repositories.alerts import AlertRepository


def test_repository_annotations_are_deferred_for_python_312() -> None:
    assert AlertRepository.audit.__annotations__["return"] == "list[AlertAudit]"
