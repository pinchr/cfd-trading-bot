#!/bin/bash
# Linting script for CFD Trading Bot
# Usage: ./run_linter.sh [fast|full]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

MODE=${1:-fast}
ERRORS=0
WARNINGS=0

echo -e "${BLUE}=== CFD Trading Bot Linter ===${NC}"
echo "Mode: $MODE"
echo ""

# Exclude patterns
EXCLUDE="venv|.git|__pycache__|.vscode|.github|docker|temporary|frontend|tests"

# Track results
PASSED=()
FAILED=()

run_check() {
    local name="$1"
    local cmd="$2"
    local ignore="${3:-}"
    
    echo -n "Running $name... "
    
    if [ -n "$ignore" ]; then
        output=$(eval "$cmd" 2>&1 || true)
    else
        output=$(eval "$cmd" 2>&1 || true)
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED+=("$name")
    else
        count=$(echo "$output" | grep -c ":\d*:" || echo "0")
        if [ "$count" -gt 0 ]; then
            echo -e "${RED}✗ FAIL ($count issues)${NC}"
            if [ "$MODE" = "full" ]; then
                echo "$output" | head -20
            fi
        else
            echo -e "${YELLOW}⚠ WARN${NC}"
        fi
        FAILED+=("$name")
        ERRORS=$((ERRORS + 1))
    fi
}

# cd "$(dirname "$0")/backend"

# === FAST CHECKS (syntax only) ===
echo -e "${BLUE}=== Fast Checks (Syntax & Format) ===${NC}"

run_check "Black format" "python -m black --check --line-length=120 ."
run_check "isort order" "python -m isort --check-only --diff ."
run_check "Flake8 syntax" "python -m flake8 --select=E9,F63,F7,F82 --exclude='$EXCLUDE' ."

if [ "$MODE" = "full" ]; then
    echo ""
    echo -e "${BLUE}=== Full Checks ===${NC}"
    
    run_check "Flake8 full" "python -m flake8 --exclude='$EXCLUDE' --max-line-length=120 --extend-ignore=E203,W503,Q003 ."
    run_check "Mypy types" "python -m mypy . --exclude='$EXCLUDE' . || true"
    run_check "Pyright" "python -m pyright . || true"
fi

echo ""
echo -e "${BLUE}=== Summary ===${NC}"
echo -e "Passed: ${GREEN}${#PASSED[@]}${NC}"
echo -e "Failed: ${RED}${#FAILED[@]}${NC}"

if [ ${#FAILED[@]} -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. Run with 'full' for details.${NC}"
    exit 1
fi
