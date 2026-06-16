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
        self.hotspots = []
        self._load_hotspots()
        print(f"RoutingEngine loaded {len(self.G.nodes)} nodes and {len(self.G.edges)} edges.")

    def _load_hotspots(self):
        """Loads permanent hotspots from MySQL database"""
        self.hotspots = []
        try:
            from api.database import SessionLocal
            from api.models import PermanentHotspot
            
            db = SessionLocal()
            try:
                rows = db.query(PermanentHotspot).filter(PermanentHotspot.is_active == True).all()
                self.hotspots = [
                    {
                        "latitude": h.latitude,
                        "longitude": h.longitude,
                        "risk_boost": h.risk_boost or 0.5
                    }
                    for h in rows
                ]
                print(f"RoutingEngine: Loaded {len(self.hotspots)} permanent hotspots from MySQL.")
            finally:
                db.close()
        except Exception as e:
            print(f"RoutingEngine Warning: Could not load hotspots from MySQL: {e}. Using empty default list.")
            self.hotspots = []

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculates distance between two points in km"""
        R = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _get_hotspot_penalty(self, lat: float, lon: float) -> float:
        """Calculates risk boost penalty based on distance to cached hotspots"""
        max_penalty = 0.0
        for h in self.hotspots:
            dist = self._haversine(lat, lon, h["latitude"], h["longitude"])
            if dist <= 0.5: # 500 meters
                # Linear falloff penalty: full penalty at 0m, 0 penalty at 500m
                penalty = h["risk_boost"] * (1.0 - (dist / 0.5))
                if penalty > max_penalty:
                    max_penalty = penalty
        return max_penalty

    def _calculate_route_safety_score(self, coordinates: List[List[float]]) -> float:
        """Calculates a safety score percentage for a route based on proximity to hotspots"""
        if not self.hotspots:
            return 100.0
            
        penalty_sum = 0.0
        for point in coordinates:
            penalty = self._get_hotspot_penalty(point[0], point[1])
            penalty_sum += penalty
            
        # Normalize: each full penalty (1.0) deducts 10% from the safety score. Clamp between 30% and 100%.
        score = 100.0 - (penalty_sum * 10.0)
        return max(30.0, min(100.0, score))

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
        
        def weight_func(u, v, d):
            base_length = d.get('length', 10.0)
            
            if safety_weight > 0 and self.hotspots:
                n_lat, n_lon = self.node_coords[u]
                penalty = self._get_hotspot_penalty(n_lat, n_lon)
                # Apply penalty scaled by safety_weight
                return base_length * (1 + penalty * 5.0 * safety_weight)
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
