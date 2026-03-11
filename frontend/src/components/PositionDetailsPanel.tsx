import React, { useState, useEffect } from "react";
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

interface PositionDetailsPanelProps {
  position: Position;
  onClose: () => void;
  onConfirm: (newTp?: number, newSl?: number) => void;
  isAdjusting?: boolean;
}

export const PositionDetailsPanel: React.FC<PositionDetailsPanelProps> = ({
  position,
  onClose,
  onConfirm,
  isAdjusting = false,
}) => {
  const [pendingTp, setPendingTp] = useState(position.take_profit);
  const [pendingSl, setPendingSl] = useState(position.stop_loss);
  const [hasChanges, setHasChanges] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    setPendingTp(position.take_profit);
    setPendingSl(position.stop_loss);
    setHasChanges(false);
    setConfirming(false);
  }, [position]);

  const tpChanged = pendingTp !== position.take_profit;
  const slChanged = pendingSl !== position.stop_loss;
  const totalChanged = tpChanged || slChanged;

  const handleConfirm = () => {
    setConfirming(true);
    onConfirm(pendingTp, pendingSl);
  };

  const handleCancel = () => {
    setPendingTp(position.take_profit);
    setPendingSl(position.stop_loss);
    setHasChanges(false);
    setConfirming(false);
  };

  const direction = position.direction;
  const entry = position.entry_price;
  const current = position.current_price;

  // Calculate P&L
  const pnl = direction === "buy" 
    ? (current - entry) * position.size * position.leverage
    : (entry - current) * position.size * position.leverage;
  const pnlPct = (pnl / (entry * position.size / position.leverage)) * 100;

  // Slider ranges
  const tpMin = entry * 0.9;
  const tpMax = entry * 1.15;
  const slMin = entry * 0.85;
  const slMax = entry * 1.05;

  return (
    <div style={{
      position: "absolute",
      top: 0,
      right: 0,
      width: "280px",
      height: "100%",
      background: "rgba(15, 20, 30, 0.95)",
      borderLeft: "1px solid rgba(255,255,255,0.1)",
      padding: "16px",
      zIndex: 100,
      overflowY: "auto",
      boxShadow: "-4px 0 20px rgba(0,0,0,0.5)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "18px" }}>{position.symbol}</span>
          <span style={{
            padding: "2px 8px",
            borderRadius: "4px",
            background: direction === "buy" ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
            color: direction === "buy" ? "#22c55e" : "#ef4444",
            fontSize: "12px",
            fontWeight: "bold",
          }}>
            {direction.toUpperCase()}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "transparent",
            border: "none",
            color: "rgba(255,255,255,0.5)",
            cursor: "pointer",
            fontSize: "18px",
          }}
        >
          ✕
        </button>
      </div>

      {/* Entry Price */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "12px", marginBottom: "4px" }}>
          📍 Entry Price
        </div>
        <div style={{ fontSize: "18px", fontWeight: "bold", color: "#fff" }}>
          ${entry.toFixed(2)}
        </div>
      </div>

      {/* Current Price */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "12px", marginBottom: "4px" }}>
          💵 Current Price
        </div>
        <div style={{ fontSize: "18px", fontWeight: "bold", color: "#fff" }}>
          ${current.toFixed(2)}
        </div>
      </div>

      <hr style={{ border: "none", borderTop: "1px solid rgba(255,255,255,0.1)", margin: "16px 0" }} />

      {/* Take Profit Slider */}
      <div style={{ marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <span style={{ color: "rgba(255,255,255,0.7)", fontSize: "13px" }}>🎯 Take Profit</span>
          {tpChanged && (
            <span style={{ color: "#fbbf24", fontSize: "11px" }}>● Unconfirmed</span>
          )}
        </div>
        
        <div style={{ 
          background: "rgba(34, 197, 94, 0.1)", 
          borderRadius: "8px", 
          padding: "12px",
          border: tpChanged ? "1px solid #fbbf24" : "1px solid rgba(34, 197, 94, 0.3)",
        }}>
          <input
            type="range"
            min={tpMin}
            max={tpMax}
            step={0.5}
            value={pendingTp}
            onChange={(e) => {
              setPendingTp(parseFloat(e.target.value));
              setHasChanges(true);
            }}
            style={{
              width: "100%",
              marginBottom: "8px",
              accentColor: "#22c55e",
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "rgba(255,255,255,0.4)" }}>
            <span>${tpMin.toFixed(0)}</span>
            <span style={{ color: "#22c55e", fontWeight: "bold" }}>${pendingTp.toFixed(2)}</span>
            <span>${tpMax.toFixed(0)}</span>
          </div>
        </div>
      </div>

      {/* Stop Loss Slider */}
      <div style={{ marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <span style={{ color: "rgba(255,255,255,0.7)", fontSize: "13px" }}>🛡️ Stop Loss</span>
          {slChanged && (
            <span style={{ color: "#fbbf24", fontSize: "11px" }}>● Unconfirmed</span>
          )}
        </div>
        
        <div style={{ 
          background: "rgba(239, 68, 68, 0.1)", 
          borderRadius: "8px", 
          padding: "12px",
          border: slChanged ? "1px solid #fbbf24" : "1px solid rgba(239, 68, 68, 0.3)",
        }}>
          <input
            type="range"
            min={slMin}
            max={slMax}
            step={0.5}
            value={pendingSl}
            onChange={(e) => {
              setPendingSl(parseFloat(e.target.value));
              setHasChanges(true);
            }}
            style={{
              width: "100%",
              marginBottom: "8px",
              accentColor: "#ef4444",
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "rgba(255,255,255,0.4)" }}>
            <span>${slMin.toFixed(0)}</span>
            <span style={{ color: "#ef4444", fontWeight: "bold" }}>${pendingSl.toFixed(2)}</span>
            <span>${slMax.toFixed(0)}</span>
          </div>
        </div>
      </div>

      <hr style={{ border: "none", borderTop: "1px solid rgba(255,255,255,0.1)", margin: "16px 0" }} />

      {/* P&L Display */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "12px", marginBottom: "4px" }}>
          💰 Unrealized P&L
        </div>
        <div style={{ 
          fontSize: "24px", 
          fontWeight: "bold", 
          color: pnl >= 0 ? "#22c55e" : "#ef4444" 
        }}>
          {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)} USD
          <span style={{ fontSize: "14px", marginLeft: "8px", opacity: 0.7 }}>
            ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* Duration */}
      <div style={{ marginBottom: "20px", color: "rgba(255,255,255,0.5)", fontSize: "12px" }}>
        ⏱️ {position.opened_at}
      </div>

      {/* Action Buttons */}
      {totalChanged && (
        <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
          <button
            onClick={handleCancel}
            style={{
              flex: 1,
              padding: "10px",
              borderRadius: "6px",
              border: "1px solid rgba(255,255,255,0.2)",
              background: "transparent",
              color: "rgba(255,255,255,0.7)",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isAdjusting}
            style={{
              flex: 1,
              padding: "10px",
              borderRadius: "6px",
              border: "none",
              background: isAdjusting ? "#fbbf24" : "#22c55e",
              color: "#000",
              cursor: isAdjusting ? "wait" : "pointer",
              fontSize: "13px",
              fontWeight: "bold",
            }}
          >
            {isAdjusting ? "Saving..." : "Confirm"}
          </button>
        </div>
      )}

      {/* Close Position Button */}
      <button
        onClick={() => {
          if (confirm("Close this position?")) {
            onClose();
          }
        }}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: "6px",
          border: "1px solid #ef4444",
          background: "rgba(239, 68, 68, 0.1)",
          color: "#ef4444",
          cursor: "pointer",
          fontSize: "14px",
          fontWeight: "bold",
        }}
      >
        Close Position
      </button>
    </div>
  );
};

// API functions
export const adjustPosition = async (
  positionId: string,
  takeProfit?: number,
  stopLoss?: number
): Promise<void> => {
  const params = new URLSearchParams();
  if (takeProfit !== undefined) params.set("take_profit", takeProfit.toString());
  if (stopLoss !== undefined) params.set("stop_loss", stopLoss.toString());
  
  const response = await fetch(`${apiUrl}/trades/update/${positionId}?${params}`, {
    method: "POST",
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to adjust position");
  }
};

export const closePosition = async (positionId: string): Promise<void> => {
  const response = await fetch(`${apiUrl}/trade/${positionId}/close`, {
    method: "POST",
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Failed to close position");
  }
};
