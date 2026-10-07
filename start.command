#!/bin/bash
root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
/bin/bash "$root/start.sh" "$@"
result=$?
if [ "$result" -ne 0 ] && [ "$result" -ne 130 ]; then
    printf '\nStartup failed (%s). Press Enter to close.\n' "$result" >&2
    read -r _
fi
exit "$result"
