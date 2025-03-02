# VIEW FLAT TEXTURE MODE
# unlit , color view , no outlines

bl_info = {
    "name": "VIEW Flat Texture View",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Changes the viewport settings to flat color texture",
}  

import bpy

class ZENV_OT_flat_texture_view(bpy.types.Operator):
    """Set viewport to flat texture view across all 3D viewports in all screens"""
    bl_idname = "zenv.flat_texture_view"
    bl_label = "Flat Texture View"
    bl_options = {'REGISTER', 'UNDO'}

    def apply_shading_settings(self, space):
        """Apply flat texture view settings to a 3D view space"""
        shading = space.shading
        shading.type = 'SOLID'
        shading.light = 'FLAT'
        shading.color_type = 'TEXTURE'
        shading.show_object_outline = False

    def execute(self, context):
        # Store current screen and area
        current_screen = context.window.screen
        current_area = context.area

        # Apply settings to all 3D viewports in all screens
        processed_count = 0
        for window in context.window_manager.windows:
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        space = area.spaces.active
                        self.apply_shading_settings(space)
                        processed_count += 1

        # Report success
        self.report({'INFO'}, f"Applied flat texture view to {processed_count} viewports")
        return {'FINISHED'}


class ZENV_PT_FlatColorView_Panel(bpy.types.Panel):
    """Panel for flat color viewport display settings"""
    bl_label = "VIEW Flat Color"
    bl_idname = "ZENV_PT_flat_color_view"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_flat_texture_view.bl_idname)


def register():
    bpy.utils.register_class(ZENV_OT_flat_texture_view)
    bpy.utils.register_class(ZENV_PT_FlatColorView_Panel)


def unregister():
    bpy.utils.unregister_class(ZENV_OT_flat_texture_view)
    bpy.utils.unregister_class(ZENV_PT_FlatColorView_Panel)


if __name__ == "__main__":
    register()
