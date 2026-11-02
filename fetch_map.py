
import osmnx as ox

def fetch_bangalore_map(output_path="bengaluru_grid.graphml"):
    """Download a road graph broad enough for central, south, and east Bengaluru.

    Bounds include RV University, Koramangala, MG Road, and Whitefield. Keep
    these bounds in sync with the landmark coordinates in app.py.
    """
    # OSMnx 2.x order: west, south, east, north. Extending only the east/west
    # span keeps the graph focused on the corridors this route demo supports.
    bounds = (77.485, 12.895, 77.765, 13.005)
    print(f"Fetching Bengaluru drive network within bounds {bounds}...")

    try:
        G = ox.graph_from_bbox(bounds, network_type="drive", simplify=True)
        if G:
            ox.save_graphml(G, filepath=output_path)
            print(f"Saved {len(G):,} nodes and {G.number_of_edges():,} edges to {output_path}")
            return output_path
    except Exception as e:
        print(f"Bengaluru network download failed: {e}")

    return None

if __name__ == "__main__":
    fetch_bangalore_map()
