bl_info = {
    "name": "MAT Rename Material add or remove affix ",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " add or remove customizable prefix and suffix to material names, for selected or all . Added to Side tab "
}

import bpy

# Operator for adding prefix or suffix to materials
class MATERIAL_OT_add(bpy.types.Operator):
    bl_idname = "material.add_custom"
    bl_label = "Add Custom Prefix/Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.StringProperty()  # "prefix" or "suffix"

    def execute(self, context):
        prefix = context.scene.custom_prefix
        suffix = context.scene.custom_suffix
        apply_to_all = context.scene.apply_to_all_materials

        def apply_prefix_suffix(obj):
            for mat_slot in obj.material_slots:
                if mat_slot.material:
                    if self.type == "prefix" and not mat_slot.material.name.startswith(prefix):
                        mat_slot.material.name = prefix + mat_slot.material.name
                    elif self.type == "suffix" and not mat_slot.material.name.endswith(suffix):
                        mat_slot.material.name += suffix

        if apply_to_all:
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    apply_prefix_suffix(obj)
        else:
            obj = context.object
            if obj and obj.type == 'MESH':
                apply_prefix_suffix(obj)

        return {'FINISHED'}

# Operator for removing prefix or suffix from materials
class MATERIAL_OT_remove(bpy.types.Operator):
    bl_idname = "material.remove_custom"
    bl_label = "Remove Custom Prefix/Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.StringProperty()  # "prefix" or "suffix"

    def execute(self, context):
        prefix = context.scene.custom_prefix
        suffix = context.scene.custom_suffix
        apply_to_all = context.scene.apply_to_all_materials

        def remove_prefix_suffix(obj):
            for mat_slot in obj.material_slots:
                if mat_slot.material:
                    if self.type == "prefix" and mat_slot.material.name.startswith(prefix):
                        mat_slot.material.name = mat_slot.material.name[len(prefix):]
                    elif self.type == "suffix" and mat_slot.material.name.endswith(suffix):
                        mat_slot.material.name = mat_slot.material.name[:-len(suffix)]

        if apply_to_all:
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    remove_prefix_suffix(obj)
        else:
            obj = context.object
            if obj and obj.type == 'MESH':
                remove_prefix_suffix(obj)

        return {'FINISHED'}

# Panel in the UI side tab
class MATERIAL_PT_custom_panel(bpy.types.Panel):
    bl_label = "Material Custom Prefix/Suffix"
    bl_idname = "ZENV_Material_Custom_Naming_Ops"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Prefix operations
        row = layout.row()
        row.label(text="Prefix:")
        row.prop(scene, "custom_prefix", text="")
        row = layout.row(align=True)
        row.operator("material.add_custom", text="Add").type = "prefix"
        row.operator("material.remove_custom", text="Remove").type = "prefix"
        layout.separator()

        # Suffix operations
        row = layout.row()
        row.label(text="Suffix:")
        row.prop(scene, "custom_suffix", text="")
        row = layout.row(align=True)
        row.operator("material.add_custom", text="Add").type = "suffix"
        row.operator("material.remove_custom", text="Remove").type = "suffix"
        layout.separator()

        # Apply to all materials checkbox
        layout.prop(scene, "apply_to_all_materials", text="Apply to All Materials in Scene")

# Registering the classes and properties
def register():
    bpy.utils.register_class(MATERIAL_OT_add)
    bpy.utils.register_class(MATERIAL_OT_remove)
    bpy.utils.register_class(MATERIAL_PT_custom_panel)
    bpy.types.Scene.custom_prefix = bpy.props.StringProperty(default="d_")
    bpy.types.Scene.custom_suffix = bpy.props.StringProperty(default="_MI")
    bpy.types.Scene.apply_to_all_materials = bpy.props.BoolProperty(default=False)

def unregister():
    bpy.utils.unregister_class(MATERIAL_OT_add)
    bpy.utils.unregister_class(MATERIAL_OT_remove)
    bpy.utils.unregister_class(MATERIAL_PT_custom_panel)
    del bpy.types.Scene.custom_prefix
    del bpy.types.Scene.custom_suffix
    del bpy.types.Scene.apply_to_all_materials

if __name__ == "__main__":
    register()
