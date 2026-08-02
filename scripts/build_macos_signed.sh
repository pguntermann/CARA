#!/usr/bin/env bash
# Build, Developer ID–sign, notarize, and staple CARA.app for website distribution.
#
# Prerequisites (local machine only — never commit these):
#   - Developer ID Application certificate + private key in login Keychain
#   - notarytool keychain profile (e.g. created with:
#       xcrun notarytool store-credentials "CARA" --apple-id … --team-id … --password …)
#
# This script intentionally contains NO passwords, API keys, or .p12 material.
# Only public identifiers (identity display name, team id in that name, profile name).
#
# Usage (from repo root):
#   ./scripts/build_macos_signed.sh
#
# Optional env overrides:
#   CARA_CODESIGN_IDENTITY   default: Developer ID Application: Philipp Guntermann (7ZWX577M73)
#   CARA_NOTARY_PROFILE      default: CARA
#   CARA_BUNDLE_IDENTIFIER   default: com.pguntermann.cara
#   CARA_ENTITLEMENTS        default: packaging/macos/entitlements.plist
#   CARA_SKIP_NOTARIZE=1     build+sign only (no notarytool / staple)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IDENTITY="${CARA_CODESIGN_IDENTITY:-Developer ID Application: Philipp Guntermann (7ZWX577M73)}"
NOTARY_PROFILE="${CARA_NOTARY_PROFILE:-CARA}"
ENTITLEMENTS="${CARA_ENTITLEMENTS:-$ROOT/packaging/macos/entitlements.plist}"
APP="$ROOT/dist/CARA.app"
PYTHON="${ROOT}/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "error: expected venv Python at $PYTHON" >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "error: entitlements not found: $ENTITLEMENTS" >&2
  exit 1
fi
if ! security find-identity -v -p codesigning | grep -F "$IDENTITY" >/dev/null; then
  echo "error: codesigning identity not found in Keychain:" >&2
  echo "  $IDENTITY" >&2
  echo "Run: security find-identity -v -p codesigning" >&2
  exit 1
fi

VERSION="$("$PYTHON" -c "import json; print(json.load(open('app/config/config.json'))['version'])")"
echo "==> Building CARA ${VERSION} (signed PyInstaller pass)"

export CARA_CODESIGN_IDENTITY="$IDENTITY"
export CARA_ENTITLEMENTS="$ENTITLEMENTS"
export CARA_BUNDLE_IDENTIFIER="${CARA_BUNDLE_IDENTIFIER:-com.pguntermann.cara}"

"$PYTHON" -m PyInstaller CARA_macos.spec -y

if [[ ! -d "$APP" ]]; then
  echo "error: expected app bundle at $APP" >&2
  exit 1
fi

echo "==> Deep-signing with Hardened Runtime + timestamp"
# Authoritative sign of the finished .app (inside-out via --deep).
codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" \
  "$APP"

echo "==> Verifying signature"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -dv --verbose=2 "$APP" 2>&1 | grep -E 'Authority|TeamIdentifier|Runtime' || true

if [[ "${CARA_SKIP_NOTARIZE:-}" == "1" ]]; then
  echo "==> Skipping notarization (CARA_SKIP_NOTARIZE=1)"
  echo "Signed app: $APP"
  exit 0
fi

NOTARY_ZIP="$ROOT/dist/CARA-notarize.zip"
DIST_ZIP="$ROOT/dist/CARA.${VERSION}.macOS.AppBundle.zip"
rm -f "$NOTARY_ZIP"

echo "==> Creating zip for notarytool"
# ditto (not zip) for a proper .app archive. Omit resource forks / xattrs so the
# archive does not embed AppleDouble "._*" entries (Finder unzip materializes
# those as real files and breaks the code signature seal).
ditto -c -k --norsrc --noextattr --keepParent "$APP" "$NOTARY_ZIP"

echo "==> Submitting to Apple notary service (profile: ${NOTARY_PROFILE})"
# Credentials come from Keychain profile — never from this repo.
xcrun notarytool submit "$NOTARY_ZIP" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait

echo "==> Stapling notarization ticket"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

echo "==> Creating distribution zip"
rm -f "$DIST_ZIP"
ditto -c -k --norsrc --noextattr --keepParent "$APP" "$DIST_ZIP"
rm -f "$NOTARY_ZIP"

echo
echo "Done."
echo "  App:  $APP"
echo "  Zip:  $DIST_ZIP"
echo "Gatekeeper check (optional): spctl --assess --type execute -vv \"$APP\""
