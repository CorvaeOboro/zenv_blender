bl_info = {
    "name": 'MESH Separate by UV Quadrants',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250809',
    "description": 'Separate mesh into sliced objects based on UV space quadrants',
    "status": 'working',
    "approved": True,
    "sort_priority": '3',
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "tags": ['UV split'],
    "description_short": 'split mesh along UV seams and transform',
    "description_medium": 'Separate mesh into sliced objects based on UV space quadrants , useful to cut a tiling landscape texture into its texture "tiles" for painting or transition baking',
    "description_long": """
Separate Mesh by UV Quadrants
the selected mesh is sliced and separated into objects based on UV space quadrants
stores original positions , transforms the mesh to UV space to slice
then transforms back to original positions and localizes UV to zero to one space
""",
    "location": 'View3D > Sidebar > ZENV',
    "doc_url": '',
}

import bpy
import bmesh
from mathutils import Vector, Matrix
from bpy.types import Panel, Operator, PropertyGroup
import math

class ZENV_PG_MeshSeparateByUVQuadrant_Properties(PropertyGroup):
    do_phase_0: bpy.props.BoolProperty(
        name="Phase 0: Prepare Mesh",
        default=True,
        description="Triangulate mesh and separate vertices for UV transformation"
    )
    do_phase_1: bpy.props.BoolProperty(
        name="Phase 1: To UV Space",
        default=True,
        description="Transform mesh to UV space coordinates"
    )
    do_phase_2: bpy.props.BoolProperty(
        name="Phase 2: Separate Quadrants",
        default=True,
        description="Separate mesh into separate objects based on UV quadrants"
    )
    do_phase_3: bpy.props.BoolProperty(
        name="Phase 3: To 3D Space",
        default=True,
        description="Transform separated meshes back to original 3D space"
    )
    do_phase_4: bpy.props.BoolProperty(
        name="Phase 4: UVs to 0-1",
        default=True,
        description="Move all UVs of separated meshes so their bounding box fits in 0-1 space, without scaling."
    )
    quadrant_size: bpy.props.FloatProperty(
        name="Quadrant Size",
        description="Size of UV quadrants (1.0 = one UV tile)",
        default=1.0,
        min=0.1,
        max=10.0,
        step=1
    )

class ZENV_OT_MeshSeparateByUVQuadrant(Operator):
    """Separate mesh into separate objects based on UV quadrants.
    
    This operator performs a multi-phase process:
    1. Prepares mesh by triangulating and separating vertices
    2. Transforms mesh to UV space coordinates
    3. Separates mesh into separate objects based on UV quadrants
    4. Transforms separated meshes back to original 3D space
    """
    bl_idname = "zenv.split_uv_quadrant"
    bl_label = "Separate UV Quadrants"
    bl_options = {'REGISTER', 'UNDO'}
    
    def log_msg(self, message):
        """Print a message to console and Blender's info area"""
        print(message)
        self.report({'INFO'}, message)

    def phase_0_prepare_and_store(self, obj):
        """
        Prepare mesh by completely separating into individual triangles:
        1) Triangulate the mesh
        2) Create new mesh with completely separate triangles
        3) Store UV and original position data for each vertex
        4) Apply all transforms and unparent the object, storing its original world matrix
        5) Store original materials for later restoration
        """
        self.log_msg("=== PHASE 0: Prepare Mesh + Store Original Positions ===")

        # Apply all transforms FIRST
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        # Unparent while keeping transform
        if obj.parent:
            bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

        # Now store the object's original world matrix for later restoration (should now be identity)
        obj["_zenv_original_world_matrix"] = [list(row) for row in obj.matrix_world]

        # Store the object's materials for restoration
        obj["_zenv_materials"] = [mat.name if mat else "" for mat in obj.data.materials]
        # Also store material indices for each face
        face_materials = [p.material_index for p in obj.data.polygons]
        obj["_zenv_face_material_indices"] = face_materials

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get initial BMesh (after transforms applied)
        bm_orig = bmesh.new()
        bm_orig.from_mesh(obj.data)
        # Ensure UV layers exist
        if not bm_orig.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm_orig.free()
            return {'CANCELLED'}
        uv_layer_orig = bm_orig.loops.layers.uv.verify()
        # Triangulate
        bmesh.ops.triangulate(bm_orig, faces=bm_orig.faces[:])
        # Create new BMesh for rebuilt mesh
        bm_new = bmesh.new()
        pos_layer = bm_new.verts.layers.float_vector.new("original_position")
        uv_layer_new = bm_new.loops.layers.uv.new("UVMap")
        triangle_count = 0
        # Process each triangle, creating completely new vertices for each
        for face in bm_orig.faces:
            new_verts = []
            uvs = []
            for loop in face.loops:
                new_vert = bm_new.verts.new(loop.vert.co)
                new_vert[pos_layer] = loop.vert.co.copy()
                new_verts.append(new_vert)
                uvs.append(loop[uv_layer_orig].uv.copy())
            try:
                new_face = bm_new.faces.new(new_verts)
                for loop, uv in zip(new_face.loops, uvs):
                    loop[uv_layer_new].uv = uv
                triangle_count += 1
            except ValueError as e:
                self.log_msg(f"Warning: Could not create face: {str(e)}")
        bm_orig.free()
        bm_new.verts.index_update()
        bm_new.edges.index_update()
        bm_new.faces.index_update()
        bm_new.to_mesh(obj.data)
        bm_new.free()
        self.log_msg(f"Rebuilt mesh with {triangle_count} separate triangles")
        return {'FINISHED'}

    def phase_1_to_uv_space(self, obj):
        """Transform mesh to UV space while storing original positions"""
        self.log_msg("=== PHASE 1: Transform to UV Space ===")
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create BMesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        if not bm.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm.free()
            return {'CANCELLED'}
        
        # Create custom data layer for original positions if it doesn't exist
        pos_layer = bm.verts.layers.float_vector.get("original_position")
        if pos_layer is None:
            pos_layer = bm.verts.layers.float_vector.new("original_position")
        
        # Store original positions before any transformation
        for vert in bm.verts:
            vert[pos_layer] = vert.co.copy()
        
        # Get active UV layer
        uv_layer = bm.loops.layers.uv.verify()
        
        # Transform vertices to UV space
        for face in bm.faces:
            for loop in face.loops:
                vert = loop.vert
                uv = loop[uv_layer].uv
                vert.co.x = uv.x
                vert.co.y = uv.y
                vert.co.z = 0
        
        # Update the mesh
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()
        
        self.log_msg("Transformed to UV space")
        return {'FINISHED'}

    def slice_along_axis(self, bm, axis_value, is_vertical):
        """Slice the mesh along a specific UV axis value"""
        # Define plane normal based on whether we're cutting vertically or horizontally
        if is_vertical:
            plane_co = Vector((axis_value, 0, 0))
            plane_no = Vector((1, 0, 0))
        else:
            plane_co = Vector((0, axis_value, 0))
            plane_no = Vector((0, 1, 0))
        
        # Perform the bisect operation
        result = bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=plane_co,
            plane_no=plane_no,
            clear_inner=False,
            clear_outer=False
        )
        
        return result['geom_cut']

    def phase_2_separate_quadrants(self, obj):
        """Separate mesh into separate objects based on UV quadrants"""
        self.log_msg("=== PHASE 2: Separate UV Quadrants ===")
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create BMesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        if not bm.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm.free()
            return {'CANCELLED'}
        
        # Get UV bounds
        uv_layer = bm.loops.layers.uv.verify()
        pos_layer = bm.verts.layers.float_vector["original_position"]
        
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                min_x = min(min_x, uv.x)
                max_x = max(max_x, uv.x)
                min_y = min(min_y, uv.y)
                max_y = max(max_y, uv.y)
        
        # Calculate cutting boundaries
        whole_min_x = math.floor(min_x - 1)
        whole_max_x = math.ceil(max_x + 1)
        whole_min_y = math.floor(min_y - 1)
        whole_max_y = math.ceil(max_y + 1)
        
        # Ensure we include surrounding integers
        whole_min_x = min(whole_min_x, -1)
        whole_max_x = max(whole_max_x, 1)
        whole_min_y = min(whole_min_y, -1)
        whole_max_y = max(whole_max_y, 1)
        
        def update_new_vertices(new_verts, axis_value, is_vertical):
            """Update UV coordinates and interpolate original positions for new vertices"""
            for new_vert in new_verts:
                # Set UV coordinates based on current position
                new_uv = Vector((new_vert.co.x, new_vert.co.y))
                for loop in new_vert.link_loops:
                    loop[uv_layer].uv = new_uv
                
                # Find connected edges for interpolation
                connected_edges = new_vert.link_edges
                if connected_edges:
                    # Find the edge that crosses our cutting plane
                    crossing_edge = None
                    for edge in connected_edges:
                        v1, v2 = edge.verts
                        if is_vertical:
                            if (v1.co.x - axis_value) * (v2.co.x - axis_value) < 0:
                                crossing_edge = edge
                                break
                        else:
                            if (v1.co.y - axis_value) * (v2.co.y - axis_value) < 0:
                                crossing_edge = edge
                                break
                    
                    if crossing_edge:
                        # Interpolate original position
                        v1, v2 = crossing_edge.verts
                        pos1 = Vector(v1[pos_layer])
                        pos2 = Vector(v2[pos_layer])
                        
                        # Calculate interpolation factor
                        if is_vertical:
                            total_dist = abs(v2.co.x - v1.co.x)
                            if total_dist > 0:
                                factor = abs(new_vert.co.x - v1.co.x) / total_dist
                            else:
                                factor = 0.5
                        else:
                            total_dist = abs(v2.co.y - v1.co.y)
                            if total_dist > 0:
                                factor = abs(new_vert.co.y - v1.co.y) / total_dist
                            else:
                                factor = 0.5
                        
                        # Set interpolated position
                        new_vert[pos_layer] = pos1.lerp(pos2, factor)
        
        # First, perform all vertical cuts
        for x in range(whole_min_x, whole_max_x + 1):
            try:
                new_verts = self.slice_along_axis(bm, x, True)
                update_new_vertices(new_verts, x, True)
            except Exception as e:
                self.log_msg(f"Warning: Vertical cut at x={x} failed: {str(e)}")
        
        # Then perform all horizontal cuts
        for y in range(whole_min_y, whole_max_y + 1):
            try:
                new_verts = self.slice_along_axis(bm, y, False)
                update_new_vertices(new_verts, y, False)
            except Exception as e:
                self.log_msg(f"Warning: Horizontal cut at y={y} failed: {str(e)}")
        
        # Update mesh indices
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        
        # Now separate into quadrants
        quadrant_faces = {}
        
        # First, group faces by quadrant
        for face in bm.faces:
            # Calculate face center in UV space
            center_uv = Vector((0, 0))
            for loop in face.loops:
                center_uv += loop[uv_layer].uv
            center_uv /= len(face.loops)
            
            # Determine quadrant
            quad_x = math.floor(center_uv.x)
            quad_y = math.floor(center_uv.y)
            quadrant = (quad_x, quad_y)
            
            if quadrant not in quadrant_faces:
                quadrant_faces[quadrant] = []
            quadrant_faces[quadrant].append(face)
        
        # Create new objects for each quadrant
        created_objects = []
        # Retrieve original world matrix if present
        orig_matrix = None
        orig_materials = None
        orig_face_material_indices = None
        if "_zenv_original_world_matrix" in obj:
            om = obj["_zenv_original_world_matrix"]
            orig_matrix = Matrix([Vector(row) for row in om])
        if "_zenv_materials" in obj:
            orig_materials = obj["_zenv_materials"]
        if "_zenv_face_material_indices" in obj:
            orig_face_material_indices = obj["_zenv_face_material_indices"]
        orig_name = obj.name
        for quadrant, faces in quadrant_faces.items():
            quad_x, quad_y = quadrant
            # Build base name
            base_name = f"{orig_name}_uv_{quad_x}_{quad_y}"
            mesh_name = base_name
            obj_name = base_name
            # Ensure mesh name is unique
            suffix = 1
            while mesh_name in bpy.data.meshes or obj_name in bpy.data.objects:
                mesh_name = f"{base_name}_{suffix}"
                obj_name = f"{base_name}_{suffix}"
                suffix += 1
            new_mesh = bpy.data.meshes.new(name=mesh_name)
            new_bm = bmesh.new()
            new_pos_layer = new_bm.verts.layers.float_vector.new("original_position")
            new_uv_layer = new_bm.loops.layers.uv.verify()
            vert_map = {}
            face_map = []
            for face in faces:
                new_verts = []
                for vert in face.verts:
                    if vert not in vert_map:
                        new_vert = new_bm.verts.new(vert.co)
                        new_vert[new_pos_layer] = vert[pos_layer]
                        vert_map[vert] = new_vert
                    new_verts.append(vert_map[vert])
                new_face = new_bm.faces.new(new_verts)
                for loop, new_loop in zip(face.loops, new_face.loops):
                    new_loop[new_uv_layer].uv = loop[uv_layer].uv
                face_map.append((new_face, face.index))
            new_bm.to_mesh(new_mesh)
            new_bm.free()
            # Assign original materials to the new mesh
            if orig_materials:
                new_mesh.materials.clear()
                for mat_name in orig_materials:
                    if mat_name and mat_name in bpy.data.materials:
                        new_mesh.materials.append(bpy.data.materials[mat_name])
                    else:
                        new_mesh.materials.append(None)
            # Restore material indices for faces
            if orig_face_material_indices:
                for new_face, old_face_index in zip(new_mesh.polygons, range(len(faces))):
                    if old_face_index < len(orig_face_material_indices):
                        new_mesh.polygons[new_face.index].material_index = orig_face_material_indices[old_face_index]
            new_obj = bpy.data.objects.new(name=obj_name, object_data=new_mesh)
            bpy.context.scene.collection.objects.link(new_obj)
            # Restore original world matrix if available
            if orig_matrix:
                new_obj.matrix_world = orig_matrix.copy()
            new_obj.select_set(True)
            created_objects.append(new_obj)
        # Remove the original object from all collections and Blender data
        for coll in obj.users_collection:
            coll.objects.unlink(obj)
        bpy.data.objects.remove(obj)
        bm.free()
        
        # Set the first created object as active
        if created_objects:
            bpy.context.view_layer.objects.active = created_objects[0]
        
        self.log_msg(f"Separated into {len(created_objects)} quadrants")
        return {'FINISHED'}

    def phase_3_to_3d_space(self, context):
        """Transform separated objects back to 3D space using original positions"""
        self.log_msg("=== PHASE 3: Transform to 3D Space ===")
        
        # Process all selected objects (the quadrants)
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            
            # Get the original position layer
            pos_layer = bm.verts.layers.float_vector.get("original_position")
            if not pos_layer:
                self.log_msg(f"No original position data found for {obj.name}. Skipping.")
                bm.free()
                continue
            
            # Transform vertices back to original positions
            for vert in bm.verts:
                try:
                    orig_pos = vert[pos_layer]
                    vert.co = Vector(orig_pos)
                except (KeyError, IndexError, TypeError):
                    continue
            
            # Update the mesh
            bm.to_mesh(obj.data)
            obj.data.update()
            bm.free()
        
        self.log_msg("Transformed objects back to 3D space")
        return {'FINISHED'}

    def phase_4_merge_by_distance(self, context):
        """(DISABLED) Merge vertices and UVs at very small distances to reconstruct the meshes (no-op as per user request)"""
        self.log_msg("=== PHASE 4: Merging Vertices and UVs (DISABLED) ===")
        # No operation performed to avoid collapsing meshes
        return {'FINISHED'}

    def phase_4_move_uvs_to_01(self, context):
        """Offset each mesh's UVs so their original tile/quadrant is mapped to 0-1, preserving texture mapping."""
        self.log_msg("=== PHASE 5: Move UVs to 0-1 Space (per tile offset)===" )
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            if not bm.loops.layers.uv:
                bm.free()
                continue
            uv_layer = bm.loops.layers.uv.verify()
            # Find min UV
            min_uv = [float('inf'), float('inf')]
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    min_uv[0] = min(min_uv[0], uv.x)
                    min_uv[1] = min(min_uv[1], uv.y)
            # Only proceed if we found any valid UVs
            if min_uv[0] == float('inf') or min_uv[1] == float('inf'):
                self.log_msg(f"Skipping {obj.name}: no valid UVs found.")
                bm.free()
                continue
            # Compute integer tile offset
            tile_offset = (math.floor(min_uv[0]), math.floor(min_uv[1]))
            # Offset all UVs by -tile_offset
            for face in bm.faces:
                for loop in face.loops:
                    loop[uv_layer].uv -= Vector(tile_offset)
            bm.to_mesh(mesh)
            mesh.update()
            bm.free()
        self.log_msg("Offset all UVs by their tile, now in 0-1 space and texture mapping preserved")
        return {'FINISHED'}

    def execute(self, context):
        """Execute the UV quadrant separating operation"""
        try:
            # Get the active object
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "No valid mesh object selected")
                return {'CANCELLED'}
            
            props = context.scene.zenv_split_uv_props
            if props.do_phase_0:
                result = self.phase_0_prepare_and_store(obj)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_1:
                result = self.phase_1_to_uv_space(obj)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_2:
                result = self.phase_2_separate_quadrants(obj)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_3:
                result = self.phase_3_to_3d_space(context)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_4:
                result = self.phase_4_move_uvs_to_01(context)
                if result != {'FINISHED'}:
                    return result

            self.report({'INFO'}, "Successfully separated mesh by UV quadrants")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error processing mesh: {str(e)}")
            try:
                if obj and hasattr(obj, 'mode') and obj.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass
            return {'CANCELLED'}

class ZENV_PT_MeshSeparateByUVQuadrant_Panel(Panel):
    """Panel for controlling UV quadrant separating operations.
    
    Provides controls for:
    - Mesh preparation and vertex separation
    - UV space transformation
    - Quadrant separation
    - 3D space transformation
    - Move UVs to 0-1 space
    """
    bl_label = "MESH Separate by UV Quadrants"
    bl_idname = "ZENV_PT_MeshSeparateByUVQuadrant"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_split_uv_props
        
        col = layout.column(align=True)
        col.prop(props, "do_phase_0", text="0: Prepare Mesh")
        col.prop(props, "do_phase_1", text="1: To UV Space")
        col.prop(props, "do_phase_2", text="2: Separate Quadrants")
        col.prop(props, "do_phase_3", text="3: To 3D Space")
        col.prop(props, "do_phase_4", text="4: UVs to 0-1")
        
        box = layout.box()
        box.prop(props, "quadrant_size")
        
        layout.operator("zenv.split_uv_quadrant")

# Registration
classes = (
    ZENV_PG_MeshSeparateByUVQuadrant_Properties,
    ZENV_OT_MeshSeparateByUVQuadrant,
    ZENV_PT_MeshSeparateByUVQuadrant_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_split_uv_props = bpy.props.PointerProperty(type=ZENV_PG_MeshSeparateByUVQuadrant_Properties)

def unregister():
    del bpy.types.Scene.zenv_split_uv_props
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
