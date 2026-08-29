"""
TEX Transition Bake by UV Stitch - Create texture transitions between two meshes.

Two meshes that are touching are merged and their UVs welded, creating a
texture transition by UV stitching where the target UV island is snapped to match.
Then texture bake the merged onto the target mesh.
Bakes saved to "00_bake_texture" subfolder by target object name.
"""

#region blinfo
bl_info = {
    "name": 'TEX Transition Bake by UV Stitch',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Create a transition between two meshes by UV stitching',
    "status": 'wip',
    "approved": False,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 70,
    "addon_order": 70,
    "location": 'View3D > ZENV',
    "tags": ['texture', 'transition', 'uv', 'weld', 'bake', 'stitch'],
    "description_short": 'Create texture transitions by UV stitching between two meshes.',
    "description_medium": 'Merges two touching meshes, welds their UVs, stitches the target '
                          'UV island to match the source, and bakes the merged result onto '
                          'the target mesh. Supports flip X/Y and cleanup options.',
    "description_long": 'UV stitching workflow for texture transitions. Finds shared '
                        'edges between source and target meshes in world space, merges them '
                        'into a single BMesh, welds the seam vertices, copies UVs, stitches '
                        'the target-side UV edges, and bakes the result via Cycles. Output '
                        'saved to 00_bake_texture subfolder.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}
#endregion

#region imports
import bpy
import bmesh
import mathutils
from mathutils import Vector
import math
import os
import tempfile
import re
import logging
import numpy as np
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, IntProperty
#endregion

#region logger
logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region props
class ZENV_TEXTransitionBakeByUVWeld_Properties:
    """Property management for UV welding addon"""
    
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_weld_debug = BoolProperty(
            name="Debug Mode",
            description="Enable debug logging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_steps = BoolProperty(
            name="Step Mode",
            description="Execute steps separately for debugging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_cleanup = BoolProperty(
            name="Cleanup After Baking",
            description="Remove temporary objects and materials after baking",
            default=True
        )

        # Baking properties
        bpy.types.Scene.zenv_weld_resolution = IntProperty(
            name="Bake Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        
        bpy.types.Scene.zenv_weld_flip_x = BoolProperty(
            name="Flip X",
            description="Mirror the texture horizontally before baking",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_flip_y = BoolProperty(
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
#endregion

#region utils
class ZENV_TEXTransitionBakeByUVWeld_Utils:
    """Utility functions for UV welding, ordered by workflow stage:
    validate -> edge detect -> merge -> stitch -> material setup -> render -> cleanup -> helpers
    """

    #region validate
    # Pre-flight checks: UV range and material validation before any work begins.
    
    @staticmethod
    def validate_uv_space(obj):
        """Check if UVs are within 0-1 space"""
        if not obj.data.uv_layers.active:
            logger.error(f"No UV layer found on {obj.name}")
            return False
        
        uv_layer = obj.data.uv_layers.active
        outside_uvs = []
        for poly in obj.data.polygons:
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                if uv.x < -0.1 or uv.x > 1.1 or uv.y < -0.1 or uv.y > 1.1:
                    outside_uvs.append((poly.index, loop_idx, (uv.x, uv.y)))
        
        if outside_uvs:
            logger.error(f"Found {len(outside_uvs)} UV coordinates outside 0-1 space in {obj.name}")
            for poly_idx, loop_idx, uv_coords in outside_uvs[:5]:  # Show first 5 examples
                logger.error(f"  Polygon {poly_idx}, UV: {uv_coords}")
            logger.warning(f"{obj.name} has UVs outside 0-1 space. Baking may be unpredictable.")
            return False
        return True

    @staticmethod
    def validate_materials(obj):
        """Check if materials have valid diffuse textures"""
        if not obj.material_slots:
            logger.error(f"No materials found on {obj.name}")
            return False
            
        valid_textures = False
        for slot in obj.material_slots:
            if not slot.material:
                logger.error(f"Empty material slot found on {obj.name}")
                continue
                
            mat = slot.material
            if not mat.use_nodes:
                logger.error(f"Material {mat.name} not using nodes")
                continue
                
            # Check for image texture nodes connected to diffuse
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    # Trace back from color input
                    for link in mat.node_tree.links:
                        if link.to_socket == node.inputs['Base Color']:
                            if link.from_node.type == 'TEX_IMAGE':
                                if link.from_node.image:
                                    valid_textures = True
                                    logger.info(f"Found valid texture in {mat.name}: {link.from_node.image.name}")
                                else:
                                    logger.error(f"Empty image texture node in {mat.name}")
            
        return valid_textures
    #endregion

    #region edgedetect
    # Find edges that are touching between source and target meshes in world space.
    
    @staticmethod
    def get_shared_edges(source_obj, target_obj):
        """Find edges that are touching (close) between two meshes (in world-space), using segment-to-segment sampling for detection."""
        logger.info(f"Starting segment-sampling edge analysis between {source_obj.name} and {target_obj.name}")

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

        # Helper: sample N points along an edge
        def sample_edge(v0, v1, n=7):
            return [v0 + (v1 - v0) * (i / (n - 1)) for i in range(n)]

        # Helper: minimum distance between a point and a segment
        def point_to_segment_distance(pt, a, b):
            ab = b - a
            t = np.dot(pt - a, ab) / (np.dot(ab, ab) + 1e-12)
            t = np.clip(t, 0.0, 1.0)
            closest = a + ab * t
            return np.linalg.norm(pt - closest)

        # Collect all edges (world space)
        src_edges = []
        for e in bm1.edges:
            v0 = np.array(source_matrix @ e.verts[0].co)
            v1 = np.array(source_matrix @ e.verts[1].co)
            src_edges.append({'v_idx': [e.verts[0].index, e.verts[1].index], 'v0': v0, 'v1': v1})
        tgt_edges = []
        for e in bm2.edges:
            v0 = np.array(target_matrix @ e.verts[0].co)
            v1 = np.array(target_matrix @ e.verts[1].co)
            tgt_edges.append({'v_idx': [e.verts[0].index, e.verts[1].index], 'v0': v0, 'v1': v1})

        SAMPLE_COUNT = 7
        DIST_THRESH = 0.02  # Blender units

        # Build a KD-tree on target edge midpoints for spatial culling
        # so we only do expensive segment-segment checks on candidate
        # pairs, reducing O(NxM) to O(N log M).
        from mathutils.kdtree import KDTree
        tgt_midpoints = []
        for te in tgt_edges:
            mid = (te['v0'] + te['v1']) * 0.5
            tgt_midpoints.append(mid)
        kd_tgt = KDTree(len(tgt_midpoints))
        for i, mid in enumerate(tgt_midpoints):
            # KDTree expects a Vector; convert from numpy array
            kd_tgt.insert(Vector((float(mid[0]), float(mid[1]), float(mid[2]))), i)
        kd_tgt.balance()

        shared_edges = []
        for src in src_edges:
            src_samples = sample_edge(src['v0'], src['v1'], SAMPLE_COUNT)
            src_mid = (src['v0'] + src['v1']) * 0.5
            # Query the KDTree for target edges within DIST_THRESH of the
            # source edge midpoint. This dramatically reduces the number
            # of expensive segment-segment distance checks.
            candidates = kd_tgt.find_range(
                Vector((float(src_mid[0]), float(src_mid[1]), float(src_mid[2]))),
                DIST_THRESH * 2,  # generous radius to catch nearby edges
            )
            for _, tgt_idx, _ in candidates:
                tgt = tgt_edges[tgt_idx]
                # For each sample point on source edge, find min distance to target segment
                min_dist = min(point_to_segment_distance(pt, tgt['v0'], tgt['v1']) for pt in src_samples)
                if min_dist < DIST_THRESH:
                    shared_edges.append((
                        src['v_idx'],
                        tgt['v_idx'],
                        {
                            'min_dist': min_dist,
                            'sample_count': SAMPLE_COUNT
                        }
                    ))
        logger.info(f"Found {len(shared_edges)} shared edges (segment sampling)", "EDGE DETECTION COMPLETE")
        bm1.free()
        bm2.free()
        # Format for downstream compatibility
        formatted = []
        for (src_idx, tgt_idx, meta) in shared_edges:
            formatted.append((
                src_idx,
                tgt_idx,
                {
                    'edge_dir': None,  # Not used downstream
                    'edge_length': None,
                    'source_verts': src_idx,
                    'target_verts': tgt_idx,
                    'meta': meta
                }
            ))
        return formatted
    #endregion

    #region merge
    # Merge source + target into a single BMesh, weld the seam, copy UVs,
    # build vertex groups, and store face sets in custom properties.
    
    @staticmethod
    def create_merged_mesh(source_obj, target_obj, shared_edges):
        """
        Merge source + target into a single BMesh, weld the seam, 
        build final vertex groups, and store final face sets in custom props.
        """
        logger.info("===== CREATE_MERGED_MESH: START =====")

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

        try:
            logger.info(f"Source BMesh: {len(bm_source.verts)} verts, {len(bm_source.edges)} edges, {len(bm_source.faces)} faces")
            logger.info(f"Target BMesh: {len(bm_target.verts)} verts, {len(bm_target.edges)} edges, {len(bm_target.faces)} faces")

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
                    logger.info("Skipping duplicate face in target mesh")

            bm.faces.ensure_lookup_table()
            logger.info(f"Post-copy, merged BMesh has {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces")

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

            logger.info(f"Will weld {len(weld_map)} target verts into source verts", "WELD")

            # Use remove_doubles for welding. The deprecated bmesh.ops.weld_verts
            # was removed in Blender 4.x; remove_doubles with the same threshold
            # achieves the same result.
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=WELD_DISTANCE_THRESHOLD)
            bm.normal_update()

            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            logger.info(f"After weld, merged BMesh has {len(bm.verts)} verts, {len(bm.edges)} edges, {len(bm.faces)} faces")

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

            # (E) Build face-index sets so 'stitch_uvs' can identify boundary edges
            bm.faces.ensure_lookup_table()
            source_face_indices = set()
            target_face_indices = set()

            for sf, new_f in source_face_map.items():
                if new_f and new_f.is_valid:
                    source_face_indices.add(new_f.index)
            for tf, new_f in target_face_map.items():
                if new_f and new_f.is_valid:
                    target_face_indices.add(new_f.index)

            # (F) Convert BMesh -> mesh
            bm.to_mesh(merged_mesh)
            bm.free()
            bm = None  # mark as freed

            # Save face sets in custom props
            merged_obj["source_faces"] = list(source_face_indices)
            merged_obj["target_faces"] = list(target_face_indices)

            # (G) Build vertex groups
            logger.info("Building vertex groups after weld...")
            grp_source = merged_obj.vertex_groups.new(name="source_verts")
            grp_target = merged_obj.vertex_groups.new(name="target_verts")
            grp_seam   = merged_obj.vertex_groups.new(name="seam_verts")

            # Make an array of final world coords and build a spatial index
            # for O(1) lookup instead of O(N) linear scan.
            final_coords = [merged_obj.matrix_world @ v.co for v in merged_mesh.vertices]

            # Build a dict keyed by rounded coordinates for fast lookup.
            # The key precision (6 decimals) is finer than the weld threshold.
            _final_index_map = {}
            for i, c in enumerate(final_coords):
                key = (round(c.x, 6), round(c.y, 6), round(c.z, 6))
                _final_index_map[key] = i

            def find_final_index(world_co, tolerance=1e-6):
                # Fast dict lookup by rounded coordinates.
                key = (round(world_co.x, 6), round(world_co.y, 6), round(world_co.z, 6))
                idx = _final_index_map.get(key)
                if idx is not None:
                    return idx
                # Fallback: linear scan for edge cases where rounding differs
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

            logger.info(f"source_verts group size = {len(final_source_indices)}", "GROUPS")
            logger.info(f"target_verts group size = {len(final_target_indices)}", "GROUPS")
            logger.info(f"seam_verts group size   = {len(final_seam_indices)}", "GROUPS")

            logger.info("===== CREATE_MERGED_MESH: END =====")
            return merged_obj

        finally:
            # Free BMeshes on exception.
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
            if bm_source is not None:
                try:
                    bm_source.free()
                except Exception:
                    pass
            if bm_target is not None:
                try:
                    bm_target.free()
                except Exception:
                    pass
    #endregion

    #region stitch
    # Stitch only the target-side UV edges along the seam, keeping UV Sync
    # selection ON and using face selection mode. Optionally flip target UVs.
    
    @staticmethod
    def stitch_uvs(obj, shared_edges):
        """
        Additional pass to 'stitch' only the target-side UV edges along the seam,
        while keeping UV Sync selection ON and using face selection mode.

        This version avoids bpy.ops.uv.select_all (which can fail in a context override)
        by manually deselecting/selecting loops in BMesh.
        """
        logger.info("===== stitch_uvs: START (stitch target side) =====")

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
                logger.error("Could not find a WINDOW region in IMAGE_EDITOR; aborting stitch.")
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
                logger.info(f"Context area type: {area.type}")
                logger.info(f"Context mode: {obj.mode}")
                logger.info(f"Context active object: {bpy.context.active_object.name}")

                # Keep sync selection ON
                bpy.context.scene.tool_settings.use_uv_select_sync = True

                # Use face selection in 3D + face selection in UV
                bpy.context.tool_settings.mesh_select_mode = (False, False, True)
                bpy.context.tool_settings.uv_select_mode = 'FACE'

                logger.info(f"mesh_select_mode: {bpy.context.tool_settings.mesh_select_mode}")
                logger.info(f"uv_select_mode: {bpy.context.tool_settings.uv_select_mode}")
                logger.info(f"use_uv_select_sync: {bpy.context.scene.tool_settings.use_uv_select_sync}")

                # 1) Select "source_verts" group in 3D
                if "source_verts" in obj.vertex_groups:
                    bpy.ops.object.vertex_group_set_active(group='source_verts')
                    bpy.ops.object.vertex_group_select()

                    bm = bmesh.from_edit_mesh(obj.data)
                    bm.verts.ensure_lookup_table()
                    bm.faces.ensure_lookup_table()

                    selected_verts_3d = [v for v in bm.verts if v.select]
                    selected_faces_3d = [f for f in bm.faces if f.select]
                    logger.info(f"3D Selection: {len(selected_verts_3d)} verts, {len(selected_faces_3d)} faces", "DEBUG")

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
                        logger.info(f"UV Editor Selection: {uv_selected_faces} faces selected")
                    else:
                        logger.info("No active UV layer found on the mesh!")

                else:
                    logger.error("source_verts vertex group not found; skipping stitch.")
                    return obj

                # 3) Attempt the uv.stitch operator
                try:
                    logger.info("Calling bpy.ops.uv.stitch() ...", "DEBUG")
                    bpy.ops.uv.stitch(use_limit=False, snap_islands=True, limit=0.01)
                    logger.info("UV stitch completed successfully")
                except Exception as e:
                    logger.error(f"UV stitch failed with error: {str(e)}")
                    logger.info(f"Failed stitch context - Area: {area.type}")
                    logger.info(f"Failed stitch context - Mode: {obj.mode}")
                    logger.info(f"Failed stitch context - Active: {bpy.context.active_object.name}")
                    logger.info(f"Failed stitch context - Region: {region.type}")

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
            logger.error(f"Error during UV operations: {str(e)}")

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

        logger.info("===== stitch_uvs: END (stitch target side) =====")
        return obj
    #endregion

    #region matsetup
    # Create and configure material node trees for baking: simple display
    # material, target bake material, and multi-texture source bake material.
    
    @staticmethod
    def setup_material_nodes(material, image_texture):
        """Setup material nodes with optional texture flipping"""
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # Create nodes
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image_texture
        tex_image.extension = 'REPEAT'  # Allow texture to repeat
        
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')
        
        # Position nodes
        tex_image.location = (-300, 300)
        principled.location = (0, 300)
        output.location = (300, 300)
        
        # Connect nodes
        links.new(tex_image.outputs['Color'], principled.inputs['Base Color'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        logger.info(f"Setup material nodes for {material.name}")
        return tex_image

    @staticmethod
    def create_bake_material(context, image, obj):
        """Create material for baking with optional texture flipping"""
        material = bpy.data.materials.new(name=f"{obj.name}_bake")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # Create nodes
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        tex_image.extension = 'REPEAT'
        
        # For baking target, both Principled BSDF and Image Texture are needed
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')
        
        # Position nodes
        tex_image.location = (-300, 300)
        principled.location = (0, 300)
        output.location = (300, 300)
        
        # Connect nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        # Set image node as active for baking
        tex_image.select = True
        nodes.active = tex_image
        
        logger.info(f"Created bake material for {obj.name}")
        return material, tex_image

    @staticmethod
    def setup_bake_materials(merged_obj, source_obj, context):
        """Setup materials for baking with texture flipping support.

        Uses Emission shaders instead of Principled BSDF so the EMIT bake
        captures the exact texture color.  Principled BSDF in Blender 4.x
        conserves energy between diffuse and specular, which causes a
        DIFFUSE/COLOR bake to come out darker and desaturated.
        """
        
        # Create new bake material
        bake_material = bpy.data.materials.new(name=f"{merged_obj.name}_bake_source")
        bake_material.use_nodes = True
        nodes = bake_material.node_tree.nodes
        links = bake_material.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # Create main material output
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (300, 300)
        
        # Create mix shader to combine all textures
        mix = nodes.new('ShaderNodeMixShader')
        mix.location = (100, 300)
        links.new(mix.outputs[0], output.inputs['Surface'])
        
        # Track last mix node
        last_mix = None
        texture_count = 0
        
        # Process each material from source object
        for mat in source_obj.data.materials:
            if not mat or not mat.use_nodes:
                continue
                
            # Find image texture nodes connected to diffuse
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    for link in mat.node_tree.links:
                        if link.to_socket == node.inputs['Base Color'] and link.from_node.type == 'TEX_IMAGE':
                            if link.from_node.image:
                                # Create nodes for this texture
                                tex_image = nodes.new('ShaderNodeTexImage')
                                tex_image.image = link.from_node.image
                                tex_image.extension = 'REPEAT'
                                tex_image.location = (-600, 300 - texture_count * 300)
                                
                                # Use Emission shader so the EMIT bake captures
                                # the exact texture color without BSDF energy loss.
                                emission = nodes.new('ShaderNodeEmission')
                                emission.location = (-300, 300 - texture_count * 300)
                                
                                # Link texture to Emission color
                                links.new(tex_image.outputs['Color'], emission.inputs['Color'])
                                
                                if texture_count == 0:
                                    # First texture
                                    links.new(emission.outputs['Emission'], mix.inputs[1])
                                else:
                                    # Additional textures
                                    new_mix = nodes.new('ShaderNodeMixShader')
                                    new_mix.location = (100, 300 - texture_count * 150)
                                    new_mix.inputs[0].default_value = 0.5  # Equal mix
                                    
                                    if last_mix:
                                        links.new(last_mix.outputs[0], new_mix.inputs[1])
                                    links.new(emission.outputs['Emission'], new_mix.inputs[2])
                                    last_mix = new_mix
                                
                                texture_count += 1
                                logger.info(f"Added texture {tex_image.image.name} to bake material")
        
        # If more than one texture exists, connect the last mix
        if last_mix:
            links.new(last_mix.outputs[0], mix.inputs[2])
        
        # Clear materials from merged object
        merged_obj.data.materials.clear()
        
        # Assign new bake material
        merged_obj.data.materials.append(bake_material)
        
        logger.info(f"Setup {texture_count} textures for baking")
        return bake_material
    #endregion

    #region render
    # Configure Cycles render settings for texture baking.
    
    @staticmethod
    def setup_render_settings(context):
        """Setup render settings for baking"""
        logger.info("Setting up render settings...")
        
        # Store original render engine
        original_engine = context.scene.render.engine
        
        # Set to Cycles for baking
        context.scene.render.engine = 'CYCLES'
        
        # Configure Cycles settings
        if hasattr(context.scene, 'cycles'):
            context.scene.cycles.samples = 512  # Increase samples
            context.scene.cycles.use_denoising = True
            context.scene.cycles.use_adaptive_sampling = True
            context.scene.cycles.adaptive_threshold = 0.01
        
        return original_engine
    #endregion

    #region cleanup
    # Restore materials and remove temporary objects created during the workflow.
    
    @staticmethod
    def restore_materials(obj, materials):
        obj.data.materials.clear()
        for mat in materials:
            obj.data.materials.append(mat)

    @staticmethod
    def cleanup_temp_objects(obj):
        temp_source_name = obj.get("temp_source", None)
        temp_target_name = obj.get("temp_target", None)
        
        if temp_source_name:
            temp_source = bpy.data.objects.get(temp_source_name)
            if temp_source:
                logger.info(f"Removing temp object: {temp_source.name}")
                bpy.data.objects.remove(temp_source, do_unlink=True)
        
        if temp_target_name:
            temp_target = bpy.data.objects.get(temp_target_name)
            if temp_target:
                logger.info(f"Removing temp object: {temp_target.name}")
                bpy.data.objects.remove(temp_target, do_unlink=True)
    #endregion

    #region helpers
    # Small utility helpers used across multiple workflow stages.
    
    @staticmethod
    def safe_filename(name):
        # Remove unsafe characters for filenames
        name = re.sub(r'[^\w\-_. ]', '_', name)
        name = name.strip('_')
        # Ensure the result is non-empty
        return name if name else "unnamed"
    #endregion

#endregion

#region operator
class ZENV_OT_TEXTransitionBakeByUVWeld_Bake(Operator):
    """Weld UVs between selected meshes, then stitch only the target side, and finally bake."""
    bl_idname = "zenv.transition_weld"
    bl_label = "Weld UVs / Stitch Target and Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    #region poll
    @classmethod
    def poll(cls, context):
        sel = context.selected_objects
        return (
            len(sel) == 2 and
            all(obj.type == 'MESH' for obj in sel) and
            context.active_object in sel
        )
    #endregion
    
    #region execute
    def execute(self, context):
        
        #region init
        # Pre-declare resources so the exception handler and finally block
        # can safely check them.
        bake_material = None
        target_bake_mat = None
        merged_obj = None
        original_engine = None
        original_target_materials = []
        #endregion

        try:
            #region precheck
            # Identify source vs target from selection
            target_obj = context.active_object
            source_obj = [obj for obj in context.selected_objects if obj != target_obj][0]

            logger.info("===== TRANSITION_WELD OPERATOR START =====")
            logger.info(f"Source object (UV reference): {source_obj.name}")
            logger.info(f"Target object (UV to transform): {target_obj.name}")

            # Validate UVs
            if not ZENV_TEXTransitionBakeByUVWeld_Utils.validate_uv_space(source_obj):
                self.report({'ERROR'}, f"Source object {source_obj.name} has UVs outside 0-1 space")
                return {'CANCELLED'}
            if not ZENV_TEXTransitionBakeByUVWeld_Utils.validate_uv_space(target_obj):
                self.report({'ERROR'}, f"Target object {target_obj.name} has UVs outside 0-1 space")
                return {'CANCELLED'}

            # Validate materials
            if not ZENV_TEXTransitionBakeByUVWeld_Utils.validate_materials(source_obj):
                self.report({'ERROR'}, f"Source object {source_obj.name} has no valid diffuse textures")
                return {'CANCELLED'}
            #endregion

            #region setup
            # 1) Setup render for baking
            original_engine = ZENV_TEXTransitionBakeByUVWeld_Utils.setup_render_settings(context)

            # 2) Find shared edges
            shared_edges = ZENV_TEXTransitionBakeByUVWeld_Utils.get_shared_edges(source_obj, target_obj)
            if not shared_edges:
                self.report({'ERROR'}, "No shared edges found between source and target.")
                return {'CANCELLED'}
            logger.info(f"Found {len(shared_edges)} shared edges")
            #endregion

            #region merge
            # 3) Merge and weld
            merged_obj = ZENV_TEXTransitionBakeByUVWeld_Utils.create_merged_mesh(source_obj, target_obj, shared_edges)
            if not merged_obj:
                self.report({'ERROR'}, "Failed to create merged mesh.")
                return {'CANCELLED'}

            # Validate merged mesh UVs
            if not ZENV_TEXTransitionBakeByUVWeld_Utils.validate_uv_space(merged_obj):
                self.report({'ERROR'}, "Merged mesh has UVs outside 0-1 space")
                return {'CANCELLED'}
            #endregion

            #region matsetup
            # 4) Setup materials for baking
            bake_material = ZENV_TEXTransitionBakeByUVWeld_Utils.setup_bake_materials(merged_obj, source_obj, context)
            if not bake_material:
                self.report({'ERROR'}, "Failed to setup bake materials.")
                return {'CANCELLED'}
            #endregion

            #region bakeimg
            # Create bake image
            image_name = f"{ZENV_TEXTransitionBakeByUVWeld_Utils.safe_filename(target_obj.name)}_baked_from_{ZENV_TEXTransitionBakeByUVWeld_Utils.safe_filename(source_obj.name)}"
            bake_image = bpy.data.images.new(
                image_name,
                width=context.scene.zenv_weld_resolution,
                height=context.scene.zenv_weld_resolution,
                alpha=True,
                float_buffer=False,  # PNG does not support float; use 8-bit
                is_data=False
            )

            # Bake target images should be sRGB so that Cycles' linear bake
            # output is gamma-encoded to sRGB on save, matching the original
            # source albedo textures. (Non-Color would save raw linear values,
            # producing a dark image.)
            bake_image.colorspace_settings.name = 'sRGB'

            # Set filepath for the image
            blend_filepath = bpy.data.filepath
            if blend_filepath:
                base_dir = os.path.dirname(blend_filepath)
            else:
                base_dir = tempfile.gettempdir()

            # Create 00_bake_texture subfolder if it doesn't exist
            bake_folder = os.path.join(base_dir, "00_bake_texture")
            os.makedirs(bake_folder, exist_ok=True)

            # Set the image filepath in the bake folder
            image_filepath = os.path.join(bake_folder, image_name + ".png")
            bake_image.filepath_raw = image_filepath
            logger.info(f"Bake image will be saved to: {image_filepath}")

            # Create a temporary material for the target object
            target_bake_mat = bpy.data.materials.new(name=f"{target_obj.name}_bake_target")
            target_bake_mat, target_tex_image = ZENV_TEXTransitionBakeByUVWeld_Utils.create_bake_material(context, bake_image, target_obj)

            # Capture and replace target object materials.
            # Original materials are restored in the finally block.
            original_target_materials = list(target_obj.data.materials)
            target_obj.data.materials.clear()
            target_obj.data.materials.append(target_bake_mat)
            #endregion

            #region stitch
            # 5) Perform UV weld
            ZENV_TEXTransitionBakeByUVWeld_Utils.stitch_uvs(merged_obj, shared_edges)
            #endregion

            #region bake
            # 6) Setup objects for baking
            bpy.ops.object.select_all(action='DESELECT')
            merged_obj.select_set(True)
            context.view_layer.objects.active = target_obj
            target_obj.select_set(True)

            # Configure bake settings
            # EMIT bake captures the Emission shader color directly (the
            # source texture), with no BSDF energy conservation loss that
            # would darken/desaturate the result.
            if hasattr(context.scene, 'cycles'):
                context.scene.cycles.bake_type = 'EMIT'
                context.scene.render.bake.margin = 16
                context.scene.render.bake.use_selected_to_active = True
                context.scene.render.bake.use_clear = True
                context.scene.render.bake.target = 'IMAGE_TEXTURES'
                # Explicitly disable cage baking. A leftover cage_object from
                # a previous bake (or user scene settings) triggers Blender's
                # "Invalid cage object, the cage mesh must have the same
                # number of faces as the active object" error, since the
                # merged source mesh rarely matches the target's face count.
                context.scene.render.bake.use_cage = False
                context.scene.render.bake.cage_object = None

            # 7) Bake
            logger.info("Starting bake...")
            bpy.ops.object.bake(
                type='EMIT',
                use_selected_to_active=True,
                margin=16,
                use_clear=True
            )
            #endregion

            #region save
            # 8) Save the baked image
            # Set alpha_mode BEFORE save so it affects the saved file.
            bake_image.file_format = 'PNG'
            bake_image.alpha_mode = 'STRAIGHT'
            bake_image.save()
            logger.info(f"Baked image saved to: {image_filepath}")
            #endregion

            #region cleanup_ok
            # 9) Cleanup
            if context.scene.zenv_weld_cleanup:
                # Clean up temp duplicate objects before removing the merged
                # object.
                ZENV_TEXTransitionBakeByUVWeld_Utils.cleanup_temp_objects(merged_obj)
                merged_mesh = merged_obj.data
                bpy.data.objects.remove(merged_obj, do_unlink=True)
                if merged_mesh.users == 0:
                    bpy.data.meshes.remove(merged_mesh)
                merged_obj = None  # mark as cleaned up
                if bake_material and bake_material.users == 0:
                    bpy.data.materials.remove(bake_material, do_unlink=True)
                    bake_material = None
                if target_bake_mat and target_bake_mat.users == 0:
                    bpy.data.materials.remove(target_bake_mat, do_unlink=True)
                    target_bake_mat = None
            #endregion

            logger.info("===== TRANSITION_WELD OPERATOR END =====")
            self.report({'INFO'}, f"Baked image saved to: {image_filepath}")
            return {'FINISHED'}

        #region except
        except Exception as e:
            logger.error(f"Error during transition weld: {str(e)}")
            self.report({'ERROR'}, str(e))

            # Clean up resources created before the failure.
            if bake_material is not None:
                try:
                    if bake_material.users == 0:
                        bpy.data.materials.remove(bake_material, do_unlink=True)
                except Exception:
                    pass
                bake_material = None
            if target_bake_mat is not None:
                try:
                    if target_bake_mat.users == 0:
                        bpy.data.materials.remove(target_bake_mat, do_unlink=True)
                except Exception:
                    pass
                target_bake_mat = None
            if merged_obj is not None:
                try:
                    ZENV_TEXTransitionBakeByUVWeld_Utils.cleanup_temp_objects(merged_obj)
                    merged_mesh = merged_obj.data
                    bpy.data.objects.remove(merged_obj, do_unlink=True)
                    if merged_mesh.users == 0:
                        bpy.data.meshes.remove(merged_mesh)
                except Exception:
                    pass
                merged_obj = None

            return {'CANCELLED'}
        #endregion

        #region finally
        finally:
            # Restore target object's original materials.
            try:
                target_obj = context.active_object
                if target_obj and original_target_materials:
                    target_obj.data.materials.clear()
                    for mat in original_target_materials:
                        if mat:
                            target_obj.data.materials.append(mat)
            except Exception:
                pass

            # Restore render engine.
            if original_engine is not None:
                try:
                    context.scene.render.engine = original_engine
                except Exception:
                    pass
        #endregion
    #endregion
#endregion

#region panel
class ZENV_PT_TEXTransitionBakeByUVWeld(Panel):
    """Panel for UV stitching tools"""
    bl_label = "TEX Transition by UV Weld"
    bl_idname = "ZENV_PT_transition_texture_weld"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "zenv_weld_resolution")
        
        row = layout.row(align=True)
        row.prop(scene, "zenv_weld_flip_x", text="Flip X")
        row.prop(scene, "zenv_weld_flip_y", text="Flip Y")
        
        layout.prop(scene, "zenv_weld_cleanup")

        layout.operator("zenv.transition_weld")
#endregion

#region register
classes = (
    ZENV_OT_TEXTransitionBakeByUVWeld_Bake,
    ZENV_PT_TEXTransitionBakeByUVWeld,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_TEXTransitionBakeByUVWeld_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_TEXTransitionBakeByUVWeld_Properties.unregister()

if __name__ == "__main__":
    register()
#endregion
