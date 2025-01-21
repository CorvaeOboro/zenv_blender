"""
MAT Remove Unused Materials - A Blender addon for cleaning up materials.

Removes materials that are not assigned to any objects or faces.
"""

bl_info = {
    "name": "MAT Remove Unused Materials",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Remove unused materials and materials with no faces",
    "category": "ZENV",
}

import bpy
from bpy.types import Operator, Panel

class ZENV_OT_RemoveUnusedMaterials(Operator):
    """Remove materials that are not used by any objects or faces."""
    bl_idname = "zenv.remove_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the material removal operation."""
        try:
            # Track materials in use
            used_materials = set()
            materials_with_faces = set()
            
            # Check all objects in the scene
            for obj in bpy.data.objects:
                if obj.type != 'MESH':
                    continue
                    
                mesh = obj.data
                
                # Check materials assigned to the object
                for slot in obj.material_slots:
                    if slot.material:
                        used_materials.add(slot.material)
                
                # Check materials actually used by faces
                if mesh.polygons and mesh.materials:
                    for polygon in mesh.polygons:
                        if polygon.material_index < len(mesh.materials):
                            mat = mesh.materials[polygon.material_index]
                            if mat:
                                materials_with_faces.add(mat)
            
            # Remove unused materials
            initial_count = len(bpy.data.materials)
            materials_to_remove = []
            
            for mat in bpy.data.materials:
                # Check if material is used and has faces
                if mat not in used_materials or mat not in materials_with_faces:
                    materials_to_remove.append(mat)
            
            # Remove the materials
            for mat in materials_to_remove:
                bpy.data.materials.remove(mat)
            
            # Report results
            removed_count = initial_count - len(bpy.data.materials)
            if removed_count > 0:
                self.report(
                    {'INFO'}, 
                    f"Removed {removed_count} unused materials"
                )
            else:
                self.report(
                    {'INFO'}, 
                    "No unused materials found"
                )
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error removing materials: {str(e)}")
            return {'CANCELLED'}

class ZENV_PT_RemoveUnusedMaterialsPanel(Panel):
    """Panel for removing unused materials."""
    bl_label = "Remove Unused Materials"
    bl_idname = "ZENV_PT_remove_unused_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        box = layout.box()
        box.label(text="Clean Up:", icon='MATERIAL')
        box.operator(ZENV_OT_RemoveUnusedMaterials.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_RemoveUnusedMaterials,
    ZENV_PT_RemoveUnusedMaterialsPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
