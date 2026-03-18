#!/bin/bash
# Backtest Cron - rotates through JSON strategies and TFs
# Runs every 15 minutes, tests different combinations

BACKEND="http://localhost:8001"
LOG_FILE="/Users/pinchr/dev/cfd-trading-bot/backtest_results.log"

# Get minute to determine which test to run
MINUTE=$(date +%M)

# Map minutes to test combinations
# 0,15 = XAG 5m
# 30,45 = XAG 60m  
# 60 (next hour) = BTC 5m
# etc.

case $MINUTE in
    00|15)
        SYM="XAG"; STRAT="xag_v3_exp"; TF="5"
        ;;
    30|45)
        SYM="XAG"; STRAT="xag_v3_exp"; TF="60"
        ;;
    05|20)
        SYM="BTC"; STRAT="btc_v2_core"; TF="5"
        ;;
    35|50)
        SYM="BTC"; STRAT="btc_v2_core"; TF="60"
        ;;
    10|25)
        SYM="XAU"; STRAT="xau_v2_momentum"; TF="5"
        ;;
    40|55)
        SYM="XAU"; STRAT="xau_v2_momentum"; TF="60"
        ;;
    *)
        SYM="XAG"; STRAT="xag_v3_exp"; TF="5"
        ;;
esac

# Run test (single period for speed)
result=$(curl -s "$BACKEND/api/backtest?symbol=$SYM&days=7&strategy=$STRAT&use_unified_strategy=true&resolution=$TF" 2>/dev/null)
pnl=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('total_pnl',0))" 2>/dev/null)
trades=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trades_count',0))" 2>/dev/null)

echo "$(date): $SYM $TFm $STRAT = \$$pnl ($trades trades)" >> $LOG_FILE
