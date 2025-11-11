# GEN PLANET PROCEDURAL
# Generate procedural planets with customizable features

bl_info = {
    "name": 'GEN Planet Procedural',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Generate procedural planets with customizable features',
    "status": 'wip',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "location": 'View3D > ZENV',
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
            default=128,
            min=32,
            max=512
        )
        
        # Terrain Properties
        bpy.types.Scene.zenv_terrain_scale = FloatProperty(
            name="Terrain Scale",
            description="Scale of terrain features",
            default=2.0,
            min=0.0,
            max=20.0
        )
        
        bpy.types.Scene.zenv_terrain_roughness = FloatProperty(
            name="Roughness",
            description="Roughness of terrain features",
            default=0.7,
            min=0.0,
            max=2.0
        )
        
        bpy.types.Scene.zenv_terrain_layers = IntProperty(
            name="Terrain Layers",
            description="Number of terrain detail layers",
            default=5,
            min=1,
            max=12
        )
        
        # Ocean Properties
        bpy.types.Scene.zenv_ocean_level = FloatProperty(
            name="Ocean Level",
            description="Height of ocean relative to terrain",
            default=0.2,
            min=0.0,
            max=1.0
        )
        
        bpy.types.Scene.zenv_generate_ocean = BoolProperty(
            name="Generate Ocean",
            description="Generate ocean layer",
            default=True
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
        del bpy.types.Scene.zenv_ocean_level
        del bpy.types.Scene.zenv_generate_ocean
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
        bmesh.ops.create_icosphere(bm, subdivisions=int(math.log2(resolution/12)), radius=radius)
        
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
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1)
        
        for vert in bm.verts:
            displacement = 0
            current_scale = scale
            current_intensity = roughness
            
            # Multi-layered noise
            for i in range(layers):
                point = vert.co.normalized() * current_scale
                
                # Combine different noise types for varied terrain
                base_noise = noise.noise(point) * 0.5
                turb = noise.turbulence_vector(point * 2.0, 2).x * 0.3
                detail = noise.noise(point * 4.0) * noise.noise(point * 8.0) * 0.2  # Fractal-like detail
                
                value = base_noise + turb + detail
                
                displacement += value * current_intensity
                current_scale *= 2.0
                current_intensity *= 0.5
            
            vert.co += vert.co.normalized() * displacement * scale * 0.5
        
        bm.to_mesh(obj.data)
        bm.free()
    
    @staticmethod
    def create_ocean_sphere(planet_obj, ocean_level):
        """Create ocean sphere around planet"""
        radius = planet_obj.dimensions.x * 0.5 * (1.0 + ocean_level * 0.1)
        
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=4, radius=radius)
        
        mesh = bpy.data.meshes.new("Ocean")
        bm.to_mesh(mesh)
        bm.free()
        
        ocean_obj = bpy.data.objects.new("Ocean", mesh)
        bpy.context.scene.collection.objects.link(ocean_obj)
        
        mat = bpy.data.materials.new(name="Ocean_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        nodes.clear()
        
        output = nodes.new('ShaderNodeOutputMaterial')
        glass = nodes.new('ShaderNodeBsdfGlass')
        volume = nodes.new('ShaderNodeVolumePrincipled')
        mix = nodes.new('ShaderNodeMixShader')
        
        glass.inputs['Color'].default_value = (0.2, 0.4, 0.8, 1.0)
        glass.inputs['Roughness'].default_value = 0.0
        glass.inputs['IOR'].default_value = 1.33
        
        volume.inputs['Color'].default_value = (0.2, 0.4, 0.8, 1.0)
        volume.inputs['Density'].default_value = 0.1
        
        mix.inputs[0].default_value = 0.9
        
        links.new(glass.outputs['BSDF'], mix.inputs[1])
        links.new(volume.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs[0])
        
        ocean_obj.data.materials.append(mat)
        return ocean_obj
    
    @staticmethod
    def create_surface_material(obj, color, planet_type):
        """Create surface material for planet"""
        mat = bpy.data.materials.new(name="Planet_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        nodes.clear()
        
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        bump = nodes.new('ShaderNodeBump')
        noise = nodes.new('ShaderNodeTexNoise')
        
        principled.inputs['Base Color'].default_value = (*color, 1)
        principled.inputs['Roughness'].default_value = 0.7
        principled.inputs['Specular'].default_value = 0.2
        
        noise.inputs['Scale'].default_value = 50
        noise.inputs['Detail'].default_value = 16
        noise.inputs['Roughness'].default_value = 0.7
        
        bump.inputs['Strength'].default_value = 0.5
        
        links.new(noise.outputs['Color'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], principled.inputs['Normal'])
        links.new(principled.outputs['BSDF'], output.inputs[0])
        
        obj.data.materials.append(mat)
    
    @staticmethod
    def add_craters(obj, count=10):
        """Add impact craters to planet surface"""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        for _ in range(count):
            theta = random.uniform(0, 2 * math.pi)
            phi = random.uniform(0, math.pi)
            radius = random.uniform(0.1, 0.3)
            
            point = Vector((
                math.sin(phi) * math.cos(theta),
                math.sin(phi) * math.sin(theta),
                math.cos(phi)
            ))
            
            for vert in bm.verts:
                dist = (vert.co.normalized() - point).length
                if dist < radius:
                    depth = math.cos(dist / radius * math.pi) * 0.1
                    vert.co -= vert.co.normalized() * depth
        
        bm.to_mesh(obj.data)
        bm.free()
    
    @staticmethod
    def create_atmosphere(obj, height, density, color):
        """Create atmosphere around planet"""
        atmos = obj.copy()
        atmos.data = obj.data.copy()
        atmos.name = "Atmosphere"
        bpy.context.scene.collection.objects.link(atmos)
        
        atmos.scale = Vector((1 + height,) * 3)
        
        mat = bpy.data.materials.new(name="Atmosphere")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        nodes.clear()
        
        output = nodes.new('ShaderNodeOutputMaterial')
        volume = nodes.new('ShaderNodeVolumePrincipled')
        
        volume.inputs['Density'].default_value = density
        volume.inputs['Color'].default_value = (*color, 1)
        
        links.new(volume.outputs[0], output.inputs[1])
        
        atmos.data.materials.append(mat)
        
        return atmos

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
            
            planet = ZENV_PlanetProcedural_Utils.create_base_sphere(
                scene.zenv_planet_radius,
                scene.zenv_resolution
            )
            
            ZENV_PlanetProcedural_Utils.apply_terrain_displacement(
                planet,
                scene.zenv_terrain_scale,
                scene.zenv_terrain_roughness,
                scene.zenv_terrain_layers
            )
            
            ZENV_PlanetProcedural_Utils.create_surface_material(
                planet,
                scene.zenv_surface_color,
                scene.zenv_planet_type
            )
            
            if scene.zenv_generate_ocean:
                ocean = ZENV_PlanetProcedural_Utils.create_ocean_sphere(
                    planet,
                    scene.zenv_ocean_level
                )
                ocean.parent = planet
            
            if scene.zenv_generate_craters and scene.zenv_planet_type == 'ROCKY':
                ZENV_PlanetProcedural_Utils.add_craters(planet)
            
            if scene.zenv_atmosphere_height > 0:
                ZENV_PlanetProcedural_Utils.create_atmosphere(
                    planet,
                    scene.zenv_atmosphere_height,
                    scene.zenv_atmosphere_density,
                    scene.zenv_atmosphere_color
                )
            
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
        
        box = layout.box()
        box.label(text="Base Settings:")
        box.prop(scene, "zenv_planet_type")
        box.prop(scene, "zenv_planet_radius")
        box.prop(scene, "zenv_resolution")
        
        box = layout.box()
        box.label(text="Terrain Settings:")
        box.prop(scene, "zenv_terrain_scale")
        box.prop(scene, "zenv_terrain_roughness")
        box.prop(scene, "zenv_terrain_layers")
        
        box = layout.box()
        box.label(text="Ocean Settings:")
        box.prop(scene, "zenv_ocean_level")
        box.prop(scene, "zenv_generate_ocean")
        
        box = layout.box()
        box.label(text="Atmosphere Settings:")
        box.prop(scene, "zenv_atmosphere_height")
        box.prop(scene, "zenv_atmosphere_density")
        
        box = layout.box()
        box.label(text="Color Settings:")
        box.prop(scene, "zenv_surface_color")
        box.prop(scene, "zenv_atmosphere_color")
        
        box = layout.box()
        box.label(text="Features:")
        box.prop(scene, "zenv_generate_clouds")
        box.prop(scene, "zenv_generate_craters")
        
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
