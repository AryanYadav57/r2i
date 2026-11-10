"""
fleet/network.py - Array-backed road network for fast many-to-many routing.

Wraps a feature-enriched MultiDiGraph (congestion scores applied) as numpy
arrays and runs scipy's C Dijkstra from many sources at once.
Parallel edges are collapsed to the shortest one.
"""

from __future__ import annotations

import math

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from r2i import config
from r2i.models.congestion import compute_congestion_score, compute_idle_time
from r2i.models.vehicle import VEHICLE_SPECS, SpecVehicle

_EPS = 1e-9


class RoadNetwork:
    def __init__(self, G: nx.MultiDiGraph, cfg=config):
        self.cfg = cfg
        self.node_ids = list(G.nodes())
        index = {n: i for i, n in enumerate(self.node_ids)}
        self.n = len(self.node_ids)
        self.lat = np.array([float(G.nodes[n]["y"]) for n in self.node_ids])
        self.lon = np.array([float(G.nodes[n]["x"]) for n in self.node_ids])

        score = []
        for n in self.node_ids:
            d = G.nodes[n]
            s = d.get("congestion_score")
            score.append(float(s) if s is not None else compute_congestion_score(d, cfg))
        self.congestion = np.array(score)
        self.idle_s = np.array([compute_idle_time(s, cfg) for s in self.congestion])
        self.is_signal = np.array([bool(G.nodes[n].get("is_signal")) for n in self.node_ids])

        best: dict = {}
        for u, v, d in G.edges(data=True):
            if u == v:
                continue
            length = float(d.get("length", 50.0))
            key = (index[u], index[v])
            if key not in best or length < best[key][0]:
                tt = float(d.get("travel_time", length / 8.33))
                best[key] = (length, tt)
        keys = np.array(list(best.keys()), dtype=np.int64).reshape(-1, 2)
        vals = np.array(list(best.values()), dtype=float).reshape(-1, 2)
        self.eu, self.ev = keys[:, 0], keys[:, 1]
        self.len_km = vals[:, 0] / 1000.0
        self.tt_s = vals[:, 1]
        self.edge_idle_s = self.idle_s[self.ev]          # idle at the edge's head node
        self._edge_index = {k: i for i, k in enumerate(best.keys())}
        self._csr_cache: dict = {}

    # ------------------------------------------------------------------ weights
    def edge_weights(self, objective: str) -> np.ndarray:
        """'distance' -> km; a vehicle class key -> R2I cost (g CO2 + alpha*s)."""
        if objective == "distance":
            return self.len_km
        spec = VEHICLE_SPECS[objective]
        veh = SpecVehicle(spec, spec.capacity_kg / 2)    # plan at half load
        idle_g_s = veh.idle_cost(1.0)
        cruise_g_km = veh.cruise_cost(1.0)
        return (cruise_g_km * self.len_km + idle_g_s * self.edge_idle_s
                + self.cfg.ALPHA * (self.tt_s + self.edge_idle_s))

    def _csr(self, objective: str) -> csr_matrix:
        if objective not in self._csr_cache:
            w = self.edge_weights(objective) + _EPS
            self._csr_cache[objective] = csr_matrix((w, (self.eu, self.ev)), shape=(self.n, self.n))
        return self._csr_cache[objective]

    def dijkstra(self, sources, objective: str):
        """Return (dist[len(sources), n], predecessors[len(sources), n])."""
        dist, pred = dijkstra(self._csr(objective), directed=True,
                              indices=list(sources), return_predecessors=True)
        return dist, pred

    # ------------------------------------------------------------------ paths
    @staticmethod
    def path(pred_row, source: int, target: int) -> list:
        if source == target:
            return [source]
        out = [target]
        while out[-1] != source:
            p = pred_row[out[-1]]
            if p < 0:
                return []
            out.append(int(p))
        return out[::-1]

    def edge(self, u: int, v: int) -> int:
        return self._edge_index[(u, v)]

    def path_stats(self, path: list) -> dict:
        length = tt = idle = 0.0
        for u, v in zip(path[:-1], path[1:]):
            e = self.edge(u, v)
            length += self.len_km[e]
            tt += self.tt_s[e]
            idle += self.edge_idle_s[e]
        return {"length_km": length, "travel_s": tt, "idle_s": idle}

    def nearest(self, lat: float, lon: float) -> int:
        k = math.cos(math.radians(lat))
        return int(np.argmin((self.lat - lat) ** 2 + ((self.lon - lon) * k) ** 2))

    def coords(self, i: int) -> tuple:
        return float(self.lat[i]), float(self.lon[i])

    def explore(self, source: int, target: int, objective: str, max_nodes: int = 6000):
        """Dijkstra settle order from source until target (for visualising the search)."""
        import heapq

        A = self._csr(objective)
        dist, prev = {source: 0.0}, {}
        settled, order, heap = set(), [], [(0.0, source)]
        while heap and len(order) < max_nodes:
            d, u = heapq.heappop(heap)
            if u in settled:
                continue
            settled.add(u)
            order.append(u)
            if u == target:
                break
            for k in range(A.indptr[u], A.indptr[u + 1]):
                v, nd = int(A.indices[k]), d + float(A.data[k])
                if nd < dist.get(v, float("inf")):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(heap, (nd, v))
        path = [target] if target in settled else []
        while path and path[-1] != source:
            path.append(prev[path[-1]])
        return order, path[::-1]
