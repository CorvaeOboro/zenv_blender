#region META
bl_info = {
    "name": 'MESH Wood Grain Generator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Realistic woodgrain using plane cuts and layered noise with inward crevices, zero-centered displacement.',
    "status": 'wip',
    "approved": False,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 50,
    "addon_order": 55,
    "location": 'View3D > ZENV',
    "tags": ['mesh', 'wood', 'grain', 'noise', 'displacement'],
    "description_short": 'Realistic woodgrain using plane cuts and layered noise.',
    "description_medium": 'Bisect-plane approach with multi-layer wood grain noise, '
                          'zero-centered displacement, and carved-in crevices.',
    "description_long": 'MESH Wood Grain Generator uses a bisect-plane approach with '
                        'multi-layer wood grain noise. Features radial rings, macro end '
                        'grain, fine detail, and longitudinal crevices. Zero-centered '
                        'displacement ensures symmetrical results. Optional vertex color '
                        'preview and smoothing passes.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}
#endregion

#region IMPORT
import bpy
import bmesh
import math
import logging
from mathutils import Vector, Matrix, Quaternion, noise
from bpy.props import (
    FloatProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region PROPS
class ZENV_PG_WoodGrainProps(PropertyGroup):
    """Properties for wood grain generation"""

    scale: FloatProperty(
        name="Pattern Scale",
        description="Overall scale of the ring/macro/fine patterns",
        default=1.0,
        min=0.1,
        max=10.0,
        subtype='DISTANCE'
    )
    strength: FloatProperty(
        name="Effect Strength",
        description="Final multiplier after zero-centering & clamping",
        default=1.0,
        min=0.0,
        max=5.0,
        precision=3
    )
    grid_density: FloatProperty(
        name="Grid Density",
        description="Distance between plane cuts on every axis (default 0.003 = 3 mm)",
        default=0.003,
        min=0.0001,
        max=0.1,
        precision=4,
        subtype='DISTANCE'
    )
    displacement_depth: FloatProperty(
        name="Displacement Depth",
        description="Maximum displacement distance in Blender units (meters). "
                    "Larger values produce deeper grooves/ridges.",
        default=0.02,
        min=0.0,
        max=0.5,
        precision=4,
        subtype='DISTANCE'
    )
    ring_scale: FloatProperty(
        name="Ring Scale",
        description="Scale factor for radial ring frequencies",
        default=0.1,
        min=0.01,
        max=5.0
    )
    distortion: FloatProperty(
        name="Grain Distortion",
        description="Swirl/knot intensity + macro wave amplitude + partial crevice factor",
        default=2.0,
        min=0.0,
        max=10.0
    )
    variation: FloatProperty(
        name="Pattern Variation",
        description="Variation factor to reduce repetition",
        default=0.2,
        min=0.0,
        max=1.0
    )
    grain_direction: FloatVectorProperty(
        name="Grain Direction",
        description="Custom direction if auto_direction is off ",
        default=(0.0, 0.0, 1.0),
        subtype='DIRECTION'
    )
    auto_direction: BoolProperty(
        name="Auto Detect Direction",
        description="Use the mesh's longest dimension as the 'length' of the wood",
        default=True
    )
    use_normal: BoolProperty(
        name="Use Normal",
        description="Displace along each vertex's normal instead of local Z",
        default=True
    )
    visualize_colors: BoolProperty(
        name="Vertex Color Preview",
        description="Store a color gradient representing displacement magnitude after final clamp",
        default=False
    )
    do_smoothing: BoolProperty(
        name="Smooth After Cuts",
        description="Light smoothing pass to reduce seam artifacts from many plane cuts",
        default=True
    )

    # Crevice-specific properties
    crevice_scale: FloatProperty(
        name="Crevice Pattern Scale",
        description="Pattern size for elongated lines in X/Y Larger => fewer lines, smaller => more lines",
        default=0.02,
        min=0.001,
        max=50.0
    )
    crevice_contrast: FloatProperty(
        name="Crevice Contrast",
        description="Exponent to sharpen or thin out the lines",
        default=4.0,
        min=0.0,
        max=10.0
    )
    crevice_strength: FloatProperty(
        name="Crevice Strength",
        description="Amplitude of the carved lines effect (negative = inward grooves)",
        default=-0.3,
        min=-5.0,
        max=5.0
    )
#endregion

#region NOISE
class ZENV_WoodGrainNoise:
    """
    Functions for multiple noise layers combined into a final displacement:
      - radial rings
      - macro end grain
      - fine detail
      - long crevices (inward)
    We then zero-center the sum so there's both positive & negative from the surface.
    """

    #region ALIGN
    @staticmethod
    def rotation_matrix_from_vector(from_vec: Vector, to_vec: Vector) -> Matrix:
        """
        Returns a 4x4 matrix rotating from 'from_vec' to 'to_vec'.
        Returns identity if either vector is zero-length (review (section)4.3).
        """
        if from_vec.length < 1e-8 or to_vec.length < 1e-8:
            return Matrix.Identity(4)
        f = from_vec.normalized()
        t = to_vec.normalized()
        if (f - t).length < 1e-8:
            return Matrix.Identity(4)
        if (f + t).length < 1e-8:
            perp = f.cross(Vector((1,0,0)))
            if perp.length < 1e-6:
                perp = f.cross(Vector((0,1,0)))
            perp.normalize()
            q = Quaternion(perp, math.pi)
            return q.to_matrix().to_4x4()

        q = f.rotation_difference(t)
        return q.to_matrix().to_4x4()
    #endregion

    #region SWIRL
    @staticmethod
    def swirl_knot_transform(x, y, z, swirl_strength):
        """
        Swirl (x, y) for knot-like distortions.
        """
        swirl_angle = swirl_strength * noise.noise((x*0.5, y*0.5, z*0.5))
        cos_a = math.cos(swirl_angle)
        sin_a = math.sin(swirl_angle)
        sx = x*cos_a - y*sin_a
        sy = x*sin_a + y*cos_a
        return sx, sy
    #endregion

    #region RINGS
    @staticmethod
    def radial_rings(aligned_pos, ring_scale, swirl_strength=0.3):
        """
        Radial ring pattern from the center (Z axis) plus minor swirl & noise.
        Returns ~ [-1..1].
        """
        x, y, z = aligned_pos
        sx, sy = ZENV_WoodGrainNoise.swirl_knot_transform(x, y, z, swirl_strength)
        radial = math.sqrt(sx*sx + sy*sy)

        rings = math.sin(ring_scale * radial * 2.0)
        # break up perfect circles
        rings += noise.noise((sx*0.5, sy*0.5, z*0.5)) * 0.3
        return rings  # in ~ [-1..1]
    #endregion

    #region MACRO
    @staticmethod
    def macro_end_grain(aligned_pos, board_z_min, board_z_max, amplitude=1.0):
        """
        Large-scale wave near the ends of the board. ~ [-amplitude..+amplitude]
        """
        x, y, z = aligned_pos
        z_range = board_z_max - board_z_min
        if abs(z_range) < 1e-6:
            return 0.0

        z_norm = (z - board_z_min) / z_range
        dist_from_center = abs(z_norm - 0.5) * 2.0
        end_factor = 1.0 - dist_from_center

        big_noise = noise.noise((x*0.3, y*0.3, z*0.1))
        return big_noise * end_factor * amplitude  # ~ [-ampl..+ampl]
    #endregion

    #region FINE
    @staticmethod
    def fine_grain_detail(aligned_pos, amplitude=0.3):
        """
        Higher-frequency small-scale noise for micro-detail. ~ [-ampl..+ampl]
        """
        x, y, z = aligned_pos
        detail = noise.noise((x*5.0, y*5.0, z*5.0))
        return detail * amplitude  # ~ [-0.3..+0.3]
    #endregion

    #region CREVICE
    @staticmethod
    def longitudinal_crevices(aligned_pos, pattern_scale=5.0, contrast=3.0, amplitude=0.5):
        """
        Creates thin, elongated lines along Z by scaling X/Y and
        applying a contrast curve. Forces lines inward (negative).
        Range is about [-amplitude..0].
        """
        x, y, z = aligned_pos

        # interpret pattern_scale as "repeat distance"
        freq = 1.0 / max(pattern_scale, 1e-6)
        xx = x * freq
        yy = y * freq

        # Basic 3D noise in [-1..1]
        n = noise.noise((xx, yy, z*0.52))

        # Shift from [-1..1] to [0..1], clamped to avoid float edge issues
        # with non-integer exponents (review (section)4.4)
        n_01 = max(0.0, min(1.0, (n + 1.0) * 0.5))

        # Contrast curve
        cval = n_01**contrast

        # Shift back to [-1..+1]
        cval2 = (cval * 2.0) - 1.0

        # Force negative => carve inward
        cval2 = -abs(cval2)

        return cval2 * amplitude  # in ~ [-amplitude..0]
    #endregion

    #region COMBINE
    @staticmethod
    def combined_wood_displacement(
        local_pos, grain_dir,
        scale, variation, ring_scale, distortion,
        z_min, z_max,
        crevice_scale=5.0,
        crevice_contrast=3.0,
        crevice_strength=0.5
    ):
        """
        Summation of the 4 noise layers, each with a smaller amplitude so they
        don't overshadow each other. Then we do a final zero-centering in a
        second pass (outside this function).
        """
        # 1) Align so that 'grain_dir' is local Z
        align_mat = ZENV_WoodGrainNoise.rotation_matrix_from_vector(Vector((0,0,1)), grain_dir)
        inv_align = align_mat.inverted()

        # 2) Scale the coordinate (global scale for ring/macro/fine layers)
        scaled_pos = local_pos * scale
        aligned = inv_align @ scaled_pos
        ax, ay, az = aligned

        # Evaluate layers; apply smaller weighting so the sum stays in a moderate range
        # You can adjust these if you want more or less influence:
        ring_val   = ZENV_WoodGrainNoise.radial_rings(aligned, ring_scale, swirl_strength=distortion*0.3) * 0.4
        macro_val  = ZENV_WoodGrainNoise.macro_end_grain(aligned, z_min, z_max, amplitude=0.3*distortion)
        fine_val   = ZENV_WoodGrainNoise.fine_grain_detail(aligned, amplitude=0.2)
        crev_val   = ZENV_WoodGrainNoise.longitudinal_crevices(
            aligned,
            pattern_scale=crevice_scale,
            contrast=crevice_contrast,
            amplitude=crevice_strength * distortion
        )

        combined = ring_val + macro_val + fine_val + crev_val

        # Variation noise => scale final
        var_n = noise.noise(local_pos * variation)
        combined *= (1.0 + var_n*0.2)

        return combined  # Unclamped for now; we'll do final clamp & shift outside.
    #endregion
#endregion

#region UTILS
class ZENV_WoodGrainUtils:
    """
    Mesh utility and plane cut code plus bounding box logic.
    """

    @staticmethod
    def get_bounds_and_longest_axis(bm):
        """
        Returns (bounds_min, bounds_max, longest_axis_index).
        """
        min_v = Vector((min(v.co.x for v in bm.verts),
                        min(v.co.y for v in bm.verts),
                        min(v.co.z for v in bm.verts)))
        max_v = Vector((max(v.co.x for v in bm.verts),
                        max(v.co.y for v in bm.verts),
                        max(v.co.z for v in bm.verts)))
        dims = max_v - min_v
        axis_idx = max(range(3), key=lambda i: dims[i])
        return min_v, max_v, axis_idx

    @staticmethod
    def clamp_slices(slice_positions, max_slices=250):
        """If slice_positions is too large, pick an evenly spaced subset."""
        if len(slice_positions) > max_slices:
            step = len(slice_positions) / float(max_slices)
            slice_positions = [
                slice_positions[int(i * step)] for i in range(max_slices)
            ]
        return slice_positions

    @staticmethod
    def create_cut_positions(bounds_min, bounds_max, density, grain_axis_idx):
        """
        Create lists of plane positions for each axis, clamped to max_slices.
        All three axes are subdivided so that wide faces receive an internal
        vertex grid — this is required for grooves to form across the face of
        a board, not just along its perimeter.
        """
        all_positions = [[], [], []]
        max_slices_per_axis = 250

        for axis in range(3):
            min_a = bounds_min[axis]
            max_a = bounds_max[axis]
            step = density

            pos_list = []
            current = min_a
            while current <= (max_a + 1e-8):
                pos_list.append(current)
                current += step

            # clamp
            pos_list = ZENV_WoodGrainUtils.clamp_slices(pos_list, max_slices=max_slices_per_axis)
            all_positions[axis] = pos_list

        return all_positions
#endregion

#region OP
class ZENV_OT_WoodGrain(Operator):
    """Apply multi-layer woodgrain pattern with inward crevices, zero-centered displacement."""
    bl_idname = "zenv.wood_grain"
    bl_label = "Apply Wood Grain"
    bl_options = {'REGISTER', 'UNDO'}

    #region POLL
    @classmethod
    def poll(cls, context):
        # Always available - if no mesh is active, execute() creates a
        # default example board and applies the wood grain to it.
        return context.scene is not None
    #endregion

    #region HELPERS
    @staticmethod
    def _create_default_board(context):
        """Create a default example 2x4-like board and make it active/selected.

        Dimensions are in Blender meters: ~1.5m long (X), ~0.1m wide (Y),
        ~0.05m tall (Z) - a nominal 2x4 profile oriented along X so the
        auto-detected grain direction runs the length of the board.
        """
        import bpy
        length = 1.5
        width = 0.1
        height = 0.05
        # Centered at origin.
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        board = context.active_object
        board.name = "WoodGrain_ExampleBoard"
        board.scale = (length, width, height)
        # Apply scale so the operator's transform_apply + bounds logic
        # sees the real world-space dimensions.
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return board
    #endregion

    #region EXEC
    def execute(self, context):
        props = context.scene.zenv_wood_props
        obj = context.active_object

        # No active mesh -> create a default example 2x4 board so the
        # operator is always usable.  Dimensions are in Blender meters:
        # ~1.5m long, ~0.1m wide, ~0.05m tall (a nominal 2x4 profile).
        if not obj or obj.type != 'MESH':
            obj = self._create_default_board(context)
            self.report({'INFO'}, f"No mesh selected - created default board '{obj.name}'.")
            logger.info(f"Created default example board: {obj.name}")

        logger.info("=== Starting Wood Grain Generation (Bisect Planes) ===")
        logger.info(f"Object: {obj.name}")

        # Save mode for restoration in finally (review (section)2.3)
        original_mode = obj.mode
        bm = None

        try:
            #region INIT
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Create bmesh
            me = obj.data
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            # Determine grain_dir
            bounds_min, bounds_max, auto_axis = ZENV_WoodGrainUtils.get_bounds_and_longest_axis(bm)
            if props.auto_direction:
                grain_dir = Vector((0,0,0))
                grain_dir[auto_axis] = 1.0
            else:
                grain_dir = Vector(props.grain_direction)
                # Fall back to auto-detection if user direction is zero-length
                # (review (section)4.2)
                if grain_dir.length < 1e-6:
                    grain_dir = Vector((0,0,0))
                    grain_dir[auto_axis] = 1.0
                    logger.warning("grain_direction is zero-length; falling back to auto-detection")
                else:
                    grain_dir = grain_dir.normalized()

            logger.info(f"   Grain Dir: {grain_dir}")
            logger.info(f"   Bounds Min: {bounds_min}, Max: {bounds_max}")
            #endregion

            #region BISECT
            # Create cut positions - only along the grain axis (review (section)3.1/(section)3.2)
            cut_positions = ZENV_WoodGrainUtils.create_cut_positions(
                bounds_min, bounds_max, props.grid_density, auto_axis
            )

            # Plane cuts
            axis_normals = [Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1))]
            for axis_idx, positions in enumerate(cut_positions):
                plane_no = axis_normals[axis_idx]
                for pos in positions:
                    plane_co = Vector((0,0,0))
                    plane_co[axis_idx] = pos
                    try:
                        bmesh.ops.bisect_plane(
                            bm,
                            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                            plane_co=plane_co,
                            plane_no=plane_no,
                            clear_outer=False,
                            clear_inner=False
                        )
                    except Exception as e:
                        logger.error(f"Bisect error: {e}")
            #endregion

            #region SMOOTH
            # Optionally smooth after all cuts
            if props.do_smoothing:
                try:
                    bmesh.ops.smooth_vert(
                        bm,
                        verts=bm.verts,
                        factor=0.5,
                        use_axis_x=True,
                        use_axis_y=True,
                        use_axis_z=True
                    )
                except Exception as e:
                    logger.warning(f"Smoothing failed (skipped): {e}")
            #endregion

            #region DISPLACE
            # Precompute alignment matrix once (review (section)3.5)
            align_mat = ZENV_WoodGrainNoise.rotation_matrix_from_vector(Vector((0,0,1)), grain_dir)
            inv_align = align_mat.inverted()

            min_aligned = inv_align @ (bounds_min * props.scale)
            max_aligned = inv_align @ (bounds_max * props.scale)
            z_min = min(min_aligned.z, max_aligned.z)
            z_max = max(min_aligned.z, max_aligned.z)

            # PASS 1: gather combined, unshifted displacement
            disp_map = {}
            for v in bm.verts:
                disp_raw = ZENV_WoodGrainNoise.combined_wood_displacement(
                    v.co, grain_dir,
                    props.scale,
                    props.variation,
                    props.ring_scale,
                    props.distortion,
                    z_min,
                    z_max,
                    props.crevice_scale,
                    props.crevice_contrast,
                    props.crevice_strength
                )
                disp_map[v] = disp_raw

            # zero-center approach:
            # find average, subtract from all => symmetrical around 0
            avg_val = sum(disp_map.values()) / len(disp_map) if disp_map else 0.0
            logger.info(f"   Average raw displacement = {avg_val:.4f}")

            # compute min/max after subtracting average, to clamp [-1..1]
            min_disp = float('inf')
            max_disp = float('-inf')
            for v in bm.verts:
                shifted = disp_map[v] - avg_val
                if shifted < min_disp:
                    min_disp = shifted
                if shifted > max_disp:
                    max_disp = shifted

            logger.info(f"   Range after shift: [{min_disp:.4f}, {max_disp:.4f}]")

            final_min = -1.0
            final_max = 1.0
            final_depth = props.displacement_depth

            # PASS 2: apply final displacement per VERTEX (not per loop!)
            # The old code iterated over faces/loops, which applied displacement
            # N times per vertex (once per adjacent face), causing compounding
            # (review (section)2.1).
            color_layer = None
            if props.visualize_colors:
                color_layer = bm.loops.layers.color.get("WoodGrain")
                if not color_layer:
                    color_layer = bm.loops.layers.color.new("WoodGrain")
            else:
                # Remove stale vertex color layer from previous runs (review (section)3.10)
                stale = bm.loops.layers.color.get("WoodGrain")
                if stale:
                    bm.loops.layers.color.remove(stale)

            # We'll track final min/max for logging
            final_used_min = float('inf')
            final_used_max = float('-inf')

            # Compute clamped displacement per vertex and apply once
            clamped_map = {}
            for v in bm.verts:
                shifted = disp_map[v] - avg_val
                # clamp to [-1..1]
                clamped = max(final_min, min(shifted, final_max))
                clamped_map[v] = clamped
                # multiply by final depth
                disp_val = clamped * final_depth * props.strength

                # apply
                if props.use_normal:
                    v.co += v.normal * disp_val
                else:
                    v.co.z += disp_val

                if disp_val < final_used_min:
                    final_used_min = disp_val
                if disp_val > final_used_max:
                    final_used_max = disp_val
            #endregion

            #region COLOR
            # Separate color pass - per loop, reads pre-computed clamped values
            if color_layer:
                for face in bm.faces:
                    for loop in face.loops:
                        v = loop.vert
                        clamped = clamped_map[v]
                        denom = (final_max - final_min) if (final_max != final_min) else 1e-8
                        color_norm = (clamped - final_min) / denom
                        # woodish gradient
                        r = color_norm
                        g = color_norm * 0.7
                        b = color_norm * 0.4
                        loop[color_layer] = (r, g, b, 1.0)
            #endregion

            #region MESH
            bm.to_mesh(me)
            bm.free()
            bm = None  # mark as freed so finally doesn't double-free
            me.update()
            #endregion

            #region MATERIAL
            # optional material with vertex color
            if props.visualize_colors:
                mat_name = "WoodGrainVCol_Mat"
                if mat_name not in bpy.data.materials:
                    mat = bpy.data.materials.new(mat_name)
                    mat.use_nodes = True
                    nt = mat.node_tree
                    nt.nodes.clear()

                    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
                    out_node.location = (300,0)

                    princ_node = nt.nodes.new("ShaderNodeBsdfPrincipled")
                    princ_node.location = (0,0)

                    attr_node = nt.nodes.new("ShaderNodeAttribute")
                    attr_node.location = (-300,0)
                    attr_node.attribute_name = "WoodGrain"

                    nt.links.new(attr_node.outputs["Color"], princ_node.inputs["Base Color"])
                    nt.links.new(princ_node.outputs["BSDF"], out_node.inputs["Surface"])
                else:
                    mat = bpy.data.materials[mat_name]

                # assign to object if not already
                if not obj.data.materials or mat.name not in [m.name for m in obj.data.materials]:
                    obj.data.materials.append(mat)
            #endregion

            logger.info(f"Final used displacement range: [{final_used_min:.6f}, {final_used_max:.6f}]")
            logger.info("=== Wood Grain Generation Complete ===")

            return {'FINISHED'}

        #region EXCEPT
        except Exception as e:
            logger.error(f"Wood grain generation failed: {e}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        #endregion

        #region FINALLY
        finally:
            # Free BMesh if still allocated (review (section)2.3)
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
            # Restore original mode (review (section)2.3)
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                pass
        #endregion
    #endregion
#endregion

#region PANEL
class ZENV_PT_WoodGrainPanel(Panel):
    """Panel for wood grain settings"""
    bl_label = "MESH Wood Grain Generator"
    bl_idname = "ZENV_PT_wood_grain_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        # Always show in the ZENV sidebar so the panel is visible even when
        # no object is selected. The operator's own poll greys out the button
        # when no active mesh is available.
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_wood_props

        col = layout.column(align=True)
        col.prop(props, "scale")
        col.prop(props, "strength")
        col.prop(props, "displacement_depth")
        col.prop(props, "grid_density")
        col.prop(props, "ring_scale")
        col.prop(props, "distortion")
        col.prop(props, "variation")

        col.separator()
        col.label(text="Long Crevices:")
        col.prop(props, "crevice_scale")
        col.prop(props, "crevice_contrast")
        col.prop(props, "crevice_strength")

        col.separator()
        col.prop(props, "use_normal")
        col.prop(props, "visualize_colors")
        col.prop(props, "do_smoothing")

        box = layout.box()
        box.prop(props, "auto_direction")
        if not props.auto_direction:
            box.prop(props, "grain_direction")

        layout.operator("zenv.wood_grain", icon='MOD_WAVE')
#endregion

#region REGISTER
classes = (
    ZENV_PG_WoodGrainProps,
    ZENV_OT_WoodGrain,
    ZENV_PT_WoodGrainPanel
)

def register():
    _install_logger()
    # Remove any stale Scene property first so the PropertyGroup class can
    # be cleanly re-registered after importlib.reload (e.g. via the Addon
    # Manager).  Without this, the old class stays registered and the new
    # one is silently skipped, leaving the panel to crash in draw().
    if hasattr(bpy.types.Scene, 'zenv_wood_props'):
        delattr(bpy.types.Scene, 'zenv_wood_props')
    for c in classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass
    bpy.types.Scene.zenv_wood_props = PointerProperty(type=ZENV_PG_WoodGrainProps)

def unregister():
    # Delete the Scene PointerProperty BEFORE unregistering the
    # PropertyGroup class — Blender refuses to unregister a class that is
    # still referenced by an active property, and the resulting RuntimeError
    # would leave the old class stuck in RNA.
    if hasattr(bpy.types.Scene, 'zenv_wood_props'):
        delattr(bpy.types.Scene, 'zenv_wood_props')
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except RuntimeError:
            pass
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
