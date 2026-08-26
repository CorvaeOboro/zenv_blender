#region META
bl_info = {
    "name": 'GEN VFX Slash',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Parabola Slash Mesh Generator',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['generate', 'vfx', 'slash', 'parabola', 'mesh', 'game'],
    "description_short": 'generate a parabola mesh for vfx slash effects',
    "description_medium": 'Generates a parabola-shaped mesh for VFX slash effects common in game combat animations. Supports three mesh types: gradient-width ribbon (sharp at ends, wide in center), curved tube, or simple line. Configurable angle, height, width, segment count, gradient width, curve radius, and cross-section resolution. Includes per-mesh-type UV mapping.',
    "description_long": """
VFX SLASH GENERATOR
generates a parabola mesh for vfx slash effects
useful for game vfx
""",
    "image_overview": 'zenv_blender_GEN_vfx_slash.png',
    "addon_image": 'zenv_blender_GEN_vfx_slash.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import bmesh
import math
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, Operator, Panel
#endregion


#region PROPS
# Property group for VFX slash generation settings, registered on the Scene.

class ZENV_PG_VFXSlashProperties(PropertyGroup):
    """Properties for the VFX Slash Generator"""
    # --- Arc Shape ---------------------------------------------------------
    angle: FloatProperty(
        name="Angle",
        description="Rotation of the whole arc around the Z axis (degrees). 0 = arc bulges toward +X",
        default=0.0,
        min=0.0,
        max=360.0
    )
    height: FloatProperty(
        name="Height",
        description="Peak bulge of the arc along the forward axis (distance from chord to apex)",
        default=2.0,
        min=0.1,
        max=10.0
    )
    width: FloatProperty(
        name="Width",
        description="Length of the chord (end-to-end span of the slash)",
        default=4.0,
        min=0.1,
        max=10.0
    )
    arc_curvature: FloatProperty(
        name="Arc Curvature",
        description="Shape of the arc bulge. 1.0 = standard parabola, >1.0 = flatter middle with sharper shoulders, <1.0 = rounder dome",
        default=1.0,
        min=0.1,
        max=5.0
    )
    arc_peak: FloatProperty(
        name="Peak Position",
        description="Where the apex sits along the chord (0.0 = left end, 0.5 = centered, 1.0 = right end)",
        default=0.5,
        min=0.0,
        max=1.0
    )
    segments: IntProperty(
        name="Segments",
        description="Number of segments along the arc",
        default=32,
        min=4,
        max=64
    )
    # --- End Taper ---------------------------------------------------------
    end_sharpness: FloatProperty(
        name="End Sharpness",
        description="How pointed the ends/corners are. 1.0 = smooth parabolic taper, >1.0 = sharper points, <1.0 = blunter/rounder ends. Affects ribbon width and tube taper profiles",
        default=1.0,
        min=0.1,
        max=5.0
    )
    # --- Mesh Type ---------------------------------------------------------
    mesh_type: EnumProperty(
        name="Mesh Type",
        description="Type of mesh to generate",
        items=[
            ('GRADIENT', "Gradient Ribbon", "Ribbon mesh with gradient width (sharp at ends, wide in center)"),
            ('CURVE', "Curved Tube", "Tube mesh along the slash line with circular cross-section"),
            ('LINE', "Line", "Simple line mesh (vertices and edges only)"),
        ],
        default='GRADIENT',
    )
    # --- Gradient Ribbon ---------------------------------------------------
    gradient_width: FloatProperty(
        name="Max Width",
        description="Maximum width of the ribbon at the apex of the arc",
        default=0.35,
        min=0.01,
        max=1.0
    )
    # --- Curved Tube -------------------------------------------------------
    curve_radius: FloatProperty(
        name="Max Radius",
        description="Maximum radius of the tube at the apex of the arc",
        default=0.1,
        min=0.01,
        max=0.5
    )
    curve_taper: FloatProperty(
        name="Taper Amount",
        description="How much the tube tapers toward the ends (0 = uniform tube, 1 = tapers fully to points at the ends)",
        default=0.8,
        min=0.0,
        max=1.0
    )
    curve_segments: IntProperty(
        name="Cross Sections",
        description="Number of segments in the circular cross-section of the tube",
        default=8,
        min=3,
        max=32,
    )
#endregion


#region OP
# Operator that generates a parabola-shaped VFX slash mesh.

class ZENV_OT_VFXSlashAdd(Operator):
    """Create a new VFX slash parabola mesh"""
    bl_idname = "zenv.vfx_slash_add"
    bl_label = "Add VFX Slash"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def bulge_factor(t, peak, sharpness):
        """Normalized bulge factor in [0, 1].

        Produces a parabola that is 0 at t=0 and t=1 and peaks at 1.0 when
        ``t == peak``. ``sharpness`` is applied as an exponent: 1.0 gives a
        smooth parabola, >1.0 concentrates the bulge near the peak (sharper
        shoulders/points), <1.0 spreads it out (rounder dome).
        """
        # Clamp peak away from the exact ends so the denominators stay sane.
        p = min(max(peak, 1e-4), 1.0 - 1e-4)
        if t <= p:
            f = 1.0 - ((t - p) / p) ** 2
        else:
            f = 1.0 - ((t - p) / (1.0 - p)) ** 2
        if f < 0.0:
            f = 0.0
        return f ** sharpness

    @classmethod
    def create_parabola_points(cls, props):
        """Generate points for the parabola based on properties.

        The parabola is centered at the origin: the midpoint of its chord
        sits at (0, 0, 0). The chord runs along the Y axis (from -width/2
        to +width/2) and the arc bulges toward +X (forward X axis). The
        ``angle`` property rotates the whole arc around the Z axis.
        ``arc_curvature`` controls the bulge profile sharpness and
        ``arc_peak`` shifts the apex along the chord.
        """
        points = []
        angle_rad = math.radians(props.angle)

        for i in range(props.segments):
            t = i / (props.segments - 1)
            # Chord along Y, centered on the origin.
            y = (t - 0.5) * props.width
            # Bulge along +X (forward X axis), shaped by curvature/peak.
            x = props.height * cls.bulge_factor(t, props.arc_peak, props.arc_curvature)

            # Rotate points around the centered origin.
            rotated_x = x * math.cos(angle_rad) - y * math.sin(angle_rad)
            rotated_y = x * math.sin(angle_rad) + y * math.cos(angle_rad)

            points.append(Vector((rotated_x, rotated_y, 0)))

        return points

    @classmethod
    def create_gradient_mesh(cls, name, points, props):
        """Create mesh with gradient width"""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        # Create vertices for both sides of the gradient
        verts_left = []
        verts_right = []
        
        for i, point in enumerate(points):
            t = i / (len(points) - 1)
            # Ribbon width follows the arc bulge profile, sharpened by
            # end_sharpness so the corners can be made pointier or blunter.
            width = props.gradient_width * cls.bulge_factor(t, props.arc_peak, props.end_sharpness)
            
            # Calculate normal vector perpendicular to curve
            if i < len(points) - 1:
                tangent = (points[i + 1] - point).normalized()
            else:
                tangent = (point - points[i - 1]).normalized()
            normal = Vector((-tangent.y, tangent.x, 0))
            
            # Create vertices on both sides
            vert_left = bm.verts.new(point + normal * width)
            vert_right = bm.verts.new(point - normal * width)
            verts_left.append(vert_left)
            verts_right.append(vert_right)

        bm.verts.ensure_lookup_table()

        # Create faces
        for i in range(len(points) - 1):
            bm.faces.new((verts_left[i], verts_left[i + 1], 
                         verts_right[i + 1], verts_right[i]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @classmethod
    def create_curved_mesh(cls, name, points, props):
        """Create curved mesh along the line.

        The tube radius follows the same parabolic profile as the gradient
        ribbon: largest at the center of the arc and tapering toward the
        ends. The ``curve_taper`` property controls how strong the taper is
        (0 keeps a uniform tube, 1 collapses the ends to points).
        """
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        segments_circle = props.curve_segments
        taper = props.curve_taper
        point_count = len(points)

        # Create vertices for the tube
        for i, point in enumerate(points):
            t = i / (point_count - 1)
            # Taper profile follows the arc bulge, sharpened by end_sharpness.
            # Blend between a uniform tube (taper=0) and the tapered profile.
            profile = cls.bulge_factor(t, props.arc_peak, props.end_sharpness)
            radius = props.curve_radius * (1.0 - taper + taper * profile)

            # Calculate orientation
            if i < len(points) - 1:
                forward = (points[i + 1] - point).normalized()
            else:
                forward = (point - points[i - 1]).normalized()
            up = Vector((0, 0, 1))
            right = forward.cross(up).normalized()

            # Create circle vertices
            for j in range(segments_circle):
                angle = (j / segments_circle) * 2 * math.pi
                circle_pos = (right * math.cos(angle) + up * math.sin(angle)) * radius
                vert = bm.verts.new(point + circle_pos)

        bm.verts.ensure_lookup_table()

        # Create faces
        verts_per_ring = segments_circle
        for i in range(len(points) - 1):
            for j in range(segments_circle):
                j1 = (j + 1) % segments_circle
                idx1 = i * segments_circle + j
                idx2 = i * segments_circle + j1
                idx3 = (i + 1) * segments_circle + j1
                idx4 = (i + 1) * segments_circle + j
                bm.faces.new((bm.verts[idx1], bm.verts[idx2], 
                            bm.verts[idx3], bm.verts[idx4]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @classmethod
    def create_mesh_data(cls, name, points):
        """Create mesh data from points"""
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        # Add vertices
        for point in points:
            bm.verts.new(point)
        bm.verts.ensure_lookup_table()

        # Create edges
        for i in range(len(points) - 1):
            bm.edges.new((bm.verts[i], bm.verts[i + 1]))

        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @classmethod
    def add_uv_mapping(cls, mesh, is_gradient=False, is_curved=False, curve_segments=8):
        """Add UV mapping to the mesh. Line-only meshes (no faces) are skipped."""
        # Line meshes have no faces and therefore no loops - UV mapping is
        # meaningless for them.
        if not mesh.polygons:
            return

        if mesh.uv_layers:
            uv_layer = mesh.uv_layers.active
        else:
            uv_layer = mesh.uv_layers.new()

        if is_gradient:
            # Map UVs for gradient mesh
            for face in mesh.polygons:
                for i, loop_index in enumerate(face.loop_indices):
                    if i in (0, 1):  # Top vertices
                        uv_layer.data[loop_index].uv.y = 1
                    else:  # Bottom vertices
                        uv_layer.data[loop_index].uv.y = 0
                    if i in (0, 3):  # Left vertices
                        uv_layer.data[loop_index].uv.x = face.index / (len(mesh.polygons))
                    else:  # Right vertices
                        uv_layer.data[loop_index].uv.x = (face.index + 1) / (len(mesh.polygons))
        elif is_curved:
            # Map UVs for curved mesh
            for face in mesh.polygons:
                for i, loop_index in enumerate(face.loop_indices):
                    v = i % 2
                    u = (face.index // curve_segments) / max(1, (len(mesh.polygons) // curve_segments))
                    uv_layer.data[loop_index].uv = Vector((u, v))

    def execute(self, context):
        props = context.scene.zenv_vfx_slash_props

        try:
            # Generate parabola points
            points = self.create_parabola_points(props)

            # Create mesh based on mesh_type enum
            if props.mesh_type == 'GRADIENT':
                mesh = self.create_gradient_mesh("VFX_Slash", points, props)
                self.add_uv_mapping(mesh, is_gradient=True)
            elif props.mesh_type == 'CURVE':
                mesh = self.create_curved_mesh("VFX_Slash", points, props)
                self.add_uv_mapping(mesh, is_curved=True,
                                    curve_segments=props.curve_segments)
            else:
                mesh = self.create_mesh_data("VFX_Slash", points)
                # Line meshes have no faces - UV mapping is skipped.
                self.add_uv_mapping(mesh)

            # Create object and link to scene
            obj = bpy.data.objects.new("VFX_Slash", mesh)
            context.collection.objects.link(obj)
        except Exception as e:
            # Clean up any partially created mesh data.
            if 'mesh' in dir() and mesh is not None:
                bpy.data.meshes.remove(mesh)
            self.report({'ERROR'}, f"Failed to create VFX slash: {e}")
            return {'CANCELLED'}

        # Select and make active
        for o in context.view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({'INFO'}, f"Created VFX slash ({props.mesh_type.lower()} mesh)")
        return {'FINISHED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_VFXSlashPanel(Panel):
    """Panel for VFX Slash Generator"""
    bl_label = "GEN VFX Slash Generator"
    bl_idname = "ZENV_PT_vfx_slash"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_vfx_slash_props

        # --- Arc Shape section ---
        box = layout.box()
        box.label(text="Arc Shape", icon='CURVE_BEZCURVE')
        col = box.column(align=True)
        col.prop(props, "angle")
        col.prop(props, "height")
        col.prop(props, "width")
        col.prop(props, "arc_curvature")
        col.prop(props, "arc_peak")
        col.prop(props, "segments")

        # --- End Taper section ---
        box = layout.box()
        box.label(text="End Taper", icon='MOD_SIMPLIFY')
        box.prop(props, "end_sharpness")

        # --- Mesh Type section ---
        box = layout.box()
        box.label(text="Mesh Type", icon='MESH_DATA')
        box.prop(props, "mesh_type", text="")

        # --- Type-specific settings ---
        if props.mesh_type == 'GRADIENT':
            box = layout.box()
            box.label(text="Gradient Ribbon", icon='MOD_WAVE')
            col = box.column(align=True)
            col.prop(props, "gradient_width")
        elif props.mesh_type == 'CURVE':
            box = layout.box()
            box.label(text="Curved Tube", icon='MESH_CYLINDER')
            col = box.column(align=True)
            col.prop(props, "curve_radius")
            col.prop(props, "curve_taper")
            col.prop(props, "curve_segments")

        # --- Operator ---
        layout.operator("zenv.vfx_slash_add", text="Add VFX Slash")
#endregion


#region REG
classes = (
    ZENV_PG_VFXSlashProperties,
    ZENV_OT_VFXSlashAdd,
    ZENV_PT_VFXSlashPanel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_vfx_slash_props = PointerProperty(type=ZENV_PG_VFXSlashProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_vfx_slash_props

if __name__ == "__main__":
    register()
#endregion
