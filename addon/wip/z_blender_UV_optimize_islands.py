# UV ISLAND OPTIMIZER
# Optimize UV island positions by moving them closer to UV space origin (0,0)
# while maintaining texture mapping by moving in whole number increments

bl_info = {
    "name": "UV Island Optimizer",
    "category": "UV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Side Panel > UV",
    "description": "Optimize UV island positions by moving them closer to origin",
}

import bpy
import bmesh
import math
from mathutils import Vector
from collections import defaultdict

class ZENV_UVIslandOptimizer_Logger:
    """Logger class for UV optimization operations"""
    @staticmethod
    def log_info(message, category="INFO"):
        print(f"[{category}] {message}")

    @staticmethod
    def log_error(message):
        print(f"[ERROR] {message}")

class ZENV_UVIslandOptimizer_Utils:
    """Utility functions for UV island optimization"""
    
    @staticmethod
    def get_uv_islands(bm, uv_layer):
        """Get UV islands from the mesh"""
        logger = ZENV_UVIslandOptimizer_Logger
        
        # Initialize island detection
        bm.faces.ensure_lookup_table()
        faces = set(bm.faces)
        islands = []
        
        while faces:
            # Start a new island
            face = faces.pop()
            island = {face}
            island_faces = {face}
            
            # Grow island
            while island_faces:
                face = island_faces.pop()
                # Check connected faces through UV space
                for edge in face.edges:
                    for link_face in edge.link_faces:
                        if link_face not in faces:
                            continue
                        
                        # Check if faces share UV coordinates
                        shared_uvs = False
                        for loop in edge.link_loops:
                            luv = loop[uv_layer]
                            for other_loop in edge.link_loops:
                                if other_loop.face == link_face:
                                    other_uv = other_loop[uv_layer]
                                    if (luv.uv - other_uv.uv).length < 0.0001:
                                        shared_uvs = True
                                        break
                            if shared_uvs:
                                break
                        
                        if shared_uvs:
                            island.add(link_face)
                            island_faces.add(link_face)
                            faces.remove(link_face)
            
            islands.append(island)
            logger.log_info(f"Found island with {len(island)} faces")
        
        return islands

    @staticmethod
    def get_island_bounds(island, uv_layer):
        """Get UV bounds of an island"""
        min_u = float('inf')
        min_v = float('inf')
        max_u = float('-inf')
        max_v = float('-inf')
        
        for face in island:
            for loop in face.loops:
                u, v = loop[uv_layer].uv
                min_u = min(min_u, u)
                min_v = min(min_v, v)
                max_u = max(max_u, u)
                max_v = max(max_v, v)
        
        return min_u, min_v, max_u, max_v

    @staticmethod
    def get_island_center(island, uv_layer):
        """Get center point of UV island"""
        min_u, min_v, max_u, max_v = ZENV_UVIslandOptimizer_Utils.get_island_bounds(island, uv_layer)
        return Vector(((min_u + max_u) / 2, (min_v + max_v) / 2))

    @staticmethod
    def get_closest_grid_offset(center):
        """Get closest grid point offset that would move center towards origin"""
        # Calculate offset to move center towards origin
        offset_u = -math.floor(center.x)  # Move towards 0 in whole numbers
        offset_v = -math.floor(center.y)
        return Vector((offset_u, offset_v))

    @staticmethod
    def move_island(island, uv_layer, offset):
        """Move an entire UV island by offset"""
        for face in island:
            for loop in face.loops:
                loop[uv_layer].uv += offset

class ZENV_UVIslandOptimizer_Properties(bpy.types.PropertyGroup):
    target_position: bpy.props.EnumProperty(
        name="Target Position",
        description="Where to move UV islands",
        items=[
            ('ORIGIN', 'Origin (0,0)', 'Move islands towards UV space origin'),
            ('CENTER', 'UV Center (0.5,0.5)', 'Move islands towards UV space center'),
        ],
        default='ORIGIN'
    )

class ZENV_OT_OptimizeUVIslands(bpy.types.Operator):
    """Optimize UV island positions by moving them closer to origin"""
    bl_idname = "zenv.zenv_optimize_islands"
    bl_label = "Optimize UV Islands"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'MESH')
    
    def execute(self, context):
        logger = ZENV_UVIslandOptimizer_Logger
        obj = context.active_object
        
        # Store original mode
        original_mode = obj.mode
        
        # Switch to edit mode if needed
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        
        # Ensure UV layer exists
        if not bm.loops.layers.uv:
            self.report({'ERROR'}, "No UV layer found")
            return {'CANCELLED'}
        
        uv_layer = bm.loops.layers.uv.verify()
        
        try:
            # Get UV islands
            islands = ZENV_UVIslandOptimizer_Utils.get_uv_islands(bm, uv_layer)
            logger.log_info(f"Found {len(islands)} UV islands")
            
            # Process each island
            for island in islands:
                # Get island center
                center = ZENV_UVIslandOptimizer_Utils.get_island_center(island, uv_layer)
                
                # Adjust target based on settings
                if context.scene.zenv_uv_optimizer.target_position == 'CENTER':
                    # Move towards UV center (0.5, 0.5)
                    center -= Vector((0.5, 0.5))
                
                # Calculate optimal offset
                offset = ZENV_UVIslandOptimizer_Utils.get_closest_grid_offset(center)
                
                # Move island if needed
                if offset.length > 0:
                    ZENV_UVIslandOptimizer_Utils.move_island(island, uv_layer, offset)
                    logger.log_info(f"Moved island by offset {offset}")
            
            # Update mesh
            bmesh.update_edit_mesh(me)
            
            # Restore original mode
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=original_mode)
            
            self.report({'INFO'}, f"Optimized {len(islands)} UV islands")
            return {'FINISHED'}
            
        except Exception as e:
            logger.log_error(f"Error during UV optimization: {str(e)}")
            self.report({'ERROR'}, str(e))
            
            # Ensure we restore original mode even on error
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=original_mode)
                
            return {'CANCELLED'}

class ZENV_PT_UVIslandOptimizer_Panel(bpy.types.Panel):
    """Panel for UV island optimization tools"""
    bl_label = "UV Island Optimizer"
    bl_idname = "ZENV_PT_uv_island_optimizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Optimize UV Islands:")
        
        props = context.scene.zenv_uv_optimizer
        col.prop(props, "target_position", text="")
        
        col.separator()
        row = col.row(align=True)
        row.operator(ZENV_OT_OptimizeUVIslands.bl_idname, text="Move Islands to Target")

# Registration
classes = (
    ZENV_UVIslandOptimizer_Properties,
    ZENV_OT_OptimizeUVIslands,
    ZENV_PT_UVIslandOptimizer_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_uv_optimizer = bpy.props.PointerProperty(type=ZENV_UVIslandOptimizer_Properties)

def unregister():
    del bpy.types.Scene.zenv_uv_optimizer
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
