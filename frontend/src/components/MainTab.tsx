import React, { useState, useEffect, useCallback } from "react";
import { SignalsGrid } from "./SignalsGrid";
import { CandlestickChart } from "./CandlestickChart";
import { OpenPositionsSummary } from "./OpenPositionsSummary";
import { apiUrl } from "../api";

// Interval-appropriate display candle counts (visible candles, reduced for BB visibility)
const CANDLE_COUNTS: Record<string, number> = {
  "1": 48, // 48 min of 1m candles
  "5": 48, // ~4 hours of 5m candles
  "15": 48, // ~12 hours of 15m candles
  "30": 48, // ~24 hours of 30m candles
  "60": 48, // ~2 days of 1h candles
  "D": 48, // ~2 months of daily candles
};

interface MainTabProps {
  onSignalClick?: (signal: any) => void;
  selectedSymbol: string;
  onSymbolSelect: (symbol: string) => void;
}

const instruments = [
  { symbol: "XAU", name: "Gold", color: "#eab308" },
  { symbol: "XAG", name: "Silver", color: "#94a3b8" },
  { symbol: "US100", name: "Nasdaq-100", color: "var(--accent)" },
  { symbol: "BTC", name: "Bitcoin", color: "#f97316" },
];

const timeframes = [
  { value: "1", label: "1m" },
  { value: "5", label: "5m" },
  { value: "15", label: "15m" },
  { value: "30", label: "30m" },
  { value: "60", label: "1H" },
  { value: "D", label: "1D" },
];

interface Trade {
  id: string;
  symbol: string;
  direction: "buy" | "sell";
  entry_price: number;
  exit_price?: number;
  opened_at: string;
  closed_at?: string;
  pnl_usd?: number;
  take_profit?: number;
  stop_loss?: number;
  result?: "win" | "loss";
  size?: number;
}

interface StrategyInfo {
  id: string;
  name: string;
  description: string;
  tooltip?: string;
}

export const MainTab: React.FC<MainTabProps> = ({
  onSignalClick,
  selectedSymbol,
  onSymbolSelect,
}) => {
  const [chartData, setChartData] = useState<any>(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState(() => {
    return localStorage.getItem("cfd_timeframe") || "60";
  });
  const [loading, setLoading] = useState(false);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  
  // Last refresh timestamps for sections
  const [lastRefresh, setLastRefresh] = useState({
    chart: Date.now(),
    positions: Date.now(),
    signals: Date.now(),
  });

  // Helper to format age string
  const formatAge = (timestamp: number): string => {
    const ageMs = Date.now() - timestamp;
    if (ageMs < 60000) return `${Math.floor(ageMs / 1000)}s`;
    if (ageMs < 3600000) return `${Math.floor(ageMs / 60000)}m`;
    return `${Math.floor(ageMs / 3600000)}h`;
  };

  // Get status color based on freshness - different thresholds per section
  const getStatusColor = (timestamp: number, section: "chart" | "positions" | "signals"): string => {
    const ageMs = Date.now() - timestamp;
    if (section === "chart") {
      // Charts: green < 5min, yellow < 7.5min, red > 7.5min
      if (ageMs < 300000) return "var(--success)";
      if (ageMs < 450000) return "#eab308";
      return "var(--danger)";
    } else if (section === "positions") {
      // Positions: green < 5s, yellow < 10s, red > 10s (refreshes every 1s)
      if (ageMs < 5000) return "var(--success)";
      if (ageMs < 10000) return "#eab308";
      return "var(--danger)";
    } else {
      // Signals: green < 15s, yellow < 30s, red > 30s (refreshes every 10s)
      if (ageMs < 15000) return "var(--success)";
      if (ageMs < 30000) return "#eab308";
      return "var(--danger)";
    }
  };

  // Collapsible sections state - mutual exclusion: only one can be expanded
  const [expandedSection, setExpandedSection] = useState<
    "signals" | "trades" | null
  >("signals");

  // Strategy state
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selectedPos, setSelectedPos] = useState<any>(null);
  const [symbolStrategies, setSymbolStrategies] = useState<
    Record<string, string>
  >({});

  useEffect(() => {
    localStorage.setItem("cfd_timeframe", selectedTimeframe);
  }, [selectedTimeframe]);

  // Fetch available strategies on mount
  useEffect(() => {
    fetch(apiUrl("strategies"))
      .then((r) => (r.ok ? r.json() : { strategies: [] }))
      .then((data) => setStrategies(data.strategies || []))
      .catch(() => {});
    fetch(apiUrl("strategy-selections"))
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: Record<string, string>) => setSymbolStrategies(data))
      .catch(() => {});
  }, []);

  const handleStrategyChange = useCallback(
    async (symbol: string, strategyId: string) => {
      setSymbolStrategies((prev) => ({ ...prev, [symbol]: strategyId }));
      try {
        await fetch(
          `${apiUrl(`strategy/${symbol}`)}?strategy_id=${encodeURIComponent(strategyId)}`,
          {
            method: "POST",
          },
        );
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const fetchChartData = async (symbol: string, resolution: string) => {
    try {
      setLoading(true);
      const count = CANDLE_COUNTS[resolution] || 100;
      const url = apiUrl("chart/" + symbol) + "?resolution=" + resolution + "&count=" + count;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        // Handle both data.data (old format) and data.candles (new format)
        const candleData = data.candles || data.data;
        if (candleData && Array.isArray(candleData) && candleData.length > 0) {
          // Transform candles to have 'time' field if only 'timestamp' exists
          const transformedData = candleData.map((c: any) => ({
            ...c,
            time: c.time || c.timestamp,
          }));
          const validData = transformedData.filter(
            (candle: any) =>
              candle &&
              (typeof candle.time === "string" || typeof candle.timestamp === "string") &&
              typeof candle.open === "number" &&
              typeof candle.high === "number" &&
              typeof candle.low === "number" &&
              typeof candle.close === "number" &&
              typeof candle.volume === "number",
          );
          if (validData.length > 0) {
            setChartData({ ...data, data: validData });
            setLastRefresh(r => ({ ...r, chart: Date.now() }));
          } else {
            setChartData({ error: "Invalid data format" });
          }
        } else {
          setChartData({ error: data.error || "No chart data available" });
        }
      }
    } catch (error) {
      setChartData({ error: "Network error" });
    } finally {
      setLoading(false);
    }
  };

  const fetchTrades = async () => {
    try {
      const [openRes, closedRes] = await Promise.all([
        fetch(apiUrl("trades/open")),
        fetch(apiUrl("trades/history")),
      ]);

      const allTrades: Trade[] = [];

      if (openRes.ok) {
        const openData = await openRes.json();
        if (openData.positions) {
          setPositions(openData.positions);
          allTrades.push(
            ...openData.positions.map((p: any) => ({
              ...p,
              result: undefined,
            })),
          );
        }
      }

      if (closedRes.ok) {
        const closedData = await closedRes.json();
        if (closedData.trades) {
          allTrades.push(...closedData.trades);
        }
      }

      setTrades(allTrades);
    } catch (error) {
      console.error("Failed to fetch trades:", error);
    }
  };

  useEffect(() => {
    if (selectedSymbol) {
      fetchChartData(selectedSymbol, selectedTimeframe);
    }
  }, [selectedSymbol, selectedTimeframe]);

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 10000); // Refresh every 10 seconds
    
    // Handle TP/SL line dragging from chart
    const handleLineAdjust = async (e: CustomEvent) => {
      const { positionId, type, value } = e.detail;
      try {
        const endpoint = type === "tp" 
          ? `trades/update/${positionId}?take_profit=${value}`
          : `trades/update/${positionId}?stop_loss=${value}`;
        await fetch(apiUrl(endpoint), {
          method: "POST",
        });
        fetchTrades(); // Refresh after update
      } catch (error) {
        console.error("Failed to update position:", error);
      }
    };
    
    window.addEventListener("adjustPositionLine", handleLineAdjust as unknown as EventListener);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener("adjustPositionLine", handleLineAdjust as unknown as EventListener);
    };
  }, []);

  const handleSignalClick = (signal: any) => {
    if (signal.symbol && signal.symbol !== selectedSymbol) {
      onSymbolSelect(signal.symbol);
    }
    onSignalClick?.(signal);
  };

  const currentInstrument = instruments.find(
    (i) => i.symbol === selectedSymbol,
  );

  return (
    <div className="flex flex-col h-full p-2 md:p-4 gap-2 md:gap-3 overflow-auto">
      {/* Chart Section */}
      <div
        className="flex-1 min-h-[200px] md:min-h-0 rounded-sm overflow-hidden"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
      >
        {/* Chart Header */}
        <div
          className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-2 md:px-4 py-2 md:py-2.5 gap-2 sm:gap-0"
          style={{ borderBottom: "1px solid var(--bg-tertiary)" }}
        >
          <div className="flex items-center gap-2 md:gap-3 w-full sm:w-auto">
            {/* Symbol Tabs - scrollable on mobile */}
            <div className="flex items-center gap-0.5 overflow-x-auto flex-shrink-0">
              {instruments.map((inst) => (
                <button
                  key={inst.symbol}
                  onClick={() => onSymbolSelect(inst.symbol)}
                  className="px-2 md:px-2.5 py-1 text-[11px] font-medium rounded-sm transition-all whitespace-nowrap flex-shrink-0"
                  style={{
                    color:
                      selectedSymbol === inst.symbol ? "var(--text-primary)" : "#4a5568",
                    backgroundColor:
                      selectedSymbol === inst.symbol
                        ? "var(--bg-tertiary)"
                        : "transparent",
                    borderLeft:
                      selectedSymbol === inst.symbol
                        ? `2px solid ${inst.color}`
                        : "2px solid transparent",
                  }}
                >
                  {inst.symbol}
                </button>
              ))}
            </div>
            <span
              className="text-[10px] hidden sm:inline"
              style={{ color: "#4a5568" }}
            >
              {currentInstrument?.name}
            </span>
            {chartData &&
              !chartData.error &&
              (() => {
                const isLive = chartData.source === "alpha_vantage";
                const isCache = chartData.source === "cache";
                const fetchedAt = chartData.fetched_at
                  ? new Date(chartData.fetched_at + "Z")
                  : null;
                const ageMs = fetchedAt
                  ? Date.now() - fetchedAt.getTime()
                  : Infinity;
                const isStale = ageMs > 5 * 60 * 1000; // > 5 minutes
                const ageStr = fetchedAt
                  ? ageMs < 60000
                    ? `${Math.floor(ageMs / 1000)}s ago`
                    : ageMs < 3600000
                      ? `${Math.floor(ageMs / 60000)}m ago`
                      : `${Math.floor(ageMs / 3600000)}h ago`
                  : "";

                return (
                  <div className="flex items-center gap-1">
                    <div
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{
                        backgroundColor: getStatusColor(lastRefresh.chart, "chart"),
                      }}
                      title={`Updated ${formatAge(lastRefresh.chart)} ago`}
                    />
                    <span
                      className="text-[9px] px-1 py-0.5 rounded-sm"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: getStatusColor(lastRefresh.chart, "chart"),
                      }}
                    >
                      {isLive
                        ? "LIVE"
                        : isCache
                          ? "CACHED"
                          : chartData.source?.toUpperCase()}
                      {ageStr ? ` ${ageStr}` : ""}
                    </span>
                  </div>
                );
              })()}
          </div>

          <div className="flex items-center gap-2 overflow-x-auto w-full sm:w-auto">
            {/* Strategy Selector */}
            {strategies.length > 0 && (
              <select
                value={symbolStrategies[selectedSymbol] || "adaptive_regime"}
                onChange={(e) =>
                  handleStrategyChange(selectedSymbol, e.target.value)
                }
                className="text-[10px] font-medium rounded-sm py-1 px-1.5 outline-none cursor-pointer flex-shrink-0"
                style={{
                  color: "var(--text-primary)",
                  backgroundColor: "var(--bg-tertiary)",
                  border: "1px solid #2d3548",
                }}
                title="Trading strategy for this symbol"
              >
                {strategies.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}

            {/* Timeframe Selector */}
            <div className="flex gap-0.5 flex-shrink-0">
              {timeframes.map((tf) => (
                <button
                  key={tf.value}
                  onClick={() => setSelectedTimeframe(tf.value)}
                  className="px-2 py-1 text-[10px] font-medium rounded-sm transition-all flex-shrink-0"
                  style={{
                    color:
                      selectedTimeframe === tf.value ? "var(--text-primary)" : "#4a5568",
                    backgroundColor:
                      selectedTimeframe === tf.value
                        ? "var(--bg-tertiary)"
                        : "transparent",
                  }}
                >
                  {tf.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Chart Area */}
        <div className="p-1 md:p-2" style={{ height: "calc(100% - 45px)" }}>
          {loading ? (
            <div
              className="h-full flex items-center justify-center"
              style={{ color: "#4a5568" }}
            >
              <div className="text-center">
                <div className="text-xs uppercase tracking-widest mb-1">
                  Loading...
                </div>
                <div className="text-[10px]">
                  {selectedSymbol}{" "}
                  {
                    timeframes.find((tf) => tf.value === selectedTimeframe)
                      ?.label
                  }
                </div>
              </div>
            </div>
          ) : chartData && chartData.data ? (
            <CandlestickChart
              key={`${selectedSymbol}-${selectedTimeframe}`}
              symbol={selectedSymbol}
              data={chartData.data}
              height={380}
              showVolume={true}
              showRSI={true}
              resolution={selectedTimeframe}
              trades={trades}
              selectedPosition={selectedPos}
            />
          ) : (
            <div
              className="h-full flex items-center justify-center"
              style={{ color: "#4a5568" }}
            >
              <div className="text-center">
                <div className="text-xs uppercase tracking-widest mb-1">
                  No Data
                </div>
                <div className="text-[10px]">
                  {chartData?.error || "Select a symbol"}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Open Positions Section - always visible but compact */}
      <OpenPositionsSummary
        onSelectPosition={(pos) => { if (pos) { setSelectedPos(pos); onSymbolSelect(pos.symbol); } }} lastRefresh={lastRefresh.positions} />

      {/* Signals Section - collapsible */}
      <div
        className="rounded-sm overflow-hidden"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
      >
        {/* Section Header */}
        <button
          onClick={() =>
            setExpandedSection(expandedSection === "signals" ? null : "signals")
          }
          className="w-full flex items-center justify-between px-3 py-2 transition-colors"
          style={{
            backgroundColor: expandedSection === "signals" ? "var(--bg-tertiary)" : "transparent",
            borderBottom: "0.1px solid var(--bg-tertiary)",
          }}
        >
          <span
            className="text-[11px] font-medium uppercase tracking-wider flex items-center gap-2"
            style={{ color: "var(--text-muted)" }}
          >
            Trading Signals
            <span className="text-[10px] px-2 py-0.5 rounded-sm" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}>
              {signals.length}
            </span>
            <span 
              className="w-1.5 h-1.5 rounded-full" 
              style={{ backgroundColor: getStatusColor(lastRefresh.signals, "signals") }}
              title={`Updated ${formatAge(lastRefresh.signals)} ago`}
            />
            <span className="text-[9px]" style={{ color: getStatusColor(lastRefresh.signals, "signals") }}>
              {formatAge(lastRefresh.signals)}
            </span>
          </span>
          <span
            style={{
              color: expandedSection === "signals" ? "var(--text-muted)" : "var(--text-primary)",
              transform:
                expandedSection === "signals"
                  ? "rotate(180deg)"
                  : "rotate(0deg)",
              transition: "transform 0.2s, color 0.2s",
            }}
            className="text-[10px]"
          >
            ▼
          </span>
        </button>

        {/* Collapsible Content */}
        {expandedSection === "signals" && (
          <SignalsGrid 
            onSignalClick={handleSignalClick}
            selectedSymbol={selectedSymbol}
            onRefresh={() => {
              setLastRefresh(r => ({ ...r, signals: Date.now() }));
              // Fetch signals to update state
              fetch(apiUrl("signals")).then(r => r.json()).then(d => {
                if (d.signals) setSignals(d.signals);
              }).catch(() => {});
            }}
          />
        )}
      </div>
    </div>
  );
};
