# MESH SEPARATE BY UV
# separates mesh into individual objects based on UV islands
# useful for splitting objects that share UV space into separate objects

bl_info = {
    "name": "MESH Separate by UV Islands",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 7),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Separates mesh into individual objects based on UV islands",
}

import bpy
import bmesh
from mathutils import Vector

class ZENV_OT_SeparateByUV_Islands(bpy.types.Operator):
    """Separate the mesh by UV islands - splits mesh into individual objects based on UV borders"""
    bl_idname = "zenv.separatebyuv_islands"
    bl_label = "Separate by UV Islands"
    bl_options = {'REGISTER', 'UNDO'}

    def get_linked_faces_uv(self, start_face, uv_layer, processed_faces):
        """Find all faces connected in UV space"""
        island_faces = set()
        faces_to_process = {start_face}

        while faces_to_process:
            current_face = faces_to_process.pop()
            if current_face in island_faces:
                continue

            island_faces.add(current_face)
            processed_faces.add(current_face)

            # Check each vertex in the current face
            for vert in current_face.verts:
                # Get all faces connected to this vertex
                connected_faces = set(f for e in vert.link_edges for f in e.link_faces)
                
                for connected_face in connected_faces:
                    if connected_face in processed_faces:
                        continue

                    # Check if faces share UV coordinates
                    shares_uv = False
                    for loop in current_face.loops:
                        if loop.vert == vert:
                            current_uv = loop[uv_layer].uv
                            # Find matching UV in connected face
                            for c_loop in connected_face.loops:
                                if c_loop.vert == vert and (c_loop[uv_layer].uv - current_uv).length < 0.00001:
                                    shares_uv = True
                                    break
                            if shares_uv:
                                break

                    if shares_uv:
                        faces_to_process.add(connected_face)

        return island_faces

    def find_uv_islands(self, bm, uv_layer):
        """Find all UV islands in the mesh"""
        islands = []
        processed_faces = set()

        for face in bm.faces:
            if face not in processed_faces:
                island = self.get_linked_faces_uv(face, uv_layer, processed_faces)
                islands.append(island)

        return islands

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Active object is not a mesh")
                return {'CANCELLED'}

            # Store original mode and switch to EDIT
            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='EDIT')

            # Get mesh data
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.faces.ensure_lookup_table()

            if not bm.loops.layers.uv:
                self.report({'ERROR'}, "Mesh has no UV layer")
                return {'CANCELLED'}

            uv_layer = bm.loops.layers.uv.verify()

            # Find UV islands
            islands = self.find_uv_islands(bm, uv_layer)
            
            if not islands:
                self.report({'WARNING'}, "No UV islands found")
                return {'CANCELLED'}

            # Mark seams between islands
            for edge in bm.edges:
                edge.seam = False
                faces = edge.link_faces
                if len(faces) == 2:
                    # Check if faces belong to different islands
                    face1_island = None
                    face2_island = None
                    for i, island in enumerate(islands):
                        if faces[0] in island:
                            face1_island = i
                        if faces[1] in island:
                            face2_island = i
                    if face1_island != face2_island:
                        edge.seam = True

            bmesh.update_edit_mesh(me)

            # Select seam edges and split
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.mesh.select_mode(type='EDGE')
            
            for edge in bm.edges:
                if edge.seam:
                    edge.select = True
            
            bmesh.update_edit_mesh(me)
            bpy.ops.mesh.edge_split()

            # Separate by loose parts
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='LOOSE')

            # Return to original mode
            bpy.ops.object.mode_set(mode=original_mode)

            self.report({'INFO'}, f"Successfully separated into {len(islands)} UV islands")
            return {'FINISHED'}

        except Exception as e:
            if 'obj' in locals():
                bpy.ops.object.mode_set(mode=original_mode)
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            return {'CANCELLED'}

class ZENV_PT_SeparateByUV_Panel(bpy.types.Panel):
    """Panel for UV separation tools"""
    bl_label = "Separate by UV"
    bl_idname = "ZENV_PT_separatebyuv"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.separatebyuv_islands", icon='OUTLINER_OB_MESH')

classes = (
    ZENV_OT_SeparateByUV_Islands,
    ZENV_PT_SeparateByUV_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
