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
