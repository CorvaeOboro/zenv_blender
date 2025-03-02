"""
Split Mesh by UV Quadrants
Splits mesh into separate objects based on UV space quadrants
"""

bl_info = {
    "name": "Split by UV Quadrants",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV",
    "description": "Split mesh into separate objects based on UV space quadrants",
    "warning": "",
    "doc_url": "",
    "category": "ZENV",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.types import Panel, Operator, PropertyGroup
import math

class ZENV_PG_SplitUVQuadrant(PropertyGroup):
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
        name="Phase 2: Split Quadrants",
        default=True,
        description="Split mesh into separate objects based on UV quadrants"
    )
    do_phase_3: bpy.props.BoolProperty(
        name="Phase 3: To 3D Space",
        default=True,
        description="Transform split meshes back to original 3D space"
    )
    do_phase_4: bpy.props.BoolProperty(
        name="Phase 4: Merge Vertices",
        default=True,
        description="Merge vertices and UVs at very small distances to reconstruct the meshes"
    )
    quadrant_size: bpy.props.FloatProperty(
        name="Quadrant Size",
        description="Size of UV quadrants (1.0 = one UV tile)",
        default=1.0,
        min=0.1,
        max=10.0,
        step=1
    )

class ZENV_OT_SplitUVQuadrant(Operator):
    """Split mesh into separate objects based on UV quadrants.
    
    This operator performs a multi-phase process:
    1. Prepares mesh by triangulating and separating vertices
    2. Transforms mesh to UV space coordinates
    3. Splits mesh into separate objects based on UV quadrants
    4. Transforms split meshes back to original 3D space
    5. Merges vertices and UVs to reconstruct the meshes
    """
    bl_idname = "zenv.split_uv_quadrant"
    bl_label = "Split UV Quadrants"
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
        """
        self.log_msg("=== PHASE 0: Prepare Mesh + Store Original Positions ===")

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get initial BMesh
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
            # Create three new vertices for this triangle
            new_verts = []
            uvs = []
            
            for loop in face.loops:
                # Create new vertex with original position
                new_vert = bm_new.verts.new(loop.vert.co)
                new_vert[pos_layer] = loop.vert.co.copy()
                new_verts.append(new_vert)
                # Store UV coordinates
                uvs.append(loop[uv_layer_orig].uv.copy())
            
            try:
                # Create new face
                new_face = bm_new.faces.new(new_verts)
                # Assign UV coordinates
                for loop, uv in zip(new_face.loops, uvs):
                    loop[uv_layer_new].uv = uv
                triangle_count += 1
            except ValueError as e:
                self.log_msg(f"Warning: Could not create face: {str(e)}")
        
        # Clean up original BMesh
        bm_orig.free()
        
        # Update indices
        bm_new.verts.index_update()
        bm_new.edges.index_update()
        bm_new.faces.index_update()
        
        # Update the mesh
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

    def phase_2_split_quadrants(self, obj):
        """Split mesh into separate objects based on UV quadrants"""
        self.log_msg("=== PHASE 2: Split UV Quadrants ===")
        
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
        for quadrant, faces in quadrant_faces.items():
            # Create new mesh and BMesh
            new_mesh = bpy.data.meshes.new(name=f"quadrant_{quadrant[0]}_{quadrant[1]}")
            new_bm = bmesh.new()
            
            # Create vertex layer for original positions
            new_pos_layer = new_bm.verts.layers.float_vector.new("original_position")
            new_uv_layer = new_bm.loops.layers.uv.verify()
            
            # Create vertex map for copying
            vert_map = {}
            
            # Copy faces and their vertices
            for face in faces:
                # Create vertices if they don't exist
                new_verts = []
                for vert in face.verts:
                    if vert not in vert_map:
                        new_vert = new_bm.verts.new(vert.co)
                        new_vert[new_pos_layer] = vert[pos_layer]
                        vert_map[vert] = new_vert
                    new_verts.append(vert_map[vert])
                
                # Create face
                new_face = new_bm.faces.new(new_verts)
                
                # Copy UV coordinates
                for loop, new_loop in zip(face.loops, new_face.loops):
                    new_loop[new_uv_layer].uv = loop[uv_layer].uv
            
            # Finalize the new mesh
            new_bm.to_mesh(new_mesh)
            new_bm.free()
            
            # Create new object
            new_obj = bpy.data.objects.new(name=f"quadrant_{quadrant[0]}_{quadrant[1]}", object_data=new_mesh)
            bpy.context.scene.collection.objects.link(new_obj)
            new_obj.select_set(True)
            created_objects.append(new_obj)
        
        # Clean up original object
        bpy.context.scene.collection.objects.unlink(obj)
        bpy.data.objects.remove(obj)
        bm.free()
        
        # Set the first created object as active
        if created_objects:
            bpy.context.view_layer.objects.active = created_objects[0]
        
        self.log_msg(f"Split into {len(created_objects)} quadrants")
        return {'FINISHED'}

    def phase_3_to_3d_space(self, context):
        """Transform split objects back to 3D space using original positions"""
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
                if pos_layer in vert:
                    orig_pos = vert[pos_layer]
                    vert.co = Vector(orig_pos)
            
            # Update the mesh
            bm.to_mesh(obj.data)
            obj.data.update()
            bm.free()
        
        self.log_msg("Transformed objects back to 3D space")
        return {'FINISHED'}

    def phase_4_merge_by_distance(self, context):
        """Merge vertices and UVs at very small distances to reconstruct the meshes"""
        self.log_msg("=== PHASE 4: Merging Vertices and UVs ===")
        
        total_weld_count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            bm = bmesh.new()
            bm.from_mesh(obj.data)
            
            if not bm.loops.layers.uv:
                self.log_msg(f"No UV layers found in {obj.name}. Skipping.")
                bm.free()
                continue

            uv_layer = bm.loops.layers.uv.verify()
            
            # Use very small merge distances
            MERGE_DISTANCE = 0.00001  # For vertex positions
            UV_GRID_SIZE = 0.000001   # For UV coordinate binning
            
            # First, create a map of vertices by their UV coordinates
            uv_vert_map = {}
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    vert = loop.vert
                    key = (round(uv.x / UV_GRID_SIZE), round(uv.y / UV_GRID_SIZE))
                    
                    if key not in uv_vert_map:
                        uv_vert_map[key] = []
                    uv_vert_map[key].append((vert, uv.copy()))

            # Merge vertices that share the same UV coordinates (within merge distance)
            weld_count = 0
            for verts_and_uvs in uv_vert_map.values():
                if len(verts_and_uvs) > 1:
                    # Keep the first vertex as target
                    target_vert = verts_and_uvs[0][0]
                    target_uv = verts_and_uvs[0][1]
                    
                    # Collect vertices to merge
                    verts_to_merge = []
                    for other_vert, other_uv in verts_and_uvs[1:]:
                        if (target_vert.co - other_vert.co).length <= MERGE_DISTANCE:
                            verts_to_merge.append(other_vert)
                    
                    if verts_to_merge:
                        # Use BMesh weld operator to merge vertices
                        bmesh.ops.weld_verts(bm, targetmap={v: target_vert for v in verts_to_merge})
                        weld_count += len(verts_to_merge)
                        
                        # Update UV coordinates for the merged vertices' faces
                        for face in target_vert.link_faces:
                            for loop in face.loops:
                                if loop.vert == target_vert:
                                    loop[uv_layer].uv = target_uv

            # Update mesh indices
            bm.verts.index_update()
            bm.edges.index_update()
            bm.faces.index_update()
            
            # Remove doubles to clean up the mesh
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=MERGE_DISTANCE)
            
            # Update the mesh
            bm.to_mesh(obj.data)
            obj.data.update()
            bm.free()
            
            total_weld_count += weld_count
        
        self.log_msg(f"Merged {total_weld_count} vertices across all objects")
        return {'FINISHED'}

    def execute(self, context):
        """Execute the UV quadrant splitting operation"""
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
                result = self.phase_2_split_quadrants(obj)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_3:
                result = self.phase_3_to_3d_space(context)
                if result != {'FINISHED'}:
                    return result

            if props.do_phase_4:
                result = self.phase_4_merge_by_distance(context)
                if result != {'FINISHED'}:
                    return result

            self.report({'INFO'}, "Successfully split mesh by UV quadrants")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error processing mesh: {str(e)}")
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

class ZENV_PT_SplitUVQuadrant(Panel):
    """Panel for controlling UV quadrant splitting operations.
    
    Provides controls for:
    - Mesh preparation and vertex separation
    - UV space transformation
    - Quadrant splitting
    - 3D space transformation
    - Vertex merging and mesh reconstruction
    """
    bl_label = "MESH Split UV Quadrants"
    bl_idname = "ZENV_PT_SplitUVQuadrant"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_split_uv_props
        
        col = layout.column(align=True)
        col.prop(props, "do_phase_0")
        col.prop(props, "do_phase_1")
        col.prop(props, "do_phase_2")
        col.prop(props, "do_phase_3")
        col.prop(props, "do_phase_4")
        
        box = layout.box()
        box.prop(props, "quadrant_size")
        
        layout.operator("zenv.split_uv_quadrant")

# Registration
classes = (
    ZENV_PG_SplitUVQuadrant,
    ZENV_OT_SplitUVQuadrant,
    ZENV_PT_SplitUVQuadrant,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_split_uv_props = bpy.props.PointerProperty(type=ZENV_PG_SplitUVQuadrant)

def unregister():
    del bpy.types.Scene.zenv_split_uv_props
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
