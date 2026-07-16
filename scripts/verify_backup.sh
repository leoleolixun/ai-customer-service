#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
ENV_FILE="${ENV_FILE:-/etc/ai-customer-service/production.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/deploy/compose.production.yml}"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

read_metadata() {
    local key="$1"
    awk -v key="${key}" '
        index($0, key "=") == 1 { value = substr($0, length(key) + 2) }
        END { sub(/\r$/, "", value); print value }
    ' "${backup_dir}/metadata.env"
}

[[ $# -eq 1 ]] || die "usage: $0 BACKUP_DIRECTORY"
[[ -d "$1" ]] || die "backup directory not found: $1"
backup_dir="$(cd -- "$1" && pwd -P)"
[[ -n "${backup_dir}" && "${backup_dir}" != "/" ]] || die "unsafe backup directory"

[[ -f "${ENV_FILE}" ]] || die "environment file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "compose file not found: ${COMPOSE_FILE}"
[[ -f "${backup_dir}/metadata.env" ]] || die "metadata.env is missing"
[[ -f "${backup_dir}/SHA256SUMS" ]] || die "SHA256SUMS is missing"
[[ -s "${backup_dir}/postgres.dump" ]] || die "postgres.dump is missing or empty"
[[ -d "${backup_dir}/minio/bucket" ]] || die "MinIO bucket directory is missing"
command -v docker >/dev/null 2>&1 || die "required command not found: docker"
command -v sha256sum >/dev/null 2>&1 || die "required command not found: sha256sum"

backup_id="$(read_metadata BACKUP_ID)"
[[ "${backup_id}" =~ ^backup-[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || die "invalid backup ID"
[[ "$(read_metadata FORMAT_VERSION)" == "1" ]] || die "unsupported backup format"

printf 'Verifying checksums...\n'
(
    cd -- "${backup_dir}"
    sha256sum --check --strict SHA256SUMS
)

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
"${COMPOSE[@]}" config --quiet

printf 'Verifying PostgreSQL archive catalog...\n'
"${COMPOSE[@]}" run --rm --no-deps \
    -v "${backup_dir}:/backup:ro" \
    --entrypoint pg_restore \
    postgres-tools --list /backup/postgres.dump >/dev/null

expected_minio_count="$(read_metadata MINIO_OBJECT_COUNT)"
[[ "${expected_minio_count}" =~ ^[0-9]+$ ]] || die "invalid expected MinIO object count"
actual_minio_count="$(find "${backup_dir}/minio/bucket" -type f -print | wc -l | tr -d '[:space:]')"
[[ "${actual_minio_count}" == "${expected_minio_count}" ]] \
    || die "MinIO object count mismatch: expected ${expected_minio_count}, got ${actual_minio_count}"

printf 'Backup verified: %s (MinIO objects: %s)\n' \
    "${backup_id}" "${actual_minio_count}"
