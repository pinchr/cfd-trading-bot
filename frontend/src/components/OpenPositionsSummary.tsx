import React, { useState, useEffect, useRef } from "react";
import { apiUrl } from "../api";

interface Position {
  id: string;
  symbol: string;
  direction: "buy" | "sell";
  entry_price: number;
  current_price: number;
  size: number;
  leverage: number;
  unrealized_pnl_usd: number;
  margin_usd: number;
  take_profit: number;
  stop_loss: number;
  opened_at: string;
}

interface SymbolConfig {
  step: number;
  min: number;
  max: number;
  decimals: number;
}

const SYMBOL_CONFIG: Record<string, SymbolConfig> = {
  BTC: { step: 1, min: 50000, max: 150000, decimals: 0 },
  XAU: { step: 0.1, min: 2500, max: 3500, decimals: 1 },
  XAG: { step: 0.01, min: 25, max: 40, decimals: 2 },
  US100: { step: 5, min: 15000, max: 25000, decimals: 0 },
  default: { step: 0.5, min: 0, max: 100000, decimals: 2 },
};

interface OpenPositionsSummaryProps {
  onClearSelection?: () => void;
  onClosePosition?: (id: string) => void;
  onSelectPosition?: (position: Position | null) => void;
  selectedPositionId?: string | null;
  lastRefresh?: number | null;
  onRefresh?: () => void;
}

const formatDuration = (openedAt: string): string => {
  const opened = new Date(openedAt);
  const now = new Date();
  const diff = now.getTime() - opened.getTime();
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
};

// Get status color: green < 5s, yellow < 10s, red > 10s
const getStatusColor = (timestamp: number | null | undefined): string => {
  if (!timestamp) return "var(--danger)";
  const ageMs = Date.now() - timestamp;
  if (ageMs < 5000) return "var(--success)";
  if (ageMs < 10000) return "var(--warning)";
  return "var(--danger)";
};

const formatAge = (timestamp: number | null | undefined): string => {
  if (!timestamp) return "";
  const ageMs = Date.now() - timestamp;
  if (ageMs < 60000) return `${Math.floor(ageMs / 1000)}s`;
  return `${Math.floor(ageMs / 60000)}m`;
};

const formatTime = (openedAt: string): string => {
  // Parse as UTC and convert to Warsaw time
  const date = new Date(openedAt.replace('Z', '+00:00'));
  const warsawDate = new Date(date.toLocaleString('en-US', { timeZone: 'Europe/Warsaw' }));
  return warsawDate.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: 'Europe/Warsaw',
  });
};

export const OpenPositionsSummary: React.FC<OpenPositionsSummaryProps> = ({
  onClosePosition,
  onSelectPosition,
  selectedPositionId,
  onClearSelection,
  lastRefresh: externalLastRefresh,
}) => {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(false);
  const [minimized, setMinimized] = useState(false);
  // Use external lastRefresh if provided, otherwise use internal
  const [internalLastFetched, setInternalLastFetched] = useState<number>(Date.now());
  const lastFetched = internalLastFetched;
  
  // Track previous P&L for flash animation
  const [flashingPositions, setFlashingPositions] = useState<Set<string>>(new Set());
  const prevPnLRef = useRef<Record<string, number>>({});
  
  // Update flashing positions when P&L changes
  useEffect(() => {
    const newFlashing = new Set<string>();
    const newPrevPnL: Record<string, number> = {};
    
    positions.forEach(pos => {
      const prevPnl = prevPnLRef.current[pos.id];
      if (prevPnl !== undefined && prevPnl !== pos.unrealized_pnl_usd) {
        newFlashing.add(pos.id);
      }
      newPrevPnL[pos.id] = pos.unrealized_pnl_usd;
    });
    
    prevPnLRef.current = newPrevPnL;
    
    if (newFlashing.size > 0) {
      setFlashingPositions(newFlashing);
      setTimeout(() => setFlashingPositions(new Set()), 500);
    }
  }, [positions]);
  
  const [editingPosition, setEditingPosition] = useState<string | null>(null);
  const [editSl, setEditSl] = useState<number>(0);
  const [editTp, setEditTp] = useState<number>(0);
  const [editSlString, setEditSlString] = useState<string>("");
  const [editTpString, setEditTpString] = useState<string>("");
  const editSlTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editTpTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [slDragStart, setSlDragStart] = useState<{
    x: number;
    value: number;
  } | null>(null);
  const [tpDragStart, setTpDragStart] = useState<{
    x: number;
    value: number;
  } | null>(null);

  const fetchPositions = async () => {
    try {
      // Add timestamp to prevent caching
      const res = await fetch(apiUrl("trades/open") + "?t=" + Date.now());
      if (res.ok) {
        const data = await res.json();
        const newPositions = data.positions || [];
        
        // Only update positions if not editing - otherwise we'd overwrite edit state
        if (!editingPosition) {
          setPositions(newPositions);
        } else {
          // Still update but preserve editing state
          setPositions(prev => {
            // If editing, only update positions that are NOT being edited
            return prev.map(p => {
              if (p.id === editingPosition) {
                // Keep the old position data to avoid overwriting edit state
                const oldPos = prev.find(op => op.id === p.id);
                return oldPos || p;
              }
              const newPos = newPositions.find((np: Position) => np.id === p.id);
              return newPos || p;
            });
          });
        }
        
        // Always update internal timestamp
        setInternalLastFetched(Date.now());
      }
    } catch (error) {
      console.error("Failed to fetch positions:", error);
    }
  };

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 1000);
    return () => clearInterval(interval);
  }, []);

  // Escape key to clear selection
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && onClearSelection) {
        onClearSelection();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClearSelection]);

  const handleClose = async (id: string) => {
    setLoading(true);
    // Optimistic update - remove immediately from UI
    setPositions(prev => prev.filter(p => p.id !== id));
    try {
      const res = await fetch(apiUrl(`trade/${id}/close`), { method: "POST", cache: "no-store" });
      const data = await res.json();
      
      if (res.ok) {
        setTimeout(() => fetchPositions(), 200);
      } else if (data.error && data.error.includes("not found")) {
        // Already closed - just remove from UI, no need to revert
        console.log("Position already closed");
      } else {
        fetchPositions();
      }
      onClosePosition?.(id);
    } catch (error) {
      console.error("Failed to close position:", error);
      fetchPositions();
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (pos: Position) => {
    setEditingPosition(pos.id);
    const cfg = getSymbolConfig(pos.symbol);
    setEditSl(pos.stop_loss);
    setEditTp(pos.take_profit);
    setEditSlString(pos.stop_loss.toFixed(cfg.decimals));
    setEditTpString(pos.take_profit.toFixed(cfg.decimals));
    // Clear any pending timeouts
    if (editSlTimeoutRef.current) {
      clearTimeout(editSlTimeoutRef.current);
      editSlTimeoutRef.current = null;
    }
    if (editTpTimeoutRef.current) {
      clearTimeout(editTpTimeoutRef.current);
      editTpTimeoutRef.current = null;
    }
  };

  const saveEdit = async (id: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        stop_loss: editSl.toString(),
        take_profit: editTp.toString(),
      });
      await fetch(apiUrl(`trade/update/${id}?${params.toString()}`), {
        method: "POST",
      });
      await fetchPositions();
      setEditingPosition(null);
    } catch (error) {
      console.error("Failed to update position:", error);
    } finally {
      setLoading(false);
    }
  };

  const cancelEdit = () => {
    setEditingPosition(null);
    // Clear pending timeouts
    if (editSlTimeoutRef.current) {
      clearTimeout(editSlTimeoutRef.current);
      editSlTimeoutRef.current = null;
    }
    if (editTpTimeoutRef.current) {
      clearTimeout(editTpTimeoutRef.current);
      editTpTimeoutRef.current = null;
    }
  };

  const getSymbolConfig = (symbol: string): SymbolConfig => {
    return SYMBOL_CONFIG[symbol] || SYMBOL_CONFIG.default;
  };

  // Slider drag handlers for SL
  const handleSlDragStart = (e: React.MouseEvent, value: number) => {
    setSlDragStart({ x: e.clientX, value });
  };

  const handleSlDragMove = (e: MouseEvent) => {
    if (!slDragStart) return;
    const config = getSymbolConfig(
      positions.find((p) => p.id === editingPosition)?.symbol || "",
    );
    const deltaPixels = e.clientX - slDragStart.x;
    const sensitivity = config.step * 2; // 2 units per 10 pixels
    const deltaValue =
      Math.round(((deltaPixels / 10) * sensitivity) / config.step) *
      config.step;
    const newValue = slDragStart.value + deltaValue;
    setEditSl(Math.max(config.min, Math.min(config.max, newValue)));
  };

  const handleSlDragEnd = () => {
    setSlDragStart(null);
  };

  // Slider drag handlers for TP
  const handleTpDragStart = (e: React.MouseEvent, value: number) => {
    setTpDragStart({ x: e.clientX, value });
  };

  const handleTpDragMove = (e: MouseEvent) => {
    if (!tpDragStart) return;
    const config = getSymbolConfig(
      positions.find((p) => p.id === editingPosition)?.symbol || "",
    );
    const deltaPixels = e.clientX - tpDragStart.x;
    const sensitivity = config.step * 2;
    const deltaValue =
      Math.round(((deltaPixels / 10) * sensitivity) / config.step) *
      config.step;
    const newValue = tpDragStart.value + deltaValue;
    setEditTp(Math.max(config.min, Math.min(config.max, newValue)));
  };

  const handleTpDragEnd = () => {
    setTpDragStart(null);
  };

  // Add/remove global event listeners for dragging
  useEffect(() => {
    if (slDragStart || tpDragStart) {
      const handleMove = (e: MouseEvent) => {
        if (slDragStart) handleSlDragMove(e);
        if (tpDragStart) handleTpDragMove(e);
      };
      const handleUp = () => {
        handleSlDragEnd();
        handleTpDragEnd();
      };
      window.addEventListener("mousemove", handleMove);
      window.addEventListener("mouseup", handleUp);
      return () => {
        window.removeEventListener("mousemove", handleMove);
        window.removeEventListener("mouseup", handleUp);
      };
    }
  }, [slDragStart, tpDragStart]);

  if (positions.length === 0) {
    return (
      <div
        className="rounded-sm overflow-hidden"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
      >
        {/* Header - clickable to minimize */}
        <button
          onClick={() => setMinimized(!minimized)}
          className="w-full flex items-center justify-between px-3 py-2 transition-colors"
          style={{
            backgroundColor: minimized ? "transparent" : "var(--bg-tertiary)",
            borderBottom: "0.1px solid var(--bg-tertiary)",
          }}
        >
          <span
            className="text-[11px] font-medium uppercase tracking-wider flex items-center gap-2"
            style={{ color: "var(--text-muted)" }}
          >
            Open Positions
            <span className="text-[10px] px-2 py-0.5 rounded-sm" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-muted)" }}>
              0
            </span>
            {!minimized && (
              <span className="text-[9px]" style={{ color: getStatusColor(lastFetched) }}>
                {formatAge(lastFetched)}
              </span>
            )}
          </span>
          <span
            style={{
              color: minimized ? "var(--text-primary)" : "var(--text-muted)",
              transform: minimized ? "rotate(0deg)" : "rotate(180deg)",
              transition: "transform 0.2s, color 0.2s",
            }}
            className="text-[10px]"
          >
            ▼
          </span>
        </button>

        {!minimized && (
          <div className="px-3 py-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
            No open positions
          </div>
        )}
      </div>
    );
  }

  const totalPnl = positions.reduce(
    (sum, p) => sum + (p.unrealized_pnl_usd || 0),
    0,
  );
  const totalMargin = positions.reduce(
    (sum, p) => sum + (p.margin_usd || 0),
    0,
  );

  return (
    <div
      className="rounded-sm overflow-hidden"
      style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--bg-tertiary)" }}
    >
      {/* Header - clickable to minimize */}
      <button
        onClick={() => setMinimized(!minimized)}
        className="w-full flex items-center justify-between px-3 py-2 transition-colors"
        style={{
          backgroundColor: minimized ? "transparent" : "var(--bg-tertiary)",
          borderBottom: "0.1px solid var(--bg-tertiary)",
        }}
      >
        {/* Left: Title + Count + Status */}
        <span
          className="text-[11px] font-medium uppercase tracking-wider flex items-center gap-2"
          style={{ color: "var(--text-muted)" }}
        >
          Open Positions
          <span className="text-[10px] px-2 py-0.5 rounded-sm" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-primary)" }}>
            {positions.length}
          </span>
          {!minimized && (
            <>
              <span 
                className="w-1.5 h-1.5 rounded-full" 
                style={{ backgroundColor: getStatusColor(lastFetched) }}
                title={`Updated ${formatAge(lastFetched)} ago`}
              />
              <span className="text-[9px]" style={{ color: getStatusColor(lastFetched) }}>
                {formatAge(lastFetched)}
              </span>
            </>
          )}
        </span>

        {/* Right: Margin + P&L + Minimize */}
        <div className="flex items-center gap-3">
          {positions.length > 0 && (
            <div className="flex items-center gap-3 text-[10px]">
              <span><span style={{ color: "var(--text-muted)" }}>Margin: </span><span style={{ color: "var(--text-primary)" }}>${totalMargin.toFixed(2)}</span></span>
              <span><span style={{ color: "var(--text-muted)" }}>P&L: </span><span style={{ color: totalPnl >= 0 ? "var(--success)" : "var(--danger)" }}>{totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}</span></span>
            </div>
          )}
          <span
            style={{
              color: minimized ? "var(--text-primary)" : "var(--text-muted)",
              transform: minimized ? "rotate(0deg)" : "rotate(180deg)",
              transition: "transform 0.2s, color 0.2s",
            }}
            className="text-[10px]"
          >
            ▼
          </span>
        </div>
      </button>

      {/* Positions List */}
      {!minimized && (
        <div className="flex flex-col">
        {positions.map((pos) => {
          const pnlColor =
            (pos.unrealized_pnl_usd || 0) >= 0 ? "var(--success)" : "var(--danger)";
          const dirColor = pos.direction === "buy" ? "var(--success)" : "var(--danger)";
          const pnlPct =
            pos.margin_usd > 0
              ? ((pos.unrealized_pnl_usd || 0) / pos.margin_usd) * 100
              : 0;
          
          // Calculate progress to SL and TP
          const entryPrice = pos.entry_price;
          const currentPrice = pos.current_price || entryPrice;
          const tp = pos.take_profit;
          const sl = pos.stop_loss;
          const isBuy = pos.direction === "buy";
          
          let slProgress = 0, tpProgress = 0;
          if (isBuy && sl && tp) {
            const range = tp - sl;
            slProgress = range > 0 ? ((currentPrice - sl) / range) * 100 : 50;
            tpProgress = range > 0 ? ((currentPrice - sl) / range) * 100 : 50;
          } else if (!isBuy && sl && tp) {
            const range = sl - tp;
            slProgress = range > 0 ? ((sl - currentPrice) / range) * 100 : 50;
            tpProgress = range > 0 ? ((sl - currentPrice) / range) * 100 : 50;
          }
          
          const config = getSymbolConfig(pos.symbol);
          const isEditing = editingPosition === pos.id;

          return (
            <div 
              key={pos.id} 
              className="px-3 py-2 cursor-pointer hover:bg-white/5"
              style={{ 
                borderBottom: "1px solid var(--border)",
                borderLeft: `3px solid ${dirColor}`,
                paddingLeft: "calc(12px - 3px)"
              }}
              onClick={() => {
                startEdit(pos);
                onSelectPosition?.(pos);
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {/* Symbol & Direction */}
                  <div className="flex items-center gap-1.5">
                    <span
                      className="text-xs font-bold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {pos.symbol}
                    </span>
                    <span
                      className="text-[9px] font-bold px-1.5 py-0.5 rounded-sm"
                      style={{
                        color: dirColor,
                        backgroundColor: `${dirColor}15`,
                      }}
                    >
                      {pos.direction.toUpperCase()}
                    </span>
                  </div>

                  {/* Size, Leverage & Entry */}
                  <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {pos.size.toFixed(4)} lot (x{pos.leverage || 1}) @{" "}
                    {pos.entry_price.toFixed(2)}
                  </div>

                  {/* Current Price */}
                  <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    → {pos.current_price.toFixed(2)}
                  </div>
                </div>

                {/* P&L */}
                <div className="flex items-center gap-2">
                  <div 
                    className={`text-right transition-all duration-300 ${flashingPositions.has(pos.id) ? 'scale-110 brightness-150' : ''}`}
                    style={{
                      backgroundColor: flashingPositions.has(pos.id) ? `${pnlColor}30` : 'transparent',
                      borderRadius: '4px',
                      padding: flashingPositions.has(pos.id) ? '4px 8px' : '0',
                    }}
                  >
                    <div
                      className="text-xs font-bold"
                      style={{ color: pnlColor }}
                    >
                      {pos.unrealized_pnl_usd >= 0 ? "+" : ""}$
                      {pos.unrealized_pnl_usd.toFixed(2)}
                    </div>
                    <div className="text-[9px]" style={{ color: pnlColor }}>
                      {pnlPct >= 0 ? "+" : ""}
                      {pnlPct.toFixed(1)}%
                    </div>
                  </div>

                  {/* Edit Button */}
                  <button
                    onClick={() => startEdit(pos)}
                    disabled={loading}
                    className="px-2 py-1 text-[9px] font-bold rounded-sm transition-all"
                    style={{
                      backgroundColor: "rgba(59, 130, 246, 0.1)",
                      color: "var(--accent)",
                      border: "1px solid rgba(59, 130, 246, 0.3)",
                      opacity: loading ? 0.5 : 1,
                    }}
                  >
                    EDIT
                  </button>

                  {/* Close Button */}
                  <button
                    onClick={() => handleClose(pos.id)}
                    disabled={loading}
                    className="px-2 py-1 text-[9px] font-bold rounded-sm transition-all"
                    style={{
                      backgroundColor: "rgba(239, 68, 68, 0.1)",
                      color: "var(--danger)",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                      opacity: loading ? 0.5 : 1,
                    }}
                  >
                    CLOSE
                  </button>
                </div>
              </div>

              {/* SL/TP Progress Bar */}
              {sl && tp && (
                <div className="mt-1.5">
                  <div className="flex items-center gap-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--bg-tertiary)" }}>
                    {/* SL zone */}
                    <div 
                      className="h-full rounded-full"
                      style={{ 
                        width: `${Math.min(100, Math.max(0, slProgress))}%`,
                        backgroundColor: "var(--danger)",
                        opacity: 0.6
                      }}
                    />
                    {/* Current price zone */}
                    <div 
                      className="h-full w-1.5 rounded-full"
                      style={{ 
                        backgroundColor: "var(--text-muted)",
                        minWidth: "4px"
                      }}
                    />
                    {/* TP zone */}
                    <div 
                      className="h-full rounded-full flex-1"
                      style={{ 
                        backgroundColor: "var(--success)",
                        opacity: 0.6
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[8px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                    <span>SL: {sl.toFixed(config.decimals)}</span>
                    <span>{formatDuration(pos.opened_at)}</span>
                    <span>TP: {tp.toFixed(config.decimals)}</span>
                  </div>
                </div>
              )}

              {/* SL/TP Display + Open Time */}
              {!isEditing && (
                <div className="flex items-center justify-between mt-1">
                  <div className="flex items-center gap-4 text-[9px]">
                    <span style={{ color: "var(--text-muted)" }}>
                      SL:{" "}
                      <span style={{ color: "var(--danger)" }}>
                        {pos.stop_loss.toFixed(2)}
                      </span>
                    </span>
                    <span style={{ color: "var(--text-muted)" }}>
                      TP:{" "}
                      <span style={{ color: "var(--success)" }}>
                        {pos.take_profit.toFixed(2)}
                      </span>
                    </span>
                  </div>
                  {pos.opened_at && (
                    <span className="text-[9px]" style={{ color: "var(--text-muted)" }}>
                      {formatTime(pos.opened_at)} (
                      {formatDuration(pos.opened_at)})
                    </span>
                  )}
                </div>
              )}

              {/* Edit SL/TP Form */}
              {isEditing && (
                <div
                  className="mt-2 p-2 rounded-sm"
                  style={{ backgroundColor: "var(--bg-primary)" }}
                >
                  {/* Stop Loss */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px]" style={{ color: "var(--danger)" }}>
                      Stop Loss:
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setEditSl((prev) => prev - config.step)}
                        className="px-2 py-0.5 text-[10px] rounded"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                      >
                        −
                      </button>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={editSl.toFixed(2)}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) {
                            setEditSl(val);
                          }
                        }}
                        className="w-20 px-2 py-0.5 text-[10px] text-center rounded"
                        style={{
                          backgroundColor: "var(--bg-tertiary)",
                          color: "var(--danger)",
                        }}
                      />
                      <button
                        onClick={() => {
                          console.log("SL + clicked, current:", editSl, "step:", config.step);
                          setEditSl((prev) => prev + config.step);
                        }}
                        className="px-2 py-0.5 text-[10px] rounded"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {/* Take Profit */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px]" style={{ color: "var(--success)" }}>
                      Take Profit:
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setEditTp((prev) => prev - config.step)}
                        className="px-2 py-0.5 text-[10px] rounded"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                      >
                        −
                      </button>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={editTp.toFixed(2)}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (!isNaN(val)) {
                            setEditTp(val);
                          }
                        }}
                        className="w-20 px-2 py-0.5 text-[10px] text-center rounded"
                        style={{
                          backgroundColor: "var(--bg-tertiary)",
                          border: "1px solid var(--success)33",
                          color: "var(--success)",
                        }}
                      />
                      <button
                        onClick={() => setEditTp((prev) => prev + config.step)}
                        className="px-2 py-0.5 text-[10px] rounded"
                        style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={cancelEdit}
                      className="px-3 py-1 text-[9px] rounded-sm"
                      style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => saveEdit(pos.id)}
                      disabled={loading}
                      className="px-3 py-1 text-[9px] font-bold rounded-sm"
                      style={{
                        backgroundColor: "rgba(34, 197, 94, 0.1)",
                        color: "var(--success)",
                        border: "1px solid rgba(34, 197, 94, 0.3)",
                        opacity: loading ? 0.5 : 1,
                      }}
                    >
                      Save
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      )}
    </div>
  );
};
