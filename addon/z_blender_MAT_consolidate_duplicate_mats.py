bl_info = {
    "name": 'MAT Consolidate Materials by Texture',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Consolidates materials based on base color texture',
    "status": 'working',
    "approved": True,
    "sort_priority": '33',
    "group": 'Material',
    "group_prefix": 'MAT',
    "description_short": 'reduce to one material per texture',
    "description_long": """
MATERIAL CONSOLIDATE BY TEXTURE
 consolidates materials based on base color texture
useful for cleaning up duplicate materials
""",
    "location": 'View3D > ZENV',
}

import bpy

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_ConsolidateMaterials_Operator(bpy.types.Operator):
    """Consolidate materials by their base color texture"""
    bl_idname = "zenv.consolidatematerials_consolidate"
    bl_label = "Consolidate Materials by Texture"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    @staticmethod
    def consolidate_materials_by_texture(context):
        """Consolidate materials based on their base color texture"""
        obj = context.active_object

        if obj is None or obj.type != 'MESH':
            return

        mats = obj.data.materials
        texture_to_materials = {}
        
        # Map textures to materials
        for mat in mats:
            if mat is not None and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED' and node.inputs['Base Color'].links:
                        texture_node = node.inputs['Base Color'].links[0].from_node
                        if texture_node.type == 'TEX_IMAGE' and texture_node.image:
                            texture_name = texture_node.image.name
                            if texture_name not in texture_to_materials:
                                texture_to_materials[texture_name] = []
                            texture_to_materials[texture_name].append(mat.name)
                            break

        # Reassign faces and remove unused materials
        for texture_name, mat_names in texture_to_materials.items():
            base_mat_name = texture_name if texture_name in mats else mat_names[0]
            base_mat = bpy.data.materials.get(base_mat_name)
            if base_mat is None or len(mat_names) <= 1:
                continue
            
            for poly in obj.data.polygons:
                if mats[poly.material_index].name in mat_names:
                    poly.material_index = mats.find(base_mat.name)

            # Clean up unused materials
            for mat_name in mat_names:
                if mat_name != base_mat_name:
                    mat = bpy.data.materials.get(mat_name)
                    if mat:
                        bpy.data.materials.remove(mat)

    def execute(self, context):
        try:
            self.consolidate_materials_by_texture(context)
            self.report({'INFO'}, "Materials consolidated successfully")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error consolidating materials: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_ConsolidateMaterials_Panel(bpy.types.Panel):
    """Panel for material consolidation tools"""
    bl_label = "MAT Consolidate Materials"
    bl_idname = "ZENV_PT_consolidate_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.consolidatematerials_consolidate", icon='NODE_MATERIAL')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_ConsolidateMaterials_Operator,
    ZENV_PT_ConsolidateMaterials_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
