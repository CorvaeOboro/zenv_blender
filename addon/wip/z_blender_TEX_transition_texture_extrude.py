#region META
bl_info = {
    "name": 'TEX Transition Texture Extrude',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Create a transition between two meshes by extruding the edge and baking',
    "status": 'working',
    "approved": True,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 70,
    "addon_order": 70,
    "tags": ['texture', 'bake', 'transition', 'extrude', 'mesh', 'uv'],
    "description_short": 'Create a transition between two meshes by extruding the edge and baking',
    "description_medium": 'Detects shared edges between two touching meshes, extrudes the source mesh onto the target, extends UVs, creates a bake cage, and bakes the diffuse color transition via Cycles.',
    "description_long": """
    TEXTURE TRANSITION by EDGE EXTRUSION
    Creates a continuous texture transition between two touching meshes by
    detecting shared edges, extruding the source mesh's edge onto the target,
    extending UVs, creating a bake cage, and baking the diffuse color from
    the source onto the target via Cycles. Supports per-step toggles,
    configurable bake resolution, samples, margin, and debug mode.""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_TEX_transition_texture_extrude.png',
    "addon_image": 'zenv_blender_TEX_transition_texture_extrude.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import logging
import os
from datetime import datetime
from bpy.props import BoolProperty, FloatProperty, StringProperty, IntProperty, PointerProperty
from bpy.types import PropertyGroup, Operator, Panel
import mathutils
from mathutils.kdtree import KDTree

logger = logging.getLogger(__name__)
_zenv_transition_texture_console_handler = None


def _install_logger():
    """Attach a single StreamHandler to the addon logger (idempotent)."""
    global _zenv_transition_texture_console_handler
    if _zenv_transition_texture_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_transition_texture_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_transition_texture_console_handler
    if _zenv_transition_texture_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_transition_texture_console_handler)
    except ValueError:
        pass
    _zenv_transition_texture_console_handler = None

#endregion
#region PROPS
class ZENV_PG_TransitionTextureExtrude(PropertyGroup):
    """Properties for the Transition Texture Extrude addon."""
    debug: BoolProperty(
        name="Debug Mode",
        description="Keep temporary objects for debugging",
        default=False
    )
    offset: FloatProperty(
        name="Bake Offset",
        description="Offset distance for baking cage",
        default=0.001,
        min=0.0001,
        max=0.1
    )
    resolution: IntProperty(
        name="Resolution",
        description="Resolution of the baked texture",
        default=1024,
        min=64,
        max=8192
    )
    samples: IntProperty(
        name="Samples",
        description="Number of samples for baking",
        default=32,
        min=1,
        max=4096
    )
    margin: IntProperty(
        name="Margin",
        description="Margin size in pixels for bake result",
        default=16,
        min=0,
        max=64
    )
    save_path: StringProperty(
        name="Save Path",
        description="Directory path to save baked textures",
        subtype='DIR_PATH',
        default="//textures"
    )
    # Step toggles
    step_separate: BoolProperty(
        name="1. Separate Meshes",
        description="Separate meshes at shared edge",
        default=True
    )
    step_extend: BoolProperty(
        name="2. Extend Edge",
        description="Extend source mesh over target",
        default=True
    )
    step_uvs: BoolProperty(
        name="3. Extend UVs",
        description="Extend UVs of source mesh",
        default=True
    )
    step_cage: BoolProperty(
        name="4. Create Cage",
        description="Create baking cage",
        default=True
    )
    step_bake: BoolProperty(
        name="5. Bake Texture",
        description="Bake texture from source to target",
        default=True
    )

#endregion
#region UTILS
class ZENV_TransitionTextureExtrude_Utils:
    """Utility functions for texture transition."""

    @staticmethod
    def get_shared_edges(source_obj, target_obj):
        """Find edges that are touching between two meshes.

        Transforms vertices to world space before comparison so that
        objects with different world transforms are handled correctly.
        Uses a KDTree for target vertex proximity queries instead of
        brute-force iteration.
        """
        logger.info("Starting edge analysis between %s and %s",
                     source_obj.name, target_obj.name)

        bm1 = bmesh.new()
        bm1.from_mesh(source_obj.data)
        bm1.verts.ensure_lookup_table()
        bm1.edges.ensure_lookup_table()

        bm2 = bmesh.new()
        bm2.from_mesh(target_obj.data)
        bm2.verts.ensure_lookup_table()
        bm2.edges.ensure_lookup_table()

        logger.info("Source mesh: %d edges, %d vertices", len(bm1.edges), len(bm1.verts))
        logger.info("Target mesh: %d edges, %d vertices", len(bm2.edges), len(bm2.verts))

        # Build world-space vertex positions for both meshes.
        # Force dependency graph update so matrix_world is current.
        if bpy.context.view_layer:
            bpy.context.view_layer.update()
        sm1 = source_obj.matrix_world
        sm2 = target_obj.matrix_world

        # Build KDTree for target mesh vertices in world space.
        target_verts_world = []
        kd = KDTree(len(bm2.verts))
        for v2_idx, v2 in enumerate(bm2.verts):
            co_world = sm2 @ v2.co
            target_verts_world.append(co_world)
            kd.insert(co_world, v2_idx)
        kd.balance()

        threshold = 0.001  # Distance threshold for vertex proximity
        shared_edges = []

        # For each edge in source mesh (in world space).
        for e1 in bm1.edges:
            v1_start = sm1 @ e1.verts[0].co
            v1_end = sm1 @ e1.verts[1].co
            e1_dir = (v1_end - v1_start).normalized()
            e1_length = (v1_end - v1_start).length

            if e1_length < 1e-8:
                continue

            # Find matching vertices in target mesh using KDTree.
            start_matches = []
            for co, idx, dist in kd.find_range(v1_start, threshold):
                start_matches.append((idx, target_verts_world[idx].copy(), dist))

            end_matches = []
            for co, idx, dist in kd.find_range(v1_end, threshold):
                end_matches.append((idx, target_verts_world[idx].copy(), dist))

            if not start_matches or not end_matches:
                continue

            # Find matching edges in target mesh.
            min_distance = float('inf')
            closest_edge = None

            for e2 in bm2.edges:
                s_idx = e2.verts[0].index
                e_idx_ = e2.verts[1].index

                for sm in start_matches:
                    for em in end_matches:
                        if ((s_idx == sm[0] and e_idx_ == em[0]) or
                                (s_idx == em[0] and e_idx_ == sm[0])):
                            v2_start = target_verts_world[s_idx]
                            v2_end = target_verts_world[e_idx_]
                            e2_dir = (v2_end - v2_start).normalized()
                            e2_length = (v2_end - v2_start).length

                            dot_product = abs(e1_dir.dot(e2_dir))
                            length_diff = abs(e1_length - e2_length)

                            if dot_product > 0.99 and length_diff < threshold:
                                dist = (sm[2] + em[2]) / 2.0
                                if dist < min_distance:
                                    min_distance = dist
                                    closest_edge = (e2.index, e2, {
                                        'source_start': v1_start.copy(),
                                        'source_end': v1_end.copy(),
                                        'target_start': v2_start.copy(),
                                        'target_end': v2_end.copy(),
                                        'distance': dist,
                                        'edge_length': e1_length,
                                        'edge_dir': e1_dir.copy(),
                                    })

            if closest_edge:
                shared_edges.append((
                    e1.index,
                    closest_edge[0],
                    closest_edge[2]
                ))

        bm1.free()
        bm2.free()

        logger.info("Found %d shared edges", len(shared_edges))
        return shared_edges

    @staticmethod
    def _compute_edge_extension_direction(edge, direction_sign):
        """Compute the extension direction for an edge.

        Uses the average face normal of linked faces (falling back to a
        perpendicular in XY if no faces are linked) instead of always
        using the XY-plane perpendicular.
        """
        link_faces = edge.link_faces
        if link_faces:
            # Average normal of linked faces.
            avg_normal = mathutils.Vector((0, 0, 0))
            for f in link_faces:
                avg_normal += f.normal
            avg_normal.normalize()
            # Project onto the plane perpendicular to the edge direction.
            edge_dir = (edge.verts[1].co - edge.verts[0].co).normalized()
            ext_dir = avg_normal - edge_dir * avg_normal.dot(edge_dir)
            if ext_dir.length > 1e-8:
                ext_dir.normalize()
            else:
                # Fallback: XY perpendicular.
                ext_dir = mathutils.Vector((-edge_dir.y, edge_dir.x, 0)).normalized()
        else:
            edge_dir = (edge.verts[1].co - edge.verts[0].co).normalized()
            ext_dir = mathutils.Vector((-edge_dir.y, edge_dir.x, 0)).normalized()

        return ext_dir if direction_sign > 0 else -ext_dir

    @staticmethod
    def extend_mesh_at_edge(obj, edge_data, direction, distance):
        """Extend mesh from specified edges using BMesh extrude operator.

        Parameters:
          obj: Source object to extend.
          edge_data: List of (source_edge_idx, target_edge_idx, info_dict).
          direction: Sign-based direction (+1 or -1).
          distance: Extension distance (used instead of edge_length).
        """
        logger.info("Starting mesh extension for %s", obj.name)

        # Create copy of object with clear name.
        new_name = "%s_extended" % obj.name
        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj.name = new_name
        new_obj.data.name = "%s_mesh" % new_name
        bpy.context.collection.objects.link(new_obj)

        edge_indices = [edge_info[0] for edge_info in edge_data]
        logger.info("Processing %d edges for extension", len(edge_indices))

        bm = bmesh.new()
        bm.from_mesh(new_obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Get or create UV layer.
        uv_layer = bm.loops.layers.uv.verify()

        for edge_idx_iter, edge_info in enumerate(edge_data):
            logger.info("Processing edge %d/%d", edge_idx_iter + 1, len(edge_data))

            # Ensure lookup tables before accessing by index.
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            try:
                edge = bm.edges[edge_indices[edge_idx_iter]]
                edge_info_dict = edge_info[2]
                edge_length = edge_info_dict['edge_length']

                # Compute extension direction from face normals.
                extend_dir = ZENV_TransitionTextureExtrude_Utils._compute_edge_extension_direction(
                    edge, 1 if direction > 0 else -1
                )
                extend_dist = distance if distance > 0 else edge_length

                # Collect original UVs.
                orig_uvs = {}
                uv_edge_verts = []
                for face in edge.link_faces:
                    for loop in face.loops:
                        orig_uvs[loop.vert.index] = loop[uv_layer].uv.copy()
                        if loop.vert in edge.verts:
                            uv_edge_verts.append((loop.vert.index, loop[uv_layer].uv.copy()))

                # Compute UV density.
                uv_density = 1.0
                uv_normal = mathutils.Vector((0, 1, 0))
                if len(uv_edge_verts) >= 2:
                    uv_edge_dir = (uv_edge_verts[1][1] - uv_edge_verts[0][1]).normalized()
                    uv_edge_length = (uv_edge_verts[1][1] - uv_edge_verts[0][1]).length
                    if edge_length != 0:
                        uv_density = uv_edge_length / edge_length
                    uv_normal = mathutils.Vector((-uv_edge_dir.y, uv_edge_dir.x, 0))

                # Store original geometry.
                orig_verts = set(edge.verts)
                orig_faces = set(edge.link_faces)
                orig_vert_indices = {v.index for v in orig_verts}

                # Extrude.
                ret = bmesh.ops.extrude_edge_only(bm, edges=[edge])

                # Ensure lookup tables after extrusion.
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()

                # Collect new geometry - track new verts directly from extrude result.
                new_verts = set()
                new_faces = set()
                new_edges = set()
                for elem in ret['geom']:
                    if isinstance(elem, bmesh.types.BMVert):
                        if elem not in orig_verts:
                            new_verts.add(elem)
                    elif isinstance(elem, bmesh.types.BMFace):
                        if elem not in orig_faces:
                            new_faces.add(elem)
                    elif isinstance(elem, bmesh.types.BMEdge):
                        new_edges.add(elem)

                # Build mapping from original vert to corresponding new vert.
                vert_mapping = {}
                for nv in new_verts:
                    # New verts from extrude_edge_only correspond 1:1 to original verts.
                    # Find the closest original vert.
                    best_dist = float('inf')
                    best_orig = None
                    for ov in orig_verts:
                        d = (nv.co - ov.co).length
                        if d < best_dist:
                            best_dist = d
                            best_orig = ov
                    if best_orig is not None:
                        vert_mapping[best_orig] = nv

                # Translate new vertices.
                bmesh.ops.translate(
                    bm,
                    vec=extend_dir * extend_dist,
                    verts=list(new_verts)
                )

                # Update UVs for new geometry.
                new_edge = None
                for e in new_edges:
                    if all(v in new_verts for v in e.verts):
                        new_edge = e
                        break

                if new_edge and len(uv_edge_verts) >= 2:
                    orig_mid = (edge.verts[0].co + edge.verts[1].co) / 2
                    new_mid = (new_edge.verts[0].co + new_edge.verts[1].co) / 2
                    actual_offset = (new_mid - orig_mid).length

                    uv_offset_length = actual_offset * uv_density
                    uv_offset_dir = uv_normal if direction > 0 else -uv_normal
                    # UV coordinates are 2D - use .xy for the offset.
                    uv_offset = (uv_offset_dir * uv_offset_length).xy

                    # Update UVs on new faces.
                    for face in new_faces:
                        for loop in face.loops:
                            if loop.vert in orig_verts:
                                # Original vertex on the edge - keep its UV.
                                if loop.vert.index in orig_uvs:
                                    loop[uv_layer].uv = orig_uvs[loop.vert.index].copy()
                            else:
                                # New vertex - find its corresponding original vert.
                                for ov, nv in vert_mapping.items():
                                    if loop.vert == nv and ov.index in orig_uvs:
                                        loop[uv_layer].uv = orig_uvs[ov.index].copy() + uv_offset
                                        break

            except Exception as e:
                logger.error("Error processing edge %d: %s", edge_idx_iter + 1, str(e))
                continue

        # Final geometry update.
        bm.normal_update()
        bm.to_mesh(new_obj.data)
        new_obj.data.update()
        bm.free()

        logger.info("Mesh extension complete")
        return new_obj

    @staticmethod
    def extend_uvs(obj, edge_data, direction, distance):
        """Extend UVs from specified edges using BMesh API (headless-safe).

        Only modifies UVs of faces that were created by the extension,
        not the entire UV map.  Uses BMesh directly instead of bpy.ops.
        """
        logger.info("Starting UV extension on %s", obj.name)

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            bm.free()
            logger.info("No active UV layer found, skipping UV extension")
            return obj

        # Identify extended faces: faces that share a vertex with a shared edge
        # but were not part of the original mesh.  We detect them by checking
        # for faces where some vertices coincide with shared-edge endpoints
        # and other vertices are offset by the extension direction.
        shared_edge_indices = {e_info[0] for e_info in edge_data}
        threshold = 0.001

        # Collect world-space edge endpoints for matching.
        edge_endpoints = []
        for e_info in edge_data:
            info = e_info[2]
            edge_endpoints.append((info['source_start'].copy(), info['source_end'].copy()))

        # Find faces that are adjacent to shared edges (these are the extended faces).
        extended_faces = set()
        for e_idx in shared_edge_indices:
            if e_idx < len(bm.edges):
                edge = bm.edges[e_idx]
                for face in edge.link_faces:
                    extended_faces.add(face)

        if not extended_faces:
            # Try to find faces by position matching (for extended mesh).
            for face in bm.faces:
                for ep_start, ep_end in edge_endpoints:
                    face_verts = [v.co for v in face.verts]
                    # Check if face has vertices near both edge endpoints.
                    near_start = any((v - ep_start).length < threshold for v in face_verts)
                    near_end = any((v - ep_end).length < threshold for v in face_verts)
                    if near_start and near_end:
                        extended_faces.add(face)
                        break

        if not extended_faces:
            bm.free()
            logger.info("No extended faces found, skipping UV extension")
            return obj

        # Compute UV offset direction from the 3D direction.
        # Project the 3D extension direction onto the UV plane.
        uv_offset = mathutils.Vector((direction.x * distance, direction.y * distance, 0))

        # Offset UVs only on the extended faces - specifically the vertices
        # that are NOT on the shared edge (the "new" vertices).
        for face in extended_faces:
            # Determine which vertices of this face are on the shared edge.
            edge_verts = set()
            for ep_start, ep_end in edge_endpoints:
                for v in face.verts:
                    if (v.co - ep_start).length < threshold or (v.co - ep_end).length < threshold:
                        edge_verts.add(v)

            for loop in face.loops:
                if loop.vert not in edge_verts:
                    # This is an extended vertex - offset its UV.
                    current_uv = loop[uv_layer].uv.copy()
                    loop[uv_layer].uv = current_uv + uv_offset.xy

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        logger.info("UV extension complete")
        return obj

    @staticmethod
    def create_bake_cage(obj, offset):
        """Create offset cage for baking.

        Creates a copy with a Solidify modifier and applies it so the
        cage mesh is self-contained.
        """
        cage = obj.copy()
        cage.data = obj.data.copy()
        cage.name = "%s_cage" % obj.name
        bpy.context.scene.collection.objects.link(cage)

        mod = cage.modifiers.new(name="Cage", type='SOLIDIFY')
        mod.thickness = offset
        mod.offset = 1.0

        # Apply the modifier so the cage mesh is self-contained.
        bpy.context.view_layer.objects.active = cage
        cage.select_set(True)
        bpy.ops.object.select_all(action='DESELECT')
        cage.select_set(True)
        bpy.context.view_layer.objects.active = cage
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except Exception as e:
            logger.warning("Could not apply cage modifier: %s", str(e))

        return cage

    @staticmethod
    def prepare_mesh_for_baking(obj):
        """Prepare mesh for baking by setting correct shading and normals."""
        orig_shade_smooth = [p.use_smooth for p in obj.data.polygons]

        # Set flat shading directly on polygons (headless-safe).
        for p in obj.data.polygons:
            p.use_smooth = False

        # use_auto_smooth was removed in Blender 4.1+.
        if hasattr(obj.data, 'use_auto_smooth'):
            obj.data.use_auto_smooth = False

        # Recalculate face normals.
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()

        return orig_shade_smooth

    @staticmethod
    def restore_mesh_shading(obj, orig_shade_smooth):
        """Restore original shading settings."""
        for p, smooth in zip(obj.data.polygons, orig_shade_smooth):
            p.use_smooth = smooth

    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking.

        Does not force GPU - respects the user's existing device setting.
        Guards Cycles availability.
        """
        logger.info("Setting up render settings for baking")

        original_engine = context.scene.render.engine
        logger.info("Original render engine: %s", original_engine)

        # Set to Cycles.
        context.scene.render.engine = 'CYCLES'
        logger.info("Set render engine to CYCLES")

        original_device = None
        if hasattr(context.scene, 'cycles'):
            # Preserve original device; don't force GPU.
            original_device = context.scene.cycles.device
            context.scene.cycles.samples = context.scene.zenv_transition_texture.samples
            logger.info("Cycles samples set to: %d", context.scene.cycles.samples)

            # Set bake type and passes.
            context.scene.cycles.bake_type = 'DIFFUSE'
            context.scene.render.bake.use_pass_direct = False
            context.scene.render.bake.use_pass_indirect = False
            context.scene.render.bake.use_pass_color = True
            logger.info("Configured for diffuse color-only baking (no lighting)")

            # Bake settings - disable denoising for baking.
            context.scene.cycles.use_denoising = False
            if hasattr(context.scene.cycles, 'use_high_quality_normals'):
                context.scene.cycles.use_high_quality_normals = True
            logger.info("Disabled denoising for baking")

        # Bake settings.
        context.scene.render.bake.margin = context.scene.zenv_transition_texture.margin
        context.scene.render.bake.use_clear = True
        context.scene.render.bake.use_selected_to_active = True
        context.scene.render.bake.max_ray_distance = 0.1
        logger.info("Bake settings: margin=%d, ray_distance=0.1",
                     context.scene.render.bake.margin)

        return original_engine, original_device

    @staticmethod
    def setup_bake_materials(source_obj, target_obj, context):
        """Setup temporary material for baking while preserving original materials."""
        logger.info("Setting up bake materials")

        # Ensure texture directory exists.
        texture_dir = bpy.path.abspath(context.scene.zenv_transition_texture.save_path)
        if not os.path.exists(texture_dir):
            try:
                os.makedirs(texture_dir)
                logger.info("Created texture directory: %s", texture_dir)
            except Exception as e:
                logger.error("Failed to create texture directory: %s", str(e))
                texture_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
                os.makedirs(texture_dir, exist_ok=True)
                logger.info("Using fallback directory: %s", texture_dir)

        # Generate unique filename.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "bake_transition_%s.png" % timestamp
        texture_path = os.path.join(texture_dir, filename)
        logger.info("Texture will be saved to: %s", texture_path)

        # Store original materials.
        source_original_mats = [mat for mat in source_obj.data.materials]
        target_original_mats = [mat for mat in target_obj.data.materials]
        logger.info("Stored original materials - Source: %d, Target: %d",
                     len(source_original_mats), len(target_original_mats))

        # Create temporary bake material.
        temp_bake_mat = bpy.data.materials.new(name="__TEMP_BAKE_MATERIAL__")
        temp_bake_mat.use_nodes = True
        nodes = temp_bake_mat.node_tree.nodes
        nodes.clear()

        # Create image node for baking.
        tex_image = nodes.new('ShaderNodeTexImage')
        bake_image = bpy.data.images.new(
            filename,
            width=context.scene.zenv_transition_texture.resolution,
            height=context.scene.zenv_transition_texture.resolution,
            alpha=True,
            float_buffer=False  # PNG is 8-bit; float_buffer wastes memory.
        )
        bake_image.filepath_raw = texture_path
        bake_image.file_format = 'PNG'

        tex_image.image = bake_image
        tex_image.select = True
        nodes.active = tex_image

        # Temporarily assign bake material to target.
        if not target_obj.data.materials:
            target_obj.data.materials.append(temp_bake_mat)
        else:
            target_obj.data.materials[0] = temp_bake_mat

        logger.info("Temporary bake material setup complete")

        return {
            'bake_image': bake_image,
            'temp_material': temp_bake_mat,
            'source_materials': source_original_mats,
            'target_materials': target_original_mats
        }

    @staticmethod
    def cleanup_material_slots(obj):
        """Remove unused material slots from the object using data API.

        Instead of bpy.ops.object.material_slot_remove(), this method
        clears all materials and re-appends only the ones used by
        polygons, preserving their order.
        """
        logger.info("Cleaning up material slots on %s", obj.name)

        if obj.type != 'MESH' or not obj.data:
            return

        # Collect used material indices and the actual materials.
        used_indices = set()
        for polygon in obj.data.polygons:
            used_indices.add(polygon.material_index)

        # Build list of materials that are used.
        used_materials = []
        old_slots = list(obj.material_slots)
        for i, slot in enumerate(old_slots):
            if i in used_indices and slot.material is not None:
                used_materials.append(slot.material)

        # Clear all material slots and re-append used ones.
        obj.data.materials.clear()
        for mat in used_materials:
            obj.data.materials.append(mat)

        # Remap polygon material indices.
        # Build old-index -> new-index mapping.
        old_to_new = {}
        new_idx = 0
        for i, slot in enumerate(old_slots):
            if i in used_indices and slot.material is not None:
                old_to_new[i] = new_idx
                new_idx += 1

        for polygon in obj.data.polygons:
            old_idx = polygon.material_index
            polygon.material_index = old_to_new.get(old_idx, 0)

        logger.info("Material slot cleanup complete on %s (%d -> %d slots)",
                     obj.name, len(old_slots), len(used_materials))

#endregion
#region OP
class ZENV_OT_TransitionTextureExtrude(Operator):
    """Bake texture transition between selected meshes"""
    bl_idname = "zenv.transition_bake_extend"
    bl_label = "Bake Transition"
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
        props = context.scene.zenv_transition_texture
        try:
            # Get objects based on selection order.
            # Active object (last selected) will be the target.
            # Other selected object will be the source to extend.
            target_obj = context.active_object
            source_obj = [obj for obj in context.selected_objects if obj != target_obj][0]

            logger.info("Using selection order for baking:")
            logger.info("Source object (will be extended): %s", source_obj.name)
            logger.info("Target object (active, bake target): %s", target_obj.name)

            debug_mode = props.debug
            temp_objects = []

            # Store original settings.
            original_engine = context.scene.render.engine
            original_device = (
                context.scene.cycles.device if hasattr(context.scene, 'cycles') else None
            )

            # Initialize variables so they're always defined.
            source_extended = source_obj
            source_uvs = source_obj
            cage_obj = None
            bake_data = None

            try:
                # 0) Clean up unused material slots.
                logger.info("Step 0: Cleaning up unused material slots")
                ZENV_TransitionTextureExtrude_Utils.cleanup_material_slots(source_obj)
                ZENV_TransitionTextureExtrude_Utils.cleanup_material_slots(target_obj)

                # 1) Setup global render/bake settings.
                original_engine, original_device = \
                    ZENV_TransitionTextureExtrude_Utils.setup_render_settings(context)

                # 2) Step 1: find shared edges.
                shared_edges = []
                if props.step_separate:
                    logger.info("Step 1: Finding shared edges")
                    shared_edges = ZENV_TransitionTextureExtrude_Utils.get_shared_edges(
                        source_obj, target_obj
                    )
                    if not shared_edges:
                        self.report({'ERROR'}, "No shared edges found")
                        return {'CANCELLED'}
                    logger.info("Found %d shared edges", len(shared_edges))

                # 3) Step 2: Extend only the source mesh.
                if props.step_extend and shared_edges:
                    logger.info("Step 2: Extending source mesh")
                    # Direction: from source toward target (world-space).
                    direction_vec = (target_obj.location - source_obj.location).normalized()
                    direction_sign = 1.0  # Extend toward target.

                    source_extended = ZENV_TransitionTextureExtrude_Utils.extend_mesh_at_edge(
                        source_obj,
                        shared_edges,
                        direction_sign,
                        1.0
                    )

                    if debug_mode:
                        temp_objects.append(source_extended)

                # 4) Step 3: Extend UVs on the newly extended source.
                if props.step_uvs and shared_edges:
                    logger.info("Step 3: Extending UVs")
                    source_uvs = ZENV_TransitionTextureExtrude_Utils.extend_uvs(
                        source_extended,
                        shared_edges,
                        (target_obj.location - source_obj.location).normalized(),
                        0.2
                    )
                    if debug_mode:
                        temp_objects.append(source_uvs)

                # 5) Step 4: Create cage (optional).
                if props.step_cage and shared_edges:
                    logger.info("Step 4: Creating bake cage")
                    cage_obj = ZENV_TransitionTextureExtrude_Utils.create_bake_cage(
                        source_uvs,
                        props.offset
                    )
                    if debug_mode:
                        temp_objects.append(cage_obj)

                # 6) Step 5: Bake.
                if props.step_bake:
                    logger.info("Step 5: Setting up bake materials")

                    bake_source = source_uvs
                    logger.info("Using source mesh for baking: %s", bake_source.name)

                    bake_data = ZENV_TransitionTextureExtrude_Utils.setup_bake_materials(
                        bake_source, target_obj, context
                    )

                    logger.info("Starting bake process")
                    logger.info("Source object (for baking): %s", bake_source.name)
                    logger.info("Target object: %s", target_obj.name)

                    # Correct selection order: source selected, target active.
                    bpy.ops.object.select_all(action='DESELECT')
                    bake_source.select_set(True)
                    target_obj.select_set(True)
                    bpy.context.view_layer.objects.active = target_obj

                    logger.info("Selection state set for baking")

                    # Perform bake - pass cage object if available.
                    try:
                        bake_kwargs = dict(
                            type='DIFFUSE',
                            pass_filter={'COLOR'},
                            use_selected_to_active=True,
                            margin=props.margin,
                            use_clear=True
                        )
                        if cage_obj is not None:
                            bake_kwargs['use_cage'] = True
                            bake_kwargs['cage_object'] = cage_obj.name
                        bpy.ops.object.bake(**bake_kwargs)

                        logger.info("Bake operation completed")

                        if bake_data['bake_image'].has_data:
                            try:
                                bake_data['bake_image'].save()
                                logger.info("Baked texture saved to: %s",
                                             bake_data['bake_image'].filepath_raw)
                                try:
                                    bake_data['bake_image'].pack()
                                    logger.info("Image packed successfully")
                                except Exception as e:
                                    logger.info("Warning: Could not pack image: %s", str(e))
                            except Exception as e:
                                logger.error("Failed to save baked image: %s", str(e))
                                raise
                        else:
                            logger.error("Bake failed - no image data generated")
                            raise Exception("No image data after baking")

                    except Exception as e:
                        logger.error("Bake operation failed: %s", str(e))
                        raise

                    finally:
                        # Restore original materials.
                        logger.info("Restoring original materials")
                        target_obj.data.materials.clear()
                        for mat in bake_data['target_materials']:
                            target_obj.data.materials.append(mat)

                        # Remove temporary material.
                        try:
                            bpy.data.materials.remove(bake_data['temp_material'])
                        except Exception:
                            pass
                        logger.info("Cleanup completed")

                # Cleanup duplicates if not in debug mode.
                if not debug_mode:
                    for obj_del in temp_objects:
                        if obj_del and obj_del != source_obj:
                            try:
                                bpy.data.objects.remove(obj_del, do_unlink=True)
                            except (ReferenceError, RuntimeError):
                                pass
                    if cage_obj and cage_obj != source_obj:
                        try:
                            bpy.data.objects.remove(cage_obj, do_unlink=True)
                        except (ReferenceError, RuntimeError):
                            pass
                    # Also clean up extended source if it's not in temp_objects
                    # (it's only added to temp_objects in debug mode).
                    if source_extended != source_obj:
                        try:
                            bpy.data.objects.remove(source_extended, do_unlink=True)
                        except (ReferenceError, RuntimeError):
                            pass

                logger.info("Texture transition complete")
                return {'FINISHED'}

            finally:
                # Restore original render settings.
                context.scene.render.engine = original_engine
                if hasattr(context.scene, 'cycles') and original_device:
                    context.scene.cycles.device = original_device
                # Clean up bake image if bake failed.
                if bake_data and 'bake_image' in bake_data:
                    try:
                        if not bake_data['bake_image'].has_data:
                            bpy.data.images.remove(bake_data['bake_image'])
                    except (ReferenceError, RuntimeError):
                        pass

        except Exception as e:
            logger.exception("Error during texture transition")
            self.report({'ERROR'}, "Transition failed: %s" % str(e))
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_TransitionTextureExtrude(Panel):
    """Panel for texture transition generation and settings"""
    bl_label = "TEX Texture Transition"
    bl_idname = "ZENV_PT_TransitionTextureExtrude"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_transition_texture

        layout.prop(props, "debug")

        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(props, "offset")
        box.prop(props, "resolution")
        box.prop(props, "samples")
        box.prop(props, "margin")
        box.prop(props, "save_path")

        box = layout.box()
        box.label(text="Process Steps:")
        box.prop(props, "step_separate")
        box.prop(props, "step_extend")
        box.prop(props, "step_uvs")
        box.prop(props, "step_cage")
        box.prop(props, "step_bake")

        layout.operator("zenv.transition_bake_extend")

#endregion
#region REG
classes = (
    ZENV_PG_TransitionTextureExtrude,
    ZENV_OT_TransitionTextureExtrude,
    ZENV_PT_TransitionTextureExtrude,
)


def register():
    """Register all addon classes, scene property, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.zenv_transition_texture = PointerProperty(
        type=ZENV_PG_TransitionTextureExtrude
    )


def unregister():
    """Unregister all addon classes, remove scene property, and remove the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_transition_texture"):
        delattr(bpy.types.Scene, "zenv_transition_texture")
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
