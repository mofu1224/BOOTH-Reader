#!/bin/bash
# Developer/CI-only personal-use browser. Nothing here is packaged by vendor_payload.
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
cd "$root"
mkdir -p .cache/tmp .cache/home .cache/downloads
export HOME="$root/.cache/home" TMPDIR="$root/.cache/tmp" COPYFILE_DISABLE=1
image=.cache/downloads/ui-test-driver.dmg
if [ ! -f "$image" ]; then
    /usr/bin/curl --fail --location --output "$image" https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg
fi
mount="$root/.cache/ui-driver-mount"
[ ! -e "$mount" ] || { printf 'Test mount path already exists.\n' >&2; exit 1; }
mkdir "$mount"
trap '/usr/bin/hdiutil detach "$mount" >/dev/null 2>&1 || true; /bin/rmdir "$mount" 2>/dev/null || true' EXIT
/usr/bin/hdiutil verify "$image" >/dev/null
/usr/bin/hdiutil attach -readonly -nobrowse -noautoopen -mountpoint "$mount" "$image" >/dev/null
app="$mount/Google Chrome.app"
/usr/bin/codesign --verify --deep --strict -R '=anchor apple generic and certificate leaf[subject.OU] = "EQHXZ8M8AV"' "$app"
/usr/sbin/spctl --assess --type execute "$app"
mkdir -p .cache/ui-test-driver
/usr/bin/ditto "$app" '.cache/ui-test-driver/Google Chrome.app'
printf 'Signature-verified UI test driver ready in ignored .cache; not redistributed.\n'
