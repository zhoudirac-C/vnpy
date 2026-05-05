#!/usr/bin/env bash
set -u -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_DIR="${EVIDENCE_DIR:-${REPO_ROOT}/docs/community/ops/validation_results/podman-e2e/${TIMESTAMP}}"
NETWORK_NAME="${NETWORK_NAME:-vnpy-e2e}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-vnpy-e2e-postgres}"
POSTGRES_VOLUME="${POSTGRES_VOLUME:-vnpy-e2e-postgres-data}"
IMAGE_NAME="${IMAGE_NAME:-localhost/vnpy-e2e:latest}"
HOST_GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || printf unknown)"

mkdir -p "${EVIDENCE_DIR}"

log() {
    printf '[%s] %s\n' "$(date --iso-8601=seconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "${EVIDENCE_DIR}/run.log"
}

run_logged() {
    local name="$1"
    shift
    log "RUN ${name}: $*"
    "$@" >"${EVIDENCE_DIR}/${name}.stdout.log" 2>"${EVIDENCE_DIR}/${name}.stderr.log"
    local code=$?
    log "DONE ${name}: exit=${code}"
    return "${code}"
}

wait_for_postgres() {
    local attempt
    for attempt in $(seq 1 60); do
        if podman exec "${POSTGRES_CONTAINER}" pg_isready -U vnpy -d vnpy >/dev/null 2>&1; then
            log "PostgreSQL is ready"
            return 0
        fi
        sleep 1
    done
    log "PostgreSQL did not become ready"
    podman logs "${POSTGRES_CONTAINER}" >"${EVIDENCE_DIR}/postgres.logs" 2>&1 || true
    return 1
}

cd "${REPO_ROOT}" || exit 1

log "Evidence dir: ${EVIDENCE_DIR}"
run_logged podman-info podman info || exit 1
run_logged podman-build podman build -f tools/podman/Containerfile.e2e -t "${IMAGE_NAME}" . || exit 1

podman network exists "${NETWORK_NAME}" >/dev/null 2>&1 || run_logged podman-network-create podman network create "${NETWORK_NAME}" || exit 1
run_logged podman-rm-old-postgres podman rm -f "${POSTGRES_CONTAINER}" || true
podman volume exists "${POSTGRES_VOLUME}" >/dev/null 2>&1 || run_logged podman-volume-create podman volume create "${POSTGRES_VOLUME}" || exit 1
run_logged podman-start-postgres \
    podman run -d \
    --name "${POSTGRES_CONTAINER}" \
    --network "${NETWORK_NAME}" \
    -e POSTGRES_DB=vnpy \
    -e POSTGRES_USER=vnpy \
    -e POSTGRES_PASSWORD=vnpy-e2e-password \
    -v "${POSTGRES_VOLUME}:/var/lib/postgresql/data" \
    docker.io/library/postgres:16-alpine || exit 1
wait_for_postgres || exit 1
run_logged podman-ps-before podman ps --all || true

COMMON_ENV=(
    -e HOME=/tmp/vnpy-e2e-home
    -e POSTGRES_HOST="${POSTGRES_CONTAINER}"
    -e POSTGRES_PORT=5432
    -e POSTGRES_DB=vnpy
    -e POSTGRES_USER=vnpy
    -e POSTGRES_PASSWORD=vnpy-e2e-password
    -e OPENAI_API_KEY=e2e-fake-openai-key
    -e TRADINGAGENTS_WORKER_FACTORY=vnpy_tradingagents.tradingagents_factory:build
    -e HOST_GIT_COMMIT="${HOST_GIT_COMMIT}"
    -e UV_PROJECT_ENVIRONMENT=/tmp/vnpy-e2e-venv
    -e UV_CACHE_DIR=/tmp/vnpy-e2e-uv-cache
    -e UV_LINK_MODE=copy
)

COMMON_RUN=(
    podman run --rm
    --network "${NETWORK_NAME}"
    "${COMMON_ENV[@]}"
    -v "${REPO_ROOT}:/workspace"
    -v "${EVIDENCE_DIR}:/evidence"
    -w /workspace
    "${IMAGE_NAME}"
)

PRE_EXIT=0
run_logged e2e-pre-restart \
    "${COMMON_RUN[@]}" \
    bash -lc 'mkdir -p "$HOME" && git config --global --add safe.directory /workspace && uv run --with pytest --with ruff --with psycopg2-binary --with "polars[rtcompat]" --with scipy python tools/podman/e2e_runner.py --phase pre-restart --evidence-dir /evidence' || PRE_EXIT=$?

run_logged podman-restart-postgres podman restart "${POSTGRES_CONTAINER}" || exit 1
wait_for_postgres || exit 1

POST_EXIT=0
run_logged e2e-post-restart \
    "${COMMON_RUN[@]}" \
    bash -lc 'mkdir -p "$HOME" && git config --global --add safe.directory /workspace && uv run --with pytest --with ruff --with psycopg2-binary --with "polars[rtcompat]" --with scipy python tools/podman/e2e_runner.py --phase post-restart --evidence-dir /evidence' || POST_EXIT=$?

run_logged podman-ps-after podman ps --all || true

if [[ "${PRE_EXIT}" -ne 0 || "${POST_EXIT}" -ne 0 ]]; then
    log "E2E completed with failures: pre=${PRE_EXIT}, post=${POST_EXIT}"
    exit 1
fi

log "E2E completed successfully"
