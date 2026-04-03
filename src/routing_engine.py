import networkx as nx
import sqlite3
from typing import Dict, List, Tuple, Optional
import math
from datetime import datetime

class RoutingEngine:
    """
    Graph-based routing engine that calculates the safest path 
    between two GPS coordinates using the RoadDatabase and RiskPredictor.
    """
    
    def __init__(self, db_path: str, risk_predictor=None):
        self.db_path = db_path
        self.predictor = risk_predictor
        self.G = nx.DiGraph()
        self.edge_map = {}
        self.node_coords = {}
        self._load_graph()
        print(f"RoutingEngine loaded {len(self.G.nodes)} nodes and {len(self.G.edges)} edges.")

    def _load_graph(self):
        """Loads nodes and edges from SQLite into NetworkX"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load edges
        cursor.execute("SELECT u, v, edge_id, segment_length_m, centroid_lat, centroid_lon, name FROM segments")
        
        for row in cursor.fetchall():
            u, v, edge_id, length, lat, lon, name = row
            
            # Add edge
            self.G.add_edge(u, v, key=edge_id, length=length, name=name)
            self.edge_map[edge_id] = (u, v)
            
            # Approximate node coords (store rough centroid as node coords for nearest node matching)
            # In a real OSM graph, nodes have exact lat/lon, but here we estimate
            self.node_coords[u] = (lat, lon)
            self.node_coords[v] = (lat, lon)
            
        conn.close()

    def get_nearest_node(self, lat: float, lon: float) -> int:
        """Finds the nearest graph node to a given lat/lon"""
        best_node = None
        min_dist = float('inf')
        
        for node_id, (n_lat, n_lon) in self.node_coords.items():
            # Simple euclidean distance for speed (valid for small areas like Colombo)
            dist = (lat - n_lat)**2 + (lon - n_lon)**2
            if dist < min_dist:
                min_dist = dist
                best_node = node_id
                
        # If the nearest road is more than ~5km away (0.05 degrees), reject it
        if min_dist > 0.05 ** 2:
            return None
                
        return best_node

    def calculate_safe_route(
        self, 
        start_lat: float, 
        start_lon: float, 
        end_lat: float, 
        end_lon: float,
        safety_weight: float = 1.0
    ) -> Dict:
        """
        Calculates the safest route applying a penalty to high-risk edges.
        safety_weight: 0.0 means Fastest Path, 1.0 means Max Safety Path.
        """
        start_node = self.get_nearest_node(start_lat, start_lon)
        end_node = self.get_nearest_node(end_lat, end_lon)
        
        if not start_node or not end_node:
            raise ValueError("Could not map start or end coordinates to the road network.")

        # If we have a predictor, apply dynamic weights
        # Otherwise fall back to distance
        def weight_func(u, v, d):
            base_length = d.get('length', 10.0)
            
            if self.predictor and safety_weight > 0:
                penalty = 0
                if hasattr(self.predictor, 'accident_reports') and self.predictor.accident_reports:
                    # Rough check using edge coordinates
                    n_lat, n_lon = self.node_coords[u]
                    boost, _ = self.predictor.accident_reports.get_risk_boost(n_lat, n_lon)
                    penalty = boost * 10 * safety_weight # Amplified penalty
                
                return base_length * (1 + penalty)
            else:
                return base_length

        try:
            # Calculate shortest path using Dijkstra
            path = nx.shortest_path(self.G, source=start_node, target=end_node, weight=weight_func)
            
            # Reconstruct the route geometry and instructions
            route_coords = []
            instructions = []
            total_distance = 0
            
            for i in range(len(path) - 1):
                u = path[i]
                v = path[i+1]
                edge_data = self.G.get_edge_data(u, v)
                
                n_lat, n_lon = self.node_coords[u]
                route_coords.append([n_lat, n_lon]) # Format: [lat, lon] for Leaflet/Flutter
                total_distance += edge_data.get('length', 0)
                
                name = edge_data.get('name', 'Unknown Road')
                if not instructions or instructions[-1]['road'] != name:
                    instructions.append({"road": name, "instruction": f"Proceed on {name}"})
            
            # Add end node
            end_n_lat, end_n_lon = self.node_coords[path[-1]]
            route_coords.append([end_n_lat, end_n_lon])
            
            return {
                "success": True,
                "coordinates": route_coords,
                "instructions": instructions,
                "distance_m": round(total_distance, 1),
                "nodes": path
            }
            
        except nx.NetworkXNoPath:
            return {"success": False, "message": "No path found between coordinates."}
        except Exception as e:
            return {"success": False, "message": f"Routing error: {str(e)}"}
