# OSM to Road Network Conversion Project

A comprehensive Python project for converting OpenStreetMap (OSM) data into optimized road network files with turn restrictions and H3 spatial indexing.

## Project Structure

```
osm-road-network/
├── README.md
├── requirements.txt
├── setup.py
├── config/
│   └── config.yaml
├── src/
│   ├── __init__.py
│   ├── downloader.py
│   ├── network_builder.py
│   ├── speed_processor.py
│   ├── restriction_handler.py
│   ├── h3_processor.py
│   └── utils.py
├── tests/
│   ├── __init__.py
│   ├── test_speed_processor.py
│   ├── test_h3_processor.py
│   └── test_network_builder.py
├── notebooks/
│   └── create_network.ipynb (original)
├── data/
│   ├── maps/
│   ├── output/
│   └── .gitkeep
└── scripts/
    └── create_network.py
```

## Core Modules

### 1. `src/downloader.py`
Handles OSM data downloads and caching.

```python
import os
from pyrosm import get_data
from pathlib import Path

class OSMDownloader:
    def __init__(self, cache_dir='data/maps'):
        self.cache_dir = cache_dir
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
    
    def download_region(self, region_name):
        """Download OSM data for a region."""
        try:
            fp = get_data(region_name, directory=self.cache_dir)
            return fp
        except Exception as e:
            raise RuntimeError(f"Error downloading {region_name}: {e}")
    
    def get_cached_file(self, region_name):
        """Get path to cached OSM file if it exists."""
        pbf_file = f"{self.cache_dir}/{region_name.lower()}-latest.osm.pbf"
        if os.path.exists(pbf_file):
            return pbf_file
        return None
```

### 2. `src/speed_processor.py`
Processes and predicts speed limits.

```python
import re
import pandas as pd
import numpy as np

class SpeedProcessor:
    MPH_TO_KMPH = 1.60934
    
    SPEED_DEFAULTS = {
        "motorway": 110,
        "motorway_link": 110,
        "trunk": 90,
        "trunk_link": 90,
        "primary": 70,
        "primary_link": 70,
        "secondary": 60,
        "secondary_link": 60,
        "tertiary": 50,
        "tertiary_link": 50,
        "residential": 30,
        "living_street": 30,
        "service": 20,
        "unclassified": 40,
        "road": 40,
    }
    
    @staticmethod
    def predict_maxspeed(highway):
        """Predict speed based on highway type."""
        if isinstance(highway, list):
            highway = highway[0]
        highway = str(highway).lower() if highway else ""
        return SpeedProcessor.SPEED_DEFAULTS.get(highway, 50)
    
    @staticmethod
    def fix_speed_format(df):
        """Convert speed values to km/h format."""
        speed_parts = df['maxspeed'].astype(str).str.extract(
            r'(\d+\.?\d*)\s*(mph|km/h|kmh|kph)?',
            flags=re.IGNORECASE
        )
        
        df['speed_value'] = pd.to_numeric(speed_parts[0], errors='coerce')
        df['speed_unit'] = speed_parts[1].str.lower()
        df['maxspeed'] = df['speed_value'].copy()
        
        df.loc[df['speed_unit'] == 'mph', 'maxspeed'] = (
            df['speed_value'] * SpeedProcessor.MPH_TO_KMPH
        )
        
        return df.drop(columns=['speed_value', 'speed_unit'])
    
    @staticmethod
    def process_speeds(edges_df, highway_col='highway'):
        """Process and fill missing speeds."""
        edges_df = SpeedProcessor.fix_speed_format(edges_df)
        edges_df['maxspeed'] = edges_df.apply(
            lambda row: (
                SpeedProcessor.predict_maxspeed(row[highway_col])
                if pd.isna(row['maxspeed'])
                else row['maxspeed']
            ),
            axis=1
        )
        edges_df['maxspeed'] = edges_df['maxspeed'].astype(float)
        return edges_df
```

### 3. `src/restriction_handler.py`
Extracts and processes turn restrictions.

```python
import osmium
import pandas as pd

class RestrictionHandler(osmium.SimpleHandler):
    """Extract turn restrictions from OSM relations."""
    
    def __init__(self):
        super().__init__()
        self.restrictions = []
    
    def relation(self, r):
        if 'restriction' not in r.tags:
            return
        
        rel = {
            "id": r.id,
            "restriction": r.tags["restriction"],
            "from": None,
            "via": None,
            "to": None
        }
        
        for m in r.members:
            if m.role == "from" and m.type == "w":
                rel["from"] = str(m.ref)
            elif m.role == "via" and m.type == "n":
                rel["via"] = str(m.ref)
            elif m.role == "to" and m.type == "w":
                rel["to"] = str(m.ref)
        
        self.restrictions.append(rel)

class TurnRestrictionProcessor:
    @staticmethod
    def extract_restrictions(pbf_file):
        """Extract turn restrictions from PBF file."""
        handler = RestrictionHandler()
        handler.apply_file(pbf_file, locations=False)
        return pd.DataFrame(handler.restrictions)
    
    @staticmethod
    def apply_restrictions(G, restriction_df):
        """Apply turn restrictions to graph."""
        forbidden = []
        
        for _, row in restriction_df.iterrows():
            via_node = row['via']
            from_way = row['from']
            to_way = row['to']
            
            if via_node not in G.nodes:
                continue
            
            incoming_edges = G.in_edges(via_node, data=True)
            outgoing_edges = G.out_edges(via_node, data=True)
            
            from_edge = TurnRestrictionProcessor._find_edge(
                incoming_edges, from_way
            )
            to_edge = TurnRestrictionProcessor._find_edge(
                outgoing_edges, to_way
            )
            
            if from_edge and to_edge:
                forbidden.append((from_edge, to_edge))
        
        return forbidden
    
    @staticmethod
    def _find_edge(edges, way_id):
        """Find edge matching a way ID."""
        for u, v, data in edges:
            osmid = data.get('osmid')
            if osmid == way_id or (isinstance(osmid, list) and way_id in osmid):
                return (u, v)
        return None
```

### 4. `src/h3_processor.py`
Handles H3 spatial indexing.

```python
import h3

class H3Processor:
    @staticmethod
    def latlng_to_cell(lat, lng, resolution=15):
        """Convert coordinates to H3 cell."""
        return h3.latlng_to_cell(lat, lng, resolution)
    
    @staticmethod
    def find_lca(cell1, cell2):
        """Find Lowest Common Ancestor between two H3 cells."""
        if cell1 is None or cell2 is None:
            return None
        
        cell1_res = h3.get_resolution(cell1)
        cell2_res = h3.get_resolution(cell2)
        lca_res = min(cell1_res, cell2_res)
        
        while lca_res >= 0:
            if (h3.cell_to_parent(cell1, lca_res) ==
                h3.cell_to_parent(cell2, lca_res)):
                return h3.cell_to_parent(cell1, lca_res)
            lca_res -= 1
        
        return None
    
    @staticmethod
    def get_lca_resolution(cell1, cell2):
        """Get resolution of LCA between two cells."""
        lca = H3Processor.find_lca(cell1, cell2)
        if lca is None:
            return -1
        return h3.get_resolution(lca)
    
    @staticmethod
    def add_h3_cells(edges_df, nodes_df, resolution=15):
        """Add H3 cells to edges dataframe."""
        edges_df['incoming_cell'] = edges_df['target'].apply(
            lambda t: H3Processor.latlng_to_cell(
                nodes_df.loc[t]['geometry'].y,
                nodes_df.loc[t]['geometry'].x,
                resolution
            )
        )
        edges_df['outgoing_cell'] = edges_df['source'].apply(
            lambda s: H3Processor.latlng_to_cell(
                nodes_df.loc[s]['geometry'].y,
                nodes_df.loc[s]['geometry'].x,
                resolution
            )
        )
        edges_df['lca_res'] = edges_df.apply(
            lambda row: H3Processor.get_lca_resolution(
                row['incoming_cell'],
                row['outgoing_cell']
            ),
            axis=1
        )
        return edges_df
```

### 5. `src/network_builder.py`
Main network building orchestration.

```python
import pandas as pd
import networkx as nx
import osmnx as ox
from pyrosm import OSM
from .speed_processor import SpeedProcessor
from .restriction_handler import TurnRestrictionProcessor
from .h3_processor import H3Processor

class NetworkBuilder:
    def __init__(self, pbf_file, district_name):
        self.pbf_file = pbf_file
        self.district_name = district_name
        self.graph = None
        self.edges_df = None
        self.nodes_df = None
    
    def get_district_boundaries(self):
        """Extract district boundaries from OSM."""
        osm = OSM(self.pbf_file)
        boundaries = osm.get_boundaries()
        boundaries_filtered = boundaries[
            (boundaries["name"].notna()) &
            (pd.to_numeric(boundaries["admin_level"], errors='coerce').notna())
        ]
        boundaries_filtered["admin_level"] = (
            boundaries_filtered["admin_level"].astype(int)
        )
        return boundaries_filtered[
            boundaries_filtered["admin_level"] == 8
        ].set_index("name")
    
    def build_graph(self, district_name, network_type='driving'):
        """Build network graph for a district."""
        osm = OSM(self.pbf_file)
        boundaries = self.get_district_boundaries()
        
        bbox_geom = boundaries.loc[district_name]["geometry"]
        osm_district = OSM(self.pbf_file, bounding_box=bbox_geom)
        
        nodes_gdf, edges_gdf = osm_district.get_network(
            network_type=network_type,
            nodes=True
        )
        
        self.graph = osm_district.to_graph(
            nodes_gdf,
            edges_gdf,
            graph_type="networkx",
            osmnx_compatible=True
        )
        
        return self.graph
    
    def simplify_graph(self):
        """Simplify graph and remove self-loops."""
        self.graph = ox.simplify_graph(self.graph)
        
        loop_edges = [
            edge for edge in self.graph.edges()
            if edge[0] == edge[1]
        ]
        self.graph.remove_edges_from(loop_edges)
    
    def extract_edges_and_nodes(self):
        """Extract edges and nodes from graph."""
        edges_df = nx.to_pandas_edgelist(
            self.graph,
            source="source",
            target="target"
        )
        
        edges_df['id'] = edges_df.apply(
            lambda row: (row['source'], row['target']),
            axis=1
        )
        edges_df = edges_df[[
            "id", "source", "target", "length", "maxspeed", "geometry"
        ]]
        
        self.edges_df = edges_df[
            edges_df.apply(
                lambda row: row['source'] != row['target'],
                axis=1
            )
        ]
        
        self.nodes_df = pd.DataFrame(
            nx.get_node_attributes(self.graph, 'geometry').items(),
            columns=['id', 'geometry']
        ).set_index('id')
        
        return self.edges_df, self.nodes_df
    
    def process_speeds(self, highway_col='highway'):
        """Process speed limits in edges."""
        self.edges_df = SpeedProcessor.process_speeds(
            self.edges_df,
            highway_col
        )
    
    def add_turn_restrictions(self):
        """Extract and apply turn restrictions."""
        restriction_df = TurnRestrictionProcessor.extract_restrictions(
            self.pbf_file
        )
        
        forbidden = TurnRestrictionProcessor.apply_restrictions(
            self.graph,
            restriction_df
        )
        
        return restriction_df, forbidden
    
    def build_edge_graph(self, forbidden_turns=None):
        """Build edge graph with turn restrictions."""
        if forbidden_turns is None:
            forbidden_turns = []
        
        edge_graph = []
        for node in self.graph.nodes:
            incoming = self.graph.in_edges(node, data=False)
            outgoing = self.graph.out_edges(node, data=False)
            for u, v in incoming:
                for x, y in outgoing:
                    edge_graph.append(((u, v), (x, y)))
        
        new_edge_graph = list(set(edge_graph) - set(forbidden_turns))
        
        edge_graph_df = pd.DataFrame(
            new_edge_graph,
            columns=['incoming_edge', 'outgoing_edge']
        )
        edge_graph_df = edge_graph_df[
            edge_graph_df.apply(
                lambda row: row['incoming_edge'] != row['outgoing_edge'],
                axis=1
            )
        ]
        
        return edge_graph_df
    
    def add_h3_indexing(self):
        """Add H3 spatial indexing."""
        self.edges_df = H3Processor.add_h3_cells(
            self.edges_df,
            self.nodes_df,
            resolution=15
        )
    
    def calculate_costs(self):
        """Calculate travel time costs."""
        def travel_time(length, maxspeed):
            return length / (maxspeed * 1000 / 3600)
        
        self.edges_df['cost'] = self.edges_df.apply(
            lambda row: travel_time(row['length'], row['maxspeed']),
            axis=1
        )
    
    def create_shortcut_table(self, edge_graph_df):
        """Create shortcut table for hierarchical routing."""
        self.edges_df.set_index('id', inplace=True)
        
        shortcut_table = edge_graph_df.copy()
        shortcut_table['next_edge'] = shortcut_table['outgoing_edge']
        shortcut_table['cost'] = shortcut_table['incoming_edge'].apply(
            lambda x: self.edges_df.loc[x]['cost']
        )
        shortcut_table['via_cell'] = shortcut_table['incoming_edge'].apply(
            lambda x: self.edges_df.loc[x]['incoming_cell']
        )
        shortcut_table['via_cell_res'] = 15
        
        shortcut_table['lca_res_incoming'] = shortcut_table['incoming_edge'].apply(
            lambda x: self.edges_df.loc[x]['lca_res']
        )
        shortcut_table['lca_res_outgoing'] = shortcut_table['outgoing_edge'].apply(
            lambda x: self.edges_df.loc[x]['lca_res']
        )
        shortcut_table['lca_res'] = shortcut_table.apply(
            lambda row: max(
                row['lca_res_incoming'],
                row['lca_res_outgoing']
            ),
            axis=1
        )
        
        return shortcut_table
    
    def save_outputs(self, output_dir='data/output'):
        """Save all output files."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        prefix = f"{output_dir}/{self.district_name}_driving"
        
        self.nodes_df.to_csv(f"{prefix}_simplified_nodes.csv")
        self.edges_df.to_csv(f"{prefix}_simplified_edges_with_h3.csv")
        
        print(f"Outputs saved to {output_dir}")
```

### 6. `scripts/create_network.py`
Main execution script.

```python
import argparse
from pathlib import Path
from src.downloader import OSMDownloader
from src.network_builder import NetworkBuilder

def main(region, district, output_dir):
    print(f"Starting OSM to Road Network conversion...")
    print(f"Region: {region}, District: {district}")
    
    # Download OSM data
    downloader = OSMDownloader(cache_dir='data/maps')
    pbf_file = downloader.download_region(region)
    print(f"Downloaded: {pbf_file}")
    
    # Build network
    builder = NetworkBuilder(pbf_file, district)
    
    print("Building graph...")
    builder.build_graph(district)
    
    print("Simplifying graph...")
    builder.simplify_graph()
    
    print("Extracting edges and nodes...")
    builder.extract_edges_and_nodes()
    
    print("Processing speeds...")
    builder.process_speeds()
    
    print("Adding turn restrictions...")
    restriction_df, forbidden = builder.add_turn_restrictions()
    
    print("Building edge graph...")
    edge_graph_df = builder.build_edge_graph(forbidden)
    
    print("Adding H3 indexing...")
    builder.add_h3_indexing()
    
    print("Calculating costs...")
    builder.calculate_costs()
    
    print("Creating shortcut table...")
    shortcut_table = builder.create_shortcut_table(edge_graph_df)
    
    print("Saving outputs...")
    builder.save_outputs(output_dir)
    
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert OSM data to road network files"
    )
    parser.add_argument(
        "--region",
        required=True,
        help="OSM region name (e.g., Kentucky, California)"
    )
    parser.add_argument(
        "--district",
        required=True,
        help="District/area name within region"
    )
    parser.add_argument(
        "--output",
        default="data/output",
        help="Output directory"
    )
    
    args = parser.parse_args()
    main(args.region, args.district, args.output)
```

## Requirements

```
# requirements.txt
pyrosm>=0.6.1
osmnx>=1.9.1
networkx>=3.0
geopandas>=0.12.0
shapely>=2.0
pandas>=1.5.0
h3>=3.7.0
osmium>=3.6.0
pyyaml>=6.0
pytest>=7.0.0
```

## Installation & Usage

### Setup
```bash
git clone <repository>
cd osm-road-network
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Basic Usage
```bash
python scripts/create_network.py --region Kentucky --district Somerset --output data/output
```

### In Python
```python
from src.network_builder import NetworkBuilder
from src.downloader import OSMDownloader

# Download and process
downloader = OSMDownloader()
pbf_file = downloader.download_region("Kentucky")

# Build network
builder = NetworkBuilder(pbf_file, "Somerset")
builder.build_graph("Somerset")
builder.simplify_graph()
builder.extract_edges_and_nodes()
builder.process_speeds()
builder.add_h3_indexing()
builder.calculate_costs()
builder.save_outputs()
```

## Output Files

- `{district}_driving_simplified_nodes.csv` - Network nodes with H3 cells
- `{district}_driving_simplified_edges_with_h3.csv` - Network edges with speeds and H3 indexing
- `{district}_driving_edge_graph.csv` - Edge connectivity graph
- `{district}_driving_shortcut_table.csv` - Shortcut table for hierarchical routing

## Key Features

- **OSM Data Processing**: Downloads and parses OpenStreetMap data
- **Graph Simplification**: Removes redundant nodes and self-loops
- **Speed Limit Processing**: Handles multiple formats (mph/km/h) and predicts missing values
- **Turn Restrictions**: Extracts and applies OSM turn restriction relations
- **H3 Spatial Indexing**: Adds hierarchical hexagonal spatial indexing
- **Hierarchical Routing**: Supports shortcut tables for faster routing algorithms
- **Comprehensive Logging**: Tracks all processing steps

## Testing

```bash
pytest tests/ -v
```

## Contributing

Contributions welcome! Please ensure all tests pass and code is well-documented.

## License

MIT License