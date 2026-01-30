import "./App.css";
import { useState, useEffect } from "react";

// API base URL - change to "http://localhost:8000" for local development
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ShoeCard component to display individual shoe with reviews
function ShoeCard({ shoe }) {
  const [reviews, setReviews] = useState([]);
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [showReviews, setShowReviews] = useState(false);

  useEffect(() => {
    // Fetch reviews for this shoe (query param avoids 404 when model has "/" e.g. S/Lab)
    setLoadingReviews(true);
    fetch(`${API_BASE_URL}/reviews?shoe_model=${encodeURIComponent(shoe.model)}`)
      .then((res) => res.json())
      .then((data) => {
        setReviews(Array.isArray(data) ? data : []);
        setLoadingReviews(false);
      })
      .catch((err) => {
        console.error("Failed to fetch reviews:", err);
        setLoadingReviews(false);
      });
  }, [shoe.model]);

  return (
    <>
      <div className="shoe-card-wrapper">
        <div className="shoe-card">
          <img src={shoe.image} alt={shoe.model} className="shoe-img" />
          <h2>{shoe.model}</h2>
          <p>
            <strong className="brand-name">Brand:</strong> {shoe.brand}
          </p>
          <p>
            <strong className="retailers">Retailers</strong>
          </p>
          <ul>
            {shoe.retailers.map((r, i) => (
              <li key={i}>
                <strong>{r.retailer}</strong>: {r.price} -{" "}
                <a href={r.link} target="_blank" className="buy-button">
                  Buy
                </a>
              </li>
            ))}
          </ul>
          
          {reviews.length > 0 && (
            <button 
              className="reviews-toggle-button"
              onClick={() => setShowReviews(true)}
            >
              💬 {reviews.length} review{reviews.length !== 1 ? 's' : ''}
            </button>
          )}
        </div>
      </div>

      {/* Pop-out overlay: left = shoe card, right = reviews */}
      {showReviews && reviews.length > 0 && (
        <div 
          className="reviews-popout-overlay" 
          onClick={() => setShowReviews(false)}
          role="button"
          tabIndex={0}
          aria-label="Close reviews"
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
                <img src={shoe.image} alt={shoe.model} className="shoe-img" />
                <h2>{shoe.model}</h2>
                <p>
                  <strong className="brand-name">Brand:</strong> {shoe.brand}
                </p>
                <p>
                  <strong className="retailers">Retailers</strong>
                </p>
                <ul>
                  {shoe.retailers.map((r, i) => (
                    <li key={i}>
                      <strong>{r.retailer}</strong>: {r.price} -{" "}
                      <a href={r.link} target="_blank" className="buy-button">
                        Buy
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            
            <div className="reviews-popout-right">
              <strong className="retailers">What People Say</strong>
              {loadingReviews ? (
                <p>Loading reviews...</p>
              ) : (
                <ul className="reviews-list">
                  {reviews.slice(0, 5).map((review, i) => (
                    <li key={i} className="review-item">
                      <strong>{review.post_title}</strong>
                      <br />
                      <span style={{ color: "#666" }}>
                        {review.summary || review.post_text.substring(0, 150) + "..."}
                      </span>
                      {review.pros && review.pros.length > 0 && (
                        <div style={{ marginTop: "10px" }}>
                          <strong style={{ color: "#4CAF50" }}>✓ Pros:</strong>
                          <ul style={{ margin: "5px 0", paddingLeft: "20px", color: "#4CAF50" }}>
                            {review.pros.map((pro, idx) => (
                              <li key={idx} style={{ fontSize: "0.9em" }}>{pro}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {review.cons && review.cons.length > 0 && (
                        <div style={{ marginTop: "10px" }}>
                          <strong style={{ color: "#f44336" }}>✗ Cons:</strong>
                          <ul style={{ margin: "5px 0", paddingLeft: "20px", color: "#f44336" }}>
                            {review.cons.map((con, idx) => (
                              <li key={idx} style={{ fontSize: "0.9em" }}>{con}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <br />
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
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [shoes, setShoes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch all shoes on initial load
  useEffect(() => {
    fetch(`${API_BASE_URL}/shoes`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setShoes(data);
        setError(null);
      })
      .catch((err) => {
        console.error("Failed to fetch shoes:", err);
        setError("Failed to load shoes. Make sure the backend server is running.");
      });
  }, []);

  // Search when user types: empty = all shoes, non-empty = search (semantic or text fallback)
  useEffect(() => {
    if (searchTerm.trim() === "") {
      // Clear search: reset to full list so UI doesn't stay on "those 10"
      setLoading(true);
      setError(null);
      fetch(`${API_BASE_URL}/shoes`)
        .then((res) => {
          if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
          }
          return res.json();
        })
        .then((data) => {
          setShoes(Array.isArray(data) ? data : []);
          setLoading(false);
          setError(null);
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
    fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(searchTerm)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setShoes(Array.isArray(data) ? data : []);
        setLoading(false);
        setError(null);
      })
      .catch((err) => {
        console.error("Failed to search shoes:", err);
        setError(`Search failed: ${err.message}`);
        setLoading(false);
        setShoes([]);
      });
  }, [searchTerm]);

  return (
    <div className="app">
      <div className="header">
        <div className="header-title">
          <img src="" alt="" />
          <h1>Shoe Scout</h1>
        </div>
        <h2>Find the best deals on running shoes!</h2>
        <h3>Updated Daily</h3>
        <input
          type="text"
          id="search-input"
          name="search"
          placeholder="Search by model, brand, or description (e.g., 'daily trainer for long runs')"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="search-bar"
        />
      </div>
      <div className="app-container">
        <div className="shoe-grid">
          {error && (
            <p
              style={{ textAlign: "center", fontSize: "1.2rem", color: "#ff4444" }}
            >
              {error}
            </p>
          )}
          {loading && !error && (
            <p
              style={{ textAlign: "center", fontSize: "1.2rem", color: "#666" }}
            >
              Searching...
            </p>
          )}
          {!loading && !error && shoes.length === 0 && (
            <p
              style={{ textAlign: "center", fontSize: "1.2rem", color: "#666" }}
            >
              No shoes found. Try a different search.
            </p>
          )}
          {!loading && shoes.map((shoe, index) => (
            <ShoeCard key={index} shoe={shoe} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default App;
