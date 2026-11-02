# Product Requirements Document (PRD)
**Project Title:** Route-to-Impact (R2I) Eco-Routing Engine
**Target Platform:** Web Dashboard (Streamlit)
**Status:** MVP Development (Smart India Hackathon Submission)

---

## 1. Executive Summary
The Route-to-Impact (R2I) Engine is an Intelligent Transportation Systems (ITS) routing algorithm. Unlike traditional GPS applications that strictly optimize for travel time or distance, R2I optimizes for **thermodynamic engine efficiency**. By evaluating urban bottlenecks, the engine dynamically reroutes Internal Combustion Engine (ICE) vehicles to minimize idling, thereby reducing localized air pollution. Simultaneously, it demonstrates the structural efficiency of Electric Vehicles (EVs) in congested grids, directly encouraging EV adoption.

## 2. Problem Statement & Elevator Pitch (SIH Alignment)

**The Elevator Pitch:**
Current navigation apps (like Google Maps) only optimize for the shortest time or distance. Because of this, they route thousands of petrol and diesel cars straight into massive traffic jams where engines sit idling—burning millions of liters of fuel without actually moving. R2I fixes this by routing vehicles based on **emissions cost** rather than just distance, diverting petrol cars away from high-idling bottlenecks to stop pollution at the source.

**SIH Problem Alignment:**
* **The Core Issue:** Rising air pollution in India is causing a rapid increase in chronic respiratory diseases. The idling vehicular emissions mentioned above are a primary contributor.
* **Government Goal:** The National Clean Air Programme (NCAP) requires actionable solutions to combat these emissions.
* **Our Intervention:** We provide a software-only spatial data solution that eases the adoption of EVs by mathematically proving their time and energy superiority in traffic, while actively reducing the fuel wasted by ICE vehicles.

## 3. Target Audience & Personas
1. **Daily Commuters:** Looking to reduce their carbon footprint and save money on wasted fuel in traffic.
2. **Logistics & Delivery Fleets:** Companies (like Zomato, Swiggy, Amazon) looking to optimize their delivery grids, transition to EV fleets, and reduce total fuel expenditure.
3. **Urban Planners & Government:** Policymakers evaluating city infrastructure and the impact of congestion on localized air quality.

---

## 4. Functional Requirements (FR)

### FR1: Geospatial Data Ingestion
* **Description:** The system must accurately map urban street networks.
* **Implementation:** Use `OSMnx` to fetch raw OpenStreetMap (OSM) topological data for a localized grid (e.g., a 5km radius in a major Indian city).

### FR2: Multi-Objective Routing Logic Core
* **Description:** The system must calculate paths based on custom environmental edge weights rather than just distance.
* **Implementation:** Utilize `NetworkX` to execute modified A* or Dijkstra pathfinding algorithms.

### FR3: Vehicle Propulsion Profiling
* **Description:** The routing engine must alter its pathing logic based on the physical engine type of the vehicle.
* **ICE Profile:** Must penalize routes with high predicted congestion (idling) by applying a carbon/fuel cost equation.
* **EV Profile:** Must disregard idle carbon penalties (as EVs have zero point-of-use emissions) and strictly optimize for time and kinetic energy efficiency.

### FR4: Interactive User Dashboard
* **Description:** A user interface allowing users to input parameters and view route comparisons.
* **Implementation:** Built using `Streamlit`. Must include:
  * Origin and Destination selectors.
  * Vehicle type toggle (ICE vs. EV).
  * Side-by-side metric display (Carbon Saved, Fuel Saved in mL, Time Delta).
  * A visual map rendering the standard route vs. the eco-route.

---

## 5. Non-Functional Requirements (NFR)
* **Performance:** Pathfinding on a 5km topological grid must compute in under 2 seconds.
* **Usability:** The Streamlit dashboard must be intuitive and require no coding knowledge from the end-user.
* **Extensibility:** The cost-function backend must be modular so that live-traffic APIs (like Google Maps API) can easily replace static probability data in future iterations.

---

## 6. The Mathematical Model & Engine Logic
The engine evaluates the environmental cost ($W$) of every road segment using this dual-state physics equation:

`W_edge = (Distance * E_cruise) + (T_idle * E_idle)`

* **Distance:** Length of the street link (km).
* **E_cruise:** Fuel burn/carbon rate during optimal cruising (grams of CO2/km).
* **T_idle:** Calculated delay time spent stationary (seconds), derived from intersection density and congestion indices.
* **E_idle:** Baseline consumption penalty of an engine standing still (grams of CO2/second).

### Physical Calibration Constants:
* **Petrol Carbon Multiplier:** 1 Liter of Petrol ≈ 740g weight -> Generates 2,310g of atmospheric CO2.
* **ICE Idle Draw:** A 1.5L engine draws 0.2 mL of fuel per second while idling (12 mL/min).
* **EV Invariance:** Wasted stationary idling energy is exactly 0.000g CO2/sec.

---

## 7. Assumptions & Project Limitations (MVP Scope)
To ensure academic and technical honesty, the MVP declares the following constraints:
* **Static Congestion:** The MVP relies on historical/probabilistic traffic weights rather than a live-streaming congestion API.
* **Flat Topology:** Gradient and slope calculations (which affect fuel consumption on hills or allow EV regenerative braking) are excluded from the current physics layer.
* **Auxiliary Power:** Climate control (e.g., Air Conditioning draw) is excluded from the idle cost calculation.

---

## 8. SIH Category & Strategic Deployment (Software Edition)

This project belongs strictly in the **Software** category of the Smart India Hackathon. It relies entirely on data science, algorithms, and web interfaces—with zero reliance on custom physical IoT devices or engine sensors.

**Tech Stack (100% Code):**
* **OpenStreetMap (OSMnx):** Pulling existing map data via software.
* **NetworkX (Python):** Running mathematical pathfinding algorithms.
* **Streamlit:** Creating a web-based user interface and dashboard.

### Strategic Advantage for Pitching
When presenting to the judges (especially those representing the Ministry of Environment), emphasizing that this is a software-only solution is a major strength:

1. **Zero Hardware Costs:** Easing EV adoption or reducing ICE emissions doesn't require waiting for citizens to buy expensive hardware monitors or for the government to install new physical traffic sensors.
2. **Instant Scalability:** Because it is software, the R2I Engine can be deployed to any city in India tomorrow. You just feed it a new city's map data, and the algorithm works immediately.
3. **Integration Ready:** As a software engine, this routing algorithm could theoretically be implemented via an API directly into existing apps that millions of Indians already use daily (like Google Maps, Swiggy, or Zomato delivery apps).

**In short:** R2I is an algorithmic, data-driven web application ready for immediate deployment as a digital public good.
