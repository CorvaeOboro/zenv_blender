"""
Procedural Planet Generator
Generate stylized sci-fi planets with terrain, oceans, and atmospheres
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector, noise
from bpy.props import (FloatProperty, IntProperty, EnumProperty, 
                      BoolProperty, PointerProperty)

bl_info = {
    "name": "GEN Planet Procedural",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 2),
    "location": "View3D > ZENV",
    "description": "Generate procedural sci-fi planets with terrain, oceans, and atmospheres"
}

# Property Groups
class ZENV_TerrainProperties(bpy.types.PropertyGroup):
    resolution: IntProperty(
        name="Resolution",
        description="Base mesh resolution",
        min=2,
        max=12,
        default=6
    )
    noise_type: EnumProperty(
        name="Noise Type",
        description="Type of noise for terrain generation",
        items=[
            ('PERLIN', "Perlin", "Classic noise"),
            ('MANHATTAN', "Manhattan", "Block-based noise"),
            ('SPIRAL', "Spiral", "Spiral pattern noise"),
            ('VORONOI', "Voronoi", "Cell-based noise")
        ],
        default='PERLIN'
    )
    displacement_strength: FloatProperty(
        name="Displacement",
        description="Strength of terrain displacement",
        min=0,
        max=1,
        default=0.5
    )
    mountain_scale: FloatProperty(
        name="Mountain Scale",
        description="Scale of mountain features",
        min=0,
        max=2,
        default=1
    )
    erosion_iterations: IntProperty(
        name="Erosion Iterations",
        description="Number of erosion simulation steps",
        min=0,
        max=100,
        default=10
    )
    crater_density: FloatProperty(
        name="Crater Density",
        description="Density of crater features",
        min=0,
        max=1,
        default=0.3
    )

class ZENV_OceanProperties(bpy.types.PropertyGroup):
    wave_height: FloatProperty(
        name="Wave Height",
        description="Height of ocean waves",
        min=0,
        max=1,
        default=0.1
    )
    wave_scale: FloatProperty(
        name="Wave Scale",
        description="Scale of wave patterns",
        min=0.1,
        max=10,
        default=1
    )
    wave_speed: FloatProperty(
        name="Wave Speed",
        description="Speed of wave animation",
        min=0,
        max=2,
        default=0.5
    )
    wave_pattern: EnumProperty(
        name="Wave Pattern",
        description="Type of wave pattern",
        items=[
            ('REGULAR', "Regular", "Regular wave pattern"),
            ('STORM', "Storm", "Storm pattern"),
            ('CALM', "Calm", "Minimal waves")
        ],
        default='REGULAR'
    )

class ZENV_AtmosphereProperties(bpy.types.PropertyGroup):
    cloud_density: FloatProperty(
        name="Cloud Density",
        description="Density of cloud coverage",
        min=0,
        max=1,
        default=0.5
    )
    cloud_pattern: EnumProperty(
        name="Cloud Pattern",
        description="Type of cloud pattern",
        items=[
            ('WISPY', "Wispy", "Light cloud coverage"),
            ('STORMY', "Stormy", "Heavy storm patterns"),
            ('BANDED', "Banded", "Jupiter-like bands")
        ],
        default='WISPY'
    )
    rotation_speed: FloatProperty(
        name="Rotation Speed",
        description="Speed of atmosphere rotation",
        min=0,
        max=2,
        default=0.1
    )
    atmosphere_thickness: FloatProperty(
        name="Thickness",
        description="Thickness of atmosphere layer",
        min=0.01,
        max=0.5,
        default=0.1
    )

# Utility Functions
def create_base_sphere(context, resolution):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=resolution, radius=1.0)
    mesh = bpy.data.meshes.new("Planet_Base")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Planet_Terrain", mesh)
    context.collection.objects.link(obj)
    return obj

def apply_noise_displacement(obj, noise_type, strength, scale):
    # Create displacement modifier
    mod = obj.modifiers.new(name="Displacement", type='DISPLACE')
    tex = bpy.data.textures.new("Planet_Noise", type='NOISE')
    
    if noise_type == 'MANHATTAN':
        tex.noise_type = 'VORONOI_F2'
        tex.noise_scale = 0.5
        tex.contrast = 5
    elif noise_type == 'SPIRAL':
        tex.noise_type = 'MUSGRAVE'
        tex.musgrave_type = 'RIDGED_MULTIFRACTAL'
        tex.noise_scale = 2
    elif noise_type == 'VORONOI':
        tex.noise_type = 'VORONOI_F1'
        tex.noise_scale = 1
    
    mod.texture = tex
    mod.strength = strength * scale
    mod.mid_level = 0.5

def create_ocean_layer(context, planet_obj, props):
    # Create ocean mesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.02)
    mesh = bpy.data.meshes.new("Planet_Ocean")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Planet_Ocean", mesh)
    context.collection.objects.link(obj)
    
    # Create wave animation
    mod = obj.modifiers.new(name="Waves", type='WAVE')
    mod.height = props.wave_height
    mod.width = props.wave_scale
    mod.speed = props.wave_speed
    
    # Setup material
    mat = bpy.data.materials.new(name="Ocean_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    # Create basic ocean shader
    output = nodes.new('ShaderNodeOutputMaterial')
    glass = nodes.new('ShaderNodeBsdfGlass')
    glass.inputs['Color'].default_value = (0.2, 0.4, 0.8, 1.0)
    mat.node_tree.links.new(glass.outputs[0], output.inputs[0])
    
    obj.data.materials.append(mat)
    return obj

def create_atmosphere_layer(context, planet_obj, props):
    # Create atmosphere mesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.1)
    mesh = bpy.data.meshes.new("Planet_Atmosphere")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Planet_Atmosphere", mesh)
    context.collection.objects.link(obj)
    
    # Setup material
    mat = bpy.data.materials.new(name="Atmosphere_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    # Create volumetric atmosphere shader
    output = nodes.new('ShaderNodeOutputMaterial')
    volume = nodes.new('ShaderNodeVolumePrincipled')
    volume.inputs['Density'].default_value = props.cloud_density * 0.1
    mat.node_tree.links.new(volume.outputs[0], output.inputs[1])
    
    # Add rotation animation
    if props.rotation_speed > 0:
        obj.rotation_euler.z = 0
        obj.keyframe_insert(data_path="rotation_euler", frame=1)
        obj.rotation_euler.z = props.rotation_speed * math.pi * 2
        obj.keyframe_insert(data_path="rotation_euler", frame=250)
        
        # Make rotation cyclic
        for fcurve in obj.animation_data.action.fcurves:
            for kf in fcurve.keyframe_points:
                kf.interpolation = 'LINEAR'
            fcurve.modifiers.new('CYCLES')
    
    obj.data.materials.append(mat)
    return obj

# Operator
class ZENV_OT_GeneratePlanet(bpy.types.Operator):
    bl_idname = "object.generate_planet"
    bl_label = "Generate Planet"
    bl_description = "Generate a procedural planet"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        
        # Create terrain
        terrain_obj = create_base_sphere(context, scene.zenv_terrain.resolution)
        apply_noise_displacement(
            terrain_obj,
            scene.zenv_terrain.noise_type,
            scene.zenv_terrain.displacement_strength,
            scene.zenv_terrain.mountain_scale
        )
        
        # Create ocean if enabled
        if scene.zenv_ocean.wave_height > 0:
            ocean_obj = create_ocean_layer(context, terrain_obj, scene.zenv_ocean)
        
        # Create atmosphere if enabled
        if scene.zenv_atmosphere.cloud_density > 0:
            atmos_obj = create_atmosphere_layer(context, terrain_obj, scene.zenv_atmosphere)
        
        return {'FINISHED'}

# UI Panel
class ZENV_PT_PlanetPanel(bpy.types.Panel):
    bl_label = "Planet Generator"
    bl_idname = "ZENV_PT_planet"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Terrain Settings
        box = layout.box()
        box.label(text="Terrain Settings")
        box.prop(scene.zenv_terrain, "resolution")
        box.prop(scene.zenv_terrain, "noise_type")
        box.prop(scene.zenv_terrain, "displacement_strength")
        box.prop(scene.zenv_terrain, "mountain_scale")
        box.prop(scene.zenv_terrain, "erosion_iterations")
        box.prop(scene.zenv_terrain, "crater_density")
        
        # Ocean Settings
        box = layout.box()
        box.label(text="Ocean Settings")
        box.prop(scene.zenv_ocean, "wave_height")
        box.prop(scene.zenv_ocean, "wave_scale")
        box.prop(scene.zenv_ocean, "wave_speed")
        box.prop(scene.zenv_ocean, "wave_pattern")
        
        # Atmosphere Settings
        box = layout.box()
        box.label(text="Atmosphere Settings")
        box.prop(scene.zenv_atmosphere, "cloud_density")
        box.prop(scene.zenv_atmosphere, "cloud_pattern")
        box.prop(scene.zenv_atmosphere, "rotation_speed")
        box.prop(scene.zenv_atmosphere, "atmosphere_thickness")
        
        # Generate Button
        layout.operator("object.generate_planet")

# Registration
classes = (
    ZENV_TerrainProperties,
    ZENV_OceanProperties,
    ZENV_AtmosphereProperties,
    ZENV_OT_GeneratePlanet,
    ZENV_PT_PlanetPanel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_terrain = PointerProperty(type=ZENV_TerrainProperties)
    bpy.types.Scene.zenv_ocean = PointerProperty(type=ZENV_OceanProperties)
    bpy.types.Scene.zenv_atmosphere = PointerProperty(type=ZENV_AtmosphereProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.zenv_terrain
    del bpy.types.Scene.zenv_ocean
    del bpy.types.Scene.zenv_atmosphere

if __name__ == "__main__":
    register()
