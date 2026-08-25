#region META
bl_info = {
    "name": 'MESH Separate By Material',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Separate mesh by material assignment',
    "status": 'working',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 20,
    "addon_order": 10,
    "tags": ['mesh separate', 'material', 'split by material'],
    "description_short": 'for each material detach mesh into parts',
    "description_medium": 'Separates mesh objects by material assignment while preserving hierarchies.',
    "description_long": """
MESH Separate By Material - A Blender addon for mesh separation
Separates mesh objects by material assignment while preserving hierarchies.
""",
    "location": 'View3D > Sidebar > ZENV > MESH Separate By Material',
    "image_overview": 'zenv_blender_MESH_separate_by_material.png',
    "addon_image": 'zenv_blender_MESH_separate_by_material.png',
}

#region IMPORT
import bpy
import bmesh
import logging
from bpy.types import Operator, Panel
import time

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region OP
class ZENV_OT_SeparateByMaterial(Operator):
    """Separate mesh objects by material assignments."""
    bl_idname = "zenv.separate_by_material"
    bl_label = "Separate By Material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when at least one mesh object is selected."""
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def separate_mesh(self, context, obj):
        """Separate a mesh object by material assignments."""
        if not obj or obj.type != 'MESH':
            return False

        # Get mesh data
        mesh = obj.data
        if not mesh.polygons or not mesh.materials:
            return False

        # Get unique material indices
        mat_indices = set(p.material_index for p in mesh.polygons)
        if len(mat_indices) <= 1:
            return False

        # Store original hierarchy info
        orig_parent = obj.parent
        if not obj.users_collection:
            logger.warning("Object '%s' is not in any collection; skipping", obj.name)
            return False
        orig_collection = obj.users_collection[0]  # Primary collection
        orig_world_matrix = obj.matrix_world.copy()
        orig_matrix_local = obj.matrix_local.copy()

        # Store child objects
        children = [child for child in obj.children]

        # Track original mode for restoration
        original_mode = obj.mode

        # Track progress
        start_time = time.time()
        processed_count = 0
        total_materials = len(mat_indices)

        # Make object active and enter edit mode
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        # Process each material - re-fetch BMesh each iteration because
        # bpy.ops.mesh.separate invalidates the previous BMesh reference.
        separated_objects = []
        for mat_idx in mat_indices:
            # Skip if no material
            if mat_idx >= len(mesh.materials) or not mesh.materials[mat_idx]:
                continue

            # Store material reference
            material = mesh.materials[mat_idx]

            # Deselect all faces
            bpy.ops.mesh.select_all(action='DESELECT')

            # Re-fetch BMesh for selection (stale after previous separate)
            bm = bmesh.from_edit_mesh(mesh)
            bm.faces.ensure_lookup_table()

            # Select faces with current material
            for face in bm.faces:
                face.select = (face.material_index == mat_idx)

            # Update mesh
            bmesh.update_edit_mesh(mesh)

            # Separate selected faces - check return value for failure
            try:
                result = bpy.ops.mesh.separate(type='SELECTED')
                if 'CANCELLED' in result:
                    logger.info("Separate cancelled for material index %d on '%s'",
                                mat_idx, obj.name)
                    continue
            except RuntimeError as exc:
                logger.warning("Separate failed for material index %d on '%s': %s",
                               mat_idx, obj.name, exc)
                continue

            # Update progress
            processed_count += 1
            if time.time() - start_time > 1.0:  # Update every second
                self.report(
                    {'INFO'},
                    f"Processing material {processed_count}/{total_materials}"
                )
                start_time = time.time()

        # Exit edit mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Process separated objects
        for new_obj in context.selected_objects:
            if new_obj != obj and new_obj.type == 'MESH':
                separated_objects.append(new_obj)

                # Ensure proper collection membership
                for collection in new_obj.users_collection:
                    collection.objects.unlink(new_obj)
                orig_collection.objects.link(new_obj)

                # Set up parent relationship
                if orig_parent:
                    new_obj.parent = orig_parent
                    # Calculate and apply correct transform
                    new_obj.matrix_local = orig_matrix_local
                else:
                    # If no parent, use world matrix
                    new_obj.matrix_world = orig_world_matrix

                # Name by material
                if (len(new_obj.data.materials) > 0 and
                    new_obj.data.materials[0] is not None):
                    mat_name = new_obj.data.materials[0].name
                    new_obj.name = f"{obj.name}_{mat_name}"
                    new_obj.data.name = f"{obj.name}_{mat_name}_mesh"

        # Reassign children to first separated object if original will be deleted
        if len(obj.data.polygons) == 0 and separated_objects:
            new_parent = separated_objects[0]
            for child in children:
                # Store original local transform
                child_local = child.matrix_local.copy()
                # Reparent
                child.parent = new_parent
                # Restore local transform
                child.matrix_local = child_local

            # Delete original object
            bpy.data.objects.remove(obj, do_unlink=True)

        # Restore original mode if it wasn't OBJECT
        if original_mode != 'OBJECT' and context.view_layer.objects.active is not None:
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except RuntimeError:
                pass

        return True

    def execute(self, context):
        """Execute the separation operation."""
        # Snapshot selected mesh object names to avoid reprocessing
        # newly created objects that may appear in the selection after
        # separation.
        selected_names = {obj.name for obj in context.selected_objects
                          if obj.type == 'MESH'}
        try:
            # Get selected objects from the snapshot
            objects = [bpy.data.objects[name] for name in selected_names
                       if name in bpy.data.objects]
            if not objects:
                self.report({'ERROR'}, "No mesh objects selected")
                return {'CANCELLED'}

            # Track progress
            separated_count = 0
            total_objects = len(objects)

            # Process each object
            for i, obj in enumerate(objects):
                if self.separate_mesh(context, obj):
                    separated_count += 1

                # Progress update for multiple objects
                if total_objects > 1:
                    self.report(
                        {'INFO'},
                        f"Processing object {i+1}/{total_objects}"
                    )

            # Final report
            if separated_count > 0:
                self.report(
                    {'INFO'},
                    f"Separated {separated_count} objects by material"
                )
            else:
                self.report(
                    {'INFO'},
                    "No objects needed separation"
                )

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to separate mesh by material")
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            # Guard mode restore - may fail if context is invalid
            active = context.view_layer.objects.active if context.view_layer else None
            if active is not None and active.mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except RuntimeError:
                    pass
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_SeparateByMaterial(Panel):
    """Panel for material separation."""
    bl_label = "MESH Separate By Material"
    bl_idname = "ZENV_PT_separate_by_material"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        layout.operator(ZENV_OT_SeparateByMaterial.bl_idname)

#endregion
#region REG
classes = (
    ZENV_OT_SeparateByMaterial,
    ZENV_PT_SeparateByMaterial,
)

def register():
    """Register the addon classes and configure the module logger handler."""
    global _logger_handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    if _logger_handler is None:
        _logger_handler = logging.StreamHandler()
        _logger_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
        logger.addHandler(_logger_handler)
    if not logger.level:
        logger.setLevel(logging.INFO)

def unregister():
    """Unregister the addon classes and remove the module logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
