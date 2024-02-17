
bl_info = {
    "name": "MESH Rename objects by Material",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " Rename each mesh, object, and collection by the material assigned to it"
}   

import bpy

def rename_objects_by_material():
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            mat_name = obj.material_slots[0].material.name if obj.material_slots else "NoMaterial"
            obj.name = mat_name
            obj.data.name = mat_name
    
    for coll in bpy.data.collections:
        materials = set()
        for obj in coll.objects:
            if obj.type == 'MESH':
                mat_name = obj.material_slots[0].material.name if obj.material_slots else "NoMaterial"
                materials.add(mat_name)
        
        if materials:
            coll.name = next(iter(materials))  # Use the first material found
        else:
            coll.name = "NoMaterial"

class RenameByMaterialOperator(bpy.types.Operator):
    """Rename Meshes, Objects and Collections by Material"""
    bl_idname = "object.rename_by_material"
    bl_label = "Rename by Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rename_objects_by_material()
        return {'FINISHED'}

class ZENV_PT_RenameByMaterialPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "MESH Rename by Material"
    bl_idname = "ZENV_PT_rename_by_material"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("object.rename_by_material")

def register():
    bpy.utils.register_class(RenameByMaterialOperator)
    bpy.utils.register_class(ZENV_PT_RenameByMaterialPanel)

def unregister():
    bpy.utils.unregister_class(RenameByMaterialOperator)
    bpy.utils.unregister_class(ZENV_PT_RenameByMaterialPanel)

if __name__ == "__main__":
    register()
