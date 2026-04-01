import "./App.css";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Chart color palette for retailer lines
const CHART_COLORS = [
  "#f97316", // orange (primary)
  "#2563eb", // blue
  "#16a34a", // green
  "#8b5cf6", // violet
  "#0891b2", // cyan
  "#dc2626", // red
];

// Popular shoes to suggest when no results found
const POPULAR_SHOES = [
  "Nike Pegasus 41",
  "ASICS Gel-Kayano 31",
  "Brooks Ghost 16",
  "Hoka Clifton 9",
  "New Balance Fresh Foam 1080v13",
  "ON Cloudmonster 2",
  "Altra Torin 7",
  "Saucony Endorphin Speed 4",
];

const SIZE_OPTIONS = [
  "",
  ...Array.from({ length: 23 }, (_, i) => {
    const size = 5 + i * 0.5;
    return Number.isInteger(size) ? String(size) : size.toFixed(1);
  }),
];

const WIDTH_OPTIONS = [
  { value: "", label: "Any" },
  { value: "narrow", label: "Narrow" },
  { value: "standard", label: "Standard" },
  { value: "wide", label: "Wide" },
  { value: "extra-wide", label: "Extra Wide" },
];

// Keywords for "Best for" tags
const BEST_FOR_KEYWORDS = {
  marathon: ["marathon", "26.2", "long distance race"],
  trail: ["trail", "off-road", "hiking", "terrain", "technical trail", "ultra trail"],
  "daily trainer": ["daily trainer", "everyday", "daily run", "rotation", "workhorse"],
  speed: ["speed", "tempo", "race day", "fast", "5k", "10k", "carbon plate", "race shoe"],
  recovery: ["recovery", "easy run", "slow", "cushioned", "plush", "soft"],
  "long runs": ["long run", "high mileage", "endurance", "ultra"],
  "wide toe box": ["wide toe", "zero drop", "natural fit", "toe splay", "bunions"],
  stability: ["stability", "overpronation", "motion control", "support", "arch support"],
};

// Parse price string to number
function parsePrice(priceStr) {
  if (!priceStr) return Infinity;
  const match = priceStr.match(/[\d,.]+/);
  if (!match) return Infinity;
  return parseFloat(match[0].replace(/,/g, ""));
}

// Get minimum price from retailers
function getMinPrice(shoe) {
  if (!shoe.retailers || shoe.retailers.length === 0) return Infinity;
  return Math.min(...shoe.retailers.map((r) => parsePrice(r.price)));
}

// Get all unique brands from shoes
function getUniqueBrands(shoes) {
  const brands = new Set(shoes.map((s) => s.brand).filter(Boolean));
  return Array.from(brands).sort();
}

// Get all unique retailers from shoes
function getUniqueRetailers(shoes) {
  const retailers = new Set();
  shoes.forEach((s) => {
    s.retailers?.forEach((r) => {
      if (r.retailer) retailers.add(r.retailer);
    });
  });
  return Array.from(retailers).sort();
}

function normalizeValue(value) {
  return String(value ?? "").trim().toLowerCase().replace(/[+\s_-]+/g, "");
}

function normalizeSizeValue(value) {
  return normalizeValue(value).replace(/^us/, "");
}

function normalizeWidthValue(value) {
  const normalized = normalizeValue(value);
  if (!normalized) return "";
  if (["n", "narrow"].includes(normalized)) return "narrow";
  if (["d", "m", "medium", "regular", "standard", "default"].includes(normalized)) return "standard";
  if (["w", "wide"].includes(normalized)) return "wide";
  if (["2xwide", "doublewide", "extrawide", "xxwide", "2e", "3e", "4e"].includes(normalized)) return "extra-wide";
  if (/^\d+e$/.test(normalized)) {
    return parseInt(normalized, 10) >= 2 ? "extra-wide" : "wide";
  }
  return normalized;
}

function getVariantEntries(shoe) {
  const variants = [];

  if (Array.isArray(shoe?.size_variants)) {
    variants.push(...shoe.size_variants);
  }

  if (Array.isArray(shoe?.variants)) {
    variants.push(...shoe.variants);
  }

  if (Array.isArray(shoe?.available_sizes)) {
    variants.push(...shoe.available_sizes.map((size) => (
      typeof size === "object" ? size : { size }
    )));
  }

  if (Array.isArray(shoe?.available_widths)) {
    variants.push(...shoe.available_widths.map((width) => (
      typeof width === "object" ? width : { width }
    )));
  }

  if (Array.isArray(shoe?.sizes)) {
    variants.push(...shoe.sizes.map((size) => (
      typeof size === "object" ? size : { size }
    )));
  }

  if (shoe?.size || shoe?.width) {
    variants.push({
      size: shoe.size,
      width: shoe.width,
      available: shoe.available,
    });
  }

  return variants;
}

function shoeHasMatchingSize(shoe, selectedSize) {
  if (!selectedSize) return true;

  const target = normalizeSizeValue(selectedSize);
  const variants = getVariantEntries(shoe).filter((variant) => variant?.available !== false);
  if (variants.length === 0) return false;

  return variants.some((variant) => {
    const sizeFields = [variant?.size, variant?.value, variant?.name, variant?.label];
    return sizeFields.some((field) => normalizeSizeValue(field) === target);
  });
}

function shoeHasMatchingWidth(shoe, selectedWidth) {
  if (!selectedWidth) return true;

  const target = normalizeWidthValue(selectedWidth);
  const variants = getVariantEntries(shoe).filter((variant) => variant?.available !== false);
  if (variants.length === 0) return false;

  return variants.some((variant) => {
    const widthFields = [variant?.width, variant?.width_value, variant?.widthLabel, variant?.value];
    return widthFields.some((field) => normalizeWidthValue(field) === target);
  });
}

function getDiscountPercent(shoe) {
  const discount = shoe?.discount_pct ?? shoe?.deal_info?.discount_percent;
  if (typeof discount === "number") return discount;
  const parsed = Number.parseFloat(discount);
  return Number.isFinite(parsed) ? parsed : 0;
}

// Shoe image with graceful fallback
function ShoeImage({ src, alt }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return <div className="shoe-img-placeholder">👟</div>;
  }
  return (
    <img
      src={src}
      alt={alt}
      className="shoe-img"
      onError={() => setFailed(true)}
    />
  );
}

function PriceHistoryChart({ shoeModel }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState(null);

  // Sanitized ID prefix for SVG gradient IDs (must be unique per shoe)
  const idPrefix = useMemo(
    () => "ph-" + shoeModel.replace(/[^a-zA-Z0-9]/g, "").slice(0, 20),
    [shoeModel]
  );

  useEffect(() => {
    fetch(`${API_BASE_URL}/shoes/${encodeURIComponent(shoeModel)}/price-history`)
      .then((res) => res.json())
      .then((data) => {
        setHistory(data.price_history || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [shoeModel]);

  const chartData = useMemo(() => {
    if (!history.length) return null;

    // Group by retailer, then by calendar day (average prices per day)
    const byRetailer = {};
    history.forEach((entry) => {
      const retailer = entry.retailer || "Unknown";
      const price = entry.price_value;
      if (!price || price === Infinity || isNaN(price)) return;
      const d = new Date(entry.timestamp);
      const dayKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      if (!byRetailer[retailer]) byRetailer[retailer] = {};
      if (!byRetailer[retailer][dayKey]) byRetailer[retailer][dayKey] = [];
      byRetailer[retailer][dayKey].push(price);
    });

    // Convert to sorted point arrays, keep retailers with ≥2 days of data
    const series = Object.entries(byRetailer)
      .map(([retailer, days]) => ({
        retailer,
        points: Object.entries(days)
          .map(([k, prices]) => ({
            date: new Date(k),
            price: prices.reduce((a, b) => a + b, 0) / prices.length,
          }))
          .sort((a, b) => a.date - b.date),
      }))
      .filter((s) => s.points.length >= 2)
      .sort((a, b) => b.points.length - a.points.length)
      .slice(0, 6);

    // Stats from all raw history (not just daily agg)
    const allPrices = history
      .map((h) => h.price_value)
      .filter((p) => p && p !== Infinity && !isNaN(p));
    const statsMin = Math.min(...allPrices);
    const statsMax = Math.max(...allPrices);
    const statsAvg = allPrices.reduce((a, b) => a + b, 0) / allPrices.length;

    return { series, statsMin, statsMax, statsAvg, hasChart: series.length > 0 };
  }, [history]);

  if (loading) return null;
  if (!chartData || history.length === 0) return null;

  const { series, statsMin, statsMax, statsAvg, hasChart } = chartData;

  // ── SVG layout constants ──────────────────────────────────────────────────
  const W = 400, H = 160;
  const PAD = { top: 16, right: 12, bottom: 28, left: 46 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  let toX, toY, xLabels, yLabels, gridYs;

  if (hasChart) {
    const allDates = series.flatMap((s) => s.points.map((p) => p.date.getTime()));
    const allPriceVals = series.flatMap((s) => s.points.map((p) => p.price));
    const minTime = Math.min(...allDates);
    const maxTime = Math.max(...allDates);
    const minP = Math.min(...allPriceVals);
    const maxP = Math.max(...allPriceVals);
    const pad = (maxP - minP) * 0.12 || 10;
    const priceMin = Math.max(0, minP - pad);
    const priceMax = maxP + pad;
    const timeRange = maxTime - minTime || 1;

    toX = (date) => PAD.left + ((date.getTime() - minTime) / timeRange) * plotW;
    toY = (price) => PAD.top + plotH - ((price - priceMin) / (priceMax - priceMin)) * plotH;

    // Y grid: 4 evenly-spaced price levels
    gridYs = [0.0, 0.33, 0.67, 1.0].map((t) => ({
      price: priceMin + (priceMax - priceMin) * t,
      y: toY(priceMin + (priceMax - priceMin) * t),
    }));

    yLabels = gridYs;

    // X axis: 3-4 date labels
    const xCount = Math.min(4, series[0].points.length);
    xLabels = Array.from({ length: xCount }, (_, i) => {
      const t = minTime + timeRange * (i / Math.max(xCount - 1, 1));
      return {
        date: new Date(t),
        x: PAD.left + ((t - minTime) / timeRange) * plotW,
      };
    });
  }

  // ── SVG path helpers ──────────────────────────────────────────────────────
  const makePath = (points) => {
    if (points.length < 2) return "";
    const coords = points.map((p) => [toX(p.date), toY(p.price)]);
    let d = `M ${coords[0][0]},${coords[0][1]}`;
    for (let i = 1; i < coords.length; i++) {
      const cpX = (coords[i - 1][0] + coords[i][0]) / 2;
      d += ` C ${cpX},${coords[i - 1][1]} ${cpX},${coords[i][1]} ${coords[i][0]},${coords[i][1]}`;
    }
    return d;
  };

  const makeArea = (points) => {
    if (points.length < 2) return "";
    const baseY = PAD.top + plotH;
    const coords = points.map((p) => [toX(p.date), toY(p.price)]);
    let d = `M ${coords[0][0]},${baseY} L ${coords[0][0]},${coords[0][1]}`;
    for (let i = 1; i < coords.length; i++) {
      const cpX = (coords[i - 1][0] + coords[i][0]) / 2;
      d += ` C ${cpX},${coords[i - 1][1]} ${cpX},${coords[i][1]} ${coords[i][0]},${coords[i][1]}`;
    }
    d += ` L ${coords[coords.length - 1][0]},${baseY} Z`;
    return d;
  };

  // ── Tooltip handler ───────────────────────────────────────────────────────
  const handleMouseMove = (e) => {
    if (!hasChart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * W;
    const relX = svgX - PAD.left;
    if (relX < 0 || relX > plotW) { setTooltip(null); return; }

    const allDates = series.flatMap((s) => s.points.map((p) => p.date.getTime()));
    const minTime = Math.min(...allDates);
    const maxTime = Math.max(...allDates);
    const hoverT = minTime + (relX / plotW) * (maxTime - minTime);
    const hoverDate = new Date(hoverT);

    const entries = series.map((s, idx) => {
      const nearest = s.points.reduce((best, p) =>
        Math.abs(p.date - hoverDate) < Math.abs(best.date - hoverDate) ? p : best
      );
      return { retailer: s.retailer, price: nearest.price, date: nearest.date, color: CHART_COLORS[idx % CHART_COLORS.length] };
    });

    setTooltip({ x: PAD.left + relX, date: entries[0]?.date || hoverDate, entries });
  };

  return (
    <div className="price-history-section">
      <h4>Price History</h4>

      {hasChart ? (
        <div className="price-chart-wrapper" onMouseLeave={() => setTooltip(null)}>
          {/* SVG chart */}
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="price-chart-svg"
            onMouseMove={handleMouseMove}
            aria-label={`Price history chart for ${shoeModel}`}
          >
            <defs>
              {series.map((_, i) => (
                <linearGradient key={i} id={`${idPrefix}-g${i}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity="0.18" />
                  <stop offset="100%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity="0" />
                </linearGradient>
              ))}
            </defs>

            {/* Chart border/background */}
            <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH}
              fill="#fafafe" rx="4" />

            {/* Horizontal grid lines */}
            {gridYs.map((g, i) => (
              <line key={i} x1={PAD.left} y1={g.y} x2={PAD.left + plotW} y2={g.y}
                stroke="#e2e8f0" strokeWidth="1" />
            ))}

            {/* Area fill (single series only) */}
            {series.length === 1 && (
              <path d={makeArea(series[0].points)} fill={`url(#${idPrefix}-g0)`} />
            )}

            {/* Lines */}
            {series.map((s, i) => (
              <path
                key={s.retailer}
                d={makePath(s.points)}
                fill="none"
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                strokeWidth={series.length === 1 ? 2.5 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ))}

            {/* Data point dots (only when ≤10 points to avoid clutter) */}
            {series.map((s, i) =>
              s.points.length <= 10 && s.points.map((p, j) => (
                <circle key={`${i}-${j}`}
                  cx={toX(p.date)} cy={toY(p.price)}
                  r="3" fill={CHART_COLORS[i % CHART_COLORS.length]}
                  stroke="white" strokeWidth="1.5"
                />
              ))
            )}

            {/* Y axis labels */}
            {yLabels.filter((_, i) => i % 2 === 0 || yLabels.length <= 4).map((l, i) => (
              <text key={i} x={PAD.left - 6} y={l.y + 4}
                textAnchor="end" fontSize="9" fill="#64748b">
                ${Math.round(l.price)}
              </text>
            ))}

            {/* X axis labels */}
            {xLabels.map((l, i) => (
              <text key={i} x={l.x} y={H - 4}
                textAnchor={i === 0 ? "start" : i === xLabels.length - 1 ? "end" : "middle"}
                fontSize="8.5" fill="#94a3b8">
                {l.date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </text>
            ))}

            {/* Tooltip crosshair */}
            {tooltip && (
              <>
                <line
                  x1={tooltip.x} y1={PAD.top}
                  x2={tooltip.x} y2={PAD.top + plotH}
                  stroke="#1e293b" strokeWidth="1"
                  strokeDasharray="3,2" opacity="0.45"
                />
                {tooltip.entries.map((entry, i) => (
                  <circle key={i}
                    cx={tooltip.x} cy={toY(entry.price)}
                    r="4.5" fill={entry.color}
                    stroke="white" strokeWidth="2"
                  />
                ))}
              </>
            )}
          </svg>

          {/* Hover tooltip box */}
          {tooltip && (
            <div
              className="price-chart-tooltip"
              style={{ left: `${Math.min(((tooltip.x - PAD.left) / plotW) * 100, 58)}%` }}
            >
              <div className="price-chart-tooltip-date">
                {tooltip.date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </div>
              {tooltip.entries.map((e, i) => (
                <div key={i} className="price-chart-tooltip-row">
                  <span className="price-chart-tooltip-dot" style={{ background: e.color }} />
                  <span className="price-chart-tooltip-retailer">{e.retailer}</span>
                  <span className="price-chart-tooltip-price">${e.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* Per-retailer legend (multi-series only) */}
      {hasChart && series.length > 1 && (
        <div className="price-chart-legend">
          {series.map((s, i) => (
            <div key={s.retailer} className="price-chart-legend-item">
              <span className="price-chart-legend-dot"
                style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
              <span>{s.retailer}</span>
            </div>
          ))}
        </div>
      )}

      {/* Stats strip always shown */}
      <div className="price-history-stats">
        <div className="price-stat">
          <span className="price-stat-label">Lowest</span>
          <span className="price-stat-value price-stat--low">${statsMin.toFixed(0)}</span>
        </div>
        <div className="price-stat">
          <span className="price-stat-label">Average</span>
          <span className="price-stat-value">${statsAvg.toFixed(0)}</span>
        </div>
        <div className="price-stat">
          <span className="price-stat-label">Highest</span>
          <span className="price-stat-value price-stat--high">${statsMax.toFixed(0)}</span>
        </div>
      </div>
    </div>
  );
}

function SimilarShoes({ shoeModel }) {
  const [similar, setSimilar] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/shoes/${encodeURIComponent(shoeModel)}/similar?limit=4`)
      .then((res) => res.json())
      .then((data) => {
        setSimilar(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [shoeModel]);

  if (loading) return <p className="similar-loading">Finding similar shoes...</p>;
  if (similar.length === 0) return null;

  return (
    <div className="similar-shoes">
      <h4>Similar Shoes</h4>
      <div className="similar-shoes-grid">
        {similar.map((s) => (
          <div key={s.model} className="similar-shoe-card">
            <ShoeImage src={s.image} alt={s.model} />
            <span className="similar-shoe-name">{s.model}</span>
            <span className="similar-shoe-price">
              {s.retailers?.[0]?.price || "N/A"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Price Alert Modal ────────────────────────────────────────────────────────
function PriceAlertModal({ shoe, onClose }) {
  const minPrice = getMinPrice(shoe);
  const suggestedTarget = minPrice < Infinity ? Math.floor(minPrice * 0.9) : "";

  const [email, setEmail] = useState("");
  const [targetPrice, setTargetPrice] = useState(suggestedTarget);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { type: 'success' | 'error', message }

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !String(targetPrice).trim()) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE_URL}/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          shoe_model: shoe.model,
          target_price: parseFloat(targetPrice),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create alert.");
      setResult({ type: "success", message: data.message });
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="alert-modal-overlay"
      onClick={onClose}
      role="button"
      tabIndex={0}
      aria-label="Close price alert"
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClose(); }}
    >
      <div className="alert-modal" onClick={(e) => e.stopPropagation()}>
        <button className="alert-modal-close" onClick={onClose} aria-label="Close">×</button>

        <div className="alert-modal-header">
          <span className="alert-modal-icon">🔔</span>
          <div>
            <h3 className="alert-modal-title">Set Price Alert</h3>
            <p className="alert-modal-subtitle">{shoe.model}</p>
          </div>
        </div>

        {/* Current price context */}
        {minPrice < Infinity && (
          <div className="alert-current-price-row">
            <span className="alert-current-label">Current best price</span>
            <span className="alert-current-value">${minPrice.toFixed(2)}</span>
          </div>
        )}

        {result ? (
          <div className={`alert-result alert-result--${result.type}`}>
            {result.type === "success" ? "✓" : "✗"} {result.message}
            {result.type === "success" && (
              <button className="alert-done-btn" onClick={onClose}>Done</button>
            )}
          </div>
        ) : (
          <form className="alert-form" onSubmit={handleSubmit}>
            <label className="alert-label">
              Your email
              <input
                className="alert-input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </label>

            <label className="alert-label">
              Alert me when price drops to
              <div className="alert-price-input-wrapper">
                <span className="alert-dollar">$</span>
                <input
                  className="alert-input alert-input--price"
                  type="number"
                  min="1"
                  max={minPrice < Infinity ? Math.ceil(minPrice) : 1000}
                  step="1"
                  placeholder={suggestedTarget || "120"}
                  value={targetPrice}
                  onChange={(e) => setTargetPrice(e.target.value)}
                  required
                />
              </div>
              {minPrice < Infinity && (
                <span className="alert-hint">
                  Suggested: ${suggestedTarget} (10% below current)
                </span>
              )}
            </label>

            <button
              className="alert-submit-btn"
              type="submit"
              disabled={submitting || !email.trim() || !targetPrice}
            >
              {submitting ? "Setting alert…" : "🔔 Notify Me"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function ShoeCard({ shoe, onCompareToggle, isCompareSelected, compareCount }) {
  const [reviews, setReviews] = useState(null); // null = not loaded yet
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [showReviews, setShowReviews] = useState(false);
  const [bestForTags, setBestForTags] = useState([]);
  const [showAlertModal, setShowAlertModal] = useState(false);

  // Lazy: only fetch reviews when the user clicks the reviews button
  const handleOpenReviews = useCallback(() => {
    if (reviews === null && !loadingReviews) {
      setLoadingReviews(true);
      fetch(`${API_BASE_URL}/reviews?shoe_model=${encodeURIComponent(shoe.model)}`)
        .then((res) => res.json())
        .then((data) => {
          const reviewData = Array.isArray(data) ? data : [];
          setReviews(reviewData);
          // Extract "Best for" tags from reviews
          const tags = extractBestForTags(reviewData);
          setBestForTags(tags);
          setLoadingReviews(false);
        })
        .catch((err) => {
          console.error("Failed to fetch reviews:", err);
          setReviews([]);
          setLoadingReviews(false);
        });
    }
    setShowReviews(true);
  }, [shoe.model, reviews, loadingReviews]);

  // Extract best-for tags from review text
  function extractBestForTags(reviewData) {
    const foundTags = new Set();
    const textToSearch = reviewData
      .map((r) => `${r.post_title || ""} ${r.post_text || ""} ${r.summary || ""} ${(r.pros || []).join(" ")} ${(r.cons || []).join(" ")}`)
      .join(" ")
      .toLowerCase();

    for (const [tag, keywords] of Object.entries(BEST_FOR_KEYWORDS)) {
      for (const keyword of keywords) {
        if (textToSearch.includes(keyword.toLowerCase())) {
          foundTags.add(tag);
          break;
        }
      }
    }
    return Array.from(foundTags).slice(0, 3); // Max 3 tags
  }

  // Close overlay on Escape key
  useEffect(() => {
    if (!showReviews) return;
    const handler = (e) => { if (e.key === "Escape") setShowReviews(false); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showReviews]);

  const hasReviewData = reviews !== null && reviews.length > 0;

  const canAddToCompare = isCompareSelected || compareCount < 3;

  return (
    <>
      <div className="shoe-card-wrapper">
        <div className={`shoe-card ${isCompareSelected ? "shoe-card--selected" : ""}`}>
          {/* Compare checkbox */}
          <label className="compare-checkbox">
            <input
              type="checkbox"
              checked={isCompareSelected}
              onChange={() => onCompareToggle(shoe)}
              disabled={!canAddToCompare}
            />
            <span>Compare</span>
          </label>

          {/* Sale Badge */}
          {shoe.discount_pct && (
            <div className="sale-badge">
              {Math.round(shoe.discount_pct)}% OFF
            </div>
          )}

          {/* Price Drop Indicator */}
          {shoe.average_price && shoe.discount_pct >= 10 && (
            <div className="price-drop-indicator">
              🔥 Price Drop
            </div>
          )}

          <ShoeImage src={shoe.image} alt={shoe.model} />
          <h2>{shoe.model}</h2>
          <p>
            <span className="brand-name">{shoe.brand}</span>
          </p>

          {/* Best for tags */}
          {bestForTags.length > 0 && (
            <div className="best-for-tags">
              {bestForTags.map((tag) => (
                <span key={tag} className="best-for-tag">
                  {tag}
                </span>
              ))}
            </div>
          )}

          <span className="retailers">Retailers</span>
          <ul>
            {shoe.retailers.map((r, i) => (
              <li key={i}>
                <strong>{r.retailer}</strong>: {r.price}
                {" — "}
                <a href={r.link} target="_blank" rel="noopener noreferrer" className="buy-button">
                  Buy
                </a>
              </li>
            ))}
          </ul>

          <div className="shoe-card-buttons">
            <button
              className="reviews-toggle-button"
              onClick={handleOpenReviews}
            >
              💬 Reviews
            </button>
            <button
              className="alert-toggle-button"
              onClick={() => setShowAlertModal(true)}
              aria-label={`Set price alert for ${shoe.model}`}
            >
              🔔 Alert
            </button>
          </div>
        </div>
      </div>

      {showAlertModal && (
        <PriceAlertModal shoe={shoe} onClose={() => setShowAlertModal(false)} />
      )}

      {showReviews && (
        <div
          className="reviews-popout-overlay"
          onClick={() => setShowReviews(false)}
          role="button"
          tabIndex={0}
          aria-label="Close reviews"
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setShowReviews(false); }}
        >
          <div
            className="reviews-popout-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="reviews-popout-close"
              onClick={() => setShowReviews(false)}
              aria-label="Close"
            >
              ×
            </button>

            <div className="reviews-popout-left">
              <div className="shoe-card reviews-popout-card">
                <ShoeImage src={shoe.image} alt={shoe.model} />
                <h2>{shoe.model}</h2>
                <p><span className="brand-name">{shoe.brand}</span></p>
                <span className="retailers">Retailers</span>
                <ul>
                  {shoe.retailers.map((r, i) => (
                    <li key={i}>
                      <strong>{r.retailer}</strong>: {r.price}
                      {" — "}
                      <a href={r.link} target="_blank" rel="noopener noreferrer" className="buy-button">
                        Buy
                      </a>
                    </li>
                  ))}
                </ul>
                <PriceHistoryChart shoeModel={shoe.model} />
              </div>
            </div>

            <div className="reviews-popout-right">
              <h3>Community Reviews</h3>
              {loadingReviews ? (
                <p className="status-message status-message--loading">Loading reviews...</p>
              ) : !hasReviewData ? (
                <p className="status-message status-message--empty">
                  No community reviews yet for this shoe.
                </p>
              ) : (
                <ul className="reviews-list">
                  {reviews.slice(0, 5).map((review, i) => (
                    <li key={i} className="review-item">
                      <strong>{review.post_title}</strong>
                      <p className="review-summary">
                        {review.summary || (review.post_text ? review.post_text.substring(0, 200) + "…" : "")}
                      </p>
                      {review.pros && review.pros.length > 0 && (
                        <div className="review-pros">
                          <span className="review-pros-label">✓ Pros</span>
                          <ul>
                            {review.pros.map((pro, idx) => (
                              <li key={idx}>{pro}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {review.cons && review.cons.length > 0 && (
                        <div className="review-cons">
                          <span className="review-cons-label">✗ Cons</span>
                          <ul>
                            {review.cons.map((con, idx) => (
                              <li key={idx}>{con}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <a
                        href={review.post_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="review-link"
                      >
                        Read full review on Reddit →
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              <SimilarShoes shoeModel={shoe.model} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function CompareModal({ shoes, onClose }) {
  const [reviewsData, setReviewsData] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAllReviews = async () => {
      const results = {};
      await Promise.all(
        shoes.map(async (shoe) => {
          try {
            const res = await fetch(
              `${API_BASE_URL}/reviews?shoe_model=${encodeURIComponent(shoe.model)}`
            );
            const data = await res.json();
            results[shoe.model] = Array.isArray(data) ? data : [];
          } catch {
            results[shoe.model] = [];
          }
        })
      );
      setReviewsData(results);
      setLoading(false);
    };
    fetchAllReviews();
  }, [shoes]);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Aggregate pros/cons from reviews
  const aggregateReviews = (shoeModel) => {
    const reviews = reviewsData[shoeModel] || [];
    const allPros = [];
    const allCons = [];
    reviews.forEach((r) => {
      if (r.pros) allPros.push(...r.pros);
      if (r.cons) allCons.push(...r.cons);
    });
    // Dedupe and limit
    const uniquePros = [...new Set(allPros)].slice(0, 5);
    const uniqueCons = [...new Set(allCons)].slice(0, 5);
    return { pros: uniquePros, cons: uniqueCons, count: reviews.length };
  };

  return (
    <div
      className="compare-modal-overlay"
      onClick={onClose}
      role="button"
      tabIndex={0}
      aria-label="Close comparison"
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClose();
      }}
    >
      <div className="compare-modal" onClick={(e) => e.stopPropagation()}>
        <button className="compare-modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h2 className="compare-modal-title">Compare Shoes</h2>

        {loading ? (
          <p className="status-message status-message--loading">Loading comparison data...</p>
        ) : (
          <div className="compare-grid">
            {shoes.map((shoe) => {
              const { pros, cons, count } = aggregateReviews(shoe.model);
              const minPrice = getMinPrice(shoe);
              return (
                <div key={shoe.model} className="compare-column">
                  <ShoeImage src={shoe.image} alt={shoe.model} />
                  <h3>{shoe.model}</h3>
                  <p className="compare-brand">{shoe.brand}</p>

                  <div className="compare-section">
                    <span className="compare-label">Best Price</span>
                    <span className="compare-price">
                      {minPrice === Infinity ? "N/A" : `$${minPrice.toFixed(2)}`}
                    </span>
                  </div>

                  <div className="compare-section">
                    <span className="compare-label">Reviews</span>
                    <span>{count} community review{count !== 1 ? "s" : ""}</span>
                  </div>

                  {pros.length > 0 && (
                    <div className="compare-section">
                      <span className="compare-label compare-label--pros">Pros</span>
                      <ul className="compare-pros-list">
                        {pros.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {cons.length > 0 && (
                    <div className="compare-section">
                      <span className="compare-label compare-label--cons">Cons</span>
                      <ul className="compare-cons-list">
                        {cons.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="compare-retailers">
                    <span className="compare-label">Retailers</span>
                    {shoe.retailers.map((r, i) => (
                      <div key={i} className="compare-retailer-row">
                        <span>{r.retailer}</span>
                        <span>{r.price}</span>
                        <a
                          href={r.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="buy-button"
                        >
                          Buy
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ChatPanel({ onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hi! I'm ShoeScout AI 👟 Tell me what you're looking for — running style, foot type, budget, distance — and I'll find the best match from our database.",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || thinking) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setThinking(true);

    try {
      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.response || "Sorry, I couldn't find an answer." },
      ]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Something went wrong. Please try again." },
      ]);
    } finally {
      setThinking(false);
    }
  }, [input, thinking]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-panel-header">
        <span>🤖 ShoeScout AI</span>
        <button onClick={onClose} aria-label="Close chat">×</button>
      </div>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`chat-message chat-message--${msg.role}`}
          >
            {msg.text}
          </div>
        ))}
        {thinking && (
          <div className="chat-message chat-message--thinking">
            Thinking…
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          type="text"
          placeholder="e.g. daily trainer for wide feet under $150"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={thinking}
        />
        <button
          className="chat-send-btn"
          onClick={sendMessage}
          disabled={thinking || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}

function FilterSidebar({
  allBrands,
  allRetailers,
  selectedBrands,
  setSelectedBrands,
  selectedRetailers,
  setSelectedRetailers,
  selectedGender,
  setSelectedGender,
  selectedCategory,
  selectedSize,
  setSelectedSize,
  selectedWidth,
  setSelectedWidth,
  minDiscount,
  setMinDiscount,
  priceRange,
  setPriceRange,
  maxPrice,
  sortOption,
  setSortOption,
  onClearFilters,
  apiBrands = [],
}) {
  const handleBrandToggle = (brand) => {
    setSelectedBrands((prev) =>
      prev.includes(brand) ? prev.filter((b) => b !== brand) : [...prev, brand]
    );
  };

  const handleRetailerToggle = (retailer) => {
    setSelectedRetailers((prev) =>
      prev.includes(retailer) ? prev.filter((r) => r !== retailer) : [...prev, retailer]
    );
  };

  const hasActiveFilters =
    selectedBrands.length > 0 ||
    selectedRetailers.length > 0 ||
    selectedGender !== null ||
    selectedCategory !== null ||
    selectedSize !== "" ||
    selectedWidth !== "" ||
    minDiscount > 0 ||
    priceRange[0] > 0 ||
    priceRange[1] < maxPrice;

  return (
    <aside className="filter-sidebar">
      <div className="filter-header">
        <h3>Filters</h3>
        {hasActiveFilters && (
          <button className="clear-filters-btn" onClick={onClearFilters}>
            Clear all
          </button>
        )}
      </div>

      {/* Gender toggle */}
      <div className="filter-section">
        <h4>Gender</h4>
        <div className="gender-pills">
          <button 
            className={`gender-pill ${selectedGender === 'mens' ? 'active' : ''}`}
            onClick={() => setSelectedGender(selectedGender === 'mens' ? null : 'mens')}
          >
            👟 Men's
          </button>
          <button 
            className={`gender-pill ${selectedGender === 'womens' ? 'active' : ''}`}
            onClick={() => setSelectedGender(selectedGender === 'womens' ? null : 'womens')}
          >
            👟 Women's
          </button>
        </div>
      </div>

      {/* Size */}
      <div className="filter-section">
        <h4>Size</h4>
        <select
          className="sort-select"
          value={selectedSize}
          onChange={(e) => setSelectedSize(e.target.value)}
        >
          <option value="">Any size</option>
          {SIZE_OPTIONS.filter(Boolean).map((size) => (
            <option key={size} value={size}>{size}</option>
          ))}
        </select>
      </div>

      {/* Width */}
      <div className="filter-section">
        <h4>Width</h4>
        <select
          className="sort-select"
          value={selectedWidth}
          onChange={(e) => setSelectedWidth(e.target.value)}
        >
          {WIDTH_OPTIONS.map((option) => (
            <option key={option.value || "any"} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Minimum Discount */}
      <div className="filter-section">
        <h4>Minimum Discount</h4>
        <div className="discount-summary">
          <span className="discount-summary-value">{minDiscount}%</span>
          <span className="discount-summary-label">off or more</span>
        </div>
        <div className="price-slider-container">
          <input
            type="range"
            min="0"
            max="80"
            value={minDiscount}
            onChange={(e) => setMinDiscount(Number(e.target.value))}
            className="price-slider"
          />
        </div>
      </div>

      {/* Sort */}
      <div className="filter-section">
        <h4>Sort by</h4>
        <select
          className="sort-select"
          value={sortOption}
          onChange={(e) => setSortOption(e.target.value)}
        >
          <option value="relevance">Relevance</option>
          <option value="price-low">Price: Low to High</option>
          <option value="price-high">Price: High to Low</option>
          <option value="reviews">Most Reviews</option>
        </select>
      </div>

      {/* Price Range */}
      <div className="filter-section">
        <h4>Price Range</h4>
        <div className="price-range-inputs">
          <span>${priceRange[0]}</span>
          <span>-</span>
          <span>${priceRange[1] >= maxPrice ? `${maxPrice}+` : priceRange[1]}</span>
        </div>
        <div className="price-slider-container">
          <input
            type="range"
            min="0"
            max={maxPrice}
            value={priceRange[0]}
            onChange={(e) =>
              setPriceRange([Math.min(Number(e.target.value), priceRange[1] - 10), priceRange[1]])
            }
            className="price-slider"
          />
          <input
            type="range"
            min="0"
            max={maxPrice}
            value={priceRange[1]}
            onChange={(e) =>
              setPriceRange([priceRange[0], Math.max(Number(e.target.value), priceRange[0] + 10)])
            }
            className="price-slider"
          />
        </div>
      </div>

      {/* Brand Filter */}
      <div className="filter-section">
        <h4>Brand</h4>
        <div className="filter-checkboxes">
          {allBrands.map((brand) => {
            const brandData = apiBrands?.find(b => b.brand === brand);
            return (
              <label key={brand} className="filter-checkbox">
                <input
                  type="checkbox"
                  checked={selectedBrands.includes(brand)}
                  onChange={() => handleBrandToggle(brand)}
                />
                <span>{brand}</span>
                {brandData?.model_count && (
                  <span className="filter-count">({brandData.model_count})</span>
                )}
              </label>
            );
          })}
        </div>
      </div>

      {/* Retailer Filter */}
      <div className="filter-section">
        <h4>Retailer</h4>
        <div className="filter-checkboxes">
          {allRetailers.map((retailer) => (
            <label key={retailer} className="filter-checkbox">
              <input
                type="checkbox"
                checked={selectedRetailers.includes(retailer)}
                onChange={() => handleRetailerToggle(retailer)}
              />
              <span>{retailer}</span>
            </label>
          ))}
        </div>
      </div>
    </aside>
  );
}

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [shoes, setShoes] = useState([]);
  const [allShoes, setAllShoes] = useState([]); // Keep original list for filters
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const debounceRef = useRef(null);

  // Pagination state
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalShoes, setTotalShoes] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  // Deals state
  const [deals, setDeals] = useState([]);
  const [showDeals, setShowDeals] = useState(false);

  // Filter state
  const [selectedBrands, setSelectedBrands] = useState([]);
  const [selectedRetailers, setSelectedRetailers] = useState([]);
  const [selectedGender, setSelectedGender] = useState(null); // null, 'mens', or 'womens'
  const [selectedCategory, setSelectedCategory] = useState(null); // null, 'road', or 'trail'
  const [selectedSize, setSelectedSize] = useState("");
  const [selectedWidth, setSelectedWidth] = useState("");
  const [minDiscount, setMinDiscount] = useState(0);
  const [priceRange, setPriceRange] = useState([0, 300]);
  const [sortOption, setSortOption] = useState("relevance");

  // Compare state
  const [compareShoes, setCompareShoes] = useState([]);
  const [showCompareModal, setShowCompareModal] = useState(false);

  // Mobile filter toggle
  const [showFilters, setShowFilters] = useState(false);

  // Brands from API
  const [apiBrands, setApiBrands] = useState([]);

  // Derived data
  const allBrands = useMemo(() => {
    if (apiBrands.length > 0) return apiBrands.map(b => b.brand).filter(Boolean);
    return getUniqueBrands(allShoes);
  }, [apiBrands, allShoes]);
  const allRetailers = useMemo(() => getUniqueRetailers(allShoes), [allShoes]);
  const maxPrice = 300;

  const buildCatalogQuery = useCallback((pageNumber = 1) => {
    const params = new URLSearchParams({
      page: String(pageNumber),
      limit: "24",
    });

    if (selectedGender) params.set("gender", selectedGender);
    if (selectedCategory) params.set("category", selectedCategory);
    if (selectedSize) params.set("size", selectedSize);
    if (selectedWidth) params.set("width", selectedWidth);
    if (minDiscount > 0) params.set("min_discount", String(minDiscount));
    if (selectedBrands.length > 0) params.set("brand", selectedBrands[0]);
    if (selectedRetailers.length > 0) params.set("retailer", selectedRetailers[0]);

    return params.toString();
  }, [
    selectedGender,
    selectedCategory,
    selectedSize,
    selectedWidth,
    minDiscount,
    selectedBrands,
    selectedRetailers,
  ]);

  const fetchCatalogPage = useCallback(async (pageNumber = 1, append = false) => {
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setError(null);
    }

    try {
      const res = await fetch(`${API_BASE_URL}/shoes?${buildCatalogQuery(pageNumber)}`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      const shoeData = data.shoes || (Array.isArray(data) ? data : []);

      setShoes((prev) => (append ? [...prev, ...shoeData] : shoeData));
      setAllShoes((prev) => (append ? [...prev, ...shoeData] : shoeData));
      setTotalPages(data.total_pages || 1);
      setTotalShoes(data.total || shoeData.length);
      setPage(pageNumber);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch shoes:", err);
      setError("Could not connect to the server. Please try again shortly.");
    } finally {
      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  }, [buildCatalogQuery]);

  // Fetch brands from API
  useEffect(() => {
    fetch(`${API_BASE_URL}/brands`)
      .then((res) => res.json())
      .then((data) => {
        if (data.brands) setApiBrands(data.brands);
      })
      .catch(() => {});
  }, []);

  // Fetch deals
  useEffect(() => {
    fetch(`${API_BASE_URL}/deals?limit=20`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) setDeals(data);
      })
      .catch(() => {});
  }, []);

  // Fetch shoes with pagination on initial load
  useEffect(() => {
    if (searchTerm.trim()) return;
    fetchCatalogPage(1, false);
  }, [fetchCatalogPage, searchTerm]);

  // Load more shoes
  const loadMore = useCallback(() => {
    if (loadingMore || page >= totalPages || searchTerm.trim()) return;
    const nextPage = page + 1;
    fetchCatalogPage(nextPage, true);
  }, [page, totalPages, loadingMore, searchTerm, fetchCatalogPage]);

  // Debounced search: wait 300ms after user stops typing before fetching
  useEffect(() => {
    clearTimeout(debounceRef.current);
    const q = searchTerm.trim();
    if (!q) return undefined;

    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(q)}`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          const shoeData = Array.isArray(data) ? data : [];
          setShoes(shoeData);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Search failed:", err);
          setError(`Search failed: ${err.message}`);
          setLoading(false);
          setShoes([]);
        });
    }, 300);

    return () => clearTimeout(debounceRef.current);
  }, [searchTerm]);

  // Apply filters and sorting
  const filteredAndSortedShoes = useMemo(() => {
    let result = [...shoes];

    // Filter by brand
    if (selectedBrands.length > 0) {
      result = result.filter((s) => selectedBrands.includes(s.brand));
    }

    // Filter by retailer
    if (selectedRetailers.length > 0) {
      result = result.filter((s) =>
        s.retailers?.some((r) => selectedRetailers.includes(r.retailer))
      );
    }

    // Filter by price range
    result = result.filter((s) => {
      const minPrice = getMinPrice(s);
      if (minPrice === Infinity) return true; // Keep shoes without price info
      return minPrice >= priceRange[0] && minPrice <= priceRange[1];
    });

    // Filter by gender (local filter for consistency)
    if (selectedGender) {
      result = result.filter((s) => {
        if (!s.gender) return true; // Keep if no gender info
        if (selectedGender === 'mens') return s.gender.toLowerCase().startsWith('men');
        if (selectedGender === 'womens') return s.gender.toLowerCase().startsWith('women');
        return true;
      });
    }

    if (selectedCategory) {
      result = result.filter((shoe) => {
        if (!shoe.category) return true;
        return shoe.category.toLowerCase() === selectedCategory;
      });
    }

    if (selectedSize) {
      result = result.filter((shoe) => shoeHasMatchingSize(shoe, selectedSize));
    }

    if (selectedWidth) {
      result = result.filter((shoe) => shoeHasMatchingWidth(shoe, selectedWidth));
    }

    if (minDiscount > 0) {
      result = result.filter((shoe) => getDiscountPercent(shoe) >= minDiscount);
    }

    // Sort
    switch (sortOption) {
      case "price-low":
        result.sort((a, b) => getMinPrice(a) - getMinPrice(b));
        break;
      case "price-high":
        result.sort((a, b) => getMinPrice(b) - getMinPrice(a));
        break;
      case "reviews":
        // We don't have review count readily available, so sort by retailer count as proxy
        result.sort((a, b) => (b.retailers?.length || 0) - (a.retailers?.length || 0));
        break;
      default:
        // relevance - keep original order from API
        break;
    }

    return result;
  }, [
    shoes,
    selectedBrands,
    selectedRetailers,
    selectedGender,
    selectedCategory,
    selectedSize,
    selectedWidth,
    minDiscount,
    priceRange,
    sortOption,
  ]);

  // Compare handlers
  const handleCompareToggle = useCallback((shoe) => {
    setCompareShoes((prev) => {
      const exists = prev.find((s) => s.model === shoe.model);
      if (exists) {
        return prev.filter((s) => s.model !== shoe.model);
      }
      if (prev.length >= 3) return prev;
      return [...prev, shoe];
    });
  }, []);

  const clearFilters = useCallback(() => {
    setSelectedBrands([]);
    setSelectedRetailers([]);
    setSelectedGender(null);
    setSelectedCategory(null);
    setSelectedSize("");
    setSelectedWidth("");
    setMinDiscount(0);
    setPriceRange([0, 300]);
    setSortOption("relevance");
  }, [maxPrice]);

  const handleSuggestedSearch = useCallback((term) => {
    setSearchTerm(term);
  }, []);

  const renderContent = () => {
    if (error) {
      return <p className="status-message status-message--error">{error}</p>;
    }
    if (loading) {
      return (
        <div className="skeleton-grid">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="skeleton-card" />
          ))}
        </div>
      );
    }

    // Show deals view
    if (showDeals && deals.length > 0) {
      return (
        <>
          <div className="shoe-grid">
            {deals.map((shoe) => (
              <div key={shoe.model} className="shoe-card-wrapper">
                <div className="shoe-card deal-card">
                  <div className="deal-badge">
                    {shoe.deal_info.discount_percent}% OFF
                  </div>
                  <ShoeImage src={shoe.image} alt={shoe.model} />
                  <h2>{shoe.model}</h2>
                  <p><span className="brand-name">{shoe.brand}</span></p>
                  <div className="deal-price-info">
                    <span className="deal-current-price">${shoe.deal_info.current_price.toFixed(2)}</span>
                    <span className="deal-avg-price">Avg: ${shoe.deal_info.average_price}</span>
                  </div>
                  <p className="deal-retailer">at {shoe.deal_info.retailer}</p>
                  {shoe.retailers?.map((r, i) => (
                    r.retailer === shoe.deal_info.retailer && (
                      <a key={i} href={r.link} target="_blank" rel="noopener noreferrer" className="buy-button deal-buy">
                        Buy Now
                      </a>
                    )
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      );
    }

    if (filteredAndSortedShoes.length === 0) {
      return (
        <div className="empty-state">
          <div className="empty-state-icon">👟</div>
          <h3>No shoes found</h3>
          <p>
            {searchTerm.trim()
              ? `We couldn't find any shoes matching "${searchTerm}".`
              : "No shoes match your current filters."}
          </p>
          <div className="empty-state-suggestions">
            <p>Try one of these popular searches:</p>
            <div className="suggestion-chips">
              {POPULAR_SHOES.map((shoe) => (
                <button
                  key={shoe}
                  className="suggestion-chip"
                  onClick={() => handleSuggestedSearch(shoe)}
                >
                  {shoe}
                </button>
              ))}
            </div>
          </div>
          {(selectedBrands.length > 0 || selectedRetailers.length > 0 || selectedGender || selectedCategory || selectedSize || selectedWidth || minDiscount > 0 || priceRange[0] > 0 || priceRange[1] < maxPrice) && (
            <button className="clear-filters-btn-large" onClick={clearFilters}>
              Clear all filters
            </button>
          )}
        </div>
      );
    }
    return (
      <>
        <div className="shoe-grid">
          {filteredAndSortedShoes.map((shoe) => (
            <ShoeCard
              key={shoe.model}
              shoe={shoe}
              onCompareToggle={handleCompareToggle}
              isCompareSelected={compareShoes.some((s) => s.model === shoe.model)}
              compareCount={compareShoes.length}
            />
          ))}
        </div>
        {!searchTerm.trim() && page < totalPages && (
          <button
            className="load-more-btn"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? "Loading..." : `Load More (${shoes.length} of ${totalShoes})`}
          </button>
        )}
      </>
    );
  };

  return (
    <div className="app">
      <div className="header">
        <div className="header-title">
          <h1>ShoeScout</h1>
        </div>
        <p className="header-tagline">Find the best deals on running shoes from 15+ retailers</p>
        <p className="header-updated">Prices updated every 6 hours · AI-powered search · Reddit community reviews</p>

        {/* Deals toggle */}
        {deals.length > 0 && (
          <button
            className={`deals-toggle ${showDeals ? 'deals-toggle--active' : ''}`}
            onClick={() => setShowDeals(!showDeals)}
          >
            {showDeals ? '← Back to All Shoes' : `🔥 ${deals.length} Hot Deals`}
          </button>
        )}

        <input
          type="text"
          id="search-input"
          name="search"
          placeholder='Search by model, brand, or "daily trainer for long runs"'
          value={searchTerm}
          onChange={(e) => { setSearchTerm(e.target.value); setShowDeals(false); }}
          className="search-bar"
          autoComplete="off"
        />

        {/* Category Tabs */}
        <div className="category-tabs">
          <button 
            className={`category-tab ${selectedCategory === null ? 'active' : ''}`}
            onClick={() => setSelectedCategory(null)}
          >
            All Shoes
          </button>
          <button 
            className={`category-tab ${selectedCategory === 'road' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('road')}
          >
            🏢 Road
          </button>
          <button 
            className={`category-tab ${selectedCategory === 'trail' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('trail')}
          >
            ⛰️ Trail
          </button>
        </div>
        {/* Mobile filter toggle */}
        <button
          className="mobile-filter-toggle"
          onClick={() => setShowFilters((prev) => !prev)}
        >
          {showFilters ? "Hide Filters" : "Show Filters"}
        </button>
      </div>

      <div className="app-layout">
        {/* Filter Sidebar */}
        <FilterSidebar
          allBrands={allBrands}
          allRetailers={allRetailers}
          selectedBrands={selectedBrands}
          setSelectedBrands={setSelectedBrands}
          selectedRetailers={selectedRetailers}
          setSelectedRetailers={setSelectedRetailers}
          selectedGender={selectedGender}
          setSelectedGender={setSelectedGender}
          selectedCategory={selectedCategory}
          selectedSize={selectedSize}
          setSelectedSize={setSelectedSize}
          selectedWidth={selectedWidth}
          setSelectedWidth={setSelectedWidth}
          minDiscount={minDiscount}
          setMinDiscount={setMinDiscount}
          priceRange={priceRange}
          setPriceRange={setPriceRange}
          maxPrice={maxPrice}
          sortOption={sortOption}
          setSortOption={setSortOption}
          onClearFilters={clearFilters}
          apiBrands={apiBrands}
        />

        {/* Mobile Filters (overlay) */}
        {showFilters && (
          <div className="mobile-filter-overlay" onClick={() => setShowFilters(false)}>
            <div className="mobile-filter-panel" onClick={(e) => e.stopPropagation()}>
              <div className="mobile-filter-header">
                <h3>Filters & Sort</h3>
                <button onClick={() => setShowFilters(false)}>×</button>
              </div>
              <FilterSidebar
                allBrands={allBrands}
                allRetailers={allRetailers}
                selectedBrands={selectedBrands}
                setSelectedBrands={setSelectedBrands}
                selectedRetailers={selectedRetailers}
                setSelectedRetailers={setSelectedRetailers}
                selectedGender={selectedGender}
                setSelectedGender={setSelectedGender}
                selectedCategory={selectedCategory}
                selectedSize={selectedSize}
                setSelectedSize={setSelectedSize}
                selectedWidth={selectedWidth}
                setSelectedWidth={setSelectedWidth}
                minDiscount={minDiscount}
                setMinDiscount={setMinDiscount}
                priceRange={priceRange}
                setPriceRange={setPriceRange}
                maxPrice={maxPrice}
                sortOption={sortOption}
                setSortOption={setSortOption}
                onClearFilters={clearFilters}
                apiBrands={apiBrands}
              />
              <button
                className="mobile-filter-apply"
                onClick={() => setShowFilters(false)}
              >
                Apply Filters
              </button>
            </div>
          </div>
        )}

        <div className="app-container">
          {/* Results count */}
          {!loading && !error && (
            <div className="results-count">
              {showDeals
                ? `${deals.length} deal${deals.length !== 1 ? "s" : ""} available`
                : `${filteredAndSortedShoes.length} shoe${filteredAndSortedShoes.length !== 1 ? "s" : ""} found${!searchTerm.trim() && totalShoes > shoes.length ? ` (${totalShoes} total)` : ""}`
              }
            </div>
          )}
          {renderContent()}
        </div>
      </div>

      {/* Compare Bar */}
      {compareShoes.length > 0 && (
        <div className="compare-bar">
          <div className="compare-bar-items">
            {compareShoes.map((shoe) => (
              <div key={shoe.model} className="compare-bar-item">
                <span>{shoe.model}</span>
                <button
                  onClick={() => handleCompareToggle(shoe)}
                  aria-label={`Remove ${shoe.model} from comparison`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <button
            className="compare-bar-button"
            onClick={() => setShowCompareModal(true)}
            disabled={compareShoes.length < 2}
          >
            Compare ({compareShoes.length}/3)
          </button>
          <button
            className="compare-bar-clear"
            onClick={() => setCompareShoes([])}
          >
            Clear
          </button>
        </div>
      )}

      {/* Compare Modal */}
      {showCompareModal && compareShoes.length >= 2 && (
        <CompareModal
          shoes={compareShoes}
          onClose={() => setShowCompareModal(false)}
        />
      )}

      {/* AI Chat */}
      {showChat && <ChatPanel onClose={() => setShowChat(false)} />}
      <button
        className="chat-fab"
        onClick={() => setShowChat((prev) => !prev)}
        aria-label="Open AI shoe assistant"
      >
        🤖 Ask AI
      </button>
    </div>
  );
}

export default App;
