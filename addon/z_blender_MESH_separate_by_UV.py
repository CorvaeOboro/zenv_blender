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

            # Check each edge in the current face
            for edge in current_face.edges:
                # Get connected faces through this edge
                connected_faces = set(f for f in edge.link_faces if f != current_face)
                
                for connected_face in connected_faces:
                    if connected_face in processed_faces:
                        continue

                    # Check if faces share UV coordinates along the edge
                    shares_uv = False
                    edge_verts = set(edge.verts)
                    
                    # Get UV coordinates for the edge in current face
                    current_uvs = {}
                    for loop in current_face.loops:
                        if loop.vert in edge_verts:
                            current_uvs[loop.vert] = loop[uv_layer].uv
                    
                    # Check UV coordinates in connected face
                    for loop in connected_face.loops:
                        if loop.vert in edge_verts:
                            connected_uv = loop[uv_layer].uv
                            if loop.vert in current_uvs:
                                # Compare UVs
                                if (connected_uv - current_uvs[loop.vert]).length < 0.00001:
                                    shares_uv = True
                                else:
                                    shares_uv = False
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

    def duplicate_island(self, context, obj, island_faces, uv_layer):
        """Create a new object from the given UV island"""
        # Create new mesh and bmesh
        new_mesh = bpy.data.meshes.new(name=f"{obj.name}_island")
        new_bm = bmesh.new()
        
        # Create vertex map from old to new
        vert_map = {}
        
        # Copy vertices and create mapping
        for face in island_faces:
            for vert in face.verts:
                if vert not in vert_map:
                    new_vert = new_bm.verts.new(vert.co)
                    vert_map[vert] = new_vert
        
        new_bm.verts.ensure_lookup_table()
        new_bm.verts.index_update()
        
        # Create new UV layer
        new_uv_layer = new_bm.loops.layers.uv.new()
        
        # Copy faces and their UVs
        for face in island_faces:
            new_verts = [vert_map[v] for v in face.verts]
            try:
                new_face = new_bm.faces.new(new_verts)
                # Copy UV coordinates
                for i, loop in enumerate(face.loops):
                    new_face.loops[i][new_uv_layer].uv = loop[uv_layer].uv
            except ValueError as e:
                continue  # Skip faces that can't be created (e.g., duplicate faces)
        
        # Create new object
        new_bm.to_mesh(new_mesh)
        new_obj = bpy.data.objects.new(name=f"{obj.name}_island", object_data=new_mesh)
        
        # Copy materials from original object
        for mat in obj.data.materials:
            new_obj.data.materials.append(mat)
        
        # Link new object to scene
        context.collection.objects.link(new_obj)
        
        # Copy transform from original object
        new_obj.matrix_world = obj.matrix_world
        
        return new_obj

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Active object is not a mesh")
                return {'CANCELLED'}

            # Store original mode and switch to OBJECT
            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Create bmesh from object
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.faces.ensure_lookup_table()

            if not bm.loops.layers.uv:
                bm.free()
                self.report({'ERROR'}, "Mesh has no UV layer")
                return {'CANCELLED'}

            uv_layer = bm.loops.layers.uv.verify()

            # Find UV islands
            islands = self.find_uv_islands(bm, uv_layer)
            
            if not islands:
                bm.free()
                self.report({'WARNING'}, "No UV islands found")
                return {'CANCELLED'}

            # Create new objects for each island
            new_objects = []
            for island in islands:
                new_obj = self.duplicate_island(context, obj, island, uv_layer)
                new_objects.append(new_obj)

            # Remove original object if we created new ones
            if new_objects:
                bpy.data.objects.remove(obj, do_unlink=True)

            # Select all new objects and make the first one active
            if new_objects:
                for obj in new_objects:
                    obj.select_set(True)
                context.view_layer.objects.active = new_objects[0]

            bm.free()

            # Return to original mode
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)

            self.report({'INFO'}, f"Successfully separated into {len(islands)} UV islands")
            return {'FINISHED'}

        except Exception as e:
            if 'bm' in locals():
                bm.free()
            if 'obj' in locals() and obj:
                bpy.ops.object.mode_set(mode=original_mode)
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            return {'CANCELLED'}

class ZENV_PT_SeparateByUV_Panel(bpy.types.Panel):
    """Panel for UV island separation tools"""
    bl_label = "MESH Separate by UV"
    bl_idname = "ZENV_PT_separate_by_uv"
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
