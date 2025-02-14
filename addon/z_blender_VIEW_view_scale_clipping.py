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
            'clip_start_factor': 0.01,  # Start clipping at 1% of max size
            'clip_end_factor': 5.0,     # End clipping at 5x max size (reduced from 10x)
            'view_lens': 50.0,          # Standard lens
            'zoom_factor': 0.5          # Zoom factor to get closer to objects
        }
        
        # Get largest object size
        max_size = 0.0
        active_obj = None
        bounds_center = mathutils.Vector((0, 0, 0))
        total_objects = 0
        
        objects = context.scene.objects  # Always use all objects
            
        for obj in objects:
            size = ZENV_ViewportUtils.get_object_size(obj)
            if size > max_size:
                max_size = size
                active_obj = obj
            bounds_center += obj.matrix_world.translation
            total_objects += 1
                
        if max_size == 0.0 or total_objects == 0:
            return False

        # Calculate average center and adjusted size
        bounds_center /= total_objects
        adjusted_size = max_size * settings['zoom_factor']  # Use half the max size for closer view

        # Calculate clip values
        clip_start = max(adjusted_size * settings['clip_start_factor'], 0.001)
        clip_end = adjusted_size * settings['clip_end_factor']
            
        # Update viewport settings across all screens
        processed_count = 0
        for window in context.window_manager.windows:
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                # Update clip values
                                space.clip_start = clip_start
                                space.clip_end = clip_end
                                # Update lens
                                space.lens = settings['view_lens']
                                
                                # Update view distance for closer look
                                region3d = space.region_3d
                                if region3d:
                                    # Set view distance based on adjusted size
                                    region3d.view_distance = adjusted_size * 2
                                    # Look at center of bounds
                                    region3d.view_location = bounds_center
                                
                                processed_count += 1
        
        return processed_count

class ZENV_OT_UpdateViewport(Operator):
    """Update viewport settings based on object size across all viewports"""
    bl_idname = "zenv.update_viewport"
    bl_label = "View Fit Bounds"
    bl_description = "Adjust viewport clipping to fit scene bounds in all viewports"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.scene.objects
        
    def execute(self, context):
        # Store current screen and area
        current_screen = context.window.screen
        current_area = context.area
        
        # Update all viewports
        processed_count = ZENV_ViewportUtils.update_viewport_settings(context)
        
        if processed_count:
            self.report({'INFO'}, f"Updated {processed_count} viewports to fit scene bounds")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No objects found to calculate bounds")
            return {'CANCELLED'}

class ZENV_PT_ViewportPanel(Panel):
    """Panel for viewport settings"""
    bl_label = "VIEW Bounds Scale"
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
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
