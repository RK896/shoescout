import "./App.css";
import { useState, useEffect } from "react";

// API base URL - change to "http://localhost:8000" for local development
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ShoeCard component to display individual shoe with reviews
function ShoeCard({ shoe }) {
  const [reviews, setReviews] = useState([]);
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [isFlipped, setIsFlipped] = useState(false);

  useEffect(() => {
    // Fetch reviews for this shoe
    setLoadingReviews(true);
    fetch(`${API_BASE_URL}/reviews/${encodeURIComponent(shoe.model)}`)
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

  const handleCardClick = () => {
    if (reviews.length > 0) {
      setIsFlipped(!isFlipped);
    }
  };

  return (
    <div 
      className={`shoe-card-container ${isFlipped ? 'flipped' : ''}`}
      onClick={handleCardClick}
      style={{ cursor: reviews.length > 0 ? 'pointer' : 'default' }}
    >
      <div className="shoe-card-inner">
        {/* Front of card */}
        <div className="shoe-card-front">
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
                <a 
                  href={r.link} 
                  target="_blank" 
                  className="buy-button"
                  onClick={(e) => e.stopPropagation()}
                >
                  Buy
                </a>
              </li>
            ))}
          </ul>
          {reviews.length > 0 && (
            <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "#666" }}>
              💬 {reviews.length} review{reviews.length !== 1 ? 's' : ''} - Click to see
            </p>
          )}
        </div>

        {/* Back of card - Reviews */}
        <div className="shoe-card-back">
          <h2>{shoe.model}</h2>
          <strong className="retailers">What People Say</strong>
          {loadingReviews ? (
            <p>Loading reviews...</p>
          ) : reviews.length > 0 ? (
            <ul style={{ maxHeight: "400px", overflowY: "auto", fontSize: "0.9rem", textAlign: "left" }}>
              {reviews.slice(0, 3).map((review, i) => (
                <li key={i} style={{ marginBottom: "1rem", paddingBottom: "1rem", borderBottom: i < reviews.length - 1 ? "1px solid #eee" : "none" }}>
                  <strong>{review.post_title}</strong>
                  <br />
                  <span style={{ color: "#666" }}>
                    {review.post_text.substring(0, 200)}
                    {review.post_text.length > 200 ? "..." : ""}
                  </span>
                  <br />
                  <a 
                    href={review.post_url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    style={{ fontSize: "0.8rem", color: "#0066cc" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    Read more on Reddit →
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p>No reviews yet</p>
          )}
          <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "#666" }}>
            Click to flip back
          </p>
        </div>
      </div>
    </div>
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

  // Semantic search when user types
  useEffect(() => {
    if (searchTerm.trim() === "") {
      // If search is empty, fetch all shoes
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
          setError("Failed to load shoes.");
        });
      return;
    }

    setLoading(true);
    setError(null);
    // Call semantic search endpoint
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
