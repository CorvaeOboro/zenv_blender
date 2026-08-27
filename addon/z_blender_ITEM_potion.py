#region META
bl_info = {
    "name": 'ITEM Potion Generator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Generate procedural potion bottles with modular components',
    "status": 'working',
    "approved": True,
    "group": 'Items',
    "group_prefix": 'ITEM',
    "group_order": 60,
    "addon_order": 10,
    "tags": ['item', 'potion', 'bottle', 'procedural', 'fantasy', 'generator'],
    "description_short": 'generate procedural potion bottles with modular components',
    "description_medium": 'Generates procedural potion bottles with modular components: glass bottle (Catmull-Rom spline profile spun around Z axis), liquid fill with surface effects, cork stopper with spiral groove and wood-grain shader, neck decorations, toppers, interior effects, and base decorations. Configurable dimensions, fill level, colors, and decoration types.',
    "description_long": """
POTION GENERATOR
- generates procedural potion bottles with modular components
- useful for creating fantasy potions with modular decorative elements
""",
    "image_overview": 'zenv_blender_ITEM_potion.png',
    "addon_image": 'zenv_blender_ITEM_potion.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import bmesh
import math
import random
import time
from mathutils import Vector, Matrix
#endregion


#region MATS
# Material creation helpers for potion components.

class ZENV_PotionGenerator_Materials:
    """Material creation for potion components"""
    
    @classmethod
    def create_glass_material(cls):
        """Create glass material for bottle"""
        mat = bpy.data.materials.new(name="Potion_Glass")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = False
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF for glass
        principled.inputs['Base Color'].default_value = (0.9, 0.92, 0.95, 1.0)  # Slight blue tint
        principled.inputs['Metallic'].default_value = 0.0
        principled.inputs['Roughness'].default_value = 0.1  # Slightly rough for realism
        principled.inputs['IOR'].default_value = 1.45  # Glass IOR
        principled.inputs['Transmission Weight'].default_value = 0.9  # Transparent
        principled.inputs['Alpha'].default_value = 0.5  # Semi-transparent for viewport visibility
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        return mat

    @classmethod
    def create_liquid_material(cls, color):
        """Create liquid material with subsurface and volume"""
        mat = bpy.data.materials.new(name="Potion_Liquid")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = False
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF for liquid with subsurface
        # NOTE: Transmission Weight kept low so the Base Color is visible.
        #       High transmission turns the liquid into glass and hides the chosen color.
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Metallic'].default_value = 0.0
        principled.inputs['Roughness'].default_value = 0.05  # Smooth liquid surface
        principled.inputs['IOR'].default_value = 1.33  # Water IOR
        principled.inputs['Transmission Weight'].default_value = 0.05  # Mostly opaque so color reads
        principled.inputs['Alpha'].default_value = 1.0  # Fully opaque

        # Add subsurface scattering for depth. Subsurface Radius is in scene units,
        # so scaling the 0..1 color values makes the scattering visible.
        principled.inputs['Subsurface Weight'].default_value = 0.8
        principled.inputs['Subsurface Radius'].default_value = (
            max(color[0] * 5.0, 0.01),
            max(color[1] * 5.0, 0.01),
            max(color[2] * 5.0, 0.01),
        )
        principled.inputs['Subsurface Scale'].default_value = 0.15
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

        return mat

    @classmethod
    def create_basic_material(cls, name="Basic_Material", color=(0.5, 0.5, 0.5, 1.0), roughness=0.5, metallic=0.0):
        """Create a basic material for decorative elements"""
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Metallic'].default_value = metallic
        principled.inputs['Roughness'].default_value = roughness
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        return mat
#endregion


#region PROPS
# Property group for potion generator settings, registered on the Scene.

class ZENV_PG_PotionGenerator_Props(bpy.types.PropertyGroup):
    """Property group for potion generator settings"""
    # Main component toggles
    use_bottle: bpy.props.BoolProperty(
        name="Generate Bottle",
        description="Enable/disable bottle generation",
        default=True
    )
    
    use_liquid: bpy.props.BoolProperty(
        name="Generate Liquid",
        description="Enable/disable liquid generation",
        default=True
    )
    
    use_neck: bpy.props.BoolProperty(
        name="Add Neck Decorations",
        description="Enable/disable neck decorations",
        default=False
    )
    
    use_topper: bpy.props.BoolProperty(
        name="Add Topper",
        description="Enable/disable topper",
        default=True
    )
    
    use_interior: bpy.props.BoolProperty(
        name="Add Interior Effects",
        description="Enable/disable interior effects",
        default=False
    )
    
    use_base: bpy.props.BoolProperty(
        name="Add Base Decorations",
        description="Enable/disable base decorations",
        default=False
    )

    # Bottle properties
    bottle_height: bpy.props.FloatProperty(
        name="Bottle Height",
        default=1.0,
        min=0.1,
        max=5.0
    )
    
    bottle_width: bpy.props.FloatProperty(
        name="Bottle Width",
        default=0.5,
        min=0.1,
        max=2.0
    )

    # Liquid properties
    liquid_fill_amount: bpy.props.FloatProperty(
        name="Fill Amount",
        description="How full the bottle is",
        default=0.7,
        min=0.0,
        max=1.0
    )

    liquid_noise_amount: bpy.props.FloatProperty(
        name="Surface Noise",
        description="Amount of surface distortion",
        default=0.3,
        min=0.0,
        max=1.0
    )

    liquid_noise_scale: bpy.props.FloatProperty(
        name="Noise Scale",
        description="Scale of the surface noise",
        default=2.0,
        min=0.1,
        max=10.0
    )

    liquid_color: bpy.props.FloatVectorProperty(
        name="Liquid Color",
        description="Color of the potion liquid",
        subtype='COLOR',
        default=(0.2, 0.8, 0.2, 1.0),
        size=4,
        min=0.0,
        max=1.0
    )

    # Neck decorations
    neck_decoration_type: bpy.props.EnumProperty(
        name="Neck Decoration Type",
        items=[
            ('NONE', "None", "No neck decoration"),
            ('CLOTH', "Wrapped Cloth", "Cloth wrapped around neck"),
            ('CHAINS', "Wrapped Chains", "Chains wrapped around neck"),
            ('ROPE', "Tied Rope", "Rope tied around neck")
        ],
        default='NONE'
    )

    # Topper decorations
    topper_type: bpy.props.EnumProperty(
        name="Topper Type",
        items=[
            ('NONE', "None", "No topper"),
            ('CORK', "Cork", "Simple cork stopper"),
            ('SPHERE', "Sphere", "Decorative sphere"),
            ('SPIRAL_SPHERE', "Spiral Sphere", "Sphere with spiral wrap"),
            ('SPIRAL_CURL', "Spiral Curl", "Curled spiral decoration")
        ],
        default='CORK'
    )

    # Interior effects
    interior_effect_type: bpy.props.EnumProperty(
        name="Interior Effect Type",
        items=[
            ('NONE', "None", "No interior effect"),
            ('BUBBLES', "Bubbles", "Floating bubbles"),
            ('LIGHT', "Light Spark", "Glowing light effect"),
            ('TENTACLES', "Tentacles", "Moving tentacles"),
            ('VORTEX', "Spiral Vortex", "Swirling vortex effect")
        ],
        default='NONE'
    )

    # Base decorations
    base_type: bpy.props.EnumProperty(
        name="Base Type",
        items=[
            ('NONE', "None", "No base decoration"),
            ('TEETH', "Teeth", "Decorative teeth around base"),
            ('CLAWS', "Claws", "Claw feet"),
            ('CLOTH', "Wrapped Cloth", "Cloth wrapped around base")
        ],
        default='NONE'
    )

    # Cork properties
    cork_height_factor: bpy.props.FloatProperty(
        name="Cork Height",
        description="Height of the cork relative to bottle height",
        default=0.22,
        min=0.05,
        max=0.4
    )
    
    cork_width_factor: bpy.props.FloatProperty(
        name="Cork Width",
        description="Width of the cork relative to neck width",
        default=0.85,
        min=0.5,
        max=1.0
    )
    
    cork_detail: bpy.props.FloatProperty(
        name="Cork Detail",
        description="Amount of surface detail on the cork",
        default=0.5,
        min=0.0,
        max=1.0
    )
    
    cork_spiral_turns: bpy.props.IntProperty(
        name="Spiral Turns",
        description="Number of turns in the cork spiral",
        default=3,
        min=1,
        max=10
    )
    
    cork_spiral_depth: bpy.props.FloatProperty(
        name="Spiral Depth",
        description="Depth of the spiral groove",
        default=0.3,
        min=0.1,
        max=0.8
    )

    seed: bpy.props.IntProperty(
        name="Random Seed",
        description="Seed for reproducible cork skew and other random effects (0 = random)",
        default=0,
        min=0,
    )
#endregion


#region OP
# Operator that generates a procedural potion bottle with modular components.

class ZENV_OT_PotionGenerator(bpy.types.Operator):
    """Generate a procedural potion bottle with modular components"""
    bl_idname = "zenv.generate_potion"
    bl_label = "Generate Potion"
    bl_options = {'REGISTER', 'UNDO'}

    # Bottle/liquid profile control points (normalized: x=width factor, z=height factor)
    BOTTLE_CONTROL_POINTS = [
        (0.05, 0.0),    # Base center
        (0.7, 0.05),    # Base edge
        (1.0, 0.3),     # Belly (widest point)
        (0.4, 0.65),    # Shoulder
        (0.3, 0.75),    # Neck start
        (0.25, 0.95),   # Neck
        (0.25, 1.0),    # Top opening
    ]

    LIQUID_CONTROL_POINTS = [
        (0.05, 0.0),    # Base center
        (0.7, 0.05),    # Base edge
        (1.0, 0.3),     # Belly (widest point)
        (0.4, 0.65),    # Shoulder
        (0.3, 0.75),    # Neck start
    ]

    @classmethod
    def catmull_rom_point(cls, p0, p1, p2, p3, t):
        """Calculate a point on a Catmull-Rom spline segment.

        Args:
            p0, p1, p2, p3: Four control points (tuples of (x, z)).
            t: Parameter in [0, 1) within the segment p1->p2.

        Returns:
            (x, z) tuple for the interpolated point.
        """
        t2 = t * t
        t3 = t2 * t

        x = 0.5 * ((2 * p1[0]) +
                  (-p0[0] + p2[0]) * t +
                  (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0]) * t2 +
                  (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0]) * t3)

        z = 0.5 * ((2 * p1[1]) +
                  (-p0[1] + p2[1]) * t +
                  (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1]) * t2 +
                  (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1]) * t3)

        return (x, z)

    @classmethod
    def interpolate_profile(cls, control_points, segments_per_section=16):
        """Generate a smooth profile through control points via Catmull-Rom.

        Returns a list of (x, z) tuples.
        """
        profile_points = []
        for i in range(len(control_points) - 1):
            p0 = control_points[max(0, i - 1)]
            p1 = control_points[i]
            p2 = control_points[i + 1]
            p3 = control_points[min(len(control_points) - 1, i + 2)]
            for j in range(segments_per_section):
                t = j / segments_per_section
                x, z = cls.catmull_rom_point(p0, p1, p2, p3, t)
                profile_points.append((x, z))
        profile_points.append(control_points[-1])
        return profile_points

    def execute(self, context):
        props = context.scene.zenv_potion_props

        # Track created objects for cleanup on failure
        created_objects = []

        try:
            wm = context.window_manager
            wm.progress_begin(0, 6)

            # Create main bottle
            wm.progress_update(0)
            if props.use_bottle:
                bottle = self.create_bottle(context, props)
                if bottle:
                    created_objects.append(bottle)
            else:
                bottle = None

            # Create liquid
            wm.progress_update(1)
            if props.use_liquid:
                if bottle is None:
                    bottle = self.create_bottle(context, props)
                    if bottle:
                        created_objects.append(bottle)
                liquid = self.create_liquid(context, bottle, props)
                if liquid:
                    created_objects.append(liquid)
            else:
                liquid = None

            # Add decorations
            wm.progress_update(2)
            self.add_neck_decorations(context, bottle, props)
            wm.progress_update(3)
            self.add_topper(context, bottle, props)
            wm.progress_update(4)
            self.add_interior_effects(context, liquid, props)
            wm.progress_update(5)
            self.add_base_decoration(context, bottle, props)

            wm.progress_update(6)
            wm.progress_end()

            self.report({'INFO'}, "Potion generated successfully.")
            return {'FINISHED'}

        except Exception as e:
            # Clean up partially created objects to avoid datablock pollution
            for obj in created_objects:
                if obj and obj.name in bpy.data.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
            self.report({'ERROR'}, f"Failed to generate potion: {e}")
            return {'CANCELLED'}

    def create_bottle(self, context, props):
        """Create the main bottle mesh using spin operation with HIGH RESOLUTION curved profile"""
        height = props.bottle_height
        width = props.bottle_width
        
        # Create empty mesh
        mesh = bpy.data.meshes.new("Potion_Bottle_Mesh")
        bottle = bpy.data.objects.new("Potion_Bottle", mesh)
        context.collection.objects.link(bottle)
        context.view_layer.objects.active = bottle
        bottle.select_set(True)
        
        # Create bottle profile with SMOOTH CURVES using interpolation
        bm = bmesh.new()

        # Generate smooth profile via shared Catmull-Rom interpolation
        raw_points = self.interpolate_profile(self.BOTTLE_CONTROL_POINTS)
        profile_points = [(x * width, z * height) for x, z in raw_points]

        # Create vertices for HIGH RESOLUTION profile
        verts = []
        for x, z in profile_points:
            v = bm.verts.new((x, 0, z))
            verts.append(v)
        
        # Create edges connecting all vertices
        for i in range(len(verts) - 1):
            bm.edges.new([verts[i], verts[i + 1]])
        
        bm.to_mesh(mesh)
        bm.free()
        
        # Enter edit mode and spin the profile around Z axis
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Spin with HIGH STEPS for smooth revolution
        bpy.ops.mesh.spin(
            steps=72,  # High step count for smooth circular revolution
            angle=math.radians(360),
            center=(0, 0, 0),
            axis=(0, 0, 1),
            use_auto_merge=True
        )
        
        # Clean up duplicate vertices
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Ensure bottle is selected and active
        bpy.ops.object.select_all(action='DESELECT')
        bottle.select_set(True)
        context.view_layer.objects.active = bottle
        
        # Add Solidify modifier for consistent wall thickness (hollow bottle)
        solidify = bottle.modifiers.new(name="Glass_Walls", type='SOLIDIFY')
        solidify.thickness = props.bottle_width * 0.04  # 4% wall thickness
        solidify.offset = -1.0  # Solidify inward to keep outer shape
        solidify.use_even_offset = True
        solidify.use_quality_normals = True
        solidify.use_rim = True  # Keep top rim open
        bpy.ops.object.modifier_apply(modifier=solidify.name)
        
        # Apply smooth shading
        bpy.ops.object.shade_smooth()
        
        # Add materials AFTER conversion
        glass_mat = ZENV_PotionGenerator_Materials.create_glass_material()
        if bottle.data.materials:
            bottle.data.materials[0] = glass_mat
        else:
            bottle.data.materials.append(glass_mat)
        
        # Ensure all faces use the material
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bottle.active_material_index = 0
        bpy.ops.object.material_slot_assign()
        bpy.ops.object.mode_set(mode='OBJECT')

        # Add a thickened glass "lip" (torus) at the top opening of the bottle.
        self.create_lip(context, bottle, props)

        return bottle

    def create_lip(self, context, bottle, props):
        """Create a thickened glass lip (torus) around the bottle's top opening.

        The torus sits at the rim of the neck and shares the bottle's glass
        material so it reads as a continuous thickened rim.
        """
        neck_radius = props.bottle_width * 0.25  # Matches bottle profile neck
        wall_thickness = props.bottle_width * 0.04  # Same as Solidify walls
        # Minor radius is thicker than the wall so the lip reads as a real rim
        lip_minor_radius = wall_thickness * 2.5

        bpy.ops.mesh.primitive_torus_add(
            major_radius=neck_radius,
            minor_radius=lip_minor_radius,
            major_segments=64,
            minor_segments=16,
            location=(0.0, 0.0, props.bottle_height),
        )
        lip = context.active_object
        lip.name = "Potion_Lip"

        # Smooth shading
        bpy.ops.object.shade_smooth()

        # Reuse the bottle's glass material if present, otherwise create one
        if bottle.data.materials:
            glass_mat = bottle.data.materials[0]
        else:
            glass_mat = ZENV_PotionGenerator_Materials.create_glass_material()
        lip.data.materials.clear()
        lip.data.materials.append(glass_mat)

        # Assign material to all faces
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        lip.active_material_index = 0
        bpy.ops.object.material_slot_assign()
        bpy.ops.object.mode_set(mode='OBJECT')

        # Parent to bottle
        lip.parent = bottle

        return lip

    def create_liquid(self, context, bottle, props):
        """Create liquid using SAME CURVE as bottle for matching sync"""
        height = props.bottle_height
        width = props.bottle_width
        
        # Create liquid mesh
        mesh = bpy.data.meshes.new("Potion_Liquid_Mesh")
        liquid = bpy.data.objects.new("Potion_Liquid", mesh)
        context.collection.objects.link(liquid)
        context.view_layer.objects.active = liquid
        liquid.select_set(True)
        
        bm = bmesh.new()

        # Generate smooth profile via shared Catmull-Rom interpolation
        # Uses liquid control points (subset of bottle) with inset factor
        inset_factor = 0.92  # Scale down to 92% to fit inside glass
        raw_points = self.interpolate_profile(self.LIQUID_CONTROL_POINTS)
        liquid_points = [(x * width * inset_factor, z * height) for x, z in raw_points]

        # Create vertices
        verts = []
        for x, z in liquid_points:
            v = bm.verts.new((x, 0, z))
            verts.append(v)
        
        # Create edges
        for i in range(len(verts) - 1):
            bm.edges.new([verts[i], verts[i + 1]])
        
        bm.to_mesh(mesh)
        bm.free()
        
        # Spin to create liquid volume
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        bpy.ops.mesh.spin(
            steps=64,
            angle=math.radians(360),
            center=(0, 0, 0),
            axis=(0, 0, 1),
            use_auto_merge=True
        )
        
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Cut liquid to fill level
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bm = bmesh.from_edit_mesh(liquid.data)
        
        # Calculate fill height
        max_z = max(v.co.z for v in bm.verts)
        min_z = min(v.co.z for v in bm.verts)
        fill_height = min_z + (max_z - min_z) * props.liquid_fill_amount
        
        # Delete vertices above fill level
        verts_to_delete = [v for v in bm.verts if v.co.z > fill_height]
        bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
        
        # Fill top hole
        bpy.ops.mesh.select_all(action='SELECT')
        bmesh.update_edit_mesh(liquid.data)
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Smooth shading
        bpy.ops.object.shade_smooth()
        
        # Remesh for clean topology
        remesh = liquid.modifiers.new(name="Smooth_Surface", type='REMESH')
        remesh.mode = 'SMOOTH'
        remesh.octree_depth = 6
        remesh.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=remesh.name)
        
        # Optional: Add subtle surface displacement
        if props.liquid_noise_amount > 0:
            displace = liquid.modifiers.new(name="Surface_Ripples", type='DISPLACE')
            tex = bpy.data.textures.new("Liquid_Noise", type='MUSGRAVE')
            tex.noise_scale = props.liquid_noise_scale * 3.0
            tex.noise_intensity = 0.5
            displace.texture = tex
            displace.strength = props.liquid_noise_amount * 0.001 * props.bottle_width
            displace.direction = 'NORMAL'
            bpy.ops.object.modifier_apply(modifier=displace.name)
        
        # Subdivision for smooth surface
        subsurf = liquid.modifiers.new(name="Smooth", type='SUBSURF')
        subsurf.levels = 1
        subsurf.render_levels = 2
        bpy.ops.object.modifier_apply(modifier=subsurf.name)
        
        # Assign liquid material
        liquid_mat = ZENV_PotionGenerator_Materials.create_liquid_material(props.liquid_color)
        liquid.data.materials.clear()
        liquid.data.materials.append(liquid_mat)
        
        # Ensure all faces have material
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        liquid.active_material_index = 0
        bpy.ops.object.material_slot_assign()
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Parent to bottle but keep as separate object
        liquid.parent = bottle
        
        return liquid

    def add_neck_decorations(self, context, bottle, props):
        """Add decorations around the bottle neck"""
        if not props.use_neck:
            return
            
        if props.neck_decoration_type == 'CLOTH':
            # Create a cloth band wrapped around the bottle neck.
            # Neck geometry (matches bottle profile): radius = width*0.25,
            # spanning roughly z = 0.75..0.95 of bottle height.
            neck_radius = props.bottle_width * 0.25
            cloth_radius = neck_radius * 1.08  # Slightly outside the glass
            cloth_height = props.bottle_height * 0.12  # Short band
            neck_mid_z = props.bottle_height * 0.85  # Center of neck region

            bpy.ops.mesh.primitive_cylinder_add(
                radius=cloth_radius,
                depth=cloth_height,
                vertices=48,
                location=(0.0, 0.0, neck_mid_z),
            )
            cloth = context.active_object
            cloth.name = "Neck_Cloth"

            # Remove top and bottom caps so it is an open band (cloth wrap)
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bm = bmesh.from_edit_mesh(cloth.data)
            bm.faces.ensure_lookup_table()
            for f in bm.faces:
                # Caps have normals nearly parallel to Z
                if abs(f.normal.z) > 0.9:
                    f.select_set(True)
            bmesh.update_edit_mesh(cloth.data)
            bpy.ops.mesh.delete(type='FACE')
            bpy.ops.object.mode_set(mode='OBJECT')

            # Solidify to give the cloth some thickness
            solidify = cloth.modifiers.new(name="Cloth_Thickness", type='SOLIDIFY')
            solidify.thickness = props.bottle_width * 0.01
            solidify.offset = 0.0
            bpy.ops.object.modifier_apply(modifier=solidify.name)

            # Subtle displacement for cloth folds
            displace = cloth.modifiers.new(name="Cloth_Folds", type='DISPLACE')
            fold_tex = bpy.data.textures.new("Cloth_Folds", type='STUCCI')
            fold_tex.noise_scale = 0.4
            fold_tex.turbulence = 2.0
            displace.texture = fold_tex
            displace.strength = props.bottle_width * 0.015
            displace.direction = 'NORMAL'
            bpy.ops.object.modifier_apply(modifier=displace.name)

            # Smooth shading
            bpy.ops.object.shade_smooth()

            # Add material
            cloth_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Neck_Cloth_Material",
                color=(0.5, 0.2, 0.1, 1.0),
                roughness=0.9,
                metallic=0.0
            )
            cloth.data.materials.clear()
            cloth.data.materials.append(cloth_mat)

            # Assign material to all faces
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            cloth.active_material_index = 0
            bpy.ops.object.material_slot_assign()
            bpy.ops.object.mode_set(mode='OBJECT')

            cloth.parent = bottle

        elif props.neck_decoration_type == 'CHAINS':
            # Create chain
            bpy.ops.curve.primitive_bezier_circle_add()
            chain = context.active_object
            chain.name = "Neck_Chain"
            # Add material
            chain_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Chain_Material",
                color=(0.7, 0.7, 0.7, 1.0),
                roughness=0.3,
                metallic=0.9
            )
            chain.data.materials.append(chain_mat)
            # Add array modifier for chain links
            chain.parent = bottle

        elif props.neck_decoration_type == 'ROPE':
            # Create rope
            bpy.ops.curve.primitive_bezier_circle_add()
            rope = context.active_object
            rope.name = "Neck_Rope"
            # Add material
            rope_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Rope_Material",
                color=(0.6, 0.5, 0.3, 1.0),
                roughness=0.8,
                metallic=0.0
            )
            rope.data.materials.append(rope_mat)
            # Add curve modifiers for rope twist
            rope.parent = bottle

    def create_cork(self, context, bottle, props):
        """Create a detailed cork stopper with wood grain"""
        # Get bottle dimensions for cork sizing
        neck_radius = props.bottle_width * 0.25  # From bottle profile
        cork_radius = neck_radius * props.cork_width_factor
        cork_height = props.bottle_height * props.cork_height_factor
        
        # Create base cylinder with high resolution
        bpy.ops.mesh.primitive_cylinder_add(
            radius=cork_radius,
            depth=cork_height,
            vertices=32  # Increased from 16 for finer detail
        )
        cork = context.active_object
        cork.name = "Bottle_Cork"
        
        # Position cork at bottle neck
        cork.location = Vector((0, 0, props.bottle_height * 0.95))
        
        # Add subtle skew for wonky look (seeded for reproducibility).
        # Range kept small so the cork stays mostly straight, not weirdly tilted.
        rng = random.Random(props.seed if props.seed > 0 else None)
        skew_angle_x = rng.uniform(-0.03, 0.03)
        skew_angle_y = rng.uniform(-0.03, 0.03)
        cork.rotation_euler.x += skew_angle_x
        cork.rotation_euler.y += skew_angle_y
        
        # Create spiral pattern using curve
        bpy.ops.curve.primitive_bezier_circle_add(
            radius=cork_radius * 0.8,
            enter_editmode=False,
            align='WORLD',
            location=cork.location  # Position at creation
        )
        spiral = context.active_object
        spiral.name = "Cork_Spiral"
        
        # Add screw modifier to create spiral
        screw = spiral.modifiers.new(name="Screw", type='SCREW')
        screw.axis = 'Z'
        screw.screw_offset = cork_height / props.cork_spiral_turns
        screw.iterations = props.cork_spiral_turns
        screw.steps = 16
        screw.render_steps = 16
        
        # Select and convert spiral to mesh
        bpy.ops.object.select_all(action='DESELECT')
        spiral.select_set(True)
        context.view_layer.objects.active = spiral
        bpy.ops.object.convert(target='MESH')
        
        # Add thickness to spiral
        solidify = spiral.modifiers.new(name="Solidify", type='SOLIDIFY')
        solidify.thickness = cork_radius * 0.1 * props.cork_spiral_depth
        bpy.ops.object.modifier_apply(modifier=solidify.name)
        
        # Switch back to cork as active object
        bpy.ops.object.select_all(action='DESELECT')
        cork.select_set(True)
        context.view_layer.objects.active = cork
        
        # Boolean cut spiral from cork (ensure cork is active)
        context.view_layer.objects.active = cork
        bool_spiral = cork.modifiers.new(name="Boolean_Spiral", type='BOOLEAN')
        bool_spiral.object = spiral
        bool_spiral.operation = 'DIFFERENCE'
        
        # Add high-res remesh for finer detail
        remesh = cork.modifiers.new(name="Remesh", type='REMESH')
        remesh.mode = 'SHARP'
        remesh.octree_depth = 7  # Higher resolution
        remesh.scale = 0.99
        remesh.use_smooth_shade = True
        
        # Add displacement for wood grain
        displace = cork.modifiers.new(name="Displace", type='DISPLACE')
        wood_tex = bpy.data.textures.new("Wood_Grain", type='WOOD')
        wood_tex.noise_scale = 0.5
        wood_tex.noise_basis = 'ORIGINAL_PERLIN'
        wood_tex.wood_type = 'RINGS'
        wood_tex.turbulence = 5
        displace.texture = wood_tex
        displace.strength = props.cork_detail * 0.02 * cork_radius
        
        # Add noise texture for surface detail
        displace_noise = cork.modifiers.new(name="Surface_Detail", type='DISPLACE')
        noise_tex = bpy.data.textures.new("Cork_Surface", type='MUSGRAVE')
        noise_tex.noise_scale = 1.0
        noise_tex.noise_intensity = 1.0
        noise_tex.nabla = 0.03
        displace_noise.texture = noise_tex
        displace_noise.strength = props.cork_detail * 0.01 * cork_radius
        
        # Add subsurf for final smoothing
        subsurf = cork.modifiers.new(name="Subsurf", type='SUBSURF')
        subsurf.levels = 2
        subsurf.render_levels = 3
        
        # Create material with UNIQUE name
        mat_name = f"Cork_Material_{int(time.time() * 1000)}"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes for wood material
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        wood_noise = nodes.new('ShaderNodeTexNoise')  # Changed from TexMusgrave for Blender 4.x
        color_ramp = nodes.new('ShaderNodeValToRGB')
        mapping = nodes.new('ShaderNodeMapping')
        texcoord = nodes.new('ShaderNodeTexCoord')
        bump = nodes.new('ShaderNodeBump')
        
        # Setup noise texture for cork grain
        wood_noise.inputs['Scale'].default_value = 3.0
        wood_noise.inputs['Detail'].default_value = 2.0
        wood_noise.inputs['Roughness'].default_value = 0.5  # Changed from Dimension for Noise node
        
        # Setup color ramp for cork colors
        color_ramp.color_ramp.elements[0].position = 0.35
        color_ramp.color_ramp.elements[0].color = (0.45, 0.28, 0.15, 1)  # Darker cork
        color_ramp.color_ramp.elements[1].position = 0.65
        color_ramp.color_ramp.elements[1].color = (0.65, 0.42, 0.22, 1)  # Lighter cork
        
        # Setup bump for surface texture
        bump.inputs['Strength'].default_value = 0.8
        bump.inputs['Distance'].default_value = 0.015
        
        # Setup principled BSDF for cork material
        principled.inputs['Roughness'].default_value = 0.85  # Cork is rough
        principled.inputs['Specular IOR Level'].default_value = 0.15  # Low specularity
        principled.inputs['Sheen Weight'].default_value = 0.2  # Slight sheen for realism
        
        # Link nodes
        links.new(texcoord.outputs['Generated'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], wood_noise.inputs['Vector'])
        links.new(wood_noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(wood_noise.outputs['Fac'], bump.inputs['Height'])
        links.new(color_ramp.outputs['Color'], principled.inputs['Base Color'])
        links.new(bump.outputs['Normal'], principled.inputs['Normal'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        # ASSIGN MATERIAL IMMEDIATELY after creation, BEFORE modifiers
        cork.data.materials.clear()
        cork.data.materials.append(mat)

        # Apply modifiers in correct order AFTER assigning material
        context.view_layer.objects.active = cork
        for modifier in cork.modifiers:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except Exception:
                pass
        
        # Invariant: Delete the spiral helper object
        if spiral and spiral.name in bpy.data.objects:
            bpy.data.objects.remove(spiral, do_unlink=True)
        
        # Ensure cork is selected and active
        bpy.ops.object.select_all(action='DESELECT')
        cork.select_set(True)
        context.view_layer.objects.active = cork
        
        # Verify material is STILL assigned after modifiers
        if len(cork.data.materials) == 0:
            cork.data.materials.append(mat)
        
        # FORCE material assignment to all faces
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        cork.active_material_index = 0
        bpy.ops.object.material_slot_assign()
        bpy.ops.object.mode_set(mode='OBJECT')

        # Apply smooth shading BEFORE parenting
        bpy.ops.object.shade_smooth()

        # Parent to bottle LAST (after everything else is done)
        cork.parent = bottle

        return cork

    def add_topper(self, context, bottle, props):
        """Add topper decoration"""
        if not props.use_topper:
            return
            
        if props.topper_type == 'CORK':
            self.create_cork(context, bottle, props)

        elif props.topper_type == 'SPHERE':
            bpy.ops.mesh.primitive_uv_sphere_add()
            sphere = context.active_object
            sphere.name = "Bottle_Topper"
            # Position and scale sphere
            sphere.location = Vector((0, 0, props.bottle_height * 1.05))
            sphere.scale = Vector((0.15, 0.15, 0.15))
            # Add material
            sphere_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Topper_Material",
                color=(0.8, 0.6, 0.2, 1.0),
                roughness=0.3,
                metallic=0.8
            )
            sphere.data.materials.append(sphere_mat)
            bpy.ops.object.shade_smooth()
            sphere.parent = bottle

        elif props.topper_type in {'SPIRAL_SPHERE', 'SPIRAL_CURL'}:
            bpy.ops.curve.primitive_bezier_circle_add()
            spiral = context.active_object
            spiral.name = "Bottle_Spiral"
            # Add material
            spiral_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Spiral_Material",
                color=(0.8, 0.6, 0.2, 1.0),
                roughness=0.4,
                metallic=0.7
            )
            spiral.data.materials.append(spiral_mat)
            # Add curve modifiers for spiral shape
            spiral.parent = bottle

    def add_interior_effects(self, context, liquid, props):
        """Add effects inside the potion"""
        if not props.use_interior:
            return
            
        if props.interior_effect_type == 'BUBBLES':
            # Create actual bubble spheres scattered inside the liquid volume.
            # A particle system with no render object shows nothing in Blender 4.x,
            # so we instantiate real small spheres within the liquid bounds.
            if liquid is None:
                return

            # Compute liquid bounding box to place bubbles inside
            liquid_bbox = [Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))]
            for v in liquid.data.vertices:
                co = liquid.matrix_world @ v.co
                if co.x < liquid_bbox[0].x: liquid_bbox[0].x = co.x
                if co.y < liquid_bbox[0].y: liquid_bbox[0].y = co.y
                if co.z < liquid_bbox[0].z: liquid_bbox[0].z = co.z
                if co.x > liquid_bbox[1].x: liquid_bbox[1].x = co.x
                if co.y > liquid_bbox[1].y: liquid_bbox[1].y = co.y
                if co.z > liquid_bbox[1].z: liquid_bbox[1].z = co.z

            min_co, max_co = liquid_bbox
            center = (min_co + max_co) * 0.5
            # Inset so bubbles sit inside the liquid, not on the glass
            inset_xy = (max_co.x - min_co.x) * 0.25
            inset_z_top = (max_co.z - min_co.z) * 0.15
            inset_z_bot = (max_co.z - min_co.z) * 0.05

            rng = random.Random(props.seed if props.seed > 0 else None)
            bubble_count = 50
            bubble_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Bubble_Material",
                color=(0.9, 0.95, 1.0, 1.0),
                roughness=0.0,
                metallic=0.0,
            )
            # Make bubble material slightly transparent
            if bubble_mat.use_nodes:
                bsdf = bubble_mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs['Transmission Weight'].default_value = 0.8
                    bsdf.inputs['Alpha'].default_value = 0.6
                    bubble_mat.blend_method = 'BLEND'

            bubbles_parent = None
            for i in range(bubble_count):
                # Random position inside the inset liquid box
                x = rng.uniform(min_co.x + inset_xy, max_co.x - inset_xy)
                y = rng.uniform(min_co.y + inset_xy, max_co.y - inset_xy)
                z = rng.uniform(min_co.z + inset_z_bot, max_co.z - inset_z_top)
                # Random small radius
                radius = rng.uniform(
                    props.bottle_width * 0.005,
                    props.bottle_width * 0.02,
                )

                bpy.ops.mesh.primitive_uv_sphere_add(
                    radius=radius,
                    segments=12,
                    ring_count=8,
                    location=(x, y, z),
                )
                bubble = context.active_object
                bubble.name = f"Potion_Bubble_{i}"
                bubble.data.materials.clear()
                bubble.data.materials.append(bubble_mat)
                bpy.ops.object.shade_smooth()
                bubble.parent = liquid

        elif props.interior_effect_type == 'LIGHT':
            # Add point light for spark effect
            bpy.ops.object.light_add(type='POINT')
            light = context.active_object
            light.name = "Potion_Spark"
            light.parent = liquid

        elif props.interior_effect_type == 'TENTACLES':
            # Create curves for tentacles
            for i in range(3):
                bpy.ops.curve.primitive_bezier_curve_add()
                tentacle = context.active_object
                tentacle.name = f"Potion_Tentacle_{i}"
                tentacle.parent = liquid

        elif props.interior_effect_type == 'VORTEX':
            # Create spiral curve for vortex
            bpy.ops.curve.primitive_bezier_spiral_add()
            vortex = context.active_object
            vortex.name = "Potion_Vortex"
            vortex.parent = liquid

    def add_base_decoration(self, context, bottle, props):
        """Add decoration to bottle base"""
        if not props.use_base:
            return
            
        if props.base_type == 'TEETH':
            # Create teeth around base
            teeth_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Teeth_Material",
                color=(0.9, 0.9, 0.85, 1.0),
                roughness=0.6,
                metallic=0.0
            )
            for i in range(8):
                angle = (i / 8) * 2 * math.pi
                bpy.ops.mesh.primitive_cone_add(radius1=0.1, depth=0.2)
                tooth = context.active_object
                tooth.name = f"Base_Tooth_{i}"
                # Position around the base perimeter
                base_radius = props.bottle_width * 0.7
                tooth.location = (math.cos(angle) * base_radius,
                                  math.sin(angle) * base_radius,
                                  0.1)
                tooth.data.materials.append(teeth_mat)
                tooth.parent = bottle

        elif props.base_type == 'CLAWS':
            # Create claw feet
            claw_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Claw_Material",
                color=(0.3, 0.25, 0.2, 1.0),
                roughness=0.7,
                metallic=0.0
            )
            for i in range(3):
                angle = (i / 3) * 2 * math.pi
                bpy.ops.mesh.primitive_cone_add(radius1=0.15, depth=0.3)
                claw = context.active_object
                claw.name = f"Base_Claw_{i}"
                # Position around the base perimeter
                base_radius = props.bottle_width * 0.7
                claw.location = (math.cos(angle) * base_radius,
                                 math.sin(angle) * base_radius,
                 0.15)
                claw.data.materials.append(claw_mat)
                claw.parent = bottle

        elif props.base_type == 'CLOTH':
            # Create cloth wrap for base
            bpy.ops.mesh.primitive_plane_add()
            cloth = context.active_object
            cloth.name = "Base_Cloth"
            # Add material
            cloth_mat = ZENV_PotionGenerator_Materials.create_basic_material(
                name="Cloth_Material",
                color=(0.6, 0.3, 0.2, 1.0),
                roughness=0.9,
                metallic=0.0
            )
            cloth.data.materials.append(cloth_mat)
            cloth.parent = bottle
#endregion


#region OP_SEED
# Operator that randomizes the potion generator seed property.

class ZENV_OT_PotionRandomizeSeed(bpy.types.Operator):
    """Randomize the potion generator seed"""
    bl_idname = "zenv.potion_randomize_seed"
    bl_label = "Randomize Seed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.zenv_potion_props
        props.seed = random.randint(1, 999999)
        self.report({'INFO'}, f"Seed set to {props.seed}")
        return {'FINISHED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_PotionGenerator_Panel(bpy.types.Panel):
    """Panel for procedural potion generation"""
    bl_label = "ITEM Potion Generator"
    bl_idname = "ZENV_PT_potion_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_potion_props

        # Seed controls at the top of the panel
        box = layout.box()
        box.label(text="Seed", icon='HELP')
        box.prop(props, "seed", text="Seed")
        box.operator("zenv.potion_randomize_seed", text="Randomize Seed", icon='FILE_REFRESH')

        # Add operator
        layout.operator("zenv.generate_potion", text="Generate Potion")
        
        # Bottle properties
        box = layout.box()
        box.prop(props, "use_bottle", text="Bottle")
        if props.use_bottle:
            col = box.column(align=True)
            col.prop(props, "bottle_height")
            col.prop(props, "bottle_width")
        
        # Liquid properties
        box = layout.box()
        box.prop(props, "use_liquid", text="Liquid")
        if props.use_liquid:
            col = box.column(align=True)
            col.prop(props, "liquid_fill_amount")
            col.prop(props, "liquid_noise_amount")
            col.prop(props, "liquid_noise_scale")
            col.prop(props, "liquid_color")
        
        # Neck decorations
        box = layout.box()
        box.prop(props, "use_neck", text="Neck Decorations")
        if props.use_neck:
            box.prop(props, "neck_decoration_type")
        
        # Topper
        box = layout.box()
        box.prop(props, "use_topper", text="Topper")
        if props.use_topper:
            box.prop(props, "topper_type")
            if props.topper_type == 'CORK':
                col = box.column(align=True)
                col.prop(props, "cork_height_factor")
                col.prop(props, "cork_width_factor")
                col.prop(props, "cork_detail")
                col.prop(props, "cork_spiral_turns")
                col.prop(props, "cork_spiral_depth")
        
        # Interior effects
        box = layout.box()
        box.prop(props, "use_interior", text="Interior Effects")
        if props.use_interior:
            box.prop(props, "interior_effect_type")
        
        # Base decoration
        box = layout.box()
        box.prop(props, "use_base", text="Base Decorations")
        if props.use_base:
            box.prop(props, "base_type")
#endregion


#region REG
classes = (
    ZENV_PG_PotionGenerator_Props,
    ZENV_OT_PotionGenerator,
    ZENV_OT_PotionRandomizeSeed,
    ZENV_PT_PotionGenerator_Panel,
)

def register():

    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except (ValueError, RuntimeError):
            pass  # already registered

    try:
        del bpy.types.Scene.zenv_potion_props
    except AttributeError:
        pass
    bpy.types.Scene.zenv_potion_props = bpy.props.PointerProperty(type=ZENV_PG_PotionGenerator_Props)

def unregister():
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except (ValueError, RuntimeError):
            pass  # not registered
    try:
        del bpy.types.Scene.zenv_potion_props
    except AttributeError:
        pass

if __name__ == "__main__":
    register()
#endregion
