import './App.css'
import { useState, useEffect } from 'react'

function App() {
  const [searchTerm, setSearchTerm] = useState("")
  const [shoes, setShoes] = useState([])

  const filteredShoes = shoes.filter(shoe =>
    shoe.model.toLowerCase().includes(searchTerm.toLowerCase()) ||
    shoe.brand.toLowerCase().includes(searchTerm.toLowerCase())
  )

  useEffect(() => {
    fetch("http://localhost:8000/shoes")
      .then(res => res.json())        
      .then(data => setShoes(data))
      .catch(err => console.error("Failed to fetch shoes:", err));  
  }, []);
  


  return (
    <div className='app-container'>
      <h1>ShoeScout 🏃‍♂️</h1>
      <h2>Find the best deals on running shoes!</h2>
      <input
        type="text" 
        id = "search-input"
        name = "search"
        placeholder='Search by model or brand'
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className='search-bar'
        />

      <div className='shoe-grid'>
        {filteredShoes.map((shoe, index) => (
          <div key = {index} className='shoe-card'>
            <img src={shoe.image} alt={shoe.model} className='shoe-img'/>
            <h2>{shoe.model}</h2>
            <p><strong>Brand:</strong> {shoe.brand}</p>
            <ul>
              {shoe.retailers.map((r,i) =>(
                <li key = {i}>
                  <strong>{r.retailer}</strong>: {r.price} - <a href={r.link} target = "_blank">Buy</a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
