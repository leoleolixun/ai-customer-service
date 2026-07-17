#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <image:tag-or-digest>" >&2
  exit 2
fi

work_dir="$(mktemp -d)"
container_id=""
cleanup() {
  if [ -n "$container_id" ]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT INT TERM

container_id="$(docker create "$1")"
docker export "$container_id" --output "$work_dir/rootfs.tar"
mkdir -p "$work_dir/rootfs"
tar -xf "$work_dir/rootfs.tar" -C "$work_dir/rootfs"
uv run python scripts/check_secrets.py --path "$work_dir/rootfs/app"
