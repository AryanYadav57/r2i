# R2I Engine - Hackathon Team Task Board

Welcome to the Route-to-Impact (R2I) project! The core mathematical logic, PRD, and initial prototype (`r2i_engine.py`) have already been established. To build the MVP for the hackathon, we need to execute the following tasks.

Please claim a role and start working through your checklist.

---

## 👨‍💻 Role: Backend / Data Engineer
**Objective:** Replace our 4-node prototype grid with a real-world map and apply the eco-routing math.

- [ ] **Task 1: Learn OSMnx.** Review the `osmnx` Python documentation for downloading street networks.
- [ ] **Task 2: Download the Demo Zone.** Write a script (e.g., `fetch_map.py`) that uses `ox.graph_from_place("Koramangala, Bengaluru, India", network_type="drive")` to download a real neighborhood graph.
- [ ] **Task 3: Save the Graph.** Save the downloaded map locally as a `.graphml` file so we don't have to hit the API every time the app loads.
- [ ] **Task 4: Integrate the Math.** Modify `r2i_engine.py` to load this `.graphml` file and run the A* routing algorithm (with our ICE/EV cost functions) over the real streets.

---

## 🎨 Role: Frontend / UI Developer
**Objective:** Build the interactive web dashboard using Streamlit so judges can visually see the route changing.

- [ ] **Task 1: Learn Streamlit.** Review the basic Streamlit documentation (it is pure Python, no HTML/CSS required).
- [ ] **Task 2: UI Skeleton.** Create an `app.py` file and build the basic layout: a sidebar with "Origin", "Destination", and a toggle switch for "Vehicle Type (ICE vs EV)".
- [ ] **Task 3: Metric Displays.** Add Streamlit metric cards (e.g., `st.metric`) to display "Carbon Saved", "Fuel Saved", and "Time Difference".
- [ ] **Task 4: Map Rendering.** Figure out how to plot a `NetworkX` graph or `OSMnx` route visually inside the Streamlit app (Streamlit supports Folium maps via `streamlit-folium`).

---

## 📊 Role: Project Manager / Pitch Lead
**Objective:** Ensure the science is bulletproof and build the final presentation for the judges.

- [ ] **Task 1: Read the PRD.** Understand the "Elevator Pitch" and how the ICE vs EV thermodynamic math works.
- [ ] **Task 2: Data Validation.** Research official Indian government reports (like ARAI) to find the exact emissions data (grams of CO2 per liter of petrol in India) and update our calibration constants.
- [ ] **Task 3: Identify Bottlenecks.** Find 3-5 real-world intersections in our chosen "Demo Zone" that are notorious for traffic jams. Give these coordinates to the Backend Engineer so they can hardcode high "idle penalties" onto those specific streets.
- [ ] **Task 4: Pitch Deck.** Start outlining the 5-minute presentation slides using the "SIH Problem Statement Alignment" section in the PRD.
