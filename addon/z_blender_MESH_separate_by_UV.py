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
        """ Find and return the first UV island as a list of face indices. """
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
        """ Determine if two faces share a UV edge. """
        shared_uvs = [loop[uv_layer].uv.copy() for loop in face1.loops]
        other_uvs = [loop[uv_layer].uv.copy() for loop in face2.loops]
        return any(uv in other_uvs for uv in shared_uvs)

class MESH_OT_separate_by_uv_quadrant(bpy.types.Operator):
    """Separate the mesh by the average UV quadrant of each face"""
    bl_idname = "mesh.separate_by_uv_quadrant"
    bl_label = "Separate by UV Quadrant"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        
        # Dictionary to store faces by their quadrant
        quadrant_faces = {}

        # Determine the quadrant for each face
        for face in bm.faces:
            u_avg = sum(loop[uv_layer].uv.x for loop in face.loops) / len(face.loops)
            v_avg = sum(loop[uv_layer].uv.y for loop in face.loops) / len(face.loops)

            # Determine quadrant index based on average UV coordinates
            quadrant_x = math.floor(u_avg)
            quadrant_y = math.floor(v_avg)

            quadrant_id = (quadrant_x, quadrant_y)
            if quadrant_id not in quadrant_faces:
                quadrant_faces[quadrant_id] = []
            quadrant_faces[quadrant_id].append(face)

        # Update BMesh to deselect all initially
        bpy.ops.mesh.select_all(action='DESELECT')
        bmesh.update_edit_mesh(obj.data)
        
        # Separate faces by quadrant
        for quadrant, faces in quadrant_faces.items():
            for face in faces:
                face.select_set(True)

            bmesh.update_edit_mesh(obj.data)
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.mesh.select_all(action='DESELECT')
        
        bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}
    
class MESH_PT_separate_by_uv_combined(bpy.types.Panel):
    """Creates a Panel in the Object properties window for separating by UV"""
    bl_label = "Separate Mesh by UV"
    bl_idname = "MESH_PT_separate_by_uv_combined"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        layout.operator("mesh.separate_by_uv_islands")
        layout.separator()
        layout.operator("mesh.separate_by_uv_quadrant")
        layout = self.layout
        layout.operator("mesh.separate_by_uv_quadrant")

def register():
    bpy.utils.register_class(MESH_OT_separate_by_uv_quadrant)
    bpy.utils.register_class(MESH_PT_separate_by_uv_quadrant)
    bpy.utils.register_class(MESH_OT_separate_by_uv)
    bpy.utils.register_class(MESH_PT_separate_by_uv)

def unregister():
    bpy.utils.unregister_class(MESH_OT_separate_by_uv_quadrant)
    bpy.utils.unregister_class(MESH_PT_separate_by_uv_quadrant)
    bpy.utils.unregister_class(MESH_OT_separate_by_uv)
    bpy.utils.unregister_class(MESH_PT_separate_by_uv)

if __name__ == "__main__":
    register()
