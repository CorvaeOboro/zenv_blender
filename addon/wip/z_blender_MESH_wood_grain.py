"""
MESH Wood Grain Generator - Bisect-plane approach
with multi-layer wood grain noise, zero-centered displacement,
and carved-in crevices.
"""

bl_info = {
    "name": "MESH Wood Grain Generator",
    "author": "CorvaeOboro",
    "version": (1, 5),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Realistic woodgrain using plane cuts and layered noise with inward crevices, zero-centered displacement.",
    "category": "ZENV",
}

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
logger.setLevel(logging.DEBUG)


# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

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
        description="Distance between plane cuts (e.g. 0.005 for 5 mm)",
        default=0.003,
        min=0.0001,
        max=0.1,
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
        description="Custom direction if auto_direction is off (e.g. 0,0,1)",
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
        description="Pattern size for elongated lines in X/Y (default 5.0). Larger => fewer lines, smaller => more lines",
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
        description="Amplitude of the carved lines effect (they push inward)",
        default=-0.1,
        min=-5.0,
        max=5.0
    )


# ------------------------------------------------------------------------
#    Multi-Layer Woodgrain Noise
# ------------------------------------------------------------------------

class ZENV_WoodGrainNoise:
    """
    Functions for multiple noise layers combined into a final displacement:
      - radial rings
      - macro end grain
      - fine detail
      - long crevices (inward)
    We then zero-center the sum so there's both positive & negative from the surface.
    """

    @staticmethod
    def rotation_matrix_from_vector(from_vec: Vector, to_vec: Vector) -> Matrix:
        """
        Returns a 4x4 matrix rotating from 'from_vec' to 'to_vec'.
        """
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

    @staticmethod
    def fine_grain_detail(aligned_pos, amplitude=0.3):
        """
        Higher-frequency small-scale noise for micro-detail. ~ [-ampl..+ampl]
        """
        x, y, z = aligned_pos
        detail = noise.noise((x*5.0, y*5.0, z*5.0))
        return detail * amplitude  # ~ [-0.3..+0.3]

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

        # Shift from [-1..1] to [0..1]
        n_01 = (n + 1.0)*0.5

        # Contrast curve
        cval = n_01**contrast

        # Shift back to [-1..+1]
        cval2 = (cval * 2.0) - 1.0

        # Force negative => carve inward
        cval2 = -abs(cval2)

        return cval2 * amplitude  # in ~ [-amplitude..0]

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

# ------------------------------------------------------------------------
#    Mesh Utility Functions
# ------------------------------------------------------------------------

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
        """
        all_positions = []
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
            all_positions.append(pos_list)

        return all_positions

# ------------------------------------------------------------------------
#    Main Operator
# ------------------------------------------------------------------------

class ZENV_OT_WoodGrain(Operator):
    """Apply multi-layer woodgrain pattern with inward crevices, zero-centered displacement."""
    bl_idname = "zenv.wood_grain"
    bl_label = "Apply Wood Grain"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.zenv_wood_props
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object.")
            return {'CANCELLED'}

        logger.info("=== Starting Wood Grain Generation (Bisect Planes) ===")
        logger.info(f"Object: {obj.name}")

        # Save mode, apply scale
        original_mode = obj.mode
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
            grain_dir = Vector(props.grain_direction).normalized()

        logger.info(f"   Grain Dir: {grain_dir}")
        logger.info(f"   Bounds Min: {bounds_min}, Max: {bounds_max}")

        # Create cut positions
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
                logger.error(f"Smoothing error: {e}")

        # Precompute z_min, z_max in aligned space for macro_end_grain layer
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
        all_values = disp_map.values()
        avg_val = sum(all_values)/len(all_values) if all_values else 0.0
        logger.info(f"   Average raw displacement = {avg_val:.4f}")

        # compute min/max after subtracting average, to clamp [-1..1]
        # We'll do a second pass
        min_disp = float('inf')
        max_disp = float('-inf')
        for v in bm.verts:
            shifted = disp_map[v] - avg_val
            if shifted < min_disp:
                min_disp = shifted
            if shifted > max_disp:
                max_disp = shifted

        logger.info(f"   Range after shift: [{min_disp:.4f}, {max_disp:.4f}]")

        # clamp to [-1..1], then apply final depth=0.01 for example
        # But let's keep the code consistent with previous approach (0.008).
        # We'll do final multiply by user Strength too.
        final_min = -1.0
        final_max = 1.0
        final_depth = 0.008

        # PASS 2: apply final displacement + color
        color_layer = None
        if props.visualize_colors:
            color_layer = bm.loops.layers.color.get("WoodGrain")
            if not color_layer:
                color_layer = bm.loops.layers.color.new("WoodGrain")

        # We'll track final min/max for logging
        final_used_min = float('inf')
        final_used_max = float('-inf')

        for face in bm.faces:
            for loop in face.loops:
                v = loop.vert
                shifted = disp_map[v] - avg_val
                # clamp to [-1..1]
                clamped = max(final_min, min(shifted, final_max))
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

                # color
                if color_layer:
                    # map disp_val from [final_min..final_max]*depth*strength to [0..1]
                    #  but simpler is: normalized = (clamped - final_min)/(final_max - final_min)
                    #  ignoring the earlier multiplication by final_depth * strength
                    denom = (final_max - final_min) if (final_max != final_min) else 1e-8
                    color_norm = (clamped - final_min) / denom
                    # woodish gradient
                    r = color_norm
                    g = color_norm * 0.7
                    b = color_norm * 0.4
                    loop[color_layer] = (r, g, b, 1.0)

        bm.to_mesh(me)
        bm.free()
        me.update()

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

        # restore mode
        bpy.ops.object.mode_set(mode=original_mode)

        logger.info(f"Final used displacement range: [{final_used_min:.6f}, {final_used_max:.6f}]")
        logger.info("=== Wood Grain Generation Complete ===")

        return {'FINISHED'}


# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_WoodGrainPanel(Panel):
    """Panel for wood grain settings"""
    bl_label = "Wood Grain Generator"
    bl_idname = "ZENV_PT_wood_grain_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_wood_props

        col = layout.column(align=True)
        col.prop(props, "scale")
        col.prop(props, "strength")
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


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_WoodGrainProps,
    ZENV_OT_WoodGrain,
    ZENV_PT_WoodGrainPanel
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.zenv_wood_props = PointerProperty(type=ZENV_PG_WoodGrainProps)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.zenv_wood_props

if __name__ == "__main__":
    register()
