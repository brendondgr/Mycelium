# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD RYZEN AI MAX+ 395 (32 threads) |
| RAM | 121 GB |
| GPU | none (no model is called; conversion is pypdf / ElementTree / BeautifulSoup) |
| Python | 3.13 (uv-managed) |
| Lockfile | web/backend/uv.lock |
| Container | none — run on the host against the compose Postgres (port 11450), read-only |
| Total wall clock | 1,119.7 s for the fetch (about 19 minutes), plus about 5 s for `check_ids.py` |

## Where the time went

Network-bound. The per-source throttles set the pace, and CORE without a key is
the slowest (one request every 6.5 s); four workers share each source's
throttle, so more workers would not help.

## Anything about the hardware that affects the claim

Only the network: requests went out from a home connection, not a campus one.
With no publisher keys configured that does not change which sources answered.
