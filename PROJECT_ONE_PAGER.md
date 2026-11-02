# 🚀 The R2I Engine: Quick-Start Guide for the Team

*If you are confused about what exactly we are building for this hackathon, read this! It explains the entire project in plain English in less than 2 minutes.*

---

## 1. What are we building?
We are building a web-based dashboard (using Streamlit) that acts like a smarter version of Google Maps. 

Instead of just routing a user based on the "shortest time", our app routes them based on the **"lowest carbon emissions."** We call this the Route-to-Impact (R2I) Engine.

## 2. Why are we building it? (The SIH Problem)
The government (Ministry of Environment) wants solutions to reduce air pollution and increase Electric Vehicle (EV) adoption. 

Right now, normal GPS apps route thousands of petrol/diesel cars into massive traffic jams. When cars sit still in traffic (idling), they burn fuel and pump massive amounts of toxic CO2 into the city without even moving. We are building software to fix this.

## 3. How does it work? (The Magic)
Our web dashboard will have a map and a toggle switch where the user can choose what car they are driving: **ICE (Petrol)** or **EV (Electric)**.

**If the user selects a Petrol Car:**
Our algorithm looks at the map, sees a massive traffic jam, and says: *"If you sit in that traffic jam, your engine will idle and pump out 2,000 grams of CO2. Let's route you on a longer, but completely clear road instead."* The car avoids the jam, saving fuel and reducing city pollution.

**If the user selects an EV:**
Our algorithm knows that Electric Vehicles **do not pollute or waste energy when standing completely still**. So, the algorithm says: *"You have zero idling emissions! Just take whatever route is fastest."*

**The Result:** Our app visually proves to users that EVs are faster, cheaper, and vastly superior in city traffic, which directly encourages people to buy EVs!

---

## 4. What are we physically coding for this hackathon?

We are not building hardware. We are writing 100% Python code. Here are the 3 pieces we need to build to win:

1. **The Map Data:** We will write a Python script using a library called `osmnx` to download the real street map of a congested Indian city (like Bengaluru or Delhi).
2. **The Routing Math:** We will use a library called `NetworkX` to run pathfinding algorithms (like A*) over those streets to find the lowest-emission route.
3. **The Web Dashboard:** We will use `Streamlit` to build a clean, dark-themed web app where judges can click the "ICE" vs "EV" toggle and watch the routes physically change on the screen in real-time.

---
*Ready to start? Check out the `TEAM_TASKS.md` file to claim your role (Frontend or Backend) and start coding!*
