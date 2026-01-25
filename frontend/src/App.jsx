import "./App.css";
import { useState, useEffect } from "react";

function App() {
  const [searchTerm, setSearchTerm] = useState("");
  const [shoes, setShoes] = useState([]);
  const [loading, setLoading] = useState(false);

  // Fetch all shoes on initial load
  useEffect(() => {
    fetch("https://shoescout.onrender.com/shoes")
      .then((res) => res.json())
      .then((data) => setShoes(data))
      .catch((err) => console.error("Failed to fetch shoes:", err));
  }, []);

  // Semantic search when user types
  useEffect(() => {
    if (searchTerm.trim() === "") {
      // If search is empty, fetch all shoes
      fetch("https://shoescout.onrender.com/shoes")
        .then((res) => res.json())
        .then((data) => setShoes(data))
        .catch((err) => console.error("Failed to fetch shoes:", err));
      return;
    }

    setLoading(true);
    // Call semantic search endpoint
    fetch(`https://shoescout.onrender.com/search?q=${encodeURIComponent(searchTerm)}`)
      .then((res) => res.json())
      .then((data) => {
        setShoes(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to search shoes:", err);
        setLoading(false);
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
          {loading && (
            <p
              style={{ textAlign: "center", fontSize: "1.2rem", color: "#666" }}
            >
              Searching...
            </p>
          )}
          {!loading && shoes.length === 0 && (
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
