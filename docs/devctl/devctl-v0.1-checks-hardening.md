# devctl v0.1 — checks hardening

`devctl` v0.1 keeps the same minimal UX:

```bash
python tools/devctl.py status
python tools/devctl.py start
```

The goal of this patch is to make the first real conveyor run safer and easier to inspect.

## What changed

- `status` now prints the `devctl` version.
- `status` shows a bootstrap/update hint when both `tools/` and `docs/devctl/` are dirty.
- `requiredCommands` errors now include the check that required the missing tool.
- non-empty `setup` and `services` sections are rejected in v0.1 instead of being silently ignored.
- commit trailers now use `Devctl-Version: 0.1`.

## What stays intentionally out of scope

v0.1 still does not:

- auto-install dependencies;
- run `npm install` / `npx playwright install` automatically;
- auto-start backend/frontend services;
- perform rollback after failed checks;
- merge/rebase/pull diverged branches automatically.

## Smoke check for this patch

This patch is designed to be applied by `devctl start` itself.

The manifest checks are intentionally lightweight:

```bash
python -m py_compile tools/devctl.py
python tools/devctl.py status
```

They validate that the updated script is syntactically valid and that the `status` command still runs while the patch is applied but not yet committed.

## Expected successful flow

1. Put this patch zip into `p2p_workspace/patches/`.
2. Make sure the current bootstrap devctl version is already committed and pushed.
3. Run:

```bash
python tools/devctl.py status
python tools/devctl.py start
```

If checks pass, `devctl` should create a pre archive, apply the patch, run checks, create a post archive, commit with patch trailers, push, update `.devctl/state.json`, and write `report.md`.
