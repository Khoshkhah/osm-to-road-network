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
        self.edge_graph_df = None
        self.shortcut_table = None
        self.edge_id_df = None    
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
        self.edge_id_df = edges_df.reset_index()[['id', 'index']]
        
        edges_df = edges_df[[
            "source", "target", "length", "maxspeed", "geometry", "highway"
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
        self.edge_graph_df = edge_graph_df
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
        # Use MultiIndex for robust tuple lookups
        if 'source' in self.edges_df.columns and 'target' in self.edges_df.columns:
            self.edges_df.set_index(['source', 'target'], inplace=True)
        #elif 'id' in self.edges_df.columns:
             # Fallback if source/target not available (should not happen based on extract_edges_and_nodes)
        #     self.edges_df.set_index('id', inplace=True)
        
        shortcut_table = edge_graph_df.copy()
        shortcut_table['via_edge'] = shortcut_table['outgoing_edge']
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
        self.shortcut_table = shortcut_table
        return shortcut_table
    
    def save_outputs(self, output_dir='data/output'):
        """Save all output files."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        prefix = f"{output_dir}/{self.district_name}_driving"
        self.edge_id_df.to_csv(f"{prefix}_edge_id.csv",index=False)
        self.edge_id_df.set_index("id", inplace=True)
        self.nodes_df.to_csv(f"{prefix}_simplified_nodes.csv")
        # Use index to lookup edge_id since 'id' column is no longer present
        self.edges_df["id"] = self.edges_df.index.map(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.edges_df.to_csv(f"{prefix}_simplified_edges_with_h3.csv",index=False)
        self.edge_graph_df["incoming_edge"] = self.edge_graph_df["incoming_edge"].apply(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.edge_graph_df["outgoing_edge"] = self.edge_graph_df["outgoing_edge"].apply(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.edge_graph_df.to_csv(f"{prefix}_edge_graph.csv",index=False)
        self.shortcut_table["incoming_edge"] = self.shortcut_table["incoming_edge"].apply(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.shortcut_table["outgoing_edge"] = self.shortcut_table["outgoing_edge"].apply(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.shortcut_table["via_edge"] = self.shortcut_table["via_edge"].apply(lambda x: self.edge_id_df.loc[[x]]['index'].values[0])
        self.shortcut_table.to_csv(f"{prefix}_shortcut_table.csv", index=False)
        
        print(f"Outputs saved to {output_dir}")
