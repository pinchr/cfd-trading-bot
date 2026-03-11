"""
Dynamic TP/SL calculation for backtest
Implements HTF RSI-based dynamic TP rules from strategy config
"""

def calculate_dynamic_tp(sl_pct, htf_candles, htf_indicators, direction):
    """
    Calculate dynamic take profit based on HTF RSI conditions
    
    Args:
        sl_pct: Base stop loss percentage (e.g., 0.02 for 2%)
        htf_candles: Higher timeframe candles
        htf_indicators: Technical indicators on HTF
        direction: 'buy' or 'sell'
    
    Returns:
        tp_pct: Calculated take profit percentage
    """
    import math
    
    # Default RR ratio
    base_rr = 2.5
    tp_pct = sl_pct * base_rr
    
    if not htf_candles or len(htf_candles) < 14:
        return tp_pct
    
    try:
        # Calculate RSI on HTF
        from indicators import TechnicalIndicators
        htf_data = TechnicalIndicators.calculate_all(htf_candles, period=14)
        
        if htf_data and 'rsi' in htf_data:
            htf_rsi = htf_data['rsi']
            
            # Rules from JSON config:
            # HTF RSI > 65: TP reduced (market overbought, less room down)
            # HTF RSI > 50: Base RR
            # HTF RSI < 40: TP increased (market oversold, more room up)
            
            if htf_rsi > 65:
                # Overbought - reduce TP
                tp_pct = sl_pct * 1.5  # Lower RR in overbought
            elif htf_rsi > 50:
                # Normal trending up
                tp_pct = sl_pct * base_rr
            elif htf_rsi < 40:
                # Oversold - increase TP
                tp_pct = sl_pct * 3.5  # Higher RR in oversold
            else:
                # Between 40-50
                tp_pct = sl_pct * base_rr
                
    except Exception as e:
        print(f"[DYNAMIC-TP] Error calculating: {e}")
    
    return min(tp_pct, 0.15)  # Cap at 15% max


def update_backtest_with_dynamic_tp():
    """
    Call this function in backtest.py after loading strategy config
    to set up dynamic TP calculation
    """
    pass