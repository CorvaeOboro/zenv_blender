
bl_info = {
    "name": "MAT Remove Unassigned Materials",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Removes materials that are not assigned to any mesh faces",
}

import bpy

class OBJECT_OT_RemoveUnassignedMaterials(bpy.types.Operator):
    bl_idname = "object.remove_unassigned_materials"
    bl_label = "Remove Unassigned Materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                mesh = obj.data
                face_material_indices = {poly.material_index for poly in mesh.polygons}

                # Create a list of material slots to remove
                slots_to_remove = [i for i, slot in enumerate(obj.material_slots) if i not in face_material_indices]

                # Reverse the list to remove from the end to avoid index changes during removal
                for i in reversed(slots_to_remove):
                    mesh.materials.pop(index=i)
        
        self.report({'INFO'}, "Unassigned materials removed")
        return {'FINISHED'}

class ZENV_PT_RemoveUnassignedMaterialsPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "MAT unused"
    bl_idname = "ZENV_PT_remove_unassigned_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("object.remove_unassigned_materials")

def register():
    bpy.utils.register_class(OBJECT_OT_RemoveUnassignedMaterials)
    bpy.utils.register_class(ZENV_PT_RemoveUnassignedMaterialsPanel)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_RemoveUnassignedMaterials)
    bpy.utils.unregister_class(ZENV_PT_RemoveUnassignedMaterialsPanel)

if __name__ == "__main__":
    register()
