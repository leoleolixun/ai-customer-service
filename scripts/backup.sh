#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
ENV_FILE="${ENV_FILE:-/etc/ai-customer-service/production.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/deploy/compose.production.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/ai-customer-service}"
VERIFY_SCRIPT="${SCRIPT_DIR}/verify_backup.sh"
QUIESCE_WRITES="${QUIESCE_WRITES:-true}"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

read_env_value() {
    local key="$1"
    awk -v key="${key}" '
        index($0, key "=") == 1 { value = substr($0, length(key) + 2) }
        END { sub(/\r$/, "", value); print value }
    ' "${ENV_FILE}"
}

[[ -f "${ENV_FILE}" ]] || die "environment file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "compose file not found: ${COMPOSE_FILE}"
[[ -x "${VERIFY_SCRIPT}" ]] || die "verification script is not executable: ${VERIFY_SCRIPT}"
require_command docker
require_command sha256sum

[[ -n "${BACKUP_ROOT}" && "${BACKUP_ROOT}" != "/" ]] || die "unsafe backup root"
mkdir -p -- "${BACKUP_ROOT}"
BACKUP_ROOT="$(cd -- "${BACKUP_ROOT}" && pwd -P)"
[[ -n "${BACKUP_ROOT}" && "${BACKUP_ROOT}" != "/" ]] || die "unsafe backup root"
chmod 700 "${BACKUP_ROOT}"

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
"${COMPOSE[@]}" config --quiet

running_services="$("${COMPOSE[@]}" ps --status running --services)"
grep -qx postgres <<<"${running_services}" || die "postgres service is not running"
grep -qx minio <<<"${running_services}" || die "minio service is not running"

backup_id="backup-$(date -u +'%Y%m%dT%H%M%SZ')-$$"
final_dir="${BACKUP_ROOT}/${backup_id}"
tmp_dir="$(mktemp -d "${BACKUP_ROOT}/.incomplete-${backup_id}.XXXXXX")"
api_was_running=false
worker_was_running=false
beat_was_running=false
services_resumed=false
resume_services() {
    local services=()
    [[ "${api_was_running}" == true ]] && services+=(api)
    [[ "${worker_was_running}" == true ]] && services+=(worker)
    [[ "${beat_was_running}" == true ]] && services+=(beat)
    if [[ ${#services[@]} -gt 0 ]]; then
        "${COMPOSE[@]}" up -d "${services[@]}" >/dev/null
    fi
    services_resumed=true
}
cleanup() {
    if [[ -n "${tmp_dir:-}" && -d "${tmp_dir}" ]]; then
        case "${tmp_dir}" in
            "${BACKUP_ROOT}"/.incomplete-*) rm -rf -- "${tmp_dir}" ;;
            *) printf 'ERROR: refusing to remove unsafe temporary path: %s\n' "${tmp_dir}" >&2 ;;
        esac
    fi
    if [[ "${services_resumed}" != true ]]; then
        resume_services
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p -- "${tmp_dir}/minio/bucket"

if [[ "${QUIESCE_WRITES}" == true ]]; then
    grep -qx api <<<"${running_services}" && api_was_running=true
    grep -qx worker <<<"${running_services}" && worker_was_running=true
    grep -qx beat <<<"${running_services}" && beat_was_running=true
    services_to_stop=()
    [[ "${api_was_running}" == true ]] && services_to_stop+=(api)
    [[ "${worker_was_running}" == true ]] && services_to_stop+=(worker)
    [[ "${beat_was_running}" == true ]] && services_to_stop+=(beat)
    if [[ ${#services_to_stop[@]} -gt 0 ]]; then
        printf 'Quiescing API, worker, and beat for a cross-store consistent backup...\n'
        "${COMPOSE[@]}" stop -t 60 "${services_to_stop[@]}" >/dev/null
    fi
elif [[ "${QUIESCE_WRITES}" != false ]]; then
    die "QUIESCE_WRITES must be true or false"
fi

printf 'Creating PostgreSQL logical backup...\n'
"${COMPOSE[@]}" exec -T postgres sh -eu -c '
    exec pg_dump \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --format=custom \
        --compress=9 \
        --no-owner \
        --no-acl
' >"${tmp_dir}/postgres.dump"
[[ -s "${tmp_dir}/postgres.dump" ]] || die "PostgreSQL dump is empty"

printf 'Mirroring MinIO bucket...\n'
"${COMPOSE[@]}" run --rm --no-deps \
    -v "${tmp_dir}/minio:/backup" \
    --entrypoint /bin/sh \
    minio-client -eu -c '
        mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
        mc stat "local/$APP_S3_BUCKET" >/dev/null
        mc mirror --overwrite --preserve "local/$APP_S3_BUCKET" /backup/bucket
    '

minio_object_count="$(find "${tmp_dir}/minio/bucket" -type f -print | wc -l | tr -d '[:space:]')"
[[ "${minio_object_count}" =~ ^[0-9]+$ ]] || die "invalid MinIO object count"
app_image="$(read_env_value APP_IMAGE)"
[[ -n "${app_image}" ]] || die "APP_IMAGE is missing from ${ENV_FILE}"

alembic_revision="$("${COMPOSE[@]}" run --rm --no-deps migrate \
    alembic current 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
git_commit="unknown"
if command -v git >/dev/null 2>&1 && git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_commit="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)"
fi

{
    printf 'FORMAT_VERSION=1\n'
    printf 'BACKUP_ID=%s\n' "${backup_id}"
    printf 'CREATED_AT_UTC=%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf 'APPLICATION_IMAGE=%s\n' "${app_image}"
    printf 'ALEMBIC_REVISION=%s\n' "${alembic_revision}"
    printf 'GIT_COMMIT=%s\n' "${git_commit}"
    printf 'MINIO_OBJECT_COUNT=%s\n' "${minio_object_count}"
    printf 'REDIS_INCLUDED=false\n'
} >"${tmp_dir}/metadata.env"

"${COMPOSE[@]}" config --images | LC_ALL=C sort -u >"${tmp_dir}/compose-images.txt"

(
    cd -- "${tmp_dir}"
    find . -type f ! -name SHA256SUMS -print0 \
        | LC_ALL=C sort -z \
        | xargs -0 sha256sum >SHA256SUMS
)
chmod -R go-rwx "${tmp_dir}"

ENV_FILE="${ENV_FILE}" COMPOSE_FILE="${COMPOSE_FILE}" \
    "${VERIFY_SCRIPT}" "${tmp_dir}"

[[ ! -e "${final_dir}" ]] || die "backup target already exists: ${final_dir}"
mv -- "${tmp_dir}" "${final_dir}"
tmp_dir=""
resume_services
trap - EXIT INT TERM

printf 'Backup completed: %s\n' "${final_dir}"
printf 'Copy this directory to encrypted off-host storage before considering the backup durable.\n'
