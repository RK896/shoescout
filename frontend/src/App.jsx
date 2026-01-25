import "./App.css";
import { useState, useEffect } from "react";

// API base URL - change to "http://localhost:8000" for local development
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
            <div key={index} className="shoe-card">
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
          ))}
        </div>
      </div>
    </div>
  );
}

export default App;
