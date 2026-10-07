#!/bin/bash
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = arm64 ] || fail 'Mac Apple Silicon required.'
manifest="$root/portable/macos-arm64.json"
json() { /usr/bin/plutil -extract "$2" raw -o - "$1"; }
minimum="$(json "$manifest" minimumMacOS)"
major="$(/usr/bin/sw_vers -productVersion)"
[ "${major%%.*}" -ge "${minimum%%.*}" ] || fail "macOS $minimum or later required."
for path in .cache .cache/tmp .cache/downloads .cache/home .tools .tools/python .venv .playwright-browsers; do
    [ ! -L "$root/$path" ] || fail "Linked generated directory: $path"
done
export HOME="$root/.cache/home" TMPDIR="$root/.cache/tmp" TEMP="$root/.cache/tmp" TMP="$root/.cache/tmp"
export PYTHONNOUSERSITE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export PIP_CONFIG_FILE=/dev/null PIP_CACHE_DIR="$root/.cache/pip" PLAYWRIGHT_BROWSERS_PATH="$root/.playwright-browsers"
export PATH=/usr/bin:/bin:/usr/sbin:/sbin COPYFILE_DISABLE=1
unset PYTHONHOME PYTHONPATH DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES NODE_OPTIONS NODE_PATH
/bin/mkdir -p "$TMPDIR" "$HOME" "$root/.cache/downloads" "$root/.tools"
python="$root/.tools/python/bin/python3"
version="$(json "$manifest" python.version)"
ready=false
if [ -x "$python" ] && [ "$("$python" -E -s -c 'import sys,ssl,sqlite3,venv,ensurepip; print(sys.version.split()[0])' 2>/dev/null)" = "$version" ]; then
    ready=true
fi
if [ "$ready" = false ]; then
    for arg in "$@"; do [ "$arg" != --check ] || fail 'Not ready. Run ./start.sh.'; done
    if [ -x "$python" ]; then
        "$python" -E -s -c 'import fcntl,sys; f=open(sys.argv[1],"a+b"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)' "$root/.cache/runtime.lock" || fail 'Runtime is in use. Stop BOOTH-Reader first.'
    fi
    vendor="$root/vendor/macos-arm64"
    index="$vendor/manifest.json"
    [ -f "$index" ] || fail 'Mac vendor payload missing. Clone the complete repository.'
    archive="$root/.cache/downloads/$(json "$manifest" python.asset)"
    expected="$(json "$manifest" python.sha256)"
    hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/cut -d ' ' -f 1; }
    work="$(/usr/bin/mktemp -d "$TMPDIR/bootstrap.XXXXXXXX")"
    trap '/bin/rm -rf "$work"' EXIT
    joined="$work/python.tar.gz"
    : > "$joined"
    i=0
    while file="$(json "$index" "assets.python.parts.$i.file" 2>/dev/null)"; do
        case "$file" in */*|*..*) fail 'Invalid vendor chunk path.';; esac
        [ ! -L "$vendor/$file" ] || fail 'Linked vendor chunk.'
        [ "$(hash "$vendor/$file")" = "$(json "$index" "assets.python.parts.$i.sha256")" ] || fail 'Vendor chunk hash mismatch.'
        /bin/cat "$vendor/$file" >> "$joined"
        i=$((i + 1))
    done
    [ "$i" -gt 0 ] && [ "$(hash "$joined")" = "$expected" ] || fail 'Python publisher hash mismatch.'
    /bin/mv "$joined" "$archive"
    /usr/bin/tar -xzf "$archive" -C "$work"
    candidate="$work/python/bin/python3"
    "$candidate" -E -s -c 'import ssl,sqlite3,venv,ensurepip' || fail 'Python self-check failed.'
    backup="$work/previous-python"
    if [ -e "$root/.tools/python" ]; then /bin/mv "$root/.tools/python" "$backup"; fi
    /bin/mv "$work/python" "$root/.tools/python"
fi
cd "$root"
if [ "$ready" = false ]; then
    result=0
    "$python" -E -s -X utf8 "$root/tools/manage_portable.py" auto "$@" || result=$?
    if [ "$result" -ne 0 ] && [ -d "$backup" ]; then
        /bin/rm -rf "$root/.tools/python"
        /bin/mv "$backup" "$root/.tools/python"
    fi
    exit "$result"
fi
exec "$python" -E -s -X utf8 "$root/tools/manage_portable.py" auto "$@"
