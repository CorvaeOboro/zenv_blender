"""
MESH Separate by Material - A Blender addon for material-based mesh separation.

This addon provides functionality to separate meshes into different objects based
on their material assignments. It handles complex geometry by:
1. Triangulating the mesh to ensure proper topology
2. Marking edges along material boundaries
3. Separating into distinct objects while preserving material boundaries
"""

bl_info = {
    "name": "MESH Separate by Material",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 7),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Separates mesh into different objects based on material",
}

import bpy
import bmesh
from bpy.types import Operator, Panel

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_SeparateByMaterial_Split(Operator):
    """Separates selected mesh into multiple objects based on material assignments.
    
    This operator performs the following steps:
    1. Triangulates the mesh to ensure proper topology
    2. Marks edges between different materials
    3. Separates the mesh into distinct objects
    4. Names each object based on its material
    
    Note:
        The original object must have materials assigned to its faces.
    """
    bl_idname = "zenv.separatebymaterial_split"
    bl_label = "Split by Material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if the operator can be executed."""
        return context.active_object and context.active_object.type == 'MESH'

    def prepare_mesh(self, context, obj):
        """Prepare the mesh for separation by triangulating and marking boundaries."""
        try:
            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.faces.ensure_lookup_table()
            
            # Triangulate faces
            bmesh.ops.triangulate(
                bm,
                faces=bm.faces,
                quad_method='BEAUTY',
                ngon_method='BEAUTY'
            )
            
            # Update the mesh
            bmesh.update_edit_mesh(me)
            bpy.ops.object.mode_set(mode='OBJECT')
            return True
            
        except Exception as e:
            self.report({'ERROR'}, f"Error preparing mesh: {str(e)}")
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return False

    def get_connected_faces(self, bm, start_faces, material_index):
        """Get all connected faces with the same material index using BMesh.
        
        Args:
            bm: BMesh object
            start_faces: Initial faces to check
            material_index: Material index to match
            
        Returns:
            set: Set of connected faces with the same material
        """
        faces_to_check = set(start_faces)
        checked_faces = set()
        result_faces = set()
        
        while faces_to_check:
            current_face = faces_to_check.pop()
            checked_faces.add(current_face)
            
            if current_face.material_index == material_index:
                result_faces.add(current_face)
                
                # Add connected faces through edges
                for edge in current_face.edges:
                    for linked_face in edge.link_faces:
                        if (linked_face not in checked_faces and 
                            linked_face not in faces_to_check):
                            faces_to_check.add(linked_face)
        
        return result_faces

    def separate_by_material(self, context, obj):
        """Separate the mesh by material assignments using BMesh for accuracy."""
        try:
            base_name = obj.name
            
            # Create BMesh
            bpy.ops.object.mode_set(mode='EDIT')
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.faces.ensure_lookup_table()
            
            # Process each material
            for mat_index, material in enumerate(obj.data.materials):
                if not material:
                    continue
                
                # Get all faces with this material
                material_faces = {f for f in bm.faces 
                                if f.material_index == mat_index}
                
                if not material_faces:
                    continue
                
                # Deselect all faces
                for face in bm.faces:
                    face.select = False
                
                # Get connected face groups
                remaining_faces = material_faces.copy()
                while remaining_faces:
                    start_face = remaining_faces.pop()
                    connected_faces = self.get_connected_faces(
                        bm, [start_face], mat_index
                    )
                    
                    # Select connected faces
                    for face in connected_faces:
                        face.select = True
                        if face in remaining_faces:
                            remaining_faces.remove(face)
                    
                    # Update the mesh
                    bmesh.update_edit_mesh(me)
                    
                    # Separate selected faces if there are any
                    if any(f.select for f in bm.faces):
                        bpy.ops.mesh.separate(type='SELECTED')
                        
                        # Update BMesh after separation
                        bm = bmesh.from_edit_mesh(me)
                        bm.faces.ensure_lookup_table()
                
                # Exit edit mode to rename the new object
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # Find and rename the newly created object
                new_objects = [o for o in context.selected_objects 
                             if o != obj and o.type == 'MESH']
                for new_obj in new_objects:
                    new_obj.name = f"{base_name}_{material.name}"
                
                # Re-enter edit mode for next iteration
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(me)
                bm.faces.ensure_lookup_table()
            
            # Final cleanup
            bpy.ops.object.mode_set(mode='OBJECT')
            return True
            
        except Exception as e:
            self.report({'ERROR'}, f"Error separating by material: {str(e)}")
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return False

    def execute(self, context):
        """Execute the operator."""
        try:
            active_obj = context.active_object
            
            # Check for materials
            if not active_obj.data.materials:
                self.report({'ERROR'}, "Object has no materials assigned")
                return {'CANCELLED'}

            # Ensure we're in object mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Prepare the mesh
            if not self.prepare_mesh(context, active_obj):
                return {'CANCELLED'}

            # Separate by material
            if not self.separate_by_material(context, active_obj):
                return {'CANCELLED'}

            self.report({'INFO'}, 
                       f"Successfully separated {active_obj.name} by materials")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            if active_obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}


# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_SeparateByMaterial_Panel(Panel):
    """Panel for material-based mesh separation."""
    bl_label = "Separate by Material"
    bl_idname = "ZENV_PT_separatebymaterial"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        box = layout.box()
        box.label(text="Split Mesh:", icon='MATERIAL')
        op = box.operator(
            ZENV_OT_SeparateByMaterial_Split.bl_idname,
            icon='MOD_BOOLEAN'
        )


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_SeparateByMaterial_Split,
    ZENV_PT_SeparateByMaterial_Panel,
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
