import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.core.db import validate_exactly_one


def test_health_endpoint():
    response = Client().get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mycelium-api"}


class _Row:
    def __init__(self, **ids):
        self.__dict__.update(ids)


def test_validate_exactly_one_accepts_single_field():
    validate_exactly_one(_Row(a_id=1, b_id=None), "a", "b")


@pytest.mark.parametrize("ids", [{"a_id": None, "b_id": None}, {"a_id": 1, "b_id": 2}])
def test_validate_exactly_one_rejects_zero_or_many(ids):
    with pytest.raises(ValidationError):
        validate_exactly_one(_Row(**ids), "a", "b")
