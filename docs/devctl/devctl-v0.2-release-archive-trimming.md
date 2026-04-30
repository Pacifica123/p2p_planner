# devctl v0.2 — release archive trimming

`devctl` v0.2 keeps the same commands:

```bash
python tools/devctl.py status
python tools/devctl.py start
```

The goal of this patch is to keep `archives/` useful as a lightweight project snapshot store even when the project contains a prepared `release/` directory.

## Problem

The project-level `release/` directory is useful and should remain in the working tree, but it can contain heavy generated payloads:

- nested release `.zip` files;
- Windows backend executables such as `p2p-planner-backend.exe`.

When `devctl start` creates pre/post/failed snapshots, copying those payloads into every archive quickly inflates archive size by many megabytes.

## What changed

By default, `devctl` still includes the `release/` directory structure in snapshot archives, but omits heavy release payload files:

- `release/**/*.zip`
- `release/**/*.exe`

For transparency, `devctl` writes small placeholder text files into the archive:

- `тут_был_zip_архив.txt` next to omitted release zip files;
- `тут_был_экзешник.txt` next to omitted executable files.

The placeholders explain that the payload was intentionally skipped, list the omitted file path and size, and clarify that nothing was deleted from the working copy.

## Escape hatch

If a future patch truly needs full release payloads inside devctl snapshots, its manifest may opt out of trimming:

```json
{
  "archive": {
    "includeReleasePayloads": true
  }
}
```

This should be rare. Normal development snapshots should stay lightweight.

## What stays intentionally unchanged

- `release/` is not excluded wholesale.
- Source files, docs, configs, migrations, frontend/backend code and release metadata are still archived.
- Existing archive exclusions still apply: `.git/`, `target/`, `node_modules/`, `dist/`, `build/`, `.env`, local databases and similar generated/local files.
- Real release artifacts are not removed from the project tree; they are only omitted from devctl snapshot zip files.

## Smoke check for this patch

The lightweight validation for this patch is:

```bash
python -m py_compile tools/devctl.py
python tools/devctl.py status
```

A manual archive check should show that a project containing `release/*.zip` and `release/**/*.exe` produces a much smaller snapshot containing placeholder text files instead of those payloads.
