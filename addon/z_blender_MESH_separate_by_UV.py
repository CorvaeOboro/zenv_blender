bl_info = {
    "name": "Separate Mesh by UV Islands",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > ZENV Tab",
    "description": "Separates a mesh into new objects based on UV islands",
    "warning": "",
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

        # Separate each UV island into a new object
        while True:
            bpy.ops.object.mode_set(mode='EDIT')
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.verify()
            island = self.get_first_uv_island(bm, uv_layer)
            if not island:
                bpy.ops.object.mode_set(mode='OBJECT')
                break  # No more islands to process

            # Select the first found island
            bpy.ops.mesh.select_all(action='DESELECT')
            bm.faces.ensure_lookup_table()
            for face in island:
                bm.faces[face.index].select_set(True)
            bmesh.update_edit_mesh(obj.data)

            # Separate the selected island
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}

    def get_first_uv_island(self, bm, uv_layer):
        """Find and return the first UV island as a list of face indices."""
        faces_visited = set()
        for face in bm.faces:
            if face not in faces_visited:
                island = []
                stack = [face]
                while stack:
                    f = stack.pop()
                    if f not in faces_visited:
                        faces_visited.add(f)
                        island.append(f)
                        for loop in f.loops:
                            for l_edge in loop.edge.link_loops:
                                other_face = l_edge.face
                                if other_face not in faces_visited and self.faces_share_uv_edge(f, other_face, uv_layer):
                                    stack.append(other_face)
                return island
        return None

    def faces_share_uv_edge(self, face1, face2, uv_layer):
        """Determine if two faces share a UV edge."""
        shared_uvs = [loop[uv_layer].uv.copy() for loop in face1.loops]
        other_uvs = [loop[uv_layer].uv.copy() for loop in face2.loops]
        return any(uv in other_uvs for uv in shared_uvs)

#=============================================================================
# SEPARATE BY UV QUADRANTS 
class MESH_OT_separate_by_uv_quadrant(bpy.types.Operator):
    """Separate the mesh by the average UV quadrant of each face"""
    bl_idname = "mesh.separate_by_uv_quadrant"
    bl_label = "Separate by UV Quadrant"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def get_uv_quadrant(face, uv_layer):
        """Calculate the UV quadrant for a given face based on its first vertex."""
        first_loop_uv = face.loops[0][uv_layer].uv
        return math.floor(first_loop_uv.x), math.floor(first_loop_uv.y)

    @classmethod
    def separate_faces_by_quadrant(cls, bm, uv_layer):
        from collections import defaultdict
        """Separate faces by their UV quadrant using a default dictionary."""
        quadrant_faces = defaultdict(list)
        for face in bm.faces:
            quadrant_id = cls.get_uv_quadrant(face, uv_layer)
            quadrant_faces[quadrant_id].append(face)
        return quadrant_faces

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        

        quadrant_faces = self.separate_faces_by_quadrant(bm, uv_layer)

        quadrant_faces = self.separate_faces_by_quadrant(bm, uv_layer)
        

        # Apply UV offset to ensure UVs are within 0-1 UV space
        for quadrant, faces in quadrant_faces.items():
            bpy.ops.mesh.select_all(action='DESELECT')
            for face in faces:
                face.select_set(True)
            bmesh.update_edit_mesh(obj.data)
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.object.mode_set(mode='OBJECT')

            # Calculate the offset for the quadrant
            offset_x = -quadrant[0]
            offset_y = -quadrant[1]

            # Apply the offset to the UV coordinates of the separated objects
            for separated_obj in context.selected_objects:
                if separated_obj == obj:
                    continue  # Skip the original object
                bpy.context.view_layer.objects.active = separated_obj
                bpy.ops.object.mode_set(mode='EDIT')
                separated_bm = bmesh.from_edit_mesh(separated_obj.data)
                separated_uv_layer = separated_bm.loops.layers.uv.verify()
                for face in separated_bm.faces:
                    for loop in face.loops:
                        loop_uv = loop[separated_uv_layer].uv
                        loop_uv.x += offset_x
                        loop_uv.y += offset_y
                bmesh.update_edit_mesh(separated_obj.data)
                bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all and set the original object as active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        return {'FINISHED'}

    
#=============================================================================
# UI SIDE PANEL
class MESH_PT_separate_by_uv_combined(bpy.types.Panel):
    """Creates a Panel in the Object properties window for separating by UV"""
    bl_label = "Separate Mesh by UV"
    bl_idname = "MESH_PT_separate_by_uv_combined"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    #bl_context = "objectmode"  # Ensure this is set to the correct context for the panel to appear

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
