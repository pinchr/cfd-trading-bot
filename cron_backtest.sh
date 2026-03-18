#!/bin/bash
# Backtest cron - runs every 15 minutes
# Tests XAG and BTC strategies

BACKEND="http://localhost:8001"
LOG_FILE="/Users/pinchr/dev/cfd-trading-bot/cron_backtest.log"

echo "=== Backtest run: $(date) ===" >> $LOG_FILE

# Test XAG strategies
echo "Testing XAG..." >> $LOG_FILE
XAG_RESULT=$(curl -s "$BACKEND/api/backtest?symbol=XAG&days=14&strategy=JSON:xag_extreme&use_unified_strategy=true")
XAG_PNL=$(echo "$XAG_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
echo "XAG xag_extreme: \$$XAG_PNL" >> $LOG_FILE

# Test BTC strategies  
echo "Testing BTC..." >> $LOG_FILE
BTC_RESULT=$(curl -s "$BACKEND/api/backtest?symbol=BTC&days=14&strategy=JSON:btc_v2_core&use_unified_strategy=true")
BTC_PNL=$(echo "$BTC_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
echo "BTC btc_v2_core: \$$BTC_PNL" >> $LOG_FILE

echo "=== Done ===" >> $LOG_FILE
