import React from "react";

interface TradingToggleProps {
  value: boolean;  // false = preview/simulate, true = live
  onChange: (value: boolean) => void;
}

export const TradingToggle: React.FC<TradingToggleProps> = ({ value, onChange }) => {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "10px 12px",
        background: "var(--bg-secondary)",
        borderRadius: "0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}
      >
        Trading Mode
      </span>
      
      <div
        style={{
          position: "relative",
          display: "flex",
          background: "var(--bg-tertiary)",
          borderRadius: "0",
          border: "1px solid var(--border)",
          width: "100%",
          height: "28px",
          cursor: "pointer",
        }}
        onClick={() => onChange(!value)}
      >
        {/* Sliding background */}
        <div
          style={{
            position: "absolute",
            top: "0",
            left: value ? "50%" : "0",
            width: "50%",
            height: "100%",
            background: value ? "#ef4444" : "#22c55e",
            transition: "all 0.15s ease-out",
            zIndex: 0,
          }}
        />
        
        {/* Left option - Preview */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: !value ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            Preview
          </span>
        </div>
        
        {/* Right option - Live */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: value ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            Live
          </span>
        </div>
      </div>
    </div>
  );
};

// Broker selector (separate from trading mode)
interface BrokerToggleProps {
  value: "simulation" | "ibkr";
  onChange: (value: "simulation" | "ibkr") => void;
}

export const BrokerToggle: React.FC<BrokerToggleProps> = ({ value, onChange }) => {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "10px 12px",
        background: "var(--bg-secondary)",
        borderRadius: "0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}
      >
        Broker
      </span>
      
      <div
        style={{
          position: "relative",
          display: "flex",
          background: "var(--bg-tertiary)",
          borderRadius: "0",
          border: "1px solid var(--border)",
          width: "100%",
          height: "28px",
          cursor: "pointer",
        }}
        onClick={() => onChange(value === "simulation" ? "ibkr" : "simulation")}
      >
        {/* Sliding background */}
        <div
          style={{
            position: "absolute",
            top: "0",
            left: value === "simulation" ? "0" : "50%",
            width: "50%",
            height: "100%",
            background: value === "simulation" ? "#eab308" : "#ef4444",
            transition: "all 0.15s ease-out",
            zIndex: 0,
          }}
        />
        
        {/* Left option */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: value === "simulation" ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            Sim
          </span>
        </div>
        
        {/* Right option */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: value === "ibkr" ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            IBKR
          </span>
        </div>
      </div>
    </div>
  );
};

interface DynamicPositionsToggleProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

export const DynamicPositionsToggle: React.FC<DynamicPositionsToggleProps> = ({ value, onChange }) => {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "10px 12px",
        background: "var(--bg-secondary)",
        borderRadius: "0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}
      >
        Dynamic Positions
      </span>
      
      <div
        style={{
          position: "relative",
          display: "flex",
          background: "var(--bg-tertiary)",
          borderRadius: "0",
          border: "1px solid var(--border)",
          width: "100%",
          height: "28px",
          cursor: "pointer",
        }}
        onClick={() => onChange(!value)}
      >
        {/* Sliding background */}
        <div
          style={{
            position: "absolute",
            top: "0",
            left: value ? "50%" : "0",
            width: "50%",
            height: "100%",
            background: value ? "#22c55e" : "#6b7280",
            transition: "all 0.15s ease-out",
            zIndex: 0,
          }}
        />
        
        {/* Left option - Off */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: !value ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            Off
          </span>
        </div>
        
        {/* Right option - On */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "50%",
            height: "100%",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 500,
              color: value ? "white" : "var(--text-muted)",
              transition: "color 0.15s ease",
            }}
          >
            On
          </span>
        </div>
      </div>
    </div>
  );
};
