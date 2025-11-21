import pandas as pd
import argparse
import os

def index_edges(input_file, output_file):
    """
    Add an integer index to the edges CSV.
    """
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    
    print("Adding edge_index column...")
    df['edge_index'] = range(len(df))
    
    # Move edge_index to the front
    cols = ['edge_index'] + [col for col in df.columns if col != 'edge_index']
    df = df[cols]
    
    print(f"Saving to {output_file}...")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=False)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add integer index to edges CSV.")
    parser.add_argument("--input", required=True, help="Input CSV file path")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    
    args = parser.parse_args()
    
    index_edges(args.input, args.output)
