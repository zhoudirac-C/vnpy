# Podman E2E Results

| ID | Result | Time | Commit | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| PE2E-00 | 通过 | 2026-05-05T08:16:12+00:00 | e81ff256 | /evidence | Podman image built and postgres runner container started by tools/podman/run_e2e.sh |
| PE2E-01 | 通过 | 2026-05-05T08:16:12+00:00 | e81ff256 | /evidence | PostgreSQL select 1 succeeded |
| PE2E-02 | 通过 | 2026-05-05T08:16:13+00:00 | e81ff256 | /evidence | Peewee params came from vn.py database.* settings |
| PE2E-03 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | 25 extension tables are ready |
| PE2E-04 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | Missing PostgreSQL/provider/API key readiness fails explicitly |
| PE2E-05 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | Readiness status is ready |
| PE2E-06 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | local_file provider returned and persisted 3 bars |
| PE2E-07 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | worker loaded lazily; response action=hold, error_type=dependency_error |
| PE2E-08 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | Forbidden trading handles blocked before runner execution |
| PE2E-09 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | UI guidance is present; runtime secret stays out of settings and secret policy blocks value leaks |
| PE2E-10 | 通过 | 2026-05-05T08:16:14+00:00 | e81ff256 | /evidence | TradingAgentsApp is registered and UI module imports |
| PE2E-11 | 通过 | 2026-05-05T08:16:24+00:00 | e81ff256 | /evidence | local closed-loop report: /evidence/closed_loop_local.md |
| PE2E-12 | 通过 | 2026-05-05T08:16:42+00:00 | e81ff256 | /evidence | production profile rejects missing key and passes with configured gates |
| PE2E-13 | 通过 | 2026-05-05T08:16:43+00:00 | e81ff256 | /evidence | paper smoke buy/hold paths passed without live Gateway |
| PE2E-14 | 通过 | 2026-05-05T08:16:43+00:00 | e81ff256 | /evidence | disabled TradingAgents service degrades without worker call |
| PE2E-15 | 通过 | 2026-05-05T08:17:22+00:00 | e81ff256 | /evidence | Persistence sentinel survived PostgreSQL container restart |
