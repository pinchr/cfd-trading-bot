import React, { useState, useEffect } from "react";
import { apiUrl } from "../api";

interface NewsArticle {
  symbol: string;
  name: string;
  headline: string;
  sentiment: number;
  direction: "buy" | "sell" | "neutral";
  importance: number;
  source: string;
  url: string;
  published: string;
}

interface NewsResponse {
  news: NewsArticle[];
  timestamp: string;
}

const symbolColors: Record<string, string> = {
  XAU: "#eab308",
  XAG: "#94a3b8",
  US100: "#3b82f6",
  BTC: "#f97316",
};

export const NewsTab: React.FC = () => {
  const [newsData, setNewsData] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchNews = async () => {
      setLoading(true);
      try {
        const response = await fetch(apiUrl("news/all"));
        if (response.ok) {
          const data: NewsResponse = await response.json();
          setNewsData(data.news);
        }
      } catch (error) {
        console.error("Failed to fetch news:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
    const interval = setInterval(fetchNews, 10800000); // 3h
    return () => clearInterval(interval);
  }, []);

  const getDirColor = (direction: string) => {
    if (direction === "buy") return "#22c55e";
    if (direction === "sell") return "#ef4444";
    return "#64748b";
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    if (diffMins < 1) return "Now";
    if (diffMins < 60) return `${diffMins}m`;
    if (diffHours < 24) return `${diffHours}h`;
    return `${Math.floor(diffMs / 86400000)}d`;
  };

  return (
    <div className="h-full flex flex-col p-2 md:p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span
          className="text-[11px] font-medium uppercase tracking-wider"
          style={{ color: "#64748b" }}
        >
          News & Sentiment
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchNews()}
            disabled={loading}
            className="px-3 py-1 text-xs bg-[#1a1f35]/50 hover:bg-blue-500/70 rounded border border-[#2a3349]/50 text-[#e2e8f0] transition-all font-medium"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
          <span className="text-[10px]" style={{ color: "#374151" }}>
            {newsData.length} articles
          </span>
        </div>
      </div>

      {/* Content */}
      <div
        className="flex-1 overflow-auto rounded-sm"
        style={{ backgroundColor: "#0d1220", border: "1px solid #1a1f35" }}
      >
        {loading && newsData.length === 0 ? (
          <div
            className="h-full flex items-center justify-center"
            style={{ color: "#4a5568" }}
          >
            <div className="text-xs uppercase tracking-widest">
              Loading news...
            </div>
          </div>
        ) : newsData.length > 0 ? (
          <>
            {/* Mobile card layout */}
            <div className="md:hidden p-2 space-y-2">
              {newsData.map((article, idx) => {
                const dirColor = getDirColor(article.direction);
                const symColor = symbolColors[article.symbol] || "#64748b";
                return (
                  <div
                    key={idx}
                    className="rounded-sm p-3"
                    style={{
                      backgroundColor: "#0b0f1a",
                      border: "1px solid #131825",
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ backgroundColor: symColor }}
                        />
                        <span
                          className="font-bold text-[11px]"
                          style={{ color: "#e2e8f0" }}
                        >
                          {article.symbol}
                        </span>
                        <span
                          className="text-[10px] font-bold px-2 py-0.5 rounded-sm"
                          style={{
                            color: dirColor,
                            backgroundColor: `${dirColor}15`,
                          }}
                        >
                          {article.direction.toUpperCase()}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className="font-bold text-[11px]"
                          style={{ color: dirColor }}
                        >
                          {article.sentiment > 0 ? "+" : ""}
                          {article.sentiment.toFixed(2)}
                        </span>
                        <span
                          className="text-[10px]"
                          style={{ color: "#374151" }}
                        >
                          {formatTime(article.published)}
                        </span>
                      </div>
                    </div>
                    <div
                      className="text-[11px] leading-relaxed"
                      style={{ color: "#c8cdd8" }}
                    >
                      {article.headline}
                    </div>
                    <div
                      className="flex items-center justify-between mt-1.5 text-[9px]"
                      style={{ color: "#374151" }}
                    >
                      <span>{article.source}</span>
                      <span>Imp: {Math.round(article.importance * 100)}%</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Desktop table */}
            <table className="w-full text-[11px] hidden md:table">
              <thead>
                <tr style={{ borderBottom: "1px solid #1a1f35" }}>
                  <th
                    className="px-4 py-2.5 text-left font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Symbol
                  </th>
                  <th
                    className="px-3 py-2.5 text-left font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Headline
                  </th>
                  <th
                    className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Sentiment
                  </th>
                  <th
                    className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Signal
                  </th>
                  <th
                    className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Imp.
                  </th>
                  <th
                    className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Source
                  </th>
                  <th
                    className="px-3 py-2.5 text-center font-medium uppercase tracking-wider"
                    style={{ color: "#4a5568" }}
                  >
                    Time
                  </th>
                </tr>
              </thead>
              <tbody>
                {newsData.map((article, idx) => {
                  const dirColor = getDirColor(article.direction);
                  const symColor = symbolColors[article.symbol] || "#64748b";
                  return (
                    <tr
                      key={idx}
                      style={{ borderBottom: "1px solid #131825" }}
                      className="transition-colors"
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.backgroundColor =
                          "rgba(26, 31, 53, 0.5)")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.backgroundColor = "transparent")
                      }
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ backgroundColor: symColor }}
                          />
                          <span
                            className="font-bold"
                            style={{ color: "#e2e8f0" }}
                          >
                            {article.symbol}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 max-w-md">
                        <div className="truncate" style={{ color: "#c8cdd8" }}>
                          {article.headline}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <span className="font-bold" style={{ color: dirColor }}>
                          {article.sentiment > 0 ? "+" : ""}
                          {article.sentiment.toFixed(2)}
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
                          {article.direction.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <div
                            className="w-8 h-1 rounded-full"
                            style={{ backgroundColor: "#1a1f35" }}
                          >
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${article.importance * 100}%`,
                                backgroundColor: "#64748b",
                              }}
                            />
                          </div>
                          <span
                            className="text-[9px]"
                            style={{ color: "#4a5568" }}
                          >
                            {Math.round(article.importance * 100)}%
                          </span>
                        </div>
                      </td>
                      <td
                        className="px-3 py-2.5 text-center"
                        style={{ color: "#374151" }}
                      >
                        {article.source}
                      </td>
                      <td
                        className="px-3 py-2.5 text-center"
                        style={{ color: "#374151" }}
                      >
                        {formatTime(article.published)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        ) : (
          <div
            className="h-full flex items-center justify-center"
            style={{ color: "#4a5568" }}
          >
            <div className="text-xs uppercase tracking-widest">
              No news available
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
