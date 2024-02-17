
bl_info = {
    "name": "Flip UVs",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Flip UVs either vertically or horizontally",
}   
import bpy
import bmesh

def flip_uvs(bm, horizontal=False, vertical=False):
    uv_layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        for loop in face.loops:
            uv = loop[uv_layer].uv
            if horizontal:
                uv.x = -uv.x
            if vertical:
                uv.y = -uv.y

class FlipUVsHorizontal(bpy.types.Operator):
    """Flip UVs Horizontally"""
    bl_idname = "uv.flip_uvs_horizontal"
    bl_label = "Flip UVs Horizontally"
    
    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        flip_uvs(bm, horizontal=True)
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}

class FlipUVsVertical(bpy.types.Operator):
    """Flip UVs Vertically"""
    bl_idname = "uv.flip_uvs_vertical"
    bl_label = "Flip UVs Vertically"

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        flip_uvs(bm, vertical=True)
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(FlipUVsHorizontal.bl_idname)
    self.layout.operator(FlipUVsVertical.bl_idname)

def register():
    bpy.utils.register_class(FlipUVsHorizontal)
    bpy.utils.register_class(FlipUVsVertical)
    bpy.types.IMAGE_MT_uvs.append(menu_func)

def unregister():
    bpy.utils.unregister_class(FlipUVsHorizontal)
    bpy.utils.unregister_class(FlipUVsVertical)
    bpy.types.IMAGE_MT_uvs.remove(menu_func)

if __name__ == "__main__":
    register()
