# Release stabilization profile side effects v1

- Статус: Phase 0 side-effect baseline
- Дата: 2026-05-27
- Родительский документ: `docs/development/release-stabilization-program-v1.md`
- Назначение: сделать цену каждого release-gates/autopsy профиля явной до rollout controlled mutators.

---

## 1. Side-effect classes

| Class | Meaning | Default policy |
|---|---|---|
| `read-only` | Inspect files, versions, config, ports or metadata without writing. | Allowed. |
| `write-run-artifacts` | Write `.dev-bootstrap/runs/**`, logs, reports, temporary diagnostic files. | Allowed for diagnostic profiles. |
| `write-dependencies` | Run package manager or create dependency marker files. | Explicit profile/flag required. |
| `network-download` | Download packages, Playwright browsers or remote assets. | Explicit consent required. |
| `write-env-files` | Create or modify `.env*` files. | Explicit consent and backup required. |
| `write-database` | Execute migrations or API smoke that writes rows. | Safe DB proof required. |
| `create-database` | Create per-run or managed DB. | Explicit managed DB profile/flag required. |
| `drop-database` | Drop managed DB after run. | Retention policy required. |
| `start-process` | Start backend/frontend or helper process. | Allowed only when process ownership is recorded. |
| `stop-owned-process` | Stop a process started by current workspace/tool run. | Allowed with PID/identity proof. |
| `stop-foreign-process` | Stop process not started by current workspace/tool run. | Forbidden by default. |
| `write-project-files` | Modify tracked source/docs/config files. | Only through devctl patch application, not release-gates/autopsy runtime. |

---

## 2. Profile matrix

| Profile | Purpose | Allowed side effects | Forbidden by default | Release meaning |
|---|---|---|---|---|
| `diagnostic` | Classify environment and prerequisites. | `read-only`, `write-run-artifacts` | deps install, DB writes, process mutation, network download | Diagnostic value only; no product confidence. |
| `prepared-local` | Use existing local deps and explicit DB. | `read-only`, `write-run-artifacts`, `start-process`, `stop-owned-process`, optional `write-database` only with safe target | create/drop DB, network browser install, stop foreign process | Partial local confidence. |
| `isolated-db` | Fresh managed DB checks. | `read-only`, `write-run-artifacts`, `create-database`, `write-database`, retention-controlled `drop-database` | dependency install unless separately allowed, stop foreign process | DB/migration confidence. |
| `managed-runtime` | Managed backend/frontend dynamic ports. | `read-only`, `write-run-artifacts`, `start-process`, `stop-owned-process`, optional safe `write-database` | fixed-port process killing, network download unless separately allowed | Runtime confidence. |
| `full-local-release` | Maximum local release signal. | All non-destructive classes with explicit consent; DB/deps/browser/process side effects only as expanded plan shows | `stop-foreign-process`, unguarded env overwrite, production-looking DB URL | Beta-candidate input only if evidence is complete. |
| `clean-machine-dry` | Verify archive/checkout shape. | `read-only`, `write-run-artifacts`, sandbox copy creation | network/deps/runtime/DB writes | Portability signal, not runtime proof. |
| `clean-machine-runtime` | Opt-in clean runtime rehearsal. | sandbox deps/runtime/DB/process side effects with consent and retention policy | mutation outside sandbox or safe DB target | Strong portability signal. |

---

## 3. Consent summary requirements

Every profile that allows a side effect beyond `read-only` and `write-run-artifacts` must produce a human-readable consent summary before execution or inside dry-run output.

Required fields:

```text
profile
expanded flags
allowed side effects
denied side effects
database target and safety proof
process ports and ownership strategy
dependency/network actions
retention policy
cleanup command or rollback note
```

For dry-run profiles the summary must say explicitly:

```text
No DB/dependency/network/process mutation will be performed in this run.
```

---

## 4. DB safety rules

A DB-writing gate is allowed only when at least one condition is true:

1. `TEST_DATABASE_URL` is explicit and not production-looking.
2. Managed DB was created for the run.
3. A documented admin/maintenance connection created a safe per-run DB.
4. The profile is dry-run and no write occurs.

Blocked by default:

- production-looking host/name/user combinations;
- missing target proof;
- destructive cleanup without retention policy;
- fallback from failed managed DB creation to dirty shared dev DB.

---

## 5. Process safety rules

A runtime profile must distinguish:

```text
owned process
foreign process
stale pid file
port occupied but unknown owner
process started then died
readiness unavailable
```

Allowed cleanup:

- stop process started by this run;
- remove stale runtime state file after identity check;
- leave foreign process untouched and classify as `REL-PORT` / `REL-PROC`.

Forbidden cleanup:

- killing a foreign process to make a gate green;
- hiding a port conflict as generic frontend/backend failure.

---

## 6. Patch/release boundary

`devctl` patch application may modify project files because that is the explicit patch workflow.

`devbootstrap release-gates` and future autopsy profiles should not mutate tracked project files. They may only create run artifacts unless the profile explicitly allows a controlled side effect such as dependency installation, managed DB, or managed runtime.

This keeps release-gates from becoming an invisible fixer and preserves the rule:

```text
Diagnostics produce evidence.
Patches change the project.
```

---

## 7. Phase 4 controlled-mutators artifact

Phase 4 makes the consent summary enforceable as bundle evidence. Every `release-gates` run now includes:

- `release-gates-consent.json` / `.md` for expanded profile flags and allowed/denied side effects;
- `remediation/controlled-mutators.json` / `.md` for enabled mutators, actual status, cleanup, rollback and evidence paths.

The default `diagnostic` profile must keep DB/dependency/network/process/sandbox mutators disabled. More invasive profiles are acceptable only when the controlled-mutators ledger reports `unsafeMutationCount == 0` and `cleanupCoverage == "ok"`.
