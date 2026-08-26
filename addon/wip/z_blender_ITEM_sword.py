
bl_info = {
    "name": 'ITEM Sword Generator',
    "blender": (4, 0, 2),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate swords with advanced geometry, bevels, and improved pivot',
    "status": 'wip',
    "approved": False,
    "group": 'Item',
    "group_prefix": 'ITEM',
    "group_order": 50,
    "addon_order": 50,
    "location": 'View3D > ZENV',
    "tags": ['item', 'sword', 'weapon', 'generator', 'mesh'],
    "description_short": 'Generate   swords with  geometry.',
    "description_medium": 'Creates a complete sword mesh with blade, crossguard, grip, and pommel. '
                          'Supports multiple blade types, hilt styles, pattern welding, and surface decoration.',
    "description_long": ' sword generator with  orientation and realistic geometry. '
                        'Crossguard at origin, blade in +Y direction, grip in -Y direction, pommel at base. '
                        'More subdivisions, fuller inset, bevels/chamfers for realism. '
                        'Randomization for unique results each generation.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}

import bpy
import bmesh
import math
import random
import logging
from mathutils import Vector, Matrix
from bpy.props import (
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty
)
from bpy.types import PropertyGroup, Operator, Panel

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

# ------------------------------------------------------------------------
# Sword Options (CheckBoxes)
# ------------------------------------------------------------------------
class ZENV_PG_SwordOptions(PropertyGroup):
    """Property group for basic sword generation options"""
    enable_blade: BoolProperty(
        name="Generate Blade",
        default=True,
        description="Enable or disable generating the blade"
    )
    enable_crossguard: BoolProperty(
        name="Generate Crossguard",
        default=True,
        description="Enable or disable generating the crossguard"
    )
    enable_grip: BoolProperty(
        name="Generate Grip",
        default=True,
        description="Enable or disable generating the grip"
    )
    enable_pommel: BoolProperty(
        name="Generate Pommel",
        default=True,
        description="Enable or disable generating the pommel"
    )
    enable_pattern_welding: BoolProperty(
        name="Apply Pattern Welding",
        default=True,
        description="Enable or disable the pattern welding effect"
    )
    enable_surface_decoration: BoolProperty(
        name="Apply Surface Decoration",
        default=True,
        description="Enable or disable the surface decoration (Etched/Inlaid/Engraved)"
    )

# ------------------------------------------------------------------------
# Sword Blade Properties
# ------------------------------------------------------------------------
class ZENV_PG_SwordBlade(PropertyGroup):
    """Property group for blade-specific properties and customization"""
    blade_type: EnumProperty(
        name="Blade Type",
        description="Historical blade classification",
        items=[
            ('LONGSWORD', "Longsword", "Two-handed European sword"),
            ('KATANA', "Katana", "Japanese curved sword"),
            ('RAPIER', "Rapier", "Thin thrusting sword"),
            ('VIKING', "Viking", "Norse pattern-welded sword")
        ],
        default='LONGSWORD'
    )
    
    blade_length: FloatProperty(
        name="Blade Length",
        description="Length of blade from crossguard to tip",
        default=90.0, min=45.0, max=150.0,
        unit='LENGTH'
    )
    
    fuller_width: FloatProperty(
        name="Fuller Width",
        description="Width of the blood groove (fuller). A value of 0 means no fuller.",
        default=2.0, min=0.0, max=5.0,
        unit='LENGTH'
    )
    
    distal_taper: FloatProperty(
        name="Distal Taper",
        description="Thickness reduction towards tip (0.3 = strong taper, 0.9 = slight taper)",
        default=0.6, min=0.3, max=0.9
    )
    
    edge_bevels: BoolProperty(
        name="Edge Bevels",
        description="Add cutting edge geometry to the blade (light chamfer at edges)",
        default=True
    )

# ------------------------------------------------------------------------
# Sword Hilt Properties
# ------------------------------------------------------------------------
class ZENV_PG_SwordHilt(PropertyGroup):
    """Property group for hilt-specific properties including grip, pommel, and crossguard"""
    grip_style: EnumProperty(
        name="Grip Style",
        items=[
            ('LEATHER', "Leather Wrap", "Traditional leather grip"),
            ('CORD', "Cord Wrap", "Japanese style cord wrap"),
            ('WIRE', "Wire Wrap", "Twisted wire wrap"),
            ('WOOD', "Wood Grip", "Carved wooden grip")
        ],
        default='LEATHER'
    )
    
    grip_length: FloatProperty(
        name="Grip Length",
        description="Length of handle (extends in the -Y direction)",
        default=15.0, min=8.0, max=30.0,
        unit='LENGTH'
    )
    
    pommel_type: EnumProperty(
        name="Pommel Type",
        items=[
            ('WHEEL', "Wheel", "Circular pommel"),
            ('SCENT_STOPPER', "Scent-stopper", "Tapered pommel"),
            ('FISHTAIL', "Fishtail", "Spread pommel"),
            ('PEAR', "Pear", "Rounded pommel")
        ],
        default='WHEEL'
    )
    
    crossguard_style: EnumProperty(
        name="Crossguard Style",
        items=[
            ('STRAIGHT', "Straight", "Simple straight crossguard"),
            ('CURVED', "Curved", "Curved quillons"),
            ('COMPLEX', "Complex", "Ornate design")
        ],
        default='STRAIGHT'
    )

# ------------------------------------------------------------------------
# Sword Decoration Properties
# ------------------------------------------------------------------------
class ZENV_PG_SwordDecoration(PropertyGroup):
    """Property group for decorative elements and surface treatments"""
    pattern_welding: BoolProperty(
        name="Pattern Welding",
        description="Add Damascus-style patterns (if enabled)",
        default=False
    )
    
    surface_decoration: EnumProperty(
        name="Surface Decoration",
        items=[
            ('NONE', "None", "No decoration"),
            ('ETCHED', "Etched", "Acid-etched patterns"),
            ('INLAID', "Inlaid", "Metal inlay work"),
            ('ENGRAVED', "Engraved", "Engraved designs")
        ],
        default='NONE'
    )
    
    decoration_density: FloatProperty(
        name="Decoration Density",
        description="Density of decorative patterns",
        default=0.5, min=0.1, max=1.0
    )

# ------------------------------------------------------------------------
# Sword Generator Operator
# ------------------------------------------------------------------------
class ZENV_OT_GenerateSword(Operator):
    """Generate a historically accurate sword with customizable blade, hilt, and decorative properties.
    Creates a complete sword mesh with proper geometry, including bevels and optional pattern welding."""

    bl_idname = "zenv.generate_sword"
    bl_label = "Generate Sword"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        # Use a local RNG to avoid polluting the global random state (review (section)2.3)
        self._rng = random.Random()

        sword_opts = context.scene.sword_options
        blade_props = context.scene.sword_blade
        hilt_props = context.scene.sword_hilt
        decor_props = context.scene.sword_decoration

        # Track created objects for cleanup on failure (review (section)2.4)
        created_objects = []

        try:
            # Generate in correct order so references line up visually:
            # 1. Crossguard at (0,0,0)
            # 2. Blade in +Y
            # 3. Grip in -Y
            # 4. Pommel further in -Y
            blade_obj = None
            crossguard_obj = None
            grip_obj = None
            pommel_obj = None

            if sword_opts.enable_crossguard:
                crossguard_obj = self.create_crossguard(context, hilt_props)
                if crossguard_obj:
                    created_objects.append(crossguard_obj)

            if sword_opts.enable_blade:
                blade_obj = self.create_blade(context, blade_props)
                if blade_obj:
                    created_objects.append(blade_obj)

            if sword_opts.enable_grip:
                grip_obj = self.create_grip(context, hilt_props)
                if grip_obj:
                    created_objects.append(grip_obj)

            if sword_opts.enable_pommel:
                pommel_obj = self.create_pommel(context, hilt_props)
                if pommel_obj:
                    created_objects.append(pommel_obj)

            # Apply any requested decorative steps
            if sword_opts.enable_pattern_welding and decor_props.pattern_welding:
                if blade_obj:
                    self.apply_pattern_welding(blade_obj, decor_props)
            if (sword_opts.enable_surface_decoration and
                decor_props.surface_decoration != 'NONE'):
                if blade_obj:
                    self.apply_surface_decoration(blade_obj, decor_props)

            logger.info(f"Sword generated: {len(created_objects)} objects")
            return {'FINISHED'}

        except Exception as e:
            # Clean up partial results on failure (review (section)2.4)
            logger.error(f"Sword generation failed: {e}")
            for obj in created_objects:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    
    # --------------------------------------------------------------------
    # Create Blade: More realistic geometry, subdivisions, fuller, bevel
    # --------------------------------------------------------------------
    def create_blade(self, context, props):
        """
        Create a subdivided blade mesh around (0,0,0) as the base (crossguard),
        extending in the +Y direction. Includes:
         - Curved spine
         - Proper taper
         - Fuller (optional)
         - Edge bevel/chamfer
         - High subdivisions for smooth shape
        """
        rng = self._rng
        bm = None

        try:
            bm = bmesh.new()

            length = props.blade_length * rng.uniform(0.9, 1.1)
            # We'll define a "spine curve" from y=0 (at crossguard) to y=length.

            # Let's define how many major segments we'll have along the length
            major_segments = 8
            # We'll subdivide further later. This is for initial shape definition.

            spine_points = []
            for i in range(major_segments + 1):
                t = i / major_segments
                y = length * t

                # We'll add curvature for a Katana or keep it straighter for others
                x_offset = 0.0
                if props.blade_type == 'KATANA':
                    # Curvature amplitude
                    amp = (length * 0.1) * rng.uniform(0.8, 1.2)
                    x_offset = math.sin(t * math.pi) * amp

                # We can also add slight random vertical waviness for variety
                # or keep it minimal for more "professional forging".
                spine_points.append(Vector((x_offset, y, 0.0)))

            # Create cross-sections from these spine points
            # We'll store the cross-section verts in each segment for connecting faces
            all_ring_verts = []

            base_width = 5.0  # ~5cm wide
            base_thickness = 0.6  # ~6mm thickness
            for i in range(len(spine_points)):
                t = i / major_segments
                # Distal taper factor
                taper = 1.0 - t * (1.0 - props.distal_taper)

                # Slight random variation
                taper *= rng.uniform(0.95, 1.05)

                # The cross-section width, thickness
                width = base_width * taper * rng.uniform(0.9, 1.1)
                thickness = base_thickness * taper * rng.uniform(0.9, 1.1)

                center = spine_points[i]

                # We'll create 8 vertices around the cross-section for more detail
                ring_verts = []
                # Let's do a symmetrical shape (like a flattened rectangle)
                # We'll do top/bottom, left/right, etc. with round corners
                # For simplicity, we can define corners in local "blade space"

                half_w = width / 2.0
                half_t = thickness / 2.0

                corners = [
                    Vector((-half_w, 0, -half_t)),
                    Vector(( half_w, 0, -half_t)),
                    Vector(( half_w, 0,  half_t)),
                    Vector((-half_w, 0,  half_t)),
                ]

                # We'll subdivide these corners once to form an octagon-like shape
                # or simply create 8 points around the perimeter
                perimeter_points = []
                for c_i in range(len(corners)):
                    c1 = corners[c_i]
                    c2 = corners[(c_i+1) % len(corners)]
                    midpoint = (c1 + c2) / 2
                    perimeter_points.append(c1)
                    perimeter_points.append(midpoint)

                # Transform these points so that their local "up/down" is in +Z,
                # but we actually want the thickness in Z and width in X, so
                # by default, we'll treat X as horizontal, Z as vertical.
                # Then shift by 'center.y' in global space.

                ring = []
                for pp in perimeter_points:
                    # local_x = pp.x, local_z = pp.z
                    # We'll place them at (center.x + local_x, center.y, center.z + local_z).
                    v = bm.verts.new((
                        center.x + pp.x,
                        center.y,
                        center.z + pp.z
                    ))
                    ring.append(v)

                all_ring_verts.append(ring)

            # Connect faces between consecutive rings
            for i in range(len(all_ring_verts) - 1):
                ringA = all_ring_verts[i]
                ringB = all_ring_verts[i+1]
                countA = len(ringA)
                for j in range(countA):
                    v1 = ringA[j]
                    v2 = ringA[(j+1) % countA]
                    v3 = ringB[(j+1) % countA]
                    v4 = ringB[j]
                    bm.faces.new((v1, v2, v3, v4))

            bm.verts.ensure_lookup_table()

            # Ensure the tip is pointed BEFORE any bevel operations (review (section)2.5)
            # Bevel operations can invalidate vert references, so scale first.
            tip_ring = all_ring_verts[-1]
            bmesh.ops.scale(
                bm,
                vec=(0.1, 1.0, 0.1),  # flatten in X,Z
                verts=tip_ring
            )

            # If fuller_width > 0, let's create a groove in the middle
            # We can create a set of edges along the top and use a "bevel" inward or extrude inward.
            if props.fuller_width > 0.01:
                # We'll identify a line along the top center of each ring,
                # then do a small inset to represent the fuller.
                # Since we have 8 perimeter points, let's assume
                # the "center top" is around index 2 or 3 in ring array.

                # A robust solution might be to find the top center based on minimal x offset,
                # but let's pick the middle between (2,3) or so for demonstration.

                # We'll collect edges from ring i to i+1 in that center region
                groove_edges = []
                seen_edges = set()  # deduplicate (review fix)
                for i in range(len(all_ring_verts) - 1):
                    # approximate top center
                    ringA = all_ring_verts[i]
                    ringB = all_ring_verts[i+1]
                    # Let's pick ringA[2] -> ringA[3], ringB[2] -> ringB[3]
                    topA = ringA[2]
                    topA2 = ringA[3]
                    topB = ringB[2]
                    topB2 = ringB[3]

                    # Make edges if they don't exist
                    e1 = bm.edges.get((topA, topA2))
                    e2 = bm.edges.get((topA2, topB2))
                    e3 = bm.edges.get((topB2, topB))
                    e4 = bm.edges.get((topB, topA))
                    # Deduplicate before appending
                    for e in (e1, e2, e3, e4):
                        if e is not None and e not in seen_edges:
                            seen_edges.add(e)
                            groove_edges.append(e)

                # Use a small "bevel" on these edges to push them inward
                # The distance will approximate the fuller width.
                bmesh.ops.bevel(
                    bm,
                    geom=groove_edges,
                    offset=props.fuller_width * 0.1,  # adjust as needed
                    segments=1,
                    profile=0.5,
                    affect='EDGES'
                )

            # If edge_bevels, apply a small chamfer along the outer perimeter
            if props.edge_bevels:
                bm.edges.ensure_lookup_table()
                perimeter_edges = [e for e in bm.edges if len(e.link_faces) < 2]
                if perimeter_edges:
                    bmesh.ops.bevel(
                        bm,
                        geom=perimeter_edges,
                        offset=0.05,  # small chamfer
                        segments=1,
                        profile=0.7,
                        affect='EDGES'
                    )

            # Convert BMesh to Mesh
            mesh = bpy.data.meshes.new("Blade")
            bm.to_mesh(mesh)
            bm.free()
            bm = None  # mark as freed so finally doesn't double-free (review (section)2.4)

            # Create and link the object (review (section)3.2: use passed context)
            blade_obj = bpy.data.objects.new("Blade", mesh)
            context.collection.objects.link(blade_obj)

            # Move blade so its base is exactly at y=0 (the crossguard pivot).
            # Since we built from y=0 up, it's already aligned for the crossguard.

            return blade_obj

        finally:
            # Free BMesh if still allocated (review (section)2.4)
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
    
    # --------------------------------------------------------------------
    # Create Crossguard: At Origin
    # --------------------------------------------------------------------
    def create_crossguard(self, context, props):
        """
        Create a crossguard at (0,0,0). Blade extends +Y, grip extends -Y.
        We'll add subdivisions/bevels for a more realistic shape.
        """
        rng = self._rng
        bm = None

        try:
            bm = bmesh.new()

            # Basic shape logic from previous code, with more detail
            if props.crossguard_style == 'STRAIGHT':
                width = rng.uniform(18.0, 22.0)
                height = rng.uniform(1.5, 2.5)
                depth = rng.uniform(3.0, 5.0)
                bmesh.ops.create_cube(bm, size=1.0)
                bm.verts.ensure_lookup_table()
                bmesh.ops.scale(bm, vec=(width, depth, height), verts=[v for v in bm.verts])

            elif props.crossguard_style == 'CURVED':
                # Let's create a cylinder and then "bend" it or subdiv for shape
                rad = rng.uniform(2.0, 3.0)
                length = rng.uniform(20.0, 25.0)
                segs = 16
                geom = bmesh.ops.create_cone(
                    bm,
                    cap_ends=True,
                    cap_tris=False,
                    segments=segs,
                    radius1=rad,
                    radius2=rad,  # same radius => cylinder
                    depth=length
                )


                # We want the cylinder aligned along X or Z, so let's rotate it.
                # By default, create_cylinder is along Z. We'll rotate it so axis is X
                bmesh.ops.rotate(
                    bm,
                    verts=[v for v in bm.verts],
                    cent=(0,0,0),
                    matrix=Matrix.Rotation(math.radians(90.0), 3, 'Y')
                )

                # Now the cylinder's length is along X. We'll flatten the center a bit
                # or allow slight random curvature. We'll skip a fancy bend for brevity.

            elif props.crossguard_style == 'COMPLEX':
                # Create a filled circle, then extrude the face to produce
                # solid geometry instead of a wireframe (review (section)3.8).
                ring_radius = rng.uniform(8.0, 12.0)
                ring_segments = 16
                geom = bmesh.ops.create_circle(bm, segments=ring_segments, radius=ring_radius)

                # Fill the circle with an n-gon face so extrusion creates
                # solid geometry rather than floating wire edges.
                bmesh.ops.contextual_create(bm, geom=geom['edges'])

                # Now extrude the face to give the crossguard depth.
                faces_to_extrude = [f for f in bm.faces]
                if faces_to_extrude:
                    ret = bmesh.ops.extrude_face_region(bm, geom=faces_to_extrude)
                    new_verts = [v for v in ret['geom']
                                 if isinstance(v, bmesh.types.BMVert)]
                    bmesh.ops.translate(
                        bm,
                        verts=new_verts,
                        vec=(0, rng.uniform(-1.0, 1.0), rng.uniform(1.0, 3.0))
                    )

            # Small bevel on perimeter edges
            bm.edges.ensure_lookup_table()
            perimeter_edges = [e for e in bm.edges if len(e.link_faces) < 2]
            if perimeter_edges:
                bmesh.ops.bevel(
                    bm,
                    geom=perimeter_edges,
                    offset=0.2,
                    segments=1,
                    profile=0.7,
                    affect='EDGES'
                )

            # Convert BMesh to Mesh
            mesh = bpy.data.meshes.new("Crossguard")
            bm.to_mesh(mesh)
            bm.free()
            bm = None  # mark as freed (review (section)2.4)

            crossguard_obj = bpy.data.objects.new("Crossguard", mesh)
            context.collection.objects.link(crossguard_obj)  # review (section)3.2

            # Assign a default steel material to the crossguard (review (section)3.6)
            self._assign_material(crossguard_obj, "SteelMaterial",
                                  base_color=(0.4, 0.4, 0.42, 1.0),
                                  metallic=0.9, roughness=0.3)

            # Crossguard is at origin by design, orientation as is.
            return crossguard_obj

        finally:
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
    
    # --------------------------------------------------------------------
    # Create Grip: Extends in -Y from Origin
    # --------------------------------------------------------------------
    def create_grip(self, context, props):
        """
        Create a grip that extends from y=0 (crossguard) to negative y.
        More subdivisions, plus optional wrapping details.
        """
        rng = self._rng
        bm = None

        try:
            bm = bmesh.new()

            length = props.grip_length * rng.uniform(0.9, 1.1)
            # We'll model a cylinder from 0 to -length on the Y-axis
            radius = rng.uniform(1.2, 1.6)
            segments = 16

            geom = bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=segments,  # review (section)2.1: was 'segs' (undefined)
                radius1=radius,
                radius2=radius,  # same radius => cylinder
                depth=length
            )

            # By default, the cylinder is along Z from -depth/2 to +depth/2 in local coords
            # We want it along Y, from 0 to -length. So rotate 90 deg to make it along Y
            bmesh.ops.rotate(
                bm,
                verts=[v for v in bm.verts],
                cent=(0, 0, 0),
                matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
            )

            # Now the cylinder extends from -length/2 to +length/2 along Y.
            # Let's shift it so that its top is at y=0, bottom is at y=-length
            translate_vec = Vector((0, -length/2, 0))
            bmesh.ops.translate(bm, verts=[v for v in bm.verts], vec=translate_vec)

            # Light bevel on top/bottom edges
            bm.edges.ensure_lookup_table()
            perimeter_edges = [e for e in bm.edges if len(e.link_faces) < 2]
            if perimeter_edges:
                bmesh.ops.bevel(
                    bm,
                    geom=perimeter_edges,
                    offset=0.05,
                    segments=1,
                    profile=0.7,
                    affect='EDGES'
                )

            # Additional wrap geometry - created as a separate object so
            # the wrap has its own faces and does not leave disconnected
            # wire edges inside the grip mesh (review (section)3.1).
            wrap_obj = None
            if props.grip_style == 'LEATHER':
                wrap_obj = self.add_leather_wrap(context, length)
            elif props.grip_style == 'CORD':
                wrap_obj = self.add_cord_wrap(context, length)
            # (WIRE, WOOD omitted for brevity, can be added similarly)

            mesh = bpy.data.meshes.new("Grip")
            bm.to_mesh(mesh)
            bm.free()
            bm = None  # mark as freed (review (section)2.4)

            grip_obj = bpy.data.objects.new("Grip", mesh)
            context.collection.objects.link(grip_obj)  # review (section)3.2

            # Assign a default leather/wood material to the grip (review (section)3.6)
            self._assign_material(grip_obj, "GripMaterial",
                                  base_color=(0.2, 0.12, 0.06, 1.0),
                                  metallic=0.0, roughness=0.7)
            if wrap_obj is not None:
                self._assign_material(wrap_obj, "WrapMaterial",
                                      base_color=(0.15, 0.08, 0.04, 1.0),
                                      metallic=0.0, roughness=0.8)

            return grip_obj

        finally:
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
    
    # --------------------------------------------------------------------
    # Create Pommel: Attaches further at the base of the grip (-Y)
    # --------------------------------------------------------------------
    def create_pommel(self, context, props):
        """
        Create pommel geometry near the end of the grip (slightly below y = -grip_length).
        We'll place it so that its top is flush with y = -grip_length.
        """
        rng = self._rng
        bm = None

        try:
            bm = bmesh.new()

            if props.pommel_type == 'WHEEL':
                segments = 32
                radius = rng.uniform(2.5, 3.5)
                thickness = rng.uniform(1.5, 2.5)
                # We'll create a cylinder for the wheel shape, then do some bevel
                geom = bmesh.ops.create_cone(
                    bm,
                    cap_ends=True,
                    cap_tris=False,
                    segments=segments,  # review (section)2.2: was 'segs' (undefined)
                    radius1=radius,
                    radius2=radius,  # same radius => cylinder
                    depth=thickness
                )


                # Rotate so the cylinder is along the Y-axis
                bmesh.ops.rotate(
                    bm,
                    verts=[v for v in bm.verts],
                    cent=(0, 0, 0),
                    matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
                )

                # Shift so the top is at y=0, the bottom is at y=-thickness
                bmesh.ops.translate(bm, verts=[v for v in bm.verts], vec=(0, -thickness/2, 0))

            elif props.pommel_type == 'SCENT_STOPPER':
                height = rng.uniform(4.0, 6.0)
                segments = 12
                geom = bmesh.ops.create_cone(
                    bm,
                    cap_ends=True,
                    cap_tris=False,
                    segments=segments,
                    radius1=rng.uniform(2.0, 2.2),
                    radius2=0.0,
                    depth=height
                )

                # Rotate along Y
                bmesh.ops.rotate(
                    bm,
                    verts=[v for v in bm.verts],
                    cent=(0,0,0),
                    matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
                )

                # Shift top to y=0 (review (section)4.11: was -height, should be -height/2)
                bmesh.ops.translate(bm, verts=[v for v in bm.verts], vec=(0, -height/2, 0))

            elif props.pommel_type == 'FISHTAIL':
                size = rng.uniform(2.5, 3.5)
                bmesh.ops.create_cube(bm, size=size)
                bmesh.ops.scale(bm, vec=(1.0, 0.5, 1.5), verts=[v for v in bm.verts])
                # Rotate to align along Y
                bmesh.ops.rotate(
                    bm,
                    verts=[v for v in bm.verts],
                    cent=(0,0,0),
                    matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
                )
                # Shift top to y=0
                bmesh.ops.translate(bm, verts=[v for v in bm.verts], vec=(0, -size/2, 0))

            elif props.pommel_type == 'PEAR':
                radius = rng.uniform(2.0, 2.5)
                bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius)
                # Slight stretch
                stretch_factor = rng.uniform(1.1, 1.3)
                bmesh.ops.scale(bm, vec=(1.0, stretch_factor, 1.0), verts=[v for v in bm.verts])
                # Rotate so "pole" is along Y
                bmesh.ops.rotate(
                    bm,
                    verts=[v for v in bm.verts],
                    cent=(0,0,0),
                    matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
                )
                # Shift so top is at y=0 (review (section)4.10: comment said "bottom to y=0" but
                # behavior should match other pommel types: top at y=0)
                bmesh.ops.translate(bm, verts=[v for v in bm.verts], vec=(0, -radius, 0))

            # Light bevel on outer edges
            perimeter_edges = [e for e in bm.edges if len(e.link_faces) < 2]
            if perimeter_edges:
                bmesh.ops.bevel(
                    bm,
                    geom=perimeter_edges,
                    offset=0.1,
                    segments=1,
                    profile=0.7,
                    affect='EDGES'
                )

            mesh = bpy.data.meshes.new("Pommel")
            bm.to_mesh(mesh)
            bm.free()
            bm = None  # mark as freed (review (section)2.4)

            pommel_obj = bpy.data.objects.new("Pommel", mesh)
            context.collection.objects.link(pommel_obj)  # review (section)3.2

            # Assign a default steel material to the pommel (review (section)3.6)
            self._assign_material(pommel_obj, "SteelMaterial",
                                  base_color=(0.4, 0.4, 0.42, 1.0),
                                  metallic=0.9, roughness=0.3)

            # Now place it so it sits at the bottom of the grip
            # We'll assume the grip length is in scene props:
            grip_length = props.grip_length  # We'll guess ~
            # Move pommel so top is at y = -grip_length
            # We already built the geometry so top is at y=0, bottom negative.
            # So let's just shift it by -grip_length
            pommel_obj.location.y = -grip_length

            return pommel_obj

        finally:
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
    
    # --------------------------------------------------------------------
    # Wraps & Decorations
    # --------------------------------------------------------------------
    def add_leather_wrap(self, context, length):
        """
        Creates banding geometry as a separate object to simulate leather
        strips on the grip. Each band is a torus-like ring with actual
        faces (review (section)3.1: was disconnected wire geometry).
        """
        rng = self._rng
        bm = bmesh.new()
        try:
            num_bands = rng.randint(3, 6)
            base_radius = 1.0  # grip radius

            for i in range(num_bands):
                band_y = -rng.uniform(0.1, 0.9) * length
                ring_segments = 16
                band_thickness = rng.uniform(0.05, 0.15)

                # Create two rings (inner and outer) and connect faces
                inner_verts = []
                outer_verts = []
                for s in range(ring_segments):
                    angle = 2 * math.pi * s / ring_segments
                    cx = math.cos(angle)
                    sz = math.sin(angle)
                    inner_verts.append(bm.verts.new(
                        (cx * base_radius, band_y, sz * base_radius)))
                    outer_verts.append(bm.verts.new(
                        (cx * (base_radius + band_thickness),
                         band_y, sz * (base_radius + band_thickness))))

                # Connect faces between inner and outer rings
                for s in range(ring_segments):
                    s2 = (s + 1) % ring_segments
                    bm.faces.new((
                        inner_verts[s], inner_verts[s2],
                        outer_verts[s2], outer_verts[s],
                    ))

            mesh = bpy.data.meshes.new("LeatherWrap")
            bm.to_mesh(mesh)
            bm.free()
            bm = None
            wrap_obj = bpy.data.objects.new("LeatherWrap", mesh)
            context.collection.objects.link(wrap_obj)
            return wrap_obj
        finally:
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass

    def add_cord_wrap(self, context, length):
        """
        Create crisscross wrap geometry as a separate object with actual
        faces (review (section)3.1: was disconnected wire geometry).
        Each cord is a thin tube following a spiral path.
        """
        rng = self._rng
        bm = bmesh.new()
        try:
            base_radius = 1.0
            tube_radius = 0.04
            tube_segments = 6

            for direction in (1, -1):
                wraps = rng.randint(2, 3)
                for w in range(wraps):
                    angle_start = rng.uniform(0, math.pi)
                    pitch = rng.uniform(0.2, 0.5) * direction
                    spiral_segments = 20
                    prev_ring = None
                    for i in range(spiral_segments + 1):
                        t = i / spiral_segments
                        y = -length * t
                        angle = angle_start + (pitch * 2 * math.pi * t)
                        cx = math.cos(angle) * base_radius
                        cz = math.sin(angle) * base_radius
                        center = Vector((cx, y, cz))

                        # Create a small ring around the center point
                        ring_verts = []
                        for s in range(tube_segments):
                            a = 2 * math.pi * s / tube_segments
                            # Perpendicular offset
                            rx = math.cos(a) * tube_radius
                            rz = math.sin(a) * tube_radius
                            ring_verts.append(bm.verts.new(
                                (cx + rx, y, cz + rz)))

                        # Connect to previous ring
                        if prev_ring is not None:
                            for s in range(tube_segments):
                                s2 = (s + 1) % tube_segments
                                bm.faces.new((
                                    prev_ring[s], prev_ring[s2],
                                    ring_verts[s2], ring_verts[s],
                                ))
                        prev_ring = ring_verts

            mesh = bpy.data.meshes.new("CordWrap")
            bm.to_mesh(mesh)
            bm.free()
            bm = None
            wrap_obj = bpy.data.objects.new("CordWrap", mesh)
            context.collection.objects.link(wrap_obj)
            return wrap_obj
        finally:
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
    
    def _assign_material(self, obj, mat_name, base_color=(0.5, 0.5, 0.5, 1.0),
                         metallic=0.0, roughness=0.5):
        """Assign or reuse a Principled BSDF material to ``obj``.

        If a material with ``mat_name`` already exists in bpy.data, it is
        reused rather than recreated (review (section)3.6).
        """
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
        else:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            for node in list(nodes):
                nodes.remove(node)
            output = nodes.new(type='ShaderNodeOutputMaterial')
            output.location = (300, 0)
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = base_color
            bsdf.inputs['Metallic'].default_value = metallic
            bsdf.inputs['Roughness'].default_value = roughness
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

    def apply_pattern_welding(self, obj, props):
        """
        Same as before: create or reuse a DamascusMaterial,
        randomize noise parameters, etc.
        """
        rng = self._rng
        mat_name = "DamascusMaterial"
        if mat_name not in bpy.data.materials:
            damascus_mat = bpy.data.materials.new(mat_name)
            damascus_mat.use_nodes = True
        else:
            damascus_mat = bpy.data.materials[mat_name]

        nodes = damascus_mat.node_tree.nodes
        links = damascus_mat.node_tree.links
        for node in nodes:
            nodes.remove(node)

        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)

        princ_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        princ_bsdf.location = (0, 0)
        links.new(princ_bsdf.outputs['BSDF'], output_node.inputs['Surface'])

        noise_tex = nodes.new(type='ShaderNodeTexNoise')
        noise_tex.location = (-300, 100)
        noise_tex.inputs['Scale'].default_value = rng.uniform(5.0, 15.0)
        noise_tex.inputs['Detail'].default_value = 16.0
        noise_tex.inputs['Distortion'].default_value = rng.uniform(0.5, 3.0)

        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-100, 100)
        color_ramp.color_ramp.elements[0].position = 0.4
        color_ramp.color_ramp.elements[1].position = 0.6
        color_ramp.color_ramp.elements[0].color = (
            rng.uniform(0.1, 0.3),
            rng.uniform(0.1, 0.3),
            rng.uniform(0.1, 0.3),
            1
        )
        color_ramp.color_ramp.elements[1].color = (
            rng.uniform(0.5, 0.9),
            rng.uniform(0.5, 0.9),
            rng.uniform(0.5, 0.9),
            1
        )

        links.new(noise_tex.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], princ_bsdf.inputs['Base Color'])

        princ_bsdf.inputs['Metallic'].default_value = rng.uniform(0.4, 0.9)
        princ_bsdf.inputs['Roughness'].default_value = rng.uniform(0.1, 0.4)

        if not obj.data.materials:
            obj.data.materials.append(damascus_mat)
        else:
            obj.data.materials[0] = damascus_mat

    def apply_surface_decoration(self, obj, props):
        """
        Adds a Voronoi-based overlay for ETCHED, INLAID, or ENGRAVED.

        Uses a second material slot so it does not overwrite the pattern
        welding material in slot 0 (review (section)3.7).
        """
        rng = self._rng
        # Always create a new decoration material in a new slot so the
        # pattern welding material (slot 0) is preserved.
        mat = bpy.data.materials.new("SwordDecoration")
        mat.use_nodes = True
        obj.data.materials.append(mat)

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Find or create Principled BSDF
        principled = None
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled = node
                break
        if not principled:
            principled = nodes.new(type='ShaderNodeBsdfPrincipled')
            principled.location = (0, 0)
            out_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not out_node:
                out_node = nodes.new(type='ShaderNodeOutputMaterial')
                out_node.location = (300,0)
            links.new(principled.outputs['BSDF'], out_node.inputs['Surface'])

        # Create Voronoi texture
        dec_tex = nodes.new(type='ShaderNodeTexVoronoi')
        dec_tex.location = (-300, 200)
        dec_tex.inputs['Scale'].default_value = (
            rng.uniform(5.0, 15.0) * (1.0 / props.decoration_density)
        )

        if props.surface_decoration == 'ETCHED':
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.location = (-100, 200)
            bump_node.inputs['Strength'].default_value = rng.uniform(0.1, 0.3)
            links.new(dec_tex.outputs['Distance'], bump_node.inputs['Height'])
            links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])

        elif props.surface_decoration == 'ENGRAVED':
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.location = (-100, 200)
            bump_node.inputs['Strength'].default_value = rng.uniform(0.3, 0.6)
            links.new(dec_tex.outputs['Distance'], bump_node.inputs['Height'])
            links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])

        elif props.surface_decoration == 'INLAID':
            mix_node = nodes.new(type='ShaderNodeMixRGB')
            mix_node.location = (-100, 200)
            mix_node.inputs['Fac'].default_value = rng.uniform(0.3, 0.7)
            # random bright metallic color for inlay
            mix_node.inputs['Color2'].default_value = (
                rng.uniform(0.5, 1.0),
                rng.uniform(0.5, 1.0),
                rng.uniform(0.0, 0.3),
                1.0
            )
            links.new(dec_tex.outputs['Distance'], mix_node.inputs['Fac'])
            links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])

# ------------------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------------------
class ZENV_PT_SwordPanel(Panel):
    """UI panel for the sword generator, providing controls for all sword customization options"""

    bl_label = "ITEM Sword Generator"
    bl_idname = "ZENV_PT_sword"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Components to Generate")
        box.prop(context.scene.sword_options, "enable_blade")
        box.prop(context.scene.sword_options, "enable_crossguard")
        box.prop(context.scene.sword_options, "enable_grip")
        box.prop(context.scene.sword_options, "enable_pommel")

        box.label(text="Decorative Processes")
        box.prop(context.scene.sword_options, "enable_pattern_welding")
        box.prop(context.scene.sword_options, "enable_surface_decoration")

        box = layout.box()
        box.label(text="Blade Settings")
        box.prop(context.scene.sword_blade, "blade_type")
        box.prop(context.scene.sword_blade, "blade_length")
        box.prop(context.scene.sword_blade, "fuller_width")
        box.prop(context.scene.sword_blade, "distal_taper")
        box.prop(context.scene.sword_blade, "edge_bevels")

        box = layout.box()
        box.label(text="Hilt Settings")
        box.prop(context.scene.sword_hilt, "grip_style")
        box.prop(context.scene.sword_hilt, "grip_length")
        box.prop(context.scene.sword_hilt, "pommel_type")
        box.prop(context.scene.sword_hilt, "crossguard_style")

        box = layout.box()
        box.label(text="Decoration Settings")
        box.prop(context.scene.sword_decoration, "pattern_welding")
        box.prop(context.scene.sword_decoration, "surface_decoration")
        box.prop(context.scene.sword_decoration, "decoration_density")

        layout.operator("zenv.generate_sword", text="Generate Sword")

# ------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------
classes = (
    ZENV_PG_SwordOptions,
    ZENV_PG_SwordBlade,
    ZENV_PG_SwordHilt,
    ZENV_PG_SwordDecoration,
    ZENV_OT_GenerateSword,
    ZENV_PT_SwordPanel,
)

def register():
    _install_logger()
    # Double-registration guard (review (section)4.5)
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, 'sword_options'):
        bpy.types.Scene.sword_options = PointerProperty(type=ZENV_PG_SwordOptions)
    if not hasattr(bpy.types.Scene, 'sword_blade'):
        bpy.types.Scene.sword_blade = PointerProperty(type=ZENV_PG_SwordBlade)
    if not hasattr(bpy.types.Scene, 'sword_hilt'):
        bpy.types.Scene.sword_hilt = PointerProperty(type=ZENV_PG_SwordHilt)
    if not hasattr(bpy.types.Scene, 'sword_decoration'):
        bpy.types.Scene.sword_decoration = PointerProperty(type=ZENV_PG_SwordDecoration)

def unregister():
    # Unregister classes BEFORE deleting properties (review (section)3.5)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    for prop_name in ("sword_options", "sword_blade", "sword_hilt", "sword_decoration"):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
    _uninstall_logger()

if __name__ == "__main__":
    register()
