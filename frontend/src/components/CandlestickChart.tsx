import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
} from "react";

interface CandleData {
  time: string;
  timestamp?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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

interface CandlestickChartProps {
  symbol: string;
  data: CandleData[];
  height?: number;
  showVolume?: boolean;
  showRSI?: boolean;
  resolution?: string;
  trades?: Trade[];
  selectedPosition?: any;
}

// ── Client-side indicator calculations ──

function calculateRSI(prices: number[], period: number): (number | null)[] {
  // Returns array aligned with prices (null for warmup period)
  const result: (number | null)[] = [];
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 0; i < prices.length; i++) {
    if (i === 0) {
      result.push(null);
      continue;
    }
    const change = prices[i] - prices[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? Math.abs(change) : 0);
    if (gains.length < period) {
      result.push(null);
      continue;
    }
    if (gains.length === period) {
      const avgGain = gains.reduce((a, b) => a + b, 0) / period;
      const avgLoss = losses.reduce((a, b) => a + b, 0) / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + rs));
    } else {
      // Use Wilder smoothing
      const prevRsi = result[result.length - 1];
      if (prevRsi === null) {
        result.push(null);
        continue;
      }
      // Recalculate with smoothing
      let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
      let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
      for (let j = period; j < gains.length; j++) {
        avgGain = (avgGain * (period - 1) + gains[j]) / period;
        avgLoss = (avgLoss * (period - 1) + losses[j]) / period;
      }
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + rs));
    }
  }
  return result;
}

function calculateSMA(prices: number[], period: number): (number | null)[] {
  return prices.map((_, i) => {
    if (i < period - 1) return null;
    const slice = prices.slice(i - period + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}

function calculateEMA(prices: number[], period: number): number[] {
  if (prices.length < period) return [];
  const multiplier = 2 / (period + 1);
  const ema: number[] = [];
  let val = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = 0; i < period - 1; i++) ema.push(NaN);
  ema.push(val);
  for (let i = period; i < prices.length; i++) {
    val = (prices[i] - val) * multiplier + val;
    ema.push(val);
  }
  return ema;
}

function calculateBollingerBands(
  prices: number[],
  period: number = 20,
  stdDevMult: number = 2,
) {
  const upper: (number | null)[] = [];
  const middle: (number | null)[] = [];
  const lower: (number | null)[] = [];

  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      upper.push(null);
      middle.push(null);
      lower.push(null);
      continue;
    }
    const slice = prices.slice(i - period + 1, i + 1);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance =
      slice.reduce((sum, p) => sum + (p - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    upper.push(mean + stdDevMult * std);
    middle.push(mean);
    lower.push(mean - stdDevMult * std);
  }
  return { upper, middle, lower };
}

function calculateMACD(prices: number[], fast = 12, slow = 26, signal = 9) {
  const emaFast = calculateEMA(prices, fast);
  const emaSlow = calculateEMA(prices, slow);

  const macdLine: (number | null)[] = [];
  for (let i = 0; i < prices.length; i++) {
    if (isNaN(emaFast[i]) || isNaN(emaSlow[i])) {
      macdLine.push(null);
    } else {
      macdLine.push(emaFast[i] - emaSlow[i]);
    }
  }

  const validMacd = macdLine.filter((v): v is number => v !== null);
  const signalEma = calculateEMA(validMacd, signal);

  const signalLine: (number | null)[] = [];
  const histogram: (number | null)[] = [];
  let validIdx = 0;
  for (let i = 0; i < prices.length; i++) {
    if (macdLine[i] === null) {
      signalLine.push(null);
      histogram.push(null);
    } else {
      const sig = isNaN(signalEma[validIdx]) ? null : signalEma[validIdx];
      signalLine.push(sig);
      histogram.push(sig !== null ? macdLine[i]! - sig : null);
      validIdx++;
    }
  }

  return { macdLine, signalLine, histogram };
}

// Trading sessions (UTC hours)
const TRADING_SESSIONS = [
  { name: "Tokyo", start: 0, end: 9, color: "#f97316", abbr: "TKY" },
  { name: "London", start: 7, end: 16, color: "var(--accent)", abbr: "LDN" },
  { name: "NY", start: 13, end: 22, color: "var(--success)", abbr: "NY" },
];

function getSessionForHour(hour: number) {
  return TRADING_SESSIONS.filter((s) => {
    if (s.start < s.end) return hour >= s.start && hour < s.end;
    return hour >= s.start || hour < s.end;
  });
}

/** Convert UTC timestamp to Warsaw time string (HH:MM) */
function toWarsawTime(timestamp: string | undefined): string {
  if (!timestamp) return "";
  const tsUtc = timestamp.endsWith("Z") ? timestamp : timestamp + "Z";
  const dt = new Date(tsUtc);
  if (isNaN(dt.getTime())) return "";
  // Convert to Warsaw timezone
  const warsaw = new Date(dt.toLocaleString("en-US", { timeZone: "Europe/Warsaw" }));
  return `${warsaw.getHours().toString().padStart(2, "0")}:${warsaw.getMinutes().toString().padStart(2, "0")}`;
}

/** Parse an ISO timestamp or HH:MM time string into { hour, date } */
function parseTimestamp(
  candle: CandleData,
): { hour: number; dateStr: string } | null {
  // Ensure UTC parsing - add Z if not present
  const ts = candle.timestamp || "";
  const tsUtc = ts.endsWith("Z") ? ts : ts + "Z";
  
  // Prefer ISO timestamp
  if (tsUtc) {
    try {
      const dt = new Date(tsUtc);
      if (!isNaN(dt.getTime())) {
        return {
          hour: dt.getUTCHours(),
          dateStr: ts.split("T")[0] || "",
        };
      }
    } catch {
      /* fall through */
    }
  }
  // Fallback: parse HH:MM from time field
  const m = candle.time.match(/^(\d{1,2}):(\d{2})/);
  if (m) return { hour: parseInt(m[1], 10), dateStr: "" };
  return null;
}

export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  symbol,
  data,
  height = 220,
  showVolume = true,
  showRSI = true,
  resolution = "60",
  trades = [],
  selectedPosition = null,
}) => {
  const [hoveredCandle, setHoveredCandle] = useState<number | null>(null);
  const [hoveredTrade, setHoveredTrade] = useState<Trade | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({
    x: 0,
    y: 0,
  });
  const [overlays, setOverlays] = useState({
    bb: true,
    sma: true,
    macd: true,
    sessions: true,
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState(0);

  // Handle wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      setZoomLevel((prev) => Math.max(0.5, Math.min(3, prev + delta)));
    }
  };

  // Handle drag/pan - will be defined after zoom calculations

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setContainerWidth(entry.contentRect.width);
    });
    ro.observe(el);
    setContainerWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const toggleOverlay = (key: keyof typeof overlays) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const isDaily = resolution === "D";

  // Validate data - keep all for indicators
  const allValidData = useMemo(() => {
    if (!data) return [];
    return data.filter(
      (d) =>
        d &&
        typeof d.open === "number" &&
        typeof d.high === "number" &&
        typeof d.low === "number" &&
        typeof d.close === "number" &&
        typeof d.volume === "number" &&
        isFinite(d.open) &&
        isFinite(d.close) &&
        d.high >= d.low,
    );
  }, [data]);

  // Find where BB starts (warmup period is 20)
  const bbWarmup = useMemo(() => {
    if (allValidData.length === 0) return 0;
    const closes = allValidData.map((d) => d.close);
    const bb = calculateBollingerBands(closes, 20, 2);
    return bb.middle.findIndex((v: number | null) => v !== null);
  }, [allValidData]);

  // Display data starts where BB is valid
  const validData = useMemo(() => {
    if (bbWarmup <= 0) return allValidData;
    return allValidData.slice(bbWarmup);
  }, [allValidData, bbWarmup]);

  // Compute all indicators on FULL data (including warmup for accurate BB)
  const indicators = useMemo(() => {
    if (allValidData.length === 0) return null;
    const closes = allValidData.map((d) => d.close);
    return {
      rsi: calculateRSI(closes, 14),
      sma20: calculateSMA(closes, 20),
      sma50: calculateSMA(closes, 50),
      bb: calculateBollingerBands(closes, 20, 2),
      macd: calculateMACD(closes),
    };
  }, [allValidData]);

  // Get BB values aligned with displayed candles (slice to match validData)
  const displayBB = useMemo(() => {
    if (!indicators?.bb || bbWarmup <= 0) return indicators?.bb;
    return {
      upper: indicators.bb.upper.slice(bbWarmup),
      middle: indicators.bb.middle.slice(bbWarmup),
      lower: indicators.bb.lower.slice(bbWarmup),
    };
  }, [indicators, bbWarmup]);

  // Compute session bands using timestamps (with date-awareness)
  const sessionBands = useMemo(() => {
    if (!overlays.sessions || validData.length === 0 || isDaily) return [];

    const parsed = validData.map((d) => parseTimestamp(d));
    // If no valid timestamps, skip sessions
    if (parsed.every((p) => p === null)) return [];

    type Band = {
      session: (typeof TRADING_SESSIONS)[0];
      startIdx: number;
      endIdx: number;
    };
    const bands: Band[] = [];

    for (const session of TRADING_SESSIONS) {
      let inSession = false;
      let startIdx = 0;
      let prevDate = "";
      for (let i = 0; i < parsed.length; i++) {
        const p = parsed[i];
        if (!p) {
          if (inSession) {
            bands.push({ session, startIdx, endIdx: i - 1 });
            inSession = false;
          }
          continue;
        }
        const active = getSessionForHour(p.hour).some(
          (s) => s.name === session.name,
        );
        // Break session when date changes (new day = new session band)
        const dateChanged = p.dateStr && prevDate && p.dateStr !== prevDate;
        if (dateChanged && inSession) {
          bands.push({ session, startIdx, endIdx: i - 1 });
          inSession = false;
        }
        if (active && !inSession) {
          startIdx = i;
          inSession = true;
        } else if (!active && inSession) {
          bands.push({ session, startIdx, endIdx: i - 1 });
          inSession = false;
        }
        prevDate = p.dateStr;
      }
      if (inSession)
        bands.push({ session, startIdx, endIdx: parsed.length - 1 });
    }
    return bands;
  }, [validData, overlays.sessions, isDaily]);

  if (!data || data.length === 0 || validData.length === 0) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ color: "#4a5568" }}
      >
        <div className="text-xs uppercase tracking-widest">No chart data</div>
      </div>
    );
  }

  if (!indicators) return null;

  const n = validData.length;
  const volumes = validData.map((d) => d.volume);

  // Include BB bands in price range
  let maxPrice = Math.max(...validData.map((d) => d.high));
  let minPrice = Math.min(...validData.map((d) => d.low));
  
  // Extend range to include trade entry/exit prices (BUG 5 fix)
  if (trades.length > 0) {
    const symbolTrades = trades.filter(t => t.symbol === symbol);
    for (const t of symbolTrades) {
      if (t.entry_price < minPrice) minPrice = t.entry_price;
      if (t.entry_price > maxPrice) maxPrice = t.entry_price;
      if (t.exit_price) {
        if (t.exit_price < minPrice) minPrice = t.exit_price;
        if (t.exit_price > maxPrice) maxPrice = t.exit_price;
      }
    }
  }
  
  // Also extend for selectedPosition (TP/SL lines)
  if (selectedPosition) {
    if (selectedPosition.take_profit > maxPrice) maxPrice = selectedPosition.take_profit;
    if (selectedPosition.stop_loss < minPrice) minPrice = selectedPosition.stop_loss;
    if (selectedPosition.entry_price < minPrice) minPrice = selectedPosition.entry_price;
    if (selectedPosition.entry_price > maxPrice) maxPrice = selectedPosition.entry_price;
  }
  
  if (overlays.bb) {
    for (const v of (displayBB?.upper || [])) {
      if (v !== null && v > maxPrice) maxPrice = v;
    }
    for (const v of (displayBB?.lower || [])) {
      if (v !== null && v < minPrice) minPrice = v;
    }
  }

  const maxVolume = Math.max(...volumes);
  const priceRange = maxPrice - minPrice || 1;

  // Layout - improved for better visibility
  const isMobile = containerWidth > 0 && containerWidth < 600;
  const showMACD = overlays.macd;
  const chartWidth = containerWidth > 0 ? Math.max(800, containerWidth) : 1100;
  const macdH = showMACD ? 50 : 0;
  const volumeH = showVolume ? 45 : 0;
  const rsiH = showRSI ? 50 : 0;
  const gapH = 8;
  const xAxisH = 25; // Height reserved for X-axis labels
  const priceChartH = Math.max(
    150,
    height -
      (showVolume ? volumeH + gapH : 0) -
      (showMACD ? macdH + gapH : 0) -
      (showRSI ? rsiH + gapH : 0) -
      xAxisH -
      10,
  );
  const totalH =
    priceChartH +
    (showVolume ? volumeH + gapH : 0) +
    (showMACD ? macdH + gapH : 0) +
    (showRSI ? rsiH + gapH : 0) +
    xAxisH;
  const rightPad = isMobile ? 50 : 60;
  const usableWidth = chartWidth - rightPad;

  const currentPrice = validData[n - 1].close;
  const prevClose = n > 1 ? validData[n - 2].close : currentPrice;
  const priceChange = currentPrice - prevClose;
  const priceChangeStr = `${priceChange >= 0 ? "+" : ""}${priceChange.toFixed(2)}`;

  const priceToY = (p: number) =>
    priceChartH - ((p - minPrice) / priceRange) * priceChartH;

  // Apply zoom to chart width - anchor to right side (newest candles)
  const zoomedWidth = usableWidth * zoomLevel;
  const maxPan = Math.max(0, zoomedWidth - usableWidth);

  // Default pan shows the rightmost (newest) candles
  const effectivePan = Math.min(Math.max(0, panOffset), maxPan);

  // Index to x coordinate with zoom - anchor to right
  const idxToX = (i: number) => {
    if (n <= 1) return usableWidth / 2;
    // Anchor to right: (n-1) maps to usableWidth
    const x =
      usableWidth - ((n - 1 - i) / (n - 1)) * zoomedWidth + effectivePan;
    return x;
  };

  // Reverse mapping: x coordinate to candle index
  const xToIdx = (x: number) => {
    if (n <= 1) return 0;
    const relativeX = usableWidth - x + effectivePan;
    const idx = Math.round((relativeX / zoomedWidth) * (n - 1));
    return Math.max(0, Math.min(n - 1, idx));
  };

  // Drag/pan handlers (defined after zoom calculations)
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartPan, setDragStartPan] = useState(0);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoomLevel > 1) {
      setIsDragging(true);
      setDragStartX(e.clientX);
      setDragStartPan(panOffset);
    }
  };

  const handleDragMove = (e: React.MouseEvent) => {
    if (isDragging && zoomLevel > 1) {
      // Reverse delta because zoom is anchored to right
      const delta = e.clientX - dragStartX;
      const newPan = Math.min(Math.max(0, dragStartPan + delta), maxPan);
      setPanOffset(newPan);
    }
  };

  const handleDragEnd = () => {
    setIsDragging(false);
  };

  // TP/SL line dragging
  const [draggingLine, setDraggingLine] = useState<"tp" | "sl" | null>(null);
  const [dragLineStartY, setDragLineStartY] = useState(0);
  const [dragLineStartValue, setDragLineStartValue] = useState(0);

  const handleLineDragStart = (line: "tp" | "sl", e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDraggingLine(line);
    setDragLineStartY(e.clientY);
    const currentValue = line === "tp" 
      ? selectedPosition?.take_profit 
      : selectedPosition?.stop_loss;
    setDragLineStartValue(currentValue || 0);
  };

  const handleLineDragMove = useCallback((e: MouseEvent) => {
    if (!draggingLine || !selectedPosition) return;
    
    const deltaY = dragLineStartY - e.clientY; // Invert: drag up = increase
    const sensitivity = priceRange / priceChartH; // pixels to price
    const deltaPrice = deltaY * sensitivity;
    
    const newValue = dragLineStartValue + deltaPrice;
    // Round to reasonable precision
    const roundedValue = Math.round(newValue * 100) / 100;
    
    // Dispatch event for parent to handle
    window.dispatchEvent(new CustomEvent("adjustPositionLine", {
      detail: {
        positionId: selectedPosition.id,
        type: draggingLine,
        value: roundedValue
      }
    }));
  }, [draggingLine, selectedPosition, dragLineStartY, dragLineStartValue, priceRange, priceChartH]);

  const handleLineDragEnd = useCallback(() => {
    setDraggingLine(null);
  }, []);

  // Add/remove global event listeners for line dragging
  useEffect(() => {
    if (draggingLine) {
      window.addEventListener("mousemove", handleLineDragMove);
      window.addEventListener("mouseup", handleLineDragEnd);
      return () => {
        window.removeEventListener("mousemove", handleLineDragMove);
        window.removeEventListener("mouseup", handleLineDragEnd);
      };
    }
  }, [draggingLine, handleLineDragMove, handleLineDragEnd]);

  // Price grid levels
  const priceLevels = [];
  const levelCount = 6;
  for (let i = 0; i <= levelCount; i++) {
    const price = minPrice + (priceRange * i) / levelCount;
    priceLevels.push({ price, y: priceToY(price) });
  }

  // Time labels — improved for readability and no overlap
  const timeLabels: { time: string; x: number; isMajor?: boolean }[] = [];
  const maxLabels = isMobile ? 4 : 8;
  const step = Math.max(1, Math.floor(n / maxLabels));
  let prevLabelDate = "";
  for (let i = 0; i < n; i += step) {
    // Convert UTC time to Warsaw for display
    let label = toWarsawTime(validData[i].timestamp) || validData[i].time;
    let isMajor = false;
    // For daily charts prefer MM/DD, for intraday prefer HH:MM with date at day boundaries
    if (validData[i].timestamp) {
      try {
        const ts = validData[i].timestamp!;
        const tsUtc = ts.endsWith("Z") ? ts : ts + "Z";
        const dt = new Date(tsUtc);
        const warsawDt = new Date(dt.toLocaleString("en-US", { timeZone: "Europe/Warsaw" }));
        const currentDate = validData[i].timestamp!.split("T")[0];
        if (!isNaN(dt.getTime())) {
          if (isDaily) {
            label = `${(warsawDt.getMonth() + 1).toString().padStart(2, "0")}/${warsawDt.getDate().toString().padStart(2, "0")}`;
            isMajor = true;
          } else {
            const timeStr = `${warsawDt.getHours().toString().padStart(2, "0")}:${warsawDt.getMinutes().toString().padStart(2, "0")}`;
            // Show full date+time at day boundaries or every 6 hours
            const isDayBoundary = currentDate !== prevLabelDate;
            const isMajorHour = warsawDt.getHours() % 6 === 0;
            if (isDayBoundary || isMajorHour) {
              label = `${warsawDt.getDate()}/${warsawDt.getMonth() + 1} ${timeStr}`;
              isMajor = true;
            } else {
              label = timeStr;
            }
          }
          prevLabelDate = currentDate;
        }
      } catch {
        /* use fallback */
      }
    }
    timeLabels.push({ time: label, x: idxToX(i), isMajor });
  }

  // Candlesticks
  const candleSpacing = usableWidth / n;
  const candleWidth = Math.max(2, candleSpacing * 0.7);

  const candlesticks = validData.map((candle, index) => {
    const x = idxToX(index);
    const openY = priceToY(candle.open);
    const closeY = priceToY(candle.close);
    const highY = priceToY(candle.high);
    const lowY = priceToY(candle.low);
    const isBullish = candle.close >= candle.open;
    const rsiVal = indicators.rsi[index];

    return {
      index,
      x,
      openY,
      closeY,
      highY,
      lowY,
      isBullish,
      bodyY: Math.min(openY, closeY),
      bodyH: Math.max(1, Math.abs(closeY - openY)),
      color: isBullish ? "var(--success)" : "var(--danger)",
      volume: candle.volume,
      data: candle,
      rsi: rsiVal,
    };
  });

  // Build polyline string for indicator overlay (aligned to candle indices)
  const toPolyline = (
    values: (number | null)[],
    mapY: (v: number) => number,
  ): string => {
    const pts: string[] = [];
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (v === null || isNaN(v)) continue;
      pts.push(`${idxToX(i)},${mapY(v)}`);
    }
    return pts.join(" ");
  };

  // Section Y offsets
  let nextY = priceChartH;
  const volumeTop = nextY + gapH;
  nextY = showVolume ? volumeTop + volumeH : nextY;
  const macdTop = nextY + gapH;
  nextY = showMACD ? macdTop + macdH : nextY;
  const rsiTop = nextY + gapH;

  // MACD scaling
  const macdVals = indicators.macd.histogram.filter(
    (v): v is number => v !== null,
  );
  const macdLineVals = indicators.macd.macdLine.filter(
    (v): v is number => v !== null,
  );
  const macdSignalVals = indicators.macd.signalLine.filter(
    (v): v is number => v !== null,
  );
  const allMacdVals = [...macdVals, ...macdLineVals, ...macdSignalVals];
  const macdMax =
    allMacdVals.length > 0 ? Math.max(...allMacdVals.map(Math.abs)) : 1;
  const macdToY = (v: number) =>
    macdTop + macdH / 2 - (v / (macdMax || 1)) * (macdH / 2 - 2);

  const handleMouseMove = (event: React.MouseEvent<SVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    let idx: number;
    if (zoomLevel === 1) {
      // Standard mapping without zoom
      idx = Math.round((x / usableWidth) * (n - 1));
    } else {
      // Use xToIdx with zoom
      idx = xToIdx(x);
    }
    if (idx >= 0 && idx < n) setHoveredCandle(idx);
  };

  const handleTouchMove = useCallback(
    (event: React.TouchEvent<SVGElement>) => {
      if (event.touches.length !== 1) return;
      const touch = event.touches[0];
      const rect = event.currentTarget.getBoundingClientRect();
      const x = touch.clientX - rect.left;
      let idx: number;
      if (zoomLevel === 1) {
        idx = Math.round((x / usableWidth) * (n - 1));
      } else {
        idx = xToIdx(x);
      }
      if (idx >= 0 && idx < n) setHoveredCandle(idx);
    },
    [usableWidth, n, zoomLevel, panOffset],
  );

  const hoveredMacd =
    hoveredCandle !== null
      ? {
          macd: indicators.macd.macdLine[hoveredCandle],
          signal: indicators.macd.signalLine[hoveredCandle],
          hist: indicators.macd.histogram[hoveredCandle],
        }
      : null;

  // RSI polyline aligned to candle x-axis
  const rsiPolyline = useMemo(() => {
    const pts: string[] = [];
    for (let i = 0; i < indicators.rsi.length; i++) {
      const v = indicators.rsi[i];
      if (v === null) continue;
      const x = idxToX(i);
      const y = rsiTop + rsiH - (v / 100) * rsiH;
      pts.push(`${x},${y}`);
    }
    return pts.join(" ");
  }, [indicators.rsi, rsiTop, rsiH, usableWidth, n]);

  return (
    <div className="h-full relative" ref={containerRef}>
      {/* Header */}
      <div className="flex flex-wrap items-center gap-1 sm:gap-3 mb-1 px-1">
        <span
          className="text-xs sm:text-sm font-bold"
          style={{ color: "var(--text-primary)" }}
        >
          {symbol}
        </span>
        <span
          className="text-xs sm:text-sm font-bold"
          style={{ color: priceChange >= 0 ? "var(--success)" : "var(--danger)" }}
        >
          {currentPrice.toFixed(2)}
        </span>
        <span
          className="text-[9px] sm:text-[10px]"
          style={{ color: priceChange >= 0 ? "var(--success)" : "var(--danger)" }}
        >
          {priceChangeStr}
        </span>

        {/* Overlay toggles */}
        <div className="flex items-center gap-1 ml-1 sm:ml-2">
          {(["bb", "sma", "macd", "sessions"] as const).map((key) => {
            const colors: Record<string, string> = {
              bb: "#a78bfa",
              sma: "#38bdf8",
              macd: "#fb923c",
              sessions: "#94a3b8",
            };
            const labels: Record<string, string> = {
              bb: "BB",
              sma: "SMA",
              macd: "MACD",
              sessions: "SESS",
            };
            const tooltips: Record<string, { title: string; desc: string }> = {
              bb: {
                title: "Bollinger Bands",
                desc: "Price envelope (20 SMA ± 2 std dev). Lower band = potential buy, upper band = potential sell. Width shows volatility.",
              },
              sma: {
                title: "SMA (20/50)",
                desc: "Simple Moving Averages. SMA20 above SMA50 = bullish (buy). SMA20 below SMA50 = bearish (sell).",
              },
              macd: {
                title: "MACD",
                desc: "EMA 12-26 difference. Line above 0 = bullish. Cross above 0 = buy, cross below 0 = sell.",
              },
              sessions: {
                title: "Trading Sessions",
                desc: "Shows market sessions: Sydney (22:00-07:00), Tokyo (00:00-09:00), London (08:00-17:00), New York (13:00-22:00) Warsaw time.",
              },
            };
            const c = colors[key];
            const tip = tooltips[key];
            return (
              <div key={key} className="relative group">
                <button
                  onClick={() => toggleOverlay(key)}
                  className="px-1 sm:px-1.5 py-0.5 text-[8px] sm:text-[9px] font-medium rounded-sm transition-all"
                  style={{
                    color: overlays[key] ? c : "var(--chart-text)",
                    backgroundColor: overlays[key] ? "var(--bg-tertiary)" : "transparent",
                    border: `1px solid ${overlays[key] ? c + "33" : "var(--bg-tertiary)"}`,
                  }}
                >
                  {labels[key]}
                </button>
                {/* Tooltip */}
                <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 px-2 py-1.5 rounded text-[9px] w-40 z-50 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                  style={{ backgroundColor: "var(--grid-line)", border: "1px solid #334155" }}
                >
                  <div className="font-bold" style={{ color: c }}>{tip.title}</div>
                  <div style={{ color: "#94a3b8", lineHeight: "1.3" }}>{tip.desc}</div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1 ml-2">
          <button
            onClick={() => setZoomLevel((prev) => Math.max(0.5, prev - 0.2))}
            className="px-2 py-0.5 text-[9px] font-bold rounded-sm"
            style={{
              backgroundColor: "var(--bg-tertiary)",
              color: "var(--text-muted)",
              border: "1px solid #2d3748",
            }}
            title="Zoom Out"
          >
            −
          </button>
          <span className="text-[9px] px-1" style={{ color: "var(--text-muted)" }}>
            {Math.round(zoomLevel * 100)}%
          </span>
          <button
            onClick={() => setZoomLevel((prev) => Math.min(3, prev + 0.2))}
            className="px-2 py-0.5 text-[9px] font-bold rounded-sm"
            style={{
              backgroundColor: "var(--bg-tertiary)",
              color: "var(--text-muted)",
              border: "1px solid #2d3748",
            }}
            title="Zoom In"
          >
            +
          </button>
          <button
            onClick={() => {
              setZoomLevel(1);
              setPanOffset(0);
            }}
            className="px-2 py-0.5 text-[9px] font-bold rounded-sm ml-1"
            style={{
              backgroundColor: "var(--bg-tertiary)",
              color: "var(--text-muted)",
              border: "1px solid #2d3748",
            }}
            title="Reset Zoom"
          >
            ⟲
          </button>
        </div>

        {/* Hover info */}
        {hoveredCandle !== null && candlesticks[hoveredCandle] && (
          <div
            className="flex flex-wrap items-center gap-1 sm:gap-2 ml-auto text-[9px] sm:text-[10px]"
            style={{ color: "var(--text-muted)" }}
          >
            {(() => {
              const candle = candlesticks[hoveredCandle].data;
              let dateStr = "";
              if (candle.timestamp) {
                try {
                  const ts = candle.timestamp;
                  const tsUtc = ts.endsWith("Z") ? ts : ts + "Z";
                  const dt = new Date(tsUtc);
                  if (!isNaN(dt.getTime())) {
                    // Convert to Warsaw timezone for display
                    const warsawTime = new Date(dt.toLocaleString("en-US", { timeZone: "Europe/Warsaw" }));
                    const day = warsawTime.getDate().toString().padStart(2, "0");
                    const month = (warsawTime.getMonth() + 1).toString().padStart(2, "0");
                    const hours = warsawTime.getHours().toString().padStart(2, "0");
                    const minutes = warsawTime.getMinutes().toString().padStart(2, "0");
                    dateStr = `${day}/${month} ${hours}:${minutes}`;
                  }
                } catch {}
              }
              if (!dateStr && candle.time) {
                // Convert UTC time to Warsaw for display
                dateStr = toWarsawTime(candle.timestamp) || candle.time;
              }
              return (
                <span style={{ color: "#94a3b8", fontWeight: "bold" }}>
                  {dateStr}
                </span>
              );
            })()}
            <span>O:{candlesticks[hoveredCandle].data.open.toFixed(2)}</span>
            <span>H:{candlesticks[hoveredCandle].data.high.toFixed(2)}</span>
            <span>L:{candlesticks[hoveredCandle].data.low.toFixed(2)}</span>
            <span>C:{candlesticks[hoveredCandle].data.close.toFixed(2)}</span>
            <span className="hidden sm:inline">
              V:{(candlesticks[hoveredCandle].data.volume / 1000).toFixed(0)}K
            </span>
            {candlesticks[hoveredCandle].rsi != null && (
              <span className="hidden sm:inline">
                RSI:{candlesticks[hoveredCandle].rsi!.toFixed(1)}
              </span>
            )}
            {overlays.macd && hoveredMacd?.macd != null && (
              <span className="hidden sm:inline" style={{ color: "#fb923c" }}>
                MACD:{hoveredMacd.macd.toFixed(2)}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Scrollable chart */}
      <div
        className="overflow-x-auto"
        style={{ WebkitOverflowScrolling: "touch" }}
      >
        <svg
          width={
            isMobile
              ? chartWidth
              : containerWidth > 0
                ? containerWidth
                : chartWidth
          }
          height={height}
          viewBox={`0 0 ${chartWidth} ${totalH}`}
          preserveAspectRatio="xMidYMid meet"
          onMouseMove={(e) => {
            handleMouseMove(e);
            handleDragMove(e);
          }}
          onMouseLeave={() => {
            setHoveredCandle(null);
            handleDragEnd();
          }}
          onMouseDown={handleMouseDown}
          onMouseUp={handleDragEnd}
          onTouchMove={handleTouchMove}
          onTouchEnd={() => setHoveredCandle(null)}
          style={{
            cursor:
              zoomLevel > 1 ? (isDragging ? "grabbing" : "grab") : "crosshair",
            minWidth: `${chartWidth}px`,
          }}
        >
          {/* ── Session Background Bands ── */}
          {overlays.sessions && sessionBands.length > 0 && (
            <g>
              {sessionBands.map((band, i) => {
                const x1 = idxToX(band.startIdx);
                const x2 = idxToX(band.endIdx);
                const w = Math.max(x2 - x1, 2);
                return (
                  <g key={`sess-${i}`}>
                    <rect
                      x={x1}
                      y={0}
                      width={w}
                      height={priceChartH}
                      fill={band.session.color}
                      fillOpacity="0.04"
                    />
                    <line
                      x1={x1}
                      y1={0}
                      x2={x1}
                      y2={priceChartH}
                      stroke={band.session.color}
                      strokeWidth="0.5"
                      strokeDasharray="3,3"
                      opacity="0.3"
                    />
                    <text
                      x={x1 + 3}
                      y={10}
                      fill={band.session.color}
                      fontSize="7"
                      fontFamily="monospace"
                      opacity="0.5"
                    >
                      {band.session.abbr}
                    </text>
                  </g>
                );
              })}
            </g>
          )}

          {/* ── Price Chart Grid ── */}
          <g stroke="var(--grid-line)" strokeWidth="1">
            {priceLevels.map((l, i) => (
              <line key={`g-${i}`} x1={0} y1={l.y} x2={usableWidth} y2={l.y} />
            ))}
          </g>

          {/* Price labels */}
          <g fill="var(--chart-text)" fontSize="10" fontFamily="monospace">
            {priceLevels.map((l, i) => (
              <text
                key={`p-${i}`}
                x={usableWidth + 5}
                y={l.y + 3}
                textAnchor="start"
              >
                {l.price.toFixed(l.price > 100 ? 0 : 2)}
              </text>
            ))}
          </g>

          {/* ── Bollinger Bands ── */}
          {overlays.bb && (
            <g>
              <path
                d={(() => {
                  const upperPts: string[] = [];
                  const lowerPts: string[] = [];
                  for (let i = 0; i < n; i++) {
                    const u = (displayBB?.upper || [])[i];
                    const l = (displayBB?.lower || [])[i];
                    if (u === null || l === null) continue;
                    const x = idxToX(i);
                    upperPts.push(`${x},${priceToY(u)}`);
                    lowerPts.unshift(`${x},${priceToY(l)}`);
                  }
                  if (upperPts.length === 0) return "";
                  return `M${upperPts.join(" L")} L${lowerPts.join(" L")}Z`;
                })()}
                fill="#a78bfa"
                fillOpacity="0.06"
              />
              <polyline
                points={toPolyline((displayBB?.upper || []), priceToY)}
                fill="none"
                stroke="#a78bfa"
                strokeWidth="0.8"
                strokeDasharray="3,2"
                opacity="0.6"
              />
              <polyline
                points={toPolyline((displayBB?.middle || []), priceToY)}
                fill="none"
                stroke="#a78bfa"
                strokeWidth="0.6"
                opacity="0.4"
              />
              <polyline
                points={toPolyline((displayBB?.lower || []), priceToY)}
                fill="none"
                stroke="#a78bfa"
                strokeWidth="0.8"
                strokeDasharray="3,2"
                opacity="0.6"
              />
            </g>
          )}

          {/* ── SMA Lines ── */}
          {overlays.sma && (
            <g>
              <polyline
                points={toPolyline(indicators.sma20, priceToY)}
                fill="none"
                stroke="#38bdf8"
                strokeWidth="1"
                opacity="0.7"
              />
              <polyline
                points={toPolyline(indicators.sma50, priceToY)}
                fill="none"
                stroke="#f472b6"
                strokeWidth="1"
                opacity="0.7"
              />
              <text
                x={usableWidth + 5}
                y={12}
                fill="#38bdf8"
                fontSize="8"
                fontFamily="monospace"
                opacity="0.7"
              >
                SMA20
              </text>
              <text
                x={usableWidth + 5}
                y={22}
                fill="#f472b6"
                fontSize="8"
                fontFamily="monospace"
                opacity="0.7"
              >
                SMA50
              </text>
            </g>
          )}

          {/* Current Price Line */}
          <line
            x1={0}
            y1={priceToY(currentPrice)}
            x2={usableWidth}
            y2={priceToY(currentPrice)}
            stroke={priceChange >= 0 ? "var(--success)" : "var(--danger)"}
            strokeWidth="0.5"
            strokeDasharray="3,3"
            opacity="0.6"
          />
          <text
            x={usableWidth + 5}
            y={priceToY(currentPrice) + 3}
            fill={priceChange >= 0 ? "var(--success)" : "var(--danger)"}
            fontSize="10"
            fontFamily="monospace"
            fontWeight="bold"
          >
            {currentPrice.toFixed(2)}
          </text>

          {/* ── Candlesticks ── */}
          <g>
            {candlesticks.map((c) => (
              <g key={`c-${c.index}`}>
                <line
                  x1={c.x}
                  y1={c.highY}
                  x2={c.x}
                  y2={c.lowY}
                  stroke={c.color}
                  strokeWidth={hoveredCandle === c.index ? "1" : "0.5"}
                  opacity={
                    hoveredCandle === null || hoveredCandle === c.index
                      ? "1"
                      : "0.5"
                  }
                />
                <rect
                  x={c.x - candleWidth / 2}
                  y={c.bodyY}
                  width={candleWidth}
                  height={Math.max(1, c.bodyH)}
                  fill={c.color}
                  stroke={c.color}
                  strokeWidth="0.3"
                  opacity={
                    hoveredCandle === null || hoveredCandle === c.index
                      ? "1"
                      : "0.5"
                  }
                />
              </g>
            ))}
          </g>

          {/* Hover crosshair */}
          {hoveredCandle !== null && candlesticks[hoveredCandle] && (
            <line
              x1={candlesticks[hoveredCandle].x}
              y1={0}
              x2={candlesticks[hoveredCandle].x}
              y2={totalH - 20}
              stroke="var(--chart-text)"
              strokeWidth="0.5"
              strokeDasharray="2,2"
            />
          )}

          {/* ── Volume ── */}
          {showVolume && (
            <g>
              <text
                x={5}
                y={volumeTop + 10}
                fill="var(--chart-text)"
                fontSize="9"
                fontFamily="monospace"
              >
                VOL
              </text>
              {candlesticks.map((c) => {
                const barH =
                  maxVolume > 0 ? (c.volume / maxVolume) * volumeH : 0;
                return (
                  <rect
                    key={`v-${c.index}`}
                    x={c.x - candleWidth / 2}
                    y={volumeTop + volumeH - barH}
                    width={candleWidth}
                    height={barH}
                    fill={c.color}
                    fillOpacity={hoveredCandle === c.index ? "0.7" : "0.3"}
                  />
                );
              })}
            </g>
          )}

          {/* ── MACD Panel ── */}
          {showMACD && macdVals.length > 0 && (
            <g>
              <rect
                x={0}
                y={macdTop}
                width={usableWidth}
                height={macdH}
                fill="var(--bg-secondary)"
                fillOpacity="0.5"
              />
              <line
                x1={0}
                y1={macdTop + macdH / 2}
                x2={usableWidth}
                y2={macdTop + macdH / 2}
                stroke="var(--bg-tertiary)"
                strokeWidth="0.5"
              />
              {validData.map((_, i) => {
                const h = indicators.macd.histogram[i];
                if (h === null) return null;
                const x = idxToX(i);
                const barH = Math.abs(h / (macdMax || 1)) * (macdH / 2 - 2);
                const barColor = h >= 0 ? "var(--success)" : "var(--danger)";
                return (
                  <rect
                    key={`mh-${i}`}
                    x={x - candleWidth / 2}
                    y={h >= 0 ? macdToY(h) : macdTop + macdH / 2}
                    width={candleWidth}
                    height={Math.max(0.5, barH)}
                    fill={barColor}
                    fillOpacity="0.5"
                  />
                );
              })}
              <polyline
                points={toPolyline(indicators.macd.macdLine, macdToY)}
                fill="none"
                stroke="#38bdf8"
                strokeWidth="1"
              />
              <polyline
                points={toPolyline(indicators.macd.signalLine, macdToY)}
                fill="none"
                stroke="#fb923c"
                strokeWidth="1"
                strokeDasharray="2,1"
              />
              <text
                x={5}
                y={macdTop + 10}
                fill="var(--chart-text)"
                fontSize="9"
                fontFamily="monospace"
              >
                MACD
              </text>
              <text
                x={usableWidth + 5}
                y={macdTop + 10}
                fill="#38bdf8"
                fontSize="7"
                fontFamily="monospace"
              >
                MACD
              </text>
              <text
                x={usableWidth + 5}
                y={macdTop + 19}
                fill="#fb923c"
                fontSize="7"
                fontFamily="monospace"
              >
                Signal
              </text>
            </g>
          )}

          {/* ── RSI Panel ── */}
          {showRSI && indicators.rsi.some((v) => v !== null) && (
            <g>
              <rect
                x={0}
                y={rsiTop}
                width={usableWidth}
                height={rsiH}
                fill="var(--bg-secondary)"
                fillOpacity="0.5"
              />
              <rect
                x={0}
                y={rsiTop}
                width={usableWidth}
                height={rsiH * 0.3}
                fill="var(--danger)"
                fillOpacity="0.05"
              />
              <rect
                x={0}
                y={rsiTop + rsiH * 0.7}
                width={usableWidth}
                height={rsiH * 0.3}
                fill="var(--success)"
                fillOpacity="0.05"
              />
              <line
                x1={0}
                y1={rsiTop + rsiH * 0.3}
                x2={usableWidth}
                y2={rsiTop + rsiH * 0.3}
                stroke="var(--bg-tertiary)"
                strokeWidth="0.5"
                strokeDasharray="2,2"
              />
              <line
                x1={0}
                y1={rsiTop + rsiH * 0.5}
                x2={usableWidth}
                y2={rsiTop + rsiH * 0.5}
                stroke="var(--bg-tertiary)"
                strokeWidth="0.5"
                strokeDasharray="4,4"
              />
              <line
                x1={0}
                y1={rsiTop + rsiH * 0.7}
                x2={usableWidth}
                y2={rsiTop + rsiH * 0.7}
                stroke="var(--bg-tertiary)"
                strokeWidth="0.5"
                strokeDasharray="2,2"
              />
              {/* RSI line — aligned to candle x-axis */}
              <polyline
                points={rsiPolyline}
                fill="none"
                stroke="#eab308"
                strokeWidth="1.5"
              />
              <text
                x={5}
                y={rsiTop + 10}
                fill="var(--chart-text)"
                fontSize="9"
                fontFamily="monospace"
              >
                RSI
              </text>
              <text
                x={usableWidth + 5}
                y={rsiTop + rsiH * 0.3 + 3}
                fill="var(--chart-text)"
                fontSize="8"
                fontFamily="monospace"
              >
                70
              </text>
              <text
                x={usableWidth + 5}
                y={rsiTop + rsiH * 0.5 + 3}
                fill="var(--chart-text)"
                fontSize="8"
                fontFamily="monospace"
              >
                50
              </text>
              <text
                x={usableWidth + 5}
                y={rsiTop + rsiH * 0.7 + 3}
                fill="var(--chart-text)"
                fontSize="8"
                fontFamily="monospace"
              >
                30
              </text>
              {/* Current RSI value */}
              {(() => {
                const lastRsi = [...indicators.rsi]
                  .reverse()
                  .find((v) => v !== null);
                if (lastRsi == null) return null;
                return (
                  <text
                    x={usableWidth + 5}
                    y={rsiTop + rsiH - (lastRsi / 100) * rsiH + 3}
                    fill="#eab308"
                    fontSize="9"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {lastRsi.toFixed(0)}
                  </text>
                );
              })()}
            </g>
          )}

          {/* ── Time labels ── */}
          <g fontFamily="monospace">
            {timeLabels.map((l, i) => (
              <text
                key={`t-${i}`}
                x={l.x}
                y={totalH - 5}
                textAnchor="middle"
                fill={l.isMajor ? "#94a3b8" : "#475569"}
                fontSize={l.isMajor ? "10" : "8"}
                fontWeight={l.isMajor ? "bold" : "normal"}
              >
                {l.time}
              </text>
            ))}
          </g>
          {/* X-axis line */}
          <line
            x1={0}
            y1={totalH - xAxisH + 5}
            x2={usableWidth}
            y2={totalH - xAxisH + 5}
            stroke="var(--grid-line)"
            strokeWidth="1"
          />

          {/* ── Trade Markers ── */}
          {trades.length > 0 && (
            <g>
              {trades
                .filter((t) => t.symbol === symbol)
                .map((trade) => {
                  try {
                    // Find the correct candle index based on trade opened_at timestamp
                    const entryDate = new Date(trade.opened_at.replace('Z', '+00:00'));
                    let effectiveEntryIdx = validData.findIndex((c) => {
                      if (!c.timestamp) return false;
                      const candleDate = new Date(c.timestamp + "Z");
                      // Find candle that matches or is closest to trade open time
                      return candleDate.getTime() <= entryDate.getTime();
                    });
                    // If no candle found before trade time, use the FIRST candle (not last!)
                    if (effectiveEntryIdx < 0) effectiveEntryIdx = 0;
                    if (effectiveEntryIdx < 0 || effectiveEntryIdx >= validData.length) return null;

                    const entryX = idxToX(effectiveEntryIdx);
                    const entryY = priceToY(trade.entry_price);
                    const isBuy = trade.direction === "buy";
                    const entryColor = isBuy ? "#22c55e" : "#ef4444";
                  
                    // Triangle marker for entry
                    const triangleSize = 4;
                    const trianglePoints = isBuy
                      ? `${entryX},${entryY - triangleSize} ${entryX - triangleSize},${entryY + triangleSize} ${entryX + triangleSize},${entryY + triangleSize}`
                      : `${entryX},${entryY + triangleSize} ${entryX - triangleSize},${entryY - triangleSize} ${entryX + triangleSize},${entryY - triangleSize}`;
                  
                    return (
                      <g key={`trade-${trade.id}`}>
                        {/* Entry marker */}
                        <polygon
                          points={trianglePoints}
                          fill={entryColor}
                          stroke={entryColor}
                          strokeWidth="2"
                          style={{ cursor: "pointer" }}
                          onMouseEnter={(e) => {
                            setHoveredTrade(trade);
                            const rect = e.currentTarget.getBoundingClientRect();
                            const containerRect =
                              containerRef.current?.getBoundingClientRect();
                            if (containerRect) {
                              setTooltipPos({
                                x: rect.left - containerRect.left - 210,
                                y: rect.top - containerRect.top - 10,
                              });
                            }
                          }}
                          onMouseLeave={() => setHoveredTrade(null)}
                        />
                        {/* Entry price line */}
                        <line
                          x1={entryX - candleWidth}
                          y1={entryY}
                          x2={entryX + candleWidth}
                          y2={entryY}
                          stroke={entryColor}
                          strokeWidth="0.5"
                          strokeDasharray="2,2"
                          opacity="0.5"
                        />

                        {/* Exit marker if closed */}
                        {trade.closed_at &&
                          trade.exit_price &&
                          (() => {
                            const exitDate = new Date(trade.closed_at.replace('Z', '+00:00'));
                            const exitIdxRaw = validData.findIndex((c, i) => {
                              if (c.timestamp && i > effectiveEntryIdx) {
                                const candleDate = new Date((c.timestamp || "") + "Z");
                                return candleDate.getTime() >= exitDate.getTime();
                              }
                              return false;
                            });
                            // Use last candle as fallback
                            // Use first candle if exit not found (not last!)
                            const exitIdx = exitIdxRaw === -1 ? 0 : exitIdxRaw;

                            if (exitIdx < 0 || exitIdx >= validData.length) return null;

                            const exitX = idxToX(exitIdx);
                            const exitY = priceToY(trade.exit_price!);
                            const exitColor = "#fbfbfeff";

                            return (
                              <g key={`exit-${trade.id}`}>
                                {/* Square marker for exit */}
                                <rect
                                  x={exitX - triangleSize / 2}
                                  y={exitY - triangleSize / 2}
                                  width={triangleSize}
                                  height={triangleSize}
                                  fill={exitColor}
                                  stroke={exitColor}
                                  strokeWidth="1"
                                  style={{ cursor: "pointer" }}
                                  onMouseEnter={(e) => {
                                    setHoveredTrade(trade);
                                    const rect =
                                      e.currentTarget.getBoundingClientRect();
                                    const containerRect =
                                      containerRef.current?.getBoundingClientRect();
                                    if (containerRect) {
                                      setTooltipPos({
                                        x: rect.left - containerRect.left - 210,
                                        y: rect.top - containerRect.top - 10,
                                      });
                                    }
                                  }}
                                  onMouseLeave={() => setHoveredTrade(null)}
                                />
                                {/* Trade line connecting entry to exit */}
                                <line
                                  x1={entryX}
                                  y1={entryY}
                                  x2={exitX}
                                  y2={exitY}
                                  stroke={exitColor}
                                  strokeWidth="1"
                                  opacity="0.3"
                                />
                              </g>
                            );
                          })()}
                      </g>
                    );
                  } catch (e) {
                    console.warn('Bad trade:', trade.id, e);
                    return null;
                  }
                }).filter(Boolean)
                }
            </g>
          )}

        {/* TP/SL Lines - only when selectedPosition is provided */}
        {selectedPosition && (
          <g>
            <text x={chartWidth-25} y={20} fill="#666" fontSize={14} style={{cursor:"pointer"}} onClick={() => window.dispatchEvent(new CustomEvent("clearPosition"))}>✕</text>
          <g>
            {/* TP Line - draggable */}
            <line 
              x1="0" x2={chartWidth} 
              y1={priceToY(selectedPosition.take_profit)} 
              y2={priceToY(selectedPosition.take_profit)} 
              stroke="#22c55e" 
              strokeWidth={draggingLine === "tp" ? "2" : "1.5"} 
              strokeDasharray="5,3" 
              style={{ cursor: "ns-resize" }}
              onMouseDown={(e) => handleLineDragStart("tp", e)}
            />
            {/* TP hit area - larger for easier grabbing */}
            <line 
              x1="0" x2={chartWidth} 
              y1={priceToY(selectedPosition.take_profit) - 8} 
              y2={priceToY(selectedPosition.take_profit) + 8} 
              stroke="transparent" 
              strokeWidth="16" 
              style={{ cursor: "ns-resize" }}
              onMouseDown={(e) => handleLineDragStart("tp", e)}
            />
            <text x="5" y={priceToY(selectedPosition.take_profit) - 8} fill="#22c55e" fontSize="11" fontWeight="bold">TP: {selectedPosition.take_profit.toFixed(2)}</text>
            <text x={usableWidth - 5} y={priceToY(selectedPosition.take_profit) + 3} fill="#22c55e" fontSize="9" textAnchor="end" opacity="0.7">↕ drag</text>
            
            {/* SL Line - draggable */}
            <line 
              x1="0" x2={chartWidth} 
              y1={priceToY(selectedPosition.stop_loss)} 
              y2={priceToY(selectedPosition.stop_loss)} 
              stroke="#ef4444" 
              strokeWidth={draggingLine === "sl" ? "2" : "1.5"} 
              strokeDasharray="5,3" 
              style={{ cursor: "ns-resize" }}
              onMouseDown={(e) => handleLineDragStart("sl", e)}
            />
            {/* SL hit area - larger for easier grabbing */}
            <line 
              x1="0" x2={chartWidth} 
              y1={priceToY(selectedPosition.stop_loss) - 8} 
              y2={priceToY(selectedPosition.stop_loss) + 8} 
              stroke="transparent" 
              strokeWidth="16" 
              style={{ cursor: "ns-resize" }}
              onMouseDown={(e) => handleLineDragStart("sl", e)}
            />
            <text x="5" y={priceToY(selectedPosition.stop_loss) - 8} fill="#ef4444" fontSize="11" fontWeight="bold">SL: {selectedPosition.stop_loss.toFixed(2)}</text>
            <text x={usableWidth - 5} y={priceToY(selectedPosition.stop_loss) + 3} fill="#ef4444" fontSize="9" textAnchor="end" opacity="0.7">↕ drag</text>
            
            {/* Entry Line */}
            <line x1="0" x2={chartWidth} y1={priceToY(selectedPosition.entry_price)} y2={priceToY(selectedPosition.entry_price)} stroke="#fbbf24" strokeWidth="1" strokeDasharray="3,2" opacity="0.8" />
            <text x="5" y={priceToY(selectedPosition.entry_price) - 5} fill="#fbbf24" fontSize="10" fontWeight="bold" opacity="0.9">ENTRY: {selectedPosition.entry_price.toFixed(2)}</text>
          </g>
          </g>
        )}

        </svg>

        {/* Trade Tooltip */}
        {hoveredTrade && (
          <div
            className="absolute z-50 p-2 rounded text-[10px] font-mono pointer-events-none"
            style={{
              right: tooltipPos.x,
              bottom: tooltipPos.y,
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--bg-tertiary)",
              color: "var(--text-primary)",
              boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
              minWidth: "200px",
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px]" style={{ color: "#94a3b8" }}>#{hoveredTrade.id}</span>
              <span className="font-bold">{hoveredTrade.symbol}</span>
              <span
                className="px-1.5 py-0.5 rounded text-[9px] font-bold"
                style={{
                  backgroundColor:
                    hoveredTrade.direction === "buy"
                      ? "rgba(34, 197, 94, 0.2)"
                      : "rgba(239, 68, 68, 0.2)",
                  color:
                    hoveredTrade.direction === "buy" ? "var(--success)" : "var(--danger)",
                }}
              >
                {hoveredTrade.direction.toUpperCase()}
              </span>
              {hoveredTrade.result && (
                <span
                  className="px-1.5 py-0.5 rounded text-[9px] font-bold"
                  style={{
                    backgroundColor:
                      hoveredTrade.result === "win"
                        ? "rgba(34, 197, 94, 0.2)"
                        : "rgba(239, 68, 68, 0.2)",
                    color:
                      hoveredTrade.result === "win" ? "var(--success)" : "var(--danger)",
                  }}
                >
                  {hoveredTrade.result.toUpperCase()}
                </span>
              )}
            </div>
            <div className="space-y-0.5" style={{ color: "#94a3b8" }}>
              <div className="flex justify-between">
                <span>Entry:</span>
                <span style={{ color: "var(--text-primary)" }}>
                  {hoveredTrade.entry_price.toFixed(2)}
                </span>
              </div>
              {hoveredTrade.exit_price && (
                <div className="flex justify-between">
                  <span>Exit:</span>
                  <span style={{ color: "var(--text-primary)" }}>
                    {hoveredTrade.exit_price.toFixed(2)}
                  </span>
                </div>
              )}
              {hoveredTrade.pnl_usd !== undefined && (
                <div className="flex justify-between">
                  <span>P&L:</span>
                  <span
                    style={{
                      color: hoveredTrade.pnl_usd >= 0 ? "var(--success)" : "var(--danger)",
                    }}
                  >
                    {hoveredTrade.pnl_usd >= 0 ? "+" : ""}$
                    {hoveredTrade.pnl_usd.toFixed(2)} USD
                  </span>
                </div>
              )}
              {(hoveredTrade.take_profit || hoveredTrade.stop_loss) && (
                <>
                  {hoveredTrade.take_profit && (
                    <div className="flex justify-between">
                      <span>TP:</span>
                      <span style={{ color: "var(--success)" }}>
                        {hoveredTrade.take_profit.toFixed(2)}
                      </span>
                    </div>
                  )}
                  {hoveredTrade.stop_loss && (
                    <div className="flex justify-between">
                      <span>SL:</span>
                      <span style={{ color: "var(--danger)" }}>
                        {hoveredTrade.stop_loss.toFixed(2)}
                      </span>
                    </div>
                  )}
                </>
              )}
              <div
                className="flex justify-between text-[9px] mt-1 pt-1"
                style={{ borderTop: "1px solid var(--bg-tertiary)" }}
              >
                <span>Opened:</span>
                <span>
                  {(() => {
                    const d = new Date(hoveredTrade.opened_at.replace('Z', '+00:00'));
                    const wd = new Date(d.toLocaleString('en-US', { timeZone: 'Europe/Warsaw' }));
                    return wd.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: 'Europe/Warsaw' });
                  })()}
                </span>
              </div>
              {hoveredTrade.closed_at && (
                <div className="flex justify-between text-[9px]">
                  <span>Closed:</span>
                  <span>
                    {(() => {
                      const d = new Date(hoveredTrade.closed_at.replace('Z', '+00:00'));
                      const wd = new Date(d.toLocaleString('en-US', { timeZone: 'Europe/Warsaw' }));
                      return wd.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: 'Europe/Warsaw' });
                    })()}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
