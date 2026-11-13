# EXP-2026-11-014 — Issues

- 2026-11-12 ~23:53: a harness smoke test (levels 1–2, joint and single
  shapes, one pass) was started while the nightly run was still using the
  decision server, against the protocol's "run alone" rule, and stopped by
  hand after about two minutes. Its partial output is not used and not kept in
  this folder. The timed runs start only after the nightly finished.
- 2026-11-13 01:03: **the decision server crashed during r1** at 32 requests in
  flight on the real states (CUDA out of memory; 80 of 113 requests failed;
  restarted by its service manager, healthy at 01:05). Trimmed log in
  `logs/crash_r1.txt`. The stop rule ended r1, so its `single`, `choice` and
  `synthetic` shapes never ran; Amendment 2 replaced them with r1b and r1s at
  safe levels. The level was not retried.
- r1's `/health` read after the stop shows the server down (it was
  restarting); r1b's first read shows the counters reset (uptime 352 s).
- The joint-vs-single comparison pairs r1's first clean `joint` pass at 1 in
  flight with r1b's first `single` pass at 1 in flight: same bodies, the server
  restarted in between (same weights and settings).
