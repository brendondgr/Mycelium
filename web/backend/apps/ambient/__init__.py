"""The ambient evidence ledger — what Mylo understood from the lab's own talk.

One platform-independent record of *observations*: what was said, by whom, about
what, when, and with what kind of force. Every adapter (Discord first, then
Slack, Teams, transcripts) writes this shape and nothing else; every later stage
— attribution, extraction, deliberation, confirmation, reports — reads it.

Two promises are structural here rather than merely intended:

* **Messages are not saved.** Raw text lives only in a Redis buffer with a TTL
  measured in hours (:mod:`.buffer`) and is deleted explicitly once a window has
  been read. Postgres holds no message body and no quote — only Mylo's own short
  account of what was said, with the dates and the kind of place it came up.
* **Nobody uninvolved is recorded.** Eligibility (:mod:`.eligibility`) is
  resolved *before* anything is buffered, so a server member without a linked,
  paid, opted-in Mycelium account leaves no trace at all.

Nothing in this app touches a profile or a project. It is the evidence, not the
conclusion.
"""
