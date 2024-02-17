bl_info = {
    "name": "MAT Rename Material add or remove suffix",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Adds or removes _MI suffix to materials"
}

import bpy

# Operator for adding suffix to materials
class MATERIAL_OT_suffix_add(bpy.types.Operator):
    bl_idname = "material.add_suffix"
    bl_label = "Add _MI Suffix to Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj and obj.type == 'MESH':
            for mat_slot in obj.material_slots:
                if mat_slot.material and not mat_slot.material.name.endswith("_MI"): # only add suffix if not already there
                    mat_slot.material.name += "_MI"
        return {'FINISHED'}

# Operator for removing suffix from materials
class MATERIAL_OT_suffix_remove(bpy.types.Operator):
    bl_idname = "material.remove_suffix"
    bl_label = "Remove _MI Suffix from Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj and obj.type == 'MESH':
            for mat_slot in obj.material_slots:
                if mat_slot.material and mat_slot.material.name.endswith("_MI"): # only remove suffix if is there
                    mat_slot.material.name = mat_slot.material.name[:-3]  # Removing the last 3 characters "_MI"
        return {'FINISHED'}

# Panel in the UI
class MATERIAL_PT_custom_panel(bpy.types.Panel):
    bl_label = "Material Suffix Operations"
    bl_idname = "ZENV_Material_Naming_Ops"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(MATERIAL_OT_suffix_add.bl_idname)
        layout.operator(MATERIAL_OT_suffix_remove.bl_idname)

# Registering the classes
def register():
    bpy.utils.register_class(MATERIAL_OT_suffix_add)
    bpy.utils.register_class(MATERIAL_OT_suffix_remove)
    bpy.utils.register_class(MATERIAL_PT_custom_panel)

def unregister():
    bpy.utils.unregister_class(MATERIAL_OT_suffix_add)
    bpy.utils.unregister_class(MATERIAL_OT_suffix_remove)
    bpy.utils.unregister_class(MATERIAL_PT_custom_panel)

if __name__ == "__main__":
    register()
