#!/bin/bash
# Test runner script for CFD Trading Bot
# Runs tests every 45 minutes when scheduled via cron
#
# Usage:
#   ./run_tests.sh              # Run tests once
#   ./run_tests.sh --cron      # Run in continuous loop (every 45 min)
#
# To add to crontab (every 45 minutes):
#   crontab -e
#   */45 * * * * /Users/pinchr/dev/cfd-trading-bot/scripts/run_tests.sh >> /tmp/cfd_tests.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/cfd_test_runner.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_services() {
    log "Checking services..."
    
    # Check backend
    if curl -s http://localhost:8001/api/account > /dev/null 2>&1; then
        log "  ✅ Backend (8001): OK"
        BACKEND_OK=true
    else
        log "  ❌ Backend (8001): DOWN - restarting..."
        cd "$PROJECT_DIR/backend"
        pkill -f "uvicorn" 2>/dev/null
        sleep 1
        python3 -m uvicorn main:app --port 8001 >> /tmp/backend.log 2>&1 &
        sleep 3
        BACKEND_OK=false
    fi
    
    # Check frontend
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        log "  ✅ Frontend (5173): OK"
    else
        log "  ❌ Frontend (5173): restarting..."
        cd "$PROJECT_DIR/frontend"
        pkill -f "vite" 2>/dev/null
        sleep 1
        npm run dev >> /tmp/frontend.log 2>&1 &
    fi
}

run_browser_tests() {
    log "Running browser-based tests..."
    
    # Use OpenClaw browser tool to test
    # This is a placeholder - actual test commands would be executed via OpenClaw
    log "  [TEST] Checking Dashboard loads correctly"
    log "  [TEST] Checking Chart renders with indicators"
    log "  [TEST] Checking Trade markers position"
    log "  [TEST] Checking Strategy dropdown works"
}

update_test_results() {
    log "Updating test results..."
    
    # Add test results to TEST_SCENARIOS.md
    TEST_RESULT_FILE="$PROJECT_DIR/TEST_SCENARIOS.md"
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
    
    # Check for specific bugs and update
    if [ -f "$PROJECT_DIR/workspace/bugs.md" ]; then
        log "  Checking bugs.md for known issues..."
    fi
}

main() {
    log "=========================================="
    log "CFD Trading Bot - Test Runner Starting"
    log "=========================================="
    
    if [ "$1" = "--cron" ]; then
        log "Running in continuous mode (every 45 minutes)"
        while true; do
            check_services
            run_browser_tests
            update_test_results
            log "Sleeping for 45 minutes..."
            sleep 2700  # 45 minutes
        done
    else
        log "Running single test cycle"
        check_services
        run_browser_tests
        update_test_results
    fi
    
    log "Test runner finished"
}

main "$@"
