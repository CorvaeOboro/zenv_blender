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
            name="Cleanup After Baking",
            description="Remove temporary objects and materials after baking",
            default=True
        )

        # Baking properties
        bpy.types.Scene.zenv_weld_resolution = bpy.props.IntProperty(
            name="Bake Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        
        bpy.types.Scene.zenv_weld_flip_x = bpy.props.BoolProperty(
            name="Flip X",
            description="Mirror the texture horizontally before baking",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_flip_y = bpy.props.BoolProperty(
            name="Flip Y",
            description="Mirror the texture vertically before baking",
            default=False
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_weld_debug
        del bpy.types.Scene.zenv_weld_steps
        del bpy.types.Scene.zenv_weld_cleanup
        del bpy.types.Scene.zenv_weld_resolution
        del bpy.types.Scene.zenv_weld_flip_x
        del bpy.types.Scene.zenv_weld_flip_y

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

        # Distance threshold for welding (adjust if needed)
        WELD_DISTANCE_THRESHOLD = 0.001

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

            # Only weld if vertices are close enough
            if (new_s0.co - new_t0.co).length <= WELD_DISTANCE_THRESHOLD:
                weld_map[new_t0] = new_s0
            if (new_s1.co - new_t1.co).length <= WELD_DISTANCE_THRESHOLD:
                weld_map[new_t1] = new_s1
        
        logger.log_info(f"Will weld {len(weld_map)} target verts into source verts", "WELD")

        # Only perform weld if we have vertices to weld
        if weld_map:
            bmesh.ops.weld_verts(bm, targetmap=weld_map)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=WELD_DISTANCE_THRESHOLD)
        bm.normal_update()

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

        # (E) Build face‐index sets so 'stitch_uvs' can identify boundary edges
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
    def stitch_uvs(obj, shared_edges):
        """
        Additional pass to 'stitch' only the target-side UV edges along the seam,
        while keeping UV Sync selection ON and using face selection mode.

        This version avoids bpy.ops.uv.select_all (which can fail in a context override)
        by manually deselecting/selecting loops in BMesh.
        """
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("===== stitch_uvs: START (stitch target side) =====")

        # --- Store original states for proper restoration ---
        original_mode = obj.mode
        original_active = bpy.context.view_layer.objects.active
        original_area_type = None
        original_select_mode = bpy.context.tool_settings.mesh_select_mode[:]
        original_uv_select_sync = bpy.context.scene.tool_settings.use_uv_select_sync
        original_uv_select_mode = bpy.context.tool_settings.uv_select_mode

        try:
            # Make 'obj' active, ensure EDIT mode
            bpy.context.view_layer.objects.active = obj
            if bpy.context.object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')

            # Find or create an Image Editor area
            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'IMAGE_EDITOR':
                    area = a
                    break
            if not area:
                # If no Image Editor exists, temporarily convert current area
                area = bpy.context.area
                original_area_type = area.type
                area.type = 'IMAGE_EDITOR'

            # Find a WINDOW region in that area
            region = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region = r
                    break

            if not region:
                logger.log_error("Could not find a WINDOW region in IMAGE_EDITOR; aborting stitch.")
                return obj

            # Prepare a context override so uv.stitch sees an IMAGE_EDITOR context
            space_data = area.spaces.active
            screen = area.id_data
            window = bpy.context.window_manager.windows[0]

            with bpy.context.temp_override(
                window=window,
                area=area,
                region=region,
                space_data=space_data,
                screen=screen
            ):
                # Log basic context info
                logger.log_info(f"Context area type: {area.type}", "CONTEXT")
                logger.log_info(f"Context mode: {obj.mode}", "CONTEXT")
                logger.log_info(f"Context active object: {bpy.context.active_object.name}", "CONTEXT")

                # Keep sync selection ON
                bpy.context.scene.tool_settings.use_uv_select_sync = True

                # Use face selection in 3D + face selection in UV
                bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                bpy.context.tool_settings.uv_select_mode = 'FACE'

                logger.log_info(f"mesh_select_mode: {bpy.context.tool_settings.mesh_select_mode}", "DEBUG")
                logger.log_info(f"uv_select_mode: {bpy.context.tool_settings.uv_select_mode}", "DEBUG")
                logger.log_info(f"use_uv_select_sync: {bpy.context.scene.tool_settings.use_uv_select_sync}", "DEBUG")

                # 1) Select "source_verts" group in 3D
                if "source_verts" in obj.vertex_groups:
                    bpy.ops.object.vertex_group_set_active(group='source_verts')
                    bpy.ops.object.vertex_group_select()

                    bm = bmesh.from_edit_mesh(obj.data)
                    bm.verts.ensure_lookup_table()
                    bm.faces.ensure_lookup_table()

                    selected_verts_3d = [v for v in bm.verts if v.select]
                    selected_faces_3d = [f for f in bm.faces if f.select]
                    logger.log_info(f"3D Selection: {len(selected_verts_3d)} verts, {len(selected_faces_3d)} faces", "DEBUG")

                    # 2) Manually clear UV selection, then set loops selected
                    uv_layer = bm.loops.layers.uv.active
                    if uv_layer:
                        # Deselect all loops in UV
                        for f in bm.faces:
                            for loop in f.loops:
                                loop[uv_layer].select = False

                        # Now select all loops for each face that is selected in 3D
                        for f in selected_faces_3d:
                            for loop in f.loops:
                                loop[uv_layer].select = True

                        bmesh.update_edit_mesh(obj.data)

                        # Check how many faces are now "UV selected"
                        uv_selected_faces = 0
                        for f in bm.faces:
                            if all(l[uv_layer].select for l in f.loops):
                                uv_selected_faces += 1
                        logger.log_info(f"UV Editor Selection: {uv_selected_faces} faces selected", "DEBUG")
                    else:
                        logger.log_info("No active UV layer found on the mesh!", "DEBUG")

                else:
                    logger.log_error("source_verts vertex group not found; skipping stitch.")
                    return obj

                # 3) Attempt the uv.stitch operator
                try:
                    logger.log_info("Calling bpy.ops.uv.stitch() ...", "DEBUG")
                    bpy.ops.uv.stitch(use_limit=False, snap_islands=True, limit=0.01)
                    logger.log_info("UV stitch completed successfully", "STITCH")
                except Exception as e:
                    logger.log_error(f"UV stitch failed with error: {str(e)}")
                    logger.log_info(f"Failed stitch context - Area: {area.type}", "ERROR")
                    logger.log_info(f"Failed stitch context - Mode: {obj.mode}", "ERROR")
                    logger.log_info(f"Failed stitch context - Active: {bpy.context.active_object.name}", "ERROR")
                    logger.log_info(f"Failed stitch context - Region: {region.type}", "ERROR")

                # 4) Optional: Flip target UVs if requested
                if bpy.context.scene.zenv_weld_flip_x or bpy.context.scene.zenv_weld_flip_y:
                    bm = bmesh.from_edit_mesh(obj.data)
                    bm.faces.ensure_lookup_table()
                    bm.verts.ensure_lookup_table()
                    uv_layer = bm.loops.layers.uv.verify()

                    # Gather target_verts from group
                    target_group = obj.vertex_groups.get("target_verts")
                    target_verts = set()
                    if target_group:
                        for v in bm.verts:
                            for g in v.groups:
                                if g.group == target_group.index:
                                    target_verts.add(v.index)

                    # Gather seam verts from shared_edges
                    seam_verts = set()
                    for edge_info in shared_edges:
                        seam_verts.update(edge_info[2]['target_verts'])

                    # Calculate seam center
                    seam_uv_coords = []
                    for f in bm.faces:
                        for loop in f.loops:
                            if loop.vert.index in seam_verts:
                                seam_uv_coords.append(Vector(loop[uv_layer].uv))
                    if seam_uv_coords:
                        seam_uv_center = sum(seam_uv_coords, Vector((0.0, 0.0))) / len(seam_uv_coords)

                        # Flip only target UVs not on the seam
                        for f in bm.faces:
                            for loop in f.loops:
                                if loop.vert.index in target_verts and loop.vert.index not in seam_verts:
                                    old_uv = Vector(loop[uv_layer].uv)
                                    rel_uv = old_uv - seam_uv_center
                                    if bpy.context.scene.zenv_weld_flip_x:
                                        rel_uv.x = -rel_uv.x
                                    if bpy.context.scene.zenv_weld_flip_y:
                                        rel_uv.y = -rel_uv.y
                                    loop[uv_layer].uv = seam_uv_center + rel_uv

                    bmesh.update_edit_mesh(obj.data)

        except Exception as e:
            logger.log_error(f"Error during UV operations: {str(e)}")

        finally:
            # Restore any area changes
            if original_area_type:
                area.type = original_area_type

            # Restore original tool settings
            bpy.context.tool_settings.mesh_select_mode = original_select_mode
            bpy.context.scene.tool_settings.use_uv_select_sync = original_uv_select_sync
            bpy.context.tool_settings.uv_select_mode = original_uv_select_mode

            # Return to Object Mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Restore original active object (and mode if needed)
            if original_active:
                bpy.context.view_layer.objects.active = original_active
                if original_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=original_mode)

        logger.log_info("===== stitch_uvs: END (stitch target side) =====")
        return obj


    @staticmethod
    def setup_material_nodes(material, image_texture):
        """Setup material nodes with optional texture flipping"""
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # Create texture coordinate node
        tex_coord = nodes.new('ShaderNodeTexCoord')
        tex_coord.location = (-600, 0)
        
        # Create mapping node for flipping
        mapping = nodes.new('ShaderNodeMapping')
        mapping.location = (-400, 0)
        
        # Create texture node
        texture = nodes.new('ShaderNodeTexImage')
        texture.image = image_texture
        texture.location = (-200, 0)
        
        # Create output node
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (200, 0)
        
        # Create shader node
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        
        # Link nodes
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
        links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        return mapping, texture

    @staticmethod
    def create_bake_material(context, image, obj):
        """Create material for baking with optional texture flipping"""
        # Create new material
        material = bpy.data.materials.new(name=f"{obj.name}_bake_material")
        material.use_nodes = True
        
        # Setup nodes
        mapping, texture = ZENV_TransitionTextureWeld_Utils.setup_material_nodes(material, image)
        
        # Apply flipping if enabled
        if context.scene.zenv_weld_flip_x or context.scene.zenv_weld_flip_y:
            mapping.inputs['Scale'].default_value[0] = -1 if context.scene.zenv_weld_flip_x else 1
            mapping.inputs['Scale'].default_value[1] = -1 if context.scene.zenv_weld_flip_y else 1
        
        return material, texture

    @staticmethod
    def setup_bake_materials(merged_obj, source_obj, context):
        """Setup materials for baking with texture flipping support"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Setting up bake materials...")
        
        # Create new material for merged object
        bake_material = bpy.data.materials.new(name=f"{merged_obj.name}_bake")
        bake_material.use_nodes = True
        nodes = bake_material.node_tree.nodes
        links = bake_material.node_tree.links
        nodes.clear()

        # Create nodes with texture flipping support
        tex_coord = nodes.new('ShaderNodeTexCoord')
        tex_coord.location = (-600, 0)

        mapping = nodes.new('ShaderNodeMapping')
        mapping.location = (-400, 0)

        # Apply flipping if enabled
        if context.scene.zenv_weld_flip_x or context.scene.zenv_weld_flip_y:
            mapping.inputs['Scale'].default_value[0] = -1 if context.scene.zenv_weld_flip_x else 1
            mapping.inputs['Scale'].default_value[1] = -1 if context.scene.zenv_weld_flip_y else 1

        # Create Principled BSDF
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)

        # Create output
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (200, 0)

        # Link nodes
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

        # Get source material and its image texture if available
        if source_obj.data.materials:
            source_mat = source_obj.data.materials[0]
            if source_mat and source_mat.use_nodes:
                for node in source_mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        # Create texture node
                        texture = nodes.new('ShaderNodeTexImage')
                        texture.image = node.image
                        texture.location = (-200, 0)
                        
                        # Link texture
                        links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
                        links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])
                        break

        # Link BSDF to output
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # Assign material to merged object
        merged_obj.data.materials.clear()
        merged_obj.data.materials.append(bake_material)

        # Push vertices slightly along their normals to prevent z-fighting
        bm = bmesh.new()
        bm.from_mesh(merged_obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # Ensure normals are correct
        
        # Push each vertex along its normal
        for v in bm.verts:
            v.co += v.normal * 0.0001
        
        bm.to_mesh(merged_obj.data)
        bm.free()
        merged_obj.data.update()

        return bake_material

    @staticmethod
    def restore_materials(obj, materials):
        obj.data.materials.clear()
        for mat in materials:
            obj.data.materials.append(mat)

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
                target_bake_mat, target_tex_image = ZENV_TransitionTextureWeld_Utils.create_bake_material(context, bake_image, target_obj)
                
                # Assign bake target material to target object
                target_obj.data.materials.clear()
                target_obj.data.materials.append(target_bake_mat)
                
                # 5) Perform UV weld
                ZENV_TransitionTextureWeld_Utils.stitch_uvs(merged_obj, shared_edges)
                
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
    """Panel for UV stitching tools"""
    bl_label = "TEX Transition by UV Weld"
    bl_idname = "ZENV_PT_transition_texture_weld"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Options:")
        box.prop(scene, "zenv_weld_cleanup")
        
        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(scene, "zenv_weld_resolution")
        
        box = layout.box()
        box.label(text="Texture Variations:")
        col = box.column(align=True)
        col.prop(scene, "zenv_weld_flip_x", text="Flip X")
        col.prop(scene, "zenv_weld_flip_y", text="Flip Y")
        
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
