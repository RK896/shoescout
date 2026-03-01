import "./App.css";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Popular shoes to suggest when no results found
const POPULAR_SHOES = [
  "Nike Pegasus 41",
  "ASICS Gel-Kayano 31",
  "Brooks Ghost 16",
  "Hoka Clifton 9",
  "New Balance Fresh Foam 1080v13",
];

// Keywords for "Best for" tags
const BEST_FOR_KEYWORDS = {
  marathon: ["marathon", "26.2", "long distance race"],
  trail: ["trail", "off-road", "hiking", "terrain"],
  "daily trainer": ["daily trainer", "everyday", "daily run", "rotation"],
  speed: ["speed", "tempo", "race day", "fast", "5k", "10k"],
  recovery: ["recovery", "easy run", "slow", "cushioned"],
  "long runs": ["long run", "high mileage", "endurance"],
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

function PriceHistory({ shoeModel }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/shoes/${encodeURIComponent(shoeModel)}/price-history`)
      .then((res) => res.json())
      .then((data) => {
        setHistory(data.price_history || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [shoeModel]);

  if (loading) return null;
  if (history.length === 0) return null;

  // Get min/max/avg prices
  const prices = history.map(h => h.price_value).filter(p => p && p !== Infinity);
  if (prices.length === 0) return null;

  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;

  return (
    <div className="price-history-section">
      <h4>Price Trends</h4>
      <div className="price-history-stats">
        <div className="price-stat">
          <span className="price-stat-label">Lowest</span>
          <span className="price-stat-value price-stat--low">${minPrice.toFixed(0)}</span>
        </div>
        <div className="price-stat">
          <span className="price-stat-label">Average</span>
          <span className="price-stat-value">${avgPrice.toFixed(0)}</span>
        </div>
        <div className="price-stat">
          <span className="price-stat-label">Highest</span>
          <span className="price-stat-value price-stat--high">${maxPrice.toFixed(0)}</span>
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

function ShoeCard({ shoe, onCompareToggle, isCompareSelected, compareCount }) {
  const [reviews, setReviews] = useState(null); // null = not loaded yet
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [showReviews, setShowReviews] = useState(false);
  const [bestForTags, setBestForTags] = useState([]);

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

          <button
            className="reviews-toggle-button"
            onClick={handleOpenReviews}
          >
            💬 Reviews
          </button>
        </div>
      </div>

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
                <PriceHistory shoeModel={shoe.model} />
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
    fetch(`${API_BASE_URL}/shoes?page=1&limit=24`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        // Handle new paginated response format
        const shoeData = data.shoes || (Array.isArray(data) ? data : []);
        setShoes(shoeData);
        setAllShoes(shoeData);
        setTotalPages(data.total_pages || 1);
        setTotalShoes(data.total || shoeData.length);
        setPage(1);
        setLoading(false);
        setError(null);
      })
      .catch((err) => {
        console.error("Failed to fetch shoes:", err);
        setError("Could not connect to the server. Please try again shortly.");
        setLoading(false);
      });
  }, []);

  // Load more shoes
  const loadMore = useCallback(() => {
    if (loadingMore || page >= totalPages || searchTerm.trim()) return;
    setLoadingMore(true);
    const nextPage = page + 1;
    fetch(`${API_BASE_URL}/shoes?page=${nextPage}&limit=24`)
      .then((res) => res.json())
      .then((data) => {
        const newShoes = data.shoes || [];
        setShoes((prev) => [...prev, ...newShoes]);
        setAllShoes((prev) => [...prev, ...newShoes]);
        setPage(nextPage);
        setLoadingMore(false);
      })
      .catch(() => setLoadingMore(false));
  }, [page, totalPages, loadingMore, searchTerm]);

  // Debounced search: wait 300ms after user stops typing before fetching
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const q = searchTerm.trim();

      if (q === "") {
        // Restore full list on clear
        setLoading(true);
        setError(null);
        fetch(`${API_BASE_URL}/shoes?page=1&limit=24`)
          .then((res) => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
          })
          .then((data) => {
            const shoeData = data.shoes || (Array.isArray(data) ? data : []);
            setShoes(shoeData);
            setAllShoes(shoeData);
            setTotalPages(data.total_pages || 1);
            setTotalShoes(data.total || shoeData.length);
            setPage(1);
            setLoading(false);
          })
          .catch((err) => {
            console.error("Failed to fetch shoes:", err);
            setError("Failed to load shoes.");
            setLoading(false);
          });
        return;
      }

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
  }, [shoes, selectedBrands, selectedRetailers, priceRange, sortOption]);

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
    setPriceRange([0, maxPrice]);
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
          {(selectedBrands.length > 0 || selectedRetailers.length > 0 || priceRange[0] > 0 || priceRange[1] < maxPrice) && (
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
        <p className="header-tagline">Find the best deals on running shoes</p>
        <p className="header-updated">Prices updated every 6 hours · Reviews from Reddit</p>

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
