# OSM to Road Network Conversion Project

A comprehensive Python project for converting OpenStreetMap (OSM) data into optimized road network files with turn restrictions and H3 spatial indexing.

## 1. Project Overview

The goal of this project is to convert raw OpenStreetMap (OSM) data into a highly optimized, graph-based road network suitable for routing algorithms. Unlike standard OSM tools, this project enriches the network with:
*   **H3 Spatial Indexing**: For efficient spatial lookups and hierarchical routing.
*   **Turn Restrictions**: Explicitly handling forbidden turns.
*   **Speed Prediction**: Inferring speed limits where missing.
*   **Shortcut Tables**: Pre-calculating costs for hierarchical routing.

## 2. Installation

```bash
pip install -r requirements.txt
```

## 3. Usage

```bash
python scripts/create_network.py --region Kentucky --district Somerset --output data/output
```

### Post-Processing (Optional)

To add integer indices to an existing edges CSV (if not using the main pipeline which does this automatically):

```bash
python scripts/index_edges.py --input data/output/Somerset_driving_simplified_edges_with_h3.csv --output data/output/Somerset_driving_edges_indexed.csv
```

## 4. Input Data

The primary input is **OpenStreetMap (OSM) data** in PBF format (`.osm.pbf`).

*   **Source**: Data is downloaded automatically using `pyrosm` from Geofabrik.
*   **Parameters**:
    *   `Region`: The geographic region (e.g., "Kentucky").
    *   `District`: A specific sub-area or city within the region (e.g., "Somerset").

## 5. Output Data

The pipeline generates four key CSV files in the `data/output/` directory:

### A. Nodes File (`*_simplified_nodes.csv`)
Contains the vertices of the road network.
*   `id`: Unique node identifier.
*   `geometry`: Point geometry (Latitude/Longitude).

### B. Edges File (`*_simplified_edges_with_h3.csv`)
Contains the road segments connecting nodes.
*   `id`: Unique integer edge identifier.
*   `source`: ID of the starting node.
*   `target`: ID of the ending node.
*   `length`: Length of the segment in meters.
*   `maxspeed`: Speed limit in km/h.
*   `geometry`: LineString geometry.
*   `incoming_cell`: H3 cell index of the target node (Integer).
*   `outgoing_cell`: H3 cell index of the source node (Integer).
*   `lca_res`: Resolution of the Lowest Common Ancestor H3 cell.
*   `cost`: Travel time cost (seconds).

### C. Edge Graph (`*_edge_graph.csv`)
Represents the connectivity *between edges*, essential for modeling turn restrictions.
*   `incoming_edge`: Integer ID of the edge entering a node.
*   `outgoing_edge`: Integer ID of the edge leaving that node.
*   **Note**: Forbidden turns are excluded from this graph.

### D. Shortcut Table (`*_shortcut_table.csv`)
An optimized table for hierarchical routing algorithms.
*   `incoming_edge`: The edge being traversed (Integer ID).
*   `via_edge`: The subsequent edge (Integer ID).
*   `cost`: Cost to traverse the incoming edge.
*   `via_cell`: H3 cell of the junction (Integer).
*   `lca_res`: Hierarchical level for routing decisions.

### E. Edge ID Mapping (`*_edge_id.csv`)
Mapping between the integer edge ID and the original (source, target) tuple.
*   `id`: Original edge identifier (source_node, target_node).
*   `index`: The assigned integer edge ID.

## 6. Pipeline Processing

The `create_network.py` script executes the following steps:

1.  **Download**: Fetches the OSM PBF file for the specified region.
2.  **Build Graph**: Extracts the driving network for the specified district using `osmnx` and `pyrosm`.
3.  **Simplify**: Removes self-loops and simplifies network topology.
4.  **Extract**: Converts the graph into Node and Edge DataFrames.
5.  **Process Speeds**:
    *   Parses existing `maxspeed` tags (handling mph/km/h).
    *   Predicts missing speeds based on `highway` type (e.g., motorway=110, residential=30).
6.  **Turn Restrictions**:
    *   Parses OSM relations to find "no_left_turn", "no_u_turn", etc.
    *   Identifies forbidden `(incoming_edge, outgoing_edge)` pairs.
7.  **Build Edge Graph**: Constructs the dual graph (edge-to-edge connectivity), filtering out forbidden turns.
8.  **H3 Indexing**:
    *   Converts node coordinates to H3 cells (Resolution 15).
    *   Calculates the Lowest Common Ancestor (LCA) resolution for edge pairs to support hierarchical spatial reasoning.
9.  **Calculate Costs**: Computes travel time based on length and speed.
10. **Create Shortcut Table**: Assembles the final routing table with all pre-calculated metrics.
11. **Save**: Exports all datasets to CSV.

## 7. Special Features

### H3 Spatial Indexing
This project uniquely integrates **Uber's H3 Hexagonal Hierarchical Spatial Index**. By mapping nodes to H3 cells and calculating LCA resolutions, the network supports **hierarchical routing algorithms**. This allows routers to ignore lower-level roads when traversing large distances, significantly speeding up pathfinding.

### Robust Turn Restrictions
Many basic OSM converters ignore turn restrictions. This project explicitly extracts them from OSM relations and builds an **Edge Graph** (Dual Graph). This ensures that a route will never suggest an illegal turn, which is critical for realistic navigation.

### Intelligent Speed Inference
Raw OSM data often lacks speed limits. The `SpeedProcessor` module uses a heuristic dictionary to infer speed limits based on road types (`highway` tag), ensuring that cost calculations are reasonable even when data is missing.

## 8. Integration with Spark Shortest Path

The output files generated by this project are designed to be directly consumed by the **[Spark-Shortest-Path](https://github.com/Khoshkhah/Spark-Shortest-Path)** project.

*   **Input for Spark**: `data/output/{district}_driving_simplified_edges_with_h3.csv`
*   **Input for Spark**: `data/output/{district}_driving_edge_graph.csv`

To use these projects together:
1.  Run `osm-to-road-network` to generate the network files.
2.  Configure `spark-shortest-path` to point to these generated CSV files.

test