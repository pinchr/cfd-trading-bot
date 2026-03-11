#!/usr/bin/env python3
"""
CFD Trading Bot - Continuous Test & Fix Workflow
Runs every 30 minutes via cron

Spawns subagents for:
1. Testing (CFD-Tester)
2. Fixing bugs (CFD-Executor)
3. Retesting (CFD-Retester)

Cron setup:
*/30 * * * * cd /Users/pinchr/dev/cfd-trading-bot && python3 scripts/cfd_workflow.py >> logs/workflow.log 2>&1
"""

import os
import sys
import time
import json
import subprocess
import requests
from datetime import datetime

PROJECT_DIR = "/Users/pinchr/dev/cfd-trading-bot"
LOG_FILE = f"{PROJECT_DIR}/logs/workflow.log"
API_BASE = "http://localhost:8001/api"

def log(message: str):
    """Log to file and stdout"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def check_services() -> bool:
    """Check if backend and frontend are running"""
    log("Checking services...")
    
    try:
        # Check backend
        r = requests.get(f"{API_BASE}/account", timeout=5)
        if r.status_code != 200:
            log(f"WARNING: Backend returned {r.status_code}")
            return False
    except Exception as e:
        log(f"WARNING: Backend not responding: {e}")
        return False
    
    # Check frontend
    try:
        r = requests.get("http://localhost:5173/cfd", timeout=5)
        if r.status_code != 200:
            log(f"WARNING: Frontend returned {r.status_code}")
    except Exception as e:
        log(f"WARNING: Frontend not responding: {e}")
        return False
    
    log("Services OK")
    return True

def run_api_tests() -> dict:
    """Run basic API tests"""
    results = {
        "api": False,
        "signals": False,
        "positions": False,
        "chart": False,
        "account": False
    }
    
    # Test account
    try:
        r = requests.get(f"{API_BASE}/account", timeout=5)
        data = r.json()
        if "account" in data and "balance_usd" in data["account"]:
            results["api"] = True
            results["account"] = True
            log(f"Account: ${data['account'].get('balance_usd', 0):.2f}")
    except Exception as e:
        log(f"API test failed: {e}")
    
    # Test signals
    try:
        r = requests.get(f"{API_BASE}/signals", timeout=10)
        if r.status_code == 200:
            results["signals"] = True
            signals = r.json().get("signals", [])
            log(f"Signals: {len(signals)} symbols")
    except Exception as e:
        log(f"Signals test failed: {e}")
    
    # Test positions
    try:
        r = requests.get(f"{API_BASE}/trades/open", timeout=5)
        if r.status_code == 200:
            results["positions"] = True
            data = r.json()
            positions = data.get("positions", [])
            log(f"Open positions: {len(positions)}")
    except Exception as e:
        log(f"Positions test failed: {e}")
    
    # Test chart
    try:
        r = requests.get(f"{API_BASE}/chart/BTC?resolution=60&count=10", timeout=10)
        if r.status_code == 200:
            results["chart"] = True
    except Exception as e:
        log(f"Chart test failed: {e}")
    
    return results

def check_subagent_running() -> bool:
    """Check if any CFD subagents are currently running"""
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout + result.stderr
        # Check for active subagent sessions
        if "CFD" in output or "subagent" in output.lower():
            # Check if it's from last few minutes
            if "seconds" in output or "minutes" in output:
                return True
    except Exception as e:
        log(f"Could not check subagent status: {e}")
    
    return False

def spawn_subagent(agent_type: str, task: str) -> str:
    """Spawn a subagent using OpenClaw sessions_spawn"""
    
    label_map = {
        "tester": "CFD-Tester",
        "executor": "CFD-Executor", 
        "retester": "CFD-Retester"
    }
    
    label = label_map.get(agent_type, f"CFD-{agent_type}")
    
    # This would use the sessions_spawn tool in production
    # For now, log what would be spawned
    log(f"Would spawn {label} with task: {task[:100]}...")
    
    # In production, this would call the OpenClaw API
    # For now, return a placeholder
    return f"subagent-{agent_type}-{int(time.time())}"

def add_test_scenario(bug_description: str, section: str):
    """Add a new test scenario to test_scenarios.md"""
    log(f"Adding test scenario: {bug_description}")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    scenario = f"""

---

### New Test (Auto-Generated {timestamp})

**Bug:** {bug_description}

**Section:** {section}

**Steps:**
1. [ ] Describe reproduction steps
2. [ ] Verify expected behavior
3. [ ] Check API response

**Expected:** What should happen

**Actual:** What actually happens

**Status:** TO TEST

"""
    
    with open(f"{PROJECT_DIR}/TEST_SCENARIOS.md", "a") as f:
        f.write(scenario)
    
    # Git commit
    try:
        subprocess.run(["git", "add", "TEST_SCENARIOS.md"], cwd=PROJECT_DIR, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"test: add auto scenario for {bug_description[:50]}"],
            cwd=PROJECT_DIR,
            check=False
        )
    except Exception as e:
        log(f"Git commit failed: {e}")

def main():
    """Main workflow"""
    log("=" * 50)
    log("Starting CFD Workflow")
    log("=" * 50)
    
    # Check services
    if not check_services():
        log("ERROR: Services not available, exiting")
        sys.exit(1)
    
    # Run tests
    log("Running API tests...")
    results = run_api_tests()
    
    # Log results
    passed = sum(results.values())
    total = len(results)
    log(f"Tests: {passed}/{total} passed")
    
    # Check for failures
    failures = [k for k, v in results.items() if not v]
    
    if failures:
        log(f"FAILED: {', '.join(failures)}")
        
        # Add test scenarios for each failure
        for failure in failures:
            add_test_scenario(
                f"API endpoint {failure.upper()} not working",
                "1. DASHBOARD"
            )
        
        # Check if we can spawn executor
        if not check_subagent_running():
            log("Spawning executor subagent...")
            spawn_subagent("executor", "Fix API failures")
        else:
            log("Subagent busy, skipping executor spawn")
    else:
        log("All tests PASSED!")
    
    log("=" * 50)
    log("Workflow complete")
    log("=" * 50)

if __name__ == "__main__":
    main()
