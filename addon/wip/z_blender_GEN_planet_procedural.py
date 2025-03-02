# GEN PLANET PROCEDURAL
# Generate procedural planets with customizable features

bl_info = {
    "name": "GEN Planet Procedural",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Generate procedural planets with customizable features",
}

import bpy
import bmesh
import logging
import math
import random
from mathutils import Vector, noise
from bpy.props import FloatProperty, IntProperty, BoolProperty, EnumProperty, FloatVectorProperty

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PlanetProcedural_Properties:
    """Property management for procedural planet generator"""
    
    @classmethod
    def register(cls):
        # Base Properties
        bpy.types.Scene.zenv_planet_radius = FloatProperty(
            name="Planet Radius",
            description="Base radius of the planet",
            default=1.0,
            min=0.1,
            max=100.0
        )
        
        bpy.types.Scene.zenv_resolution = IntProperty(
            name="Resolution",
            description="Resolution of the planet mesh",
            default=32,
            min=4,
            max=256
        )
        
        # Terrain Properties
        bpy.types.Scene.zenv_terrain_scale = FloatProperty(
            name="Terrain Scale",
            description="Scale of terrain features",
            default=1.0,
            min=0.0,
            max=10.0
        )
        
        bpy.types.Scene.zenv_terrain_roughness = FloatProperty(
            name="Roughness",
            description="Roughness of terrain features",
            default=0.5,
            min=0.0,
            max=1.0
        )
        
        bpy.types.Scene.zenv_terrain_layers = IntProperty(
            name="Terrain Layers",
            description="Number of terrain detail layers",
            default=3,
            min=1,
            max=8
        )
        
        # Atmosphere Properties
        bpy.types.Scene.zenv_atmosphere_height = FloatProperty(
            name="Atmosphere Height",
            description="Height of the atmosphere",
            default=0.1,
            min=0.0,
            max=1.0
        )
        
        bpy.types.Scene.zenv_atmosphere_density = FloatProperty(
            name="Atmosphere Density",
            description="Density of the atmosphere",
            default=0.5,
            min=0.0,
            max=1.0
        )
        
        # Color Properties
        bpy.types.Scene.zenv_surface_color = FloatVectorProperty(
            name="Surface Color",
            description="Base color of the planet surface",
            subtype='COLOR',
            default=(0.8, 0.8, 0.8),
            min=0.0,
            max=1.0
        )
        
        bpy.types.Scene.zenv_atmosphere_color = FloatVectorProperty(
            name="Atmosphere Color",
            description="Color of the atmosphere",
            subtype='COLOR',
            default=(0.5, 0.7, 1.0),
            min=0.0,
            max=1.0
        )
        
        # Feature Properties
        bpy.types.Scene.zenv_generate_clouds = BoolProperty(
            name="Generate Clouds",
            description="Generate cloud layer",
            default=True
        )
        
        bpy.types.Scene.zenv_generate_craters = BoolProperty(
            name="Generate Craters",
            description="Generate impact craters",
            default=True
        )
        
        bpy.types.Scene.zenv_planet_type = EnumProperty(
            name="Planet Type",
            description="Type of planet to generate",
            items=[
                ('ROCKY', "Rocky", "Rocky terrestrial planet"),
                ('GAS', "Gas Giant", "Gas giant planet"),
                ('ICE', "Ice", "Ice planet")
            ],
            default='ROCKY'
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_planet_radius
        del bpy.types.Scene.zenv_resolution
        del bpy.types.Scene.zenv_terrain_scale
        del bpy.types.Scene.zenv_terrain_roughness
        del bpy.types.Scene.zenv_terrain_layers
        del bpy.types.Scene.zenv_atmosphere_height
        del bpy.types.Scene.zenv_atmosphere_density
        del bpy.types.Scene.zenv_surface_color
        del bpy.types.Scene.zenv_atmosphere_color
        del bpy.types.Scene.zenv_generate_clouds
        del bpy.types.Scene.zenv_generate_craters
        del bpy.types.Scene.zenv_planet_type

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_PlanetProcedural_Utils:
    """Utility functions for procedural planet generation"""
    
    @staticmethod
    def log_info(message):
        """Log to both console and Blender info"""
        logger.info(message)
        if hasattr(bpy.context, 'window_manager'):
            bpy.context.window_manager.popup_menu(
                lambda self, context: self.layout.label(text=message),
                title="Info",
                icon='INFO'
            )
    
    @staticmethod
    def create_base_sphere(radius, resolution):
        """Create base sphere mesh"""
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=resolution, v_segments=resolution, radius=radius)
        
        # Create mesh and object
        mesh = bpy.data.meshes.new("Planet")
        bm.to_mesh(mesh)
        bm.free()
        
        obj = bpy.data.objects.new("Planet", mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj
    
    @staticmethod
    def apply_terrain_displacement(obj, scale, roughness, layers):
        """Apply terrain displacement to planet surface"""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        for vert in bm.verts:
            displacement = 0
            current_scale = scale
            current_intensity = 1.0
            
            for _ in range(layers):
                point = vert.co.normalized() * current_scale
                value = noise.noise(point) * current_intensity
                displacement += value
                current_scale *= 2
                current_intensity *= roughness
            
            vert.co = vert.co.normalized() * (obj.data.vertices[vert.index].co.length + displacement)
        
        bm.to_mesh(obj.data)
        bm.free()
    
    @staticmethod
    def create_atmosphere(obj, height, density, color):
        """Create atmosphere around planet"""
        # Create atmosphere mesh
        atmos = obj.copy()
        atmos.data = obj.data.copy()
        atmos.name = "Atmosphere"
        bpy.context.scene.collection.objects.link(atmos)
        
        # Scale atmosphere
        atmos.scale = Vector((1 + height,) * 3)
        
        # Create atmosphere material
        mat = bpy.data.materials.new(name="Atmosphere")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        volume = nodes.new('ShaderNodeVolumePrincipled')
        
        # Set up volume shader
        volume.inputs['Density'].default_value = density
        volume.inputs['Color'].default_value = (*color, 1)
        
        # Connect nodes
        links.new(volume.outputs[0], output.inputs[1])
        
        # Assign material
        atmos.data.materials.append(mat)
        
        return atmos
    
    @staticmethod
    def create_surface_material(obj, color, planet_type):
        """Create surface material for planet"""
        mat = bpy.data.materials.new(name="PlanetSurface")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create basic shader setup
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Set base color
        principled.inputs['Base Color'].default_value = (*color, 1)
        
        # Adjust properties based on planet type
        if planet_type == 'ROCKY':
            principled.inputs['Roughness'].default_value = 0.8
            principled.inputs['Metallic'].default_value = 0.1
        elif planet_type == 'GAS':
            principled.inputs['Roughness'].default_value = 0.3
            principled.inputs['Transmission'].default_value = 0.2
        else:  # ICE
            principled.inputs['Roughness'].default_value = 0.2
            principled.inputs['Metallic'].default_value = 0.0
            principled.inputs['Transmission'].default_value = 0.3
        
        # Connect nodes
        links.new(principled.outputs[0], output.inputs[0])
        
        # Assign material
        obj.data.materials.append(mat)
    
    @staticmethod
    def add_craters(obj, count=10):
        """Add impact craters to planet surface"""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        for _ in range(count):
            # Random point on sphere
            theta = random.uniform(0, 2 * math.pi)
            phi = random.uniform(0, math.pi)
            radius = random.uniform(0.1, 0.3)
            
            point = Vector((
                math.sin(phi) * math.cos(theta),
                math.sin(phi) * math.sin(theta),
                math.cos(phi)
            ))
            
            # Create crater depression
            for vert in bm.verts:
                dist = (vert.co.normalized() - point).length
                if dist < radius:
                    depth = math.cos(dist / radius * math.pi) * 0.1
                    vert.co -= vert.co.normalized() * depth
        
        bm.to_mesh(obj.data)
        bm.free()

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_PlanetProcedural_Generate(bpy.types.Operator):
    """Generate procedural planet"""
    bl_idname = "zenv.planet_generate"
    bl_label = "Generate Planet"
    bl_description = "Generate a new procedural planet"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            scene = context.scene
            
            # Create base planet
            planet = ZENV_PlanetProcedural_Utils.create_base_sphere(
                scene.zenv_planet_radius,
                scene.zenv_resolution
            )
            
            # Apply terrain
            ZENV_PlanetProcedural_Utils.apply_terrain_displacement(
                planet,
                scene.zenv_terrain_scale,
                scene.zenv_terrain_roughness,
                scene.zenv_terrain_layers
            )
            
            # Create surface material
            ZENV_PlanetProcedural_Utils.create_surface_material(
                planet,
                scene.zenv_surface_color,
                scene.zenv_planet_type
            )
            
            # Add craters if enabled
            if scene.zenv_generate_craters and scene.zenv_planet_type == 'ROCKY':
                ZENV_PlanetProcedural_Utils.add_craters(planet)
            
            # Create atmosphere if needed
            if scene.zenv_atmosphere_height > 0:
                ZENV_PlanetProcedural_Utils.create_atmosphere(
                    planet,
                    scene.zenv_atmosphere_height,
                    scene.zenv_atmosphere_density,
                    scene.zenv_atmosphere_color
                )
            
            # Select the planet
            bpy.ops.object.select_all(action='DESELECT')
            planet.select_set(True)
            context.view_layer.objects.active = planet
            
            ZENV_PlanetProcedural_Utils.log_info("Planet generated successfully")
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Error generating planet: {str(e)}")
            self.report({'ERROR'}, f"Planet generation failed: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_PlanetProcedural_Panel(bpy.types.Panel):
    """Panel for procedural planet generator"""
    bl_label = "GEN Planet Generator"
    bl_idname = "ZENV_PT_planet_procedural"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Base Settings
        box = layout.box()
        box.label(text="Base Settings:")
        box.prop(scene, "zenv_planet_type")
        box.prop(scene, "zenv_planet_radius")
        box.prop(scene, "zenv_resolution")
        
        # Terrain Settings
        box = layout.box()
        box.label(text="Terrain Settings:")
        box.prop(scene, "zenv_terrain_scale")
        box.prop(scene, "zenv_terrain_roughness")
        box.prop(scene, "zenv_terrain_layers")
        
        # Atmosphere Settings
        box = layout.box()
        box.label(text="Atmosphere Settings:")
        box.prop(scene, "zenv_atmosphere_height")
        box.prop(scene, "zenv_atmosphere_density")
        
        # Color Settings
        box = layout.box()
        box.label(text="Color Settings:")
        box.prop(scene, "zenv_surface_color")
        box.prop(scene, "zenv_atmosphere_color")
        
        # Features
        box = layout.box()
        box.label(text="Features:")
        box.prop(scene, "zenv_generate_clouds")
        box.prop(scene, "zenv_generate_craters")
        
        # Generate Button
        layout.operator("zenv.planet_generate")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_PlanetProcedural_Generate,
    ZENV_PT_PlanetProcedural_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_PlanetProcedural_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_PlanetProcedural_Properties.unregister()

if __name__ == "__main__":
    register()
