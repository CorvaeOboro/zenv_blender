bl_info = {
    "name": "MESH Separate Mesh by Material",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Separate mesh based on materials into different objects",
}

import bpy

MAX_MATERIALS = 10000  # Set the maximum number of materials to operate on

class SeparateMeshByMaterial(bpy.types.Operator):
    """Separate Mesh by Material"""
    bl_idname = "object.separate_mesh_by_material"
    bl_label = "Separate Mesh by Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure the active object is a mesh
        active_obj = context.active_object
        if active_obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh.")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')

        # Iterate over each material
        for mat_index, material in enumerate(active_obj.data.materials[:MAX_MATERIALS]):
            bpy.ops.object.select_all(action='DESELECT')
            active_obj.select_set(True)
            context.view_layer.objects.active = active_obj

            # Select faces with the current material
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            face_count = 0
            for polygon in active_obj.data.polygons:
                if polygon.material_index == mat_index:
                    polygon.select = True
                    face_count += 1

            if face_count == 0:
                continue  # Skip if no faces are assigned to this material

            bpy.ops.object.mode_set(mode='EDIT')

            # Separate the selected faces into a new object
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.object.mode_set(mode='OBJECT')

            # Rename the new object to match the material name
            new_obj = context.selected_objects[-1]
            new_obj.name = material.name if material else f"Material_{mat_index}"

        # Keep the original object
        self.report({'INFO'}, f"Mesh separated for up to {MAX_MATERIALS} materials into objects named after materials.")
        return {'FINISHED'}

class ZENV_PT_Panel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "MESH split"
    bl_idname = "ZENV_MESH_Separate_panel_a"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(SeparateMeshByMaterial.bl_idname)

def register():
    bpy.utils.register_class(SeparateMeshByMaterial)
    bpy.utils.register_class(ZENV_PT_Panel)

def unregister():
    bpy.utils.unregister_class(SeparateMeshByMaterial)
    bpy.utils.unregister_class(ZENV_PT_Panel)

if __name__ == "__main__":
    register()
