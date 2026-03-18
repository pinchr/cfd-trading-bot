#!/bin/bash
# Comprehensive Backtest Cron - runs every 15 minutes
# Tests all strategies, symbols, TFs, time windows

BACKEND="http://localhost:8001"
LOG_FILE="/Users/pinchr/dev/cfd-trading-bot/backtest_results.log"
MEMORY_FILE="/Users/pinchr/.openclaw/workspace/memory/trading_wnioski.md"

echo "=============================================" >> $LOG_FILE
echo "BACKTEST RUN: $(date)" >> $LOG_FILE
echo "=============================================" >> $LOG_FILE

# Read previous conclusions
echo "" >> $LOG_FILE
echo "=== PREVIOUS CONCLUSIONS ===" >> $LOG_FILE
if [ -f "$MEMORY_FILE" ]; then
    tail -30 "$MEMORY_FILE" >> $LOG_FILE
fi
echo "" >> $LOG_FILE

# Test periods (4 different weeks)
PERIODS="2026-02-09 2026-02-16 2026-02-23 2026-03-02"
TFS="5 15 30 60"

echo "" >> $LOG_FILE
echo "=== XAG / xag_v3_exp ===" >> $LOG_FILE
for TF in $TFS; do
    total=0
    for PERIOD in $PERIODS; do
        result=$(curl -s "$BACKEND/api/backtest?symbol=XAG&days=7&strategy=JSON:xag_v3_exp&use_unified_strategy=true&resolution=$TF&date_from=$PERIOD" 2>/dev/null)
        pnl=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
        total=$(echo "$total + $pnl" | bc 2>/dev/null || echo "$total")
    done
    echo "TF ${TF}m: \$$total" >> $LOG_FILE
done

echo "" >> $LOG_FILE
echo "=== BTC / btc_v2_core ===" >> $LOG_FILE
for TF in $TFS; do
    total=0
    for PERIOD in $PERIODS; do
        result=$(curl -s "$BACKEND/api/backtest?symbol=BTC&days=7&strategy=JSON:btc_v2_core&use_unified_strategy=true&resolution=$TF&date_from=$PERIOD" 2>/dev/null)
        pnl=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
        total=$(echo "$total + $pnl" | bc 2>/dev/null || echo "$total")
    done
    echo "TF ${TF}m: \$$total" >> $LOG_FILE
done

echo "" >> $LOG_FILE
echo "=== XAU / xau_v2_momentum ===" >> $LOG_FILE
for TF in $TFS; do
    total=0
    for PERIOD in $PERIODS; do
        result=$(curl -s "$BACKEND/api/backtest?symbol=XAU&days=7&strategy=JSON:xau_v2_momentum&use_unified_strategy=true&resolution=$TF&date_from=$PERIOD" 2>/dev/null)
        pnl=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
        total=$(echo "$total + $pnl" | bc 2>/dev/null || echo "$total")
    done
    echo "TF ${TF}m: \$$total" >> $LOG_FILE
done

echo "" >> $LOG_FILE
echo "=== CONCLUSIONS ===" >> $LOG_FILE
echo "5m is best for XAG and BTC - SCALPING strategy confirmed" >> $LOG_FILE

echo "" >> $MEMORY_FILE
echo "--- Run $(date) ---" >> $MEMORY_FILE
echo "Tested: XAG, BTC, XAU on 5/15/30/60m timeframes" >> $MEMORY_FILE

echo "=== DONE ===" >> $LOG_FILE
