"""
BATCH Metal Ingot Generator and Renderer
Generates and renders multiple variations of metal ingots
Example command:
& "C:\Program Files\Blender Foundation\Blender 4.0\blender.exe" --background --python "d:\BLENDER\dev\z_blender_BATCH_metal_ingot_render.py"
"""

import bpy
import os
import sys
import random
import datetime
import math
import time
import re  # Added for filename validation
import tempfile
from mathutils import Vector, Matrix, Euler

# GLOBAL SETTINGS

# Primary directories for the script
SCRIPT_FOLDER = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "metal_ingot_renders"))
TEXTURE_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "textures"))
HDRI_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "hdri"))  # New HDRI specific folder
LIGHTING_PRESET_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "lighting_presets"))

# Number of ingots to generate
NUMBER_OF_GENERATIONS = 500

# Whether to try loading custom presets
USE_CUSTOM_PRESETS = True  

# Camera angle setting: 'LEFT_LOWER' or 'RIGHT_LOWER'
CAMERA_ANGLE = 'LEFT_LOWER'  # Default to Left Lower angle

# Global variables to track HDRI and texture information
CURRENT_HDRI_NAME = None
CURRENT_TEXTURE_NAME = None
CURRENT_MATERIAL_TYPE = None
CURRENT_LIGHTING_PRESET = None

# Import the lighting preset loading utilities
try:
    import z_blender_LOAD_lighting_presets as load_presets
    PRESET_SYSTEM_AVAILABLE = True
except ImportError:
    print("Lighting preset system not available. Continuing with built-in presets only.")
    PRESET_SYSTEM_AVAILABLE = False

# Available lighting presets
LIGHTING_PRESETS = [
    "studio_bright", 
    "dark_rim", 
    "blacksmith_forge", 
    "night_scene", 
    "magical", 
    "cinematic"
]

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEXTURE_FOLDER, exist_ok=True)
os.makedirs(HDRI_FOLDER, exist_ok=True)

# Add BLENDER ADDON directory to Python path
blend_dir = os.path.dirname(os.path.dirname(bpy.data.filepath))
if blend_dir not in sys.path:
    sys.path.append(blend_dir)

# Try to import the metal ingot addon
try:
    from addon.wip.z_blender_GEN_metal_ingot import register, ZENV_PG_MetalIngotProps
    register()
    print("Metal ingot addon loaded successfully")
except ImportError:
    print("ERROR: Metal ingot addon not available. This script requires the Metal Ingot addon to run.")
    print("Please ensure the addon is installed at: addon/wip/z_blender_GEN_metal_ingot.py")
    sys.exit(1)  # Exit script if the addon is not available

def setup_scene():
    """Set up a basic scene for rendering, with a camera and environment"""
    # Clear existing data
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Set renderer to Cycles for best quality
    bpy.context.scene.render.engine = 'CYCLES'
    
    # Set Cycles settings for faster preview
    bpy.context.scene.cycles.device = 'GPU'
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.cycles.use_adaptive_sampling = True
    bpy.context.scene.cycles.adaptive_threshold = 0.01
    bpy.context.scene.cycles.max_bounces = 12
    bpy.context.scene.cycles.diffuse_bounces = 4
    bpy.context.scene.cycles.glossy_bounces = 4
    bpy.context.scene.cycles.transmission_bounces = 8
    bpy.context.scene.cycles.volume_bounces = 0
    bpy.context.scene.cycles.transparent_max_bounces = 8
    
    # Enable denoising for better results
    bpy.context.scene.cycles.use_denoising = True
    
    # Make sure all render passes are enabled
    bpy.context.scene.view_layers[0].use_pass_diffuse_direct = True
    bpy.context.scene.view_layers[0].use_pass_diffuse_indirect = True
    bpy.context.scene.view_layers[0].use_pass_diffuse_color = True
    
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.film_transparent = True
    
    # Set color management for better output
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium Contrast'
    
    # Find an HDRI texture to use
    hdri_path = find_hdri_texture()
    
    # Set up environment - either with HDRI or default
    if hdri_path:
        setup_hdri_environment(hdri_path)
    else:
        # Only create a default world if we didn't find an HDRI
        # This prevents overwriting the HDRI world with a default one
        setup_default_environment()

def create_camera():
    """Create and position a camera for proper ingot viewing"""
    # Create a new camera using Blender's operator
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    
    # Position for the classic isometric 3/4 view
    camera_hoffset_distance= 0.3
    camera_voffset_distance= 0.42
    
    # Use global setting to determine camera position and rotation
    # Rotated for diagonal ingot (ingot is elongated along X-axis)
    # 45 degrees rotation on both X and Z axes creates the isometric view
    # slightly lowered view instead of being above
    if CAMERA_ANGLE == 'LEFT_LOWER':
        # Left Lower Position = -X -Y +Z 
        #camera.location = Vector(((camera_hoffset_distance*-1),(camera_hoffset_distance*-1), camera_voffset_distance))
        camera.location = Vector(((-0.313492),(-0.36858), 0.349892))
        # Left Lower Rotation = +X Y0 -Z
        camera.rotation_euler = Euler((math.radians(54.2), 0, math.radians(-40.2)))
    else:  # 'RIGHT_LOWER'
        # Right Lower Position = +X -Y +Z
        camera.location = Vector((camera_hoffset_distance,(camera_hoffset_distance*-1), camera_voffset_distance))
        # Right Lower Rotation = +x y0 +z
        camera.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Calculate actual distance from camera to object (0,0,0) for precise focusing
    camera_to_object_distance = math.sqrt(
        camera_hoffset_distance**2 + 
        camera_hoffset_distance**2 + 
        camera_voffset_distance**2
    )
    
    # Camera settings
    camera.data.type = 'PERSP'
    camera.data.lens = 85  # Telephoto lens
    camera.data.clip_start = 0.01
    camera.data.clip_end = 100
    
    # Depth of field settings
    camera.data.dof.use_dof = False
    camera.data.dof.focus_distance = camera_to_object_distance  # Precise focus on object at origin
    camera.data.dof.aperture_fstop = 5.6  # Higher f-stop for greater depth of field (more in focus)
    
    # Make this the active camera
    bpy.context.scene.camera = camera
    
    return camera

def setup_lighting(preset_name=None, use_custom_presets=USE_CUSTOM_PRESETS):
    """
    Set up studio lighting for metal object rendering
    
    Args:
        preset_name: Optional specific preset to use 
        use_custom_presets: Whether to use the custom preset system if available
        
    Returns:
        str: Name of the lighting preset used
    """
    global CURRENT_LIGHTING_PRESET
    
    # List of built-in lighting presets
    lighting_presets = [
        "studio_neutral", 
        "studio_bright",
        "dramatic", 
        "dark_rim",
        "blacksmith_forge", 
        "night_scene", 
        "warm_sunlight", 
        "cool_outdoor",
        "magical",
        "cinematic"
    ]
    
    # If a specific preset is requested, use that, otherwise pick random
    if preset_name:
        if preset_name in lighting_presets:
            selected_preset = preset_name
        else:
            # Check if it's a custom preset (if custom presets are enabled)
            if use_custom_presets and PRESET_SYSTEM_AVAILABLE:
                try:
                    # Get available custom presets
                    custom_presets = load_presets.get_preset_names()
                    
                    if preset_name in custom_presets:
                        # It's a valid custom preset, load and apply it
                        print(f"Loading custom preset: {preset_name}")
                        preset_data = load_presets.load_preset(preset_name, LIGHTING_PRESET_FOLDER)
                        
                        if preset_data:
                            # Apply the custom preset
                            success = load_presets.apply_preset(preset_data)
                            if success:
                                CURRENT_LIGHTING_PRESET = f"custom_{preset_name}"
                                print(f"Applied custom lighting preset: {preset_name}")
                                return CURRENT_LIGHTING_PRESET
                        
                        # If we get here, something went wrong with the custom preset
                        print(f"Failed to apply custom preset: {preset_name}, falling back to default")
                except Exception as e:
                    print(f"Error loading custom preset: {e}")
            
            # If custom preset loading failed or wasn't found, fall back to default
            print(f"Preset '{preset_name}' not found, using 'studio_neutral' instead")
            selected_preset = "studio_neutral"
    else:
        # Try to load a custom preset if available and enabled
        if use_custom_presets and PRESET_SYSTEM_AVAILABLE and random.random() < 0.3:  # 30% chance of using custom preset
            try:
                # Get available custom presets
                custom_presets = load_presets.get_preset_names()
                
                if custom_presets:
                    # Pick a random custom preset
                    selected_custom = random.choice(custom_presets)
                    print(f"Trying custom preset: {selected_custom}")
                    preset_data = load_presets.load_preset(selected_custom, LIGHTING_PRESET_FOLDER)
                    
                    if preset_data:
                        # Apply the custom preset
                        success = load_presets.apply_preset(preset_data)
                        if success:
                            CURRENT_LIGHTING_PRESET = f"custom_{selected_custom}"
                            print(f"Applied custom lighting preset: {selected_custom}")
                            return CURRENT_LIGHTING_PRESET
            except Exception as e:
                print(f"Error loading random custom preset: {e}")
        
        # Either no custom presets, or disabled, or failed - use built-in
        selected_preset = random.choice(lighting_presets)
    
    print(f"Setting up '{selected_preset}' lighting")
    preset_name = create_lighting_preset(selected_preset)
    
    # Set the preset for tracking in filenames
    CURRENT_LIGHTING_PRESET = selected_preset

    
    # Validate world texture to prevent pink artifacts
    validate_world_texture()
    
    return preset_name

def create_metal_ingot():
    """Create a metal ingot using the addon operator with default parameters"""
    try:
        # Use the addon operator to create the ingot with its default parameters
        # The addon already has randomness built in
        bpy.ops.zenv.metal_ingot()
        
        # Find the created ingot object
        ingot_obj = None
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and 'Metal_Ingot' in obj.name:
                ingot_obj = obj
                break
        
        if ingot_obj:
            print(f"Created metal ingot using addon operator with default parameters")
            return ingot_obj
        else:
            print("ERROR: Metal Ingot object not found after running operator")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to create metal ingot using addon: {e}")
        sys.exit(1)

def set_specular_value(node, value):
    """
    Helper function to set specular value on a node with compatibility
    for different Blender versions.
    
    Args:
        node: The shader node (typically Principled BSDF)
        value: The specular value to set
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Try the standard input name first
        node.inputs['Specular'].default_value = value
        return True
    except (KeyError, IndexError):
        try:
            # Some versions use 'Specular IOR Level'
            node.inputs['Specular IOR Level'].default_value = value
            return True
        except (KeyError, IndexError):
            # If neither works, find it by checking the input names
            for input_idx, input_socket in enumerate(node.inputs):
                if 'specular' in input_socket.name.lower():
                    node.inputs[input_idx].default_value = value
                    print(f"Found specular input as '{input_socket.name}'")
                    return True
            
            print("Could not set specular value - no matching input found")
            return False

def create_dull_metal_material(obj):
    """Create and apply a dull metal material to the given object"""
    # Create new material
    mat_name = f"DullMetal_{random.randint(1000, 9999)}"
    material = bpy.data.materials.new(name=mat_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    
    # Clear default nodes
    for node in nodes:
        nodes.remove(node)
    
    # Create nodes
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    
    # Connect nodes
    links.new(principled.outputs[0], output.inputs[0])
    
    # Set material properties for dull metal
    principled.inputs['Metallic'].default_value = 0.9
    principled.inputs['Roughness'].default_value = random.uniform(0.3, 0.7)
    
    # Set specular value using helper function
    set_specular_value(principled, random.uniform(0.2, 0.5))
    
    # Base color before texturing
    principled.inputs['Base Color'].default_value = (
        random.uniform(0.2, 0.8),
        random.uniform(0.2, 0.8),
        random.uniform(0.2, 0.8),
        1.0
    )
    
    # Assign material to object
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)
    
    return material

def create_procedural_fantasy_metal(material):
    """Create a procedural shader setup for fantasy metal materials with enhanced micro displacement"""
    global CURRENT_MATERIAL_TYPE
    
    # List of fantasy metal types
    fantasy_metals = ["Bismuth", "Orichalcum", "Aged Copper", "Mythril", "Adamantium"]
    
    # Pick a random metal type
    selected_type = random.choice(fantasy_metals)
    CURRENT_MATERIAL_TYPE = selected_type
    
    # Clear existing nodes
    material.node_tree.nodes.clear()
    
    # Create the nodes
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    
    # Material output
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (1200, 0)
    
    # Principled BSDF shader
    principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled_node.location = (900, 0)
    
    # Connect Principled BSDF to Material Output
    links.new(
        principled_node.outputs['BSDF'],
        output_node.inputs['Surface']
    )
    
    # Create texture coordinate and mapping nodes
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = (-800, 0)
    
    mapping = nodes.new(type='ShaderNodeMapping')
    mapping.location = (-600, 0)
    mapping.inputs['Scale'].default_value[0] = 2.0
    mapping.inputs['Scale'].default_value[1] = 2.0
    mapping.inputs['Scale'].default_value[2] = 2.0
    
    # Connect texture coordinates to mapping
    links.new(tex_coord.outputs['Object'], mapping.inputs['Vector'])
    
    # Base noise texture for the procedural pattern
    noise_tex = nodes.new(type='ShaderNodeTexNoise')
    noise_tex.location = (-400, 0)
    
    # Color ramp for base color control
    color_ramp = nodes.new(type='ShaderNodeValToRGB')
    color_ramp.location = (-200, 0)
    
    # Connect nodes for base color
    links.new(mapping.outputs['Vector'], noise_tex.inputs['Vector'])
    links.new(noise_tex.outputs['Fac'], color_ramp.inputs['Fac'])
    links.new(color_ramp.outputs['Color'], principled_node.inputs['Base Color'])
    
    # Add high-frequency noise texture for micro detail
    micro_noise = nodes.new(type='ShaderNodeTexNoise')
    micro_noise.location = (-400, -200)
    micro_noise.inputs['Scale'].default_value = 50.0
    micro_noise.inputs['Detail'].default_value = 15.0
    micro_noise.inputs['Roughness'].default_value = 0.7
    
    # Connect mapping to micro noise
    links.new(mapping.outputs['Vector'], micro_noise.inputs['Vector'])
    
    # Color ramp for micro noise control
    micro_ramp = nodes.new(type='ShaderNodeValToRGB')
    micro_ramp.location = (-200, -200)
    micro_ramp.color_ramp.elements[0].position = 0.4
    micro_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    micro_ramp.color_ramp.elements[1].position = 0.6
    micro_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    
    links.new(micro_noise.outputs['Fac'], micro_ramp.inputs['Fac'])
    
    # Create bump
    bump_node = nodes.new(type='ShaderNodeBump')
    bump_node.location = (500, -200)
    bump_node.inputs['Strength'].default_value = 0.2  # Updated to 0.2 strength
    bump_node.inputs['Distance'].default_value = 0.01  # Adjusted for better results
    
    # Connect micro_ramp directly to bump height input instead of multiplying with noise texture
    links.new(micro_ramp.outputs['Color'], bump_node.inputs['Height'])
    links.new(bump_node.outputs['Normal'], principled_node.inputs['Normal'])
    
    # Create roughness variation
    roughness_ramp = nodes.new(type='ShaderNodeValToRGB')
    roughness_ramp.location = (500, -100)
    
    # Math node for roughness control
    roughness_math = nodes.new(type='ShaderNodeMath')
    roughness_math.location = (700, -100)
    roughness_math.operation = 'MULTIPLY'
    
    # Set parameters based on material type
    if selected_type == 'Bismuth':
        # Rainbow-like bismuth crystal appearance
        noise_tex.inputs['Scale'].default_value = 10.0
        noise_tex.inputs['Detail'].default_value = 12.0
        
        # Create colorful bismuth gradient
        color_ramp.color_ramp.elements.remove(color_ramp.color_ramp.elements[0])
        pos = 0.0
        for color in [(0.8, 0.0, 0.8, 1.0), (0.0, 0.5, 0.8, 1.0), 
                     (0.0, 0.8, 0.2, 1.0), (0.8, 0.8, 0.0, 1.0), (0.8, 0.2, 0.0, 1.0)]:
            element = color_ramp.color_ramp.elements.new(pos)
            element.color = color
            pos += 0.25
        
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.2
        
        # Roughness variation settings
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.4, 0.4, 0.4, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.1, 0.1, 0.1, 1.0)
        
        # Set specular using helper function
        set_specular_value(principled_node, 1.0)
    
    elif selected_type == 'Orichalcum':
        # Mythical golden-reddish metal
        noise_tex.inputs['Scale'].default_value = 5.0
        noise_tex.inputs['Detail'].default_value = 8.0
        
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.8, 0.3, 0.0, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (1.0, 0.6, 0.1, 1.0)
        
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.1
        
        # Roughness variation settings
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.3, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.05, 0.05, 0.05, 1.0)
        
        # Set specular using helper function
        set_specular_value(principled_node, 1.0)
    
    elif selected_type == 'Aged Copper':
        # Oxidized copper with green patina
        noise_tex.inputs['Scale'].default_value = 15.0
        noise_tex.inputs['Detail'].default_value = 10.0
        
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.0, 0.4, 0.2, 1.0)  # Green patina
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.8, 0.4, 0.2, 1.0)  # Copper
        
        # Add a middle element
        mid_element = color_ramp.color_ramp.elements.new(0.6)
        mid_element.color = (0.2, 0.5, 0.3, 1.0)  # Light green
        
        principled_node.inputs['Metallic'].default_value = 0.7
        roughness_math.inputs[1].default_value = 0.5
        
        # Roughness variation settings
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.7, 0.7, 0.7, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.3, 1.0)
        
        # Set specular using helper function
        set_specular_value(principled_node, 0.6)
    
    elif selected_type == 'Mythril':
        # Silvery-blue ethereal metal
        noise_tex.inputs['Scale'].default_value = 8.0
        noise_tex.inputs['Detail'].default_value = 6.0
        
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.5, 0.8, 1.0, 1.0)  # Light blue
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.8, 0.9, 1.0, 1.0)  # Silver-white
        
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.1
        
        # Roughness variation settings
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.3, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.05, 0.05, 0.05, 1.0)
        
        # Set specular using helper function
        set_specular_value(principled_node, 1.0)
        
    else:  # Adamantium
        # Dark, extremely hard metal
        noise_tex.inputs['Scale'].default_value = 12.0
        noise_tex.inputs['Detail'].default_value = 4.0
        
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.1, 0.1, 0.1, 1.0)  # Almost black
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.4, 1.0)  # Dark gray with hint of blue
        
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.3
        
        # Roughness variation settings
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.5, 0.5, 0.5, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.2, 0.2, 0.2, 1.0)
        
        # Set specular using helper function
        set_specular_value(principled_node, 0.8)
    
    # Connect noise to roughness variation
    links.new(noise_tex.outputs['Fac'], roughness_ramp.inputs['Fac'])
    links.new(roughness_ramp.outputs['Color'], roughness_math.inputs[0])
    links.new(roughness_math.outputs['Value'], principled_node.inputs['Roughness'])
    
    # Use bump mapping only instead of mesh displacement to avoid pinching
    material.cycles.displacement_method = 'BUMP'
    
    # Enable smooth shading
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.active_material == material:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(60)
    
    print(f"Created enhanced procedural {selected_type} material with bump mapping")
    return selected_type

def apply_random_texture(material, texture_folder):
    """Apply a random texture from the specified folder to the material"""
    global CURRENT_TEXTURE_NAME
    CURRENT_TEXTURE_NAME = None
    
    if not os.path.exists(texture_folder):
        print(f"WARNING: Texture folder not found: {texture_folder}")
        print("Falling back to procedural material")
        create_procedural_fantasy_metal(material)
        return False
    
    print(f"Searching for textures in folder: {texture_folder}")
    
    # Get all image files from the folder
    image_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
    image_files = []
    
    # Log all image extensions we're looking for
    print(f"Looking for textures with extensions: {', '.join(image_extensions)}")
    
    for file in os.listdir(texture_folder):
        ext = os.path.splitext(file)[1].lower()
        if ext in image_extensions:
            image_files.append(file)
            print(f"Found texture file: {file}")
    
    print(f"Total texture files found: {len(image_files)}")
    
    if not image_files:
        print(f"WARNING: No texture files found in {texture_folder}")
        print("Falling back to procedural material")
        create_procedural_fantasy_metal(material)
        return False
    
    # Shuffle the image files to try them in random order
    random.shuffle(image_files)
    print(f"Shuffled texture files for random selection")
    print(f"First few textures to try: {', '.join(image_files[:min(3, len(image_files))])}")
    
    # Try loading each image until one succeeds
    success = False
    tried_images = []
    
    for image_file in image_files:
        image_path = os.path.join(texture_folder, image_file)
        print(f"Attempting to load texture: {image_file}")
        print(f"Full texture path: {image_path}")
        
        # Skip if we've already tried this image
        if image_path in tried_images:
            print(f"Skipping already tried texture: {image_file}")
            continue
                
        tried_images.append(image_path)
        
        # Try to load the image
        try:
            # Check if file exists and is readable
            if not os.path.exists(image_path):
                print(f"ERROR: Texture file does not exist: {image_path}")
                
                # Add more detailed error information
                texture_dir = os.path.dirname(image_path)
                if os.path.exists(texture_dir):
                    print(f"Texture directory exists: {texture_dir}")
                    print(f"Files in the directory:")
                    for file in os.listdir(texture_dir):
                        print(f"  - {file}")
                else:
                    print(f"Texture directory does not exist: {texture_dir}")
                
                continue
                
            if not os.access(image_path, os.R_OK):
                print(f"ERROR: Texture file is not readable: {image_path}")
                # Check file permissions
                try:
                    file_stat = os.stat(image_path)
                    print(f"File permissions: {oct(file_stat.st_mode)}")
                except Exception as perm_error:
                    print(f"Error checking file permissions: {perm_error}")
                continue
            
            print(f"Preparing material node tree for texture: {image_file}")
            
            # Store the texture name for filename tracking
            CURRENT_TEXTURE_NAME = os.path.splitext(image_file)[0]  # Remove extension
            print(f"Setting current texture name to: {CURRENT_TEXTURE_NAME}")
            
            # Apply enhanced material with the texture
            success = apply_enhanced_material_with_texture(material, image_path)
            
            if success:
                print(f"Successfully applied enhanced material with texture: {image_file}")
                break
                
        except Exception as e:
            print(f"ERROR: Failed to apply texture {image_file}: {str(e)}")
            print(f"Exception type: {type(e).__name__}")
            import traceback
            print(f"Stack trace: {traceback.format_exc()}")
            continue
    
    # If all images failed, use procedural material
    if not success:
        print("WARNING: All textures failed to load. Falling back to procedural material")
        create_procedural_fantasy_metal(material)
        return False
        
    return success

def apply_enhanced_material_with_texture(material, texture_path):
    """
    Apply an enhanced hyper-realistic material with micro displacement
    using the provided texture as the base.
    
    Args:
        material: The material to enhance
        texture_path: Path to the base color texture
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Clear existing nodes
        material.node_tree.nodes.clear()
        
        # Create new nodes
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Material output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (1200, 0)
        
        # Principled BSDF shader
        principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        principled_node.location = (900, 0)
        principled_node.inputs['Metallic'].default_value = 0.9
        principled_node.inputs['Roughness'].default_value = 0.3
        set_specular_value(principled_node, 0.5)
        
        # Connect principal shader to output
        links.new(principled_node.outputs[0], output_node.inputs[0])
        
        # Load base color texture
        base_color_node = nodes.new(type='ShaderNodeTexImage')
        base_color_node.location = (300, 200)
        base_color_image = bpy.data.images.load(texture_path)
        base_color_node.image = base_color_image
        base_color_node.name = "Base_Color_Texture"
        
        # Add texture coordinate and mapping nodes for all textures
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-800, 0)
        
        mapping = nodes.new(type='ShaderNodeMapping')
        mapping.location = (-600, 0)
        mapping.inputs['Scale'].default_value[0] = 2.0
        mapping.inputs['Scale'].default_value[1] = 2.0
        mapping.inputs['Scale'].default_value[2] = 2.0
        
        # Link texture coordinates to mapping
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], base_color_node.inputs['Vector'])
        
        # Apply subtle color adjustment to maintain original texture appearance
        color_adjust = nodes.new(type='ShaderNodeBrightContrast')
        color_adjust.location = (500, 200)
        color_adjust.inputs['Contrast'].default_value = random.uniform(0.02, 0.05)  # Very subtle contrast
        color_adjust.inputs['Bright'].default_value = random.uniform(-0.05, 0.05)  # Very subtle brightness adjustment
        
        # Create a randomized subtle tint/metal color
        mix_rgb = nodes.new(type='ShaderNodeMixRGB')
        mix_rgb.location = (700, 200)
        mix_rgb.blend_type = 'MULTIPLY'
        mix_rgb.inputs['Fac'].default_value = random.uniform(0.1, 0.2)  # Subtle random tint amount
        
        # Generate a random slight metal tint with subtle color variation
        # Creates colors that are mostly neutral with slight hue variations
        r = random.uniform(0.8, 0.95)
        g = random.uniform(0.8, 0.95)
        b = random.uniform(0.8, 0.95)
        
        # Optional slight color biasing based on a random "metal type" feel
        tint_type = random.randint(0, 4)
        if tint_type == 0:  # Slight copper
            r *= 1.05
            g *= 0.95
            b *= 0.9
        elif tint_type == 1:  # Slight gold
            r *= 1.05
            g *= 1.0
            b *= 0.9
        elif tint_type == 2:  # Slight silver/platinum
            r *= 0.98
            g *= 1.0
            b *= 1.02
        elif tint_type == 3:  # Slight blue steel
            r *= 0.95
            g *= 0.98
            b *= 1.05
        # tint_type 4 remains neutral
        
        mix_rgb.inputs[2].default_value = (r, g, b, 1.0)  # Subtle random metal tint
        print(f"Applied subtle random tint: RGB({r:.2f}, {g:.2f}, {b:.2f})")
        
        # Connect adjusted texture to base color through tint
        links.new(base_color_node.outputs['Color'], color_adjust.inputs['Color'])
        links.new(color_adjust.outputs['Color'], mix_rgb.inputs[1])
        links.new(mix_rgb.outputs['Color'], principled_node.inputs['Base Color'])
        
        # Add a debug message to confirm the texture is connected
        print(f"Connected texture {texture_path} to material's Base Color input")
        
        # Create roughness variation using the base texture but keep it subtle
        separate_rgb = nodes.new(type='ShaderNodeSeparateRGB')
        separate_rgb.location = (300, -100)
        
        # Link base color to RGB separation
        links.new(base_color_node.outputs['Color'], separate_rgb.inputs['Image'])
        
        # Create subtle roughness variation
        roughness_math = nodes.new(type='ShaderNodeMath')
        roughness_math.location = (700, -100)
        roughness_math.operation = 'MULTIPLY'
        roughness_math.inputs[0].default_value = 0.3  # Base roughness
        roughness_math.inputs[1].default_value = 0.15  # Amount of variation
        
        # Add node to mix base roughness with texture-based variation
        roughness_add = nodes.new(type='ShaderNodeMath')
        roughness_add.location = (500, -100)
        roughness_add.operation = 'ADD'
        roughness_add.inputs[0].default_value = 1.0  # Base value
        
        # Use the green channel for subtle roughness variation (scaled to be minimal)
        roughness_scale = nodes.new(type='ShaderNodeMath')
        roughness_scale.location = (500, -200)
        roughness_scale.operation = 'MULTIPLY'
        roughness_scale.inputs[1].default_value = 0.1  # Very subtle effect
        
        links.new(separate_rgb.outputs['G'], roughness_scale.inputs[0])
        links.new(roughness_scale.outputs['Value'], roughness_add.inputs[1])
        links.new(roughness_add.outputs['Value'], roughness_math.inputs[0])
        links.new(roughness_math.outputs['Value'], principled_node.inputs['Roughness'])
        
        # Add extremely subtle noise texture for micro detail
        noise_tex = nodes.new(type='ShaderNodeTexNoise')
        noise_tex.location = (-300, -300)
        noise_tex.inputs['Scale'].default_value = 50.0
        noise_tex.inputs['Detail'].default_value = 15.0
        noise_tex.inputs['Roughness'].default_value = 0.7
        
        # Link mapping to noise
        links.new(mapping.outputs['Vector'], noise_tex.inputs['Vector'])
        
        # Add high-frequency micro detail noise texture
        micro_noise_tex = nodes.new(type='ShaderNodeTexNoise')
        micro_noise_tex.location = (-300, -450)
        micro_noise_tex.inputs['Scale'].default_value = 200.0  # Much higher frequency
        micro_noise_tex.inputs['Detail'].default_value = 16.0  # Maximum detail
        micro_noise_tex.inputs['Roughness'].default_value = 0.9  # Maximum roughness
        micro_noise_tex.inputs['Distortion'].default_value = 0.4  # Add some distortion
        
        # Link mapping to micro noise with additional scale
        mapping_scale = nodes.new(type='ShaderNodeMapping')
        mapping_scale.location = (-500, -450)
        mapping_scale.inputs['Scale'].default_value[0] = 5.0  # Higher scale for micro detail
        mapping_scale.inputs['Scale'].default_value[1] = 5.0
        mapping_scale.inputs['Scale'].default_value[2] = 5.0
        
        links.new(mapping.outputs['Vector'], mapping_scale.inputs['Vector'])
        links.new(mapping_scale.outputs['Vector'], micro_noise_tex.inputs['Vector'])
        
        # Color ramp for micro noise control (narrower range for sharper details)
        micro_ramp = nodes.new(type='ShaderNodeValToRGB')
        micro_ramp.location = (-100, -450)
        micro_ramp.color_ramp.elements[0].position = 0.47
        micro_ramp.color_ramp.elements[0].color = (0.47, 0.47, 0.47, 1.0)
        micro_ramp.color_ramp.elements[1].position = 0.53
        micro_ramp.color_ramp.elements[1].color = (0.53, 0.53, 0.53, 1.0)
        
        links.new(micro_noise_tex.outputs['Fac'], micro_ramp.inputs['Fac'])
        
        # Color ramp for noise control
        noise_ramp = nodes.new(type='ShaderNodeValToRGB')
        noise_ramp.location = (-100, -300)
        noise_ramp.color_ramp.elements[0].position = 0.45
        noise_ramp.color_ramp.elements[0].color = (0.45, 0.45, 0.45, 1.0)
        noise_ramp.color_ramp.elements[1].position = 0.55
        noise_ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1.0)
        
        links.new(noise_tex.outputs['Fac'], noise_ramp.inputs['Fac'])
        
        # Mix primary noise with micro detail noise
        noise_detail_mix = nodes.new(type='ShaderNodeMixRGB')
        noise_detail_mix.location = (50, -370)
        noise_detail_mix.blend_type = 'ADD'
        noise_detail_mix.inputs['Fac'].default_value = 0.3  # Control strength of micro detail
        
        links.new(noise_ramp.outputs['Color'], noise_detail_mix.inputs[1])
        links.new(micro_ramp.outputs['Color'], noise_detail_mix.inputs[2])
        
        # Create very subtle bump from texture
        bump_scale = nodes.new(type='ShaderNodeMath')
        bump_scale.location = (300, -300)
        bump_scale.operation = 'MULTIPLY'
        bump_scale.inputs[1].default_value = 0.05  # Minimal effect
        
        links.new(separate_rgb.outputs['B'], bump_scale.inputs[0])
        
        # Create bump node
        bump_node = nodes.new(type='ShaderNodeBump')
        bump_node.location = (600, -300)
        bump_node.inputs['Strength'].default_value = 0.2  # Very subtle bump
        bump_node.inputs['Distance'].default_value = 0.01
        
        # Connect noise directly to bump height input instead of multiplying with bump scale
        links.new(noise_detail_mix.outputs['Color'], bump_node.inputs['Height'])
        links.new(bump_node.outputs['Normal'], principled_node.inputs['Normal'])
        
        # Add very subtle micro displacement
        displacement_node = nodes.new(type='ShaderNodeDisplacement')
        displacement_node.location = (900, -300)
        displacement_node.inputs['Scale'].default_value = 0.005  # Very subtle displacement
        displacement_node.inputs['Midlevel'].default_value = 0.0
        
        # Math node for displacement control
        disp_math = nodes.new(type='ShaderNodeMath')
        disp_math.location = (700, -400)
        disp_math.operation = 'MULTIPLY'
        disp_math.inputs[1].default_value = 0.01  # Minimal displacement effect
        
        links.new(separate_rgb.outputs['R'], disp_math.inputs[0])
        links.new(disp_math.outputs['Value'], displacement_node.inputs['Height'])
        links.new(displacement_node.outputs['Displacement'], output_node.inputs['Displacement'])
        
        # Use both bump and displacement for enhanced surface details
        material.cycles.displacement_method = 'BOTH'
        
        # Enable smooth shading
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.active_material == material:
                for polygon in obj.data.polygons:
                    polygon.use_smooth = True
                obj.data.use_auto_smooth = True
                obj.data.auto_smooth_angle = math.radians(60)
        
        print("Created enhanced material with subtle texture processing using bump mapping")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to create enhanced material: {str(e)}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        return False

def generate_and_render(output_dir, iteration=1, texture_folder=None):
    """Generate a new ingot and render it"""
    global CURRENT_HDRI_NAME, CURRENT_TEXTURE_NAME, CURRENT_MATERIAL_TYPE, CURRENT_LIGHTING_PRESET
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")
    
    # Reset tracking variables
    CURRENT_HDRI_NAME = None
    CURRENT_TEXTURE_NAME = None
    CURRENT_MATERIAL_TYPE = None
    
    # Choose a random lighting preset if not already set
    if not CURRENT_LIGHTING_PRESET:
        CURRENT_LIGHTING_PRESET = random.choice(LIGHTING_PRESETS)
        print(f"Selected random lighting preset: {CURRENT_LIGHTING_PRESET}")
    
    # Setup new scene
    setup_scene()

    
    # Create camera with fixed position and rotation
    create_camera()
    
    # Set up lighting (will use the current lighting preset)
    setup_lighting()

    
    # Generate ingot
    ingot_obj = create_metal_ingot()
    
    # Ensure the ingot is positioned at the origin for proper camera framing
    ingot_obj.location = (0, 0, 0)
    
    # Rename ingot object to include material type for better identification
    material_name = CURRENT_MATERIAL_TYPE if CURRENT_MATERIAL_TYPE else "Texture"
    timestamp_short = datetime.datetime.now().strftime("%H%M%S")
    ingot_obj.name = f"Metal_Ingot_{material_name}_{timestamp_short}"
    
    # Create material
    material = create_dull_metal_material(ingot_obj)
    
    # Add procedural or texture-based material
    if texture_folder and os.path.exists(texture_folder) and random.random() < 0.7:
        # 70% chance of using texture-based material
        print(f"Choosing texture-based material for iteration {iteration}")
        texture_success = apply_random_texture(material, texture_folder)
        if not texture_success:
            # Fallback to procedural if texture failed
            print(f"Texture application failed, falling back to procedural material")
            material_type = create_procedural_fantasy_metal(material)
            CURRENT_MATERIAL_TYPE = material_type  # Update tracking variable
            print(f"Created fallback {material_type} material")
    else:
        # Use procedural material
        print(f"Choosing procedural material for iteration {iteration}")
        material_type = create_procedural_fantasy_metal(material)
        CURRENT_MATERIAL_TYPE = material_type  # Update tracking variable
        print(f"Created {material_type} procedural material")
    
    # Generate filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    render_path, blend_path = generate_filename(output_dir, timestamp)
    
    # Save blend file
    try:
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        print(f"Saved blend file: {blend_path}")
    except Exception as e:
        print(f"ERROR saving blend file: {str(e)}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        # Try saving to a simpler path as fallback but maintain material information
        fallback_path = os.path.join(output_dir, f"metal_ingot_{timestamp}")
        
        # Add material type if available
        if CURRENT_MATERIAL_TYPE:
            fallback_path += f"_MATERIAL_{CURRENT_MATERIAL_TYPE}"
        
        # Add lighting preset if available
        if CURRENT_LIGHTING_PRESET:
            fallback_path += f"_LIGHT_{CURRENT_LIGHTING_PRESET}"
            
        fallback_path += ".blend"
        
        try:
            print(f"Attempting to save to fallback path: {fallback_path}")
            bpy.ops.wm.save_as_mainfile(filepath=fallback_path)
            print(f"Saved blend file to fallback path: {fallback_path}")
            blend_path = fallback_path  # Update the path for validation
        except Exception as e2:
            print(f"ERROR saving to fallback path: {str(e2)}")
    
    # Render the scene
    try:
        # Final check to ensure proper lighting before render
        ensure_lights_contribute_to_diffuse()
        
        # Set view layer settings for best render results
        for view_layer in bpy.context.scene.view_layers:
            view_layer.use_pass_diffuse_direct = True
            view_layer.use_pass_diffuse_indirect = True
            view_layer.use_pass_diffuse_color = True
        
        bpy.context.scene.render.filepath = render_path
        bpy.ops.render.render(write_still=True)
        print(f"Rendered image: {render_path}")
    except Exception as e:
        print(f"ERROR rendering image: {str(e)}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        # Try saving to a simpler path as fallback but maintain material information
        fallback_render_path = os.path.join(output_dir, f"metal_ingot_{timestamp}")
        
        # Add material type if available
        if CURRENT_MATERIAL_TYPE:
            fallback_render_path += f"_MATERIAL_{CURRENT_MATERIAL_TYPE}"
        
        # Add lighting preset if available
        if CURRENT_LIGHTING_PRESET:
            fallback_render_path += f"_LIGHT_{CURRENT_LIGHTING_PRESET}"
            
        fallback_render_path += ".png"
        
        try:
            print(f"Attempting to render to fallback path: {fallback_render_path}")
            bpy.context.scene.render.filepath = fallback_render_path
            bpy.ops.render.render(write_still=True)
            print(f"Rendered image to fallback path: {fallback_render_path}")
            render_path = fallback_render_path  # Update the path for validation
        except Exception as e2:
            print(f"ERROR rendering to fallback path: {str(e2)}")
    
    # Validate that files were created successfully
    blend_valid, render_valid = validate_output_files(blend_path, render_path)  
    
    if not blend_valid or not render_valid:
        print("Warning: File validation failed")
        
    return blend_valid and render_valid

def validate_output_files(blend_path, render_path, max_wait_time=30):
    """
    Validates that output files exist, are of expected sizes, and contain required metadata in filenames.
    Waits for files to finish writing if needed.
    
    Args:
        blend_path: Path to the .blend file
        render_path: Path to the rendered image file
        max_wait_time: Maximum time to wait in seconds
    
    Returns:
        tuple: (blend_valid, render_valid) - Boolean values indicating validity
    """
    blend_valid = False
    render_valid = False
    wait_time = 0
    step_time = 0.5  # Check every 0.5 seconds
    
    print(f"Waiting for and validating output files...")
    
    # Wait for files to be created and completely written
    while wait_time < max_wait_time:
        # Check if both files exist
        blend_exists = os.path.exists(blend_path)
        render_exists = os.path.exists(render_path)
        
        if blend_exists and render_exists:
            # Check if files are still being written (size changing)
            try:
                blend_size = os.path.getsize(blend_path)
                render_size = os.path.getsize(render_path)
                
                # Wait a bit and check if sizes changed
                time.sleep(step_time)
                wait_time += step_time
                
                new_blend_size = os.path.getsize(blend_path)
                new_render_size = os.path.getsize(render_path)
                
                # If sizes haven't changed, files are likely fully written
                if (blend_size == new_blend_size and 
                    render_size == new_render_size and
                    blend_size > 0 and render_size > 0):
                    break
                    
            except (FileNotFoundError, PermissionError) as e:
                print(f"Error checking file sizes: {e}")
                time.sleep(step_time)
                wait_time += step_time
        else:
            # Files don't exist yet, wait
            time.sleep(step_time)
            wait_time += step_time
    
    # Validate file existence and size
    size_valid_blend = os.path.exists(blend_path) and os.path.getsize(blend_path) > 1000  # 1KB minimum
    size_valid_render = os.path.exists(render_path) and os.path.getsize(render_path) > 1000  # 1KB minimum
    
    # Validate filename contents
    blend_basename = os.path.basename(blend_path)
    render_basename = os.path.basename(render_path)
    
    # Check for metadata in filenames
    filename_valid_blend = True
    filename_valid_render = True
    missing_metadata = []
    
    # Verify timestamp (YYYYMMDD_HHMMSS format)
    if not re.search(r'\d{8}_\d{6}', blend_basename):
        filename_valid_blend = False
        missing_metadata.append("timestamp")
    
    # Verify material info is present if we've set a material
    if CURRENT_MATERIAL_TYPE and "_MATERIAL_" not in blend_basename:
        filename_valid_blend = False
        missing_metadata.append("material type")
    
    # Verify lighting preset info is present if we've set a lighting preset
    if CURRENT_LIGHTING_PRESET and "_LIGHT_" not in blend_basename:
        filename_valid_blend = False
        missing_metadata.append("lighting preset")
    
    # Same checks for render file
    if not re.search(r'\d{8}_\d{6}', render_basename):
        filename_valid_render = False
    
    if CURRENT_MATERIAL_TYPE and "_MATERIAL_" not in render_basename:
        filename_valid_render = False
    
    if CURRENT_LIGHTING_PRESET and "_LIGHT_" not in render_basename:
        filename_valid_render = False
    
    # Combine all validation aspects
    blend_valid = size_valid_blend and filename_valid_blend
    render_valid = size_valid_render and filename_valid_render
    
    # Report validation results
    if size_valid_blend:
        print(f"Blend file size validated: {os.path.basename(blend_path)} - Size: {os.path.getsize(blend_path)/1024:.1f} KB")
    else:
        print(f"Warning: Blend file missing or too small: {blend_path}")
    
    if filename_valid_blend:
        print(f"Blend filename metadata validated")
    else:
        print(f"Warning: Blend filename missing essential metadata: {', '.join(missing_metadata)}")
    
    if size_valid_render:
        print(f"Render file size validated: {os.path.basename(render_path)} - Size: {os.path.getsize(render_path)/1024:.1f} KB")
    else:
        print(f"Warning: Render file missing or too small: {render_path}")
    
    if filename_valid_render:
        print(f"Render filename metadata validated")
    else:
        print(f"Warning: Render filename missing essential metadata")
    
    return blend_valid, render_valid

def generate_filename(output_dir, timestamp=None):
    """
    Generate a consistent filename with all required metadata.
    
    Args:
        output_dir: Output directory for the files
        timestamp: Optional timestamp override (uses current time if None)
        
    Returns:
        tuple: (render_path, blend_path)
    """
    global CURRENT_HDRI_NAME, CURRENT_TEXTURE_NAME, CURRENT_MATERIAL_TYPE, CURRENT_LIGHTING_PRESET
    
    # Use provided timestamp or generate a new one
    if not timestamp:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Initialize filename components
    filename_parts = [f"metal_ingot_{timestamp}"]
    
    # Debug the state of global variables
    print(f"Filename generation - HDRI: {CURRENT_HDRI_NAME}, Texture: {CURRENT_TEXTURE_NAME}, Material: {CURRENT_MATERIAL_TYPE}, Light: {CURRENT_LIGHTING_PRESET}")
    
    # Add HDRI information if available
    if CURRENT_HDRI_NAME:
        hdri_base = os.path.splitext(CURRENT_HDRI_NAME)[0] if '.' in CURRENT_HDRI_NAME else CURRENT_HDRI_NAME
        filename_parts.append(f"_HDRI_{hdri_base}")
    else:
        filename_parts.append("_HDRI_none")
    
    # Add texture or material type information
    if CURRENT_TEXTURE_NAME:
        filename_parts.append(f"_TEXTURE_{CURRENT_TEXTURE_NAME}")
    elif CURRENT_MATERIAL_TYPE:
        filename_parts.append(f"_MATERIAL_{CURRENT_MATERIAL_TYPE}")
    else:
        filename_parts.append("_MATERIAL_unknown")
    
    # Add lighting preset information
    if CURRENT_LIGHTING_PRESET:
        filename_parts.append(f"_LIGHT_{CURRENT_LIGHTING_PRESET}")
    else:
        filename_parts.append("_LIGHT_default")
    
    # Join parts
    filename_base = "".join(filename_parts)
    
    # Replace any potentially problematic characters
    filename_base = filename_base.replace(" ", "_")
    # Remove any additional special characters that could cause issues
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '@']
    for char in invalid_chars:
        filename_base = filename_base.replace(char, '_')
    
    # Limit filename length to avoid path length issues (Windows has ~260 char limit)
    MAX_FILENAME_LENGTH = 100
    if len(filename_base) > MAX_FILENAME_LENGTH:
        print(f"WARNING: Filename too long ({len(filename_base)} chars), truncating")
        # Keep the beginning with iteration number and the end with material type
        parts = filename_base.split('_')
        # Ensure we keep the beginning (with timestamp) and the end (with texture/material info)
        # but truncate the middle if necessary
        keep_beginning = '_'.join(parts[:2])  # Keep first 2 parts (metal_ingot_timestamp)
        keep_end = '_'.join(parts[-3:]) if len(parts) >= 3 else '_'.join(parts[-len(parts):])  # Keep last 3 parts or all if fewer
        filename_base = f"{keep_beginning}_{keep_end}"
        if len(filename_base) > MAX_FILENAME_LENGTH:
            # If still too long, just use a simple name but keep essential info
            material_info = f"_{CURRENT_MATERIAL_TYPE}" if CURRENT_MATERIAL_TYPE else "_unknown"
            lighting_info = f"_{CURRENT_LIGHTING_PRESET}" if CURRENT_LIGHTING_PRESET else "_default"
            filename_base = f"metal_ingot_{timestamp}_short{material_info}{lighting_info}"
        print(f"Truncated filename: {filename_base}")
    
    # Create the file paths
    render_path = os.path.join(output_dir, f"{filename_base}.png")
    blend_path = os.path.join(output_dir, f"{filename_base}.blend")
    
    # Log the generated paths
    print(f"Generated render path: {render_path}")
    print(f"Generated blend path: {blend_path}")
    
    return render_path, blend_path

def find_hdri_texture():
    """Find an HDRI texture file in the hdri folder"""
    global CURRENT_HDRI_NAME
    hdri_path = None
    CURRENT_HDRI_NAME = None
    
    # Check if we have an hdri folder with HDRIs
    print(f"Looking for HDRI files in: {HDRI_FOLDER}")
    if os.path.exists(HDRI_FOLDER):
        print(f"HDRI folder exists at: {HDRI_FOLDER}")
        
        # List all files in the directory for debugging
        print(f"All files in HDRI folder:")
        for file in os.listdir(HDRI_FOLDER):
            print(f"  - {file}")
        
        # Now filter for HDR and EXR files
        hdri_files = []
        for file in os.listdir(HDRI_FOLDER):
            if file.lower().endswith(('.hdr', '.exr')):
                hdri_files.append(os.path.join(HDRI_FOLDER, file))
                print(f"Found HDRI file: {file}")
        
        if hdri_files:
            # Choose a random HDRI file
            hdri_path = random.choice(hdri_files)
            CURRENT_HDRI_NAME = os.path.splitext(os.path.basename(hdri_path))[0]
            print(f"Using HDRI environment map: {CURRENT_HDRI_NAME}")
            print(f"Full HDRI path: {hdri_path}")
        else:
            print(f"No HDRI files found in HDRI folder. Looking for files with .hdr or .exr extensions.")
            print(f"To use HDRIs, place .hdr or .exr files in: {HDRI_FOLDER}")
            print(f"You can download free HDRIs from sites like HDRI Haven, Poly Haven, or create your own in Blender.")
            
            # Fallback to texture folder as secondary option
            print(f"Falling back to texture folder: {TEXTURE_FOLDER}")
            if os.path.exists(TEXTURE_FOLDER):
                for file in os.listdir(TEXTURE_FOLDER):
                    if file.lower().endswith(('.hdr', '.exr')):
                        hdri_files.append(os.path.join(TEXTURE_FOLDER, file))
                        print(f"Found HDRI file in textures: {file}")
                
                if hdri_files:
                    hdri_path = random.choice(hdri_files)
                    CURRENT_HDRI_NAME = os.path.splitext(os.path.basename(hdri_path))[0]
                    print(f"Using HDRI from textures folder: {CURRENT_HDRI_NAME}")
    else:
        print(f"HDRI folder not found at: {HDRI_FOLDER}")
        print(f"Creating HDRI folder: {HDRI_FOLDER}")
        os.makedirs(HDRI_FOLDER, exist_ok=True)
        print(f"Put your HDRI files in this folder to use them for lighting.")
    
    return hdri_path

def setup_hdri_environment(hdri_path):
    """Set up HDRI environment lighting with random rotation"""
    global CURRENT_HDRI_NAME
    print(f"Setting up HDRI environment with file: {hdri_path}")
    
    # Get world
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    world_nodes = world.node_tree.nodes
    world_links = world.node_tree.links
    
    # Clear default nodes
    world_nodes.clear()
    print("Cleared existing world nodes")
    
    # Create new nodes
    world_output = world_nodes.new(type='ShaderNodeOutputWorld')
    world_output.location = (600, 0)
    
    # Create texture coordinate node
    tex_coord = world_nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = (-600, 0)
    
    # Create mapping node for HDRI rotation
    mapping = world_nodes.new(type='ShaderNodeMapping')
    mapping.location = (-400, 0)
    
    # Apply random rotation to the HDRI
    random_z_rotation = random.uniform(0, 2 * math.pi)  # Random rotation between 0 and 360 degrees
    mapping.inputs['Rotation'].default_value[2] = random_z_rotation
    print(f"Applied random HDRI rotation: {math.degrees(random_z_rotation):.1f} degrees")
    
    # Create environment texture node
    env_tex = world_nodes.new(type='ShaderNodeTexEnvironment')
    env_tex.location = (-200, 0)
    
    # Load the HDRI image
    try:
        print(f"Loading HDRI image: {hdri_path}")
        try:
            env_tex.image = bpy.data.images.load(hdri_path, check_existing=True)
            print(f"HDRI image loaded successfully: {env_tex.image.name} ({env_tex.image.size[0]}x{env_tex.image.size[1]})")
            
            # Keep the global HDRI name consistent and without extension
            if not CURRENT_HDRI_NAME:
                CURRENT_HDRI_NAME = os.path.splitext(os.path.basename(hdri_path))[0]
                print(f"HDRI name updated for filename: {CURRENT_HDRI_NAME}")
        except Exception as e:
            print(f"ERROR: Failed to load HDRI image: {e}")
            # Try to get more details about the file
            try:
                file_size = os.path.getsize(hdri_path)
                print(f"File size: {file_size / (1024*1024):.2f} MB")
                
                # Check file extension
                _, ext = os.path.splitext(hdri_path)
                print(f"File extension: {ext}")
                
                # Try to diagnose if this is a format Blender supports
                if ext.lower() not in ['.hdr', '.exr']:
                    print(f"WARNING: File extension {ext} may not be supported by Blender for HDRIs")
            except Exception as file_error:
                print(f"Error analyzing file: {file_error}")
            return False
            
        # Create background node
        background = world_nodes.new(type='ShaderNodeBackground')
        background.location = (300, 0)
        
        # Connect nodes
        world_links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
        world_links.new(mapping.outputs['Vector'], env_tex.inputs['Vector'])
        world_links.new(env_tex.outputs['Color'], background.inputs['Color'])
        world_links.new(background.outputs['Background'], world_output.inputs['Surface'])
        
        print("HDRI environment map loaded successfully with random rotation")
        print("Node connections established: TexCoord -> Mapping -> Environment -> Background -> World Output")
        
        # Debug world settings
        print(f"Final world settings: Nodes: {len(world_nodes)}, Links: {len(world_links)}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to load HDRI: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        return False

def setup_simple_environment():
    """Set up a simple procedural environment for metal reflections"""
    print("Using procedural environment for metal reflections")
    
    # Get world
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    
    # Enable nodes for the world
    world.use_nodes = True
    world_nodes = world.node_tree.nodes
    world_links = world.node_tree.links
    
    # Clear default nodes
    world_nodes.clear()
    
    # Create new nodes
    world_output = world_nodes.new(type='ShaderNodeOutputWorld')
    world_output.location = (300, 0)
    
    # Create a gradient background
    background = world_nodes.new(type='ShaderNodeBackground')
    background.location = (100, 0)
    background.inputs['Color'].default_value = (0.05, 0.05, 0.07, 1.0)  # Dark blue-gray

    # Connect nodes
    world_links.new(background.outputs['Background'], world_output.inputs['Surface'])

def create_lighting_preset(preset_name):
    """
    Create a specific lighting preset based on the preset name
    
    Args:
        preset_name (str): Name of the lighting preset to create
        
    Returns:
        None
    """
    global CURRENT_LIGHTING_PRESET
    
    # Set the currently used lighting preset for filename
    CURRENT_LIGHTING_PRESET = preset_name
    
    # Delete all existing lights
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj)
    
    # Default world settings to be adjusted by presets
    world = bpy.context.scene.world
    if world and world.use_nodes:
        # Adjust world background node if it exists
        bg_node = None
        for node in world.node_tree.nodes:
            if node.type == 'BACKGROUND':
                bg_node = node
                break
                
    
    # Create lighting based on the selected preset
    if preset_name == "studio_bright":
        # Default bright studio lighting - three-point setup
        # Key light (main light)
        key_light_data = bpy.data.lights.new(name="KeyLight", type='AREA')
        key_light_data.energy = 500.0
        key_light_data.size = 2.0  # Increased from 0.5 for softer light
        key_light_data.color = (1.0, 0.95, 0.9)  # Slightly warm
        
        key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.location = Vector((1.0, -1.0, 1.0))
        key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
        
        # Fill light (softer, from opposite side)
        fill_light_data = bpy.data.lights.new(name="FillLight", type='AREA')
        fill_light_data.energy = 200.0
        fill_light_data.size = 3.0  # Increased from 1.0 for softer light
        fill_light_data.color = (0.9, 0.95, 1.0)  # Slightly cool
        
        fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.0, -0.5, 0.5))
        fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
        
        # Rim light (edge highlight from behind)
        rim_light_data = bpy.data.lights.new(name="RimLight", type='SPOT')
        rim_light_data.energy = 300.0
        rim_light_data.spot_size = math.radians(45)
        rim_light_data.spot_blend = 0.5  # Added more blend for softer edges
        rim_light_data.color = (1.0, 1.0, 1.0)  # Pure white
        
        rim_light = bpy.data.objects.new(name="RimLight", object_data=rim_light_data)
        bpy.context.collection.objects.link(rim_light)
        rim_light.location = Vector((-0.5, 1.0, 0.8))
        rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-135)))
        
        # Set the background node influence to 0.1 for subtle world contribution
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "dark_rim":
        # Darker scene with strong rim lighting
        # Main fill light (dim)
        fill_light_data = bpy.data.lights.new(name="FillLight", type='AREA')
        fill_light_data.energy = 100.0
        fill_light_data.size = 1.5
        fill_light_data.color = (0.7, 0.75, 0.85)  # Cool blue tint
        
        fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((0.0, -1.5, 0.5))
        fill_light.rotation_euler = Euler((math.radians(20), 0, math.radians(-30)))
        
        # Strong rim light 1
        rim_light1_data = bpy.data.lights.new(name="RimLight1", type='AREA')
        rim_light1_data.energy = 400.0
        rim_light1_data.size = 0.3
        rim_light1_data.color = (1.0, 1.0, 1.0)  # Pure white
        
        rim_light1 = bpy.data.objects.new(name="RimLight1", object_data=rim_light1_data)
        bpy.context.collection.objects.link(rim_light1)
        rim_light1.location = Vector((-0.8, 0.8, 0.7))
        rim_light1.rotation_euler = Euler((math.radians(-30), math.radians(15), math.radians(-135)))
        
        # Strong rim light 2
        rim_light2_data = bpy.data.lights.new(name="RimLight2", type='AREA')
        rim_light2_data.energy = 300.0
        rim_light2_data.size = 0.3
        rim_light2_data.color = (1.0, 0.98, 0.95)  # Slightly warm white
        
        rim_light2 = bpy.data.objects.new(name="RimLight2", object_data=rim_light2_data)
        bpy.context.collection.objects.link(rim_light2)
        rim_light2.location = Vector((0.8, 0.8, 0.5))
        rim_light2.rotation_euler = Euler((math.radians(-30), math.radians(-15), math.radians(135)))
        
        # Darken world environment
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "blacksmith_forge":
        # Blacksmith forge: warm, orange and flickering lights
        # Main forge light (orange-red glow from below)
        forge_light_data = bpy.data.lights.new(name="ForgeLight", type='AREA')
        forge_light_data.energy = 70.0
        forge_light_data.size = 1.2
        forge_light_data.color = (1.0, 0.3, 0.05)  # Deeper orange-red fire color
        
        forge_light = bpy.data.objects.new(name="ForgeLight", object_data=forge_light_data)
        bpy.context.collection.objects.link(forge_light)
        forge_light.location = Vector((0.0, 0.0, -0.3))  # Lower position below the object
        forge_light.rotation_euler = Euler((math.radians(80), 0, 0))  # Point upward
        
        # Secondary warm light (representing ambient heat)
        ambient_light_data = bpy.data.lights.new(name="AmbientHeat", type='AREA')
        ambient_light_data.energy = 20.0
        ambient_light_data.size = 3.0
        ambient_light_data.color = (0.8, 0.4, 0.2)  # Warm orange
        
        ambient_light = bpy.data.objects.new(name="AmbientHeat", object_data=ambient_light_data)
        bpy.context.collection.objects.link(ambient_light)
        ambient_light.location = Vector((-0.5, -0.8, 0.1))
        ambient_light.rotation_euler = Euler((math.radians(20), 0, math.radians(-30)))
        
        # Add ember lights
        for i in range(4):
            angle = (i / 4) * 2 * math.pi
            radius = 0.4 + (random.random() * 0.2)
            
            # Vary colors between red and orange
            r = 1.0
            g = random.uniform(0.1, 0.3)
            b = random.uniform(0.0, 0.05)
            
            ember_name = f"EmberLight{i}"
            ember_light_data = bpy.data.lights.new(name=ember_name, type='POINT')
            ember_light_data.energy = random.uniform(15.0, 30.0)
            ember_light_data.color = (r, g, b)
            ember_light_data.shadow_soft_size = 0.2
            
            ember_light = bpy.data.objects.new(name=ember_name, object_data=ember_light_data)
            bpy.context.collection.objects.link(ember_light)
            ember_light.location = Vector((
                radius * math.cos(angle),
                radius * math.sin(angle),
                -0.25 + (random.random() * 0.1)
            ))
        
        # Set HDRI visibility
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "night_scene":
        # Night scene with multiple small light sources
        # Moonlight (soft blue directional light)
        moon_light_data = bpy.data.lights.new(name="MoonLight", type='SUN')
        moon_light_data.energy = 0.5
        moon_light_data.color = (0.7, 0.8, 1.0)  # Cool blue moonlight
        
        moon_light = bpy.data.objects.new(name="MoonLight", object_data=moon_light_data)
        bpy.context.collection.objects.link(moon_light)
        moon_light.location = Vector((0, 0, 2.0))
        moon_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
        
        # Multiple small candle/lantern lights around the object
        for i in range(5):  # Create 5 small lights
            angle = (i / 5) * 2 * math.pi
            radius = 0.8 + (random.random() * 0.3)  # Vary distance slightly
            height = 0.1 + (random.random() * 0.3)  # Vary height slightly
            
            # Random warm color variations for small lights
            r = 1.0
            g = 0.5 + (random.random() * 0.3)  # 0.5 - 0.8
            b = 0.1 + (random.random() * 0.2)  # 0.1 - 0.3
            
            # Random energy variations
            energy = 30.0 + (random.random() * 30.0)  # 30 - 60
            
            small_light_data = bpy.data.lights.new(name=f"SmallLight{i}", type='POINT')
            small_light_data.energy = energy
            small_light_data.color = (r, g, b)
            small_light_data.shadow_soft_size = 0.1  # Small shadow size for defined shadows
            
            small_light = bpy.data.objects.new(name=f"SmallLight{i}", object_data=small_light_data)
            bpy.context.collection.objects.link(small_light)
            small_light.location = Vector((
                radius * math.cos(angle),
                radius * math.sin(angle),
                height
            ))
            
        # Make world very dark
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "magical":
        # Magical scene with colorful, vibrant lights
        # Create several colored lights around the object
        colors = [
            (0.2, 0.8, 1.0),  # Cyan
            (1.0, 0.3, 1.0),  # Magenta
            (0.9, 0.9, 0.2),  # Yellow
            (0.3, 1.0, 0.4),  # Green
            (0.8, 0.3, 0.9)   # Purple
        ]
        
        for i, color in enumerate(colors):
            angle = (i / len(colors)) * 2 * math.pi
            radius = 0.8
            height = 0.4
            
            magic_light_data = bpy.data.lights.new(name=f"MagicLight{i}", type='POINT')
            magic_light_data.energy = 300.0
            magic_light_data.color = color
            magic_light_data.shadow_soft_size = 0.3  # Softer shadows for magical feel
            
            magic_light = bpy.data.objects.new(name=f"MagicLight{i}", object_data=magic_light_data)
            bpy.context.collection.objects.link(magic_light)
            magic_light.location = Vector((
                radius * math.cos(angle),
                radius * math.sin(angle),
                height
            ))
            
        # Central magical glow (white/blue)
        core_light_data = bpy.data.lights.new(name="CoreLight", type='POINT')
        core_light_data.energy = 200.0
        core_light_data.color = (0.9, 0.95, 1.0)  # Slightly blue-white
        core_light_data.shadow_soft_size = 0.5  # Very soft shadows
        
        core_light = bpy.data.objects.new(name="CoreLight", object_data=core_light_data)
        bpy.context.collection.objects.link(core_light)
        core_light.location = Vector((0.0, 0.0, 0.7))  # Hovering above
        
        # Dim world environment but not completely dark
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "cinematic":
        # Hyper-realistic cinematic dark and brooding setup
        # Key light - dramatic side lighting
        key_light_data = bpy.data.lights.new(name="KeyLight", type='AREA')
        key_light_data.energy = 400.0
        key_light_data.size = 0.3
        key_light_data.color = (1.0, 0.9, 0.8)  # Slightly warm
        
        key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.location = Vector((1.5, -0.5, 0.7))
        key_light.rotation_euler = Euler((0, math.radians(-20), math.radians(80)))
        
        # Very subtle fill to prevent complete darkness
        fill_light_data = bpy.data.lights.new(name="FillLight", type='AREA')
        fill_light_data.energy = 40.0
        fill_light_data.size = 2.0
        fill_light_data.color = (0.5, 0.6, 0.7)  # Cool blue
        
        fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.0, -0.8, 0.3))
        fill_light.rotation_euler = Euler((math.radians(20), 0, math.radians(-110)))
        
        # Subtle edge light (glint on the metal)
        edge_light_data = bpy.data.lights.new(name="EdgeLight", type='SPOT')
        edge_light_data.energy = 250.0
        edge_light_data.spot_size = math.radians(25)  # Narrow spotlight
        edge_light_data.spot_blend = 0.5  # Softer spot edge
        edge_light_data.color = (1.0, 0.97, 0.95)  # Almost white with hint of warmth
        
        edge_light = bpy.data.objects.new(name="EdgeLight", object_data=edge_light_data)
        bpy.context.collection.objects.link(edge_light)
        edge_light.location = Vector((-0.8, 1.2, 0.9))
        edge_light.rotation_euler = Euler((math.radians(-50), math.radians(10), math.radians(-125)))
        
        # Very dark environment
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "studio_neutral":
        # Studio neutral - balanced three-point lighting setup
        # Key light (main light)
        key_light_data = bpy.data.lights.new(name="KeyLight", type='AREA')
        key_light_data.energy = 400.0
        key_light_data.size = 1.0
        key_light_data.color = (1.0, 1.0, 1.0)  # Neutral white
        
        key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.location = Vector((1.2, -1.2, 1.0))
        key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
        
        # Fill light (softer, from opposite side)
        fill_light_data = bpy.data.lights.new(name="FillLight", type='AREA')
        fill_light_data.energy = 150.0
        fill_light_data.size = 1.5
        fill_light_data.color = (1.0, 1.0, 1.0)  # Neutral white
        
        fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.2, -0.8, 0.6))
        fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
        
        # Rim light (edge highlight from behind)
        rim_light_data = bpy.data.lights.new(name="RimLight", type='AREA')
        rim_light_data.energy = 200.0
        rim_light_data.size = 0.7
        rim_light_data.color = (1.0, 1.0, 1.0)  # Pure white
        
        rim_light = bpy.data.objects.new(name="RimLight", object_data=rim_light_data)
        bpy.context.collection.objects.link(rim_light)
        rim_light.location = Vector((0.0, 1.5, 0.8))
        rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-180)))
        
        # Keep world environment at 0.1
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "dramatic":
        # Dramatic high-contrast lighting
        # Strong directional key light
        key_light_data = bpy.data.lights.new(name="DramaticKey", type='SPOT')
        key_light_data.energy = 600.0
        key_light_data.spot_size = math.radians(30)  # Narrow beam
        key_light_data.spot_blend = 0.15  # Hard edge
        key_light_data.color = (1.0, 0.98, 0.95)  # Slightly warm white
        
        key_light = bpy.data.objects.new(name="DramaticKey", object_data=key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.location = Vector((1.5, -1.0, 1.2))
        key_light.rotation_euler = Euler((math.radians(60), math.radians(15), math.radians(45)))
        
        # Very subtle fill for minimal shadow detail
        fill_light_data = bpy.data.lights.new(name="SubtleFill", type='AREA')
        fill_light_data.energy = 30.0
        fill_light_data.size = 2.0
        fill_light_data.color = (0.6, 0.7, 0.9)  # Cool blue
        
        fill_light = bpy.data.objects.new(name="SubtleFill", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.5, -0.5, 0.3))
        fill_light.rotation_euler = Euler((math.radians(20), 0, math.radians(-70)))
        
        # Keep world dark
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "warm_sunlight":
        # Warm sunlight effect with soft shadows
        # Main sun light
        sun_light_data = bpy.data.lights.new(name="WarmSun", type='SUN')
        sun_light_data.energy = 2.0
        sun_light_data.color = (1.0, 0.9, 0.7)  # Warm golden sun
        sun_light_data.angle = 0.1  # Small angle for sharper shadows
        
        sun_light = bpy.data.objects.new(name="WarmSun", object_data=sun_light_data)
        bpy.context.collection.objects.link(sun_light)
        sun_light.location = Vector((0.0, -1.0, 2.0))
        sun_light.rotation_euler = Euler((math.radians(60), 0, math.radians(30)))
        
        # Skylight fill (blue tint from above)
        sky_light_data = bpy.data.lights.new(name="SkyFill", type='AREA')
        sky_light_data.energy = 80.0
        sky_light_data.size = 3.0
        sky_light_data.color = (0.8, 0.9, 1.0)  # Slight blue
        
        sky_light = bpy.data.objects.new(name="SkyFill", object_data=sky_light_data)
        bpy.context.collection.objects.link(sky_light)
        sky_light.location = Vector((0.0, 0.0, 2.0))
        sky_light.rotation_euler = Euler((math.radians(-90), 0, 0))  # Pointing straight down
        
        # Ground bounce light (warm)
        bounce_light_data = bpy.data.lights.new(name="GroundBounce", type='AREA')
        bounce_light_data.energy = 50.0
        bounce_light_data.size = 2.0
        bounce_light_data.color = (1.0, 0.85, 0.7)  # Warm bounce
        
        bounce_light = bpy.data.objects.new(name="GroundBounce", object_data=bounce_light_data)
        bpy.context.collection.objects.link(bounce_light)
        bounce_light.location = Vector((0.0, 0.0, -0.5))
        bounce_light.rotation_euler = Euler((math.radians(90), 0, 0))  # Pointing up
        
        # Keep world environment at 0.1
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    elif preset_name == "cool_outdoor":
        # Cool outdoor lighting (cloudy day)
        # Main diffuse sky light
        sky_light_data = bpy.data.lights.new(name="CoolSky", type='AREA')
        sky_light_data.energy = 200.0
        sky_light_data.size = 4.0
        sky_light_data.color = (0.75, 0.85, 1.0)  # Cool blue overcast sky
        
        sky_light = bpy.data.objects.new(name="CoolSky", object_data=sky_light_data)
        bpy.context.collection.objects.link(sky_light)
        sky_light.location = Vector((0.0, 0.0, 2.0))
        sky_light.rotation_euler = Euler((math.radians(-90), 0, 0))  # Pointing straight down
        
        # Directional light (subtle sun through clouds)
        sun_light_data = bpy.data.lights.new(name="CloudySun", type='SUN')
        sun_light_data.energy = 0.5
        sun_light_data.color = (0.9, 0.9, 1.0)  # Slightly cool white
        sun_light_data.angle = 0.5  # Large angle for very soft shadows
        
        sun_light = bpy.data.objects.new(name="CloudySun", object_data=sun_light_data)
        bpy.context.collection.objects.link(sun_light)
        sun_light.location = Vector((1.0, -1.0, 1.5))
        sun_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
        
        # Additional fill light
        fill_light_data = bpy.data.lights.new(name="CoolFill", type='AREA')
        fill_light_data.energy = 70.0
        fill_light_data.size = 2.0
        fill_light_data.color = (0.8, 0.8, 0.85)  # Neutral cool
        
        fill_light = bpy.data.objects.new(name="CoolFill", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.0, -0.5, 0.5))
        fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-60)))
        
        # Keep world environment at 0.1
        if bg_node:
            bg_node.inputs[1].default_value = 0.1
            
    else:
        # FALLBACK LIGHTING - Basic three-point setup if preset not recognized
        print(f"WARNING: Preset '{preset_name}' not recognized, falling back to basic lighting setup")
        
        # Key light (main light)
        key_light_data = bpy.data.lights.new(name="DefaultKey", type='AREA')
        key_light_data.energy = 400.0
        key_light_data.size = 1.0
        key_light_data.color = (1.0, 1.0, 1.0)  # Neutral white
        
        key_light = bpy.data.objects.new(name="DefaultKey", object_data=key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.location = Vector((1.0, -1.0, 1.0))
        key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
        
        # Fill light (softer, from opposite side)
        fill_light_data = bpy.data.lights.new(name="DefaultFill", type='AREA')
        fill_light_data.energy = 150.0
        fill_light_data.size = 1.5
        fill_light_data.color = (1.0, 1.0, 1.0)  # Neutral white
        
        fill_light = bpy.data.objects.new(name="DefaultFill", object_data=fill_light_data)
        bpy.context.collection.objects.link(fill_light)
        fill_light.location = Vector((-1.0, -0.5, 0.5))
        fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
        
        # Back light for separation
        back_light_data = bpy.data.lights.new(name="DefaultBack", type='AREA')
        back_light_data.energy = 200.0
        back_light_data.size = 0.7
        back_light_data.color = (1.0, 1.0, 1.0)  # Pure white
        
        back_light = bpy.data.objects.new(name="DefaultBack", object_data=back_light_data)
        bpy.context.collection.objects.link(back_light)
        back_light.location = Vector((0.0, 1.0, 0.8))
        back_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-180)))
        
    # Apply random global rotation to the entire light set
    random_global_rotation = random.uniform(0, 2 * math.pi)  # 0 to 360 degrees in radians
    print(f"Applying random global rotation to all lights: {math.degrees(random_global_rotation):.1f} degrees")
    
    # Debug info about world background
    if bg_node:
        print(f"Created lighting preset: {preset_name}")
        print(f"World background strength set to: {bg_node.inputs[1].default_value}")
    
    # Create a rotation matrix around the z-axis
    cos_theta = math.cos(random_global_rotation)
    sin_theta = math.sin(random_global_rotation)
    
    # Rotate all lights around the z-axis
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            # Get original x, y coordinates
            orig_x = obj.location.x
            orig_y = obj.location.y
            
            # Apply rotation matrix
            new_x = (orig_x * cos_theta) - (orig_y * sin_theta)
            new_y = (orig_x * sin_theta) + (orig_y * cos_theta)
            
            # Update location
            obj.location.x = new_x
            obj.location.y = new_y
            
            # Also rotate the light's orientation around the z-axis
            # Add the rotation to the z component
            obj.rotation_euler.z += random_global_rotation
    
    print(f"Created lighting preset: {preset_name}")
    

    # Validate world texture to prevent pink artifacts
    validate_world_texture()
    
    # Return the preset name for reference
    return preset_name

def create_light_object(name, type, location, rotation, energy=100.0, color=(1.0, 1.0, 1.0), **kwargs):
    """
    Helper function to create lights with the appropriate properties
    
    Args:
        name: Name of the light
        type: Light type ('POINT', 'SUN', 'SPOT', 'AREA')
        location: Vector for light position
        rotation: Euler angles for light rotation
        energy: Light strength
        color: RGB color for the light
        **kwargs: Additional properties specific to light types
        
    Returns:
        Light object
    """
    # Create the light data and set common properties
    light_data = bpy.data.lights.new(name=name, type=type)
    light_data.energy = energy
    light_data.color = color
    
    # Set type-specific properties
    if type == 'AREA':
        # Area light specific properties
        light_data.size = kwargs.get('size', 1.0)
        light_data.shape = kwargs.get('shape', 'SQUARE')
        if 'size_y' in kwargs:
            light_data.size_y = kwargs['size_y']
    elif type == 'SPOT':
        # Spot light specific properties
        light_data.spot_size = kwargs.get('spot_size', math.radians(45))
        light_data.spot_blend = kwargs.get('spot_blend', 0.15)
        if hasattr(light_data, 'use_diffuse'):  # Check if available
            light_data.use_diffuse = True
    elif type == 'POINT' or type == 'SUN':
        # Point and Sun light specific properties
        if hasattr(light_data, 'use_diffuse'):
            light_data.use_diffuse = True
    
    # Create the light object
    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = location
    light_obj.rotation_euler = rotation
    
    return light_obj

def validate_world_texture():
    """Check if the environment texture node has a valid image assigned.
    If not, set a fallback color to prevent pink rendering artifacts."""
    world = bpy.context.scene.world
    if not world or not world.use_nodes:
        print("No world or world nodes found in the scene")
        return False
        
    # Check environment texture nodes
    has_valid_texture = False
    env_texture_found = False
    
    print("Validating world texture nodes:")
    for node in world.node_tree.nodes:
        if node.type == 'TEX_ENVIRONMENT':
            env_texture_found = True
            print(f"Found Environment Texture node: {node.name}")
            
            # Check if the node has an image assigned
            if node.image is None:
                print(f"WARNING: Environment texture node found without image: {node.name}")
            elif not node.image.has_data or not hasattr(node.image, 'size') or node.image.size[0] == 0:
                print(f"WARNING: Environment texture node found without valid image: {node.name}")
                
                # Try to get more info about the image if possible
                if hasattr(node.image, 'filepath'):
                    print(f"Image filepath: {node.image.filepath}")
                if hasattr(node.image, 'source'):
                    print(f"Image source: {node.image.source}")
            else:
                has_valid_texture = True
                print(f"Valid environment texture found: {node.name} with image {node.image.name}")
                print(f"Image dimensions: {node.image.size[0]}x{node.image.size[1]}")
    
    if not env_texture_found:
        print("No environment texture nodes found in the world node tree")
    
    # If no valid texture is found, set a fallback
    if not has_valid_texture:
        print("No valid environment texture found, applying fallback gradient")
        for node in world.node_tree.nodes:
            if node.type == 'BACKGROUND':
                # Set a dark gray color as fallback
                node.inputs[0].default_value = (0.05, 0.05, 0.05, 1.0)
                print(f"Applied fallback color to Background node: {node.name}")
        
    return has_valid_texture

def ensure_lights_contribute_to_diffuse():
    """Ensure all lights are in the active view layer and set to contribute to diffuse."""
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            # Make sure light is in the scene collection
            if obj.name not in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.link(obj)
            
            # Check light type and set properties accordingly
            light_data = obj.data
            light_type = light_data.type if hasattr(light_data, 'type') else 'UNKNOWN'
            print(f"Processing light: {obj.name}, Type: {light_type}")
            
            # Different light types have different properties in Blender
            # Point, Sun, and Spot lights have use_diffuse, but Area lights don't
            if hasattr(light_data, 'use_diffuse'):
                light_data.use_diffuse = True
                print(f"Set diffuse contribution for {obj.name}")
            else:
                print(f"Light {obj.name} (type {light_type}) doesn't have use_diffuse attribute")
            
            # Make sure the light is not muted in render
            obj.hide_render = False
            
            # Set cast shadow explicitly
            if hasattr(light_data, 'use_shadow'):
                light_data.use_shadow = True
                
            # Boost light energy for better renders
            if hasattr(light_data, 'energy'):
                # Boost energy by 50% to ensure it's visible in renders
                light_data.energy *= 1.5
                print(f"Boosted {obj.name} energy to {light_data.energy}")
                
            print(f"Ensuring light {obj.name} contributes to shadows")
    
    # Make sure all collections containing lights are visible in render
    for collection in bpy.data.collections:
        for obj in collection.objects:
            if obj.type == 'LIGHT':
                collection.hide_render = False
                print(f"Ensuring collection '{collection.name}' is visible in render")
    
    return True

def main():
    """Main function to generate multiple ingots"""
    global OUTPUT_FOLDER, TEXTURE_FOLDER, CURRENT_HDRI_NAME
    
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Check for custom preset folder
    if not os.path.exists(LIGHTING_PRESET_FOLDER):
        os.makedirs(LIGHTING_PRESET_FOLDER, exist_ok=True)
        print(f"Created lighting preset folder: {LIGHTING_PRESET_FOLDER}")
    
    # Generate multiple ingots
    for i in range(NUMBER_OF_GENERATIONS):
        print(f"\n--- GENERATING INGOT {i+1}/{NUMBER_OF_GENERATIONS} ---")
        
        # Reset HDRI name each iteration
        CURRENT_HDRI_NAME = None
        
        # Generate a new scene and render it - use main output folder directly
        hdri_path = find_hdri_texture()
        if hdri_path:
            setup_hdri_environment(hdri_path)
        else:
            setup_simple_environment()
            
        # Print HDRI debug info before rendering
        print(f"Before rendering, HDRI name is: {CURRENT_HDRI_NAME}")
            
        generate_and_render(OUTPUT_FOLDER, i+1, texture_folder=TEXTURE_FOLDER)
        
        # Clean up memory by clearing data that's no longer needed
        bpy.ops.wm.read_factory_settings(use_empty=True)

if __name__ == "__main__":
    main()
