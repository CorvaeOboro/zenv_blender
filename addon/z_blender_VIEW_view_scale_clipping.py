# VIEW Scale Clipping
# adjusts viewport clipping and view settings based on object size

bl_info = {
    "name": "VIEW Scale Clipping",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Adjust viewport clipping based on object size"
}  

import bpy
import bmesh
import mathutils
from bpy.types import Panel, Operator

class ZENV_ViewportUtils:
    """Utility functions for viewport management"""
    
    @staticmethod
    def get_object_size(obj):
        """Get object size considering all geometry"""
        if not obj:
            return 0.0
            
        # Get world matrix
        world_matrix = obj.matrix_world
        
        # Handle different object types
        if obj.type == 'MESH':
            # Use bmesh for accurate bounds
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.transform(bm, matrix=world_matrix, verts=bm.verts)
            
            # Get bounds
            bounds = [v.co for v in bm.verts]
            bm.free()
            
        elif obj.type == 'CURVE':
            # Get curve points
            bounds = []
            for spline in obj.data.splines:
                if spline.type == 'BEZIER':
                    bounds.extend([world_matrix @ p.co for p in spline.bezier_points])
                else:
                    bounds.extend([world_matrix @ p.co for p in spline.points])
                    
        elif obj.type in {'EMPTY', 'CAMERA', 'LIGHT'}:
            # Use object location and display size
            bounds = [world_matrix.translation]
            size = obj.empty_display_size if obj.type == 'EMPTY' else 1.0
            bounds.extend([
                world_matrix @ mathutils.Vector((size, 0, 0)),
                world_matrix @ mathutils.Vector((0, size, 0)),
                world_matrix @ mathutils.Vector((0, 0, size))
            ])
            
        else:
            # Fallback to dimensions
            size = max(obj.dimensions)
            loc = world_matrix.translation
            bounds = [loc + mathutils.Vector((size, size, size))]
            
        # Calculate max distance from origin
        if bounds:
            return max(p.length for p in bounds)
        return 0.0
    
    @staticmethod
    def update_viewport_settings(context):
        """Update viewport settings based on object size"""
        # Default settings
        settings = {
            'scope': 'ALL',  # Use all objects by default
            'clip_start_factor': 0.01,
            'clip_end_factor': 10.0,
            'view_lens': 50.0
        }
        
        # Get largest object size
        max_size = 0.0
        active_obj = None
        
        objects = context.scene.objects  # Always use all objects
            
        for obj in objects:
            size = ZENV_ViewportUtils.get_object_size(obj)
            if size > max_size:
                max_size = size
                active_obj = obj
                
        if max_size == 0.0:
            return False
            
        # Update viewport settings
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Update clipping
                        space.clip_start = max_size * settings['clip_start_factor']
                        space.clip_end = max_size * settings['clip_end_factor']
                        space.lens = settings['view_lens']
                            
        # Focus view on object
        if active_obj:
            context.view_layer.objects.active = active_obj
            bpy.ops.view3d.view_selected()
            
        return True

class ZENV_OT_UpdateViewport(Operator):
    """Update viewport settings based on object size"""
    bl_idname = "zenv.update_viewport"
    bl_label = "View Fit Bounds"
    bl_description = "Adjust viewport clipping to fit scene bounds"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return bool(context.scene.objects)
    
    def execute(self, context):
        if ZENV_ViewportUtils.update_viewport_settings(context):
            self.report({'INFO'}, "Updated viewport settings")
        else:
            self.report({'WARNING'}, "No valid objects found")
            
        return {'FINISHED'}

class ZENV_PT_ViewportPanel(Panel):
    """Panel for viewport settings"""
    bl_label = "View Scale"
    bl_idname = "ZENV_PT_viewport"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_UpdateViewport.bl_idname)

classes = (
    ZENV_OT_UpdateViewport,
    ZENV_PT_ViewportPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
