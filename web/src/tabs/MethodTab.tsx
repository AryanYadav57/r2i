export default function MethodTab() {
  return (
    <div className="doc">
      <div className="inner">
        <h1>Method</h1>
        <p>R2I is a deterministic graph model, not a black box. Every number in this app comes from the formulas and assumptions below, applied to the OpenStreetMap road network of south-east Bengaluru (~20,000 junctions).</p>

        <h2>1. Congestion score</h2>
        <pre>{`S(v)      = clip( (streets·0.5 + signal·0.3 + roadclass·0.2) / 4.5 , 0, 1 )
T_idle(v) = S(v) · 17.5 s`}</pre>
        <p>Streets is the number of physical streets meeting at the junction, signal is 1 for a mapped traffic signal, roadclass ranges from 0.1 (service road) to 1.0 (primary road).</p>

        <h2>2. Edge cost</h2>
        <pre>{`W(e) = cruise_CO2(length, payload) + idle_CO2(T_idle at the next junction) + α · time`}</pre>
        <p>Cruise CO₂ scales with load: <span className="mono">factor = 1 + 0.6 · payload / kerb mass</span>. α converts seconds into grams so the router can trade time for emissions (α = 1 by default). For EVs tailpipe CO₂ is zero, so their route is the fastest one; grid CO₂ from charging is reported separately.</p>

        <h2>3. Fleet planning</h2>
        <ul>
          <li>An all-pairs cost table between the hub and every order is built per vehicle class with a multi-source Dijkstra (scipy).</li>
          <li>Google OR-Tools solves the vehicle routing problem with capacity, delivery windows and EV range. Every vehicle on shift is dispatched.</li>
          <li><b>Distance-only baseline</b>: same solver, same constraints, same time limit, but every vehicle uses distance as its cost.</li>
          <li><b>R2I</b>: each class uses its own eco-cost, then stops are re-ordered within each route using the true payload-aware cost (OR-Tools arc costs cannot depend on load, so this is a two-step approximation).</li>
          <li>Both plans are scored with the same payload-aware physics.</li>
        </ul>

        <h2>4. Assumptions</h2>
        <table><thead><tr><th>Constant</th><th>Value</th><th>Basis</th></tr></thead><tbody>
          <tr><td>Idle fuel, petrol car</td><td>0.2 mL/s (0.462 g CO₂/s)</td><td>1.5 L engine benchmark</td></tr>
          <tr><td>Base idle per junction</td><td>17.5 s</td><td>Midpoint of 15–20 s</td></tr>
          <tr><td>CO₂ per litre</td><td>petrol 2310 g · diesel 2680 g</td><td>Combustion stoichiometry</td></tr>
          <tr><td>Diesel mini-truck</td><td>179 g/km, 750 kg payload</td><td>~15 km/L light commercial vehicle</td></tr>
          <tr><td>Electric mini-truck / 3-wheeler</td><td>0.14 / 0.075 kWh/km</td><td>Manufacturer range figures</td></tr>
          <tr><td>Grid factor</td><td>710 g CO₂/kWh</td><td>CEA CO₂ baseline database</td></tr>
          <tr><td>Prices</td><td>petrol ₹103/L, diesel ₹89/L, ₹8/kWh</td><td>Bengaluru, late 2025</td></tr>
          <tr><td>Delivery stop</td><td>120 s, engine on 25 %</td><td>Last-mile assumption</td></tr>
        </tbody></table>

        <h2>5. Limitations</h2>
        <ul>
          <li>Congestion is a static structural proxy; there is no live or time-of-day traffic data.</li>
          <li>Travel times come from OSM speed limits (free-flow) plus predicted junction idling.</li>
          <li>All CO₂, fuel and ₹ figures are modelled estimates, not measurements.</li>
          <li>Fleet results depend on the solver's time limit; heuristics do not guarantee optimality.</li>
          <li>With few orders, R2I can simply prefer EVs; the preset dispatches every vehicle to keep the comparison fair.</li>
        </ul>
        <p className="hint">Source code, tests and benchmarks are in the repository README.</p>
      </div>
    </div>
  );
}
