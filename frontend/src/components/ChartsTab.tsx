import React, { useState, useEffect } from "react";
import { CandlestickChart } from "./CandlestickChart";
import { apiUrl } from "../api";

interface ChartData {
  time: string;
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
}

interface ChartResponse {
  symbol: string;
  candles?: ChartData[];
  data?: ChartData[];
  resolution?: string;
  count?: number;
  source?: string;
  fetched_at?: string;
  vix?: {
    value: number;
    name: string;
    change_pct: number;
  };
}

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

const instruments = [
  { symbol: "XAU", name: "Gold", color: "#eab308" },
  { symbol: "XAG", name: "Silver", color: "#94a3b8" },
  { symbol: "US100", name: "Nasdaq-100", color: "var(--accent)" },
  { symbol: "BTC", name: "Bitcoin", color: "#f97316" },
];

const resolutions = [
  { value: "15", label: "15m" },
  { value: "30", label: "30m" },
  { value: "60", label: "1H" },
  { value: "D", label: "1D" },
];

interface Position {
  id: string;
  symbol: string;
  direction: "buy" | "sell";
  entry_price: number;
  current_price: number;
  size: number;
  leverage: number;
  take_profit: number;
  stop_loss: number;
  opened_at: string;
}

export const ChartsTab: React.FC = () => {
  const [charts, setCharts] = useState<ChartResponse[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedResolution, setSelectedResolution] = useState(() => {
    return localStorage.getItem("cfd_chartsResolution") || "60";
  });
  const [indicatorSettingsOpen, setIndicatorSettingsOpen] = useState<string | null>(null);
  const [indicatorSettings, setIndicatorSettings] = useState<Record<string, { indicators: string[], strategy: string, available_indicators: string[] }>>(() => {
    const saved = localStorage.getItem("cfd_indicatorSettings");
    return saved ? JSON.parse(saved) : {};
  });
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);

  // Load indicator settings from backend on mount
  useEffect(() => {
    const symbols = ["XAU", "XAG", "US100", "BTC"];
    Promise.all(symbols.map(s => 
      fetch(`/cfd/api/settings/indicators/${s}`).then(r => r.json()).catch(() => null)
    )).then(results => {
      const loaded: Record<string, any> = {};
      results.forEach((data, i) => {
        if (data && !data.error && (data.indicators?.length > 0 || data.strategy)) {
          loaded[symbols[i]] = data;
        }
      });
      if (Object.keys(loaded).length > 0) {
        setIndicatorSettings(prev => ({ ...prev, ...loaded }));
        localStorage.setItem("cfd_indicatorSettings", JSON.stringify({ ...indicatorSettings, ...loaded }));
      }
    });
  }, []);

  // Fetch indicator settings when modal opens
  useEffect(() => {
    if (indicatorSettingsOpen) {
      fetch(`/cfd/api/settings/indicators/${indicatorSettingsOpen}`)
        .then(r => r.json())
        .then(data => {
          if (!data.error) {
            setIndicatorSettings(prev => ({ ...prev, [indicatorSettingsOpen]: data }));
          }
        });
    }
  }, [indicatorSettingsOpen]);

  // Save indicator settings
  const saveIndicatorSettings = async (symbol: string, indicators: string[], strategy: string) => {
    await fetch(`/cfd/api/settings/indicators/${symbol}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ indicators, strategy })
    });
    setIndicatorSettings(prev => ({ ...prev, [symbol]: { indicators, strategy, available_indicators: prev[symbol]?.available_indicators || [] } }));
    setIndicatorSettingsOpen(null);
  };

  useEffect(() => {
    localStorage.setItem("cfd_chartsResolution", selectedResolution);
  }, [selectedResolution]);

  // Persist indicator settings to localStorage
  useEffect(() => {
    localStorage.setItem("cfd_indicatorSettings", JSON.stringify(indicatorSettings));
  }, [indicatorSettings]);

  const fetchChartData = async () => {
    try {
      setLoading(true);
      const chartData: ChartResponse[] = [];
      for (const instrument of instruments) {
        const response = await fetch(
          `${apiUrl(`chart/${instrument.symbol}`)}?resolution=${selectedResolution}&count=24`,
        );
        if (response.ok) {
          const data = await response.json();
          // Transform candles to data format for compatibility
          if (data.candles) {
            chartData.push({
              ...data,
              data: data.candles
            });
          }
        }
      }
      setCharts(chartData);
    } catch (error) {
      console.error("Failed to fetch chart data:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTrades = async () => {
    const url = apiUrl("trades/open");
    console.log("[ChartsTab] Fetching trades from:", url);
    try {
      const [openRes, closedRes] = await Promise.all([
        fetch(url),
        fetch(apiUrl("trades/history")),
      ]);

      console.log("[ChartsTab] openRes status:", openRes.status, openRes.ok);

      const allTrades: Trade[] = [];

      if (openRes.ok) {
        const openData = await openRes.json();
        console.log(
          "[ChartsTab] Open positions:",
          openData.positions?.length || 0,
          openData,
        );
        if (openData.positions) {
          setOpenPositions(openData.positions);
          allTrades.push(
            ...openData.positions.map((p: any) => ({
              ...p,
              result: undefined,
            })),
          );
        }
      } else {
        console.error(
          "[ChartsTab] Failed to fetch open positions:",
          openRes.status,
        );
      }

      if (closedRes.ok) {
        const closedData = await closedRes.json();
        console.log(
          "[ChartsTab] Closed trades:",
          closedData.trades?.length || 0,
        );
        if (closedData.trades) {
          allTrades.push(...closedData.trades);
        }
      }

      console.log("[ChartsTab] Total trades:", allTrades.length);
      setTrades(allTrades);
    } catch (error) {
      console.error("[ChartsTab] Error fetching trades:", error);
    }
  };

  useEffect(() => {
    fetchChartData();
    fetchTrades();
    const interval = setInterval(() => {
      fetchChartData();
      fetchTrades();
    }, 30000);

    // Listen for TP/SL line drag events from chart
    const handleLineAdjust = async (e: CustomEvent) => {
      const { positionId, type, value } = e.detail;
      console.log("[ChartsTab] Line adjust:", positionId, type, value);
      
      // Update local state immediately for smooth UI
      setOpenPositions(prev => prev.map(p => 
        p.id === positionId 
          ? { ...p, [type === 'tp' ? 'take_profit' : 'stop_loss']: value }
          : p
      ));

      // Also update API in background
      try {
        const params = new URLSearchParams({
          [type === 'tp' ? 'take_profit' : 'stop_loss']: value.toString()
        });
        await fetch(apiUrl(`trades/update/${positionId}?${params.toString()}`), {
          method: "POST",
        });
        // Refresh positions after update
        fetchTrades();
      } catch (error) {
        console.error("Failed to update position:", error);
      }
    };

    window.addEventListener("adjustPositionLine", handleLineAdjust as EventListener);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener("adjustPositionLine", handleLineAdjust as EventListener);
    };
  }, [selectedResolution]);

  if (loading && charts.length === 0) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ color: "#4a5568" }}
      >
        <div className="text-xs uppercase tracking-widest">
          Loading charts...
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-2 md:p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span
          className="text-[11px] font-medium uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          Multi-Chart View
        </span>
        <div className="flex gap-0.5">
          {resolutions.map((res) => (
            <button
              key={res.value}
              onClick={() => setSelectedResolution(res.value)}
              className="px-2 py-1 text-[10px] font-medium rounded-sm transition-all"
              style={{
                color: selectedResolution === res.value ? "var(--text-primary)" : "#4a5568",
                backgroundColor:
                  selectedResolution === res.value ? "var(--bg-tertiary)" : "transparent",
              }}
            >
              {res.label}
            </button>
          ))}
          <button
            onClick={() => setIndicatorSettingsOpen(instruments[0]?.symbol || "XAU")}
            className="px-2 py-1 text-[10px] font-medium rounded-sm transition-all hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-muted)" }}
            title="Indicator Settings"
          >
            Settings
          </button>
        </div>
      </div>

      {/* Charts Grid - single column on mobile, 2 cols on desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 md:gap-3">
        {instruments.map((instrument) => {
          const chartData = charts.find((c) => c.symbol === instrument.symbol);
          return (
            <div
              key={instrument.symbol}
              className="rounded-sm overflow-hidden"
              style={{
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--bg-tertiary)",
              }}
            >
              <div
                className="flex items-center justify-between px-2 md:px-3 py-2"
                style={{ borderBottom: "1px solid var(--bg-tertiary)" }}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: instrument.color }}
                  />
                  <button
                    className="text-[11px] font-bold cursor-pointer hover:underline"
                    style={{ color: selectedSymbol === instrument.symbol ? "var(--accent)" : "var(--text-primary)" }}
                    onClick={() => setSelectedSymbol(selectedSymbol === instrument.symbol ? null : instrument.symbol)}
                    title="Click to show SL/TP lines"
                  >
                    {instrument.symbol}
                  </button>
                  {/* Show indicator if position is selected */}
                  {selectedSymbol === instrument.symbol && openPositions.some(p => p.symbol === instrument.symbol) && (
                    <span className="text-[9px] px-1 py-0.5 rounded" style={{ backgroundColor: "var(--accent)", color: "white" }}>
                      SL/TP
                    </span>
                  )}
                  <span className="text-[10px]" style={{ color: "#4a5568" }}>
                    {instrument.name}
                  </span>
                  {/* VIX Display */}
                  {chartData?.vix && (
                    <span
                      className="text-[10px] ml-2 px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: "var(--bg-tertiary)",
                        color: chartData.vix.change_pct > 0 ? "var(--danger)" : "var(--success)",
                      }}
                    >
                      VIX: {chartData.vix.value.toFixed(1)} ({chartData.vix.change_pct > 0 ? "+" : ""}{chartData.vix.change_pct.toFixed(1)}%)
                    </span>
                  )}
                  {/* Settings Icon */}
                  <button
                    className="ml-2 p-1 rounded hover:bg-[var(--bg-tertiary)] transition-colors"
                    style={{ color: "var(--text-muted)" }}
                    onClick={() => setIndicatorSettingsOpen(instrument.symbol)}
                    title="Indicator Settings"
                  >
                    ⚙️
                  </button>
                  {/* Trade markers legend */}
                  {trades.some((t) => t.symbol === instrument.symbol) && (
                    <div
                      className="flex items-center gap-1 ml-2 text-[9px]"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span title="Entry = ▲/▼ triangle, Exit = ■ square">
                        Trades:
                      </span>
                      <span style={{ color: "#023f18ff" }}>▲</span>
                      <span style={{ color: "#5f0808ff" }}>▼</span>
                      <span style={{ color: "#7a7a7bff" }}>■</span>
                    </div>
                  )}
                </div>
                {chartData &&
                  (() => {
                    const isLive = chartData.source === "alpha_vantage";
                    const fetchedAt = chartData.fetched_at
                      ? new Date(chartData.fetched_at + "Z")
                      : null;
                    const ageMs = fetchedAt
                      ? Date.now() - fetchedAt.getTime()
                      : Infinity;
                    const isStale = ageMs > 5 * 60 * 1000;
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
                            backgroundColor: isStale ? "var(--danger)" : "var(--success)",
                          }}
                          title={
                            isStale
                              ? "Data is stale (>5 min old)"
                              : "Data is fresh"
                          }
                        />
                        <span
                          className="text-[9px] px-1 py-0.5 rounded-sm"
                          style={{
                            backgroundColor: "var(--bg-tertiary)",
                            color: isStale ? "var(--danger)" : "var(--text-muted)",
                          }}
                        >
                          {isLive ? "LIVE" : "CACHED"} {ageStr}
                        </span>
                      </div>
                    );
                  })()}
              </div>
              <div className="p-1 md:p-2">
                {chartData && (chartData.data || chartData.candles) && (chartData.data?.length ?? chartData.candles?.length ?? 0) > 0 ? (
                  <CandlestickChart
                    symbol={instrument.symbol}
                    data={chartData.candles || chartData.data || []}
                    height={220}
                    showVolume={true}
                    showRSI={true}
                    trades={trades}
                    selectedPosition={selectedSymbol === instrument.symbol ? openPositions.find(p => p.symbol === instrument.symbol) || null : null}
                  />
                ) : (
                  <div
                    className="h-[220px] flex items-center justify-center"
                    style={{ color: "#4a5568" }}
                  >
                    <div className="text-[10px]">No data</div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Indicator Settings Modal */}
      {indicatorSettingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setIndicatorSettingsOpen(null)}>
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 w-80 max-h-[80vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-sm" style={{ color: "var(--text-primary)" }}>
                ⚙️ {indicatorSettingsOpen} Settings
              </h3>
              <button onClick={() => setIndicatorSettingsOpen(null)} className="text-lg" style={{ color: "var(--text-muted)" }}>×</button>
            </div>
            
            {indicatorSettings[indicatorSettingsOpen] ? (
              <>
                <div className="mb-4">
                  <div className="text-[10px] uppercase mb-2" style={{ color: "var(--text-muted)" }}>Strategy</div>
                  <select
                    className="w-full p-2 rounded text-xs"
                    style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
                    value={indicatorSettings[indicatorSettingsOpen].strategy}
                    onChange={(e) => {
                      const newSettings = { ...indicatorSettings[indicatorSettingsOpen], strategy: e.target.value };
                      setIndicatorSettings(prev => ({ ...prev, [indicatorSettingsOpen]: newSettings }));
                    }}
                  >
                    <option value="mms">MMS (Mean Reversion)</option>
                    <option value="adaptive_regime">Adaptive Regime</option>
                  </select>
                </div>
                
                <div className="mb-4">
                  <div className="text-[10px] uppercase mb-2" style={{ color: "var(--text-muted)" }}>Indicators</div>
                  <div className="space-y-1">
                    {(indicatorSettings[indicatorSettingsOpen].available_indicators || []).map((ind: string) => (
                      <label key={ind} className="flex items-center gap-2 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          checked={indicatorSettings[indicatorSettingsOpen].indicators.includes(ind)}
                          onChange={(e) => {
                            const current = indicatorSettings[indicatorSettingsOpen].indicators;
                            const newIndicators = e.target.checked
                              ? [...current, ind]
                              : current.filter((i: string) => i !== ind);
                            setIndicatorSettings(prev => ({
                              ...prev,
                              [indicatorSettingsOpen]: { ...prev[indicatorSettingsOpen], indicators: newIndicators }
                            }));
                          }}
                          style={{ accentColor: "var(--primary)" }}
                        />
                        <span style={{ color: "var(--text-primary)" }}>{ind}</span>
                      </label>
                    ))}
                  </div>
                </div>
                
                <button
                  className="w-full py-2 rounded text-xs font-bold"
                  style={{ backgroundColor: "var(--primary)", color: "white" }}
                  onClick={() => saveIndicatorSettings(
                    indicatorSettingsOpen,
                    indicatorSettings[indicatorSettingsOpen].indicators,
                    indicatorSettings[indicatorSettingsOpen].strategy
                  )}
                >
                  Save
                </button>
              </>
            ) : (
              <div className="text-center py-4" style={{ color: "var(--text-muted)" }}>Loading...</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
