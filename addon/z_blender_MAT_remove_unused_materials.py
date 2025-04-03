"""
MAT Remove Unused Materials - A Blender addon for cleaning up materials.
1. Unassigns the materials from the objects material slotsthat are not used on faces.
2. Removes materials from scene that are not assigned to any objects.
"""

bl_info = {
    "name": "MAT Remove Unused Materials",
    "author": "CorvaeOboro",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV > MAT Remove Unused Materials",
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

    def get_materials_in_use(self, obj):
        """Get set of materials actually used by faces in this object."""
        materials_in_use = set()
        if not obj or obj.type != 'MESH' or not obj.data.materials:
            return materials_in_use

        # Handle linked objects
        mesh = obj.data
        if obj.library or mesh.library:
            # For linked objects, consider all materials as in use
            materials_in_use.update(mat for mat in mesh.materials if mat)
            return materials_in_use

        # Find which materials are actually used by faces
        for polygon in mesh.polygons:
            if polygon.material_index < len(mesh.materials):
                mat = mesh.materials[polygon.material_index]
                if mat:  # Only add non-None materials
                    # If material is linked, consider it in use
                    if mat.library or mat.override_library:
                        materials_in_use.add(mat)
                    else:
                        materials_in_use.add(mat)
        return materials_in_use

    def clean_mesh_materials(self, obj):
        """Clean up material slots for a mesh object."""
        if not obj or obj.type != 'MESH' or not obj.data.materials:
            return 0

        # Skip linked objects
        if obj.library or obj.data.library:
            return 0

        mesh = obj.data
        removed_count = 0
        
        # Find which material slots are actually used by faces
        used_slot_indices = set()
        for polygon in mesh.polygons:
            if polygon.material_index < len(mesh.materials):
                used_slot_indices.add(polygon.material_index)
        
        # Only remove slots that are empty or unused
        slots_to_remove = []
        for i, mat in enumerate(mesh.materials):
            if i not in used_slot_indices and (mat is None or mat not in self.get_materials_in_use(obj)):
                slots_to_remove.append(i)
                removed_count += 1
        
        # Remove unused slots from highest index to lowest to maintain proper indexing
        for slot_idx in sorted(slots_to_remove, reverse=True):
            mesh.materials.pop(index=slot_idx)
            # Update face indices that are higher than the removed slot
            for polygon in mesh.polygons:
                if polygon.material_index > slot_idx:
                    polygon.material_index -= 1
                elif polygon.material_index == slot_idx:
                    polygon.material_index = 0
        
        return removed_count

    def execute(self, context):
        """Execute the material removal operation."""
        try:
            # Track materials actually in use by faces
            used_materials = set()
            total_slots_removed = 0
            objects_cleaned = 0
            
            # First pass: Clean up material slots in meshes and collect truly used materials
            # Include objects from all scenes to handle linked data
            for scene in bpy.data.scenes:
                for obj in scene.objects:
                    if obj.type == 'MESH':
                        # Clean up slots
                        slots_removed = self.clean_mesh_materials(obj)
                        if slots_removed > 0:
                            objects_cleaned += 1
                            total_slots_removed += slots_removed
                        
                        # Add materials that are actually used by faces
                        used_materials.update(self.get_materials_in_use(obj))
            
            # Also check objects in all collections (including nested ones)
            def process_collection(collection):
                for obj in collection.objects:
                    if obj.type == 'MESH':
                        used_materials.update(self.get_materials_in_use(obj))
                for child in collection.children:
                    process_collection(child)

            for collection in bpy.data.collections:
                process_collection(collection)
            
            # Remove unused materials from the scene
            initial_mat_count = len(bpy.data.materials)
            materials_to_remove = []
            
            for mat in bpy.data.materials:
                # Skip linked or override materials
                if mat.library or mat.override_library:
                    continue
                # Skip materials used by any object
                if mat not in used_materials:
                    materials_to_remove.append(mat)
            
            for mat in materials_to_remove:
                if not mat.users and not mat.use_fake_user:
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

class ZENV_PT_RemoveUnusedMaterials_Panel(Panel):
    """Panel for removing unused materials."""
    bl_label = "MAT Remove Unused Materials"
    bl_idname = "ZENV_PT_remove_unused_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        layout.operator(ZENV_OT_RemoveUnusedMaterials.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_RemoveUnusedMaterials,
    ZENV_PT_RemoveUnusedMaterials_Panel,
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
