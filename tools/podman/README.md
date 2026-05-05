# Podman E2E

This folder contains the test-only Podman stack for the vn.py + router + TradingAgents integration.

Run from the repository root:

```bash
tools/podman/run_e2e.sh
```

The script builds `localhost/vnpy-e2e:latest`, starts an isolated PostgreSQL container, runs the headless E2E runner, restarts PostgreSQL for the persistence check, and writes evidence under:

```text
docs/community/ops/validation_results/podman-e2e/<YYYYMMDD-HHMMSS>/
```

The stack uses vn.py native `database.*` settings and local fixture data. It does not call real brokers, real LLM providers, AKShare, TuShare, QMT, news feeds, or social media APIs.

The image installs `git`, PostgreSQL client tools, and the Qt shared libraries needed for headless UI import checks. Debian package downloads use the Aliyun mirror because the default Debian mirror can stall inside the local Podman VM.
