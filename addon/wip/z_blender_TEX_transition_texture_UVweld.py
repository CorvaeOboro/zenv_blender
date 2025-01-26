# TEXTURE TRANSITION by UV STITCHING
# two meshes that are touching , merge them and weld their UVs
# creating a seamless texture transition by UV stitching , where the target uv island is snapped to match
# then texture bake the merged onto the target mesh
# bakes saved to "00_bake_texture" subfolder by target object name

bl_info = {
    "name": "TEX Transition Texture UV Stitch",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 3),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Create a transition between two meshes by UV stitching ",
}

import bpy
import bmesh
import mathutils
from mathutils import Vector
import math
import os
import tempfile

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Logger:
    """Logger class for UV welding operations"""
    
    @staticmethod
    def log_info(message, category="INFO"):
        print(f"[{category}] {message}")
    
    @staticmethod
    def log_error(message):
        print(f"[ERROR] {message}")

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Properties:
    """Property management for UV welding addon"""
    
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_weld_debug = bpy.props.BoolProperty(
            name="Debug Mode",
            description="Enable debug logging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_steps = bpy.props.BoolProperty(
            name="Step Mode",
            description="Execute steps separately for debugging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_cleanup = bpy.props.BoolProperty(
            name="Cleanup",
            description="Remove temporary objects after welding",
            default=True
        )

        # Baking properties
        bpy.types.Scene.zenv_weld_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_weld_debug
        del bpy.types.Scene.zenv_weld_steps
        del bpy.types.Scene.zenv_weld_cleanup
        del bpy.types.Scene.zenv_weld_resolution

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Utils:
    """Utility functions for UV welding"""

    @staticmethod
    def get_shared_edges(source_obj, target_obj):
        """Find edges that are touching between two meshes (in world-space)."""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info(f"Starting edge analysis between {source_obj.name} and {target_obj.name}", "EDGE DETECTION")
        
        bm1 = bmesh.new()
        bm1.from_mesh(source_obj.data)
        bm1.verts.ensure_lookup_table()
        bm1.edges.ensure_lookup_table()
        bm1.faces.ensure_lookup_table()
        
        bm2 = bmesh.new()
        bm2.from_mesh(target_obj.data)
        bm2.verts.ensure_lookup_table()
        bm2.edges.ensure_lookup_table()
        bm2.faces.ensure_lookup_table()
        
        source_matrix = source_obj.matrix_world
        target_matrix = target_obj.matrix_world

        verts1_world = [source_matrix @ v.co for v in bm1.verts]
        verts2_world = [target_matrix @ v.co for v in bm2.verts]

        logger.log_info(f"Source mesh has {len(bm1.verts)} verts / {len(bm1.edges)} edges", "INFO")
        logger.log_info(f"Target mesh has {len(bm2.verts)} verts / {len(bm2.edges)} edges", "INFO")
        
        threshold = 0.01  # Increase if needed for near matches
        
        # Build dictionary for potential matches in target
        from collections import defaultdict
        def round_vec(v, digits=4):
            return (round(v.x, digits), round(v.y, digits), round(v.z, digits))
        
        dict2 = defaultdict(list)
        for j, coord in enumerate(verts2_world):
            dict2[round_vec(coord)].append(j)
        
        # Find vertex pairs that are within threshold
        vert_pairs = []
        for i, c1 in enumerate(verts1_world):
            c1r = round_vec(c1)
            if c1r in dict2:
                for j in dict2[c1r]:
                    if (c1 - verts2_world[j]).length < threshold:
                        vert_pairs.append((i, j))
        
        shared_edges = []
        # For each edge in source, see if both vertices match edges in target
        for e1 in bm1.edges:
            v1a = e1.verts[0].index
            v1b = e1.verts[1].index
            
            # Which target vertices do those correspond to?
            t_matches_a = [vp[1] for vp in vert_pairs if vp[0] == v1a]
            t_matches_b = [vp[1] for vp in vert_pairs if vp[0] == v1b]
            if not t_matches_a or not t_matches_b:
                continue
            
            # For every pair (tva, tvb), see if there's an edge in bm2
            for tva in t_matches_a:
                for tvb in t_matches_b:
                    e2_candidates = [
                        e2 for e2 in bm2.edges
                        if {e2.verts[0].index, e2.verts[1].index} == {tva, tvb}
                    ]
                    for e2 in e2_candidates:
                        # Found a shared edge
                        e1_dir = (verts1_world[v1b] - verts1_world[v1a]).normalized()
                        e1_length = (verts1_world[v1b] - verts1_world[v1a]).length
                        
                        shared_edges.append((
                            e1.index,
                            e2.index,
                            {
                                'edge_dir': e1_dir,
                                'edge_length': e1_length,
                                'source_verts': [v1a, v1b],
                                'target_verts': [e2.verts[0].index, e2.verts[1].index]
                            }
                        ))
        
        bm1.free()
        bm2.free()
        
        # Deduplicate
        unique = []
        seen = set()
        for item in shared_edges:
            src_vs = tuple(sorted(item[2]['source_verts']))
            tgt_vs = tuple(sorted(item[2]['target_verts']))
            combo = (src_vs, tgt_vs)
            if combo not in seen:
                seen.add(combo)
                unique.append(item)
        
        shared_edges = unique
        
        logger.log_info(f"Found {len(shared_edges)} shared edges", "EDGE DETECTION COMPLETE")
        return shared_edges

    @staticmethod
    def create_merged_mesh(source_obj, target_obj, shared_edges):
        """
        Merge source + target into a single BMesh, weld the seam, 
        build final vertex groups, and store final face sets in custom props.
        """
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("===== CREATE_MERGED_MESH: START =====")

        # Duplicates for debugging
        def duplicate_object(obj, suffix):
            new_data = obj.data.copy()
            new_obj = obj.copy()
            new_obj.data = new_data
            new_obj.name = f"_TEMP_{obj.name}_{suffix}"
            bpy.context.scene.collection.objects.link(new_obj)
            return new_obj
        
        temp_source = duplicate_object(source_obj, "source")
        temp_target = duplicate_object(target_obj, "target")

        # Create new mesh + object to hold merged
        merged_mesh = bpy.data.meshes.new(name=f"{source_obj.name}_merged")
        merged_obj = bpy.data.objects.new(merged_mesh.name, merged_mesh)
        bpy.context.scene.collection.objects.link(merged_obj)

        bm = bmesh.new()

        # Build BMesh for source
        bm_source = bmesh.new()
        bm_source.from_mesh(source_obj.data)
        bm_source.verts.ensure_lookup_table()
        bm_source.edges.ensure_lookup_table()
        bm_source.faces.ensure_lookup_table()

        # Build BMesh for target
        bm_target = bmesh.new()
        bm_target.from_mesh(target_obj.data)
        bm_target.verts.ensure_lookup_table()
        bm_target.edges.ensure_lookup_table()
        bm_target.faces.ensure_lookup_table()

        logger.log_info(f"Source BMesh: {len(bm_source.verts)} verts, {len(bm_source.edges)} edges, {len(bm_source.faces)} faces")
        logger.log_info(f"Target BMesh: {len(bm_target.verts)} verts, {len(bm_target.edges)} edges, {len(bm_target.faces)} faces")

        source_map = {}
        target_map = {}

        # (A) Copy source geometry in world space
        src_mat = source_obj.matrix_world
        for v in bm_source.verts:
            new_v = bm.verts.new(src_mat @ v.co)
            source_map[v] = new_v
        
        bm.verts.ensure_lookup_table()

        source_face_map = {}
        for f in bm_source.faces:
            new_f = bm.faces.new(source_map[v] for v in f.verts)
            source_face_map[f] = new_f
        
        bm.faces.ensure_lookup_table()

        # (B) Copy target geometry in world space
        tgt_mat = target_obj.matrix_world
        for v in bm_target.verts:
            new_v = bm.verts.new(tgt_mat @ v.co)
            target_map[v] = new_v
        
        bm.verts.ensure_lookup_table()

        target_face_map = {}
        for f in bm_target.faces:
            try:
                new_f = bm.faces.new(target_map[v] for v in f.verts)
                target_face_map[f] = new_f
            except ValueError:
                logger.log_info("Skipping duplicate face in target mesh", "MERGE")
        
        bm.faces.ensure_lookup_table()
        logger.log_info(f"Post-copy, merged BMesh has {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces", "MERGE")

        # (C) Prepare the weld map from shared_edges
        weld_map = {}
        old_source_seam_verts = set()
        old_target_seam_verts = set()

        for i, edge_info in enumerate(shared_edges):
            s_vs = edge_info[2]['source_verts']  # [v1, v2]
            t_vs = edge_info[2]['target_verts']  # [v3, v4]

            s0 = bm_source.verts[s_vs[0]]
            s1 = bm_source.verts[s_vs[1]]
            t0 = bm_target.verts[t_vs[0]]
            t1 = bm_target.verts[t_vs[1]]

            old_source_seam_verts.update([s0, s1])
            old_target_seam_verts.update([t0, t1])

            new_s0 = source_map[s0]
            new_s1 = source_map[s1]
            new_t0 = target_map[t0]
            new_t1 = target_map[t1]

            # Weld target side into source side
            weld_map[new_t0] = new_s0
            weld_map[new_t1] = new_s1
        
        logger.log_info(f"Will weld {len(weld_map)} target verts into source verts", "WELD")

        bmesh.ops.weld_verts(bm, targetmap=weld_map)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        logger.log_info(f"After weld, merged BMesh has {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces", "WELD")

        # (D) Create a final UV layer
        uv_layer = bm.loops.layers.uv.new()
        src_uv_layer = bm_source.loops.layers.uv.active
        tgt_uv_layer = bm_target.loops.layers.uv.active

        # Copy UVs from source
        if src_uv_layer:
            for old_f, new_f in source_face_map.items():
                if new_f and new_f.is_valid:
                    for old_loop, new_loop in zip(old_f.loops, new_f.loops):
                        new_loop[uv_layer].uv = old_loop[src_uv_layer].uv.copy()

        # Copy UVs from target
        if tgt_uv_layer:
            for old_f, new_f in target_face_map.items():
                if new_f and new_f.is_valid:
                    for old_loop, new_loop in zip(old_f.loops, new_f.loops):
                        new_loop[uv_layer].uv = old_loop[tgt_uv_layer].uv.copy()

        bm.normal_update()

        # (E) Build face‐index sets so 'weld_uvs' can identify boundary edges
        bm.faces.ensure_lookup_table()
        source_face_indices = set()
        target_face_indices = set()

        for sf, new_f in source_face_map.items():
            if new_f and new_f.is_valid:
                source_face_indices.add(new_f.index)
        for tf, new_f in target_face_map.items():
            if new_f and new_f.is_valid:
                target_face_indices.add(new_f.index)

        # (F) Convert BMesh → mesh
        bm.to_mesh(merged_mesh)
        bm.free()

        merged_obj["temp_source"] = temp_source.name
        merged_obj["temp_target"] = temp_target.name

        # Save face sets in custom props
        merged_obj["source_faces"] = list(source_face_indices)
        merged_obj["target_faces"] = list(target_face_indices)

        # (G) Build vertex groups
        logger.log_info("Building vertex groups after weld...", "GROUPS")
        grp_source = merged_obj.vertex_groups.new(name="source_verts")
        grp_target = merged_obj.vertex_groups.new(name="target_verts")
        grp_seam   = merged_obj.vertex_groups.new(name="seam_verts")

        # Make an array of final world coords:
        final_coords = [merged_obj.matrix_world @ v.co for v in merged_mesh.vertices]

        def find_final_index(world_co, tolerance=1e-6):
            # find a match in final_coords
            for i, c in enumerate(final_coords):
                if (c - world_co).length <= tolerance:
                    return i
            return None

        # Build sets for final source, target, seam
        final_source_indices = set()
        final_target_indices = set()
        final_seam_indices = set()

        # For each old source vertex -> find final index
        for old_v in bm_source.verts:
            wc = source_obj.matrix_world @ old_v.co
            idx = find_final_index(wc)
            if idx is not None:
                final_source_indices.add(idx)

        # For each old target vertex
        for old_v in bm_target.verts:
            wc = target_obj.matrix_world @ old_v.co
            idx = find_final_index(wc)
            if idx is not None:
                final_target_indices.add(idx)

        # For seam
        for old_v in old_source_seam_verts:
            wc = source_obj.matrix_world @ old_v.co
            idx = find_final_index(wc)
            if idx is not None:
                final_seam_indices.add(idx)
        for old_v in old_target_seam_verts:
            wc = target_obj.matrix_world @ old_v.co
            idx = find_final_index(wc)
            if idx is not None:
                final_seam_indices.add(idx)

        if final_source_indices:
            grp_source.add(list(final_source_indices), 1.0, 'ADD')
        if final_target_indices:
            grp_target.add(list(final_target_indices), 1.0, 'ADD')
        if final_seam_indices:
            grp_seam.add(list(final_seam_indices), 1.0, 'ADD')

        logger.log_info(f"source_verts group size = {len(final_source_indices)}", "GROUPS")
        logger.log_info(f"target_verts group size = {len(final_target_indices)}", "GROUPS")
        logger.log_info(f"seam_verts group size   = {len(final_seam_indices)}", "GROUPS")

        logger.log_info("===== CREATE_MERGED_MESH: END =====")
        return merged_obj


    @staticmethod
    def weld_uvs(obj, shared_edges):
        """
        Additional pass to 'stitch' only the target-side UV edges along the seam.
        """
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("===== weld_uvs: START (stitch target side) =====")

        # Store original mode and active object
        original_mode = bpy.context.active_object.mode if bpy.context.active_object else 'OBJECT'
        original_active = bpy.context.active_object
        original_area = bpy.context.area.type if bpy.context.area else None
        original_sync = bpy.context.scene.tool_settings.use_uv_select_sync
        original_select_mode = tuple(bpy.context.tool_settings.mesh_select_mode)

        try:
            # Ensure we're in object mode first
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Set the object as active and selected
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')

            # Get BMesh and ensure UV layer exists
            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            uv_layer = bm.loops.layers.uv.active

            if uv_layer is None:
                logger.log_error("No active UV layer found; cannot stitch.")
                return obj

            # Get face sets
            source_faces = set(obj.get("source_faces", []))
            target_faces = set(obj.get("target_faces", []))
            logger.log_info(f"Stitch: source_faces={len(source_faces)}, target_faces={len(target_faces)}")

            # First deselect all
            bpy.ops.mesh.select_all(action='DESELECT')
            
            # Find a suitable area to convert to UV editor
            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break
            
            if not area:
                logger.log_error("Could not find suitable 3D View area")
                return obj
            
            # Store original area type
            original_area_type = area.type
            
            try:
                # Convert area to IMAGE_EDITOR
                area.type = 'IMAGE_EDITOR'
                
                # Set up UV editing mode
                for space in area.spaces:
                    if space.type == 'IMAGE_EDITOR':
                        space.mode = 'UV'
                
                # Get the region for the UV editor
                region = None
                for r in area.regions:
                    if r.type == 'WINDOW':
                        region = r
                        break
                
                if region:
                    with bpy.context.temp_override(area=area, region=region):
                        # Enable sync and face selection mode
                        bpy.context.scene.tool_settings.use_uv_select_sync = True
                        bpy.context.tool_settings.mesh_select_mode = (False, False, True)  # Face mode
                        
                        # Ensure we're in face select mode for UVs
                        bpy.context.tool_settings.uv_select_mode = 'FACE'
                        
                        # Select source vertex group
                        if "source_verts" in obj.vertex_groups:
                            # Switch to vertex mode temporarily to select vertex group
                            bpy.context.tool_settings.mesh_select_mode = (True, False, False)
                            bpy.ops.object.vertex_group_set_active(group='source_verts')
                            bpy.ops.object.vertex_group_select()
                            
                            # Switch back to face mode
                            bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                            
                            # Update the mesh to ensure selection is reflected
                            bmesh.update_edit_mesh(obj.data)
                            
                            # Make sure sync is still on and we're in face mode
                            bpy.context.scene.tool_settings.use_uv_select_sync = True
                            bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                            bpy.context.tool_settings.uv_select_mode = 'FACE'
                            
                            # Perform the stitch
                            bpy.ops.uv.stitch(use_limit=False, snap_islands=True, limit=0.01)
                        else:
                            logger.log_error("source_verts vertex group not found")
                else:
                    logger.log_error("Could not find suitable region in IMAGE_EDITOR")
                
            except Exception as e:
                logger.log_error(f"UV stitch failed: {str(e)}")
            
            finally:
                # Restore area type
                area.type = original_area_type

        except Exception as e:
            logger.log_error(f"Error during UV stitching: {str(e)}")
        
        finally:
            # Restore original context
            if original_area:
                bpy.context.area.type = original_area
            
            # Restore selection mode
            bpy.context.tool_settings.mesh_select_mode = original_select_mode
            
            # Restore UV sync mode
            bpy.context.scene.tool_settings.use_uv_select_sync = original_sync
                
            # Return to object mode first
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Restore original active object and its mode
            if original_active:
                bpy.context.view_layer.objects.active = original_active
                if original_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=original_mode)
        
        logger.log_info("===== weld_uvs: END (stitch target side) =====")
        return obj

    @staticmethod
    def cleanup_temp_objects(obj):
        logger = ZENV_TransitionTextureWeld_Logger
        temp_source_name = obj.get("temp_source", None)
        temp_target_name = obj.get("temp_target", None)
        
        if temp_source_name:
            temp_source = bpy.data.objects.get(temp_source_name)
            if temp_source:
                logger.log_info(f"Removing temp object: {temp_source.name}")
                bpy.data.objects.remove(temp_source, do_unlink=True)
        
        if temp_target_name:
            temp_target = bpy.data.objects.get(temp_target_name)
            if temp_target:
                logger.log_info(f"Removing temp object: {temp_target.name}")
                bpy.data.objects.remove(temp_target, do_unlink=True)

    @staticmethod
    def setup_render_settings(context):
        """Setup render settings for baking"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Setting up render settings...")
        
        # Store original render engine
        original_engine = context.scene.render.engine
        
        # Set to Cycles for baking
        context.scene.render.engine = 'CYCLES'
        
        # Configure Cycles settings for best quality
        if hasattr(context.scene, 'cycles'):
            context.scene.cycles.samples = 512  # Increase samples for better quality
            context.scene.cycles.use_denoising = True
            context.scene.cycles.use_adaptive_sampling = True
            context.scene.cycles.adaptive_threshold = 0.01
            context.scene.cycles.use_high_quality_normals = True
        
        return original_engine

    @staticmethod
    def setup_bake_materials(merged_obj, source_obj, context):
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Setting up bake materials...")
        
        # Find the dominant material from source object
        if not source_obj.data.materials:
            logger.log_error("Source object has no materials")
            return None
            
        # Count face area per material to find dominant material
        material_areas = {}
        source_mesh = source_obj.data
        for poly in source_mesh.polygons:
            mat_index = poly.material_index
            if mat_index < len(source_mesh.materials):
                mat = source_mesh.materials[mat_index]
                if mat:
                    area = poly.area
                    material_areas[mat] = material_areas.get(mat, 0) + area
        
        # Get material with largest area
        dominant_material = max(material_areas.items(), key=lambda x: x[1])[0] if material_areas else source_mesh.materials[0]
        logger.log_info(f"Using dominant material: {dominant_material.name}")

        # Clear any existing materials from merged object
        merged_obj.data.materials.clear()
        
        # Create a copy of the dominant material to avoid modifying original
        bake_material = dominant_material.copy()
        bake_material.name = f"{dominant_material.name}_bake"
        
        # Assign the bake material to the merged object
        merged_obj.data.materials.append(bake_material)
        
        # Ensure all faces use this material
        for poly in merged_obj.data.polygons:
            poly.material_index = 0
            
        # Update mesh to ensure material assignment is reflected
        merged_obj.data.update()
        
        logger.log_info(f"Assigned bake material to merged mesh: {bake_material.name}")
        return bake_material

    @staticmethod
    def restore_materials(obj, materials):
        obj.data.materials.clear()
        for mat in materials:
            obj.data.materials.append(mat)


# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_TransitionTextureWeld_Bake(bpy.types.Operator):
    """Weld UVs between selected meshes, then stitch only the target side, and finally bake."""
    bl_idname = "zenv.transition_weld"
    bl_label = "Weld UVs / Stitch Target and Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        sel = context.selected_objects
        return (
            len(sel) == 2 and
            all(obj.type == 'MESH' for obj in sel) and
            context.active_object in sel
        )
    
    def execute(self, context):
        logger = ZENV_TransitionTextureWeld_Logger
        
        try:
            # Identify source vs target from selection
            target_obj = context.active_object
            source_obj = [obj for obj in context.selected_objects if obj != target_obj][0]
            
            logger.log_info("===== TRANSITION_WELD OPERATOR START =====")
            logger.log_info(f"Source object (UV reference): {source_obj.name}")
            logger.log_info(f"Target object (UV to transform): {target_obj.name}")
            
            # 1) Setup render for baking
            original_engine = ZENV_TransitionTextureWeld_Utils.setup_render_settings(context)
            
            # 2) Find shared edges
            shared_edges = ZENV_TransitionTextureWeld_Utils.get_shared_edges(source_obj, target_obj)
            if not shared_edges:
                self.report({'ERROR'}, "No shared edges found between source and target.")
                return {'CANCELLED'}
            
            # 3) Merge and weld
            merged_obj = ZENV_TransitionTextureWeld_Utils.create_merged_mesh(source_obj, target_obj, shared_edges)
            if not merged_obj:
                self.report({'ERROR'}, "Failed to create merged mesh.")
                return {'CANCELLED'}
            
            # 4) Setup materials for baking
            bake_material = ZENV_TransitionTextureWeld_Utils.setup_bake_materials(merged_obj, source_obj, context)
            if not bake_material:
                self.report({'ERROR'}, "Failed to setup bake materials.")
                return {'CANCELLED'}
            
            try:
                # Create bake image
                image_name = f"{target_obj.name}_baked"
                bake_image = bpy.data.images.new(
                    image_name,
                    width=context.scene.zenv_weld_resolution,
                    height=context.scene.zenv_weld_resolution,
                    alpha=True,
                    float_buffer=True,
                    is_data=False  # Ensure proper color space
                )
                
                # Set color space for better accuracy
                bake_image.colorspace_settings.name = 'sRGB'
                
                # Set filepath for the image
                blend_filepath = bpy.data.filepath
                if blend_filepath:
                    # If blend file is saved, save next to it
                    base_dir = os.path.dirname(blend_filepath)
                else:
                    # If blend file is not saved, use temp directory
                    base_dir = tempfile.gettempdir()
                
                # Create 00_bake_texture subfolder if it doesn't exist
                bake_folder = os.path.join(base_dir, "00_bake_texture")
                os.makedirs(bake_folder, exist_ok=True)
                
                # Set the image filepath in the bake folder
                image_filepath = os.path.join(bake_folder, image_name + ".png")
                bake_image.filepath_raw = image_filepath
                logger.log_info(f"Bake image will be saved to: {image_filepath}")
                
                # Create a temporary material for the target object
                target_bake_mat = bpy.data.materials.new(name=f"{target_obj.name}_bake_target")
                target_bake_mat.use_nodes = True
                target_nodes = target_bake_mat.node_tree.nodes
                target_nodes.clear()
                
                # Add image texture node for baking target
                target_tex_image = target_nodes.new('ShaderNodeTexImage')
                target_tex_image.image = bake_image
                target_tex_image.select = True
                target_nodes.active = target_tex_image
                
                # Assign bake target material to target object
                target_obj.data.materials.clear()
                target_obj.data.materials.append(target_bake_mat)
                
                # 5) Perform UV weld
                ZENV_TransitionTextureWeld_Utils.weld_uvs(merged_obj, shared_edges)
                
                # 6) Setup objects for baking
                # Deselect all objects first
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select merged object (source of bake)
                merged_obj.select_set(True)
                
                # Make target object active (destination of bake)
                context.view_layer.objects.active = target_obj
                target_obj.select_set(True)
                
                # Configure bake settings
                if hasattr(context.scene, 'cycles'):
                    context.scene.cycles.bake_type = 'DIFFUSE'
                    context.scene.render.bake.use_pass_direct = False
                    context.scene.render.bake.use_pass_indirect = False
                    context.scene.render.bake.use_pass_color = True
                    context.scene.render.bake.margin = 16
                    context.scene.render.bake.use_selected_to_active = True
                    context.scene.render.bake.use_clear = True
                    context.scene.render.bake.target = 'IMAGE_TEXTURES'
                
                # 7) Bake
                logger.log_info("Starting bake...")
                bpy.ops.object.bake(
                    type='DIFFUSE',
                    pass_filter={'COLOR'},
                    use_selected_to_active=True,  # Bake from merged (selected) to target (active)
                    margin=16,
                    use_clear=True
                )
                
                # 8) Save the baked image
                bake_image.file_format = 'PNG'
                bake_image.alpha_mode = 'STRAIGHT'
                bake_image.save()
                logger.log_info(f"Baked image saved to: {image_filepath}")
                
                # 9) Cleanup
                if context.scene.zenv_weld_cleanup:
                    bpy.data.objects.remove(merged_obj, do_unlink=True)
                    bpy.data.materials.remove(bake_material, do_unlink=True)
                    bpy.data.materials.remove(target_bake_mat, do_unlink=True)
                
                # 10) Restore render engine
                context.scene.render.engine = original_engine
                
                logger.log_info("===== TRANSITION_WELD OPERATOR END =====")
                self.report({'INFO'}, f"Baked image saved to: {image_filepath}")
                return {'FINISHED'}
                
            except Exception as e:
                if bake_material:
                    bpy.data.materials.remove(bake_material, do_unlink=True)
                if target_bake_mat:
                    bpy.data.materials.remove(target_bake_mat, do_unlink=True)
                if merged_obj:
                    bpy.data.objects.remove(merged_obj, do_unlink=True)
                raise e
            
        except Exception as e:
            logger.log_error(f"Error during transition weld: {str(e)}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_TransitionTextureWeld_Panel(bpy.types.Panel):
    """Panel for UV welding tools"""
    bl_label = "Texture Transition UV Stitch"
    bl_idname = "ZENV_PT_transition_weld"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Options:")
        box.prop(scene, "zenv_weld_debug")
        box.prop(scene, "zenv_weld_steps")
        box.prop(scene, "zenv_weld_cleanup")
        
        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(scene, "zenv_weld_resolution")
        
        layout.operator("zenv.transition_weld")


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_TransitionTextureWeld_Bake,
    ZENV_PT_TransitionTextureWeld_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_TransitionTextureWeld_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_TransitionTextureWeld_Properties.unregister()

if __name__ == "__main__":
    register()
