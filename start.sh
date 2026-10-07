#!/bin/bash
set -e
root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
exec /bin/bash "$root/tools/bootstrap.sh" "$@"
