bl_info = {
    "name": 'MESH Angular Planarize',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250809',
    "description": 'Converts smooth meshes into angular forms using normal-based clustering',
    "status": 'working',
    "approved": True,
    "sort_priority": '90',
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "description_short": 'planarize mesh faces by random k-means angle cluster , useful for rock like sharpening with flat areas',
    "description_long": """
MESH Angular Planarize - Normal-based clustering approach
Converts smooth meshes into angular forms using k-means clustering
of vertex normals and planar displacement.
""",
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
import logging
from bpy.props import (
    IntProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

class ZENV_PG_MeshAngularPlanarize_Props(PropertyGroup):
    """Properties for angular planarization"""
    
    cluster_count: IntProperty(
        name="Cluster Count",
        description="Number of normal clusters to create",
        default=8,
        min=2,
        max=50
    )
    
    displacement_strength: FloatProperty(
        name="Displacement Strength",
        description="Strength of displacement towards planar surface",
        default=0.5,
        min=0.0,
        max=1.0
    )
    
    preserve_volume: BoolProperty(
        name="Preserve Volume",
        description="Try to maintain the original mesh volume",
        default=True
    )
    
    smooth_boundaries: BoolProperty(
        name="Smooth Boundaries",
        description="Apply light smoothing at cluster boundaries",
        default=True
    )


# ------------------------------------------------------------------------
#    Planarization Utility Functions
# ------------------------------------------------------------------------

class ZENV_MeshAngularPlanarizeUtils:
    """Utility functions for mesh planarization and clustering"""
    
    @staticmethod
    def _euclidean_distance(x1, x2):
        """Calculate Euclidean distance between two points"""
        return np.sqrt(np.sum((x1 - x2) ** 2))

    @staticmethod
    def _init_centroids(data, k):
        """Initialize k centroids using k-means++ method"""
        n_samples = len(data)
        centroids = [data[np.random.randint(n_samples)]]
        
        for _ in range(k - 1):
            # Calculate distances from points to nearest centroid
            distances = np.array([
                min([ZENV_MeshAngularPlanarizeUtils._euclidean_distance(x, c) for c in centroids])
                for x in data
            ])
            
            # Choose next centroid with probability proportional to distance squared
            probs = distances ** 2
            probs /= probs.sum()
            cumprobs = probs.cumsum()
            r = np.random.random()
            
            for j, p in enumerate(cumprobs):
                if r < p:
                    centroids.append(data[j])
                    break
        
        return np.array(centroids)

    @staticmethod
    def _assign_clusters(data, centroids):
        """Assign each point to nearest centroid"""
        distances = np.array([[ZENV_MeshAngularPlanarizeUtils._euclidean_distance(x, c) for c in centroids] for x in data])
        return np.argmin(distances, axis=1)

    @staticmethod
    def _update_centroids(data, labels, k):
        """Update centroid positions"""
        centroids = np.zeros((k, data.shape[1]))
        for i in range(k):
            mask = labels == i
            if np.any(mask):
                centroids[i] = np.mean(data[mask], axis=0)
                # Normalize the normal vectors
                centroids[i] /= np.linalg.norm(centroids[i])
        return centroids

    @staticmethod
    def compute_clusters(normals, cluster_count, max_iter=100, tol=1e-4):
        """Perform k-means clustering on vertex normals
        
        Args:
            normals: numpy array of shape (n_samples, n_features)
            cluster_count: number of clusters to create
            max_iter: maximum number of iterations
            tol: tolerance for convergence
        
        Returns:
            labels: cluster assignments for each point
        """
        # Initialize centroids using k-means++
        centroids = ZENV_MeshAngularPlanarizeUtils._init_centroids(normals, cluster_count)
        
        for _ in range(max_iter):
            old_centroids = centroids.copy()
            
            # Assign points to nearest centroid
            labels = ZENV_MeshAngularPlanarizeUtils._assign_clusters(normals, centroids)
            
            # Update centroids
            centroids = ZENV_MeshAngularPlanarizeUtils._update_centroids(normals, labels, cluster_count)
            
            # Check for convergence
            if np.all(np.abs(old_centroids - centroids) < tol):
                break
        
        return labels
    
    @staticmethod
    def get_cluster_data(vertices, normals, cluster_id, cluster_mask):
        """Calculate average normal and centroid for a cluster"""
        cluster_normals = normals[cluster_mask]
        cluster_positions = vertices[cluster_mask]
        
        avg_normal = Vector(np.mean(cluster_normals, axis=0))
        avg_normal.normalize()
        
        centroid = Vector(np.mean(cluster_positions, axis=0))
        return avg_normal, centroid
    
    @staticmethod
    def smooth_boundaries(bm, clusters, strength=0.5):
        """Apply smoothing to vertices at cluster boundaries"""
        boundary_verts = set()
        
        # Find boundary vertices
        for edge in bm.edges:
            v1, v2 = edge.verts
            if clusters[v1.index] != clusters[v2.index]:
                boundary_verts.add(v1)
                boundary_verts.add(v2)
        
        # Smooth boundary vertices
        for v in boundary_verts:
            connected = [e.other_vert(v) for e in v.link_edges]
            avg_pos = sum((v.co for v in connected), Vector()) / len(connected)
            v.co = v.co.lerp(avg_pos, strength)


# ------------------------------------------------------------------------
#    Main Operator
# ------------------------------------------------------------------------

class ZENV_OT_MeshAngularPlanarize(Operator):
    """Convert smooth mesh into angular form using normal-based clustering"""
    bl_idname = "zenv.angular_planarize"
    bl_label = "Apply Angular Planarize"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.angular_planarize_props
        obj = context.active_object
        
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get mesh data
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()
        
        # Prepare data for clustering
        normals = np.array([v.normal[:] for v in bm.verts])
        positions = np.array([v.co[:] for v in bm.verts])
        
        # Perform clustering
        clusters = ZENV_MeshAngularPlanarizeUtils.compute_clusters(
            normals, 
            props.cluster_count
        )
        
        # Process each cluster
        for cluster_id in range(props.cluster_count):
            cluster_mask = clusters == cluster_id
            if not np.any(cluster_mask):
                continue
            
            # Get cluster data
            avg_normal, centroid = ZENV_MeshAngularPlanarizeUtils.get_cluster_data(
                positions, normals, cluster_id, cluster_mask
            )
            
            # Calculate plane equation
            d = avg_normal.dot(centroid)
            
            # Update vertex positions
            for i, v in enumerate(bm.verts):
                if clusters[i] == cluster_id:
                    current_d = avg_normal.dot(v.co)
                    diff = current_d - d
                    displacement = diff * avg_normal * props.displacement_strength
                    v.co -= displacement
        
        # Optional boundary smoothing
        if props.smooth_boundaries:
            ZENV_MeshAngularPlanarizeUtils.smooth_boundaries(bm, clusters, 0.3)
        
        # Update mesh
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()
        
        return {'FINISHED'}


# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_MeshAngularPlanarize_Panel(Panel):
    """Panel for angular planarize settings"""
    bl_label = "MESH Angular Planarize"
    bl_idname = "ZENV_PT_angular_planarize_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.angular_planarize_props
        
        layout.prop(props, "cluster_count")
        layout.prop(props, "displacement_strength")
        layout.prop(props, "preserve_volume")
        layout.prop(props, "smooth_boundaries")
        
        layout.separator()
        layout.operator(ZENV_OT_MeshAngularPlanarize.bl_idname)


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_MeshAngularPlanarize_Props,
    ZENV_OT_MeshAngularPlanarize,
    ZENV_PT_MeshAngularPlanarize_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.angular_planarize_props = PointerProperty(type=ZENV_PG_MeshAngularPlanarize_Props)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.angular_planarize_props

if __name__ == "__main__":
    register()
