#region META
bl_info = {
    "name": 'MESH Separate by UV Islands',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Separates mesh into individual objects based on UV islands',
    "status": 'working',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 20,
    "addon_order": 20,
    "tags": ['UV split', 'mesh separate', 'islands'],
    "description_short": 'for each uv island detach mesh into parts',
    "description_medium": 'Separates a mesh into individual objects based on UV islands. Also provides a per-face separation mode with a confirmation dialog for large face counts.',
    "description_long": """
MESH SEPARATE BY UV
 separates mesh into individual objects based on UV islands
 useful for splitting objects that share UV space into separate objects
""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_MESH_separate_by_UV_island.png',
    "addon_image": 'zenv_blender_MESH_separate_by_UV_island.png',
}

#region IMPORT
import bpy
import bmesh
import logging
from mathutils import Vector

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region OP
class ZENV_OT_MeshSeparateByUVIsland(bpy.types.Operator):
    """Separate the mesh by UV islands - splits mesh into individual objects based on UV borders"""
    bl_idname = "zenv.separatebyuv_islands"
    bl_label = "Separate by UV Islands"
    bl_options = {'REGISTER', 'UNDO'}

    # UV coordinate comparison tolerance for island detection.
    _UV_EPSILON = 1e-5

    @classmethod
    def poll(cls, context):
        """Only enable when the active object is a mesh."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

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

                    # Check if faces share UV coordinates along the edge.
                    # Build vert -> UV dicts for both faces restricted to the
                    # shared edge's vertices, then compare them directly.
                    edge_verts = set(edge.verts)
                    current_uvs = {}
                    for loop in current_face.loops:
                        if loop.vert in edge_verts:
                            current_uvs[loop.vert] = loop[uv_layer].uv
                    connected_uvs = {}
                    for loop in connected_face.loops:
                        if loop.vert in edge_verts:
                            connected_uvs[loop.vert] = loop[uv_layer].uv

                    # Faces share UV along this edge only if every shared vert
                    # has matching UVs within epsilon.
                    shares_uv = False
                    common_verts = set(current_uvs) & set(connected_uvs)
                    if common_verts:
                        shares_uv = all(
                            (connected_uvs[v] - current_uvs[v]).length < self._UV_EPSILON
                            for v in common_verts
                        )

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

    def duplicate_island(self, context, src_bm, obj, island_faces, uv_layer):
        """Create a new object from the given UV island.

        All UV layers on the source mesh (not just the active one used for
        island detection) are copied with full precision.
        """
        new_mesh = bpy.data.meshes.new(name=f"{obj.name}_island")
        new_bm = bmesh.new()

        # Create vertex map from old to new
        vert_map = {}
        for face in island_faces:
            for vert in face.verts:
                if vert not in vert_map:
                    new_vert = new_bm.verts.new(vert.co)
                    vert_map[vert] = new_vert

        new_bm.verts.ensure_lookup_table()
        new_bm.verts.index_update()

        # Recreate every UV layer that existed on the source bmesh so we
        # preserve all UV maps (lightmaps, atlases, etc.).
        src_uv_layers = list(src_bm.loops.layers.uv.values())
        src_uv_names = [src_bm.loops.layers.uv.keys()[i]
                         for i in range(len(src_uv_layers))]
        new_uv_layers = [new_bm.loops.layers.uv.new(name) for name in src_uv_names]

        skipped_faces = 0
        for face in island_faces:
            new_verts = [vert_map[v] for v in face.verts]
            try:
                new_face = new_bm.faces.new(new_verts)
            except ValueError:
                # Duplicate face or non-manifold vert set - skip but count.
                skipped_faces += 1
                continue
            # Preserve per-face attributes that matter downstream.
            new_face.material_index = face.material_index
            new_face.smooth = face.smooth
            # Copy UVs for every layer, keeping per-loop ordering.
            for src_layer, dst_layer in zip(src_uv_layers, new_uv_layers):
                for i, loop in enumerate(face.loops):
                    new_face.loops[i][dst_layer].uv = loop[src_layer].uv

        new_bm.to_mesh(new_mesh)
        new_bm.free()

        new_obj = bpy.data.objects.new(name=f"{obj.name}_island", object_data=new_mesh)

        # Copy materials from original object
        for mat in obj.data.materials:
            new_obj.data.materials.append(mat)

        # Link new object to scene
        context.collection.objects.link(new_obj)

        # Copy transform from original object
        new_obj.matrix_world = obj.matrix_world

        if skipped_faces:
            self.report({'WARNING'},
                        f"Skipped {skipped_faces} face(s) that could not be recreated in '{new_obj.name}'")

        return new_obj

    def execute(self, context):
        original_mode = None
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
            logger.info("Found %d UV island(s) on '%s'", len(islands), obj.name)
            
            if not islands:
                bm.free()
                self.report({'WARNING'}, "No UV islands found")
                return {'CANCELLED'}

            # Create new objects for each island
            new_objects = []
            for island in islands:
                new_obj = self.duplicate_island(context, bm, obj, island, uv_layer)
                new_objects.append(new_obj)

            # Remove original object if we created new ones
            if new_objects:
                bpy.data.objects.remove(obj, do_unlink=True)

            # Select all new objects and make the first one active
            if new_objects:
                for created_obj in new_objects:
                    created_obj.select_set(True)
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
            if original_mode is not None and context.view_layer.objects.active is not None:
                try:
                    bpy.ops.object.mode_set(mode=original_mode)
                except RuntimeError:
                    pass
            logger.exception("Failed to separate mesh by UV islands")
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            return {'CANCELLED'}


class ZENV_OT_MeshSeparateByUVFace(bpy.types.Operator):
    """Separate the mesh so every face becomes its own object (all UV edges split)"""
    bl_idname = "zenv.separatebyuv_faces"
    bl_label = "Separate All Faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when the active object is a mesh."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    # Above this face count show an info dialog before proceeding.
    _CONFIRM_THRESHOLD = 7000
    # Rough benchmark: ~600 faces/sec when creating separate objects.
    _FACES_PER_SECOND = 600

    def invoke(self, context, event):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh")
            return {'CANCELLED'}
        face_count = len(obj.data.polygons)
        if face_count > self._CONFIRM_THRESHOLD:
            self.face_count = face_count
            return context.window_manager.invoke_props_dialog(self, width=380)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        count = getattr(self, 'face_count', 0)
        est_seconds = max(1, count // self._FACES_PER_SECOND)
        if est_seconds >= 60:
            time_str = f"{est_seconds // 60}m {est_seconds % 60}s"
        else:
            time_str = f"{est_seconds}s"
        col = layout.column(align=True)
        col.label(text=f"Objects to create:  {count}", icon='OUTLINER_OB_MESH')
        col.label(text=f"Estimated time:       ~{time_str}", icon='TIME')
        col.separator()
        col.label(text="Blender may be unresponsive during processing.", icon='ERROR')

    def duplicate_face(self, context, src_bm, obj, face, face_index):
        """Duplicate a single face into its own object, preserving every UV map."""
        new_mesh = bpy.data.meshes.new(name=f"{obj.name}_face")
        new_bm = bmesh.new()

        vert_map = {}
        for vert in face.verts:
            new_vert = new_bm.verts.new(vert.co)
            vert_map[vert] = new_vert

        new_bm.verts.ensure_lookup_table()
        new_bm.verts.index_update()

        # Copy every source UV layer by name.
        src_uv_layers = list(src_bm.loops.layers.uv.values())
        src_uv_names = [src_bm.loops.layers.uv.keys()[i]
                         for i in range(len(src_uv_layers))]
        new_uv_layers = [new_bm.loops.layers.uv.new(name) for name in src_uv_names]

        new_verts = [vert_map[v] for v in face.verts]
        try:
            new_face = new_bm.faces.new(new_verts)
        except ValueError:
            new_bm.free()
            bpy.data.meshes.remove(new_mesh)
            return None

        new_face.material_index = face.material_index
        new_face.smooth = face.smooth

        for src_layer, dst_layer in zip(src_uv_layers, new_uv_layers):
            for i, loop in enumerate(face.loops):
                new_face.loops[i][dst_layer].uv = loop[src_layer].uv

        new_bm.to_mesh(new_mesh)
        new_obj = bpy.data.objects.new(name=f"{obj.name}_face_{face_index:04d}", object_data=new_mesh)

        for mat in obj.data.materials:
            new_obj.data.materials.append(mat)

        context.collection.objects.link(new_obj)
        new_obj.matrix_world = obj.matrix_world

        new_bm.free()
        return new_obj

    def execute(self, context):
        original_mode = None
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Active object is not a mesh")
                return {'CANCELLED'}

            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')

            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.faces.ensure_lookup_table()

            if not bm.loops.layers.uv:
                bm.free()
                self.report({'ERROR'}, "Mesh has no UV layer")
                return {'CANCELLED'}

            uv_layer = bm.loops.layers.uv.verify()

            face_count = len(bm.faces)
            logger.info("Separating '%s' into %d face object(s)", obj.name, face_count)
            wm = context.window_manager
            wm.progress_begin(0, face_count)
            new_objects = []
            for i, face in enumerate(bm.faces):
                new_obj = self.duplicate_face(context, bm, obj, face, i)
                if new_obj is not None:
                    new_objects.append(new_obj)
                if i % 100 == 0:
                    wm.progress_update(i)
            wm.progress_end()

            if new_objects:
                bpy.data.objects.remove(obj, do_unlink=True)

            if new_objects:
                for created_obj in new_objects:
                    created_obj.select_set(True)
                context.view_layer.objects.active = new_objects[0]

            bm.free()

            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)

            self.report({'INFO'}, f"Successfully separated into {len(new_objects)} faces")
            return {'FINISHED'}

        except Exception as e:
            if 'bm' in locals():
                bm.free()
            if original_mode is not None and context.view_layer.objects.active is not None:
                try:
                    bpy.ops.object.mode_set(mode=original_mode)
                except RuntimeError:
                    pass
            logger.exception("Failed to separate mesh by faces")
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            return {'CANCELLED'}


#endregion
#region PANEL
class ZENV_PT_MeshSeparateByUVIsland(bpy.types.Panel):
    """Panel for UV island separation tools"""
    bl_label = "MESH Separate by UV Islands"
    bl_idname = "ZENV_PT_separate_by_uv"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.separatebyuv_islands", icon='OUTLINER_OB_MESH')
        layout.operator("zenv.separatebyuv_faces", icon='OUTLINER_OB_MESH')

#endregion
#region REG
classes = (
    ZENV_OT_MeshSeparateByUVIsland,
    ZENV_OT_MeshSeparateByUVFace,
    ZENV_PT_MeshSeparateByUVIsland,
)

def register():
    """Register all addon classes and configure the module logger handler."""
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
    """Unregister all addon classes and remove the module logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
