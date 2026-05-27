# Release stabilization program v1

- Статус: Canonical strategic execution plan
- Дата: 2026-05-27
- Основание: `docs/development/systemic-release-stabilization-manifesto-v1.md`
- Связанные документы: `docs/dev-bootstrap/devbootstrap-v2-release-gates-plan.md`, `docs/dev-bootstrap/release-gates-test-database.md`, `docs/devctl/devctl-patch-conveyor-spec.md`, `docs/product/v1-execution-roadmap.md`
- Назначение: превратить манифест Deep Release Autopsy в измеримую, проверяемую и безопасно исполнимую программу стабилизации release/dev lifecycle.

---

## 1. Executive summary

Цель этой программы — не «починить очередной запуск», а построить release/dev контур, который системно отвечает на вопросы:

1. что именно было проверено;
2. что не было проверено и осталось unknown;
3. какой слой сломан: продукт, окружение, runtime, БД, frontend launcher, smoke, artifact, devctl/VCS transport;
4. какие доказательства есть;
5. какой failure-mode ID присвоен;
6. какой remediation закрывает класс проблемы;
7. какой probe не даст проблеме вернуться;
8. можно ли повторить результат дважды подряд.

Рабочая формула:

```text
environment/runtime/test failure
-> evidence bundle
-> failure-mode ID
-> Problem Ledger
-> remediation phase
-> regression probe
-> release confidence update
```

Главный итог программы: после нового сбоя команда не спрашивает «что опять сломалось?», а спрашивает:

```text
Какой это failure-mode?
Почему он не был покрыт?
Какой probe теперь станет постоянным?
Как изменился release confidence?
```

---

## 2. Relation to the manifesto

`systemic-release-stabilization-manifesto-v1.md` задает режим мышления: сначала вскрытие release/dev lifecycle, затем карта отказов, затем безопасные ремедиации.

Этот документ задает исполнимую программу:

- supported reality v1;
- метрики;
- failure taxonomy;
- ledgers;
- artifact contract;
- workstreams;
- фазовый roadmap;
- risk register;
- patch-chain;
- acceptance criteria;
- правила ревью будущих патчей.

Манифест отвечает на вопрос **зачем менять процесс**. Этот документ отвечает на вопрос **как именно довести процесс до измеримой готовности**.

---

## 3. Strategic synthesis

Этот план объединяет две комплементарные стратегии:

1. **Autopsy-first strategy** — поддерживаемая область реальности, workstreams, Problem/Probe/Decision ledgers, artifact contract, controlled mutators, provocation matrix.
2. **Release-confidence strategy** — score/class model, hard stop-rules, explicit unknown accounting, current-product grounding, staged patch chain and transport-failure separation.

Итоговая метастратегия:

```text
Не склеивать планы как текст.
А превратить их в один canonical operating system для стабилизации:
- манифест задает философию;
- этот program document задает управление;
- ledgers хранят память;
- release-gates/autopsy производят evidence;
- patch-chain постепенно внедряет capability;
- score/classes показывают, можно ли двигаться к beta.
```

Что оставляем из Autopsy-first strategy:

- явную supported reality v1;
- три ledger-а: Problem, Probe, Decision;
- failure taxonomy and stable IDs;
- workstreams по DB/runtime/Windows/migrations/smoke/browser/artifacts;
- provocation matrix;
- safety rules для controlled mutators;
- bundle contract and redaction/archive policies.

Что оставляем из Release-confidence strategy:

- Release Confidence Score как north-star;
- score classes and thresholds;
- Unknown Ratio and reproducibility metrics;
- stop-rule: no fix without failure-mode ID/probe;
- explicit product-context grounding: core CRUD, appearance, activity ready; auth/labels/checklists/comments не должны маскироваться как ready path;
- transport-only failure separation для `PUSH_FAILED`;
- two-run repeatability as release gate.

Что сознательно отбрасываем или понижаем в приоритете:

- один гигантский «спасительный» кодовый патч;
- любые destructive mutators до read-only diagnostics and consent profiles;
- pass/fail без unknown accounting;
- browser smoke как release proof, если он не ходит в real backend;
- использование shared dev DB для проверки strict default-state assumptions;
- трактовку GitHub/push outage как failure качества патча;
- расползание stabilization lane в обычную продуктовую разработку.

---

## 4. Supported reality v1

Программа не обещает покрыть «все вообще». Она обещает почти исчерпывающе покрыть явную поддерживаемую область.

### 4.1. Workspace and filesystem reality

В область v1 входят:

- devctl workspace layout: `project/`, `patches/`, `archives/`, `.devctl/`;
- clean archive / clean checkout;
- рабочая копия после failed run;
- workspace with spaces in path;
- Windows-style and Linux-style paths;
- наличие/отсутствие `.dev-bootstrap/` runtime state;
- наличие/отсутствие frontend `node_modules`;
- frontend dependency marker drift;
- stale logs and old runtime files;
- archive bloat and generated artifacts;
- docs-only patch and code patch workflows.

### 4.2. OS and shell reality

В область v1 входят:

- Linux shell;
- Windows `cmd.exe`;
- Windows PowerShell;
- npm `.cmd` wrapper;
- direct executable invocation;
- forwarded args through npm scripts;
- direct Vite fallback where wrapper behavior is unreliable.

Каждый запуск внешней команды обязан иметь machine-readable command resolution:

```text
executable path
shell mode
final argv
cwd
env diff
timeout
exit code
classification
```

### 4.3. Toolchain reality

Environment fingerprint должен классифицировать:

- Python;
- Git;
- Rust/Cargo/rustc;
- Node/npm;
- Docker/Compose where relevant;
- PostgreSQL tools: `psql`, `pg_isready`, `createdb`, `dropdb`, `pg_dump`;
- Playwright package and browser binaries.

Состояния инструмента:

```text
available
missing
wrong-version
present-but-unusable
ambiguous-multiple-candidates
not-required-for-profile
```

### 4.4. Runtime reality

В область v1 входят:

- legacy fixed ports `127.0.0.1:18080` and `127.0.0.1:5173`;
- dynamic managed backend/frontend ports;
- stale backend/frontend process;
- occupied port by foreign process;
- owned process still alive;
- process died after start;
- readiness endpoint unavailable;
- frontend API base URL pointing to old backend;
- CORS mismatch between frontend origin and backend allowed origins;
- start/stop/start repeatability.

### 4.5. Database reality

В область v1 входят:

- explicit `TEST_DATABASE_URL`;
- fallback from `DATABASE__URL` / `DATABASE_URL`;
- managed per-run DB;
- admin/maintenance override connection;
- missing PostgreSQL server;
- auth failure;
- missing database;
- wrong owner / insufficient privileges;
- missing `CREATEDB`;
- production-looking URL guard;
- migration disk/applied/embedded mismatch;
- dirty shared dev DB;
- fresh isolated DB;
- keep/drop/dump retention policies.

### 4.6. Verification reality

В область v1 входят:

- backend `cargo check` / tests;
- DB integration tests;
- Python API smoke;
- repeated smoke;
- frontend dependency preparation;
- frontend build/test;
- mocked browser smoke;
- real-backend browser smoke;
- clean-machine dry/deps/runtime gates;
- docs gates;
- artifact completeness and size gates;
- devctl apply/check/commit/push stages.

---

## 5. Current product grounding

Стабилизация release/dev lifecycle должна опираться на реальное состояние продукта, а не на желаемую картину.

На текущем этапе ближайший проверяемый happy-path должен строиться вокруг:

- workspace -> board -> columns -> cards;
- core backend CRUD;
- appearance/customization API;
- board appearance;
- activity feed / card history / workspace audit log;
- existing backend smoke and integration coverage.

Что нельзя считать полноценным release-blocking happy-path без отдельной готовности:

- финальный auth UX;
- полноценный login/session wiring;
- guest/public/shared UX;
- полный comments/checklists/labels flow;
- rich card history по всем будущим типам сущностей;
- real-time/p2p sync as required beta path.

Release gates должны быть честными:

```text
ready surface -> tested and score-affecting gate
partial surface -> explicit partial/known limitation
future surface -> not implemented / non-blocking roadmap item
```

Нельзя строить green release на тестировании future-ready surface как будто он уже production-ready.

---

## 6. Operating model

### 6.1. Stop-rule before fixes

На время этой stabilization lane запрещается начинать с очередного фикса, если не выполнено хотя бы одно условие:

1. сбой уже покрыт known failure-mode ID;
2. сбой сначала добавлен в Problem Ledger как observed/suspected;
3. у фикса есть regression probe or acceptance check.

Правила:

```text
Patch без failure-mode ID подозрителен.
Patch без evidence экспериментален.
Patch без acceptance check неполон.
Patch без rollback/cleanup может стать новым failure-mode.
```

### 6.2. Evidence-first loop

Каждый новый сбой проходит через цикл:

```text
observe
-> classify
-> assign ID
-> link evidence
-> choose remediation
-> add/extend probe
-> run repeatability check
-> update confidence
```

### 6.3. Supported side effects

Side effects делятся на категории:

```text
read-only
write-run-artifacts
write-dependencies
network-download
write-env-files
write-database
create-database
drop-database
start-process
stop-owned-process
stop-foreign-process
write-project-files
```

По умолчанию запрещены:

- `stop-foreign-process`;
- destructive DB cleanup without target proof;
- env overwrite without backup;
- network download without explicit consent;
- project file mutation during release-gates/autopsy.

### 6.4. Profiles

Нужны профили с ясной ценой и side effects:

| Profile | Purpose | Side effects | Release meaning |
|---|---|---|---|
| `diagnostic` | classify environment and known prerequisites | run artifacts only | no product confidence, high diagnostic value |
| `prepared-local` | use existing local deps and explicit DB | run artifacts, process start | partial local confidence |
| `isolated-db` | fresh managed DB checks | create/drop DB | DB/migration confidence |
| `managed-runtime` | managed backend/frontend dynamic ports | start/stop owned processes | runtime confidence |
| `full-local-release` | maximum local release signal | all allowed with consent | beta-candidate input |
| `clean-machine-dry` | archive/check readiness without heavy installs | sandbox artifacts | portability signal |
| `clean-machine-runtime` | opt-in full clean runtime | deps/network/DB/process | strongest portability signal |

---

## 7. Ledgers

### 7.1. Problem Ledger

Problem Ledger is the durable memory of failures.

Required fields:

```text
id
family
status
severity
ownerLayer
summary
firstObservedAt
lastObservedAt
evidence[]
rootCauseHypothesis
remediationOptions[]
chosenRemediation
acceptanceCheck
regressionProbe
cleanupOrRollback
confidence
relatedIssues[]
```

Statuses:

```text
suspected
observed
reproduced
remediation_planned
patched
guarded
closed
regressed
accepted_non_blocking
```

Severities:

```text
blocks_release
blocks_local_start
blocks_repeatability
degrades_signal
hides_failure
security_risk
usability_risk
documentation_gap
transport_only
```

### 7.2. Probe Ledger

Probe Ledger records how failure classes are detected.

Required fields:

```text
probeId
coversFailureIds[]
profile
commandOrCheck
destructiveRisk
expectedPassCondition
expectedFailureClassification
lastRunStatus
lastRunEvidence
```

Important distinction:

```text
Probe can intentionally produce a controlled failure.
A controlled expected failure is not a release regression.
```

### 7.3. Decision Ledger

Decision Ledger records why a remediation path was chosen.

Required fields:

```text
decisionId
date
context
optionsConsidered[]
chosenOption
rejectedOptions[]
riskTradeoff
rollback
reviewDate
```

Use Decision Ledger for:

- managed DB policy;
- dynamic ports vs fixed ports;
- Windows direct Vite fallback;
- auth path in browser smoke;
- archive trimming policy;
- push failure handling;
- accepting non-blocking skipped gates.

---

## 8. Failure taxonomy v1

ID format:

```text
REL-<FAMILY>-<NNN>
```

Families:

| Family | Meaning |
|---|---|
| `REL-ART` | artifact/report/bundle quality |
| `REL-SEC` | diagnostic security, redaction and secret leakage prevention |
| `REL-BE` | backend build/runtime/test |
| `REL-BROWSER` | browser/e2e realism and Playwright |
| `REL-CFG` | env/config/API/CORS mismatch |
| `REL-CLEAN` | clean-machine and packaging |
| `REL-DB` | DB discovery/auth/authority/lifecycle |
| `REL-DEPS` | dependency preparation and drift |
| `REL-DOCS` | docs/ops guide/known limitations |
| `REL-FE` | frontend build/dev server |
| `REL-MIG` | migrations disk/applied/embedded integrity |
| `REL-PORT` | port availability and conflict |
| `REL-PROC` | process ownership/lifecycle |
| `REL-SMOKE` | smoke idempotency/data assumptions |
| `REL-TEST` | test harness/classification problems |
| `REL-VCS` | devctl/git/remote transport separation |
| `REL-WIN` | Windows shell/launcher/argv |

Confidence classes for failure classification:

```text
confirmed_root_cause
high_confidence_hypothesis
low_confidence_hypothesis
symptom_only
accepted_unknown_with_next_probe
```

A `symptom_only` entry cannot be closed.

---

## 9. Initial known failure-mode seed list

| ID | Status | Summary | Owner layer | Required probe |
|---|---|---|---|---|
| `REL-FE-001` | observed | `node_modules` absent/stale blocks build/test/browser gates | devbootstrap/frontend | frontend dependency marker preflight |
| `REL-WIN-001` | observed | npm/Vite startup through wrapper can hang or lose forwarded args | devbootstrap | command-resolution self-check + direct Vite fallback |
| `REL-DB-001` | observed | DB integration tests skipped without safe `TEST_DATABASE_URL` | devbootstrap/backend tests | explicit DB or managed DB gate |
| `REL-DB-002` | observed | configured DB user may lack `CREATEDB`; admin override needed | devbootstrap | authority ladder probe |
| `REL-MIG-001` | observed | `sqlx::migrate!()` can embed stale migration list without rebuild trigger | backend/devbootstrap | build.rs check + migration integrity guard |
| `REL-SMOKE-001` | observed | fixed-user default-state assumptions fail on dirty dev DB | smoke/backend | repeated smoke + dirty-state tolerant check |
| `REL-PROC-001` | observed | old backend/frontend process can make new code appear missing | devbootstrap | owned process and health identity probe |
| `REL-PORT-001` | suspected | foreign process can occupy expected ports | devbootstrap | temporary port binder + owner classification |
| `REL-CFG-001` | suspected | frontend can call old/wrong backend or blocked origin | devbootstrap/frontend/backend | API base + CORS consistency probe |
| `REL-BROWSER-001` | suspected | mocked browser smoke can hide real backend integration gap | frontend/devbootstrap | real-backend browser path gate |
| `REL-CLEAN-001` | suspected | clean archive/checkout may not reproduce current dev setup | devbootstrap/devctl | clean-machine dry/deps gate |
| `REL-ART-001` | observed | diagnostics can be incomplete or too large to share | devbootstrap/devctl | artifact completeness and exclusion checks |
| `REL-VCS-001` | observed | remote push internal error after local apply/check/commit | devctl/Git | stage-separated devctl report |
| `REL-DOCS-001` | suspected | docs can describe old command behavior | docs/devbootstrap | docs command examples gate |
| `REL-SEC-001` | suspected | diagnostic bundle can leak secrets | devbootstrap/devctl | redaction report + secret scan |

---

## 10. Metrics

### 10.1. Release Confidence Score

Release Confidence Score is a 0-100 score.

| Block | Weight | What it measures |
|---|---:|---|
| Evidence completeness | 15 | Required machine/human bundle artifacts are present and valid. |
| Gate execution signal | 20 | Required gates executed, not silently skipped/not implemented. |
| Repeatability | 15 | Same profile passes twice and survives start/stop/start. |
| Isolation safety | 15 | Managed DB/runtime, ownership-aware stop, no unsafe mutation. |
| Cross-platform confidence | 10 | Linux, Windows shell/launcher/path realities are covered. |
| Product-path confidence | 15 | Real ready product paths are tested end-to-end. |
| Remediation maturity | 5 | Failure modes have IDs, evidence, remediation and probes. |
| Artifact quality | 5 | Bundle is small, redacted, complete and shareable. |

Score classes:

| Score | Class | Meaning |
|---:|---|---|
| `< 50` | `diagnostic_chaos` | Release forbidden; too much unknown. |
| `50-69` | `partial_signal` | Useful for fixing infra, not beta-ready. |
| `70-84` | `internal_candidate` | Good enough for internal user testing. |
| `85-94` | `beta_candidate` | Candidate for limited external beta. |
| `95+` | `stable_release_loop` | Mature repeatable release/dev loop. |

### 10.2. Unknown Ratio

```text
unknown_ratio = skipped_or_not_implemented_required_gates / all_required_gates
```

Targets:

```text
initial target: < 25%
beta target: < 10%
blocker target: 0 unknown blockers
```

Rule: skipped required gates reduce confidence. They never count as pass.

### 10.3. Reproducibility Index

```text
reproducibility_index = passed_repeatability_scenarios / total_repeatability_scenarios
```

Scenarios:

```text
release-gates once
release-gates twice
start -> stop -> start
failed start -> stop -> start
smoke on fresh DB
smoke on dirty DB
frontend launch after stale dependency marker
backend launch after migration change
clean-machine dry run
```

Target for v1 stabilization: `>= 0.8`.

### 10.4. Failure Classification Coverage

```text
classification_coverage = classified_failures / all_failures
```

Target:

```text
100% for known classes
>= 90% for new observed failures
```

### 10.5. Remediation Closure Rate

```text
remediation_closure_rate = failure_modes_with_acceptance_check / total_failure_modes
```

Target: `>= 95%`.

### 10.6. Diagnostic Coverage Metrics

| Area | Metric | Target |
|---|---|---:|
| Toolchain | required tool probes present | `>= 95%` of profile requirements |
| Commands | command resolution captured | `100%` external commands |
| Environment | env diff captured and redacted | `100%` env-affecting gates |
| Ports | owned/foreign/available classified | backend/frontend/db ports |
| DB | authority ladder level determined | every DB-writing run |
| Migrations | disk/applied/embedded consistency checked | every managed backend run |
| Frontend deps | marker/package-lock drift checked | every frontend gate |
| Browser | package/binary prereq checked | every browser gate |
| Docs | startup/limitations/checklist gates run | release profile |

### 10.7. Safety Metrics

| Metric | Target |
|---|---:|
| Foreign process kills | `0` |
| DB writes without safe target or consent | `0` |
| Env overwrites without backup | `0` |
| Secret leaks in archive | `0` |
| Destructive cleanup without rollback/manual command | `0` |
| Controlled mutators missing consent summary | `0` |
| `not_implemented` mapped to green | `0` |

### 10.8. User Experience Metrics

| Metric | Target |
|---|---:|
| Commands to produce shareable diagnostic bundle | `1` primary command/profile |
| Failed/skipped gate next-action clarity | `100%` |
| Manual fallback completeness | command + reason + verification + rollback |
| Bundle diagnostic sufficiency | no extra terminal logs needed |
| Time to first useful classification | one diagnostic run |

---

## 11. Artifact system

### 11.1. Required autopsy/release bundle

Target shape:

```text
release-autopsy.md
release-autopsy.json
summary.txt
release-confidence.json
problem-ledger.md
problem-ledger.json
probe-ledger.json
decision-ledger.md
remediation-plan.md
rerun-commands.md
next-actions.md
environment-fingerprint.json
command-resolution.json
side-effects.json
redaction-report.md
archive-size-report.md
logs/
reports/
artifacts/
```

Early implementation may reuse current `release-gates` layout, but semantic contract should converge toward this structure.

### 11.2. Evidence contract

Every issue links to evidence paths:

```text
Evidence:
- logs/07_frontend_build.log
- reports/diagnose/report.md#ports
- environment-fingerprint.json#node
- command-resolution.json#frontend-dev
```

Do not copy giant logs into prose when a path reference is enough.

### 11.3. Redaction contract

Reports must mask:

- database passwords;
- auth tokens;
- cookies;
- provider secrets;
- `.env` secret values;
- connection strings with credentials;
- local private path fragments where privacy matters.

Reports may keep non-sensitive diagnostic values:

- host/port;
- safe boolean flags;
- workspace-relative paths;
- command names;
- tool versions.

### 11.4. Archive size contract

Diagnostic/devctl archives must exclude:

```text
.git/
.venv/
node_modules/
target/
dist/
build/
coverage/
__pycache__/
.pytest_cache/
.env
.env.*
*.sqlite
*.db
```

Heavy release artifacts should be replaced by placeholders or manifest entries when full binaries are not needed for diagnosis.

---

## 12. Workstreams

### WS-1. Autopsy Harness foundation

Goal: introduce explicit diagnostic mode that produces a system map, not just pass/fail.

Scope:

- `release-gates --profile diagnostic` first;
- future `autopsy`/`deep-scan` alias if useful;
- environment fingerprint;
- command resolution planner;
- side-effect inventory;
- initial Problem Ledger;
- stable JSON schema.

Acceptance:

- diagnostic run succeeds on a machine without Node/Rust/PostgreSQL by classifying missing prerequisites;
- bundle is useful without terminal output;
- every planned side effect is visible before execution.

### WS-2. Failure taxonomy and ledgers

Goal: make failures comparable across runs.

Scope:

- family/status/severity taxonomy;
- Problem Ledger writer;
- Probe Ledger writer;
- Decision Ledger templates;
- mapping current gate statuses into ledger entries;
- stable next-action templates.

Acceptance:

- same failure receives same or related stable ID;
- ledger can be diffed between runs;
- no infra blocker appears only as raw stacktrace.

### WS-3. PostgreSQL Authority Manager

Goal: stop treating DB as mysterious prerequisite.

Scope:

- authority ladder levels 0-4;
- explicit maintenance/admin connection handling;
- managed per-run DB;
- retention policy: drop-always, keep-on-failure, keep-always;
- dump-on-failure;
- production-looking URL guard;
- manual remediation pack.

Acceptance:

- no write-capable gate runs against unknown DB target;
- missing createdb permission produces manual pack, not panic;
- failed managed DB run prints cleanup command and keeps evidence.

### WS-4. Process and Port Supervisor

Goal: make start/stop safe, owned and repeatable.

Scope:

- runtime identity file;
- owned PID verification by cwd/command/start metadata;
- foreign process detection;
- dynamic port selection;
- readiness probes;
- double stop idempotency;
- failed-start cleanup.

Acceptance:

- foreign process on port is never killed;
- stale PID is classified;
- start after failed start has deterministic classification;
- managed teardown leaves no owned backend/frontend process alive.

### WS-5. Windows Launcher Normalization

Goal: make Windows behavior explainable and testable.

Scope:

- `cmd.exe /d /c call` handling;
- PowerShell notes;
- npm `.cmd` wrapper behavior;
- forwarded args through npm scripts;
- path-with-spaces fixture;
- direct Vite fallback;
- exact argv report.

Acceptance:

- frontend launch failure includes launcher family and exact argv;
- path-with-spaces self-check exists;
- direct fallback is documented and gated.

### WS-6. Runtime Config Resolver

Goal: prevent frontend/backend/env mismatch.

Scope:

- effective backend URL;
- effective frontend API base URL;
- CORS origins;
- fixed vs dynamic ports;
- `.env` precedence;
- stale env detection;
- profile-specific env overlay.

Acceptance:

- real-backend browser gate reports which backend it actually calls;
- CORS mismatch is classified before opaque browser failure;
- stale API base URL receives `REL-CFG` classification.

### WS-7. Migration Integrity Guard

Goal: close disk/applied/embedded migration drift.

Scope:

- check backend `build.rs`;
- check `cargo:rerun-if-changed=migrations`;
- compare migration files on disk vs applied migrations;
- identify likely embedded stale list where possible;
- targeted rebuild guidance.

Acceptance:

- migration mismatch classified as `REL-MIG`;
- report explains disk/applied/embedded state;
- `cargo clean` is suggested only when evidence supports it.

### WS-8. Smoke Idempotency and Data Strategy

Goal: make smoke valid on fresh and dirty state.

Scope:

- shared-dev smoke;
- isolated-fresh smoke;
- per-run unique IDs;
- cleanup verification;
- default-state checks only in isolated DB;
- repeated smoke.

Acceptance:

- shared-dev smoke does not assume fixed user defaults;
- isolated-fresh smoke checks defaults;
- two consecutive smoke runs are required for confidence.

### WS-9. Frontend Dependency and Browser Gate Hardening

Goal: distinguish dependencies, build, mocked browser and real backend failures.

Scope:

- package-lock/package-json marker;
- dependency modes: never/missing/stale/always;
- Playwright package and browser detector;
- consent before network browser install;
- mocked browser vs real-backend browser classification.

Acceptance:

- missing/stale deps are `REL-DEPS`/`REL-FE`, not vague build failure;
- missing browsers are `REL-BROWSER`, not generic frontend failure;
- real-backend smoke is separately scored.

### WS-10. Clean-machine Sandbox and Packaging Hygiene

Goal: prove archive/checkout realism.

Scope:

- clean-machine dry sandbox;
- optional deps sandbox;
- optional runtime sandbox;
- README quickstart verification;
- archive exclude rules;
- placeholder policy for heavy files.

Acceptance:

- clean sandbox can run dry gate;
- archive size and exclusions are reported;
- missing prereqs are classified, not hidden.

### WS-11. devctl and VCS Transport Separation

Goal: avoid confusing good patch with remote outage.

Scope:

- separate stages: validate, apply, checks, commit, push;
- local commit evidence;
- push retry instructions;
- safe reissue protocol;
- remote outage classification.

Acceptance:

- `PUSH_FAILED` is `REL-VCS`, not patch failure;
- report says product status unchanged when only push failed;
- patch SHA and commit SHA are visible.

### WS-12. Documentation and Operating Guide

Goal: keep docs synchronized with tool behavior.

Scope:

- profile guide;
- side-effect consent guide;
- DB authority guide;
- manual remediation pack guide;
- transport failure playbook;
- v1 known limitations update;
- docs gate for command examples.

Acceptance:

- user can choose correct profile without asking;
- every dangerous side effect is documented;
- docs fail when command examples become stale.

---

## 13. Phased roadmap

### Phase 0. Governance freeze and baseline inventory

Purpose: stop blind fixes while preserving docs/diagnostic progress.

Actions:

1. Declare stabilization lane active.
2. Create initial Problem Ledger from known failures.
3. Define score/classes.
4. Define profile side effects.
5. Update docs map.

Phase 0 operating artifacts:

- `docs/development/release-stabilization-phase-0-baseline.md`;
- `docs/development/release-stabilization-problem-ledger.md`;
- `docs/development/release-confidence-scorecard-v1.md`;
- `docs/development/release-stabilization-profile-side-effects-v1.md`.

Exit criteria:

- every currently known blocker has family and owner layer;
- no release/dev fix is accepted without failure-mode ID;
- score can be computed at least manually.

### Phase 1. Autopsy bundle contract

Purpose: make every run self-explanatory.

Actions:

1. Add required bundle manifest.
2. Add environment fingerprint.
3. Add command-resolution artifacts.
4. Add redaction report.
5. Add artifact completeness check.

Exit criteria:

- missing tools are classified;
- bundle can be analyzed without terminal output;
- required artifacts are present or explicitly marked unavailable.

### Phase 2. Ledgers and taxonomy implementation

Purpose: make failures durable knowledge.

Actions:

1. Generate Problem Ledger JSON/Markdown.
2. Generate Probe Ledger skeleton.
3. Add Decision Ledger templates.
4. Map gate statuses into families.
5. Generate rerun/next-action commands.

Operating artifacts:

- `docs/development/release-stabilization-phase-2-ledgers-and-taxonomy.md`;
- `.dev-bootstrap/runs/<run-id>/remediation/problem-ledger.json`;
- `.dev-bootstrap/runs/<run-id>/remediation/probe-ledger.json`;
- `.dev-bootstrap/runs/<run-id>/remediation/decision-ledger-template.json`.

Exit criteria:

- repeated same failure maps to stable ID;
- unresolved blockers are listed in one place;
- each blocker has next action.

Implementation status: implemented in `tools/devbootstrap.py`; bundle contract version is now `phase-2`.

### Phase 3. Diagnostic provocation matrix

Purpose: catch expected failures before users encounter them accidentally.

Actions:

1. Add low-risk port binder probe.
2. Add launcher dry-run matrix.
3. Add DB capability probes.
4. Add dirty-state smoke probe.
5. Add clean-machine dry profile.

Exit criteria:

- expected controlled failures are classified;
- real destructive actions are still opt-in;
- unknown ratio decreases.

Operating artifacts:

- `docs/development/release-stabilization-phase-3-diagnostic-provocation-matrix.md`;
- `.dev-bootstrap/runs/<run-id>/remediation/provocation-matrix.json`;
- `.dev-bootstrap/runs/<run-id>/remediation/provocation-matrix.md`.

Implementation status: implemented in `tools/devbootstrap.py`; bundle contract version is now `phase-3`.

### Phase 4. Controlled mutators rollout

Purpose: safely perform preparation when diagnostics justify it.

Actions:

1. Managed DB create/drop with retention policy.
2. Managed runtime dynamic ports.
3. Dependency preparation with marker and consent.
4. Optional Playwright browser install with consent.
5. Cleanup and rollback artifacts.

Exit criteria:

- unsafe mutation count remains zero;
- user sees side-effect summary;
- cleanup command exists for every created resource.

Operating artifacts:

- `docs/development/release-stabilization-phase-4-controlled-mutators-rollout.md`;
- `.dev-bootstrap/runs/<run-id>/release-gates-consent.json` / `.md`;
- `.dev-bootstrap/runs/<run-id>/remediation/controlled-mutators.json`;
- `.dev-bootstrap/runs/<run-id>/remediation/controlled-mutators.md`.

Implementation status: implemented in `tools/devbootstrap.py`; bundle contract version is now `phase-4`.

### Phase 5. Repeatability loop

Purpose: prove that success is not accidental.

Actions:

1. Run same profile twice.
2. Run start-stop-start.
3. Run failed-start-retry scenario.
4. Run fresh and dirty smoke.
5. Compare ledgers between runs.

Exit criteria:

- Reproducibility Index >= 0.8;
- repeated smoke passes or produces known non-blocking classifications;
- cleanup verification passes.

Operating artifacts:

- `docs/development/release-stabilization-phase-5-repeatability-loop.md`;
- `.dev-bootstrap/runs/<run-id>/remediation/repeatability-loop.json`;
- `.dev-bootstrap/runs/<run-id>/remediation/repeatability-loop.md`.

Implementation status: implemented in `tools/devbootstrap.py`; bundle contract version is now `phase-5`. The first run in a new workspace is allowed to report `insufficient-history`; the next same-profile run is what upgrades this from contract-shape evidence to repeatability evidence.

### Phase 6. Release confidence gate

Purpose: convert evidence into release decision.

Actions:

1. Compute Release Confidence Score.
2. Compute Unknown Ratio.
3. Compute classification coverage.
4. Compute artifact quality.
5. Produce `v1-release-readiness.md`.

Exit criteria:

- score >= 85 for beta candidate;
- no unknown blockers;
- accepted skips are documented and non-blocking.

### Phase 7. Continuous memory and regression protection

Purpose: prevent return to reactive cycle.

Actions:

1. Every new failure adds/updates ledger.
2. Every remediation adds/updates probe.
3. Compare runs over time.
4. Keep docs synchronized.
5. Track recurring family counts.

Exit criteria:

- new failures add light to the map;
- fixed failures have guards;
- recurring failure family causes process review.

---

## 14. PostgreSQL Authority Ladder

DB path must use a ladder, not panic.

```text
Level 0: explicit TEST_DATABASE_URL
Level 1: managed per-run DB using provided admin/maintenance connection
Level 2: dedicated local devbootstrap role
Level 3: local-only privileged bootstrap path with explicit consent
Level 4: manual remediation pack
```

Rules:

- Application user/auth identity must not be confused with PostgreSQL admin authority.
- Production-looking URLs are blocked by default.
- DB writes require explicit safe target or consent.
- Failed managed DB run should optionally keep DB/dump evidence.
- Cleanup command must be printed for every created DB.

---

## 15. Process and port rules

Port/process handling must be ownership-aware.

Questions every runtime gate must answer:

```text
who holds the port?
is it our process?
is PID stale or reused?
does cwd/command match workspace?
is readiness alive?
did process die after start?
can it be safely stopped?
```

Rules:

- Never kill foreign process by default.
- Stop only owned process.
- Dynamic ports preferred for managed runtime.
- Fixed ports allowed for legacy profile, but conflicts are classified.
- `stop` must be idempotent.

---

## 16. Smoke strategy

### 16.1. Shared-dev smoke

Must:

- create unique entities;
- clean what it creates;
- tolerate existing user state;
- avoid fixed-user default assumptions;
- verify updates by readback;
- produce clear cleanup evidence.

### 16.2. Isolated-fresh smoke

May be stricter:

- check defaults;
- check migrations from zero;
- use managed DB;
- fail on unexpected preexisting state.

### 16.3. Browser smoke

Must distinguish:

```text
mocked browser smoke -> UI viability only
real-backend browser smoke -> release confidence input
```

Real-backend path should cover the currently ready product path:

```text
workspace
board
column
card
card details/activity where available
appearance where available
network calls to configured API base
```

Auth should be explicit:

- if final auth UX is ready, use it;
- if dev-auth/X-User-Id path is still used, mark it as dev profile and known limitation;
- never pretend dev-auth means final auth UX is release-ready.

---

## 17. Contract parity

Release confidence must include whether backend, OpenAPI, frontend client and smoke agree.

Required inventories:

```text
backend route inventory
OpenAPI route inventory
frontend API call inventory
smoke/e2e coverage inventory
known limitations inventory
```

Mismatch classes:

```text
backend_has_route_openapi_missing
openapi_has_route_backend_missing
frontend_calls_unknown_route
smoke_uses_deprecated_route
auth_contract_transition_gap
```

X-User-Id/dev-auth transition must be tracked explicitly until final auth wiring is release-ready.

---

## 18. Risk register

| Risk | Impact | Detection | Mitigation | Metric |
|---|---|---|---|---|
| Autopsy becomes giant flaky command | Users stop trusting it | high variance between runs | profile tiers and self-check fixtures | repeatability pass count |
| Bundle leaks secrets | unsafe to share logs | redaction scan | central masking + redaction report | secret leaks = 0 |
| Controlled mutators damage local env | data loss/trust loss | side-effect mismatch | consent + local guards + rollback | unsafe mutations = 0 |
| Managed DB hides explicit DB problems | false confidence | compare explicit vs managed profile | keep both profile families | DB context coverage |
| Dirty dev DB causes false smoke failures | wasted fixes | repeated smoke | fresh vs dirty split | false regression rate |
| Windows launcher remains under-tested | repeated frontend failures | recurring `REL-WIN` | dry-run matrix + fallback | recurring `REL-WIN` count |
| Release gates too slow | bypassed by users | elapsed time/profile usage | tiered profiles | profile adoption |
| Docs drift | wrong instructions | docs gate | command-example validation | docs gate pass rate |
| Push failure invalidates good patch mentally | duplicate confusion | `PUSH_FAILED` | `REL-VCS` separation | transport separation |
| AI/user overfits latest stacktrace | reactive cycle returns | patches without IDs | review rule | traceability |
| Archive bloat returns | uploads impractical | size report | exclude contract | archive size trend |
| Privileged DB convenience weakens security | unsafe local habits | privileged op report | explicit local-only consent | privileged ops with consent |
| Not implemented gates look green | false readiness | status normalization | `not_implemented` never maps pass | greenwash count |
| Score gaming | high number with weak evidence | manual audit | score must cite artifacts | score evidence coverage |
| Ledger bloat | nobody reads it | stale entries | severity and status pruning | stale ledger count |

---

## 19. Strategic patch chain

Recommended chain:

1. `release-stabilization-program-docs`  
   Add this canonical program, merge notes and docs map entry.

2. `autopsy-ledger-contract`  
   Add Problem/Probe/Decision Ledger schemas and initial seed IDs.

3. `release-confidence-scoreboard`  
   Add score/classes/unknown ratio calculation to release-gates output.

4. `command-resolution-fingerprint`  
   Record exact argv, shell mode, tool versions, env diff and timeouts.

5. `postgres-authority-manager`  
   Connect DB outcomes to `REL-DB` IDs, managed DB, manual packs and cleanup artifacts.

6. `runtime-supervisor-provocations`  
   Add port binder, foreign process, stale PID and owned-process checks.

7. `windows-launcher-provocation-matrix`  
   Add `.cmd`, `cmd.exe call`, PowerShell, path-with-spaces and Vite fallback checks.

8. `config-migration-integrity-guards`  
   Add API/CORS consistency and migration disk/applied/embedded diagnostics.

9. `smoke-idempotency-ledger`  
   Split fresh/dirty smoke behavior and require repeated smoke.

10. `frontend-browser-gate-clarity`  
    Separate dependency, build, mocked browser, real-backend browser and Playwright install states.

11. `clean-machine-and-artifact-confidence`  
    Promote clean-machine dry/deps/runtime gates and artifact trimming.

12. `devctl-vcs-transport-classification`  
    Separate apply/check/commit/push stages and document safe reissue semantics.

13. `v1-release-readiness-report`  
    Produce final readiness report with score, unknowns, limitations and accepted risks.

---

## 20. Review rules for future patches

Every stabilization patch must answer:

```text
1. Which failure-mode IDs does it address?
2. What new evidence or probe does it add?
3. Which metric changes if it works?
4. What side effects does it introduce?
5. What cleanup/rollback exists?
6. What profile should run it?
7. What remains unknown?
```

Reject or split patches that:

- mix unrelated product features and release infra changes;
- mutate environment without consent;
- make skipped gates green;
- add logs but no classification;
- add classification but no next action;
- add remediation but no probe;
- increase archive size without reason;
- silently weaken security/redaction.

---

## 21. Definition of done for the whole program

The stabilization program is successful when:

1. One command/profile can produce a shareable release/dev autopsy bundle.
2. The bundle is sufficient for analysis without extra terminal logs.
3. Every gate has precise classification.
4. Required skipped/unknown gates reduce confidence.
5. Known blocker classes have stable Problem Ledger IDs.
6. Every resolved failure has a regression probe.
7. Managed DB is safe, explicit and repeatable.
8. Managed runtime uses ownership-aware process control.
9. Windows launcher behavior is explainable through command-resolution artifacts.
10. Smoke passes twice or fails with known non-blocking classification.
11. Fresh-state checks run on isolated DB.
12. Real-backend browser path is separated from mocked browser smoke.
13. Migration mismatch is detected before vague runtime failure.
14. Clean-machine dry/deps/runtime profiles exist.
15. Docs and known limitations are synchronized with actual behavior.
16. Devctl separates patch/check/commit failure from remote push transport failure.
17. Release Confidence Score is at least 85 for beta candidate.
18. Problem Ledger has no unknown blockers.

Final strategic test:

```text
A new failure should add light to the map, not just produce the next patch.
```

---

## 22. Immediate next actions

1. Add this program document and merge notes to docs.
2. Seed Problem Ledger schema and initial known IDs.
3. Add release-confidence and unknown-ratio calculation to release-gates output.
4. Add command-resolution/environment fingerprint artifacts.
5. Implement managed DB authority ladder as the first high-value remediation track.
6. Implement process/port supervisor and Windows launcher probes.
7. Split smoke into shared-dev and isolated-fresh profiles.
8. Add real-backend browser gate only against currently ready product surface.
9. Add devctl transport failure classification.
10. Produce `v1-release-readiness.md` only after repeatability loop has real evidence.
