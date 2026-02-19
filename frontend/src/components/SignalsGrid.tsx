import React, { useState, useEffect } from "react";
import { useSWR } from 'swr';
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
  const color = isUp ? "#22c55e" : "#ef4444";

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
  loading: boolean;
  displayTakeProfit: string;
  displayStopLoss: string;
  displaySelectedSize: string;
}

export const SignalsGrid: React.FC<SignalsGridProps> = ({
  signals: externalSignals,
  onSignalClick,
}) => {
  const [signals, setSignals] = useState<Signal[]>(defaultSignals);
  const [loading, setLoading] = useState(false);
const [lastRefresh, setLastRefresh] = useState(new Date().toLocaleTimeString('pl-PL'));
  const [tradingSymbol, setTradingSymbol] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [tradeModal, setTradeModal] = useState<TradeModalState>({
    isOpen: false,
    symbol: "",
    direction: "buy",
    entryPrice: 0,
    stopLoss: 0,
    takeProfit: 0,
    suggestedSize: 0.01,
    selectedSize: 0.01,
    loading: false,
    displayTakeProfit: "",
    displayStopLoss: "",
    displaySelectedSize: "",
  });

  const fetcher = (url: string) => fetch(url).then((res) => res.json());

  const { data, error: signalsError, isLoading: signalsLoading } = useSWR('/api/signals', fetcher, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  });

  useEffect(() => {
    if (data) {
      const fetchedSignals: Signal[] = (data.signals || []).map((sig: any, idx: number) => ({
        id: `${idx}`,
        symbol: sig.symbol,
        score: sig.score,
        direction: sig.direction.toLowerCase().includes("buy") ? "buy" : sig.direction.toLowerCase().includes("sell") ? "sell" : "neutral",
        entry_point: sig.entry_point || sig.current_price,
        current_price: sig.current_price,
        take_profit: sig.take_profit,
        stop_loss: sig.stop_loss,
        confidence: sig.confidence,
        risk_reward_ratio: sig.risk_reward_ratio,
        technical_score: sig.technical_score,
        news_score: sig.news_score,
        components: sig.components,
        trend: [sig.score * 0.5, sig.score * 0.6, sig.score * 0.7, sig.score * 0.8, sig.score * 0.9, sig.score],
      }));

      const signalMap = new Map(fetchedSignals.map((s) => [s.symbol, s]));
      const mergedSignals = ALL_INSTRUMENTS.map((sym, idx) => signalMap.get(sym) || {
        id: `default-${idx}`,
        symbol: sym,
        score: 0,
        direction: "neutral",
        confidence: 0,
        trend: [],
      });
      setSignals(mergedSignals);
      setLastRefresh(new Date().toLocaleTimeString('pl-PL'));
    }
  }, [data]);

  if (signalsError) {
    console.error('Signals error:', signalsError);
    setErrorMessage('Błąd ładowania signals: ' + signalsError.message);
  }

  const [hoveredIndicator, setHoveredIndicator] = useState<string | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{
    x: number;
    y: number;
  }>({ x: 0, y: 0 });

  const indicatorTooltips: Record<string, string> = {
    RSI: "RSI mierzy overbought/oversold (14-period); &lt;#60;30 buy, &gt;#62;70 sell.",
    MACD: "Histogram momentum (EMA12-26); &gt;#62;0 bullish, cross up buy.",
    "SMA Cross": "SMA20&gt;#62;SMA50 uptrend buy bias.",
    BB: "Price near lower band buy (mean-reversion).",
    ADX: "&gt;#62;25 trending (trade momentum), &lt;#60;20 ranging (mean-rev).",
    StochRSI: "StochRSI &lt;#60;0.2 oversold→buy, &gt;#62;0.8 overbought→sell.",
    Volume:
      "Volume confirms price moves; high volume on breakout = strong signal.",
    Momentum: "Momentum &gt;#62;0 uptrend buy; divergence warns reversal.",
    Candlestick:
      "Patterns: hammer/engulfing bullish reversal buy; shooting star sell caution.",
  };

  import { useSWR } from 'swr';

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch');
  return res.json();
};

[...]

  const { data, error, isLoading } = useSWR('/api/signals', fetcher, {
    refreshInterval: 10000,
    revalidateOnFocus: false,
  });

  const [lastRefresh, setLastRefresh] = useState(new Date().toLocaleTimeString());

  useEffect(() => {
    if (data) {
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
      setLastRefresh(new Date().toLocaleTimeString());
    }
  }, [data]);

  if (error) setErrorMessage(error.message);

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
        displayTakeProfit: takeProfit.toFixed(2),
        displayStopLoss: stopLoss.toFixed(2),
        displaySelectedSize: suggestedSize.toFixed(4),
        loading: false,
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
        displayTakeProfit: takeProfit.toFixed(2),
        displayStopLoss: stopLoss.toFixed(2),
        displaySelectedSize: suggestedSize.toFixed(4),
        loading: false,
      });
    } finally {
      setTradingSymbol(null);
    }
  };

  const executeTrade = async () => {
    setTradeModal((prev) => ({ ...prev, loading: true }));
    try {
      const params = new URLSearchParams({
        symbol: tradeModal.symbol,
        direction: tradeModal.direction,
        size: tradeModal.selectedSize.toString(),
        take_profit: tradeModal.takeProfit.toString(),
        stop_loss: tradeModal.stopLoss.toString(),
      });
      const response = await fetch(
        `${apiUrl("trade/open")}?${params.toString()}`,
        { method: "POST" },
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
      loading: false,
      displayTakeProfit: "",
      displayStopLoss: "",
      displaySelectedSize: "",
    });
  };

  const getScoreColor = (score: number): string => {
    if (score > 0.5) return "#22c55e";
    if (score > 0.2) return "#4ade80";
    if (score > -0.2) return "#64748b";
    if (score > -0.5) return "#f87171";
    return "#ef4444";
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
            color: "#ef4444",
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
              ? "#22c55e"
              : signal.direction === "sell"
                ? "#ef4444"
                : "#64748b";

            return (
              <div
                key={signal.id || signal.symbol}
                onClick={() => onSignalClick?.(signal)}
                className="rounded-sm p-3"
                style={{
                  backgroundColor: "#0b0f1a",
                  border: "1px solid #131825",
                }}
              >
                {/* Row 1: Symbol, Direction, Score */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="font-bold text-xs"
                      style={{ color: "#e2e8f0" }}
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
                      className="font-bold text-xs"
                      style={{ color: scoreColor }}
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
                    <span style={{ color: "#22c55e" }}>
                      {formatPrice(signal.take_profit)}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: "#4a5568" }}>SL: </span>
                    <span style={{ color: "#ef4444" }}>
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
                        color: "#22c55e",
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
                        color: "#ef4444",
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
            <tr style={{ borderBottom: "1px solid #1a1f35" }}>
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
                ? "#22c55e"
                : signal.direction === "sell"
                  ? "#ef4444"
                  : "#64748b";

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
                      style={{ color: "#e2e8f0" }}
                    >
                      {signal.symbol}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <div
                        className="w-12 h-1.5 rounded-full overflow-hidden"
                        style={{ backgroundColor: "#1a1f35" }}
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
                    style={{ color: "#22c55e" }}
                  >
                    {formatPrice(signal.take_profit)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-right"
                    style={{ color: "#ef4444" }}
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
                          color: "#22c55e",
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
                          color: "#ef4444",
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
            style={{ backgroundColor: "#0d1220", border: "1px solid #1a1f35" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold mb-4" style={{ color: "#e2e8f0" }}>
              {tradeModal.direction === "buy" ? "Buy" : "Sell"}{" "}
              {tradeModal.symbol}
            </h3>

            {/* Entry Price */}
            <div className="flex justify-between text-sm mb-3">
              <span style={{ color: "#64748b" }}>Entry Price:</span>
              <span style={{ color: "#e2e8f0" }}>
                ${tradeModal.entryPrice.toFixed(2)}
              </span>
            </div>

            {/* Take Profit with +/- */}
            <div className="mb-3">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "#22c55e" }}>Take Profit:</span>
                <span style={{ color: "#22c55e" }}>
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
                  style={{ backgroundColor: "#1a1f35", color: "#64748b" }}
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
                    backgroundColor: "#1a1f35",
                    border: "1px solid #22c55e33",
                    color: "#22c55e",
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
                  style={{ backgroundColor: "#1a1f35", color: "#22c55e" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Stop Loss with +/- */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "#ef4444" }}>Stop Loss:</span>
                <span style={{ color: "#ef4444" }}>
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
                  style={{ backgroundColor: "#1a1f35", color: "#ef4444" }}
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
                    backgroundColor: "#1a1f35",
                    border: "1px solid #ef444433",
                    color: "#ef4444",
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
                  style={{ backgroundColor: "#1a1f35", color: "#64748b" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Position Size */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span style={{ color: "#64748b" }}>Position Size:</span>
                <span style={{ color: "#22c55e", fontSize: "11px" }}>
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
                  style={{ backgroundColor: "#1a1f35", color: "#64748b" }}
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
                    backgroundColor: "#1a1f35",
                    border: "1px solid #2d3748",
                    color: "#e2e8f0",
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
                  style={{ backgroundColor: "#1a1f35", color: "#64748b" }}
                >
                  +
                </button>
              </div>
            </div>

            {/* Risk/Reward display */}
            <div
              className="flex justify-between text-xs mb-4 px-1"
              style={{ color: "#64748b" }}
            >
              <span>
                Risk: $
                {Math.abs(tradeModal.entryPrice - tradeModal.stopLoss).toFixed(
                  2,
                )}
              </span>
              <span>
                Reward: $
                {Math.abs(
                  tradeModal.takeProfit - tradeModal.entryPrice,
                ).toFixed(2)}
              </span>
              <span
                style={{
                  color:
                    Math.abs(tradeModal.takeProfit - tradeModal.entryPrice) /
                      Math.abs(tradeModal.entryPrice - tradeModal.stopLoss) >=
                    1.5
                      ? "#22c55e"
                      : "#64748b",
                }}
              >
                R:R{" "}
                {(
                  Math.abs(tradeModal.takeProfit - tradeModal.entryPrice) /
                  Math.abs(tradeModal.entryPrice - tradeModal.stopLoss)
                ).toFixed(1)}
              </span>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={executeTrade}
                disabled={tradeModal.loading}
                className="flex-1 py-2.5 px-4 rounded font-medium text-sm"
                style={{
                  backgroundColor:
                    tradeModal.direction === "buy" ? "#22c55e" : "#ef4444",
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
                  backgroundColor: "#1a1f35",
                  color: "#64748b",
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
