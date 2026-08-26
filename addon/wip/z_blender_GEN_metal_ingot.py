#region META
bl_info = {
    "name": 'GEN Metal Ingot Generator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate metal ingot meshes with surface imperfections, bevels, grid cutting, and noise detail.',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['generative', 'metal', 'ingot', 'procedural', 'mesh', 'surface'],
    "description_short": 'Generate metal ingot meshes with surface imperfections',
    "description_medium": 'Creates metal ingots with a trapezoidal base shape, beveled edges, grid cutting for uniform topology, multi-layer noise surface displacement, smelting bubbles, micro surface detail, UV mapping, and mesh optimization.',
    "description_long": """
    GEN Metal Ingot Generator
    Creates metal ingots with surface imperfections. Uses a trapezoidal
    base shape with beveled edges, UV mapping to hide seam along base,
    surface cutting by world-unit slices, multiple noise layers for
    surface detail, and mesh optimization. Supports deterministic output
    via random seed.""",
    "location": 'View3D > ZENV > GEN Metal Ingot',
    "image_overview": 'zenv_blender_GEN_metal_ingot.png',
    "addon_image": 'zenv_blender_GEN_metal_ingot.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import math
import random
import logging
from mathutils import Vector, noise
from bpy.props import (
    FloatProperty,
    BoolProperty,
    IntProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
_zenv_ingot_console_handler = None

#endregion
#region PROPS
class ZENV_PG_MetalIngot(PropertyGroup):
    """Properties for metal ingot generation."""

    # Base shape properties
    length: FloatProperty(
        name="Length",
        description="Length of the ingot",
        default=0.2,
        min=0.05,
        max=1.0,
        unit='LENGTH'
    )
    width: FloatProperty(
        name="Width",
        description="Width of the ingot at the base",
        default=0.1,
        min=0.025,
        max=0.5,
        unit='LENGTH'
    )
    height: FloatProperty(
        name="Height",
        description="Height of the ingot",
        default=0.05,
        min=0.01,
        max=0.25,
        unit='LENGTH'
    )
    taper: FloatProperty(
        name="Taper",
        description="Amount of tapering from base to top",
        default=0.2,
        min=0.0,
        max=0.5
    )
    variation_scale: FloatProperty(
        name="Variation Range",
        description="Scale of random variations in base shape, 0.3 default",
        default=0.3,
        min=0.0,
        max=1.0
    )

    # Surface detail properties
    detail_scale: FloatProperty(
        name="Detail Intensity",
        description="Scale of surface imperfections",
        default=1.0,
        min=0.1,
        max=10.0
    )
    roughness: FloatProperty(
        name="Roughness",
        description="Intensity of surface roughness",
        default=0.001,
        min=0.0,
        max=0.01,
        precision=4
    )
    bubble_density: IntProperty(
        name="Bubble Density",
        description="Number of smelting bubbles/imperfections",
        default=15,
        min=0,
        max=100
    )
    micro_detail: FloatProperty(
        name="Micro Intensity",
        description="Intensity of centimeter-scale surface imperfections",
        default=0.0005,
        min=-1.000,
        max=1.000,
        precision=5
    )
    micro_scale: FloatProperty(
        name="Micro Scale",
        description="Scale of micro surface details (in centimeters)",
        default=0.5,
        min=0.1,
        max=5.0
    )

    # Remesh properties
    grid_size: FloatProperty(
        name="Grid Size",
        description="Size of grid cutting in centimeters",
        default=1.0,
        min=0.1,
        max=2.0,
        precision=2
    )

    # Bevel properties
    bevel_width: FloatProperty(
        name="Bevel Width",
        description="Width of edge bevels",
        default=0.005,
        min=0.001,
        max=0.02,
        precision=4
    )
    bevel_segments: IntProperty(
        name="Bevel Segments",
        description="Number of bevel segments",
        default=4,
        min=2,
        max=6
    )

    # Step control properties
    do_bevel: BoolProperty(
        name="Apply Bevel",
        description="Apply bevel modifier to edges",
        default=True
    )
    do_grid_cut: BoolProperty(
        name="Apply Grid Cut",
        description="Cut mesh into grid pattern",
        default=True
    )
    do_micro_detail: BoolProperty(
        name="Apply Micro Detail",
        description="Add micro surface imperfections",
        default=True
    )
    do_optimize: BoolProperty(
        name="Optimize Mesh",
        description="Apply smart mesh optimization",
        default=True
    )
    do_random_uv: BoolProperty(
        name="Random UV Transform",
        description="Randomly transform UVs for variation",
        default=True
    )
    do_subsurf: BoolProperty(
        name="Apply Subdivision",
        description="Add subdivision surface for smoothing",
        default=False
    )
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed for deterministic ingot generation",
        default=42,
        min=0,
        max=999999
    )

#endregion
#region UTILS
class ZENV_MetalIngot_Utils:
    """Utility functions for metal ingot generation."""

    @staticmethod
    def generate_base_shape(bm, props, rng):
        """Create the basic trapezoidal ingot shape."""
        l, w, h = props.length, props.width, props.height
        t = props.taper
        v_scale = props.variation_scale * 0.02

        def random_offset():
            return rng.uniform(-v_scale, v_scale)

        # Bottom vertices (keep flat for stability)
        v1 = bm.verts.new((-l / 2, -w / 2, 0))
        v2 = bm.verts.new((l / 2, -w / 2, 0))
        v3 = bm.verts.new((l / 2, w / 2, 0))
        v4 = bm.verts.new((-l / 2, w / 2, 0))

        # Top vertices (with taper and subtle random variations)
        top_rand = props.variation_scale * 0.01
        v5 = bm.verts.new((-l / 2 * (1 - t) + random_offset(),
                           -w / 2 * (1 - t) + random_offset(),
                           h + rng.uniform(-top_rand, top_rand)))
        v6 = bm.verts.new((l / 2 * (1 - t) + random_offset(),
                           -w / 2 * (1 - t) + random_offset(),
                           h + rng.uniform(-top_rand, top_rand)))
        v7 = bm.verts.new((l / 2 * (1 - t) + random_offset(),
                           w / 2 * (1 - t) + random_offset(),
                           h + rng.uniform(-top_rand, top_rand)))
        v8 = bm.verts.new((-l / 2 * (1 - t) + random_offset(),
                           w / 2 * (1 - t) + random_offset(),
                           h + rng.uniform(-top_rand, top_rand)))

        # Create faces
        faces = [
            [v1, v2, v3, v4],  # bottom
            [v5, v6, v7, v8],  # top
            [v1, v5, v6, v2],  # front
            [v2, v6, v7, v3],  # right
            [v3, v7, v8, v4],  # back
            [v4, v8, v5, v1],  # left
        ]

        for f in faces:
            bm.faces.new(f)

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return bm

    @staticmethod
    def add_surface_undulations(bm, props, rng):
        """Add surface imperfections using multiple noise layers."""
        noise_seed = rng.randint(0, 999999)

        for v in bm.verts:
            # Layer 1: Large-scale undulations
            noise1 = noise.noise(v.co * props.detail_scale + Vector((noise_seed, 0, 0))) * props.roughness * 0.8

            # Layer 2: Medium details
            noise2 = noise.noise(v.co * props.detail_scale * 4 + Vector((0, noise_seed, 0))) * props.roughness * 0.4

            # Layer 3: Fine surface texture
            noise3 = noise.noise(v.co * props.detail_scale * 16 + Vector((0, 0, noise_seed))) * props.roughness * 0.2

            total_displacement = (noise1 + noise2 + noise3)
            if v.co.z > props.height * 0.9:
                total_displacement *= 0.5
            v.co += v.normal * total_displacement

    @staticmethod
    def add_smelting_bubbles(bm, props, rng):
        """Add random bubble-like imperfections."""
        bubble_radius = max(props.roughness * 10, 0.005)  # Ensure visible radius

        for _ in range(props.bubble_density):
            x = rng.uniform(-props.length / 2, props.length / 2)
            y = rng.uniform(-props.width / 2, props.width / 2)
            z = rng.uniform(0, props.height)

            center = Vector((x, y, z))
            for v in bm.verts:
                dist = (center - v.co).length
                if dist < bubble_radius:
                    factor = 1 - (dist / bubble_radius)
                    v.co += v.normal * factor * props.roughness

    @staticmethod
    def add_micro_detail(bm, props, rng):
        """Add final pass of cellular noise for micro surface imperfections."""
        noise_seed = rng.randint(0, 999999)
        scale = 100 * props.micro_scale

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        # Create vertex set for edge detection
        edge_vertices = set()
        for edge in bm.edges:
            if edge.calc_face_angle_signed() > math.radians(30):
                edge_vertices.add(edge.verts[0])
                edge_vertices.add(edge.verts[1])

        def cellular_noise(pos, offset):
            """Enhanced Manhattan distance cellular noise."""
            scaled_pos = (pos * scale) + Vector((offset, offset, offset))
            p = Vector((int(scaled_pos.x), int(scaled_pos.y), int(scaled_pos.z)))

            min_dist = float('inf')
            second_min_dist = float('inf')

            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    for dz in range(-2, 3):
                        cell_pos = p + Vector((dx, dy, dz))
                        # Use a local RNG seeded deterministically - does not
                        # corrupt the global random state.
                        local_seed = hash((cell_pos.x, cell_pos.y, cell_pos.z, noise_seed))
                        local_rng = random.Random(local_seed)
                        point = cell_pos + Vector((local_rng.random(), local_rng.random(), local_rng.random()))

                        dist = abs(point.x - scaled_pos.x) + abs(point.y - scaled_pos.y) + abs(point.z - scaled_pos.z)

                        if dist < min_dist:
                            second_min_dist = min_dist
                            min_dist = dist
                        elif dist < second_min_dist:
                            second_min_dist = dist

            diff = (second_min_dist - min_dist) / scale
            return math.tanh(diff * 3.0) * 2.0 - 1.0

        # Light smoothing - does not destroy base shape (was factor=0.5)
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.1,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)

        orig_positions = {v: v.co.copy() for v in bm.verts}

        # First pass: calculate noise range for normalization
        noise_values = []
        for v in bm.verts:
            n1 = cellular_noise(v.co, 0)
            n2 = cellular_noise(v.co, 100) * 0.6
            n3 = cellular_noise(v.co, -100) * 0.3
            total = (n1 + n2 + n3) * 0.5
            noise_values.append(total)

        noise_min = min(noise_values)
        noise_max = max(noise_values)
        noise_range = noise_max - noise_min

        # Apply normalized noise
        for v, noise_val in zip(bm.verts, noise_values):
            if noise_range > 0:
                total = 2.0 * ((noise_val - noise_min) / noise_range) - 1.0
            else:
                total = 0

            total *= props.micro_detail

            if v in edge_vertices:
                total *= 0.3

            normal = Vector((0, 0, 0))
            num_faces = 0
            for face in v.link_faces:
                normal += face.normal
                num_faces += 1
            if num_faces > 0:
                normal.normalize()
            else:
                normal = v.normal

            v.co = orig_positions[v] + normal * total

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # Gentle post-smoothing
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.05,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)

    @staticmethod
    def setup_uv_mapping(bm):
        """Set up UV mapping with bottom edge seams."""
        if not bm.loops.layers.uv:
            bm.loops.layers.uv.new()

        for edge in bm.edges:
            verts_z = [v.co.z for v in edge.verts]
            if max(verts_z) < 0.01:
                edge.seam = True

        return bm

    @staticmethod
    def apply_grid_cut(bm, props):
        """Apply grid cutting using bmesh operations (headless-safe).

        Writes the mesh back only once after all cuts are complete.
        """
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        grid_size = props.grid_size * 0.01  # Convert cm to meters

        for axis in range(3):
            start = grid_size * (bounds_min[axis] // grid_size)
            end = bounds_max[axis]
            num_cuts = int((end - start) / grid_size) + 2

            for i in range(num_cuts):
                cut_pos = start + (i * grid_size)
                plane_co = Vector((0, 0, 0))
                plane_co[axis] = cut_pos
                plane_no = Vector((0, 0, 0))
                plane_no[axis] = 1.0

                try:
                    bmesh.ops.bisect_plane(
                        bm,
                        geom=bm.edges[:] + bm.faces[:],
                        dist=0.00001,
                        plane_co=plane_co,
                        plane_no=plane_no,
                        use_snap_center=False,
                        clear_outer=False,
                        clear_inner=False
                    )
                except Exception:
                    continue

        # Final cleanup - single pass after all cuts
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00001)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    @staticmethod
    def randomize_uvs(bm, rng):
        """Apply random transformation to UV coordinates."""
        uv_layer = bm.loops.layers.uv.verify()
        if not uv_layer:
            return

        angle = rng.uniform(0, math.radians(360))
        scale = rng.uniform(0.9, 1.1)
        offset_x = rng.uniform(-1, 1)
        offset_y = rng.uniform(-1, 1)
        mirror_x = rng.choice([-1, 1])
        mirror_y = rng.choice([-1, 1])

        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)

        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                x = uv.x - 0.5
                y = uv.y - 0.5
                x *= mirror_x
                y *= mirror_y
                rotated_x = x * cos_angle - y * sin_angle
                rotated_y = x * sin_angle + y * cos_angle
                scaled_x = rotated_x * scale
                scaled_y = rotated_y * scale
                final_x = scaled_x + 0.5 + offset_x
                final_y = scaled_y + 0.5 + offset_y
                loop[uv_layer].uv = Vector((final_x, final_y))

#endregion
#region OP
class ZENV_OT_MetalIngot(Operator):
    """Generate a metal ingot with realistic surface details"""
    bl_idname = "zenv.metal_ingot"
    bl_label = "Generate Metal Ingot"
    bl_description = "Generate a metal ingot mesh with surface imperfections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def _safe_mode_set(self, mode):
        """Safely switch object mode with context guard."""
        try:
            bpy.ops.object.mode_set(mode=mode)
        except Exception:
            pass

    def execute(self, context):
        props = context.scene.zenv_metal_ingot_props
        rng = random.Random(props.random_seed)

        bm = None
        obj = None

        try:
            # --- Create base mesh ---
            bm = bmesh.new()
            ZENV_MetalIngot_Utils.generate_base_shape(bm, props, rng)
            ZENV_MetalIngot_Utils.add_surface_undulations(bm, props, rng)
            ZENV_MetalIngot_Utils.add_smelting_bubbles(bm, props, rng)

            mesh = bpy.data.meshes.new("Metal_Ingot")
            obj = bpy.data.objects.new(mesh.name, mesh)
            context.collection.objects.link(obj)
            context.view_layer.objects.active = obj
            obj.select_set(True)

            # UV setup + seam marking
            ZENV_MetalIngot_Utils.setup_uv_mapping(bm)
            bm.to_mesh(mesh)
            bm.free()
            bm = None

            # Initial UV unwrap (requires edit mode)
            self._safe_mode_set('EDIT')
            try:
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.unwrap(method='CONFORMAL', margin=0.001)
            except Exception:
                pass
            self._safe_mode_set('OBJECT')

            # --- Bevel ---
            if props.do_bevel:
                bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
                bevel.width = props.bevel_width
                bevel.segments = props.bevel_segments
                bevel.limit_method = 'ANGLE'
                bevel.angle_limit = math.radians(30)
                context.view_layer.objects.active = obj
                try:
                    bpy.ops.object.modifier_apply(modifier=bevel.name)
                except Exception as e:
                    logger.warning("Bevel apply failed: %s", e)

            # --- Grid cut ---
            if props.do_grid_cut:
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                ZENV_MetalIngot_Utils.apply_grid_cut(bm, props)
                bm.to_mesh(obj.data)
                obj.data.update()
                bm.free()
                bm = None

                # Weighted normal modifier
                weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
                weighted_normal.keep_sharp = True
                weighted_normal.weight = 50
                weighted_normal.thresh = 0.01
                try:
                    bpy.ops.object.modifier_apply(modifier=weighted_normal.name)
                except Exception as e:
                    logger.warning("Weighted normal apply failed: %s", e)

            # --- Micro detail ---
            if props.do_micro_detail:
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                ZENV_MetalIngot_Utils.add_micro_detail(bm, props, rng)
                bm.to_mesh(obj.data)
                obj.data.update()
                bm.free()
                bm = None

            # --- Subdivision (optional) ---
            if props.do_subsurf:
                subsurf = obj.modifiers.new(name="Subdivision", type='SUBSURF')
                subsurf.levels = 1
                subsurf.render_levels = 2
                try:
                    bpy.ops.object.modifier_apply(modifier=subsurf.name)
                except Exception as e:
                    logger.warning("Subsurf apply failed: %s", e)

            # --- Optimize ---
            if props.do_optimize:
                self._optimize_mesh(obj, context)

            # --- Pack UVs ---
            self._safe_mode_set('EDIT')
            try:
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.pack_islands(margin=0.001)
            except Exception:
                pass
            self._safe_mode_set('OBJECT')

            # --- Random UV ---
            if props.do_random_uv:
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                ZENV_MetalIngot_Utils.randomize_uvs(bm, rng)
                bm.to_mesh(obj.data)
                obj.data.update()
                bm.free()
                bm = None

            # --- Final weighted normal ---
            weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
            weighted_normal.mode = 'CORNER_ANGLE'
            weighted_normal.weight = 50
            weighted_normal.thresh = 0.01
            weighted_normal.keep_sharp = False
            try:
                bpy.ops.object.modifier_apply(modifier=weighted_normal.name)
            except Exception as e:
                logger.warning("Final weighted normal apply failed: %s", e)

            # Auto smooth (Blender 4.0 only - wrapped for forward compat)
            try:
                obj.data.use_auto_smooth = True
                obj.data.auto_smooth_angle = math.radians(60)
            except Exception:
                pass

            logger.info("Generated metal ingot: verts=%d, faces=%d",
                        len(obj.data.vertices), len(obj.data.polygons))
            self.report({'INFO'}, "Ingot generated (%d faces)" % len(obj.data.polygons))
            return {'FINISHED'}

        except Exception as e:
            logger.error("Error generating metal ingot: %s", e)
            self.report({'ERROR'}, "Ingot generation failed: %s" % e)
            # Cleanup BMesh on failure
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
            return {'CANCELLED'}

    def _optimize_mesh(self, obj, context):
        """Smart mesh optimization using planar decimation and triangulation."""
        try:
            self._safe_mode_set('OBJECT')
            context.view_layer.objects.active = obj
            obj.select_set(True)

            # Planar decimate
            decimate = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate.decimate_type = 'DISSOLVE'
            decimate.angle_limit = math.radians(1.0)
            decimate.use_dissolve_boundaries = False
            decimate.delimit = {'SHARP'}
            try:
                bpy.ops.object.modifier_apply(modifier="Decimate")
            except Exception as e:
                logger.warning("Decimate apply failed: %s", e)

            # Triangulate
            triangulate = obj.modifiers.new(name="Triangulate", type='TRIANGULATE')
            triangulate.quad_method = 'BEAUTY'
            triangulate.ngon_method = 'BEAUTY'
            try:
                bpy.ops.object.modifier_apply(modifier="Triangulate")
            except Exception as e:
                logger.warning("Triangulate apply failed: %s", e)

            # Weighted normal
            weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
            weighted_normal.mode = 'FACE_AREA'
            weighted_normal.weight = 50
            weighted_normal.thresh = 0.01
            weighted_normal.keep_sharp = False
            try:
                bpy.ops.object.modifier_apply(modifier="Weighted Normal")
            except Exception as e:
                logger.warning("Weighted normal apply failed: %s", e)

        except Exception as e:
            logger.error("Optimization failed: %s", e)

#endregion
#region PANEL
class ZENV_PT_MetalIngot(Panel):
    """Panel for metal ingot generation"""
    bl_label = "GEN Metal Ingot Generator"
    bl_idname = "ZENV_PT_MetalIngot"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_metal_ingot_props

        # Process control box
        proc_box = layout.box()
        proc_box.label(text="Process Steps", icon='MODIFIER')
        proc_box.prop(props, "do_bevel")
        proc_box.prop(props, "do_grid_cut")
        proc_box.prop(props, "do_micro_detail")
        proc_box.prop(props, "do_optimize")
        proc_box.prop(props, "do_random_uv")
        proc_box.prop(props, "do_subsurf")
        proc_box.prop(props, "random_seed")

        # Base shape settings
        shape_box = layout.box()
        shape_box.label(text="Base Shape", icon='MESH_CUBE')
        shape_box.prop(props, "length")
        shape_box.prop(props, "width")
        shape_box.prop(props, "height")
        shape_box.prop(props, "taper")
        shape_box.prop(props, "variation_scale")

        # Surface detail settings
        detail_box = layout.box()
        detail_box.label(text="Surface Detail", icon='FORCE_TURBULENCE')
        detail_box.prop(props, "detail_scale")
        detail_box.prop(props, "roughness")
        detail_box.prop(props, "bubble_density")

        # Grid settings
        if props.do_grid_cut:
            grid_box = layout.box()
            grid_box.label(text="Grid Settings", icon='MESH_GRID')
            grid_box.prop(props, "grid_size")

        # Bevel settings
        if props.do_bevel:
            bevel_box = layout.box()
            bevel_box.label(text="Bevel Settings", icon='MOD_BEVEL')
            bevel_box.prop(props, "bevel_width")
            bevel_box.prop(props, "bevel_segments")

        # Micro detail settings
        if props.do_micro_detail:
            micro_box = layout.box()
            micro_box.label(text="Micro Detail", icon='MOD_NOISE')
            micro_box.prop(props, "micro_detail")
            micro_box.prop(props, "micro_scale")

        # Generate button
        layout.operator(ZENV_OT_MetalIngot.bl_idname, icon='MOD_CAST')

#endregion
#region REG
classes = (
    ZENV_PG_MetalIngot,
    ZENV_OT_MetalIngot,
    ZENV_PT_MetalIngot,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_ingot_console_handler
    if _zenv_ingot_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_ingot_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_ingot_console_handler
    if _zenv_ingot_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_ingot_console_handler)
    except ValueError:
        pass
    _zenv_ingot_console_handler = None


def register():
    """Register all addon classes, scene property, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.zenv_metal_ingot_props = PointerProperty(type=ZENV_PG_MetalIngot)


def unregister():
    """Unregister all addon classes, remove scene property, and remove the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_metal_ingot_props"):
        delattr(bpy.types.Scene, "zenv_metal_ingot_props")
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
