"""
VFX Splash Simulator - Creates viscous fluid splash simulations
"""

bl_info = {
    "name": 'VFX Splash Simulator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Creates viscous fluid splash simulations using FLIP',
    "status": 'wip',
    "approved": True,
    "group": 'VFX',
    "group_prefix": 'VFX',
    "location": 'View3D > ZENV',
}

import bpy
import math
import random
import logging
import time
from mathutils import Vector, Matrix
from bpy.props import (
    FloatProperty,
    BoolProperty,
    IntProperty,
    FloatVectorProperty,
    EnumProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

class ZENV_PG_SplashSimProperties(PropertyGroup):
    """Properties for splash simulation"""
    
    # Base properties
    scale: FloatProperty(
        name="Overall Scale",
        description="Scale of the splash in meters",
        default=2.0,
        min=0.1,
        max=10.0,
        unit='LENGTH'
    )
    resolution: IntProperty(
        name="Resolution",
        description="Resolution of the fluid simulation",
        default=32,
        min=8,
        max=200
    )
    
    # Fluid properties
    viscosity: FloatProperty(
        name="Viscosity",
        description="Thickness of the fluid",
        default=5.0,
        min=0.0,
        max=100.0
    )
    surface_tension: FloatProperty(
        name="Surface Tension",
        description="Surface tension of the fluid",
        default=0.07,
        min=0.0,
        max=1.0
    )
    
    # Simulation properties
    frame_start: IntProperty(
        name="Start Frame",
        description="Start frame of the simulation",
        default=1,
        min=1
    )
    frame_end: IntProperty(
        name="End Frame",
        description="End frame of the simulation",
        default=100,
        min=2
    )
    substeps: IntProperty(
        name="Substeps",
        description="Simulation substeps per frame",
        default=2,
        min=1,
        max=10
    )
    cache_type: EnumProperty(
        name="Cache Type",
        description="Type of simulation cache",
        items=[
            ('MODULAR', "Modular", "Cache simulation in chunks"),
            ('FINAL', "Final", "Cache entire simulation"),
        ],
        default='MODULAR'
    )
    
    # Force properties
    upward_bias: FloatProperty(
        name="Upward Bias",
        description="Strength of upward force",
        default=2.0,
        min=0.0,
        max=5.0
    )
    explosion_force: FloatProperty(
        name="Explosion Force",
        description="Strength of initial explosion",
        default=3.0,
        min=0.0,
        max=10.0
    )
    turbulence: FloatProperty(
        name="Turbulence",
        description="Amount of fluid turbulence",
        default=1.0,
        min=0.0,
        max=5.0
    )
    
    # Mesh properties
    voxel_size: IntProperty(
        name="Voxel Size",
        description="Size of voxels for mesh generation",
        default=2,
        min=1,
        max=10
    )
    smoothing: IntProperty(
        name="Mesh Smoothing",
        description="Amount of mesh smoothing",
        default=2,
        min=0,
        max=10
    )
    
# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_Splash(Operator):
    """Generate a fluid splash simulation"""
    bl_idname = "zenv.splash"
    bl_label = "Generate Splash"
    bl_options = {'REGISTER', 'UNDO'}
    
    def setup_domain(self, context, props):
        """Create and setup the fluid domain"""
        bpy.ops.mesh.primitive_cube_add(size=props.scale)
        domain = context.active_object
        domain.name = "FluidDomain"
        
        # Add fluid domain physics
        bpy.ops.object.modifier_add(type='FLUID')
        domain.modifiers["Fluid"].fluid_type = 'DOMAIN'
        settings = domain.modifiers["Fluid"].domain_settings
        
        # Domain settings
        settings.resolution_max = props.resolution
        settings.use_mesh = True
        settings.mesh_scale = 1
        settings.mesh_particle_radius = props.voxel_size
        settings.mesh_smoothen_pos = props.smoothing
        settings.mesh_smoothen_neg = 0
        settings.mesh_concave_upper = 1
        settings.mesh_concave_lower = 1
        
        # Time settings
        settings.cache_frame_start = props.frame_start
        settings.cache_frame_end = props.frame_end
        settings.cache_type = props.cache_type
        
        # Fluid settings
        settings.viscosity_base = props.viscosity
        settings.surface_tension = props.surface_tension
        
        # Cache directory
        settings.cache_directory = "//cache_fluid"
        
        return domain
    
    def setup_fluid(self, context, props, domain):
        """Create and setup the fluid emitter"""
        bpy.ops.mesh.primitive_ico_sphere_add(radius=props.scale * 0.2)
        fluid = context.active_object
        fluid.name = "FluidEmitter"
        
        # Position slightly above domain bottom
        fluid.location.z = -props.scale * 0.3
        
        # Add fluid physics
        bpy.ops.object.modifier_add(type='FLUID')
        fluid.modifiers["Fluid"].fluid_type = 'FLOW'
        settings = fluid.modifiers["Fluid"].flow_settings
        
        # Flow settings
        settings.flow_type = 'LIQUID'
        settings.flow_behavior = 'INFLOW'
        settings.use_initial_velocity = True
        settings.velocity_coord[2] = props.upward_bias * 2.0  # Upward velocity
        settings.velocity_normal = props.explosion_force
        settings.use_plane_init = False
        settings.subframes = props.substeps
        settings.surface_distance = 0.5
        
        return fluid
    
    def setup_forces(self, context, props, domain):
        """Setup forces affecting the fluid"""
        # Add turbulence force field
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = None
        
        # Create empty and add force field
        bpy.ops.object.empty_add(type='PLAIN_AXES', align='WORLD', location=domain.location)
        turbulence = context.active_object
        turbulence.name = "FluidTurbulence"
        
        # Add force field
        bpy.ops.object.forcefield_toggle()
        turbulence.field.type = 'TURBULENCE'
        
        # Configure force field
        turbulence.empty_display_size = props.scale * 0.5
        turbulence.field.strength = props.turbulence
        turbulence.field.flow = 1
        turbulence.field.size = props.scale
        turbulence.field.seed = random.randint(1, 1000)
        
        return turbulence
    
    def execute(self, context):
        """Execute the operator"""
        try:
            props = context.scene.zenv_splash_props
            
            # Setup domain first
            domain = self.setup_domain(context, props)
            
            # Setup fluid emitter
            fluid = self.setup_fluid(context, props, domain)
            
            # Setup forces
            turbulence = self.setup_forces(context, props, domain)
            
            # Parent forces to domain for organization
            turbulence.parent = domain
            fluid.parent = domain
            
            # Select domain to show properties
            bpy.ops.object.select_all(action='DESELECT')
            domain.select_set(True)
            context.view_layer.objects.active = domain
            
            # Set frame range
            context.scene.frame_start = props.frame_start
            context.scene.frame_end = props.frame_end
            context.scene.frame_current = props.frame_start
            
            # Start baking automatically
            bpy.ops.fluid.bake_all()
            
            self.report({'INFO'}, "Splash simulation created successfully")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            logger.error(f"Error executing splash operator: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_Splash_Panel(Panel):
    """Panel for splash simulation"""
    bl_label = "VFX Splash Simulator"
    bl_idname = "ZENV_PT_Splash"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_splash_props
        
        # Base properties
        box = layout.box()
        box.label(text="Base Properties")
        box.prop(props, "scale")
        box.prop(props, "resolution")
        
        # Fluid properties
        box = layout.box()
        box.label(text="Fluid Properties")
        box.prop(props, "viscosity")
        box.prop(props, "surface_tension")
        
        # Simulation properties
        box = layout.box()
        box.label(text="Simulation Properties")
        box.prop(props, "frame_start")
        box.prop(props, "frame_end")
        box.prop(props, "substeps")
        box.prop(props, "cache_type")
        
        # Force properties
        box = layout.box()
        box.label(text="Force Properties")
        box.prop(props, "upward_bias")
        box.prop(props, "explosion_force")
        box.prop(props, "turbulence")
        
        # Mesh properties
        box = layout.box()
        box.label(text="Mesh Properties")
        box.prop(props, "voxel_size")
        box.prop(props, "smoothing")
        
        # Generate button
        layout.operator("zenv.splash")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_SplashSimProperties,
    ZENV_OT_Splash,
    ZENV_PT_Splash_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_splash_props = PointerProperty(type=ZENV_PG_SplashSimProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_splash_props

if __name__ == "__main__":
    register()
