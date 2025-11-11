"""
Advanced Sword Generator with Improved Orientation & Realistic Geometry
- Crossguard at origin, blade in +Y direction, grip in -Y direction, pommel at base
- More subdivisions, fuller inset, bevels/chamfers for realism
- Randomization for unique results each generation
"""

import bpy
import bmesh
from mathutils import Vector, Matrix, noise, geometry
import math
import random
from bpy.props import (
    FloatProperty, 
    IntProperty, 
    EnumProperty, 
    BoolProperty, 
    FloatVectorProperty, 
    PointerProperty
)

bl_info = {
    "name": 'ITEM Sword Generator',
    "blender": (4, 0, 2),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Generate historically accurate swords with advanced geometry, bevels, and improved pivot',
    "status": 'wip',
    "approved": True,
    "group": 'Item',
    "group_prefix": 'ITEM',
    "location": 'View3D > ZENV',
}

# ------------------------------------------------------------------------
# Sword Options (CheckBoxes)
# ------------------------------------------------------------------------
class ZENV_PG_sword_options(bpy.types.PropertyGroup):
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
class ZENV_PG_sword_blade(bpy.types.PropertyGroup):
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
class ZENV_PG_sword_hilt(bpy.types.PropertyGroup):
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
class ZENV_PG_sword_decoration(bpy.types.PropertyGroup):
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
class ZENV_OT_generate_sword(bpy.types.Operator):
    """Generate a historically accurate sword with customizable blade, hilt, and decorative properties.
    Creates a complete sword mesh with proper geometry, including bevels and optional pattern welding."""
    
    bl_idname = "zenv.generate_sword"
    bl_label = "Generate Sword"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        random.seed()  # Each run gets a new random seed

        sword_opts = context.scene.sword_options
        blade_props = context.scene.sword_blade
        hilt_props = context.scene.sword_hilt
        decor_props = context.scene.sword_decoration
        
        # We always put crossguard at origin. We'll collect object references here.
        blade_obj = None
        crossguard_obj = None
        grip_obj = None
        pommel_obj = None
        
        # Generate in correct order so references line up visually:
        # 1. Crossguard at (0,0,0)
        # 2. Blade in +Y
        # 3. Grip in -Y
        # 4. Pommel further in -Y
        if sword_opts.enable_crossguard:
            crossguard_obj = self.create_crossguard(hilt_props)
        
        if sword_opts.enable_blade:
            blade_obj = self.create_blade(blade_props)
        
        if sword_opts.enable_grip:
            grip_obj = self.create_grip(hilt_props)
        
        if sword_opts.enable_pommel:
            pommel_obj = self.create_pommel(hilt_props)
        
        # Apply any requested decorative steps
        if sword_opts.enable_pattern_welding and decor_props.pattern_welding:
            if blade_obj:
                self.apply_pattern_welding(blade_obj, decor_props)
        if (sword_opts.enable_surface_decoration and
            decor_props.surface_decoration != 'NONE'):
            if blade_obj:
                self.apply_surface_decoration(blade_obj, decor_props)
        
        return {'FINISHED'}
    
    # --------------------------------------------------------------------
    # Create Blade: More realistic geometry, subdivisions, fuller, bevel
    # --------------------------------------------------------------------
    def create_blade(self, props):
        """
        Create a subdivided blade mesh around (0,0,0) as the base (crossguard),
        extending in the +Y direction. Includes:
         - Curved spine
         - Proper taper
         - Fuller (optional)
         - Edge bevel/chamfer
         - High subdivisions for smooth shape
        """
        bm = bmesh.new()
        
        length = props.blade_length * random.uniform(0.9, 1.1)
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
                amp = (length * 0.1) * random.uniform(0.8, 1.2)
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
            taper *= random.uniform(0.95, 1.05)
            
            # The cross-section width, thickness
            width = base_width * taper * random.uniform(0.9, 1.1)
            thickness = base_thickness * taper * random.uniform(0.9, 1.1)
            
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
            for i in range(len(all_ring_verts) - 1):
                # approximate top center
                ringA = all_ring_verts[i]
                ringB = all_ring_verts[i+1]
                # Let’s pick ringA[2] -> ringA[3], ringB[2] -> ringB[3]
                topA = ringA[2]
                topA2 = ringA[3]
                topB = ringB[2]
                topB2 = ringB[3]
                
                # Make edges if they don't exist
                e1 = bm.edges.get((topA, topA2))
                e2 = bm.edges.get((topA2, topB2))
                e3 = bm.edges.get((topB2, topB))
                e4 = bm.edges.get((topB, topA))
                # We'll skip checking for None for brevity
                if e1: groove_edges.append(e1)
                if e2: groove_edges.append(e2)
                if e3: groove_edges.append(e3)
                if e4: groove_edges.append(e4)
            
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
        
        # Subdivide the entire blade for smoother geometry
        edges_all = [e for e in bm.edges]
        bmesh.ops.subdivide_edges(
            bm,
            edges=edges_all,
            cuts=1,
            use_grid_fill=True
        )
        
        # If edge_bevels, apply a small chamfer along the outer perimeter
        if props.edge_bevels:
            # We'll try to detect "outer edges" by angle or by the fact
            # they only have 1 face or something similar
            perimeter_edges = []
            for e in bm.edges:
                # Check if it's an outer boundary (e.link_faces < 2)
                if len(e.link_faces) < 2:
                    perimeter_edges.append(e)
            
            bmesh.ops.bevel(
                bm,
                geom=perimeter_edges,
                offset=0.05,  # small chamfer
                segments=1,
                profile=0.7,
                affect='EDGES'
            )
        
        # Finally, ensure the tip is pointed
        # We can take the last ring and scale it down
        tip_ring = all_ring_verts[-1]
        bmesh.ops.scale(
            bm,
            vec=(0.1, 1.0, 0.1),  # flatten in X,Z
            verts=tip_ring
        )
        
        # Convert BMesh to Mesh
        mesh = bpy.data.meshes.new("Blade")
        bm.to_mesh(mesh)
        bm.free()
        
        # Create and link the object
        blade_obj = bpy.data.objects.new("Blade", mesh)
        bpy.context.collection.objects.link(blade_obj)
        
        # Move blade so its base is exactly at y=0 (the crossguard pivot).
        # Since we built from y=0 up, it's already aligned for the crossguard.
        
        return blade_obj
    
    # --------------------------------------------------------------------
    # Create Crossguard: At Origin
    # --------------------------------------------------------------------
    def create_crossguard(self, props):
        """
        Create a crossguard at (0,0,0). Blade extends +Y, grip extends -Y.
        We'll add subdivisions/bevels for a more realistic shape.
        """
        bm = bmesh.new()
        
        # Basic shape logic from previous code, with more detail
        if props.crossguard_style == 'STRAIGHT':
            width = random.uniform(18.0, 22.0)
            height = random.uniform(1.5, 2.5)
            depth = random.uniform(3.0, 5.0)
            bmesh.ops.create_cube(bm, size=1.0)
            bm.verts.ensure_lookup_table()
            bmesh.ops.scale(bm, vec=(width, depth, height), verts=bm.verts)
        
        elif props.crossguard_style == 'CURVED':
            # Let’s create a cylinder and then "bend" it or subdiv for shape
            rad = random.uniform(2.0, 3.0)
            length = random.uniform(20.0, 25.0)
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
            # Similar to before: circle + extrude. Then a bit of subdiv/bevel
            ring_radius = random.uniform(8.0, 12.0)
            ring_segments = 16
            geom = bmesh.ops.create_circle(bm, segments=ring_segments, radius=ring_radius)
            
            ret = bmesh.ops.extrude_edge_only(bm, edges=geom['edges'])
            bmesh.ops.translate(
                bm,
                verts=[v for v in ret['geom'] if isinstance(v, bmesh.types.BMVert)],
                vec=(0, random.uniform(-1.0, 1.0), random.uniform(1.0, 3.0))
            )
        
        # Let's do a quick subdiv to smooth
        edges_all = [e for e in bm.edges]
        bmesh.ops.subdivide_edges(
            bm,
            edges=edges_all,
            cuts=1,
            use_grid_fill=True
        )
        
        # Small bevel on perimeter edges
        perimeter_edges = []
        for e in bm.edges:
            if len(e.link_faces) < 2:
                perimeter_edges.append(e)
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
        
        crossguard_obj = bpy.data.objects.new("Crossguard", mesh)
        bpy.context.collection.objects.link(crossguard_obj)
        
        # Crossguard is at origin by design, orientation as is.
        return crossguard_obj
    
    # --------------------------------------------------------------------
    # Create Grip: Extends in -Y from Origin
    # --------------------------------------------------------------------
    def create_grip(self, props):
        """
        Create a grip that extends from y=0 (crossguard) to negative y.
        More subdivisions, plus optional wrapping details.
        """
        bm = bmesh.new()
        
        length = props.grip_length * random.uniform(0.9, 1.1)
        # We'll model a cylinder from 0 to -length on the Y-axis
        radius = random.uniform(1.2, 1.6)
        segments = 16
        
        geom = bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=segs,
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
        
        # Subdivide once for smoothness
        edges_all = [e for e in bm.edges]
        bmesh.ops.subdivide_edges(bm, edges=edges_all, cuts=1, use_grid_fill=True)
        
        # Light bevel on top/bottom edges
        perimeter_edges = []
        for e in bm.edges:
            if len(e.link_faces) < 2:
                perimeter_edges.append(e)
        bmesh.ops.bevel(
            bm,
            geom=perimeter_edges,
            offset=0.05,
            segments=1,
            profile=0.7,
            affect='EDGES'
        )
        
        # Additional wrap geometry
        if props.grip_style == 'LEATHER':
            self.add_leather_wrap(bm, length)
        elif props.grip_style == 'CORD':
            self.add_cord_wrap(bm, length)
        # (WIRE, WOOD omitted for brevity, can be added similarly)
        
        mesh = bpy.data.meshes.new("Grip")
        bm.to_mesh(mesh)
        bm.free()
        
        grip_obj = bpy.data.objects.new("Grip", mesh)
        bpy.context.collection.objects.link(grip_obj)
        
        return grip_obj
    
    # --------------------------------------------------------------------
    # Create Pommel: Attaches further at the base of the grip (-Y)
    # --------------------------------------------------------------------
    def create_pommel(self, props):
        """
        Create pommel geometry near the end of the grip (slightly below y = -grip_length).
        We'll place it so that its top is flush with y = -grip_length.
        """
        bm = bmesh.new()
        
        if props.pommel_type == 'WHEEL':
            segments = 32
            radius = random.uniform(2.5, 3.5)
            thickness = random.uniform(1.5, 2.5)
            # We'll create a cylinder for the wheel shape, then do some bevel
            geom = bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=segs,
                radius1=radius,
                radius2=radius,  # same radius => cylinder
                depth=thickness
            )

            
            # Rotate so the cylinder is along the Y-axis
            bmesh.ops.rotate(
                bm,
                verts=bm.verts,
                cent=(0, 0, 0),
                matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
            )
            
            # Shift so the top is at y=0, the bottom is at y=-thickness
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, -thickness/2, 0))
        
        elif props.pommel_type == 'SCENT_STOPPER':
            height = random.uniform(4.0, 6.0)
            segments = 12
            geom = bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=segments,
                radius1=random.uniform(2.0, 2.2),
                radius2=0.0,
                depth=height
            )
            
            # Rotate along Y
            bmesh.ops.rotate(
                bm,
                verts=bm.verts,
                cent=(0,0,0),
                matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
            )
            
            # Shift top to y=0
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, -height, 0))
        
        elif props.pommel_type == 'FISHTAIL':
            size = random.uniform(2.5, 3.5)
            bmesh.ops.create_cube(bm, size=size)
            bmesh.ops.scale(bm, vec=(1.0, 0.5, 1.5), verts=bm.verts)
            # Rotate to align along Y
            bmesh.ops.rotate(
                bm,
                verts=bm.verts,
                cent=(0,0,0),
                matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
            )
            # Shift top to y=0
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, -size/2, 0))
        
        elif props.pommel_type == 'PEAR':
            radius = random.uniform(2.0, 2.5)
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius)
            # Slight stretch
            stretch_factor = random.uniform(1.1, 1.3)
            bmesh.ops.scale(bm, vec=(1.0, stretch_factor, 1.0), verts=bm.verts)
            # Rotate so "pole" is along Y
            bmesh.ops.rotate(
                bm,
                verts=bm.verts,
                cent=(0,0,0),
                matrix=Matrix.Rotation(math.radians(-90.0), 3, 'X')
            )
            # Shift bottom to y=0
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, -radius, 0))
        
        # Subdivide once for smoothness
        edges_all = [e for e in bm.edges]
        bmesh.ops.subdivide_edges(bm, edges=edges_all, cuts=1, use_grid_fill=True)
        
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
        
        pommel_obj = bpy.data.objects.new("Pommel", mesh)
        bpy.context.collection.objects.link(pommel_obj)
        
        # Now place it so it sits at the bottom of the grip
        # We'll assume the grip length is in scene props:
        grip_length = props.grip_length  # We'll guess ~
        # Move pommel so top is at y = -grip_length
        # We already built the geometry so top is at y=0, bottom negative.
        # So let's just shift it by -grip_length
        pommel_obj.location.y = -grip_length
        
        return pommel_obj
    
    # --------------------------------------------------------------------
    # Wraps & Decorations
    # --------------------------------------------------------------------
    def add_leather_wrap(self, bm, length):
        """
        Creates banding geometry on top of the existing grip
        to simulate leather strips. We'll find outer edges and 'bevel' them,
        or add extra rings. For simplicity, let's just create extra circular loops.
        """
        # We'll add 3-6 'bands' around the grip, each a small ring extruded outward
        num_bands = random.randint(3, 6)
        
        # We'll place them along the grip (which goes from 0 to -length)
        for i in range(num_bands):
            band_y = -random.uniform(0.1, 0.9) * length
            # Create a ring at band_y
            ring_verts = []
            ring_segments = 16
            ring_radius = random.uniform(0.05, 0.15)
            
            for s in range(ring_segments):
                angle = 2 * math.pi * s / ring_segments
                x = math.cos(angle) * (1.0 + ring_radius)
                z = math.sin(angle) * (1.0 + ring_radius)
                v = bm.verts.new((x, band_y, z))
                ring_verts.append(v)
            
            # Connect ring edges
            for s in range(ring_segments):
                v1 = ring_verts[s]
                v2 = ring_verts[(s+1) % ring_segments]
                bm.edges.new((v1, v2))
    
    def add_cord_wrap(self, bm, length):
        """
        Create crisscross geometry on top of the grip surface.
        We'll form 2-3 spiral loops going one way, and 2-3 the other.
        """
        wraps_a = random.randint(2, 3)
        wraps_b = random.randint(2, 3)
        segments = 20
        
        # We'll do these wraps from y=0 to y=-length
        for w in range(wraps_a):
            angle_start = random.uniform(0, math.pi)
            pitch = random.uniform(0.2, 0.5)
            last_v = None
            for i in range(segments+1):
                t = i / segments
                y = -length * t
                angle = angle_start + (pitch * 2 * math.pi * t)
                r = 1.05  # slightly above the base radius 1.0
                x = math.cos(angle) * r
                z = math.sin(angle) * r
                v = bm.verts.new((x, y, z))
                if last_v:
                    bm.edges.new((last_v, v))
                last_v = v
        
        for w in range(wraps_b):
            angle_start = random.uniform(0, math.pi)
            pitch = random.uniform(-0.5, -0.2)
            last_v = None
            for i in range(segments+1):
                t = i / segments
                y = -length * t
                angle = angle_start + (pitch * 2 * math.pi * t)
                r = 1.05
                x = math.cos(angle) * r
                z = math.sin(angle) * r
                v = bm.verts.new((x, y, z))
                if last_v:
                    bm.edges.new((last_v, v))
                last_v = v
    
    def apply_pattern_welding(self, obj, props):
        """
        Same as before: create or reuse a DamascusMaterial,
        randomize noise parameters, etc.
        """
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
        noise_tex.inputs['Scale'].default_value = random.uniform(5.0, 15.0)
        noise_tex.inputs['Detail'].default_value = 16.0
        noise_tex.inputs['Distortion'].default_value = random.uniform(0.5, 3.0)
        
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-100, 100)
        color_ramp.color_ramp.elements[0].position = 0.4
        color_ramp.color_ramp.elements[1].position = 0.6
        color_ramp.color_ramp.elements[0].color = (
            random.uniform(0.1, 0.3), 
            random.uniform(0.1, 0.3), 
            random.uniform(0.1, 0.3), 
            1
        )
        color_ramp.color_ramp.elements[1].color = (
            random.uniform(0.5, 0.9), 
            random.uniform(0.5, 0.9), 
            random.uniform(0.5, 0.9), 
            1
        )
        
        links.new(noise_tex.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], princ_bsdf.inputs['Base Color'])
        
        princ_bsdf.inputs['Metallic'].default_value = random.uniform(0.4, 0.9)
        princ_bsdf.inputs['Roughness'].default_value = random.uniform(0.1, 0.4)
        
        if not obj.data.materials:
            obj.data.materials.append(damascus_mat)
        else:
            obj.data.materials[0] = damascus_mat
    
    def apply_surface_decoration(self, obj, props):
        """
        Adds a Voronoi-based overlay for ETCHED, INLAID, or ENGRAVED.
        """
        if not obj.data.materials:
            mat = bpy.data.materials.new("SwordSurfaceBase")
            mat.use_nodes = True
            obj.data.materials.append(mat)
        else:
            mat = obj.data.materials[0]
        
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
            random.uniform(5.0, 15.0) * (1.0 / props.decoration_density)
        )
        
        if props.surface_decoration == 'ETCHED':
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.location = (-100, 200)
            bump_node.inputs['Strength'].default_value = random.uniform(0.1, 0.3)
            links.new(dec_tex.outputs['Distance'], bump_node.inputs['Height'])
            links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])
        
        elif props.surface_decoration == 'ENGRAVED':
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.location = (-100, 200)
            bump_node.inputs['Strength'].default_value = random.uniform(0.3, 0.6)
            links.new(dec_tex.outputs['Distance'], bump_node.inputs['Height'])
            links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])
        
        elif props.surface_decoration == 'INLAID':
            mix_node = nodes.new(type='ShaderNodeMixRGB')
            mix_node.location = (-100, 200)
            mix_node.inputs['Fac'].default_value = random.uniform(0.3, 0.7)
            # random bright metallic color for inlay
            mix_node.inputs['Color2'].default_value = (
                random.uniform(0.5, 1.0), 
                random.uniform(0.5, 1.0), 
                random.uniform(0.0, 0.3), 
                1.0
            )
            links.new(dec_tex.outputs['Distance'], mix_node.inputs['Fac'])
            links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])

# ------------------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------------------
class ZENV_PT_SwordPanel(bpy.types.Panel):
    """UI panel for the sword generator, providing controls for all sword customization options"""
    
    bl_label = "ITEM Sword Generator"
    bl_idname = "ZENV_PT_sword"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
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
    ZENV_PG_sword_options,
    ZENV_PG_sword_blade,
    ZENV_PG_sword_hilt,
    ZENV_PG_sword_decoration,
    ZENV_OT_generate_sword,
    ZENV_PT_SwordPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sword_options = PointerProperty(type=ZENV_PG_sword_options)
    bpy.types.Scene.sword_blade = PointerProperty(type=ZENV_PG_sword_blade)
    bpy.types.Scene.sword_hilt = PointerProperty(type=ZENV_PG_sword_hilt)
    bpy.types.Scene.sword_decoration = PointerProperty(type=ZENV_PG_sword_decoration)

def unregister():
    del bpy.types.Scene.sword_options
    del bpy.types.Scene.sword_blade
    del bpy.types.Scene.sword_hilt
    del bpy.types.Scene.sword_decoration
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
