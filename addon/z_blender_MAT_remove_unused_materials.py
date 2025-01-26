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

    def clean_mesh_materials(self, obj):
        """Clean up material slots for a mesh object."""
        if not obj or obj.type != 'MESH' or not obj.data.materials:
            return 0

        mesh = obj.data
        materials_in_use = set()
        removed_count = 0
        
        # Find which materials are actually used by faces
        for polygon in mesh.polygons:
            if polygon.material_index < len(mesh.materials):
                materials_in_use.add(polygon.material_index)
        
        # Create mapping for new material indices
        old_to_new = {}
        new_index = 0
        materials_to_keep = []
        
        # Build list of materials to keep and create index mapping
        for i, mat in enumerate(mesh.materials):
            if i in materials_in_use:
                old_to_new[i] = new_index
                materials_to_keep.append(mat)
                new_index += 1
            else:
                removed_count += 1
        
        # Update face material indices
        for polygon in mesh.polygons:
            if polygon.material_index in old_to_new:
                polygon.material_index = old_to_new[polygon.material_index]
            else:
                polygon.material_index = 0
        
        # Clear material slots
        mesh.materials.clear()
        
        # Reassign kept materials
        for mat in materials_to_keep:
            mesh.materials.append(mat)
        
        return removed_count

    def execute(self, context):
        """Execute the material removal operation."""
        try:
            # Track materials in use
            used_materials = set()
            total_slots_removed = 0
            objects_cleaned = 0
            
            # First pass: Clean up material slots in meshes
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    slots_removed = self.clean_mesh_materials(obj)
                    if slots_removed > 0:
                        objects_cleaned += 1
                        total_slots_removed += slots_removed
            
            # Second pass: Collect materials still in use
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.data.materials:
                    for mat in obj.data.materials:
                        if mat:
                            used_materials.add(mat)
            
            # Remove unused materials from the scene
            initial_mat_count = len(bpy.data.materials)
            materials_to_remove = [mat for mat in bpy.data.materials if mat not in used_materials]
            
            for mat in materials_to_remove:
                bpy.data.materials.remove(mat)
            
            removed_mat_count = initial_mat_count - len(bpy.data.materials)
            
            # Report results
            if removed_mat_count > 0 or total_slots_removed > 0:
                message = []
                if removed_mat_count > 0:
                    message.append(f"Removed {removed_mat_count} unused materials")
                if total_slots_removed > 0:
                    message.append(f"Cleaned {total_slots_removed} unused material slots from {objects_cleaned} objects")
                self.report({'INFO'}, ". ".join(message))
            else:
                self.report({'INFO'}, "No unused materials found")
            
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
