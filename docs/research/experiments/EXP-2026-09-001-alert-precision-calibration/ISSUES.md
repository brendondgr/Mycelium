# Issues

- `code.dirty: true` is correct as recorded: the folder was created in the same
  change that shipped the matchers and the alert engine it will measure, so the
  tree held uncommitted work at scaffold time. The commit named in the manifest
  is the one that shipped both.
- **Not run.** This is a protocol, not a result. The shadow run needs four weeks
  of live alerts and has not started; `status` stays `planned` until it does.
