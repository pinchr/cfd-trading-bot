import React, { useState, useEffect } from "react";
import { apiUrl } from "../api";
import { TradingToggle, BrokerToggle, DynamicPositionsToggle } from "./GlassToggle";

// Trading Sessions - major market hours in UTC
interface TradingSession {
  name: string;
  city: string;
  openHour: number;
  closeHour: number;
}

const SESSIONS: TradingSession[] = [
  { name: "Sydney", city: "Sydney", openHour: 22, closeHour: 7 },    // 22:00-07:00 UTC
  { name: "Tokyo", city: "Tokyo", openHour: 0, closeHour: 9 },      // 00:00-09:00 UTC  
  { name: "London", city: "London", openHour: 7, closeHour: 16 },   // 07:00-16:00 UTC
  { name: "New York", city: "NewYork", openHour: 14.5, closeHour: 23 }, // 14:30-23:00 UTC
];

function isSessionOpen(session: TradingSession): boolean {
  const now = new Date();
  const utcHour = now.getUTCHours() + now.getUTCMinutes() / 60;
  
  // Handle sessions that span midnight
  if (session.openHour > session.closeHour) {
    return utcHour >= session.openHour || utcHour < session.closeHour;
  }
  return utcHour >= session.openHour && utcHour < session.closeHour;
}

function getSessionStatus(session: TradingSession): { open: boolean; status: string } {
  const now = new Date();
  const utcHour = now.getUTCHours() + now.getUTCMinutes() / 60;
  const open = isSessionOpen(session);
  
  if (open) {
    // Calculate time until close
    let hoursLeft = session.closeHour - utcHour;
    if (hoursLeft < 0) hoursLeft += 24;
    if (hoursLeft >= 0) {
      const h = Math.floor(hoursLeft);
      const m = Math.floor((hoursLeft - h) * 60);
      return { open: true, status: `Opened ${h}h ${m}m` };
    }
  } else {
    // Calculate time until open
    let hoursUntil = session.openHour - utcHour;
    if (hoursUntil < 0) hoursUntil += 24;
    const h = Math.floor(hoursUntil);
    const m = Math.floor((hoursUntil - h) * 60);
    return { open: false, status: `in ${h}h ${m}m` };
  }
  return { open, status: open ? "Opened" : "Closed" };
}

const MarketStatus: React.FC = () => {
  const [time, setTime] = useState({ utc: "", warsaw: "" });
  
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime({
        utc: now.toLocaleTimeString("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit" }),
        warsaw: now.toLocaleTimeString("en-GB", { timeZone: "Europe/Warsaw", hour: "2-digit", minute: "2-digit" }),
      });
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-2 rounded-sm" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="text-[10px] mb-2" style={{ color: "#6b7280" }}>
        SESJE • {time.warsaw} ({time.utc} UTC)
      </div>
      <div className="space-y-1">
        {SESSIONS.map((s) => {
          const { open, status } = getSessionStatus(s);
          return (
            <div key={s.name} className="flex items-center justify-between text-[10px]">
              <div className="flex items-center gap-1.5">
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: open ? "var(--success)" : "var(--danger)" }}
                />
                <span style={{ color: "#e5e7eb" }}>{s.name}</span>
              </div>
              <span style={{ color: open ? "var(--success)" : "var(--text-secondary)" }}>
                {status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

interface SidebarProps {
  accountData?: any;
  broker?: "simulation" | "ibkr";
  autoTrade?: boolean;
  onBrokerChange?: (broker: "simulation" | "ibkr") => void;
  onAutoTradeChange?: (autoTrade: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ accountData, broker = "simulation", autoTrade = false, onBrokerChange, onAutoTradeChange }) => {
  const [lastScan, setLastScan] = useState("--");
  const [isScanning, setIsScanning] = useState(false);
  const [dynamicPositions, setDynamicPositions] = useState(() => {
    const saved = localStorage.getItem("dynamicPositions");
    return saved ? JSON.parse(saved) : false;
  });

  const handleBrokerChange = async (newBroker: "simulation" | "ibkr") => {
    onBrokerChange?.(newBroker);
    try {
      await fetch(`${apiUrl("trading-mode")}?broker=${newBroker}&autoTrade=${autoTrade}`, { method: "POST" });
    } catch (e) {
      console.error("Failed to set broker:", e);
    }
  };

  const handleAutoTradeChange = async (enabled: boolean) => {
    onAutoTradeChange?.(enabled);
    try {
      await fetch(`${apiUrl("trading-mode")}?broker=${broker}&autoTrade=${enabled}`, { method: "POST" });
    } catch (e) {
      console.error("Failed to set mode:", e);
    }
  };

  const handleDynamicPositionsChange = async (enabled: boolean) => {
    setDynamicPositions(enabled);
    localStorage.setItem("dynamicPositions", JSON.stringify(enabled));
    try {
      await fetch(`${apiUrl("settings/dynamic-positions")}?enabled=${enabled}`, { method: "POST" });
    } catch (e) {
      console.error("Failed to set dynamic positions:", e);
    }
  };

  // API returns nested "account" object with stats
  const account = accountData?.account ?? accountData;
  const balance = account?.balance_usd ?? accountData?.balance_usd ?? 0;
  const equity = account?.equity_usd ?? accountData?.equity_usd ?? 0;
  const openTrades = account?.open_trades ?? accountData?.open_trades ?? 0;
  const closedTrades = account?.closed_trades ?? accountData?.closed_trades ?? 0;
  const winRate = account?.win_rate ?? accountData?.win_rate ?? 0;
  const winCount = account?.win_count ?? accountData?.win_count ?? 0;
  const lossCount = account?.loss_count ?? accountData?.loss_count ?? 0;
  const totalPnl = account?.total_pnl_usd ?? 0;
  const accountMode = account?.mode ?? accountData?.mode ?? "simulate";
  
  // Calculate drawdown
  const peakEquity = account?.peak_equity_usd ?? accountData?.peak_equity_usd ?? equity;
  const drawdown = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;
  const showDrawdownAlert = drawdown > 5;

  useEffect(() => {
    const updateScan = () => {
      if (accountData?.last_scan) {
        const scanTime = new Date(accountData.last_scan);
        const now = new Date();
        const diffSecs = Math.floor(
          (now.getTime() - scanTime.getTime()) / 1000,
        );
        if (diffSecs < 5) setLastScan("Now");
        else if (diffSecs < 60) setLastScan(`${diffSecs}s ago`);
        else if (diffSecs < 3600)
          setLastScan(`${Math.floor(diffSecs / 60)}m ago`);
        else setLastScan(`${Math.floor(diffSecs / 3600)}h ago`);
      }
    };
    updateScan();
    const interval = setInterval(updateScan, 1000);
    return () => clearInterval(interval);
  }, [accountData]);

  const resetAccount = async () => {
    try {
      await fetch(apiUrl("account/reset"), { method: "POST" });
    } catch (error) {
      console.error("Failed to reset account:", error);
    }
  };

  const pnlColor = totalPnl >= 0 ? "var(--success)" : "var(--danger)";
  // Use initial_balance from account if available, fallback to calculating from equity - balance
  const initialBalance = accountData?.initial_balance_usd ?? equity - totalPnl;
  const equityChange = totalPnl; // Total P&L is the equity change from initial
  const equityChangePct =
    initialBalance > 0 ? (equityChange / initialBalance) * 100 : 0;

  return (
    <div
      className="w-60 h-full flex flex-col overflow-y-auto"
      style={{ backgroundColor: "var(--bg-secondary)", borderRight: "1px solid var(--bg-tertiary)" }}
    >
      {/* Balance Section */}
      <div className="p-4" style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
        <div
          className="text-[10px] uppercase tracking-widest mb-1.5"
          style={{ color: "#4a5568" }}
        >
          Balance
        </div>
        <div className="text-lg font-bold mb-0.5" style={{ color: "var(--text-primary)" }}>
          ${balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}{" "}
          <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>
            USD
          </span>
        </div>
      </div>

      {/* Drawdown Alert */}
      {showDrawdownAlert && (
        <div 
          className="p-3 mx-2 mt-2 rounded-md"
          style={{ 
            backgroundColor: "rgba(239, 68, 68, 0.15)", 
            border: "1px solid rgba(239, 68, 68, 0.4)"
          }}
        >
          <div className="flex items-center gap-2">
            <span className="text-lg">⚠️</span>
            <div>
              <div className="text-xs font-bold" style={{ color: "#ef4444" }}>
                DRAWDOWN ALERT
              </div>
              <div className="text-[10px]" style={{ color: "#ef4444" }}>
                {drawdown.toFixed(1)}% below peak (${peakEquity.toFixed(0)})
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Equity Section */}
      <div className="p-4" style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
        <div
          className="text-[10px] uppercase tracking-widest mb-1.5"
          style={{ color: "#4a5568" }}
        >
          Equity
        </div>
        <div className="text-base font-bold" style={{ color: "var(--text-primary)" }}>
          ${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}{" "}
          <span
            className="text-[10px] font-normal"
            style={{ color: "var(--text-muted)" }}
          >
            USD
          </span>
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <span className="text-[11px] font-medium" style={{ color: pnlColor }}>
            {equityChange >= 0 ? "+" : ""}${equityChange.toFixed(2)} USD
          </span>
          <span className="text-[10px]" style={{ color: pnlColor }}>
            ({equityChangePct >= 0 ? "+" : ""}
            {equityChangePct.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div
        className="p-4 grid grid-cols-2 gap-3"
        style={{ borderBottom: "1px solid var(--bg-tertiary)" }}
      >
        <StatBox label="Open" value={openTrades.toString()} color="var(--accent)" />
        <StatBox
          label="Closed"
          value={closedTrades.toString()}
          color="var(--text-muted)"
        />
        <StatBox
          label="Wins"
          value={winCount.toString()}
          color="var(--success)"
        />
        <StatBox
          label="Losses"
          value={lossCount.toString()}
          color="var(--danger)"
        />
        {/* Win Rate Donut */}
        <div className="flex flex-col items-center justify-center p-2">
          <div className="relative" style={{ width: 48, height: 48 }}>
            <svg viewBox="0 0 36 36" className="w-12 h-12">
              {/* Background circle */}
              <circle
                cx="18" cy="18" r="15.9"
                fill="none"
                stroke="var(--bg-tertiary)"
                strokeWidth="3"
              />
              {/* Win arc */}
              <circle
                cx="18" cy="18" r="15.9"
                fill="none"
                stroke={winRate >= 50 ? "var(--success)" : "var(--danger)"}
                strokeWidth="3"
                strokeDasharray={`${winRate} ${100 - winRate}`}
                strokeDashoffset="25"
                transform="rotate(-90 18 18)"
              />
            </svg>
            <div 
              className="absolute inset-0 flex items-center justify-center text-[10px] font-bold"
              style={{ color: winRate >= 50 ? "var(--success)" : "var(--danger)" }}
            >
              {winRate}%
            </div>
          </div>
          <div className="text-[9px] mt-1" style={{ color: "var(--text-muted)" }}>
            Win Rate
          </div>
        </div>
        <StatBox
          label="Total P&L"
          value={`${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(0)}`}
          color={pnlColor}
        />
      </div>

      {/* Trading Mode */}
      <TradingToggle
        value={autoTrade}
        onChange={handleAutoTradeChange}
      />
      
      {/* Broker */}
      <BrokerToggle
        value={broker}
        onChange={handleBrokerChange}
      />

      {/* Dynamic Positions */}
      <DynamicPositionsToggle
        value={dynamicPositions}
        onChange={handleDynamicPositionsChange}
      />

      {/* Instruments
      <div className="p-4" style={{ borderBottom: '1px solid var(--bg-tertiary)' }}>
        <div className="text-[10px] uppercase tracking-widest mb-2.5" style={{ color: '#4a5568' }}>
          Instruments
        </div>
        <div className="space-y-1.5">
          {[
            { symbol: 'XAU', name: 'Gold', color: '#eab308' },
            { symbol: 'XAG', name: 'Silver', color: '#94a3b8' },
            { symbol: 'US100', name: 'Nasdaq', color: 'var(--accent)' },
            { symbol: 'BTC', name: 'Bitcoin', color: '#f97316' },
          ].map((inst) => (
            <div key={inst.symbol} className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: inst.color }} />
                <span className="text-[11px] font-medium" style={{ color: '#c8cdd8' }}>
                  {inst.symbol}
                </span>
              </div>
              <span className="text-[10px]" style={{ color: '#4a5568' }}>
                {inst.name}
              </span>
            </div>
          ))}
        </div>
      </div> */}

      {/* Market Status - replaces Scanner/Last scan */}
      <div className="p-3" style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
        <MarketStatus />
      </div>

      {/* Scanner Status - replaced by MarketStatus */}
      {/*
      <div className="p-4" style={{ borderBottom: "1px solid var(--bg-tertiary)" }}>
        <div className="flex items-center justify-between mb-2">
          <div
            className="text-[10px] uppercase tracking-widest"
            style={{ color: "#4a5568" }}
          >
            Scanner
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${isScanning ? "animate-pulse" : ""}`}
              style={{ backgroundColor: "var(--success)" }}
            />
            <span className="text-[10px]" style={{ color: "var(--success)" }}>
              Active
            </span>
          </div>
        </div>
      </div>
      */}

      {/* Reset Button */}
      <div className="p-4 mt-auto">
        <button
          onClick={resetAccount}
          className="w-full text-[10px] py-1.5 rounded-sm border transition-all hover:bg-opacity-10"
          style={{
            borderColor: "var(--bg-tertiary)",
            color: "#4a5568",
          }}
        >
          Reset Account
        </button>
      </div>
    </div>
  );
};

const StatBox: React.FC<{ label: string; value: string; color: string }> = ({
  label,
  value,
  color,
}) => (
  <div className="p-2.5 rounded-sm" style={{ backgroundColor: "var(--bg-primary)" }}>
    <div
      className="text-[9px] uppercase tracking-widest mb-1"
      style={{ color: "#4a5568" }}
    >
      {label}
    </div>
    <div className="text-sm font-bold" style={{ color }}>
      {value}
    </div>
  </div>
);
