#!/usr/bin/env bash
# Secret scanner - blocks commits containing hardcoded credentials.
#
# WHY: on 2026-10-28 the Atlas password was found hardcoded in 10 tracked
# source files of a PUBLIC GitHub repo (since 2026-02-24). monitor.sh runs
# `git add -A && git commit` on every backend restart, so a stray .env backup
# would have been committed automatically.
#
# Usage:
#   scripts/secret_scan.sh            -> scan files staged for commit
#   scripts/secret_scan.sh <file>...  -> scan specific files
#
# Exit 0 = clean, 1 = secrets found (commit must be blocked).

set -uo pipefail

PATTERNS='mongodb\+srv://[A-Za-z0-9_.-]+:[^"'"'"'[:space:]]+@|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'

# Values that are clearly placeholders, not real credentials.
PLACEHOLDER='user:pass|<password>|<your|xxxx|CHANGEME|your_password|example\.com|placeholder'

fail=0
report() {
    local f="$1"
    # Strip allowed placeholder forms before matching.
    if sed -E 's#(mongodb\+srv://)(user:pass|<[^>]*>)[^@"]*@#\1\2@#g' "$f" \
       | grep -nE "$PATTERNS" \
       | grep -vE "$PLACEHOLDER" >/dev/null 2>&1; then
        echo "❌ SECRET DETECTED in: $f" >&2
        sed -E 's#(mongodb\+srv://)([^:]+):[^@"]+@#\1\2:***REDACTED***@#g; s#(ghp_|github_pat_|sk-|AIza)[A-Za-z0-9_-]+#\1***REDACTED***#g' "$f" \
            | grep -nE "$PATTERNS" | head -5 >&2
        fail=1
    fi
}

if [ "$#" -gt 0 ]; then
    for f in "$@"; do [ -f "$f" ] && report "$f"; done
else
    # Only files actually staged for commit (respects gitignore).
    # NOTE: use command substitution, NOT a pipe - a pipe would run the loop
    # in a subshell and the `fail` flag would be lost (silent pass).
    STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
    for f in $STAGED; do
        [ -f "$f" ] && report "$f"
    done
fi

if [ "$fail" -eq 1 ]; then
    echo "" >&2
    echo "🚫 Commit blocked: hardcoded credential(s) detected." >&2
    echo "   Fix: use os.getenv(\"MONGO_URI\", ...) / os.environ, never inline the URI." >&2
    echo "   Then rotate the exposed credential - it is already public if this repo is public." >&2
    exit 1
fi

echo "✅ secret scan clean"
exit 0
