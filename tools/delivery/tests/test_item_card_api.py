"""``GET /api/items/<id>/``: one corpus item as its feed's card.

What a link opens when the item is not in the reader's loaded feed (Mylo cites
anything in the corpus). Reads rows directly, so it runs without pgvector.
"""

import uuid

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    user = User.objects.create_user("reader", password="pw")
    api = APIClient()
    api.force_authenticate(user)
    api.user = user
    return api


def _item(kind, title, **meta):
    return ContentItem.objects.create(
        type=kind,
        source="legacy",
        external_id=title,
        source_url=f"https://example.org/{title}",
        metadata={"title": title, "name": title, **meta},
    )


@pytest.mark.parametrize(
    "kind",
    [
        ContentItem.Type.GRANT,
        ContentItem.Type.FELLOWSHIP,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.PAPER,
    ],
)
def test_an_unscored_item_comes_back_as_its_feeds_card(client, kind):
    item = _item(kind, f"Unscored {kind}")
    resp = client.get(f"/api/items/{item.pk}/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["area"] == kind
    assert body["card"]["content_id"] == str(item.pk)
    assert body["card"]["title"] == f"Unscored {kind}"


def test_the_readers_own_score_is_used(client):
    item = _item(ContentItem.Type.GRANT, "Scored grant", sponsor="NSF")
    RelevanceScore.objects.create(
        content=item, target_user=client.user, score=0.42, signals={}
    )
    body = client.get(f"/api/items/{item.pk}").json()
    assert body["card"]["score"] == pytest.approx(0.42)


def test_unknown_item_is_404(client):
    assert client.get(f"/api/items/{uuid.uuid4()}/").status_code == 404


def test_signed_out_is_refused():
    item = _item(ContentItem.Type.GRANT, "Private")
    assert APIClient().get(f"/api/items/{item.pk}/").status_code in (401, 403)
