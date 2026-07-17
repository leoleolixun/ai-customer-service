#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
ENV_FILE="${ENV_FILE:-/etc/ai-customer-service/production.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/deploy/compose.production.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/ai-customer-service}"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat >&2 <<'EOF'
Usage: restore.sh BACKUP_DIRECTORY [options]

Options:
  --confirm "RESTORE <backup-id>"  Required when stdin is not a terminal.
  --skip-safety-backup             Do not back up the current state first.
  --allow-image-mismatch           Allow restore with a different APP_IMAGE.
EOF
    exit 2
}

read_key() {
    local file="$1"
    local key="$2"
    awk -v key="${key}" '
        index($0, key "=") == 1 { value = substr($0, length(key) + 2) }
        END { sub(/\r$/, "", value); print value }
    ' "${file}"
}

[[ $# -ge 1 ]] || usage
backup_input="$1"
shift
confirmation=""
skip_safety_backup=false
allow_image_mismatch=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --confirm)
            [[ $# -ge 2 ]] || usage
            confirmation="$2"
            shift 2
            ;;
        --skip-safety-backup)
            skip_safety_backup=true
            shift
            ;;
        --allow-image-mismatch)
            allow_image_mismatch=true
            shift
            ;;
        *)
            usage
            ;;
    esac
done

[[ -d "${backup_input}" ]] || die "backup directory not found: ${backup_input}"
backup_dir="$(cd -- "${backup_input}" && pwd -P)"
[[ -n "${backup_dir}" && "${backup_dir}" != "/" ]] || die "unsafe backup directory"
[[ -f "${backup_dir}/metadata.env" ]] || die "metadata.env is missing"
[[ -f "${ENV_FILE}" ]] || die "environment file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "compose file not found: ${COMPOSE_FILE}"

backup_id="$(read_key "${backup_dir}/metadata.env" BACKUP_ID)"
[[ "${backup_id}" =~ ^backup-[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || die "invalid backup ID"
expected_confirmation="RESTORE ${backup_id}"

ENV_FILE="${ENV_FILE}" COMPOSE_FILE="${COMPOSE_FILE}" \
    "${SCRIPT_DIR}/verify_backup.sh" "${backup_dir}"

backup_image="$(read_key "${backup_dir}/metadata.env" APPLICATION_IMAGE)"
current_image="$(read_key "${ENV_FILE}" APP_IMAGE)"
[[ -n "${backup_image}" && -n "${current_image}" ]] || die "APP_IMAGE metadata/config is missing"
if [[ "${backup_image}" != "${current_image}" && "${allow_image_mismatch}" != true ]]; then
    die "APP_IMAGE mismatch: backup=${backup_image}, configured=${current_image}. Set the matching immutable image or pass --allow-image-mismatch after compatibility review."
fi

if [[ -z "${confirmation}" && -t 0 ]]; then
    printf 'This replaces PostgreSQL and the application MinIO bucket, then clears Redis.\n' >&2
    printf 'Type exactly "%s": ' "${expected_confirmation}" >&2
    read -r confirmation
fi
[[ "${confirmation}" == "${expected_confirmation}" ]] \
    || die "restore confirmation did not match: ${expected_confirmation}"

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
"${COMPOSE[@]}" config --quiet
redis_url="$("${COMPOSE[@]}" run --rm --no-deps --entrypoint /bin/sh api \
    -eu -c 'printf "%s\n" "$APP_REDIS_URL"')"
redis_database="${redis_url%%\?*}"
redis_database="${redis_database##*/}"
[[ "${redis_database}" =~ ^[0-9]+$ ]] \
    || die "Compose-rendered APP_REDIS_URL must end with a numeric Redis database index"
"${COMPOSE[@]}" up -d --wait --wait-timeout 120 postgres redis minio

printf 'Stopping API, worker, and beat...\n'
"${COMPOSE[@]}" stop -t 60 api worker beat >/dev/null

restore_failed=true
on_exit() {
    if [[ "${restore_failed}" == true ]]; then
        printf 'ERROR: restore did not complete; API and worker remain stopped for investigation.\n' >&2
    fi
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${skip_safety_backup}" != true ]]; then
    printf 'Creating mandatory pre-restore safety backup...\n'
    ENV_FILE="${ENV_FILE}" COMPOSE_FILE="${COMPOSE_FILE}" BACKUP_ROOT="${BACKUP_ROOT}" \
        "${SCRIPT_DIR}/backup.sh"
else
    printf 'WARNING: pre-restore safety backup explicitly skipped.\n' >&2
fi

printf 'Replacing PostgreSQL database...\n'
"${COMPOSE[@]}" exec -T postgres sh -eu -c '
    case "$POSTGRES_DB" in
        ""|postgres|template0|template1)
            printf "Refusing to replace protected database: %s\n" "$POSTGRES_DB" >&2
            exit 1
            ;;
    esac
    dropdb --force --if-exists --username="$POSTGRES_USER" "$POSTGRES_DB"
    createdb --username="$POSTGRES_USER" --owner="$POSTGRES_USER" "$POSTGRES_DB"
'
"${COMPOSE[@]}" exec -T postgres sh -eu -c '
    exec pg_restore \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --exit-on-error \
        --no-owner \
        --no-acl
' <"${backup_dir}/postgres.dump"

printf 'Replacing MinIO application bucket...\n'
"${COMPOSE[@]}" run --rm --no-deps \
    -v "${backup_dir}/minio:/backup:ro" \
    --entrypoint /bin/sh \
    minio-client -eu -c '
        mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
        mc mb --ignore-existing "local/$APP_S3_BUCKET"
        mc rm --recursive --force "local/$APP_S3_BUCKET" >/dev/null
        mc mirror --overwrite --preserve /backup/bucket "local/$APP_S3_BUCKET"
    '

printf 'Clearing non-authoritative Redis state...\n'
"${COMPOSE[@]}" exec -T redis sh -eu -c '
    REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -n "$1" FLUSHDB >/dev/null
' -- "${redis_database}"

printf 'Starting application services...\n'
"${COMPOSE[@]}" run --rm minio-init
"${COMPOSE[@]}" up -d --no-deps api worker beat

ready=false
for ((attempt = 1; attempt <= 30; attempt++)); do
    if "${COMPOSE[@]}" exec -T api python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" \
        >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
[[ "${ready}" == true ]] || die "API readiness check did not pass within 60 seconds"

expected_revision="$(read_key "${backup_dir}/metadata.env" ALEMBIC_REVISION)"
actual_revision="$("${COMPOSE[@]}" run --rm --no-deps migrate \
    alembic current 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
[[ "${actual_revision}" == "${expected_revision}" ]] \
    || die "Alembic revision mismatch: expected '${expected_revision}', got '${actual_revision}'"

expected_minio_count="$(read_key "${backup_dir}/metadata.env" MINIO_OBJECT_COUNT)"
[[ "${expected_minio_count}" =~ ^[0-9]+$ ]] || die "invalid expected MinIO object count"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint /bin/sh \
    minio-client -eu -c '
        mc alias set app http://minio:9000 "$APP_S3_ACCESS_KEY" "$APP_S3_SECRET_KEY" >/dev/null
        mc stat "app/$APP_S3_BUCKET" >/dev/null
    '
actual_minio_count="$("${COMPOSE[@]}" run --rm --no-deps --entrypoint /bin/sh \
    minio-client -eu -c '
        mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
        mc ls --recursive --json "local/$APP_S3_BUCKET" | wc -l | tr -d "[:space:]"
    ' | tail -n 1)"
[[ "${actual_minio_count}" == "${expected_minio_count}" ]] \
    || die "restored MinIO object count mismatch: expected ${expected_minio_count}, got ${actual_minio_count}"

restore_failed=false
trap - EXIT INT TERM
printf 'Restore completed and verified: %s\n' "${backup_id}"
