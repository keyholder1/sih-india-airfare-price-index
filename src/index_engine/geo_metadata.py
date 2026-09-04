"""City coordinate reference data for map-style visualizations only.

Deliberately kept separate from every statistical calculation in this
package — coordinates never enter an index, weight, or volatility formula.
Values are standard public airport-city coordinates (approximate city
centers), not measured or fitted data.
"""

from __future__ import annotations

from typing import Dict, Tuple

# IATA code -> (latitude, longitude)
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "BLR": (12.9716, 77.5946),  # Bengaluru
    "DEL": (28.6139, 77.2090),  # Delhi
    "BOM": (19.0760, 72.8777),  # Mumbai
    "HYD": (17.3850, 78.4867),  # Hyderabad
    "MAA": (13.0827, 80.2707),  # Chennai
    "CCU": (22.5726, 88.3639),  # Kolkata
    # Added for route-coverage-expansion analysis (top-100 DGCA routes).
    "PNQ": (18.5204, 73.8567),  # Pune
    "AMD": (23.0225, 72.5714),  # Ahmedabad
    "SXR": (34.0837, 74.7973),  # Srinagar
    "GAU": (26.1445, 91.7362),  # Guwahati
    "PAT": (25.5941, 85.1376),  # Patna
    "COK": (9.9312, 76.2673),   # Kochi
    "LKO": (26.8467, 80.9462),  # Lucknow
    "IXC": (30.7333, 76.7794),  # Chandigarh
    "VNS": (25.3176, 82.9739),  # Varanasi
    "IXR": (23.3441, 85.3096),  # Ranchi
    "IDR": (22.7196, 75.8577),  # Indore
    "RPR": (21.2514, 81.6296),  # Raipur
    "BBI": (20.2961, 85.8245),  # Bhubaneswar
    "CJB": (11.0168, 76.9558),  # Coimbatore
    "ATQ": (31.6340, 74.8723),  # Amritsar
    "IXA": (23.8315, 91.2868),  # Agartala
    "IXB": (26.6812, 88.3286),  # Bagdogra
    "IXL": (34.1642, 77.5850),  # Leh
    "GOI": (15.3808, 73.8314),  # Goa (Dabolim)
    "TRV": (8.4821, 76.9200),   # Thiruvananthapuram (Trivandrum)
    "IXE": (12.9141, 74.8560),  # Mangaluru (Mangalore)
}
