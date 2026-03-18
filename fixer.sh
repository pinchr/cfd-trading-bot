#!/bin/bash
# CFD Bot Fixer Cron - Runs every 30 minutes to check and fix errors
# Usage: Add to crontab -e: */30 * * * * /Users/pinchr/dev/cfd-trading-bot/fixer.sh >> /Users/pinchr/dev/cfd-trading-bot/logs/fixer.log 2>&1

LOG_FILE="/Users/pinchr/dev/cfd-trading-bot/logs/fixer.log"
FIXES_FILE="/Users/pinchr/dev/cfd-trading-bot/FIXES.md"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "🔧 FIXER RUN - Checking for errors..."

# Check if services are running
check_service() {
    local port=$1
    local name=$2
    if lsof -i:$port > /dev/null 2>&1; then
        log "✅ $name running on port $port"
        return 0
    else
        log "❌ $name NOT running on port $port"
        return 1
    fi
}

ISSUES_FOUND=0

# 1. Check Frontend (Vite on 5173)
if ! check_service 5173 "Frontend"; then
    log "Frontend not running - attempting to start..."
    cd /Users/pinchr/dev/cfd-trading-bot/frontend
    nohup npm run dev > /tmp/frontend.log 2>&1 &
    sleep 5
    if check_service 5173 "Frontend"; then
        log "✅ Frontend restarted successfully"
        echo "
## 🔧 Frontend Auto-Restart ($TIMESTAMP)
**Status:** ✅ Fixed

**Problem:** Frontend not responding on port 5173

**Fix:** Restarted npm run dev

**Verification:** Service now running
" >> "$FIXES_FILE"
    else
        log "❌ Failed to restart frontend"
        ISSUES_FOUND=1
    fi
fi

# 2. Check Backend (FastAPI on 8001)
if ! check_service 8001 "Backend"; then
    log "Backend not running - attempting to start..."
    cd /Users/pinchr/dev/cfd-trading-bot/backend
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
    sleep 5
    if check_service 8001 "Backend"; then
        log "✅ Backend restarted successfully"
        echo "
## 🔧 Backend Auto-Restart ($TIMESTAMP)
**Status:** ✅ Fixed

**Problem:** Backend not responding on port 8001

**Fix:** Restarted uvicorn server

**Verification:** Service now running
" >> "$FIXES_FILE"
    else
        log "❌ Failed to restart backend"
        ISSUES_FOUND=1
    fi
fi

# 3. Check Backend API health
if check_service 8001 "Backend"; then
    log "Checking backend API health..."
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health 2>/dev/null || echo "000")
    if [ "$HEALTH" = "200" ]; then
        log "✅ Backend API healthy"
    else
        log "⚠️ Backend API returned $HEALTH"
        # Try account endpoint as fallback
        ACCOUNT=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/account 2>/dev/null || echo "000")
        if [ "$ACCOUNT" = "200" ]; then
            log "✅ Backend API responding (account endpoint OK)"
        else
            log "❌ Backend API not responding properly"
            ISSUES_FOUND=1
        fi
    fi
fi

# 4. Check for frontend build errors (TypeScript)
log "Checking for frontend build errors..."
cd /Users/pinchr/dev/cfd-trading-bot/frontend
BUILD_OUTPUT=$(npm run build 2>&1 | tail -20)
if echo "$BUILD_OUTPUT" | grep -q "error"; then
    log "❌ Frontend build errors detected:"
    echo "$BUILD_OUTPUT" | tee -a "$LOG_FILE"
    
    # Try to identify the error
    ERROR_MSG=$(echo "$BUILD_OUTPUT" | grep -E "error|Error" | head -3)
    echo "
## 🔧 Frontend Build Error ($TIMESTAMP)
**Status:** ⚠️ Needs Manual Fix

**Problem:** $ERROR_MSG

**Full Output:**
\`\`\`
$BUILD_OUTPUT
\`\`\`
" >> "$FIXES_FILE"
    ISSUES_FOUND=1
else
    log "✅ Frontend build clean"
fi

# 5. Check MongoDB connection
log "Checking MongoDB connection..."
MONGO_TEST=$(python3 -c "
import sys
sys.path.insert(0, '/Users/pinchr/dev/cfd-trading-bot/backend')
try:
    from database import load_account
    acc = load_account()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)

if echo "$MONGO_TEST" | grep -q "OK"; then
    log "✅ MongoDB connected"
else
    log "❌ MongoDB error: $MONGO_TEST"
    ISSUES_FOUND=1
fi

# Summary
log "========================================="
if [ $ISSUES_FOUND -eq 0 ]; then
    log "✅ All checks passed - no issues found"
else
    log "⚠️ Some issues found - see FIXES.md for details"
fi

log ""
