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
  data: ChartData[];
  resolution: string;
  count: number;
  source: string;
  fetched_at?: string;
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
  { symbol: "US100", name: "Nasdaq-100", color: "#3b82f6" },
  { symbol: "BTC", name: "Bitcoin", color: "#f97316" },
];

const resolutions = [
  { value: "15", label: "15m" },
  { value: "30", label: "30m" },
  { value: "60", label: "1H" },
  { value: "D", label: "1D" },
];

export const ChartsTab: React.FC = () => {
  const [charts, setCharts] = useState<ChartResponse[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedResolution, setSelectedResolution] = useState(() => {
    return localStorage.getItem("cfd_chartsResolution") || "60";
  });

  useEffect(() => {
    localStorage.setItem("cfd_chartsResolution", selectedResolution);
  }, [selectedResolution]);

  const fetchChartData = async () => {
    try {
      setLoading(true);
      const chartData: ChartResponse[] = [];
      for (const instrument of instruments) {
        const response = await fetch(
          `${apiUrl(`chart/${instrument.symbol}`)}?resolution=${selectedResolution}&count=20`,
        );
        if (response.ok) {
          const data = await response.json();
          if (data.data) chartData.push(data);
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
    return () => clearInterval(interval);
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
          style={{ color: "#64748b" }}
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
                color: selectedResolution === res.value ? "#e2e8f0" : "#4a5568",
                backgroundColor:
                  selectedResolution === res.value ? "#1a1f35" : "transparent",
              }}
            >
              {res.label}
            </button>
          ))}
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
                backgroundColor: "#0d1220",
                border: "1px solid #1a1f35",
              }}
            >
              <div
                className="flex items-center justify-between px-2 md:px-3 py-2"
                style={{ borderBottom: "1px solid #1a1f35" }}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: instrument.color }}
                  />
                  <span
                    className="text-[11px] font-bold"
                    style={{ color: "#e2e8f0" }}
                  >
                    {instrument.symbol}
                  </span>
                  <span className="text-[10px]" style={{ color: "#4a5568" }}>
                    {instrument.name}
                  </span>
                  {/* Trade markers legend */}
                  {trades.some((t) => t.symbol === instrument.symbol) && (
                    <div
                      className="flex items-center gap-1 ml-2 text-[9px]"
                      style={{ color: "#64748b" }}
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
                            backgroundColor: isStale ? "#ef4444" : "#22c55e",
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
                            backgroundColor: "#1a1f35",
                            color: isStale ? "#ef4444" : "#64748b",
                          }}
                        >
                          {isLive ? "LIVE" : "CACHED"} {ageStr}
                        </span>
                      </div>
                    );
                  })()}
              </div>
              <div className="p-1 md:p-2">
                {chartData && chartData.data.length > 0 ? (
                  <CandlestickChart
                    symbol={instrument.symbol}
                    data={chartData.data}
                    height={220}
                    showVolume={true}
                    showRSI={true}
                    trades={trades}
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
    </div>
  );
};
