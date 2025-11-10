bl_info = {
    "name": 'GEN Potion Generator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Generate procedural potion bottles with modular components',
    "status": 'wip',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "description_long": """
POTION GENERATOR
- generates procedural potion bottles with modular components
- useful for creating fantasy potions with various decorative elements
""",
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix

class ZENV_PotionGenerator_Materials:
    """Material creation for potion components"""
    
    @staticmethod
    def create_glass_material():
        """Create glass material for bottle"""
        mat = bpy.data.materials.new(name="Potion_Glass")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = True
        mat.shadow_method = 'CLIP'
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF
        principled.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
        principled.inputs['Metallic'].default_value = 0.1
        principled.inputs['Roughness'].default_value = 0.05
        principled.inputs['IOR'].default_value = 1.45
        principled.inputs['Transmission Weight'].default_value = 1.0
        principled.inputs['Alpha'].default_value = 0.007
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        return mat

    @staticmethod
    def create_liquid_material(color):
        """Create advanced liquid material with subsurface and volume"""
        mat = bpy.data.materials.new(name="Potion_Liquid")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = True
        mat.shadow_method = 'CLIP'
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Metallic'].default_value = 0.3
        principled.inputs['Roughness'].default_value = 0.0
        principled.inputs['IOR'].default_value = 1.33
        principled.inputs['Transmission Weight'].default_value = 1.0
        principled.inputs['Alpha'].default_value = 0.6
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

        return mat

class ZENV_PG_potion_generator(bpy.types.PropertyGroup):
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
        default=0.15,
        min=0.05,
        max=0.3
    )
    
    cork_width_factor: bpy.props.FloatProperty(
        name="Cork Width",
        description="Width of the cork relative to neck width",
        default=0.95,
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

class ZENV_OT_Generate_Potion(bpy.types.Operator):
    """Generate a procedural potion bottle with modular components"""
    bl_idname = "zenv.generate_potion"
    bl_label = "Generate Potion"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.zenv_potion_props
        
        # Create main bottle
        if props.use_bottle:
            bottle = self.create_bottle(context, props)
        else:
            bottle = None
        
        # Create liquid
        if props.use_liquid:
            if bottle is None:
                bottle = self.create_bottle(context, props)
            liquid = self.create_liquid(context, bottle, props)
        else:
            liquid = None
        
        # Add decorations
        self.add_neck_decorations(context, bottle, props)
        self.add_topper(context, bottle, props)
        self.add_interior_effects(context, liquid, props)
        self.add_base_decoration(context, bottle, props)
        
        return {'FINISHED'}

    def create_bottle(self, context, props):
        """Create the main bottle mesh using curve"""
        # Create curve for bottle profile
        bpy.ops.curve.primitive_bezier_curve_add()
        curve = context.active_object
        curve.name = "Potion_Bottle_Profile"
        
        # Modify curve points for bottle shape
        points = curve.data.splines[0].bezier_points
        height = props.bottle_height
        width = props.bottle_width
        
        # Base point
        points[0].co = Vector((0, 0, 0))
        points[0].handle_left = Vector((-width*0.2, 0, 0))
        points[0].handle_right = Vector((width*0.2, 0, 0))
        
        # Add points for bottle shape
        curve.data.splines[0].bezier_points.add(3)
        
        # Belly point
        points[1].co = Vector((width, 0, height*0.3))
        points[1].handle_left = Vector((width, 0, height*0.15))
        points[1].handle_right = Vector((width, 0, height*0.45))
        
        # Neck start
        points[2].co = Vector((width*0.3, 0, height*0.7))
        points[2].handle_left = Vector((width*0.4, 0, height*0.6))
        points[2].handle_right = Vector((width*0.3, 0, height*0.8))
        
        # Top point
        points[3].co = Vector((width*0.25, 0, height))
        points[3].handle_left = Vector((width*0.25, 0, height*0.9))
        points[3].handle_right = Vector((width*0.25, 0, height*1.1))
        
        # Convert to mesh
        curve.data.resolution_u = 32
        curve.data.fill_mode = 'FULL'
        curve.data.bevel_depth = 0.01
        curve.data.bevel_resolution = 8
        
        # Add screw modifier for revolution
        screw = curve.modifiers.new(name="Screw", type='SCREW')
        screw.steps = 32
        screw.render_steps = 32
        screw.use_smooth_shade = True
        
        # Convert to mesh
        context.view_layer.objects.active = curve
        bpy.ops.object.convert(target='MESH')
        bottle = context.active_object
        bottle.name = "Potion_Bottle"
        
        # Add materials
        bottle.data.materials.append(ZENV_PotionGenerator_Materials.create_glass_material())
        
        return bottle

    def create_liquid(self, context, bottle, props):
        """Create liquid using volumetrics and shrinkwrap"""
        # Duplicate bottle for liquid base
        bpy.ops.object.select_all(action='DESELECT')
        bottle.select_set(True)
        context.view_layer.objects.active = bottle
        bpy.ops.object.duplicate()
        liquid = context.active_object
        liquid.name = "Potion_Liquid"
        
        # Clear any inherited materials
        liquid.data.materials.clear()
        
        # Apply all modifiers from the bottle to get clean mesh
        for modifier in liquid.modifiers:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        
        # First shrinkwrap to get exact bottle interior
        shrink = liquid.modifiers.new(name="Shrinkwrap", type='SHRINKWRAP')
        shrink.wrap_method = 'PROJECT'
        shrink.wrap_mode = 'INSIDE'
        shrink.target = bottle
        shrink.offset = -props.bottle_width * 0.03
        shrink.use_project_z = True
        bpy.ops.object.modifier_apply(modifier=shrink.name)
        
        # Initial remesh for clean topology
        remesh = liquid.modifiers.new(name="Remesh", type='REMESH')
        remesh.mode = 'VOXEL'
        remesh.voxel_size = props.bottle_width * 0.02  # Smaller voxels for better detail
        remesh.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=remesh.name)
        
        # Cut the top of the liquid based on fill amount
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bm = bmesh.from_edit_mesh(liquid.data)
        
        # Calculate cut height
        max_z = max(v.co.z for v in bm.verts)
        min_z = min(v.co.z for v in bm.verts)
        liquid_height = min_z + (max_z - min_z) * props.liquid_fill_amount
        
        # Delete vertices above liquid height
        for v in bm.verts:
            if v.co.z > liquid_height:
                v.select = True
            else:
                v.select = False
        
        bmesh.update_edit_mesh(liquid.data)
        bpy.ops.mesh.delete(type='VERT')
        
        # Fill holes and ensure manifold
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Smooth the top surface
        bpy.ops.object.shade_smooth()
        
        # Add slight displacement for liquid surface
        displace = liquid.modifiers.new(name="Displace", type='DISPLACE')
        tex = bpy.data.textures.new("Liquid_Surface", type='MUSGRAVE')
        tex.noise_scale = props.liquid_noise_scale * 5.0
        tex.noise_intensity = 1.0
        tex.nabla = 0.03
        displace.texture = tex
        displace.strength = props.liquid_noise_amount * 0.003 * props.bottle_width  # Reduced strength
        displace.mid_level = 0.0
        bpy.ops.object.modifier_apply(modifier=displace.name)
        
        # Final high-quality remesh for airtight mesh
        final_remesh = liquid.modifiers.new(name="Final_Remesh", type='REMESH')
        final_remesh.mode = 'SHARP'  # Sharp mode for better detail preservation
        final_remesh.octree_depth = 8  # High resolution
        final_remesh.scale = 0.99
        final_remesh.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=final_remesh.name)
        
        # Add subsurf for final smoothing
        subsurf = liquid.modifiers.new(name="Subsurf", type='SUBSURF')
        subsurf.levels = 2
        subsurf.render_levels = 3
        bpy.ops.object.modifier_apply(modifier=subsurf.name)
        
        # Create new liquid material
        liquid_mat = ZENV_PotionGenerator_Materials.create_liquid_material(props.liquid_color)
        
        # Clear materials and assign new one
        if liquid.data.materials:
            liquid.data.materials.clear()
        liquid.data.materials.append(liquid_mat)
        
        # Parent to bottle
        liquid.parent = bottle
        
        return liquid

    def add_neck_decorations(self, context, bottle, props):
        """Add decorations around the bottle neck"""
        if not props.use_neck:
            return
            
        if props.neck_decoration_type == 'CLOTH':
            # Create cloth wrap
            bpy.ops.mesh.primitive_plane_add()
            cloth = context.active_object
            cloth.name = "Neck_Cloth"
            # Add cloth simulation and modifiers here
            cloth.parent = bottle

        elif props.neck_decoration_type == 'CHAINS':
            # Create chain
            bpy.ops.curve.primitive_bezier_circle_add()
            chain = context.active_object
            chain.name = "Neck_Chain"
            # Add array modifier for chain links
            chain.parent = bottle

        elif props.neck_decoration_type == 'ROPE':
            # Create rope
            bpy.ops.curve.primitive_bezier_circle_add()
            rope = context.active_object
            rope.name = "Neck_Rope"
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
            vertices=32  # Increased from 16 for better detail
        )
        cork = context.active_object
        cork.name = "Bottle_Cork"
        
        # Position cork at bottle neck
        cork.location = Vector((0, 0, props.bottle_height * 0.95))
        
        # Add random skew for wonky look
        skew_angle_x = random.uniform(-0.1, 0.1)
        skew_angle_y = random.uniform(-0.1, 0.1)
        cork.rotation_euler.x += skew_angle_x
        cork.rotation_euler.y += skew_angle_y
        
        # Create spiral pattern using curve
        bpy.ops.curve.primitive_bezier_circle_add(
            radius=cork_radius * 0.8,
            enter_editmode=False,
            align='WORLD'
        )
        spiral = context.active_object
        spiral.name = "Cork_Spiral"
        
        # Position spiral at cork center
        spiral.location = cork.location
        
        # Add screw modifier to create spiral
        screw = spiral.modifiers.new(name="Screw", type='SCREW')
        screw.axis = 'Z'
        screw.screw_offset = cork_height / props.cork_spiral_turns
        screw.iterations = props.cork_spiral_turns
        screw.steps = 16
        screw.render_steps = 16
        
        # Convert to mesh
        context.view_layer.objects.active = spiral
        bpy.ops.object.convert(target='MESH')
        
        # Add thickness to spiral
        solidify = spiral.modifiers.new(name="Solidify", type='SOLIDIFY')
        solidify.thickness = cork_radius * 0.1 * props.cork_spiral_depth
        bpy.ops.object.modifier_apply(modifier=solidify.name)
        
        # Boolean cut spiral from cork
        bool_spiral = cork.modifiers.new(name="Boolean_Spiral", type='BOOLEAN')
        bool_spiral.object = spiral
        bool_spiral.operation = 'DIFFERENCE'
        
        # Add high-res remesh for better detail
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
        
        # Create material with enhanced wood shader
        mat = bpy.data.materials.new(name="Cork_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes for wood material
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        wood_noise = nodes.new('ShaderNodeTexMusgrave')
        color_ramp = nodes.new('ShaderNodeValToRGB')
        mapping = nodes.new('ShaderNodeMapping')
        texcoord = nodes.new('ShaderNodeTexCoord')
        bump = nodes.new('ShaderNodeBump')
        
        # Setup noise texture
        wood_noise.inputs['Scale'].default_value = 2.0
        wood_noise.inputs['Detail'].default_value = 1.0
        wood_noise.inputs['Dimension'].default_value = 2.0
        
        # Setup color ramp for wood grain
        color_ramp.color_ramp.elements[0].position = 0.4
        color_ramp.color_ramp.elements[0].color = (0.4, 0.2, 0.1, 1)
        color_ramp.color_ramp.elements[1].position = 0.6
        color_ramp.color_ramp.elements[1].color = (0.6, 0.3, 0.15, 1)
        
        # Setup bump
        bump.inputs['Strength'].default_value = 0.5
        bump.inputs['Distance'].default_value = 0.02
        
        # Setup principled BSDF
        principled.inputs['Roughness'].default_value = 0.7
        principled.inputs['Specular IOR Level'].default_value = 0.2
        
        # Link nodes
        links.new(texcoord.outputs['Generated'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], wood_noise.inputs['Vector'])
        links.new(wood_noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(wood_noise.outputs['Fac'], bump.inputs['Height'])
        links.new(color_ramp.outputs['Color'], principled.inputs['Base Color'])
        links.new(bump.outputs['Normal'], principled.inputs['Normal'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        # Assign material
        cork.data.materials.append(mat)
        
        # Apply modifiers in correct order
        context.view_layer.objects.active = cork
        for modifier in cork.modifiers:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except:
                print(f"Failed to apply modifier: {modifier.name}")
        
        # Delete the spiral object
        bpy.data.objects.remove(spiral, do_unlink=True)
        
        # Parent to bottle
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
            sphere.parent = bottle

        elif props.topper_type in {'SPIRAL_SPHERE', 'SPIRAL_CURL'}:
            bpy.ops.curve.primitive_bezier_circle_add()
            spiral = context.active_object
            spiral.name = "Bottle_Spiral"
            # Add curve modifiers for spiral shape
            spiral.parent = bottle

    def add_interior_effects(self, context, liquid, props):
        """Add effects inside the potion"""
        if not props.use_interior:
            return
            
        if props.interior_effect_type == 'BUBBLES':
            # Create particle system for bubbles
            bubbles = liquid.modifiers.new(name="Bubbles", type='PARTICLE_SYSTEM')
            psys = liquid.particle_systems[0]
            psys.settings.count = 50
            psys.settings.type = 'EMITTER'

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
            for i in range(8):
                angle = (i / 8) * 2 * math.pi
                bpy.ops.mesh.primitive_cone_add(radius1=0.1, depth=0.2)
                tooth = context.active_object
                tooth.name = f"Base_Tooth_{i}"
                tooth.parent = bottle

        elif props.base_type == 'CLAWS':
            # Create claw feet
            for i in range(3):
                angle = (i / 3) * 2 * math.pi
                bpy.ops.mesh.primitive_cone_add(radius1=0.15, depth=0.3)
                claw = context.active_object
                claw.name = f"Base_Claw_{i}"
                claw.parent = bottle

        elif props.base_type == 'CLOTH':
            # Create cloth wrap for base
            bpy.ops.mesh.primitive_plane_add()
            cloth = context.active_object
            cloth.name = "Base_Cloth"
            cloth.parent = bottle

    def create_liquid_material(self, color):
        """Create advanced liquid material with subsurface and volume"""
        mat = bpy.data.materials.new(name="Potion_Liquid")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = True
        mat.shadow_method = 'CLIP'
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Setup principled BSDF
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Metallic'].default_value = 0.0
        principled.inputs['Roughness'].default_value = 0.05
        principled.inputs['IOR'].default_value = 1.33
        principled.inputs['Transmission Weight'].default_value = 1.0
        principled.inputs['Alpha'].default_value = 0.05
        
        # Add volume absorption for color density
        volume_abs = nodes.new('ShaderNodeVolumeAbsorption')
        volume_abs.inputs['Color'].default_value = color
        volume_abs.inputs['Density'].default_value = 0.3
        
        # Link nodes
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        links.new(volume_abs.outputs['Volume'], output.inputs['Volume'])
        
        return mat

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

classes = (
    ZENV_PG_potion_generator,
    ZENV_OT_Generate_Potion,
    ZENV_PT_PotionGenerator_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_potion_props = bpy.props.PointerProperty(type=ZENV_PG_potion_generator)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_potion_props

if __name__ == "__main__":
    register()
