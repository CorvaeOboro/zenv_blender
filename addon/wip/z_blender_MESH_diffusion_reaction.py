"""
Diffusion Reaction Generator - Creates organic, brain-like mesh structures
"""

bl_info = {
    "name": 'MESH Diffusion Reaction',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Creates organic mesh structures using diffusion-reaction patterns',
    "status": 'wip',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
import random
import numpy as np
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_DiffusionReactionProperties(PropertyGroup):
    """Properties for the Diffusion Reaction Generator"""
    resolution: IntProperty(
        name="Resolution",
        description="Resolution of the simulation grid",
        default=50,
        min=10,
        max=200
    )
    iterations: IntProperty(
        name="Iterations",
        description="Number of simulation steps",
        default=100,
        min=10,
        max=1000
    )
    feed_rate: FloatProperty(
        name="Feed Rate",
        description="Rate at which chemicals are fed into system",
        default=0.037,
        min=0.001,
        max=0.1,
        precision=4
    )
    kill_rate: FloatProperty(
        name="Kill Rate",
        description="Rate at which chemicals are removed",
        default=0.06,
        min=0.001,
        max=0.1,
        precision=4
    )
    diffusion_a: FloatProperty(
        name="Diffusion A",
        description="Diffusion rate of chemical A",
        default=0.2,
        min=0.1,
        max=0.5
    )
    diffusion_b: FloatProperty(
        name="Diffusion B",
        description="Diffusion rate of chemical B",
        default=0.1,
        min=0.1,
        max=0.5
    )
    time_step: FloatProperty(
        name="Time Step",
        description="Time step for simulation",
        default=1.0,
        min=0.1,
        max=2.0
    )
    threshold: FloatProperty(
        name="Threshold",
        description="Threshold for surface extraction",
        default=0.5,
        min=0.1,
        max=0.9
    )
    pattern_type: EnumProperty(
        name="Pattern Type",
        description="Type of pattern to generate",
        items=[
            ('MITOSIS', "Mitosis", "Cell division-like pattern"),
            ('CORAL', "Coral", "Coral growth pattern"),
            ('NEURAL', "Neural", "Neural network-like pattern")
        ],
        default='MITOSIS'
    )
    preview_steps: BoolProperty(
        name="Preview Steps",
        description="Show simulation steps in viewport",
        default=False
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_DiffusionReactionAdd(Operator):
    """Create a new diffusion-reaction pattern on the selected object"""
    bl_idname = "zenv.diffusion_reaction_add"
    bl_label = "Add Diffusion Reaction"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def get_edge_vertices(self, edge_index, cell_pos, cell_size, iso_level, grid_values):
        """Get interpolated vertex position along an edge"""
        # Edge vertices mapping (cell coordinates)
        edge_to_vertices = {
            0: [(0,0,0), (1,0,0)], 1: [(1,0,0), (1,0,1)],
            2: [(1,0,1), (0,0,1)], 3: [(0,0,1), (0,0,0)],
            4: [(0,1,0), (1,1,0)], 5: [(1,1,0), (1,1,1)],
            6: [(1,1,1), (0,1,1)], 7: [(0,1,1), (0,1,0)],
            8: [(0,0,0), (0,1,0)], 9: [(1,0,0), (1,1,0)],
            10: [(1,0,1), (1,1,1)], 11: [(0,0,1), (0,1,1)]
        }
        
        v1_offset, v2_offset = edge_to_vertices[edge_index]
        p1 = np.array([cell_pos[i] + v1_offset[i] for i in range(3)])
        p2 = np.array([cell_pos[i] + v2_offset[i] for i in range(3)])
        
        val1 = grid_values[tuple(p1)]
        val2 = grid_values[tuple(p2)]
        
        # Interpolate position
        t = (iso_level - val1) / (val2 - val1) if abs(val2 - val1) > 1e-10 else 0.5
        pos = p1 + t * (p2 - p1)
        return pos * cell_size

    def marching_cubes(self, volume, iso_level):
        """Implementation of marching cubes algorithm"""
        edges = [
            [0,1], [1,2], [2,3], [3,0],
            [4,5], [5,6], [6,7], [7,4],
            [0,4], [1,5], [2,6], [3,7]
        ]
        
        # Triangle table (simplified version)
        tri_table = [
            [], [0,8,3], [0,1,9], [1,8,3,9,8,1],
            [1,2,10], [0,8,3,1,2,10], [0,9,2,2,10,9],
            [1,8,3,9,8,1,2,10,9], [2,3,11],
            [0,8,11,11,2,0], [1,9,0,2,3,11],
            [1,9,2,2,11,3,11,8,3], [1,2,10,3,11,8],
            [0,2,10,10,8,0,11,8,10], [0,9,2,2,10,9,3,11,8],
            [3,11,8,2,10,9,10,8,9]
        ]
        
        vertices = []
        faces = []
        
        cell_size = 1.0 / (max(volume.shape) - 1)
        
        # Iterate through grid cells
        for x in range(volume.shape[0] - 1):
            for y in range(volume.shape[1] - 1):
                for z in range(volume.shape[2] - 1):
                    cell_pos = (x, y, z)
                    
                    # Get cell vertices values
                    v = [
                        volume[x,y,z], volume[x+1,y,z],
                        volume[x+1,y,z+1], volume[x,y,z+1],
                        volume[x,y+1,z], volume[x+1,y+1,z],
                        volume[x+1,y+1,z+1], volume[x,y+1,z+1]
                    ]
                    
                    # Calculate cell index
                    cell_index = 0
                    for i in range(8):
                        if v[i] > iso_level:
                            cell_index |= 1 << i
                    
                    # Get triangle vertices
                    if cell_index > 0 and cell_index < len(tri_table):
                        edge_list = tri_table[cell_index]
                        for i in range(0, len(edge_list), 3):
                            # Get vertices for triangle
                            v1 = self.get_edge_vertices(edge_list[i], cell_pos, cell_size, iso_level, volume)
                            v2 = self.get_edge_vertices(edge_list[i+1], cell_pos, cell_size, iso_level, volume)
                            v3 = self.get_edge_vertices(edge_list[i+2], cell_pos, cell_size, iso_level, volume)
                            
                            # Add vertices and face
                            face_start = len(vertices)
                            vertices.extend([v1, v2, v3])
                            faces.append([face_start, face_start+1, face_start+2])
        
        return np.array(vertices), np.array(faces)

    def execute(self, context):
        props = context.scene.diffusion_props
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get object bounds
        bounds = [obj.bound_box[0], obj.bound_box[6]]
        size = np.array(bounds[1]) - np.array(bounds[0])
        center = np.array(bounds[0]) + size/2
        
        # Initialize volume grid based on object bounds
        grid_shape = (props.resolution,) * 3
        volume = np.zeros(grid_shape)
        
        # Sample object volume
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        
        # Create grid points
        x = np.linspace(bounds[0][0], bounds[1][0], props.resolution)
        y = np.linspace(bounds[0][1], bounds[1][1], props.resolution)
        z = np.linspace(bounds[0][2], bounds[1][2], props.resolution)
        grid = np.meshgrid(x, y, z, indexing='ij')
        
        # Initialize chemicals
        a = np.ones(grid_shape)
        b = np.zeros(grid_shape)
        
        # Add initial pattern based on type
        if props.pattern_type == 'MITOSIS':
            b[grid_shape[0]//2, grid_shape[1]//2, grid_shape[2]//2] = 1.0
        elif props.pattern_type == 'CORAL':
            b[grid_shape[0]//2:grid_shape[0]//2+2, :, :] = 1.0
        else:  # NEURAL
            points = np.random.rand(10, 3) * (np.array(grid_shape) - 2) + 1
            for p in points.astype(int):
                b[p[0], p[1], p[2]] = 1.0
        
        # Run simulation
        for step in range(props.iterations):
            # Compute Laplacian
            laplace_a = np.zeros_like(a)
            laplace_b = np.zeros_like(b)
            
            for i in range(1, grid_shape[0]-1):
                for j in range(1, grid_shape[1]-1):
                    for k in range(1, grid_shape[2]-1):
                        laplace_a[i,j,k] = (
                            a[i+1,j,k] + a[i-1,j,k] +
                            a[i,j+1,k] + a[i,j-1,k] +
                            a[i,j,k+1] + a[i,j,k-1] - 6*a[i,j,k]
                        )
                        laplace_b[i,j,k] = (
                            b[i+1,j,k] + b[i-1,j,k] +
                            b[i,j+1,k] + b[i,j-1,k] +
                            b[i,j,k+1] + b[i,j,k-1] - 6*b[i,j,k]
                        )
            
            # Update concentrations
            ab2 = a * b * b
            a += props.time_step * (props.diffusion_a * laplace_a - ab2 + props.feed_rate * (1 - a))
            b += props.time_step * (props.diffusion_b * laplace_b + ab2 - (props.kill_rate + props.feed_rate) * b)
            
            # Clip values
            a = np.clip(a, 0, 1)
            b = np.clip(b, 0, 1)
            
            if props.preview_steps and step % 10 == 0:
                # Update preview mesh
                vertices, faces = self.marching_cubes(b, props.threshold)
                
                # Scale vertices to match object size
                vertices = vertices * size + np.array(bounds[0])
                
                # Update mesh
                mesh = obj.data
                mesh.clear_geometry()
                mesh.vertices.add(len(vertices))
                mesh.vertices.foreach_set("co", vertices.flatten())
                mesh.polygons.add(len(faces))
                mesh.polygons.foreach_set("vertices", faces.flatten())
                mesh.update()
                
                # Force viewport update
                context.view_layer.update()
        
        # Generate final mesh
        vertices, faces = self.marching_cubes(b, props.threshold)
        
        # Scale vertices to match object size
        vertices = vertices * size + np.array(bounds[0])
        
        # Update mesh
        mesh = obj.data
        mesh.clear_geometry()
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set("co", vertices.flatten())
        mesh.polygons.add(len(faces))
        mesh.polygons.foreach_set("vertices", faces.flatten())
        mesh.update()
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_DiffusionReactionPanel(Panel):
    """Panel for Diffusion Reaction Generator"""
    bl_label = "MESH Diffusion Reaction"
    bl_idname = "ZENV_PT_diffusion_reaction"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        props = context.scene.diffusion_props
        
        if not context.active_object or context.active_object.type != 'MESH':
            layout.label(text="Select a mesh object", icon='ERROR')
            return
            
        layout.prop(props, "pattern_type")
        
        box = layout.box()
        box.label(text="Simulation Parameters:")
        box.prop(props, "resolution")
        box.prop(props, "iterations")
        box.prop(props, "time_step")
        
        box = layout.box()
        box.label(text="Reaction Parameters:")
        box.prop(props, "feed_rate")
        box.prop(props, "kill_rate")
        box.prop(props, "diffusion_a")
        box.prop(props, "diffusion_b")
        
        box = layout.box()
        box.label(text="Mesh Parameters:")
        box.prop(props, "threshold")
        box.prop(props, "preview_steps")
        
        layout.operator("zenv.diffusion_reaction_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_DiffusionReactionProperties,
    ZENV_OT_DiffusionReactionAdd,
    ZENV_PT_DiffusionReactionPanel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.diffusion_props = PointerProperty(type=ZENV_PG_DiffusionReactionProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.diffusion_props

if __name__ == "__main__":
    register()
