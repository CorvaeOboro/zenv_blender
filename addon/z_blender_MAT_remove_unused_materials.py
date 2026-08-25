#region META
bl_info = {
    "name": 'MAT Remove Unused Materials',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Remove unused materials and materials with no faces',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 10,
    "tags": ['material', 'unused', 'remove', 'cleanup', 'slots', 'optimize'],
    "description_short": 'remove unused materials',
    "description_medium": 'Performs two operations: (1) For each mesh object, removes material slots not referenced by any polygon, remapping polygon material indices in a single pass so the result is consistent even when slot 0 itself is removed. (2) After slot cleanup, removes materials from bpy.data.materials that are not used by any object faces and have zero users (no fake user). Linked and override materials are skipped.',
    "description_long": """
MAT Remove Unused Materials - A Blender addon for cleaning up materials.
1. Unassigns the materials from the objects material slots that are not used on faces.
2. Removes materials from scene that are not assigned to any objects.
""",
    "image_overview": 'zenv_blender_MAT_remove_unused_materials.png',
    "addon_image": 'addon_remove_unused_mat_diagram.jpg',
    "location": 'View3D > Sidebar > ZENV > MAT Remove Unused Materials',
}
#endregion

#region IMPORT
import bpy
from bpy.types import Operator, Panel
#endregion


#region OP
# Operator that removes unused material slots and unreferenced materials.

class ZENV_OT_RemoveUnusedMaterials(Operator):
    """Remove materials that are not used by any objects or faces."""
    bl_idname = "zenv.remove_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def get_materials_in_use(cls, obj):
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
                if mat:
                    materials_in_use.add(mat)
        return materials_in_use

    @classmethod
    def clean_mesh_materials(cls, obj):
        """Clean up material slots for a mesh object.

        Removes slots that are not referenced by any polygon. Blender's
        ``mesh.materials.pop()`` automatically adjusts polygon
        ``material_index`` values when a slot is removed, so no explicit
        remapping is needed. Slots are popped from highest index to
        lowest to avoid index shifting during iteration.
        """
        if not obj or obj.type != 'MESH' or not obj.data.materials:
            return 0

        # Skip linked objects
        if obj.library or obj.data.library:
            return 0

        mesh = obj.data
        slot_count = len(mesh.materials)

        # Single pass over polygons to find which slot indices are in use.
        used_slot_indices = set()
        for polygon in mesh.polygons:
            if 0 <= polygon.material_index < slot_count:
                used_slot_indices.add(polygon.material_index)

        # A slot is removable if no polygon references it. (Any material
        # data-block that is still only present via a now-unused slot will
        # get its user-count dropped by `materials.pop` below.)
        slots_to_remove = [i for i in range(slot_count) if i not in used_slot_indices]
        if not slots_to_remove:
            return 0

        # Remove the unused slots from highest index to lowest.
        # Blender's materials.pop() automatically adjusts polygon
        # material_index values, so no explicit remapping is needed.
        for slot_idx in sorted(slots_to_remove, reverse=True):
            mesh.materials.pop(index=slot_idx)

        return len(slots_to_remove)

    def execute(self, context):
        """Execute the material removal operation."""
        try:
            # Track materials actually in use by faces
            used_materials = set()
            total_slots_removed = 0
            objects_cleaned = 0
            
            # First pass: Clean up material slots in meshes and collect truly used materials.
            # Iterating all scenes covers all scene objects (which includes all
            # collection objects), so a separate collection traversal is not needed.
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
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_RemoveUnusedMaterials(Panel):
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
#endregion


#region REG
classes = (
    ZENV_OT_RemoveUnusedMaterials,
    ZENV_PT_RemoveUnusedMaterials,
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
#endregion
