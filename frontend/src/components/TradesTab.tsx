import React, { useState, useEffect } from "react";
import { apiUrl } from "../api";

interface Position {
  id: string;
  symbol: string;
  name: string;
  direction: string;
  size: number;
  entry_price: number;
  current_price: number;
  take_profit: number;
  stop_loss: number;
  unrealized_pnl_usd: number;
  margin_usd: number;
  opened_at: string;
  status: string;
}

interface ClosedTrade {
  id: string;
  symbol: string;
  name: string;
  direction: string;
  size: number;
  entry_price: number;
  exit_price: number;
  pnl_usd: number;
  opened_at: string;
  closed_at: string;
  result: string;
}

export const TradesTab: React.FC = () => {
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [activeSection, setActiveSection] = useState<"open" | "history">(() => {
    const saved = localStorage.getItem("cfd_tradesSection");
    return saved === "history" ? "history" : "open";
  });
  const [stats, setStats] = useState({
    win_count: 0,
    loss_count: 0,
    win_rate: 0,
    total_pnl_usd: 0,
  });
  const [closingId, setClosingId] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("cfd_tradesSection", activeSection);
  }, [activeSection]);

  const fetchData = async (forceRefresh = false) => {
    const cacheKeyOpen = 'tradesOpen';
    const cacheKeyHist = 'tradesHistory';
    const cacheTimeKey = 'tradesTime';
    const cacheTime = localStorage.getItem(cacheTimeKey);
    // Always skip cache if forceRefresh is true
    if (forceRefresh) {
      // Skip cache, fetch fresh data
    } else if (cacheTime && Date.now() - parseInt(cacheTime) < 5000) {
      const cachedOpen = localStorage.getItem(cacheKeyOpen);
      const cachedHist = localStorage.getItem(cacheKeyHist);
      if (cachedOpen && cachedHist) {
        setOpenPositions(JSON.parse(cachedOpen).positions || []);
        const histData = JSON.parse(cachedHist);
        setClosedTrades(histData.trades || []);
        setStats({
          win_count: histData.win_count || 0,
          loss_count: histData.loss_count || 0,
          win_rate: histData.win_rate || 0,
          total_pnl_usd: histData.total_pnl_usd || 0,
        });
        return;
      }
    }

    try {
      // Add timestamp to prevent caching
      const [openRes, histRes] = await Promise.all([
        fetch(apiUrl("trades/open") + "?t=" + Date.now(), { cache: "no-store" }),
        fetch(apiUrl("trades/history") + "?t=" + Date.now(), { cache: "no-store" }),
      ]);
      if (openRes.ok) {
        const data = await openRes.json();
        setOpenPositions(data.positions || []);
        localStorage.setItem(cacheKeyOpen, JSON.stringify(data));
      }
      if (histRes.ok) {
        const data = await histRes.json();
        setClosedTrades(data.trades || []);
        setStats({
          win_count: data.win_count || 0,
          loss_count: data.loss_count || 0,
          win_rate: data.win_rate || 0,
          total_pnl_usd: data.total_pnl_usd || 0,
        });
        localStorage.setItem(cacheKeyHist, JSON.stringify(data));
        localStorage.setItem(cacheTimeKey, Date.now().toString());
      }
    } catch (error) {
      console.error("Failed to fetch trades:", error);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 60 seconds
    return () => clearInterval(interval);
  }, []);

  const closeTrade = async (positionId: string) => {
    setClosingId(positionId);
    // Optimistic update - remove immediately from UI
    setOpenPositions(prev => prev.filter(p => p.id !== positionId));
    try {
      const response = await fetch(apiUrl(`trade/close/${positionId}`), {
        method: "POST",
        cache: "no-store",
      });
      const data = await response.json();
      
      if (response.ok) {
        localStorage.removeItem('tradesOpen');
        localStorage.removeItem('tradesHistory');
        localStorage.removeItem('tradesTime');
        setTimeout(() => fetchData(true), 200);
      } else if (data.error && data.error.includes("not found")) {
        // Position already closed (probably by TP/SL) - just remove from UI
        console.log("Position already closed, removing from list");
      } else {
        // Other error - revert
        fetchData(true);
      }
    } catch (error) {
      console.error("Failed to close trade:", error);
      fetchData(true);
    } finally {
      setClosingId(null);
    }
  };

  const formatPrice = (price: number): string => {
    if (price > 10000) return price.toFixed(0);
    if (price > 100) return price.toFixed(2);
    return price.toFixed(4);
  };

  const formatTime = (dateStr: string, includeDate = false): string => {
    // Parse as UTC and convert to Warsaw time
    const date = new Date(dateStr.replace('Z', '+00:00'));
    // Warsaw is UTC+1 (or UTC+2 during DST)
    const warsawDate = new Date(date.toLocaleString('en-US', { timeZone: 'Europe/Warsaw' }));
    
    if (includeDate) {
      // Show date + time for trades
      return warsawDate.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: 'Europe/Warsaw',
      });
    }
    // Just time for recent trades
    return warsawDate.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: 'Europe/Warsaw',
    });
  };

  const getDateGroup = (dateStr: string): string => {
    // Group trades by day
    const date = new Date(dateStr.replace('Z', '+00:00'));
    const warsawDate = new Date(date.toLocaleString('en-US', { timeZone: 'Europe/Warsaw' }));
    return warsawDate.toLocaleDateString("en-GB", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      timeZone: 'Europe/Warsaw',
    });
  };

  return (
    <div className="flex flex-col h-full p-2 md:p-4 gap-2 md:gap-3 overflow-auto">
      {/* Stats Bar */}
      <div
        className="flex flex-wrap items-center gap-2 md:gap-4 px-3 md:px-4 py-2 md:py-3 rounded-sm"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
      >
        <StatPill
          label="Open"
          value={openPositions.length.toString()}
          color="var(--accent)"
        />
        <StatPill
          label="Closed"
          value={(stats.win_count + stats.loss_count).toString()}
          color="var(--text-muted)"
        />
        <StatPill
          label="Wins"
          value={stats.win_count.toString()}
          color="var(--success)"
        />
        <StatPill
          label="Losses"
          value={stats.loss_count.toString()}
          color="var(--danger)"
        />
        <StatPill
          label="WR"
          value={`${stats.win_rate}%`}
          color={stats.win_rate >= 50 ? "var(--success)" : "var(--danger)"}
        />
        <div className="flex items-center gap-2 ml-auto">
          <span
            className="text-[10px] uppercase tracking-wider hidden sm:inline"
            style={{ color: "var(--text-muted)" }}
          >
            Total P&L:
          </span>
          <span
            className="text-xs md:text-sm font-bold"
            style={{ color: stats.total_pnl_usd >= 0 ? "var(--success)" : "var(--danger)" }}
          >
            {stats.total_pnl_usd >= 0 ? "+" : ""}$
            {stats.total_pnl_usd.toFixed(2)} USD
          </span>
        </div>
      </div>

      {/* Section Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveSection("open")}
            className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm transition-all"
            style={{
              color: activeSection === "open" ? "var(--text-primary)" : "var(--text-muted)",
              backgroundColor:
                activeSection === "open" ? "var(--bg-tertiary)" : "transparent",
            }}
          >
            Open ({openPositions.length})
          </button>
          <button
            onClick={() => setActiveSection("history")}
            className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm transition-all"
            style={{
              color: activeSection === "history" ? "var(--text-primary)" : "var(--text-muted)",
              backgroundColor:
                activeSection === "history" ? "var(--bg-tertiary)" : "transparent",
            }}
          >
            History ({closedTrades.length})
          </button>
        </div>
      </div>

      {/* Content */}
      <div
        className="flex-1 rounded-sm overflow-hidden"
        style={{ 
          backgroundColor: "var(--bg-secondary)", 
          border: "1px solid var(--bg-tertiary)",
        }}
      >
        {activeSection === "open" ? (
          <div className="h-full overflow-auto">
            {openPositions.length === 0 ? (
              <div
                className="h-full flex items-center justify-center"
                style={{ color: "var(--text-muted)" }}
              >
                <div className="text-center">
                  <div className="text-xs uppercase tracking-widest mb-1">
                    No Open Positions
                  </div>
                  <div className="text-[10px]">
                    Use the signals tab to open trades
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Mobile cards */}
                <div className="md:hidden p-2 space-y-2">
                  {openPositions.map((pos) => {
                    const pnlColor =
                      pos.unrealized_pnl_usd >= 0 ? "var(--success)" : "var(--danger)";
                    const dirColor =
                      pos.direction === "buy" ? "var(--success)" : "var(--danger)";
                    return (
                      <div
                        key={pos.id}
                        className="rounded-sm p-3"
                        style={{
                          backgroundColor: "var(--bg-primary)",
                          border: "1px solid #131825",
                        }}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span
                              className="font-bold text-xs"
                              style={{ color: "var(--text-primary)" }}
                            >
                              {pos.symbol}
                            </span>
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color: dirColor,
                                backgroundColor: `${dirColor}15`,
                              }}
                            >
                              {pos.direction.toUpperCase()}
                            </span>
                            <span
                              className="text-[10px]"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {pos.size}
                            </span>
                          </div>
                          <span
                            className="text-xs font-bold"
                            style={{ color: pnlColor }}
                          >
                            {pos.unrealized_pnl_usd >= 0 ? "+" : ""}$
                            {pos.unrealized_pnl_usd.toFixed(2)} USD
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px] mb-2">
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>Entry: </span>
                            <span style={{ color: "#94a3b8" }}>
                              {formatPrice(pos.entry_price)}
                            </span>
                          </div>
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>Now: </span>
                            <span style={{ color: "var(--text-primary)" }}>
                              {formatPrice(pos.current_price)}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-[10px] mb-2">
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>TP: </span>
                            <span style={{ color: "var(--success)" }}>
                              {formatPrice(pos.take_profit)}
                            </span>
                          </div>
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>SL: </span>
                            <span style={{ color: "var(--danger)" }}>
                              {formatPrice(pos.stop_loss)}
                            </span>
                          </div>
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>
                              {formatTime(pos.opened_at, true)}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => closeTrade(pos.id)}
                          disabled={closingId === pos.id}
                          className="w-full py-1.5 text-[10px] font-bold rounded-sm transition-all"
                          style={{
                            backgroundColor: "rgba(239, 68, 68, 0.1)",
                            color: "var(--danger)",
                            border: "1px solid rgba(239, 68, 68, 0.3)",
                            opacity: closingId === pos.id ? 0.5 : 1,
                          }}
                        >
                          {closingId === pos.id
                            ? "CLOSING..."
                            : "CLOSE POSITION"}
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Desktop table */}
                <table className="w-full text-[11px] hidden md:table">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
                      <th
                        className="px-4 py-2.5 text-left font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Symbol
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Dir.
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Size
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Entry
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Current
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        TP
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        SL
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        P&L (USD)
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Opened
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Action
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {openPositions.map((pos) => {
                      const pnlColor =
                        pos.unrealized_pnl_usd >= 0 ? "var(--success)" : "var(--danger)";
                      const dirColor =
                        pos.direction === "buy" ? "var(--success)" : "var(--danger)";
                      return (
                        <tr
                          key={pos.id}
                          style={{ borderBottom: "1px solid #131825" }}
                        >
                          <td className="px-4 py-2.5">
                            <div>
                              <span
                                className="font-bold text-xs"
                                style={{ color: "var(--text-primary)" }}
                              >
                                {pos.symbol}
                              </span>
                              <span
                                className="text-[9px] ml-1.5"
                                style={{ color: "var(--text-muted)" }}
                              >
                                {pos.name}
                              </span>
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color: dirColor,
                                backgroundColor: `${dirColor}15`,
                              }}
                            >
                              {pos.direction.toUpperCase()}
                            </span>
                          </td>
                          <td
                            className="px-3 py-2.5 text-center"
                            style={{ color: "#94a3b8" }}
                          >
                            {pos.size}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "#94a3b8" }}
                          >
                            {formatPrice(pos.entry_price)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "var(--text-primary)" }}
                          >
                            {formatPrice(pos.current_price)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "var(--success)" }}
                          >
                            {formatPrice(pos.take_profit)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "var(--danger)" }}
                          >
                            {formatPrice(pos.stop_loss)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right font-bold"
                            style={{ color: pnlColor }}
                          >
                            {pos.unrealized_pnl_usd >= 0 ? "+" : ""}$
                            {pos.unrealized_pnl_usd.toFixed(2)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-center"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {formatTime(pos.opened_at, true)}
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            <button
                              onClick={() => closeTrade(pos.id)}
                              disabled={closingId === pos.id}
                              className="px-3 py-1 text-[10px] font-bold rounded-sm transition-all"
                              style={{
                                backgroundColor: "rgba(239, 68, 68, 0.1)",
                                color: "var(--danger)",
                                border: "1px solid rgba(239, 68, 68, 0.3)",
                                opacity: closingId === pos.id ? 0.5 : 1,
                              }}
                            >
                              {closingId === pos.id ? "..." : "CLOSE"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>
        ) : (
          <div className="h-full overflow-auto">
            {closedTrades.length === 0 ? (
              <div
                className="h-full flex items-center justify-center"
                style={{ color: "var(--text-muted)" }}
              >
                <div className="text-center">
                  <div className="text-xs uppercase tracking-widest mb-1">
                    No Trade History
                  </div>
                  <div className="text-[10px]">
                    Closed trades will appear here
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Mobile cards */}
                <div className="md:hidden p-2 space-y-2">
                  {closedTrades.map((trade) => {
                    const pnlColor = trade.pnl_usd >= 0 ? "var(--success)" : "var(--danger)";
                    const dirColor =
                      trade.direction === "buy" ? "var(--success)" : "var(--danger)";
                    return (
                      <div
                        key={trade.id}
                        className="rounded-sm p-3"
                        style={{
                          backgroundColor: "var(--bg-primary)",
                          border: "1px solid #131825",
                        }}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span
                              className="font-bold text-xs"
                              style={{ color: "var(--text-primary)" }}
                            >
                              {trade.symbol}
                            </span>
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color: dirColor,
                                backgroundColor: `${dirColor}15`,
                              }}
                            >
                              {trade.direction.toUpperCase()}
                            </span>
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color:
                                  trade.result === "win"
                                    ? "var(--success)"
                                    : "var(--danger)",
                                backgroundColor:
                                  trade.result === "win"
                                    ? "rgba(34, 197, 94, 0.1)"
                                    : "rgba(239, 68, 68, 0.1)",
                              }}
                            >
                              {trade.result.toUpperCase()}
                            </span>
                          </div>
                          <span
                            className="text-xs font-bold"
                            style={{ color: pnlColor }}
                          >
                            {trade.pnl_usd >= 0 ? "+" : ""}$
                            {trade.pnl_usd.toFixed(2)} USD
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px]">
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>Entry: </span>
                            <span style={{ color: "#94a3b8" }}>
                              {formatPrice(trade.entry_price)}
                            </span>
                          </div>
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>Exit: </span>
                            <span style={{ color: "#94a3b8" }}>
                              {formatPrice(trade.exit_price)}
                            </span>
                          </div>
                          <div style={{ color: "var(--text-muted)" }}>
                            {formatTime(trade.closed_at, true)}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Desktop table */}
                <table className="w-full text-[11px] hidden md:table">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
                      <th
                        className="px-4 py-2.5 text-left font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Symbol
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Dir.
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Opened
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Entry
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Exit
                      </th>
                      <th
                        className="px-3 py-2.5 text-right font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        P&L
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Result
                      </th>
                      <th
                        className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Closed
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {closedTrades.map((trade) => {
                      const pnlColor =
                        trade.pnl_usd >= 0 ? "var(--success)" : "var(--danger)";
                      const dirColor =
                        trade.direction === "buy" ? "var(--success)" : "var(--danger)";
                      return (
                        <tr
                          key={trade.id}
                          style={{ borderBottom: "1px solid #131825" }}
                        >
                          <td className="px-4 py-2.5">
                            <span
                              className="font-bold text-xs"
                              style={{ color: "var(--text-primary)" }}
                            >
                              {trade.symbol}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color: dirColor,
                                backgroundColor: `${dirColor}15`,
                              }}
                            >
                              {trade.direction.toUpperCase()}
                            </span>
                          </td>
                          <td
                            className="px-3 py-2.5 text-center"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {formatTime(trade.opened_at, true)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "#94a3b8" }}
                          >
                            {formatPrice(trade.entry_price)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right"
                            style={{ color: "#94a3b8" }}
                          >
                            {formatPrice(trade.exit_price)}
                          </td>
                          <td
                            className="px-3 py-2.5 text-right font-bold"
                            style={{ color: pnlColor }}
                          >
                            {trade.pnl_usd >= 0 ? "+" : ""}$
                            {trade.pnl_usd.toFixed(2)}
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            <span
                              className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                              style={{
                                color:
                                  trade.result === "win"
                                    ? "var(--success)"
                                    : "var(--danger)",
                                backgroundColor:
                                  trade.result === "win"
                                    ? "rgba(34, 197, 94, 0.1)"
                                    : "rgba(239, 68, 68, 0.1)",
                              }}
                            >
                              {trade.result.toUpperCase()}
                            </span>
                          </td>
                          <td
                            className="px-3 py-2.5 text-center"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {formatTime(trade.closed_at, true)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const StatPill: React.FC<{ label: string; value: string; color: string }> = ({
  label,
  value,
  color,
}) => (
  <div className="flex items-center gap-1.5">
    <span
      className="text-[10px] uppercase tracking-wider"
      style={{ color: "var(--text-muted)" }}
    >
      {label}:
    </span>
    <span className="text-[11px] font-bold" style={{ color }}>
      {value}
    </span>
  </div>
);
