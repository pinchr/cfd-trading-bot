#!/usr/bin/env python3
import json
import subprocess
import sys
import os

# Load base strategies
os.chdir('/Users/pinchr/dev/cfd-trading-bot/backend')
with open('strategies.json') as f:
    base_strategies = json.load(f)

strategies_to_test = [
    # BTC
    ("BTC", "btc_v2_core"),
    ("BTC", "btc_v2_safe"),
    ("BTC", "btc_scalp_trend"),
    ("BTC", "btc_v3_exp"),
    # XAU
    ("XAU", "xau_v2_momentum"),
    ("XAU", "xau_scalp_trend"),
    ("XAU", "xau_v3_exp"),
    # XAG
    ("XAG", "xag_v3_exp"),
]

results = []

for symbol, strategy_id in strategies_to_test:
    # Modify strategies to enable only this one
    strategies = json.loads(json.dumps(base_strategies))  # Deep copy
    for s in strategies['strategies']:
        s['enabled'] = (s['id'] == strategy_id)
    
    # Write temp config
    with open('/tmp/strategies_temp.json', 'w') as f:
        json.dump(strategies, f)
    
    # Run backtest
    cmd = [
        'curl', '-s', '-X', 'POST',
        f'http://localhost:8001/api/strategies/backtest-json?symbol={symbol}&resolution=5&days=7&initial_balance=3000',
        '-H', 'Content-Type: application/json',
        '-d', '@/tmp/strategies_temp.json'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    try:
        data = json.loads(result.stdout)
        r = data.get('results', {})
        pnl = r.get('total_pnl', 0)
        trades = r.get('trades', 0)
        wins = r.get('wins', 0)
        losses = r.get('losses', 0)
        # Calculate win rate properly
        wr = (wins / trades * 100) if trades > 0 else 0
        execution_time = data.get('execution_time_seconds', 0)
        
        results.append({
            'symbol': symbol,
            'strategy': strategy_id,
            'trades': trades,
            'wins': wins,
            'losses': losses,
            'win_rate': wr,
            'pnl': pnl,
            'exec_time': execution_time
        })
        
        print(f"✓ {symbol} {strategy_id}: {trades} trades ({wins}W/{losses}L), {wr:.1f}% WR, PnL: ${pnl:.2f}")
        
    except json.JSONDecodeError as e:
        print(f"✗ {symbol} {strategy_id}: ERROR - {result.stdout[:200]}")
        results.append({
            'symbol': symbol,
            'strategy': strategy_id,
            'trades': 0,
            'win_rate': 0,
            'pnl': 0,
            'error': result.stdout[:200]
        })

# Save results
with open('/tmp/backtest_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n" + "="*80)
print("SUMMARY - 7 days backtest (Mar 4-11, 2026)")
print("="*80)
print(f"{'Symbol':<5} {'Strategy':<20} {'Trades':>6} {'W':>3} {'L':>3} {'WR':>6} {'PnL':>12}")
print("-"*80)
for r in results:
    if 'error' not in r:
        print(f"{r['symbol']:<5} {r['strategy']:<20} {r['trades']:>6} {r['wins']:>3} {r['losses']:>3} {r['win_rate']:>5.1f}% ${r['pnl']:>10.2f}")

# Best per symbol
print("\n" + "="*80)
print("BEST PER SYMBOL:")
print("-"*80)
for symbol in ['BTC', 'XAU', 'XAG']:
    symbol_results = [r for r in results if r['symbol'] == symbol and 'error' not in r and r['trades'] > 0]
    if symbol_results:
        best = max(symbol_results, key=lambda x: x['pnl'])
        print(f"{symbol}: {best['strategy']} - ${best['pnl']:.2f} ({best['win_rate']:.1f}% WR)")
