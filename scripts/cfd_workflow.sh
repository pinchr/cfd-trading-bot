#!/bin/bash
# CFD Trading Bot - Continuous Test & Fix Workflow
# Runs every 30 minutes via cron
# 
# Cron setup:
# */30 * * * * /Users/pinchr/dev/cfd-trading-bot/scripts/cfd_workflow.sh >> /Users/pinchr/dev/cfd-trading-bot/logs/workflow.log 2>&1

set -e

LOG_FILE="/Users/pinchr/dev/cfd-trading-bot/logs/workflow.log"
PROJECT_DIR="/Users/pinchr/dev/cfd-trading-bot"
cd "$PROJECT_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if services are running
check_services() {
    log "Checking services..."
    
    # Check backend
    if ! curl -s http://localhost:8001/api/account > /dev/null 2>&1; then
        log "WARNING: Backend not responding on port 8001"
        return 1
    fi
    
    # Check frontend
    if ! curl -s http://localhost:5173/cfd > /dev/null 2>&1; then
        log "WARNING: Frontend not responding on port 5173"
        return 1
    fi
    
    log "Services OK"
    return 0
}

# Run tests via subagent
run_tests() {
    log "Starting test subagent..."
    
    # This would be replaced with actual subagent spawn in production
    # For now, we'll use curl to test basic API endpoints
    
    local test_results=""
    
    # Test 1: API health
    if curl -s http://localhost:8001/api/account | grep -q "balance_usd"; then
        test_results+="PASS:API "
    else
        test_results+="FAIL:API "
    fi
    
    # Test 2: Signals
    if curl -s http://localhost:8001/api/signals | grep -q "signals"; then
        test_results+="PASS:Signals "
    else
        test_results+="FAIL:Signals "
    fi
    
    # Test 3: Open positions
    if curl -s http://localhost:8001/api/trades/open | grep -q "positions"; then
        test_results+="PASS:Positions "
    else
        test_results+="FAIL:Positions "
    fi
    
    # Test 4: Chart data
    if curl -s "http://localhost:8001/api/chart/BTC?resolution=60&count=10" | grep -q "candles\|data"; then
        test_results+="PASS:Chart "
    else
        test_results+="FAIL:Chart "
    fi
    
    log "Test results: $test_results"
    echo "$test_results"
}

# Check for subagent availability
check_subagent_available() {
    # Check if subagent is already running
    local active_agents=$(openclaw sessions list 2>/dev/null | grep -c "subagent" || echo "0")
    
    if [ "$active_agents" -gt 0 ]; then
        log "Subagents busy: $active_agents running"
        return 1
    fi
    
    log "Subagent available"
    return 0
}

# Add new test scenario if bug found
add_test_scenario() {
    local bug_description="$1"
    local test_section="$2"
    
    log "Adding new test scenario: $bug_description"
    
    # Append to test_scenarios.md
    cat >> "$PROJECT_DIR/TEST_SCENARIOS.md" << EOF

---

### New Test (Auto-Generated $(date '+%Y-%m-%d %H:%M'))

**Bug:** $bug_description

**Test Section:** $test_section

**Steps:**
1. [ ] Describe test steps
2. [ ] Verify expected behavior

EOF
    
    git -C "$PROJECT_DIR" add TEST_SCENARIOS.md
    git -C "$PROJECT_DIR" commit -m "test: add auto-generated scenario for $bug_description" || true
}

# Main workflow
main() {
    log "========================================="
    log "Starting CFD Workflow"
    log "========================================="
    
    # Check services
    if ! check_services; then
        log "ERROR: Services not available, skipping workflow"
        exit 1
    fi
    
    # Run tests
    local results=$(run_tests)
    
    # Check if any tests failed
    if echo "$results" | grep -q "FAIL"; then
        log "Some tests failed, analyzing..."
        
        # Try to get more details
        local failed_tests=$(echo "$results" | grep -o "FAIL:[^ ]*" | tr '\n' ', ')
        log "Failed: $failed_tests"
        
        # Add new test scenarios for failures
        if echo "$failed_tests" | grep -q "API"; then
            add_test_scenario "API endpoint not responding correctly" "1. DASHBOARD"
        fi
        
        # Check subagent availability and spawn executor if needed
        if check_subagent_available; then
            log "Would spawn executor subagent (not implemented in bash)"
            # In production: spawn subagent to fix issues
        fi
    else
        log "All tests passed!"
    fi
    
    log "Workflow complete"
    log "========================================="
}

# Run main
main "$@"
