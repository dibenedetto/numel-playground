#!/bin/sh

set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <image-tag> <dockerfile-path> <stamp-file>" >&2
  exit 2
fi

IMAGE_TAG="$1"
DOCKERFILE_PATH="$2"
STAMP_FILE="$3"
DOCKER_HOST_URL="${NUMEL_DOCKER_HOST:-tcp://docker:2375}"
SRC_ROOT="${NUMEL_RUNTIME_SOURCE_ROOT:-/src}"

if [ ! -d "$SRC_ROOT" ]; then
  echo "runtime builder source root not found: $SRC_ROOT" >&2
  exit 1
fi

mkdir -p "$(dirname "$STAMP_FILE")"
TMP_STAMP="$(mktemp)"

(
  cd "$SRC_ROOT"
  {
    printf '%s\0' ".dockerignore" "README.md" "pyproject.toml" "$DOCKERFILE_PATH"
    find app runtime contrib -type f -print0
  } \
    | sort -z \
    | xargs -0 sha256sum
) | sha256sum | awk '{print $1}' > "$TMP_STAMP"

CURRENT_HASH="$(cat "$TMP_STAMP")"
PREVIOUS_HASH=""
if [ -f "$STAMP_FILE" ]; then
  PREVIOUS_HASH="$(cat "$STAMP_FILE")"
fi

if [ "$CURRENT_HASH" = "$PREVIOUS_HASH" ] \
  && docker -H "$DOCKER_HOST_URL" image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "runtime image $IMAGE_TAG is up to date ($CURRENT_HASH)"
  rm -f "$TMP_STAMP"
  exit 0
fi

echo "rebuilding runtime image $IMAGE_TAG"
echo "runtime source hash: $CURRENT_HASH"
docker -H "$DOCKER_HOST_URL" build -f "$DOCKERFILE_PATH" -t "$IMAGE_TAG" "$SRC_ROOT"
mv "$TMP_STAMP" "$STAMP_FILE"