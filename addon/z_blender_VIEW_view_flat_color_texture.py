#region META
bl_info = {
    "name": 'VIEW Flat Texture View',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Changes the viewport settings to flat color texture',
    "status": 'working',
    "approved": True,
    "group": 'View',
    "group_prefix": 'VIEW',
    "group_order": 70,
    "addon_order": 10,
    "tags": ['viewport', 'flat', 'texture', 'shading'],
    "description_short": 'quickview flat color texture , unlit viewmode',
    "description_medium": 'Sets all 3D viewports to SOLID shading with FLAT light, TEXTURE color type, and no object outlines.',
    "description_long": """
VIEW FLAT TEXTURE MODE
 unlit , color view , no outlines
""",
    "location": '3D View > Sidebar > ZENV',
    "image_overview": 'zenv_blender_VIEW_view_flat_color_texture.png',
    "addon_image": 'zenv_blender_VIEW_view_flat_color_texture.png',
}

#region IMPORT
import bpy
import logging
from bpy.types import Operator, Panel

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region OP
class ZENV_OT_FlatTextureView(Operator):
    """Set viewport to flat texture view across all 3D viewports in all screens"""
    bl_idname = "zenv.flat_texture_view"
    bl_label = "Flat Texture View"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when at least one 3D viewport exists."""
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    return True
        return False

    def apply_shading_settings(self, space):
        """Apply flat texture view settings to a 3D view space"""
        shading = space.shading
        shading.type = 'SOLID'
        shading.light = 'FLAT'
        shading.color_type = 'TEXTURE'
        shading.show_object_outline = False

    def execute(self, context):
        """Execute the flat texture view application across all 3D viewports."""
        try:
            # Apply settings to all 3D viewports in all screens
            processed_count = 0
            seen_spaces = set()
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type != 'VIEW_3D':
                        continue
                    space = area.spaces.active
                    if space is None:
                        continue
                    if space.as_pointer() in seen_spaces:
                        continue
                    seen_spaces.add(space.as_pointer())
                    self.apply_shading_settings(space)
                    processed_count += 1

            # Report success
            self.report({'INFO'}, f"Applied flat texture view to {processed_count} viewports")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to apply flat texture view")
            self.report({'ERROR'}, f"Error applying flat texture view: {str(e)}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_FlatColorView(Panel):
    """Panel for flat color viewport display settings"""
    bl_label = "VIEW Flat Color"
    bl_idname = "ZENV_PT_flat_color_view"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_FlatTextureView.bl_idname)

#endregion
#region REG
classes = (
    ZENV_OT_FlatTextureView,
    ZENV_PT_FlatColorView,
)

def register():
    """Register all addon classes and configure the module logger handler."""
    global _logger_handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    if _logger_handler is None:
        _logger_handler = logging.StreamHandler()
        _logger_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
        logger.addHandler(_logger_handler)
    if not logger.level:
        logger.setLevel(logging.INFO)

def unregister():
    """Unregister all addon classes and remove the module logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
