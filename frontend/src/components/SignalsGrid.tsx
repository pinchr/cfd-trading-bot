import React, { useState, useEffect, useRef } from "react";
import { apiUrl } from "../api";

interface Signal {
  id?: string;
  symbol: string;
  score: number;
  direction: string;
  entry_point?: number;
  current_price?: number;
  take_profit?: number;
  stop_loss?: number;
  trend?: number[];
  confidence: number;
  risk_reward_ratio?: number;
  technical_score?: number;
  news_score?: number;
  components?: any[];
}

interface SignalsGridProps {
  signals?: Signal[];
  onSignalClick?: (signal: Signal) => void;
  onRefresh?: () => void;
}

// All known instruments — rows always appear even without signal data
const ALL_INSTRUMENTS = ["XAU", "XAG", "US100", "BTC"];

const defaultSignals: Signal[] = [
  {
    id: "1",
    symbol: "XAU",
    score: 0,
    direction: "neutral",
    confidence: 0,
    trend: [],
  },
  {
    id: "2",
    symbol: "XAG",
    score: 0,
    direction: "neutral",
    confidence: 0,
    trend: [],
  },
  {
    id: "3",
    symbol: "US100",
    score: 0,
    direction: "neutral",
    confidence: 0,
    trend: [],
  },
  {
    id: "4",
    symbol: "BTC",
    score: 0,
    direction: "neutral",
    confidence: 0,
    trend: [],
  },
];

const MiniSparkline: React.FC<{ data: number[] }> = ({ data }) => {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * 60;
      const y = 14 - ((val - min) / range) * 12;
      return `${x},${y}`;
    })
    .join(" ");
  const isUp = data[data.length - 1] > data[0];
  const color = isUp ? "var(--success)" : "var(--danger)";

  return (
    <svg width="64" height="16" viewBox="0 0 64 16">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
};

interface TradeModalState {
  isOpen: boolean;
  symbol: string;
  direction: "buy" | "sell";
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  suggestedSize: number;
  selectedSize: number;
  leverage: number;
  loading: boolean;
  displayTakeProfit: string;
  displayStopLoss: string;
  displaySelectedSize: string;
  signalComponents?: { name: string; description: string; value: number }[];
}

export const SignalsGrid: React.FC<SignalsGridProps> = ({
  signals: externalSignals,
  onSignalClick,
  onRefresh,
}) => {
  const [signals, setSignals] = useState<Signal[]>(defaultSignals);
  const [loading, setLoading] = useState(false);
  const [tradingSymbol, setTradingSymbol] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  
  // Track previous scores for flash animation
  const [flashingSignals, setFlashingSignals] = useState<Set<string>>(new Set());
  const prevScoreRef = useRef<Record<string, number>>({});
  
  // Update flashing signals when score changes
  useEffect(() => {
    const newFlashing = new Set<string>();
    const newPrevScore: Record<string, number> = {};
    
    signals.forEach(sig => {
      const prevScore = prevScoreRef.current[sig.symbol];
      if (prevScore !== undefined && prevScore !== sig.score) {
        newFlashing.add(sig.symbol);
      }
      newPrevScore[sig.symbol] = sig.score;
    });
    
    prevScoreRef.current = newPrevScore;
    
    if (newFlashing.size > 0) {
      setFlashingSignals(newFlashing);
      setTimeout(() => setFlashingSignals(new Set()), 500);
    }
  }, [signals]);

  const [tradeModal, setTradeModal] = useState<TradeModalState>({
    isOpen: false,
    symbol: "",
    direction: "buy",
    entryPrice: 0,
    stopLoss: 0,
    takeProfit: 0,
    suggestedSize: 0.01,
    selectedSize: 0.01,
    leverage: 20,
    loading: false,
    displayTakeProfit: "",
    displayStopLoss: "",
    displaySelectedSize: "",
    signalComponents: [],
  });

  const [hoveredIndicator, setHoveredIndicator] = useState<string | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{
    x: number;
    y: number;
  }>({ x: 0, y: 0 });

  const indicatorTooltips: Record<string, { desc: string; combine: string }> = {
    "RSI (14)": {
      desc: "Measures momentum (0-100). Below 30 = oversold (potential buy). Above 70 = overbought (potential sell). Use as confirmation, not standalone signals.",
      combine: "Best with: SMA Cross (confirms trend direction), ADX (above 25 = strong trend)."
    },
    "MACD": {
      desc: "EMA 12-26 difference. Line above 0 = bullish. Crosses above 0 = buy signal. Crosses below 0 = sell signal. Histogram shows momentum strength.",
      combine: "Best with: RSI (check oversold/overbought), Volume (high volume confirms move)."
    },
    "SMA Cross (20/50)": {
      desc: "Simple Moving Averages crossover. Fast SMA (20) above slow SMA (50) = bullish (buy). Fast below slow = bearish (sell). Classic trend indicator.",
      combine: "Best with: ADX (above 25 confirms trend strength), RSI (filters overbought/oversold)."
    },
    "Bollinger Bands": {
      desc: "Price envelope (20 SMA ± 2 std dev). Price touching lower band = potential buy (reversion to mean). Price at upper band = potential sell. Width shows volatility.",
      combine: "Best with: RSI (below 30 = oversold confirmation), Volume (high volume on breakout)."
    },
    "ADX (Trend)": {
      desc: "Trend strength (0-100). Above 25 = trending market (follow the trend). Below 20 = ranging (use mean-reversion strategies). Does NOT show direction!",
      combine: "Best with: SMA Cross (shows direction), +DI/-DI (shows bullish/bearish momentum)."
    },
    "StochRSI": {
      desc: "Stochastic of RSI (0-1). Below 0.2 = oversold (buy). Above 0.8 = overbought (sell). More sensitive than regular RSI - good for fast moves.",
      combine: "Best with: RSI (confirmation), MACD (momentum alignment)."
    },
    "Momentum (10)": {
      desc: "Rate of change (10-period). Above 0 = uptrend, below 0 = downtrend. Divergence (price up, momentum down) = warning sign of weakening trend.",
      combine: "Best with: ADX (trend strength), Volume (confirms move)."
    },
    "Volume": {
      desc: "Trading volume. High volume on breakout = strong signal. Low volume = weak move (fakeout risk). Volume often leads price.",
      combine: "Best with: Price action (breakout patterns), RSI (confirmation)."
    },
  };

  // Get tooltip for indicator name (handles partial matches)
  const getIndicatorTooltip = (name: string): { desc: string; combine: string } | null => {
    for (const key of Object.keys(indicatorTooltips)) {
      if (name.toLowerCase().includes(key.toLowerCase()) || 
          key.toLowerCase().includes(name.toLowerCase())) {
        return indicatorTooltips[key];
      }
    }
    return null;
  };

  useEffect(() => {
    if (externalSignals && externalSignals.length > 0) {
      setSignals(externalSignals);
      return;
    }

    const fetchSignals = async () => {
      const cacheKey = 'signalsCache';
      const cacheTimeKey = 'signalsTime';
      const cacheTime = localStorage.getItem(cacheTimeKey);
      if (cacheTime && Date.now() - parseInt(cacheTime) < 30000) {
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          setSignals(JSON.parse(cached));
          return;
        }
      }

      try {
        setLoading(true);
        const response = await fetch(apiUrl("signals"));
        if (response.ok) {
          const data = await response.json();
          const fetchedSignals: Signal[] = (data.signals || []).map(
            (sig: any, idx: number) => ({
              id: `${idx}`,
              symbol: sig.symbol,
              score: sig.score,
              direction: sig.direction.toLowerCase().includes("buy")
                ? "buy"
                : sig.direction.toLowerCase().includes("sell")
                  ? "sell"
                  : "neutral",
              entry_point: sig.entry_point || sig.current_price,
              current_price: sig.current_price,
              take_profit: sig.take_profit,
              stop_loss: sig.stop_loss,
              confidence: sig.confidence,
              risk_reward_ratio: sig.risk_reward_ratio,
              technical_score: sig.technical_score,
              news_score: sig.news_score,
              components: sig.components,
              trend: [
                sig.score * 0.5,
                sig.score * 0.6,
                sig.score * 0.7,
                sig.score * 0.8,
                sig.score * 0.9,
                sig.score,
              ],
            }),
          );

          // Ensure all instruments have a row, even if no signal was returned
          const signalMap = new Map(fetchedSignals.map((s) => [s.symbol, s]));
          const mergedSignals = ALL_INSTRUMENTS.map(
            (sym, idx) =>
              signalMap.get(sym) || {
                id: `default-${idx}`,
                symbol: sym,
                score: 0,
                direction: "neutral",
                confidence: 0,
                trend: [],
              },
          );
          setSignals(mergedSignals);
          localStorage.setItem(cacheKey, JSON.stringify(mergedSignals));
          localStorage.setItem(cacheTimeKey, Date.now().toString());
          onRefresh?.();
        }
      } catch (error) {
        console.error("Failed to fetch signals:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchSignals();
    const interval = setInterval(fetchSignals, 10000); // Refresh every 10 seconds (less aggressive)
    return () => clearInterval(interval);
  }, [externalSignals]);

  const openTradeModal = async (symbol: string, direction: "buy" | "sell") => {
    setTradingSymbol(symbol);
    setErrorMessage(null);
    const signal = signals.find((s) => s.symbol === symbol);
    if (
      !signal ||
      signal.current_price === undefined ||
      signal.current_price === null ||
      signal.current_price <= 0
    ) {
      setErrorMessage(`${symbol}: No price data available`);
      setTradingSymbol(null);
      return;
    }
    const entryPrice = signal.current_price || signal.entry_point || 0;

    // Leverage per symbol (from backend INSTRUMENTS)
    const leverageMap: Record<string, number> = {
      "XAU": 20, "XAG": 20, "US100": 20, "BTC": 5
    };
    const leverage = leverageMap[symbol] || 20;
    
    try {
      // Get proposed SL/TP from backend (calculated from live ATR data)
      const proposalResponse = await fetch(
        `${apiUrl("trade/proposal")}?symbol=${symbol}&direction=${direction}`,
      );
      let stopLoss: number;
      let takeProfit: number;
      let suggestedSize: number;

      if (proposalResponse.ok) {
        const proposal = await proposalResponse.json();
        if (!proposal.error) {
          stopLoss = proposal.stop_loss;
          takeProfit = proposal.take_profit;
          suggestedSize = proposal.suggested_size || 0.01;
          console.log(
            `[PROPOSAL] ${symbol} ${direction}: SL=${stopLoss}, TP=${takeProfit}, RR=${proposal.risk_reward_ratio}`,
          );
        } else {
          throw new Error(proposal.error);
        }
      } else {
        throw new Error("Failed to get proposal");
      }

      setTradeModal({
        isOpen: true,
        symbol,
        direction,
        entryPrice,
        stopLoss,
        takeProfit,
        suggestedSize,
        selectedSize: suggestedSize,
        leverage,
        displayTakeProfit: takeProfit.toFixed(2),
        displayStopLoss: stopLoss.toFixed(2),
        displaySelectedSize: suggestedSize.toFixed(4),
        loading: false,
        signalComponents: signal.components?.map((c: any) => ({
          name: c.name,
          description: c.description,
          value: c.value
        })),
      });
    } catch (error) {
      console.warn("Failed to get proposal, using fallback:", error);
      // Fallback: calculate locally
      const atrEstimate = entryPrice * 0.01;
      const stopLoss =
        direction === "buy"
          ? entryPrice - atrEstimate * 1.5
          : entryPrice + atrEstimate * 1.5;
      const takeProfit =
        direction === "buy"
          ? entryPrice + atrEstimate * 3.0
          : entryPrice - atrEstimate * 3.0;
      const suggestedSize = 0.01;

      setTradeModal({
        isOpen: true,
        symbol,
        direction,
        entryPrice,
        stopLoss,
        takeProfit,
        suggestedSize,
        selectedSize: suggestedSize,
        leverage,
        displayTakeProfit: takeProfit.toFixed(2),
        displayStopLoss: stopLoss.toFixed(2),
        displaySelectedSize: suggestedSize.toFixed(4),
        loading: false,
        signalComponents: signal.components?.map((c: any) => ({
          name: c.name,
          description: c.description,
          value: c.value
        })),
      });
    } finally {
      setTradingSymbol(null);
    }
  };

  const executeTrade = async () => {
    setTradeModal((prev) => ({ ...prev, loading: true }));
    try {
      const response = await fetch(
        apiUrl("trade/open"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: tradeModal.symbol,
            direction: tradeModal.direction,
            size: tradeModal.selectedSize,
            entry_price: tradeModal.entryPrice || 0,
            take_profit: tradeModal.takeProfit || 0,
            stop_loss: tradeModal.stopLoss || 0,
          }),
        },
      );
      const data = await response.json();

      if (response.ok && data.status === "opened") {
        setTradeModal((prev) => ({ ...prev, isOpen: false }));
        // Refresh signals to update UI
        const refreshResponse = await fetch(apiUrl("signals"));
        if (refreshResponse.ok) {
          const refreshData = await refreshResponse.json();
          setSignals(refreshData.signals || defaultSignals);
        }
      } else {
        const error = data.error || "Failed to open trade";
        setErrorMessage(
          `${tradeModal.symbol} ${tradeModal.direction.toUpperCase()}: ${error}`,
        );
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Network error";
      setErrorMessage(
        `${tradeModal.symbol} ${tradeModal.direction.toUpperCase()}: ${msg}`,
      );
    } finally {
      setTradeModal((prev) => ({ ...prev, loading: false }));
    }
  };

  const closeTradeModal = () => {
    setTradeModal({
      isOpen: false,
      symbol: "",
      direction: "buy",
      entryPrice: 0,
      stopLoss: 0,
      takeProfit: 0,
      suggestedSize: 0.01,
      selectedSize: 0.01,
      leverage: 20,
      loading: false,
      displayTakeProfit: "",
      displayStopLoss: "",
      displaySelectedSize: "",
      signalComponents: [],
    });
  };

  const getScoreColor = (score: number): string => {
    if (score > 0.5) return "var(--success)";
    if (score > 0.2) return "#4ade80";
    if (score > -0.2) return "var(--text-muted)";
    if (score > -0.5) return "#f87171";
    return "var(--danger)";
  };

  const getScoreBarWidth = (score: number): number => {
    return Math.abs(score) * 100;
  };

  const formatPrice = (price: number | undefined): string => {
    if (price === undefined) return "--";
    if (price > 10000) return price.toFixed(0);
    if (price > 100) return price.toFixed(2);
    return price.toFixed(4);
  };

  return (
    <>
      {/* Error Message */}
      {errorMessage && (
        <div
          className="mx-3 mt-2 px-3 py-2 rounded-sm text-[11px]"
          style={{
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            color: "var(--danger)",
          }}
        >
          {errorMessage}
          <button
            onClick={() => setErrorMessage(null)}
            className="ml-2 text-[10px] underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Mobile Card Layout */}
      <div className="overflow-auto md:hidden" style={{ maxHeight: "240px" }}>
        <div className="p-2 space-y-2">
          {signals.map((signal) => {
            const scoreColor = getScoreColor(signal.score);
            const isBuy = signal.direction === "buy";
            const dirColor = isBuy
              ? "var(--success)"
              : signal.direction === "sell"
                ? "var(--danger)"
                : "var(--text-muted)";

            return (
              <div
                key={signal.id || signal.symbol}
                onClick={() => onSignalClick?.(signal)}
                className="rounded-sm p-3"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  border: "1px solid #131825",
                }}
              >
                {/* Row 1: Symbol, Direction, Score */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="font-bold text-xs"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {signal.symbol}
                    </span>
                    <span
                      className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                      style={{
                        color: dirColor,
                        backgroundColor: `${dirColor}15`,
                      }}
                    >
                      {signal.direction.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MiniSparkline data={signal.trend || []} />
                    <span
                      className={`font-bold text-xs transition-all duration-300 ${flashingSignals.has(signal.symbol) ? 'scale-125 brightness-150' : ''}`}
                      style={{ 
                        color: scoreColor,
                        backgroundColor: flashingSignals.has(signal.symbol) ? `${scoreColor}30` : 'transparent',
                        padding: flashingSignals.has(signal.symbol) ? '2px 6px' : '0',
                        borderRadius: '4px',
                      }}
                    >
                      {signal.score >= 0 ? "+" : ""}
                      {signal.score.toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Row 2: Prices */}
                <div className="flex items-center justify-between text-[10px] mb-2">
                  <div>
                    <span style={{ color: "#4a5568" }}>Entry: </span>
                    <span style={{ color: "#94a3b8" }}>
                      {formatPrice(signal.entry_point)}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: "#4a5568" }}>TP: </span>
                    <span style={{ color: "var(--success)" }}>
                      {formatPrice(signal.take_profit)}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: "#4a5568" }}>SL: </span>
                    <span style={{ color: "var(--danger)" }}>
                      {formatPrice(signal.stop_loss)}
                    </span>
                  </div>
                </div>

                {/* Row 3: Conf, R:R, Actions */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 text-[10px]">
                    <span style={{ color: "#4a5568" }}>
                      Conf:{" "}
                      <span style={{ color: "#94a3b8" }}>
                        {(signal.confidence * 100).toFixed(0)}%
                      </span>
                    </span>
                    <span style={{ color: "#4a5568" }}>
                      R:R{" "}
                      <span style={{ color: "#94a3b8" }}>
                        {signal.risk_reward_ratio
                          ? signal.risk_reward_ratio.toFixed(1)
                          : "--"}
                      </span>
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openTradeModal(signal.symbol, "buy");
                      }}
                      disabled={tradingSymbol === signal.symbol}
                      className="px-3 py-1 text-[10px] font-bold rounded-sm transition-all"
                      style={{
                        backgroundColor: "rgba(34, 197, 94, 0.1)",
                        color: "var(--success)",
                        border: "1px solid rgba(34, 197, 94, 0.2)",
                      }}
                    >
                      BUY
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openTradeModal(signal.symbol, "sell");
                      }}
                      disabled={tradingSymbol === signal.symbol}
                      className="px-3 py-1 text-[10px] font-bold rounded-sm transition-all"
                      style={{
                        backgroundColor: "rgba(239, 68, 68, 0.1)",
                        color: "var(--danger)",
                        border: "1px solid rgba(239, 68, 68, 0.2)",
                      }}
                    >
                      SELL
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Desktop Table Layout */}
      <div className="hidden md:block">
        <table className="w-full text-[11px]">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
              <th
                className="px-4 py-2 text-left font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Symbol
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Score
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Trend
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Signal
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Conf.
              </th>
              <th
                className="px-3 py-2 text-right font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Entry
              </th>
              <th
                className="px-3 py-2 text-right font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                TP
              </th>
              <th
                className="px-3 py-2 text-right font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                SL
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                R:R
              </th>
              <th
                className="px-3 py-2 text-center font-medium uppercase tracking-wider"
                style={{ color: "#4a5568" }}
              >
                Action
              </th>
            </tr>
          </thead>
          <tbody>
            {signals.map((signal) => {
              const scoreColor = getScoreColor(signal.score);
              const isBuy = signal.direction === "buy";
              const dirColor = isBuy
                ? "var(--success)"
                : signal.direction === "sell"
                  ? "var(--danger)"
                  : "var(--text-muted)";

              return (
                <tr
                  key={signal.id || signal.symbol}
                  onClick={() => onSignalClick?.(signal)}
                  className="cursor-pointer transition-colors"
                  style={{ borderBottom: "1px solid #131825" }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.backgroundColor =
                      "rgba(26, 31, 53, 0.5)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.backgroundColor = "transparent")
                  }
                >
                  <td className="px-4 py-2.5">
                    <span
                      className="font-bold text-xs"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {signal.symbol}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <div
                        className="w-12 h-1.5 rounded-full overflow-hidden"
                        style={{ backgroundColor: "var(--bg-tertiary)" }}
                      >
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${getScoreBarWidth(signal.score)}%`,
                            backgroundColor: scoreColor,
                            marginLeft:
                              signal.score < 0
                                ? `${100 - getScoreBarWidth(signal.score)}%`
                                : "0",
                          }}
                        />
                      </div>
                      <span className="font-bold" style={{ color: scoreColor }}>
                        {signal.score >= 0 ? "+" : ""}
                        {signal.score.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <MiniSparkline data={signal.trend || []} />
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                      style={{
                        color: dirColor,
                        backgroundColor: `${dirColor}15`,
                      }}
                    >
                      {signal.direction.toUpperCase()}
                    </span>
                  </td>
                  <td
                    className="px-3 py-2.5 text-center"
                    style={{ color: "#94a3b8" }}
                  >
                    {(signal.confidence * 100).toFixed(0)}%
                  </td>
                  <td
                    className="px-3 py-2.5 text-right"
                    style={{ color: "#94a3b8" }}
                  >
                    {formatPrice(signal.entry_point)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-right"
                    style={{ color: "var(--success)" }}
                  >
                    {formatPrice(signal.take_profit)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-right"
                    style={{ color: "var(--danger)" }}
                  >
                    {formatPrice(signal.stop_loss)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-center"
                    style={{ color: "#94a3b8" }}
                  >
                    {signal.risk_reward_ratio
                      ? signal.risk_reward_ratio.toFixed(1)
                      : "--"}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openTradeModal(signal.symbol, "buy");
                        }}
                        disabled={tradingSymbol === signal.symbol}
                        className="px-2 py-0.5 text-[9px] font-bold rounded-sm transition-all"
                        style={{
                          backgroundColor: "rgba(34, 197, 94, 0.1)",
                          color: "var(--success)",
                          border: "1px solid rgba(34, 197, 94, 0.2)",
                        }}
                      >
                        BUY
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openTradeModal(signal.symbol, "sell");
                        }}
                        disabled={tradingSymbol === signal.symbol}
                        className="px-2 py-0.5 text-[9px] font-bold rounded-sm transition-all"
                        style={{
                          backgroundColor: "rgba(239, 68, 68, 0.1)",
                          color: "var(--danger)",
                          border: "1px solid rgba(239, 68, 68, 0.2)",
                        }}
                      >
                        SELL
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Trade Modal */}
      {tradeModal.isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: "rgba(0, 0, 0, 0.7)" }}
          onClick={closeTradeModal}
        >
          <div
            className="p-5 rounded-lg w-96 max-w-[90vw]"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold mb-4" style={{ color: "var(--text-primary)" }}>
              {tradeModal.direction === "buy" ? "Buy" : "Sell"}{" "}
              {tradeModal.symbol}
            </h3>

            {/* Entry Price */}
            <div className="flex justify-between text-sm mb-3">
              <span style={{ color: "var(--text-muted)" }}>Entry Price:</span>
              <span style={{ color: "var(--text-primary)" }}>
                ${tradeModal.entryPrice.toFixed(2)}
              </span>
            </div>

            {/* Take Profit with +/- */}
            <div className="mb-3">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "var(--success)" }}>Take Profit:</span>
                <span style={{ color: "var(--success)" }}>
                  ${tradeModal.displayTakeProfit}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 10
                          : prev.symbol === "XAU"
                            ? 1
                            : 5;
                      const newVal = prev.takeProfit - step;
                      return {
                        ...prev,
                        takeProfit: newVal,
                        displayTakeProfit: newVal.toFixed(2),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                >
                  −
                </button>
                <input
                  type="number"
                  step={
                    tradeModal.symbol === "BTC"
                      ? 10
                      : tradeModal.symbol === "XAU"
                        ? 1
                        : 5
                  }
                  value={tradeModal.displayTakeProfit}
                  onChange={(e) =>
                    setTradeModal((prev) => {
                      const newVal =
                        parseFloat(e.target.value) || prev.takeProfit;
                      return {
                        ...prev,
                        takeProfit: newVal,
                        displayTakeProfit: newVal.toFixed(2),
                      };
                    })
                  }
                  className="flex-1 px-3 py-1.5 rounded text-sm text-center"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid var(--success)33",
                    color: "var(--success)",
                  }}
                />
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 10
                          : prev.symbol === "XAU"
                            ? 1
                            : 5;
                      const newVal = prev.takeProfit + step;
                      return {
                        ...prev,
                        takeProfit: newVal,
                        displayTakeProfit: newVal.toFixed(2),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--success)" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Stop Loss with +/- */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "var(--danger)" }}>Stop Loss:</span>
                <span style={{ color: "var(--danger)" }}>
                  ${tradeModal.displayStopLoss}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 10
                          : prev.symbol === "XAU"
                            ? 1
                            : 5;
                      const newVal = prev.stopLoss - step;
                      return {
                        ...prev,
                        stopLoss: newVal,
                        displayStopLoss: newVal.toFixed(2),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--danger)" }}
                >
                  −
                </button>
                <input
                  type="number"
                  step={
                    tradeModal.symbol === "BTC"
                      ? 10
                      : tradeModal.symbol === "XAU"
                        ? 1
                        : 5
                  }
                  value={tradeModal.displayStopLoss}
                  onChange={(e) =>
                    setTradeModal((prev) => {
                      const newVal =
                        parseFloat(e.target.value) || prev.stopLoss;
                      return {
                        ...prev,
                        stopLoss: newVal,
                        displayStopLoss: newVal.toFixed(2),
                      };
                    })
                  }
                  className="flex-1 px-3 py-1.5 rounded text-sm text-center"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid var(--danger)33",
                    color: "var(--danger)",
                  }}
                />
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 10
                          : prev.symbol === "XAU"
                            ? 1
                            : 5;
                      const newVal = prev.stopLoss + step;
                      return {
                        ...prev,
                        stopLoss: newVal,
                        displayStopLoss: newVal.toFixed(2),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Position Size */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "var(--text-muted)" }}>Position Size:</span>
                <span style={{ color: "var(--success)", fontSize: "11px" }}>
                  Suggested: {tradeModal.suggestedSize.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 0.001
                          : prev.symbol === "XAG" ||
                              prev.symbol === "XAU" ||
                              prev.symbol === "US100"
                            ? 0.003
                            : 0.01;
                      const min =
                        prev.symbol === "BTC"
                          ? 0.001
                          : prev.symbol === "XAG" ||
                              prev.symbol === "XAU" ||
                              prev.symbol === "US100"
                            ? 0.003
                            : 0.01;
                      const newVal = Math.max(min, prev.selectedSize - step);
                      return {
                        ...prev,
                        selectedSize: newVal,
                        displaySelectedSize: newVal.toFixed(4),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                >
                  −
                </button>
                <input
                  type="number"
                  step={
                    tradeModal.symbol === "BTC"
                      ? 0.001
                      : tradeModal.symbol === "XAG" ||
                          tradeModal.symbol === "XAU" ||
                          tradeModal.symbol === "US100"
                        ? 0.003
                        : 0.01
                  }
                  min={
                    tradeModal.symbol === "BTC"
                      ? 0.001
                      : tradeModal.symbol === "XAG" ||
                          tradeModal.symbol === "XAU" ||
                          tradeModal.symbol === "US100"
                        ? 0.003
                        : 0.01
                  }
                  value={tradeModal.displaySelectedSize}
                  onChange={(e) =>
                    setTradeModal((prev) => {
                      const min =
                        prev.symbol === "BTC"
                          ? 0.001
                          : prev.symbol === "XAG" ||
                              prev.symbol === "XAU" ||
                              prev.symbol === "US100"
                            ? 0.003
                            : 0.01;
                      const rawVal = parseFloat(e.target.value) || min;
                      const newVal = Math.max(min, rawVal);
                      return {
                        ...prev,
                        selectedSize: newVal,
                        displaySelectedSize: newVal.toFixed(4),
                      };
                    })
                  }
                  className="flex-1 px-3 py-1.5 rounded text-sm text-center"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid #2d3748",
                    color: "var(--text-primary)",
                  }}
                />
                <button
                  onClick={() =>
                    setTradeModal((prev) => {
                      const step =
                        prev.symbol === "BTC"
                          ? 0.001
                          : prev.symbol === "XAG" ||
                              prev.symbol === "XAU" ||
                              prev.symbol === "US100"
                            ? 0.003
                            : 0.01;
                      const newVal = prev.selectedSize + step;
                      return {
                        ...prev,
                        selectedSize: newVal,
                        displaySelectedSize: newVal.toFixed(4),
                      };
                    })
                  }
                  className="px-3 py-1 rounded text-sm font-bold"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Risk/Reward display - now with lot size AND leverage */}
            <div
              className="flex justify-between text-xs mb-4 px-1"
              style={{ color: "var(--text-muted)" }}
            >
              <span>
                Risk: $
                {(Math.abs(tradeModal.entryPrice - tradeModal.stopLoss) * tradeModal.selectedSize * (tradeModal.leverage || 1)).toFixed(
                  2,
                )}
              </span>
              <span>
                Reward: $
                {(Math.abs(
                  tradeModal.takeProfit - tradeModal.entryPrice,
                ) * tradeModal.selectedSize * (tradeModal.leverage || 1)
                ).toFixed(2)}
              </span>
              <span
                style={{
                  color:
                    Math.abs(tradeModal.takeProfit - tradeModal.entryPrice) /
                      Math.abs(tradeModal.entryPrice - tradeModal.stopLoss) >=
                    1.5
                      ? "var(--success)"
                      : "var(--text-muted)",
                }}
              >
                R:R{" "}
                {(
                  Math.abs(tradeModal.takeProfit - tradeModal.entryPrice) /
                  Math.abs(tradeModal.entryPrice - tradeModal.stopLoss)
                ).toFixed(1)}
              </span>
            </div>

            {/* Wskaźniki techniczne z tooltipami */}
            {tradeModal.signalComponents && tradeModal.signalComponents.length > 0 && (
              <div className="mb-4 p-3 rounded" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--bg-tertiary)" }}>
                <div className="text-xs font-medium mb-2" style={{ color: "var(--text-muted)" }}>
                  Wskaźniki (najedź dla szczegółów)
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {tradeModal.signalComponents.map((comp, idx) => {
                    const tooltip = getIndicatorTooltip(comp.name);
                    return (
                      <div key={idx} className="relative group">
                        <span
                          className="text-[10px] px-2 py-1 rounded cursor-help"
                          style={{ 
                            backgroundColor: "var(--bg-tertiary)", 
                            color: "#94a3b8",
                            border: "1px solid #2d3748"
                          }}
                        >
                          {comp.name.replace(/\s*\(\d+\)/, '')}
                        </span>
                        {/* Tooltip */}
                        {tooltip && (
                          <div 
                            className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 rounded shadow-lg text-xs hidden group-hover:block"
                            style={{ 
                              backgroundColor: "#1e293b", 
                              color: "var(--text-primary)",
                              border: "1px solid #475569"
                            }}
                          >
                            <div className="font-medium mb-1" style={{ color: "#38bdf8" }}>
                              {comp.name}
                            </div>
                            <div className="mb-2" style={{ color: "#cbd5e1" }}>
                              {tooltip.desc}
                            </div>
                            <div style={{ color: "var(--success)" }}>
                              💡 {tooltip.combine}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={executeTrade}
                disabled={tradeModal.loading}
                className="flex-1 py-2.5 px-4 rounded font-medium text-sm"
                style={{
                  backgroundColor:
                    tradeModal.direction === "buy" ? "var(--success)" : "var(--danger)",
                  color: "#fff",
                  opacity: tradeModal.loading ? 0.5 : 1,
                }}
              >
                {tradeModal.loading
                  ? "Opening..."
                  : `${tradeModal.direction === "buy" ? "Buy" : "Sell"} ${tradeModal.selectedSize.toFixed(2)}`}
              </button>
              <button
                onClick={closeTradeModal}
                className="py-2.5 px-4 rounded text-sm"
                style={{
                  backgroundColor: "var(--bg-tertiary)",
                  color: "var(--text-muted)",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
