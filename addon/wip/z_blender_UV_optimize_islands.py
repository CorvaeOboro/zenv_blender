# UV ISLAND OPTIMIZER
# Optimize UV island positions by moving them closer to UV space origin (0,0)
# while maintaining texture mapping by moving in whole number increments

bl_info = {
    "name": 'UV Island Optimizer',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250212',
    "description": 'Optimize UV island positions by moving them closer to origin',
    "status": 'wip',
    "approved": True,
    "group": 'UV',
    "group_prefix": 'UV',
    "location": '3D View > Side Panel > ZENV > UV Island Optimizer',
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
        """Get center point of a UV island"""
        min_u, min_v, max_u, max_v = ZENV_UVIslandOptimizer_Utils.get_island_bounds(island, uv_layer)
        return Vector(((min_u + max_u) / 2, (min_v + max_v) / 2))

class ZENV_OT_OptimizeUVIslands(bpy.types.Operator):
    """Move UV islands closer to origin while maintaining texturing"""
    bl_idname = "zenv.optimize_uv_islands"
    bl_label = "UV Optimize Islands"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me) if obj.mode == 'EDIT' else bmesh.new()
        if obj.mode != 'EDIT':
            bm.from_mesh(me)

        # Get active UV layer
        uv_layer = bm.loops.layers.uv.verify()
        
        # Get UV islands
        islands = ZENV_UVIslandOptimizer_Utils.get_uv_islands(bm, uv_layer)
        
        # Process each island
        for island in islands:
            # Get island center
            center = ZENV_UVIslandOptimizer_Utils.get_island_center(island, uv_layer)
            
            # Calculate offset to origin
            offset = -Vector((math.floor(center.x), math.floor(center.y)))
            
            # Move island
            for face in island:
                for loop in face.loops:
                    loop[uv_layer].uv += offset

        # Update mesh
        if obj.mode != 'EDIT':
            bm.to_mesh(me)
            bm.free()
        else:
            bmesh.update_edit_mesh(me)

        me.update()
        return {'FINISHED'}

class ZENV_PT_UVIslandOptimizer_Panel(bpy.types.Panel):
    """Panel for UV island optimization"""
    bl_label = "UV Optimize Islands"
    bl_idname = "ZENV_PT_uv_island_optimizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_OptimizeUVIslands.bl_idname)

# Registration
classes = (
    ZENV_OT_OptimizeUVIslands,
    ZENV_PT_UVIslandOptimizer_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
