# Podman E2E Results

| ID | Result | Time | Commit | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| PE2E-00 | 通过 | 2026-05-05T06:46:09+00:00 | 95747e92 | /evidence | Podman image built and postgres runner container started by tools/podman/run_e2e.sh |
| PE2E-01 | 通过 | 2026-05-05T06:46:09+00:00 | 95747e92 | /evidence | PostgreSQL select 1 succeeded |
| PE2E-02 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | Peewee params came from vn.py database.* settings |
| PE2E-03 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | 25 extension tables are ready |
| PE2E-04 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | Missing PostgreSQL/provider/API key readiness fails explicitly |
| PE2E-05 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | Readiness status is ready |
| PE2E-06 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | local_file provider returned and persisted 3 bars |
| PE2E-07 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | worker loaded lazily; response action=hold, error_type=dependency_error |
| PE2E-08 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | Forbidden trading handles blocked before runner execution |
| PE2E-09 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | UI guidance is present; runtime secret stays out of settings and secret policy blocks value leaks |
| PE2E-10 | 通过 | 2026-05-05T06:46:10+00:00 | 95747e92 | /evidence | TradingAgentsApp is registered and UI module imports |
| PE2E-11 | 通过 | 2026-05-05T06:46:21+00:00 | 95747e92 | /evidence | local closed-loop report: /evidence/closed_loop_local.md |
| PE2E-12 | 阻塞 | 2026-05-05T06:46:38+00:00 | 95747e92 | /evidence | production profile did not pass in the mutable E2E worktree; see closed_loop_production_full logs |
| PE2E-13 | 通过 | 2026-05-05T06:46:40+00:00 | 95747e92 | /evidence | paper smoke buy/hold paths passed without live Gateway |
| PE2E-14 | 通过 | 2026-05-05T06:46:40+00:00 | 95747e92 | /evidence | disabled TradingAgents service degrades without worker call |
| PE2E-15 | 通过 | 2026-05-05T07:15:14+00:00 | 95747e92 | /evidence | Persistence sentinel survived PostgreSQL container restart |
| PE2E-16 | 跳过 | 2026-05-05T06:46:40+00:00 | 95747e92 | /evidence | Independent worker container/RPC mode is optional and not implemented in this fork yet |
