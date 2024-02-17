bl_info = {
    "name": "VIEW Flat Texture View",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Changes the viewport settings to flat color texture",
}  

import bpy


class ZENV_OT_flat_texture_view(bpy.types.Operator):
    """Set viewport to flat texture view"""
    bl_idname = "zenv.flat_texture_view"
    bl_label = "Flat Texture View"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                shading = space.shading
                shading.type = 'SOLID'
                shading.light = 'FLAT'
                shading.color_type = 'TEXTURE'
        return {'FINISHED'}


class ZENV_PT_panel(bpy.types.Panel):
    bl_label = "VIEW"
    bl_idname = "ZENV_VIEW_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_flat_texture_view.bl_idname)


def register():
    bpy.utils.register_class(ZENV_OT_flat_texture_view)
    bpy.utils.register_class(ZENV_PT_panel)


def unregister():
    bpy.utils.unregister_class(ZENV_OT_flat_texture_view)
    bpy.utils.unregister_class(ZENV_PT_panel)


if __name__ == "__main__":
    register()
