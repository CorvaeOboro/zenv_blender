bl_info = {
    "name": "Separate Mesh by UV Islands or UDIM",
    "author": "CorvaeOboro",
    "version": (1, 3),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > ZENV Tab",
    "description": "Separates a mesh into new objects based on UV islands or UV quadrant",
    "wiki_url": "",
    "category": "ZENV",
}

import bpy
import bmesh
import math

#===========================================================
# SEPARATE BY UV ISLANDS
class MESH_OT_separate_by_uv(bpy.types.Operator):
    """Separate the mesh by UV islands"""
    bl_idname = "mesh.separate_by_uv_islands"
    bl_label = "Separate by UV Islands"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh")
            return {'CANCELLED'}

        # Switch to EDIT mode and select all
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        # Mark seams along UV islands
        bpy.ops.uv.seams_from_islands(mark_seams=True, mark_sharp=False)

        # Get BMesh
        bm = bmesh.from_edit_mesh(obj.data)

        # Split edges that are marked as seams
        edges_to_split = [e for e in bm.edges if e.seam]
        if edges_to_split:
            bmesh.ops.split_edges(bm, edges=edges_to_split)
            bmesh.update_edit_mesh(obj.data)

        # Remove seams to clean up
        for edge in bm.edges:
            edge.seam = False
        bmesh.update_edit_mesh(obj.data)

        # Separate loose parts into new objects
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='LOOSE')

        # Switch back to OBJECT mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Optionally, clean up by removing doubles (if necessary)
        # for obj in context.selected_objects:
        #     context.view_layer.objects.active = obj
        #     bpy.ops.object.mode_set(mode='EDIT')
        #     bpy.ops.mesh.select_all(action='SELECT')
        #     bpy.ops.mesh.remove_doubles()
        #     bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}

#=============================================================================
# SEPARATE BY UV QUADRANTS 
class MESH_OT_separate_by_uv_quadrant(bpy.types.Operator):
    """Separate the mesh by the average UV quadrant of each face"""
    bl_idname = "mesh.separate_by_uv_quadrant"
    bl_label = "Separate by UV Quadrant"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        
        quadrant_faces = self.separate_faces_by_quadrant(bm, uv_layer)
        self.separate_and_offset_uv(context, obj, quadrant_faces)
        self.finish_up(context, obj)
        return {'FINISHED'}
    
    def get_uv_quadrant(self, face, uv_layer):
        """Calculate the UV quadrant for a given face based on the majority of its area."""
        u_sum = 0
        v_sum = 0
        area_sum = 0
        for loop in face.loops:
            uv = loop[uv_layer].uv
            area = loop.calc_area()
            u_sum += uv.x * area
            v_sum += uv.y * area
            area_sum += area
        if area_sum == 0:
            u_avg = v_avg = 0
        else:
            u_avg = u_sum / area_sum
            v_avg = v_sum / area_sum
        return math.floor(u_avg), math.floor(v_avg)
    
    def separate_faces_by_quadrant(self, bm, uv_layer):
        from collections import defaultdict
        """Separate faces by their UV quadrant using a default dictionary."""
        quadrant_faces = defaultdict(list)
        for face in bm.faces:
            quadrant_id = self.get_uv_quadrant(face, uv_layer)
            quadrant_faces[quadrant_id].append(face)
        return quadrant_faces
    
    def separate_and_offset_uv(self, context, obj, quadrant_faces):
        """Separate faces by quadrant and offset their UVs."""
        bpy.ops.mesh.select_all(action='DESELECT')
        for quadrant, faces in quadrant_faces.items():
            self.select_faces(faces)
            self.separate_selected_faces()
            self.offset_uv_of_separated_objects(context, obj, quadrant)
            # Deselect separated object
            bpy.ops.object.mode_set(mode='OBJECT')
            separated_obj = context.selected_objects[-1]
            separated_obj.select_set(False)
            bpy.ops.object.mode_set(mode='EDIT')
    
    def select_faces(self, faces):
        """Select given faces in the mesh."""
        for face in faces:
            face.select_set(True)
        bmesh.update_edit_mesh(bpy.context.active_object.data)
    
    def separate_selected_faces(self):
        """Separate the selected faces into a new object."""
        bpy.ops.mesh.separate(type='SELECTED')
    
    def offset_uv_of_separated_objects(self, context, original_obj, quadrant):
        """Offset the UVs of the separated objects based on the quadrant."""
        offset_x, offset_y = -quadrant[0], -quadrant[1]
        bpy.ops.object.mode_set(mode='OBJECT')
        separated_obj = context.selected_objects[-1]
        self.offset_uv(separated_obj, offset_x, offset_y)
        bpy.ops.object.mode_set(mode='EDIT')
    
    def offset_uv(self, obj, offset_x, offset_y):
        """Apply the offset to the UV coordinates of the object."""
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        separated_bm = bmesh.from_edit_mesh(obj.data)
        separated_uv_layer = separated_bm.loops.layers.uv.verify()
        for face in separated_bm.faces:
            for loop in face.loops:
                loop_uv = loop[separated_uv_layer].uv
                loop_uv.x += offset_x
                loop_uv.y += offset_y
        bmesh.update_edit_mesh(obj.data)
    
    def finish_up(self, context, obj):
        """Deselect all and set the original object as active."""
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj


#=============================================================================
# UI SIDE PANEL
class MESH_PT_separate_by_uv_combined(bpy.types.Panel):
    """Creates a Panel in the Object properties window for separating by UV"""
    bl_label = "Separate Mesh by UV"
    bl_idname = "MESH_PT_separate_by_uv_combined"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        layout.operator("mesh.separate_by_uv_islands")
        layout.operator("mesh.separate_by_uv_quadrant")


def register():
    bpy.utils.register_class(MESH_OT_separate_by_uv)
    bpy.utils.register_class(MESH_OT_separate_by_uv_quadrant)
    bpy.utils.register_class(MESH_PT_separate_by_uv_combined)

def unregister():
    bpy.utils.unregister_class(MESH_PT_separate_by_uv_combined)
    bpy.utils.unregister_class(MESH_OT_separate_by_uv_quadrant)
    bpy.utils.unregister_class(MESH_OT_separate_by_uv)

if __name__ == "__main__":
    register()
