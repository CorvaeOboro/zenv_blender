# RENDER SCALE PER PIXEL
# Calculate render scale based on desired pixels per unit

bl_info = {
    "name": "RENDER Scale Per Pixel",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Calculate render scale based on desired pixels per unit",
}

import bpy
import math
import logging
from bpy.props import FloatProperty, IntProperty, BoolProperty

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_RenderScale_Properties:
    """Property management for render scale addon"""
    
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_pixels_per_unit = IntProperty(
            name="Pixels Per Unit",
            description="Desired number of pixels per Blender unit",
            default=512,
            min=1,
            max=4096
        )
        
        bpy.types.Scene.zenv_target_width = IntProperty(
            name="Target Width",
            description="Target width in pixels",
            default=2048,
            min=1,
            max=16384
        )
        
        bpy.types.Scene.zenv_target_height = IntProperty(
            name="Target Height",
            description="Target height in pixels",
            default=2048,
            min=1,
            max=16384
        )
        
        bpy.types.Scene.zenv_auto_update = BoolProperty(
            name="Auto Update",
            description="Automatically update render settings when values change",
            default=False
        )
        
        bpy.types.Scene.zenv_maintain_aspect = BoolProperty(
            name="Maintain Aspect Ratio",
            description="Maintain aspect ratio when adjusting dimensions",
            default=True
        )
        
        bpy.types.Scene.zenv_camera_distance = FloatProperty(
            name="Camera Distance",
            description="Distance from camera to subject",
            default=1.0,
            min=0.01,
            precision=3
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_pixels_per_unit
        del bpy.types.Scene.zenv_target_width
        del bpy.types.Scene.zenv_target_height
        del bpy.types.Scene.zenv_auto_update
        del bpy.types.Scene.zenv_maintain_aspect
        del bpy.types.Scene.zenv_camera_distance

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_RenderScale_Utils:
    """Utility functions for render scale calculations"""
    
    @staticmethod
    def log_info(message):
        """Log to both console and Blender info"""
        logger.info(message)
        if hasattr(bpy.context, 'window_manager'):
            bpy.context.window_manager.popup_menu(
                lambda self, context: self.layout.label(text=message),
                title="Info",
                icon='INFO'
            )
    
    @staticmethod
    def get_camera_fov(camera):
        """Get camera field of view in radians"""
        if camera.type != 'CAMERA':
            return None
            
        if camera.data.type == 'PERSP':
            return camera.data.angle
        elif camera.data.type == 'ORTHO':
            return math.atan(camera.data.ortho_scale / 2.0) * 2.0
        return None
    
    @staticmethod
    def calculate_render_scale(context):
        """Calculate render scale based on pixels per unit"""
        scene = context.scene
        camera = scene.camera
        
        if not camera:
            ZENV_RenderScale_Utils.log_info("No active camera found")
            return
        
        # Get camera FOV
        fov = ZENV_RenderScale_Utils.get_camera_fov(camera)
        if fov is None:
            ZENV_RenderScale_Utils.log_info("Invalid camera type")
            return
        
        # Calculate visible area at camera distance
        distance = scene.zenv_camera_distance
        visible_width = 2.0 * distance * math.tan(fov / 2.0)
        
        # Calculate required resolution
        pixels_per_unit = scene.zenv_pixels_per_unit
        required_pixels = int(visible_width * pixels_per_unit)
        
        # Update render settings
        render = scene.render
        if scene.zenv_maintain_aspect:
            aspect_ratio = render.resolution_y / render.resolution_x
            render.resolution_x = required_pixels
            render.resolution_y = int(required_pixels * aspect_ratio)
        else:
            render.resolution_x = required_pixels
            render.resolution_y = required_pixels
        
        ZENV_RenderScale_Utils.log_info(f"Updated render resolution to {render.resolution_x}x{render.resolution_y}")
        return True
    
    @staticmethod
    def update_target_resolution(context):
        """Update render resolution to match target dimensions"""
        scene = context.scene
        render = scene.render
        
        render.resolution_x = scene.zenv_target_width
        if scene.zenv_maintain_aspect:
            aspect_ratio = render.resolution_y / render.resolution_x
            render.resolution_y = int(scene.zenv_target_width * aspect_ratio)
        else:
            render.resolution_y = scene.zenv_target_height
        
        ZENV_RenderScale_Utils.log_info(f"Updated render resolution to {render.resolution_x}x{render.resolution_y}")
        return True

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_RenderScale_Calculate(bpy.types.Operator):
    """Calculate render scale based on pixels per unit"""
    bl_idname = "zenv.renderscale_calculate"
    bl_label = "Calculate Scale"
    bl_description = "Calculate render scale based on pixels per unit"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.scene.camera is not None
    
    def execute(self, context):
        try:
            if ZENV_RenderScale_Utils.calculate_render_scale(context):
                return {'FINISHED'}
            return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Error calculating render scale: {str(e)}")
            self.report({'ERROR'}, f"Calculation failed: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_RenderScale_UpdateResolution(bpy.types.Operator):
    """Update render resolution to match target dimensions"""
    bl_idname = "zenv.renderscale_update_resolution"
    bl_label = "Update Resolution"
    bl_description = "Update render resolution to match target dimensions"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            if ZENV_RenderScale_Utils.update_target_resolution(context):
                return {'FINISHED'}
            return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Error updating resolution: {str(e)}")
            self.report({'ERROR'}, f"Update failed: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RenderScale_Panel(bpy.types.Panel):
    """Panel for render scale tools"""
    bl_label = "RENDER Scale Per Pixel"
    bl_idname = "ZENV_PT_renderscale"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Settings
        box = layout.box()
        box.label(text="Scale Settings:")
        box.prop(scene, "zenv_pixels_per_unit")
        box.prop(scene, "zenv_camera_distance")
        box.prop(scene, "zenv_maintain_aspect")
        box.operator("zenv.renderscale_calculate")
        
        # Target Resolution
        box = layout.box()
        box.label(text="Target Resolution:")
        box.prop(scene, "zenv_target_width")
        if not scene.zenv_maintain_aspect:
            box.prop(scene, "zenv_target_height")
        box.prop(scene, "zenv_auto_update")
        box.operator("zenv.renderscale_update_resolution")
        
        # Current Resolution
        box = layout.box()
        box.label(text="Current Resolution:")
        box.label(text=f"Width: {scene.render.resolution_x}px")
        box.label(text=f"Height: {scene.render.resolution_y}px")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_RenderScale_Calculate,
    ZENV_OT_RenderScale_UpdateResolution,
    ZENV_PT_RenderScale_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_RenderScale_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_RenderScale_Properties.unregister()

if __name__ == "__main__":
    register()
