import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

interface ChartData {
  time: string;
  price: number;
  rsi?: number;
  macd?: number;
  volume?: number;
}

interface PriceChartProps {
  symbol: string;
  data?: ChartData[];
  height?: number;
  showIndicators?: boolean;
}

const mockChartData: ChartData[] = [
  { time: "09:00", price: 2050.5, rsi: 55, macd: 0.5 },
  { time: "10:00", price: 2052.75, rsi: 58, macd: 0.8 },
  { time: "11:00", price: 2048.25, rsi: 52, macd: 0.3 },
  { time: "12:00", price: 2055.0, rsi: 62, macd: 1.2 },
  { time: "13:00", price: 2061.5, rsi: 68, macd: 1.8 },
  { time: "14:00", price: 2058.75, rsi: 65, macd: 1.5 },
  { time: "15:00", price: 2065.25, rsi: 72, macd: 2.1 },
  { time: "16:00", price: 2062.0, rsi: 69, macd: 1.9 },
];

export const PriceChart: React.FC<PriceChartProps> = ({
  symbol,
  data = mockChartData,
  height = 200,
  showIndicators = false,
}) => {
  const [loading, setLoading] = useState(false);
  const [chartData, setChartData] = useState<ChartData[]>(data);

  useEffect(() => {
    if (symbol) {
      // Fetch real chart data from backend (if available)
      fetchChartData();
    }
  }, [symbol]);

  const fetchChartData = async () => {
    try {
      setLoading(true);
      // Fetch real chart data from backend
      const response = await fetch(`/api/chart/${symbol}?resolution=60&count=100`);
      if (response.ok) {
        const data = await response.json();
        setChartData(data);
      } else {
        setChartData(mockChartData);
      }
    } catch (error) {
      console.error("Failed to fetch chart data:", error);
      setChartData(mockChartData);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (value: number) => {
    return value > 1000 ? value.toFixed(0) : value.toFixed(2);
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div
          className="p-2 text-xs font-mono border"
          style={{
            backgroundColor: "#0a0e27",
            borderColor: "#00ff41",
            color: "#00ff41",
          }}
        >
          <p className="font-bold">{`Time: ${label}`}</p>
          <p>{`Price: ${formatPrice(payload[0].value)}`}</p>
          {showIndicators && payload[0].payload.rsi && (
            <p>{`RSI: ${payload[0].payload.rsi.toFixed(1)}`}</p>
          )}
          {showIndicators && payload[0].payload.macd && (
            <p>{`MACD: ${payload[0].payload.macd.toFixed(2)}`}</p>
          )}
        </div>
      );
    }
    return null;
  };

  if (loading) {
    return (
      <div
        className="border rounded-sm flex items-center justify-center"
        style={{
          backgroundColor: "#0a0e27",
          borderColor: "#00ff41",
          height: `${height}px`,
        }}
      >
        <div className="text-center">
          <div
            className="font-mono text-xs uppercase tracking-widest mb-2"
            style={{ color: "#00ff41" }}
          >
            Loading Chart...
          </div>
          <div style={{ color: "#666" }} className="text-xs">
            {symbol}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="border rounded-sm p-3"
      style={{
        backgroundColor: "#0a0e27",
        borderColor: "#00ff41",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div
          className="font-mono text-xs uppercase tracking-widest font-bold"
          style={{ color: "#00ff41" }}
        >
          {symbol} Price Chart
        </div>
        <div className="flex gap-2 text-xs" style={{ color: "#666" }}>
          <span>1H</span>
          <span>•</span>
          <span>
            Last: {formatPrice(chartData[chartData.length - 1]?.price || 0)}
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient
              id={`gradient-${symbol}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="5%" stopColor="#00ff41" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#00ff41" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" />
          <XAxis
            dataKey="time"
            stroke="#666"
            fontSize={10}
            fontFamily="monospace"
            tickLine={false}
          />
          <YAxis
            stroke="#666"
            fontSize={10}
            fontFamily="monospace"
            tickLine={false}
            tickFormatter={formatPrice}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="price"
            stroke="#00ff41"
            strokeWidth={2}
            fill={`url(#gradient-${symbol})`}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {showIndicators && (
        <div className="mt-3 pt-3 border-t" style={{ borderColor: "#1a1f2e" }}>
          <div
            className="flex justify-between text-xs"
            style={{ color: "#666" }}
          >
            <span>
              RSI: {chartData[chartData.length - 1]?.rsi?.toFixed(1) || "N/A"}
            </span>
            <span>
              MACD: {chartData[chartData.length - 1]?.macd?.toFixed(2) || "N/A"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
