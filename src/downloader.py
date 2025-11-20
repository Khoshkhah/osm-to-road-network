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
