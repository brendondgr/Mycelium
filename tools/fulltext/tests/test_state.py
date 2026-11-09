"""The worker-shared state: Redis switch-offs/throttles, database verdicts."""

import fnmatch
import time

import pytest
from django.test import override_settings

from tools.fulltext import state as S
from tools.fulltext.engine.fetcher import Fetcher
from tools.fulltext.models import SourceVerdict


class FakeRedis:
    """The handful of Redis commands SharedState uses, with real expiry."""

    def __init__(self):
        self.data = {}  # key -> (value, expires_at or None)

    def _live(self, key):
        v = self.data.get(key)
        if v and v[1] is not None and v[1] <= time.time():
            del self.data[key]
            return None
        return v

    def set(self, key, value, nx=False, px=None):
        if nx and self._live(key):
            return None
        self.data[key] = (str(value).encode(), time.time() + px / 1000 if px else None)
        return True

    def get(self, key):
        v = self._live(key)
        return v[0] if v else None

    def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)

    def incr(self, key):
        v = self._live(key)
        n = int(v[0]) + 1 if v else 1
        self.data[key] = (str(n).encode(), v[1] if v else None)
        return n

    def expire(self, key, seconds):
        v = self._live(key)
        if v:
            self.data[key] = (v[0], time.time() + seconds)

    def pttl(self, key):
        v = self._live(key)
        return int((v[1] - time.time()) * 1000) if v and v[1] else -1

    def scan_iter(self, match):
        return [
            k.encode()
            for k in list(self.data)
            if fnmatch.fnmatch(k, match) and self._live(k)
        ]


def test_two_workers_see_one_switch_off_until_it_expires(tmp_path):
    redis = FakeRedis()
    a = Fetcher({}, tmp_path, state=S.SharedState(redis), disable_ttl=0.2)
    b = Fetcher({}, tmp_path, state=S.SharedState(redis), disable_ttl=0.2)
    a._disable("core", "provider quota exhausted (HTTP 500)")
    assert b.disabled["core"].startswith("provider quota")
    time.sleep(0.25)
    assert "core" not in b.disabled


def test_strikes_are_counted_across_workers_and_cleared_by_a_success():
    redis = FakeRedis()
    one, two = S.SharedState(redis), S.SharedState(redis)
    assert one.strike("wiley") == 1 and two.strike("wiley") == 2
    one.clear_strikes("wiley")
    assert two.strike("wiley") == 1


def test_the_throttle_spaces_requests_across_workers():
    redis = FakeRedis()
    one, two = S.SharedState(redis), S.SharedState(redis)
    t = time.time()
    one.wait_turn("arxiv", 0.2)
    two.wait_turn("arxiv", 0.2)
    assert time.time() - t >= 0.19
    t = time.time()
    one.wait_turn("pmc", 0)  # no interval: never waits
    assert time.time() - t < 0.05


@pytest.mark.django_db
def test_verdicts_live_in_the_database_and_are_shared():
    one, two = S.SharedState(FakeRedis()), S.LocalState()
    one.remember("10.1/x", "unpaywall", "closed")
    one.remember("10.1/x", "unpaywall", "closed")  # idempotent
    assert two.remembered("10.1/x", "unpaywall") == "closed"
    assert SourceVerdict.objects.count() == 1
    assert one.remembered("10.1/x", "core") is None


@override_settings(FULLTEXT_REDIS_URL="redis://127.0.0.1:1/0")
def test_an_unreachable_redis_degrades_to_this_process():
    assert isinstance(S.shared_state(), S.LocalState)


@override_settings(FULLTEXT_REDIS_URL="", CELERY_BROKER_URL="redis://redis:6379/0")
def test_the_default_redis_is_the_brokers_host_on_its_own_database():
    assert S.redis_url() == "redis://redis:6379/7"
