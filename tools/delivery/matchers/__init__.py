"""Deterministic project matchers — the half of a project-aware report no model writes.

A report that says "this paper overlaps your contribution" is making two very
different kinds of claim at once. *That the paper says X* is a reading, and a
model does it. *That X lands 35 days before your milestone, which is inside your
buffer, so the venue fits* is arithmetic, and a model doing arithmetic is a model
inventing numbers with a confident tone.

So the two are separated. Everything in this package is computed in code from
stored rows: dates, day counts, time-zone conversions, overlaps, which blocker a
dataset closes, which papers the reader already has. The model is handed the
result and asked to write about it, and the report contract (plan H2) removes any
sentence carrying a number the matchers did not produce.

The matchers are cheap and re-runnable. Changing a project's deadline buffer
recomputes every timeline status with zero model calls, which is the property that
makes the buffer adjustable at all.
"""
