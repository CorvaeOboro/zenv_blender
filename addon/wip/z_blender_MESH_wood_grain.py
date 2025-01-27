"""
MESH Wood Grain Generator - Bisect-plane approach with improved radial/noise displacement
and optional vertex-color material assignment.
"""

bl_info = {
    "name": "MESH Wood Grain Generator",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Realistic woodgrain using plane cuts, radial rings, knots, and distortions.",
    "category": "ZENV",
}

import bpy
import bmesh
import math
import logging
from mathutils import Vector, Matrix, Quaternion, noise
from bpy.props import (
    FloatProperty,
    EnumProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Woodgrain Noise (Radial + Knots)
# ------------------------------------------------------------------------

class ZENV_WoodGrainUtils:
    """Utility functions for wood grain generation"""

    @staticmethod
    def rotation_matrix_from_vector(from_vec: Vector, to_vec: Vector) -> Matrix:
        """
        Returns a 4x4 Matrix that rotates from 'from_vec' to 'to_vec'.
        Both vectors should be non-zero.
        """
        f = from_vec.normalized()
        t = to_vec.normalized()

        # If nearly identical, identity
        if (f - t).length < 1e-8:
            return Matrix.Identity(4)

        # If nearly opposite, 180° rotation about any perpendicular
        if (f + t).length < 1e-8:
            perp_axis = f.cross(Vector((1, 0, 0)))
            if perp_axis.length < 1e-6:
                perp_axis = f.cross(Vector((0, 1, 0)))
            perp_axis.normalize()
            q = Quaternion(perp_axis, math.pi)
            return q.to_matrix().to_4x4()

        # Otherwise use rotation_difference
        q = f.rotation_difference(t)
        return q.to_matrix().to_4x4()

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
        """
        If slice_positions is too large, pick an evenly spaced subset.
        """
        if len(slice_positions) > max_slices:
            step = len(slice_positions) / float(max_slices)
            slice_positions = [
                slice_positions[int(i * step)] for i in range(max_slices)
            ]
        return slice_positions

    @staticmethod
    def create_cut_positions(bounds_min, bounds_max, density, grain_axis_idx):
        """
        Create lists of plane positions for each axis. 
        If this axis is the 'grain axis', we can reduce or increase cuts if desired.
        Right now we do uniform cuts but clamp them at max_slices.
        """
        all_positions = []
        max_slices_per_axis = 250

        dims = bounds_max - bounds_min

        for axis in range(3):
            min_a = bounds_min[axis]
            max_a = bounds_max[axis]

            step = density
            # (Optionally you could do half density along the grain axis if you prefer.)
            # if axis == grain_axis_idx:
            #     step *= 0.5

            pos_list = []
            current = min_a
            while current <= (max_a + 1e-8):
                pos_list.append(current)
                current += step

            # clamp
            pos_list = ZENV_WoodGrainUtils.clamp_slices(pos_list, max_slices=max_slices_per_axis)
            all_positions.append(pos_list)

        return all_positions

    @staticmethod
    def radial_wood_displacement(local_pos, grain_dir, scale, variation, ring_scale, distortion):
        """
        Creates a radial ring pattern around the local Z-axis (grain_dir).
        1) Rotate so that 'grain_dir' is local Z.
        2) radial = sqrt(x^2 + y^2)
        3) rings = some sine or fract pattern with added swirl/knot noise
        4) final displacement is positive or negative, but we keep it small negative
           so the user sees some "indentation" for ring lines. 
        """

        # 1) Build matrix that rotates from Z -> grain_dir, then invert to transform
        # local_pos so that grain_dir becomes the Z axis in our "aligned" space.
        align_mat = ZENV_WoodGrainUtils.rotation_matrix_from_vector(Vector((0, 0, 1)), grain_dir)
        inv_mat = align_mat.inverted()

        # 2) scale the coordinate for overall pattern size
        scaled_pos = local_pos * scale
        # 3) transform so grain_dir acts as Z
        aligned = inv_mat @ scaled_pos

        # 4) radial distance in the XY plane (since Z is "length" of the log)
        x, y, z = aligned
        radial = math.sqrt(x * x + y * y)

        # Introduce swirl for knots:
        # swirl angle from noise
        swirl_angle = distortion * 0.3 * noise.noise((x*0.5, y*0.5, z*0.5))
        # rotate (x,y) by swirl_angle around origin to simulate swirling grain
        cos_a = math.cos(swirl_angle)
        sin_a = math.sin(swirl_angle)
        swirl_x = x * cos_a - y * sin_a
        swirl_y = x * sin_a + y * cos_a
        radial_swirl = math.sqrt(swirl_x * swirl_x + swirl_y * swirl_y)

        # 5) ring pattern along radial
        # e.g. ring = sin(ring_scale * radial_swirl + additional 3D noise).
        base_rings = math.sin(ring_scale * radial_swirl * 2.0)
        # add 3D noise to break up the ring
        ring_noise = noise.noise((swirl_x, swirl_y, z)) * distortion * 0.5
        ring_val = base_rings + ring_noise

        # Oak-like depth settings (deep pronounced grain)
        depth = 0.008

        # 7) Variation to avoid repeating pattern
        # use the unaligned local_pos to avoid large scale repetition
        var_n = noise.noise(local_pos * variation)  
        ring_val *= (1.0 + var_n * 0.2)

        # 8) final value
        # Typically ring_val is in [-1..1]; we want some negative dips and positive ridges
        # but not huge. We'll clamp slightly to avoid massive inversions:
        ring_val = max(-1.0, min(ring_val, 1.0))
        return ring_val * depth


# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

class ZENV_PG_WoodGrainProps(PropertyGroup):
    """Properties for wood grain generation"""
    scale: FloatProperty(
        name="Pattern Scale",
        description="Overall scale of the wood grain pattern",
        default=1.0,
        min=0.1,
        max=10.0,
        subtype='DISTANCE'
    )
    strength: FloatProperty(
        name="Effect Strength",
        description="Multiplier for ring depth/displacement",
        default=1.0,
        min=0.0,
        max=5.0,
        precision=3
    )
    grid_density: FloatProperty(
        name="Grid Density",
        description="Distance between plane cuts (e.g. 0.005 for 5 mm)",
        default=0.005,
        min=0.0001,
        max=0.1,
        precision=4,
        subtype='DISTANCE'
    )
    ring_scale: FloatProperty(
        name="Ring Scale",
        description="Scale of annual growth rings",
        default=1.0,
        min=0.1,
        max=5.0
    )
    distortion: FloatProperty(
        name="Grain Distortion",
        description="Amount of knots/swirl in the grain",
        default=0.5,
        min=0.0,
        max=2.0
    )
    variation: FloatProperty(
        name="Pattern Variation",
        description="Variation factor for ring repetition",
        default=0.2,
        min=0.0,
        max=1.0
    )
    grain_direction: FloatVectorProperty(
        name="Grain Direction",
        description="Custom direction if auto_direction is off; e.g. (0,0,1)",
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
        description="Store a color gradient representing displacement magnitude",
        default=False
    )
    do_smoothing: BoolProperty(
        name="Smooth After Cuts",
        description="Light smoothing pass to reduce seam artifacts from many plane cuts",
        default=True
    )


# ------------------------------------------------------------------------
#    Main Operator
# ------------------------------------------------------------------------

class ZENV_OT_WoodGrain(Operator):
    """Apply radial woodgrain pattern using axis-aligned bisect planes."""
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

        # Initialize displacement tracking variables
        min_disp = float('inf')
        max_disp = float('-inf')
        displacement_values = {}

        # Create bmesh
        me = obj.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Figure out bounds and auto or custom grain direction
        bounds_min, bounds_max, auto_axis = ZENV_WoodGrainUtils.get_bounds_and_longest_axis(bm)
        if props.auto_direction:
            grain_dir = Vector((0,0,0))
            grain_dir[auto_axis] = 1.0
        else:
            grain_dir = props.grain_direction.normalized()

        logger.info(f"   Using grain_dir={grain_dir}")

        # Build cut positions
        cut_positions = ZENV_WoodGrainUtils.create_cut_positions(bounds_min, bounds_max, props.grid_density, auto_axis)

        # Create color attribute layer for preview
        color_layer = None
        if props.visualize_colors:
            color_layer = bm.loops.layers.color.new("WoodGrain")

        # Do plane cuts
        axis_normals = [Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1))]

        # For each axis
        for axis_idx, positions in enumerate(cut_positions):
            axis_normal = axis_normals[axis_idx]
            logger.info(f"   Cutting axis {axis_idx} with {len(positions)} positions")

            # For each cut position along this axis
            for pos in positions:
                # Create plane at this position
                plane_co = Vector((0,0,0))
                plane_co[axis_idx] = pos
                plane_no = axis_normal

                # Do the cut
                try:
                    ret = bmesh.ops.bisect_plane(
                        bm,
                        geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                        plane_co=plane_co,
                        plane_no=plane_no,
                        clear_outer=False,
                        clear_inner=False
                    )
                except Exception as e:
                    logger.error(f"Error during bisect: {str(e)}")
                    continue

        # Now apply displacement to all vertices
        for v in bm.verts:
            # Get local position
            local_pos = v.co

            # Get displacement value
            disp_val = ZENV_WoodGrainUtils.radial_wood_displacement(
                local_pos,
                grain_dir,
                props.scale,
                props.variation,
                props.ring_scale,
                props.distortion
            )

            # Track displacement values for color visualization
            displacement_values[v] = disp_val
            min_disp = min(min_disp, disp_val)
            max_disp = max(max_disp, disp_val)

            # Apply displacement
            if props.use_normal:
                disp_dir = v.normal
            else:
                disp_dir = Vector((0, 0, 1))

            v.co += disp_dir * (disp_val * props.strength)

        # Log displacement range
        logger.info(f"Displacement range: [{min_disp:.6f}, {max_disp:.6f}]")

        # Apply vertex colors if enabled
        if props.visualize_colors and color_layer and min_disp != max_disp:
            disp_range = max_disp - min_disp
            # For each face
            for face in bm.faces:
                # For each loop in the face
                for loop in face.loops:
                    # Get normalized displacement value (0-1)
                    disp_val = displacement_values[loop.vert]
                    normalized_val = (disp_val - min_disp) / disp_range
                    # Set color (using grayscale)
                    loop[color_layer] = (normalized_val, normalized_val, normalized_val, 1.0)

        # Optional smoothing pass
        if props.do_smoothing:
            bmesh.ops.smooth_vert(
                bm,
                verts=bm.verts,
                factor=0.5,
                use_axis_x=True,
                use_axis_y=True,
                use_axis_z=True
            )

        # Update mesh
        bm.to_mesh(me)
        bm.free()
        me.update()

        # If user requested vertex colors, create/assign a material that displays them.
        if props.visualize_colors:
            mat_name = "WoodGrainVCol_Mat"
            # Create a new material if needed
            if mat_name not in bpy.data.materials:
                mat = bpy.data.materials.new(mat_name)
                mat.use_nodes = True

                # Build a simple node tree referencing our VCol
                nt = mat.node_tree
                nt.nodes.clear()

                # Create nodes
                output_node = nt.nodes.new("ShaderNodeOutputMaterial")
                output_node.location = (300, 0)

                princ_node = nt.nodes.new("ShaderNodeBsdfPrincipled")
                princ_node.location = (0, 0)

                attr_node = nt.nodes.new("ShaderNodeAttribute")
                attr_node.location = (-300, 0)
                attr_node.attribute_name = "WoodGrain"

                # Link them
                nt.links.new(attr_node.outputs["Color"], princ_node.inputs["Base Color"])
                nt.links.new(princ_node.outputs["BSDF"], output_node.inputs["Surface"])

            else:
                mat = bpy.data.materials[mat_name]

            # Ensure object has that material
            if not obj.data.materials or mat.name not in [m.name for m in obj.data.materials]:
                obj.data.materials.append(mat)

        # Restore mode
        bpy.ops.object.mode_set(mode=original_mode)

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
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_wood_props = PointerProperty(type=ZENV_PG_WoodGrainProps)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_wood_props

if __name__ == "__main__":
    register()
