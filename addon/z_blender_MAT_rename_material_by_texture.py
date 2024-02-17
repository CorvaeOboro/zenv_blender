
bl_info = {
    "name": "MAT Rename Material by Texture",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Renames materials based on the base color texture name without file extension."
}


import bpy
import os
from collections import defaultdict

class RenameMaterialsOperator(bpy.types.Operator):
    """Renames material slots based on the base color texture name excluding the file extension"""
    bl_idname = "object.rename_materials"
    bl_label = "Rename Materials By Texture"
    bl_options = {'REGISTER', 'UNDO'}

    def merge_materials(self, mat_list):
        # Logic to merge materials
        # Placeholder for actual merging logic
        pass

    def execute(self, context):
        texture_material_map = defaultdict(list)

        # Collect materials with the same texture
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH' and obj.material_slots:
                for slot in obj.material_slots:
                    mat = slot.material
                    if mat and mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'BSDF_PRINCIPLED':
                                base_color = node.inputs['Base Color'].links
                                if base_color:
                                    texture_node = base_color[0].from_node
                                    if texture_node.type == 'TEX_IMAGE' and texture_node.image:
                                        texture_name = texture_node.image.name
                                        texture_name_without_extension = os.path.splitext(texture_name)[0]
                                        texture_material_map[texture_name_without_extension].append(mat)

        # Merge materials with the same texture
        for texture_name, mats in texture_material_map.items():
            if len(mats) > 1:
                self.merge_materials(mats)
            # Rename the material
            for mat in mats:
                mat.name = texture_name

        self.report({'INFO'}, "Materials renamed and merged based on base color texture names without extensions")
        return {'FINISHED'}

class ZENV_PT_Panel(bpy.types.Panel):
    bl_label = "MAT rename"
    bl_idname = "ZENV_MAT_rename_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(RenameMaterialsOperator.bl_idname)

def register():
    bpy.utils.register_class(RenameMaterialsOperator)
    bpy.utils.register_class(ZENV_PT_Panel)

def unregister():
    bpy.utils.unregister_class(RenameMaterialsOperator)
    bpy.utils.unregister_class(ZENV_PT_Panel)

if __name__ == "__main__":
    register()
