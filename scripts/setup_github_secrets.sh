#!/usr/bin/env bash
# One-time helper: push the secrets the macOS build workflow needs to GitHub.
#
# Reads DEVELOPER_ID_APP / NOTARY_* from .env.local, generates a throwaway
# keychain password, and imports your exported Developer ID .p12. No secret
# values are stored in this script — it only reads .env.local and prompts.
#
# Prereqs:
#   1. `gh` authenticated as the account that owns the repo:
#          gh auth login          # pick GitHub.com, your personal account
#          gh auth switch         # if you have multiple accounts
#   2. Export your Developer ID Application cert *with its private key*:
#          Keychain Access → My Certificates → right-click the
#          "Developer ID Application: … (TEAMID)" → Export → save as a .p12
#
# Usage:
#   ./scripts/setup_github_secrets.sh /path/to/cert.p12
set -euo pipefail

REPO="${REPO:-hdavid/stemgen}"
P12="${1:?usage: $0 /path/to/cert.p12}"
ENV_FILE="${ENV_FILE:-.env.local}"

[ -f "$ENV_FILE" ] || { echo "✗ $ENV_FILE not found" >&2; exit 1; }
[ -f "$P12" ]      || { echo "✗ p12 not found: $P12" >&2; exit 1; }

# ── Sanity: right account / repo reachable ───────────────────────────────────
echo "▶ target repo: $REPO"
if ! gh repo view "$REPO" >/dev/null 2>&1; then
    echo "✗ gh cannot access $REPO." >&2
    echo "  Run: gh auth login   (and gh auth switch to your personal account)" >&2
    exit 1
fi

# ── Pull the four values already in .env.local ───────────────────────────────
# Parse line-by-line rather than sourcing: .env.local is Make syntax and
# DEVELOPER_ID_APP holds spaces + parens (e.g. "… (TEAMID)") which break shell
# `source` (the parens glob, the spaces split into commands).
envval() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
DEVELOPER_ID_APP="$(envval DEVELOPER_ID_APP)"
NOTARY_APPLE_ID="$(envval NOTARY_APPLE_ID)"
NOTARY_TEAM_ID="$(envval NOTARY_TEAM_ID)"
NOTARY_PASSWORD="$(envval NOTARY_PASSWORD)"
: "${DEVELOPER_ID_APP:?missing in $ENV_FILE}"
: "${NOTARY_APPLE_ID:?missing in $ENV_FILE}"
: "${NOTARY_TEAM_ID:?missing in $ENV_FILE}"
: "${NOTARY_PASSWORD:?missing in $ENV_FILE}"

# ── Cert password (prompted, never echoed) ───────────────────────────────────
read -r -s -p "Password you set when exporting the .p12: " P12_PWD; echo

# ── Push everything ──────────────────────────────────────────────────────────
echo "▶ setting secrets on $REPO"
gh secret set DEVELOPER_ID_APP    --repo "$REPO" --body "$DEVELOPER_ID_APP"
gh secret set NOTARY_APPLE_ID     --repo "$REPO" --body "$NOTARY_APPLE_ID"
gh secret set NOTARY_TEAM_ID      --repo "$REPO" --body "$NOTARY_TEAM_ID"
gh secret set NOTARY_PASSWORD     --repo "$REPO" --body "$NOTARY_PASSWORD"
gh secret set MACOS_CERTIFICATE_PWD --repo "$REPO" --body "$P12_PWD"
gh secret set KEYCHAIN_PASSWORD     --repo "$REPO" --body "$(openssl rand -base64 24)"
gh secret set MACOS_CERTIFICATE_P12 --repo "$REPO" --body "$(base64 -i "$P12")"

echo "✓ all 7 secrets set on $REPO"
echo "  verify:  gh secret list --repo $REPO"
