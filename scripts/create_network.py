import argparse
from pathlib import Path
import sys
import os

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    
    print("Calculating costs...")
    builder.calculate_costs()
    
    print("Adding turn restrictions...")
    restriction_df, forbidden = builder.add_turn_restrictions()
    
    print("Building edge graph...")
    edge_graph_df = builder.build_edge_graph(forbidden)
    
    print("Adding H3 indexing...")
    builder.add_h3_indexing()
    
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
