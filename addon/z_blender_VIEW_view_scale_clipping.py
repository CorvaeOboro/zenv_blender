bl_info = {
    "name": "VIEW Clipping scale relative",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Changes the viewport settings Clip End to fit object",
}  

import bpy


class ZENV_OT_SetViewportClippingAndView(bpy.types.Operator):
    """Set viewport to match clipping range to object size"""
    bl_idname = "zenv.view_clipping_fit"
    bl_label = "VIEW Clipping Fit"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        largest_object = None
        largest_size = 0

        # Find the largest object
        for obj in bpy.data.objects:
            if obj.select_get():  # Only consider selected objects
                size = max(obj.dimensions)
                if size > largest_size:
                    largest_size = size
                    largest_object = obj

        # Set the viewport clipping
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.clip_end = largest_size * 1.5  # Adjust multiplier as needed

        # Center view on the largest object if it exists
        if largest_object:
            bpy.context.view_layer.objects.active = largest_object
            bpy.ops.view3d.view_selected()

        return {'FINISHED'}


class ZENV_PT_SetViewportClippingAndView_panel(bpy.types.Panel):
    bl_label = "VIEW_CLIP"
    bl_idname = "ZENV_VIEW_PT_SetViewportClippingAndView_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_SetViewportClippingAndView.bl_idname)


def register():
    bpy.utils.register_class(ZENV_OT_SetViewportClippingAndView)
    bpy.utils.register_class(ZENV_PT_SetViewportClippingAndView_panel)


def unregister():
    bpy.utils.unregister_class(ZENV_OT_SetViewportClippingAndView)
    bpy.utils.unregister_class(ZENV_PT_SetViewportClippingAndView_panel)


if __name__ == "__main__":
    register()
