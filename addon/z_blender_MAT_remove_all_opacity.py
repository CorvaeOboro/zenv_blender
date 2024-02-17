bl_info = {
    "name": "MAT Delete Opacity Textures",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Remove opacity textures on materials of selected object"
}   

import bpy

class ZENV_OT_DeleteOpacityTextures(bpy.types.Operator):
    """Delete textures connected to opacity of selected object"""
    bl_idname = "object.delete_opacity_textures"
    bl_label = "Delete Opacity Textures"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure there is an active object
        obj = context.active_object
        if not obj:
            self.report({'WARNING'}, "No active object selected")
            return {'CANCELLED'}

        # Ensure the active object has materials
        if not hasattr(obj.data, 'materials'):
            self.report({'WARNING'}, "Active object does not have materials")
            return {'CANCELLED'}

        # Iterate through materials of the selected object
        for mat_slot in obj.material_slots:
            mat = mat_slot.material
            if mat and mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        opacity_socket = node.inputs['Alpha']
                        if opacity_socket.is_linked:
                            for link in opacity_socket.links:
                                mat.node_tree.links.remove(link)

        return {'FINISHED'}

class ZENV_PT_DeleteOpacityTextures_Panel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "MAT Delete Opacity Textures"
    bl_idname = "ZENV_PT_DeleteOpacityTextures"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_DeleteOpacityTextures.bl_idname)

def register():
    bpy.utils.register_class(ZENV_OT_DeleteOpacityTextures)
    bpy.utils.register_class(ZENV_PT_DeleteOpacityTextures_Panel)

def unregister():
    bpy.utils.unregister_class(ZENV_OT_DeleteOpacityTextures)
    bpy.utils.unregister_class(ZENV_PT_DeleteOpacityTextures_Panel)

if __name__ == "__main__":
    register()
