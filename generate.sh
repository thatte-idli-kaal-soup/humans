#!/usr/bin/env bash
set -euo pipefail

NAME=$1
USE_ORIGINAL="${2:---use-low-res}"

./scripts/process-video.py "${USE_ORIGINAL}" "projects/${NAME}.yml" clean-workdir
./scripts/process-video.py "${USE_ORIGINAL}" "projects/${NAME}.yml" process-clips
./scripts/process-video.py "${USE_ORIGINAL}" "projects/${NAME}.yml" combine-clips
