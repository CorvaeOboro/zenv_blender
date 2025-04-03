"""
MESH Separate By Material - A Blender addon for mesh separation
Separates mesh objects by material assignment while preserving hierarchies.
"""

bl_info = {
    "name": "MESH Separate By Material",
    "author": "CorvaeOboro",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV > MESH Separate By Material",
    "description": "Separate mesh by material assignment",
    "category": "ZENV",
}

import bpy
import bmesh
from bpy.types import Operator, Panel
import time
from mathutils import Matrix

class ZENV_OT_SeparateByMaterial(Operator):
    """Separate mesh objects by material assignments."""
    bl_idname = "zenv.separate_by_material"
    bl_label = "Separate By Material"
    bl_options = {'REGISTER', 'UNDO'}

    def get_world_matrix(self, obj):
        """Get the world matrix considering the entire parent hierarchy."""
        if obj.parent:
            parent_matrix = self.get_world_matrix(obj.parent)
            return parent_matrix @ obj.matrix_local
        return obj.matrix_local

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
        orig_collection = obj.users_collection[0]  # Primary collection
        orig_world_matrix = self.get_world_matrix(obj)
        orig_matrix_local = obj.matrix_local.copy()
        
        # Store child objects
        children = [child for child in obj.children]
        
        # Track progress
        start_time = time.time()
        processed_count = 0
        total_materials = len(mat_indices)
        
        # Make object active and enter edit mode
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Get BMesh for selection
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        
        # Process each material
        separated_objects = []
        for mat_idx in mat_indices:
            # Skip if no material
            if mat_idx >= len(mesh.materials) or not mesh.materials[mat_idx]:
                continue
                
            # Store material reference
            material = mesh.materials[mat_idx]
            
            # Deselect all faces
            bpy.ops.mesh.select_all(action='DESELECT')
            
            # Select faces with current material
            for face in bm.faces:
                face.select = (face.material_index == mat_idx)
            
            # Update mesh
            bmesh.update_edit_mesh(mesh)
            
            # Separate selected faces
            bpy.ops.mesh.separate(type='SELECTED')
            
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
        
        return True

    def execute(self, context):
        """Execute the separation operation."""
        try:
            # Get selected objects
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
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
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            if context.active_object and context.active_object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

class ZENV_PT_SeparateByMaterialPanel(Panel):
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

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_SeparateByMaterial,
    ZENV_PT_SeparateByMaterialPanel,
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
