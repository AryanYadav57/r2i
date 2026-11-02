# 🌿 R2I Eco-Routing Engine: Evolution & Improvement Log

## 📌 Project Overview
The **Route-to-Impact (R2I) Engine** is an Intelligent Transportation System (ITS) designed to reduce urban air pollution by optimizing vehicle routes based on **thermodynamic engine efficiency** rather than just travel time or distance. By diverting Internal Combustion Engine (ICE) vehicles away from high-idling bottlenecks, the system reduces localized emissions and promotes the adoption of Electric Vehicles (EVs).

---

## 🚀 Major Improvements & Updates

### 1. Data & Mapping Evolution
*   **Synthetic $\rightarrow$ Real-World Data:** Transitioned from a basic 4-node simulated grid to a real-world topological map of **Koramangala, Bengaluru**, using `OSMnx` and `OpenStreetMap`.
*   **Landmark-Based Navigation:** Replaced technical Node IDs with a user-friendly **Landmark System**. Users can now select destinations like *Sony World Signal*, *Forum Mall*, and *Wipro Park*.
*   **Graph Pruning & Stability:** Implemented `weakly_connected_components` pruning to ensure the engine only operates on the main connected road network, eliminating the "Source not in G" errors.
*   **Bulletproof Node Matching:** Replaced library-dependent nearest-node searches with a **Manual Euclidean Search** to guarantee that selected landmarks always map to a valid, reachable node in the active network.

### 2. Physics & Routing Algorithm
*   **Google Maps Real-Time Integration:** Integrated the **Google Distance Matrix API** to fetch live traffic multipliers. The engine now adjusts "idling probabilities" based on actual current congestion in Bangalore.
*   **Advanced Vehicle Profiling:** Moved beyond a simple ICE/EV toggle to detailed profiles:
    *   **Economy Hatchback:** Low cruising burn, low idling cost.
    *   **Luxury SUV:** High cruising burn, high idling cost.
    *   **EV Scooter / Electric Car:** Zero point-of-use emissions.
*   **Thermodynamic Cost Model:** Implemented a multi-objective cost function that accounts for:
    *   **Cruising Cost:** Fuel burned during optimal movement.
    *   **Idling Penalty:** Fuel burned while stationary in traffic.
    *   **Acceleration Cost:** Added penalties for "Stop-and-Go" behavior at high-congestion intersections.
*   **Multi-Objective Optimization:** Added a **Route Priority Slider ($\alpha$)**, allowing users to balance the trade-off between "Absolute Greenest Route" and "Fastest Route."

### 3. Environmental & Economic Metrics
The engine now translates raw data into human-centric impact metrics:
*   **Economic Savings:** Calculates fuel savings in milliliters and converts them to **Indian Rupees (₹)** based on current Bangalore petrol prices.
*   **Carbon Footprint:** Calculates total $\text{CO}_2$ reduction in grams.
*   **Air Quality Impact:** Estimates the reduction of **PM2.5 (Particulate Matter)**, linking the software's output to public health.
*   **Nature Equivalence:** Implemented a "Tree-Day" metric, showing how many days of a mature tree's carbon absorption the trip saved.

### 4. UI/UX & Performance Overhaul
*   **Professional Dark Theme:** Implemented a high-contrast dark mode using custom CSS for a modern, "Command Center" aesthetic.
*   **Visual Route Contrast:**
    *   **Standard Route:** Rendered as a subtle gray dotted line.
    *   **Eco Route:** Rendered as a bold, vibrant dark green line.
*   **Traffic Heatmap:** Added a toggle to highlight the map's "bottlenecks" in Red, Orange, and Blue based on idling probability.
*   **State Management:** Integrated `st.session_state` to prevent page flashing and ensure that metrics remain synced with the map after calculation.
*   **Performance Optimization:** Optimized map rendering by only drawing high-congestion edges, reducing browser lag.

---

## 🛠️ Technical Stack
| Component | Technology |
| :--- | :--- |
| **Frontend** | Streamlit, Folium, Streamlit-Folium |
| **Routing Engine** | NetworkX, OSMnx |
| **Data Source** | OpenStreetMap (OSM) |
| **Traffic Intelligence** | Google Maps Distance Matrix API |
| **Language** | Python 3.11+ |

---

## 📈 Final Comparison: Prototype vs. Evolved Engine

| Feature | Original Prototype | Evolved R2I Engine |
| :--- | :--- | :--- |
| **Map Data** | 4-Node Synthetic Grid | Real Koramangala Topology |
| **Routing Logic** | Distance-based | Thermodynamic & Traffic-Aware |
| **Traffic** | Static/Random | Real-time Google Traffic API |
| **Vehicle Types** | ICE / EV | Profiled (SUV, Hatchback, etc.) |
| **Metrics** | Carbon $\text{CO}_2$ | ₹ Savings, PM2.5, Tree Equiv. |
| **UI** | Basic Streamlit | Professional Dark-Mode Dashboard |
| **UX** | Node ID selection | Landmark-based selection |
