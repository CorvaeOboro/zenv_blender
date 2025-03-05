"""
BATCH_light_manager.py

This module contains lighting functions for randomization, HDRI search/setup,
preset application, and light validation. These functions will be used by the main Task Manager.
"""

import bpy
import os
import random
import math
from mathutils import Vector, Euler

# Import globals from BATCH_main_manager (which holds configuration)
import BATCH_main_manager

# Define lighting presets
LIGHTING_PRESETS = {
    "studio_neutral": lambda: create_studio_neutral_lighting(),
    "studio_warm": lambda: create_studio_warm_lighting(),
    "studio_cool": lambda: create_studio_cool_lighting(),
    "dramatic": lambda: create_dramatic_lighting(),
    "cinematic": lambda: create_cinematic_lighting(),
    "dark_rim": lambda: create_dark_rim_lighting(),
    "soft_fill": lambda: create_soft_fill_lighting()
}

# Try to import custom lighting preset loader
try:
    import z_blender_LOAD_lighting_presets as load_presets
    PRESET_SYSTEM_AVAILABLE = True
except ImportError:
    print("Lighting preset system not available. Continuing with built-in presets only.")
    PRESET_SYSTEM_AVAILABLE = False


def setup_lighting():
    """
    Set up lighting for the scene with a random preset
    
    Returns:
        tuple: (hdri_name, lighting_preset) - The HDRI name and lighting preset used
    """
    print("\n--- SETUP LIGHTING DEBUG ---")
    print(f"Starting setup_lighting with CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print(f"Starting setup_lighting with CURRENT_LIGHTING_PRESET: '{BATCH_main_manager.CURRENT_LIGHTING_PRESET}'")
    
    # Clear existing lights
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj)
    print("Cleared existing lights")
    
    # Choose a random lighting preset
    presets = list(LIGHTING_PRESETS.keys())
    selected_preset = random.choice(presets)
    print(f"Selected lighting preset: '{selected_preset}'")
    
    # Find HDRI texture if available
    hdri_result = find_hdri_texture()
    hdri_path = None
    hdri_name = None
    
    if isinstance(hdri_result, tuple) and len(hdri_result) >= 1:
        hdri_path = hdri_result[0]
        if len(hdri_result) > 1:
            hdri_name = hdri_result[1]
    
    print(f"After find_hdri_texture - CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print(f"After find_hdri_texture - hdri_name: '{hdri_name}'")
    
    # Create the lighting setup based on the selected preset
    if selected_preset in LIGHTING_PRESETS:
        try:
            LIGHTING_PRESETS[selected_preset]()
            print(f"Created lighting setup for preset: '{selected_preset}'")
        except Exception as e:
            print(f"ERROR: Failed to create lighting preset '{selected_preset}': {str(e)}")
            print(f"Falling back to studio neutral lighting")
            try:
                create_studio_neutral_lighting()
            except Exception as e2:
                print(f"ERROR: Failed to create fallback lighting: {str(e2)}")
                print(f"Creating minimal lighting setup")
                # Create a minimal light setup
                create_light_object("Key_Light", 'SUN', Vector((0, 0, 5)), Euler((0, 0, 0)), energy=1.0)
    else:
        print(f"WARNING: Unknown lighting preset '{selected_preset}', using studio lighting")
        create_studio_neutral_lighting()
    
    # Set up HDRI environment if available
    if hdri_path:
        hdri_name_from_env = setup_hdri_environment(hdri_path)
        print(f"After setup_hdri_environment - hdri_name_from_env: '{hdri_name_from_env}'")
        # If setup_hdri_environment returned a valid name, use it
        if hdri_name_from_env:
            hdri_name = hdri_name_from_env
            print(f"Updated hdri_name to: '{hdri_name}'")
    else:
        print("No HDRI path available, creating default environment")
        create_default_environment()
    
    # Update global variables
    BATCH_main_manager.CURRENT_LIGHTING_PRESET = selected_preset
    print(f"Set BATCH_main_manager.CURRENT_LIGHTING_PRESET to: '{selected_preset}'")
    
    if hdri_name:
        BATCH_main_manager.CURRENT_HDRI_NAME = hdri_name
        print(f"Set BATCH_main_manager.CURRENT_HDRI_NAME to: '{hdri_name}'")
    elif not BATCH_main_manager.CURRENT_HDRI_NAME:
        BATCH_main_manager.CURRENT_HDRI_NAME = "default_environment"
        print(f"Set default BATCH_main_manager.CURRENT_HDRI_NAME to: 'default_environment'")
    
    # Ensure all lights contribute to diffuse
    ensure_lights_contribute_to_diffuse()
    
    print(f"Exiting setup_lighting with CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print(f"Exiting setup_lighting with CURRENT_LIGHTING_PRESET: '{BATCH_main_manager.CURRENT_LIGHTING_PRESET}'")
    print("--- END SETUP LIGHTING DEBUG ---\n")
    
    # Return the values so they can be captured by the main module
    return BATCH_main_manager.CURRENT_HDRI_NAME, BATCH_main_manager.CURRENT_LIGHTING_PRESET


def find_hdri_texture():
    """Find an HDRI texture file in the hdri folder"""
    print("\n--- FIND HDRI TEXTURE DEBUG ---")
    print(f"Starting find_hdri_texture with CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    
    # Only reset if we're actually looking for a new HDRI
    hdri_path = None
    hdri_name = None
    print(f"Looking for HDRI files in: {BATCH_main_manager.HDRI_FOLDER}")
    if os.path.exists(BATCH_main_manager.HDRI_FOLDER):
        print(f"HDRI folder exists at: {BATCH_main_manager.HDRI_FOLDER}")
        print("All files in HDRI folder:")
        for file in os.listdir(BATCH_main_manager.HDRI_FOLDER):
            print(f"  - {file}")
        hdri_files = []
        for file in os.listdir(BATCH_main_manager.HDRI_FOLDER):
            if file.lower().endswith(('.hdr', '.exr')):
                hdri_files.append(os.path.join(BATCH_main_manager.HDRI_FOLDER, file))
                print(f"Found HDRI file: {file}")
        if hdri_files:
            hdri_path = random.choice(hdri_files)
            # Store the full filename without extension for better identification
            hdri_name = os.path.splitext(os.path.basename(hdri_path))[0]
            BATCH_main_manager.CURRENT_HDRI_NAME = hdri_name
            print(f"Selected HDRI: '{hdri_path}'")
            print(f"Setting CURRENT_HDRI_NAME to: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
            print(f"Using HDRI environment map: {BATCH_main_manager.CURRENT_HDRI_NAME}")
            print(f"Full HDRI path: {hdri_path}")
        else:
            print("No HDRI files found in HDRI folder. To use HDRIs, place .hdr or .exr files in the folder.")
            print(f"Falling back to texture folder: {BATCH_main_manager.TEXTURE_FOLDER}")
            if os.path.exists(BATCH_main_manager.TEXTURE_FOLDER):
                for file in os.listdir(BATCH_main_manager.TEXTURE_FOLDER):
                    if file.lower().endswith(('.hdr', '.exr')):
                        hdri_files.append(os.path.join(BATCH_main_manager.TEXTURE_FOLDER, file))
                        print(f"Found HDRI file in textures: {file}")
                if hdri_files:
                    hdri_path = random.choice(hdri_files)
                    # Store the full filename without extension for better identification
                    hdri_name = os.path.splitext(os.path.basename(hdri_path))[0]
                    BATCH_main_manager.CURRENT_HDRI_NAME = hdri_name
                    print(f"Selected HDRI from textures: '{hdri_path}'")
                    print(f"Setting CURRENT_HDRI_NAME to: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
                    print(f"Using HDRI from textures folder: {BATCH_main_manager.CURRENT_HDRI_NAME}")
    else:
        print(f"HDRI folder not found at: {BATCH_main_manager.HDRI_FOLDER}")
        os.makedirs(BATCH_main_manager.HDRI_FOLDER, exist_ok=True)
        print(f"Created HDRI folder: {BATCH_main_manager.HDRI_FOLDER}. Put your HDRI files here.")
    
    print(f"Exiting find_hdri_texture with CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print(f"Returning hdri_path: '{hdri_path}'")
    print("--- END FIND HDRI TEXTURE DEBUG ---\n")
    
    return hdri_path, hdri_name


def setup_hdri_environment(hdri_path):
    """
    Set up HDRI environment lighting with random rotation
    
    Args:
        hdri_path: Path to the HDRI image file
        
    Returns:
        str: HDRI name (without extension) or None if failed
    """
    print("\n--- SETUP HDRI ENVIRONMENT DEBUG ---")
    print(f"Starting setup_hdri_environment with hdri_path: '{hdri_path}'")
    print(f"Before setup - CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    
    # Extract HDRI name from path for return value
    hdri_name = None
    if hdri_path:
        hdri_name = os.path.splitext(os.path.basename(hdri_path))[0]
        print(f"Extracted hdri_name: '{hdri_name}'")
    
    try:
        # Create a new world if it doesn't exist
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        
        # Set up world nodes
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # Create node setup
        output_node = nodes.new(type='ShaderNodeOutputWorld')
        output_node.location = (300, 0)
        
        background_node = nodes.new(type='ShaderNodeBackground')
        background_node.location = (100, 0)
        background_node.inputs['Strength'].default_value = 1.0
        
        env_tex_node = nodes.new(type='ShaderNodeTexEnvironment')
        env_tex_node.location = (-100, 0)
        
        # Add mapping for rotation
        mapping_node = nodes.new(type='ShaderNodeMapping')
        mapping_node.location = (-300, 0)
        
        # Random rotation for variety
        random_rotation = (
            0,  # X-axis (pitch)
            0,  # Y-axis (roll)
            random.uniform(0, 2 * math.pi)  # Z-axis (yaw) - random rotation around Z
        )
        mapping_node.inputs['Rotation'].default_value = random_rotation
        
        # Add texture coordinate node
        tex_coord_node = nodes.new(type='ShaderNodeTexCoord')
        tex_coord_node.location = (-500, 0)
        
        # Link nodes - FIX: Correct the connection between mapping and environment texture nodes
        links.new(tex_coord_node.outputs['Generated'], mapping_node.inputs['Vector'])
        links.new(mapping_node.outputs['Vector'], env_tex_node.inputs['Vector'])
        links.new(env_tex_node.outputs['Color'], background_node.inputs['Color'])
        links.new(background_node.outputs['Background'], output_node.inputs['Surface'])
        
        # Load HDRI image
        print(f"Loading HDRI image: {hdri_path}")
        if os.path.exists(hdri_path):
            image = bpy.data.images.load(hdri_path, check_existing=True)
            env_tex_node.image = image
            print(f"HDRI image loaded: {os.path.basename(hdri_path)} ({image.size[0]}x{image.size[1]})")
            print("HDRI environment map loaded successfully with random rotation")
            print(f"Node connections established: TexCoord -> Mapping -> Environment -> Background -> World Output")
            print(f"Final world settings: Nodes: {len(nodes)}, Links: {len(links)}")
            
            # Make sure the global variable is set correctly
            if hdri_name:
                BATCH_main_manager.CURRENT_HDRI_NAME = hdri_name
                print(f"Updated CURRENT_HDRI_NAME to: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
        else:
            print(f"ERROR: HDRI file not found at path: {hdri_path}")
            print("Creating default environment instead")
            create_default_environment()
            return None
    except Exception as e:
        print(f"ERROR: Failed to load HDRI image: {str(e)}")
        print("Creating default environment instead")
        create_default_environment()
        return None
    
    print(f"After setup - CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print("--- END SETUP HDRI ENVIRONMENT DEBUG ---\n")
    
    return BATCH_main_manager.CURRENT_HDRI_NAME


def create_default_environment():
    """Create a default environment with procedural lighting when no HDRI is available"""
    print("\n--- CREATE DEFAULT ENVIRONMENT DEBUG ---")
    print(f"Starting create_default_environment")
    print(f"Before setup - CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    
    # Set a default HDRI name for filename generation if not already set
    if not BATCH_main_manager.CURRENT_HDRI_NAME:
        BATCH_main_manager.CURRENT_HDRI_NAME = "default_environment"
        print(f"Set default CURRENT_HDRI_NAME to: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    
    try:
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        
        # Clear existing nodes
        world.use_nodes = True
        world.node_tree.nodes.clear()
        print("Cleared existing world nodes")
        
        # Create node setup
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        
        # Output node
        output_node = nodes.new(type='ShaderNodeOutputWorld')
        output_node.location = (300, 0)
        
        # Background node
        background_node = nodes.new(type='ShaderNodeBackground')
        background_node.location = (100, 0)
        
        # Set a neutral gray background with moderate strength
        background_node.inputs['Color'].default_value = (0.05, 0.05, 0.05, 1.0)
        background_node.inputs['Strength'].default_value = 0.5
        
        # Link nodes
        links.new(background_node.outputs['Background'], output_node.inputs['Surface'])
        
        print("Default environment setup complete")
        print(f"Background color set to dark gray (0.05, 0.05, 0.05)")
        print(f"Background strength set to 0.5")
        
        # Create a three-point lighting setup to ensure good visibility
        try:
            # Key light
            key_light = create_light_object(
                "Key_Light", 'AREA', 
                Vector((4, -4, 4)), 
                Euler((math.radians(45), 0, math.radians(45))), 
                energy=400.0, 
                color=(1.0, 0.95, 0.9)
            )
            
            # Fill light
            fill_light = create_light_object(
                "Fill_Light", 'AREA', 
                Vector((-4, -2, 2)), 
                Euler((math.radians(30), 0, math.radians(-30))), 
                energy=200.0, 
                color=(0.9, 0.95, 1.0)
            )
            
            # Rim light
            rim_light = create_light_object(
                "Rim_Light", 'AREA', 
                Vector((0, 6, 3)), 
                Euler((math.radians(45), 0, math.radians(180))), 
                energy=300.0, 
                color=(1.0, 1.0, 1.0)
            )
            
            print("Created default three-point lighting setup")
        except Exception as e:
            print(f"ERROR: Failed to create default lighting: {str(e)}")
            print("Creating minimal lighting setup")
            # Create a minimal light setup as a last resort
            create_light_object("Key_Light", 'SUN', Vector((0, 0, 5)), Euler((0, 0, 0)), energy=1.0)
    
    except Exception as e:
        print(f"ERROR: Failed to create default environment: {str(e)}")
        print("Critical error in environment setup")
    
    print(f"After setup - CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    print("--- END CREATE DEFAULT ENVIRONMENT DEBUG ---\n")


def create_lighting_preset(preset_name):
    """Create a lighting preset with the specified name"""
    print("\n--- CREATE LIGHTING PRESET DEBUG ---")
    print(f"Starting create_lighting_preset with preset_name: '{preset_name}'")
    print(f"Before setup - CURRENT_LIGHTING_PRESET: '{BATCH_main_manager.CURRENT_LIGHTING_PRESET}'")
    
    # Delete all existing lights
    for obj in bpy.context.scene.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj)
    print("Deleted all existing lights")
    
    # Create the specified lighting preset
    if preset_name == "studio_neutral":
        create_studio_neutral_lighting()
    elif preset_name == "studio_warm":
        create_studio_warm_lighting()
    elif preset_name == "studio_cool":
        create_studio_cool_lighting()
    elif preset_name == "dramatic":
        create_dramatic_lighting()
    elif preset_name == "cinematic":
        create_cinematic_lighting()
    elif preset_name == "dark_rim":
        create_dark_rim_lighting()
    elif preset_name == "soft_fill":
        create_soft_fill_lighting()
    elif preset_name == "studio_bright":
        # Compatibility with main manager's preset list
        create_studio_neutral_lighting()
        preset_name = "studio_neutral"
    else:
        print(f"Unknown preset '{preset_name}', using studio_neutral")
        create_studio_neutral_lighting()
        preset_name = "studio_neutral"
    
    print(f"Created lighting preset: '{preset_name}'")
    print(f"After setup - CURRENT_LIGHTING_PRESET: '{BATCH_main_manager.CURRENT_LIGHTING_PRESET}'")
    print("--- END CREATE LIGHTING PRESET DEBUG ---\n")
    
    return preset_name


def create_light_object(name, type, location, rotation, energy=100.0, color=(1.0, 1.0, 1.0), **kwargs):
    """
    Helper function to create lights with the appropriate properties.
    
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
    light_data = bpy.data.lights.new(name=name, type=type)
    light_data.energy = energy
    light_data.color = color
    if type == 'AREA':
        light_data.size = kwargs.get('size', 1.0)
        light_data.shape = kwargs.get('shape', 'SQUARE')
        if 'size_y' in kwargs:
            light_data.size_y = kwargs['size_y']
    elif type == 'SPOT':
        light_data.spot_size = kwargs.get('spot_size', math.radians(45))
        light_data.spot_blend = kwargs.get('spot_blend', 0.15)
    elif type in ['POINT', 'SUN']:
        pass  # No extra settings needed
    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = location
    light_obj.rotation_euler = rotation
    return light_obj


def create_studio_neutral_lighting():
    """Create a neutral studio lighting setup"""
    print("Creating studio_neutral lighting setup")
    
    # Key light
    key_light_data = bpy.data.lights.new(name="KeyLight", type='AREA')
    key_light_data.energy = 500.0
    key_light_data.size = 2.0
    key_light_data.color = (1.0, 1.0, 1.0)
    key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.0, -1.0, 1.0))
    key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Fill light
    fill_light_data = bpy.data.lights.new(name="FillLight", type='AREA')
    fill_light_data.energy = 200.0
    fill_light_data.size = 3.0
    fill_light_data.color = (1.0, 1.0, 1.0)
    fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Rim light
    rim_light_data = bpy.data.lights.new(name="RimLight", type='SPOT')
    rim_light_data.energy = 300.0
    rim_light_data.spot_size = math.radians(45)
    rim_light_data.spot_blend = 0.5
    rim_light_data.color = (1.0, 1.0, 1.0)
    rim_light = bpy.data.objects.new(name="RimLight", object_data=rim_light_data)
    bpy.context.collection.objects.link(rim_light)
    rim_light.location = Vector((-0.5, 1.0, 0.8))
    rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_studio_warm_lighting():
    """Create a warm studio lighting setup"""
    print("Creating studio_warm lighting setup")
    
    # Key light (warm)
    key_light_data = bpy.data.lights.new(name="WarmKeyLight", type='AREA')
    key_light_data.energy = 450.0
    key_light_data.size = 2.0
    key_light_data.color = (1.0, 0.9, 0.8)  # Warm color
    key_light = bpy.data.objects.new(name="WarmKeyLight", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.0, -1.0, 1.0))
    key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Fill light (slightly warm)
    fill_light_data = bpy.data.lights.new(name="WarmFillLight", type='AREA')
    fill_light_data.energy = 180.0
    fill_light_data.size = 3.0
    fill_light_data.color = (1.0, 0.95, 0.9)  # Slightly warm
    fill_light = bpy.data.objects.new(name="WarmFillLight", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Rim light (neutral)
    rim_light_data = bpy.data.lights.new(name="WarmRimLight", type='SPOT')
    rim_light_data.energy = 280.0
    rim_light_data.spot_size = math.radians(45)
    rim_light_data.spot_blend = 0.5
    rim_light_data.color = (1.0, 1.0, 1.0)  # Neutral
    rim_light = bpy.data.objects.new(name="WarmRimLight", object_data=rim_light_data)
    bpy.context.collection.objects.link(rim_light)
    rim_light.location = Vector((-0.5, 1.0, 0.8))
    rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_studio_cool_lighting():
    """Create a cool studio lighting setup"""
    print("Creating studio_cool lighting setup")
    
    # Key light (cool)
    key_light_data = bpy.data.lights.new(name="CoolKeyLight", type='AREA')
    key_light_data.energy = 450.0
    key_light_data.size = 2.0
    key_light_data.color = (0.9, 0.95, 1.0)  # Cool color
    key_light = bpy.data.objects.new(name="CoolKeyLight", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.0, -1.0, 1.0))
    key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Fill light (cooler)
    fill_light_data = bpy.data.lights.new(name="CoolFillLight", type='AREA')
    fill_light_data.energy = 180.0
    fill_light_data.size = 3.0
    fill_light_data.color = (0.8, 0.9, 1.0)  # Cooler
    fill_light = bpy.data.objects.new(name="CoolFillLight", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Rim light (slightly warm for contrast)
    rim_light_data = bpy.data.lights.new(name="CoolRimLight", type='SPOT')
    rim_light_data.energy = 280.0
    rim_light_data.spot_size = math.radians(45)
    rim_light_data.spot_blend = 0.5
    rim_light_data.color = (1.0, 0.98, 0.95)  # Slightly warm for contrast
    rim_light = bpy.data.objects.new(name="CoolRimLight", object_data=rim_light_data)
    bpy.context.collection.objects.link(rim_light)
    rim_light.location = Vector((-0.5, 1.0, 0.8))
    rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_dramatic_lighting():
    """Create a dramatic lighting setup with high contrast"""
    print("Creating dramatic lighting setup")
    
    # Strong key light
    key_light_data = bpy.data.lights.new(name="DramaticKey", type='AREA')
    key_light_data.energy = 800.0
    key_light_data.size = 1.0  # Smaller for harder shadows
    key_light_data.color = (1.0, 0.98, 0.95)
    key_light = bpy.data.objects.new(name="DramaticKey", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.2, -1.2, 1.2))
    key_light.rotation_euler = Euler((math.radians(50), 0, math.radians(45)))
    
    # Very subtle fill light
    fill_light_data = bpy.data.lights.new(name="DramaticFill", type='AREA')
    fill_light_data.energy = 50.0  # Very low energy for high contrast
    fill_light_data.size = 2.0
    fill_light_data.color = (0.8, 0.85, 0.9)  # Slightly blue
    fill_light = bpy.data.objects.new(name="DramaticFill", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.3))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Sharp rim light
    rim_light_data = bpy.data.lights.new(name="DramaticRim", type='SPOT')
    rim_light_data.energy = 400.0
    rim_light_data.spot_size = math.radians(30)  # Narrower spot
    rim_light_data.spot_blend = 0.3  # Sharper falloff
    rim_light_data.color = (1.0, 1.0, 1.0)
    rim_light = bpy.data.objects.new(name="DramaticRim", object_data=rim_light_data)
    bpy.context.collection.objects.link(rim_light)
    rim_light.location = Vector((-0.7, 1.0, 0.9))
    rim_light.rotation_euler = Euler((math.radians(-50), 0, math.radians(-135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_cinematic_lighting():
    """Create a cinematic lighting setup"""
    print("Creating cinematic lighting setup")
    
    # Main key light
    key_light_data = bpy.data.lights.new(name="CinematicKey", type='AREA')
    key_light_data.energy = 600.0
    key_light_data.size = 1.5
    key_light_data.color = (1.0, 0.95, 0.9)  # Slightly warm
    key_light = bpy.data.objects.new(name="CinematicKey", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.0, -1.0, 1.0))
    key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Subtle fill light
    fill_light_data = bpy.data.lights.new(name="CinematicFill", type='AREA')
    fill_light_data.energy = 100.0
    fill_light_data.size = 3.0
    fill_light_data.color = (0.85, 0.9, 1.0)  # Slightly cool
    fill_light = bpy.data.objects.new(name="CinematicFill", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Rim light
    rim_light_data = bpy.data.lights.new(name="CinematicRim", type='AREA')
    rim_light_data.energy = 350.0
    rim_light_data.size = 0.5
    rim_light_data.color = (1.0, 1.0, 1.0)
    rim_light = bpy.data.objects.new(name="CinematicRim", object_data=rim_light_data)
    bpy.context.collection.objects.link(rim_light)
    rim_light.location = Vector((-0.5, 1.0, 0.8))
    rim_light.rotation_euler = Euler((math.radians(-45), 0, math.radians(-135)))
    
    # Accent light (kicker)
    accent_light_data = bpy.data.lights.new(name="CinematicAccent", type='SPOT')
    accent_light_data.energy = 200.0
    accent_light_data.spot_size = math.radians(20)
    accent_light_data.spot_blend = 0.3
    accent_light_data.color = (1.0, 0.9, 0.8)  # Warm accent
    accent_light = bpy.data.objects.new(name="CinematicAccent", object_data=accent_light_data)
    bpy.context.collection.objects.link(accent_light)
    accent_light.location = Vector((0.8, 0.8, 0.4))
    accent_light.rotation_euler = Euler((math.radians(-20), math.radians(-15), math.radians(135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_dark_rim_lighting():
    """Create a dark rim lighting setup with strong rim lights"""
    print("Creating dark_rim lighting setup")
    
    # Subtle fill light
    fill_light_data = bpy.data.lights.new(name="DarkFill", type='AREA')
    fill_light_data.energy = 100.0
    fill_light_data.size = 1.5
    fill_light_data.color = (0.7, 0.75, 0.85)
    fill_light = bpy.data.objects.new(name="DarkFill", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((0.0, -1.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(20), 0, math.radians(-30)))
    
    # Rim light 1
    rim_light1_data = bpy.data.lights.new(name="DarkRim1", type='AREA')
    rim_light1_data.energy = 400.0
    rim_light1_data.size = 0.3
    rim_light1_data.color = (1.0, 1.0, 1.0)
    rim_light1 = bpy.data.objects.new(name="DarkRim1", object_data=rim_light1_data)
    bpy.context.collection.objects.link(rim_light1)
    rim_light1.location = Vector((-0.8, 0.8, 0.7))
    rim_light1.rotation_euler = Euler((math.radians(-30), math.radians(15), math.radians(-135)))
    
    # Rim light 2
    rim_light2_data = bpy.data.lights.new(name="DarkRim2", type='AREA')
    rim_light2_data.energy = 300.0
    rim_light2_data.size = 0.3
    rim_light2_data.color = (1.0, 0.98, 0.95)
    rim_light2 = bpy.data.objects.new(name="DarkRim2", object_data=rim_light2_data)
    bpy.context.collection.objects.link(rim_light2)
    rim_light2.location = Vector((0.8, 0.8, 0.5))
    rim_light2.rotation_euler = Euler((math.radians(-30), math.radians(-15), math.radians(135)))
    
    # Apply random global rotation
    apply_random_global_rotation()


def create_soft_fill_lighting():
    """Create a soft fill lighting setup with gentle, even illumination"""
    print("Creating soft_fill lighting setup")
    
    # Large soft key light
    key_light_data = bpy.data.lights.new(name="SoftKey", type='AREA')
    key_light_data.energy = 300.0
    key_light_data.size = 4.0  # Very large for soft shadows
    key_light_data.color = (1.0, 1.0, 1.0)
    key_light = bpy.data.objects.new(name="SoftKey", object_data=key_light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = Vector((1.0, -1.0, 1.0))
    key_light.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    
    # Large fill light
    fill_light_data = bpy.data.lights.new(name="SoftFill", type='AREA')
    fill_light_data.energy = 250.0
    fill_light_data.size = 3.5
    fill_light_data.color = (1.0, 1.0, 1.0)
    fill_light = bpy.data.objects.new(name="SoftFill", object_data=fill_light_data)
    bpy.context.collection.objects.link(fill_light)
    fill_light.location = Vector((-1.0, -0.5, 0.5))
    fill_light.rotation_euler = Euler((math.radians(30), 0, math.radians(-45)))
    
    # Soft top light
    top_light_data = bpy.data.lights.new(name="SoftTop", type='AREA')
    top_light_data.energy = 200.0
    top_light_data.size = 2.0
    top_light_data.color = (1.0, 1.0, 1.0)
    top_light = bpy.data.objects.new(name="SoftTop", object_data=top_light_data)
    bpy.context.collection.objects.link(top_light)
    top_light.location = Vector((0.0, 0.0, 1.5))
    top_light.rotation_euler = Euler((math.radians(-90), 0, 0))
    
    # Apply random global rotation
    apply_random_global_rotation()


def apply_random_global_rotation():
    """Apply a random global rotation to all lights"""
    random_global_rotation = random.uniform(0, 2 * math.pi)
    print(f"Applying random global rotation to all lights: {math.degrees(random_global_rotation):.1f} degrees")
    
    cos_theta = math.cos(random_global_rotation)
    sin_theta = math.sin(random_global_rotation)
    
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            orig_x = obj.location.x
            orig_y = obj.location.y
            
            # Rotate position around Z axis
            new_x = (orig_x * cos_theta) - (orig_y * sin_theta)
            new_y = (orig_x * sin_theta) + (orig_y * cos_theta)
            
            obj.location.x = new_x
            obj.location.y = new_y
            
            # Rotate orientation around Z axis
            obj.rotation_euler.z += random_global_rotation


def ensure_lights_contribute_to_diffuse():
    """Ensure all lights contribute to diffuse"""
    print("\n--- ENSURE LIGHTS CONTRIBUTE TO DIFFUSE DEBUG ---")
    print("Checking all lights to ensure they contribute to diffuse")
    
    count = 0
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            light = obj.data
            if hasattr(light, 'use_diffuse'):
                if not light.use_diffuse:
                    light.use_diffuse = True
                    count += 1
                    print(f"Enabled diffuse contribution for light: {obj.name}")
    
    print(f"Enabled diffuse contribution for {count} lights")
    print("--- END ENSURE LIGHTS CONTRIBUTE TO DIFFUSE DEBUG ---\n")


def validate_world_texture():
    """
    Check if the environment texture node has a valid image assigned.
    If not, create a default environment to prevent pink artifacts.
    """
    print("\n--- VALIDATE WORLD TEXTURE DEBUG ---")
    print(f"Validating world texture with CURRENT_HDRI_NAME: '{BATCH_main_manager.CURRENT_HDRI_NAME}'")
    
    world = bpy.context.scene.world
    if not world or not world.use_nodes:
        print("No world or world not using nodes, creating default environment")
        create_default_environment()
        return
    
    # Check if there's an environment texture node with a valid image
    env_tex_node = None
    background_node = None
    output_node = None
    mapping_node = None
    tex_coord_node = None
    
    # Identify all relevant nodes
    print("Checking world nodes:")
    for node in world.node_tree.nodes:
        print(f"  - Found node: {node.name} (type: {node.type})")
        if node.type == 'TEX_ENVIRONMENT':
            env_tex_node = node
        elif node.type == 'BACKGROUND':
            background_node = node
        elif node.type == 'OUTPUT_WORLD':
            output_node = node
        elif node.type == 'MAPPING':
            mapping_node = node
        elif node.type == 'TEX_COORD':
            tex_coord_node = node
    
    # Check if we have all required nodes
    if not env_tex_node:
        print("No environment texture node found, creating default environment")
        create_default_environment()
        return
    
    if not background_node:
        print("No background node found, creating default environment")
        create_default_environment()
        return
    
    if not output_node:
        print("No world output node found, creating default environment")
        create_default_environment()
        return
    
    # Check node connections
    print("Checking node connections:")
    links = world.node_tree.links
    
    # Check if environment texture is connected to background
    env_to_bg_connected = False
    for link in links:
        if (link.from_node == env_tex_node and link.to_node == background_node and
            link.from_socket.name == 'Color' and link.to_socket.name == 'Color'):
            env_to_bg_connected = True
            print("  - Environment texture is connected to background node")
            break
    
    if not env_to_bg_connected:
        print("Environment texture not connected to background node, creating default environment")
        create_default_environment()
        return
    
    # Check if background is connected to output
    bg_to_output_connected = False
    for link in links:
        if (link.from_node == background_node and link.to_node == output_node and
            link.from_socket.name == 'Background' and link.to_socket.name == 'Surface'):
            bg_to_output_connected = True
            print("  - Background node is connected to world output")
            break
    
    if not bg_to_output_connected:
        print("Background node not connected to world output, creating default environment")
        create_default_environment()
        return
    
    # Check if mapping is connected to environment texture (if mapping exists)
    if mapping_node and tex_coord_node:
        mapping_connected = False
        for link in links:
            if (link.from_node == mapping_node and link.to_node == env_tex_node and
                link.from_socket.name == 'Vector' and link.to_socket.name == 'Vector'):
                mapping_connected = True
                print("  - Mapping node is connected to environment texture")
                break
        
        if not mapping_connected:
            print("Mapping node exists but is not properly connected to environment texture")
            print("Fixing mapping node connection...")
            # Try to fix the connection
            for link in links:
                if link.to_node == env_tex_node and link.to_socket.name == 'Vector':
                    links.remove(link)
            links.new(mapping_node.outputs['Vector'], env_tex_node.inputs['Vector'])
            print("  - Fixed mapping node connection")
    
    # Check if the environment texture has a valid image
    if not env_tex_node.image:
        print("Environment texture node has no image, creating default environment")
        create_default_environment()
        return
    
    # Check if the image is valid
    try:
        if env_tex_node.image.size[0] == 0 or env_tex_node.image.size[1] == 0:
            print("Environment texture has invalid dimensions, creating default environment")
            create_default_environment()
            return
        
        print(f"Environment texture image: {env_tex_node.image.name}")
        print(f"Image dimensions: {env_tex_node.image.size[0]}x{env_tex_node.image.size[1]}")
        print(f"Image filepath: {env_tex_node.image.filepath}")
        
        # Check if the image file exists
        if env_tex_node.image.filepath and not os.path.exists(bpy.path.abspath(env_tex_node.image.filepath)):
            print(f"WARNING: Image file does not exist at path: {bpy.path.abspath(env_tex_node.image.filepath)}")
            print("This may cause rendering issues but the node setup appears valid")
    except Exception as e:
        print(f"Error checking environment texture dimensions: {str(e)}")
        print("Creating default environment")
        create_default_environment()
        return
    
    print(f"World texture validated successfully: {env_tex_node.image.name} ({env_tex_node.image.size[0]}x{env_tex_node.image.size[1]})")
    print("--- END VALIDATE WORLD TEXTURE DEBUG ---\n")


def create_studio_neutral_lighting():
    """Create a neutral studio lighting setup with three-point lighting"""
    # Key light (main light)
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 1000.0
    key_light.data.size = 1.0
    key_light.data.shape = 'RECTANGLE'
    key_light.data.size_y = 0.5
    key_light.location = (3.0, -3.0, 3.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(45))
    key_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(key_light)
    
    # Fill light (softer light to fill shadows)
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 400.0
    fill_light.data.size = 2.0
    fill_light.data.shape = 'RECTANGLE'
    fill_light.data.size_y = 1.0
    fill_light.location = (-3.0, -2.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(fill_light)
    
    # Rim light (backlight for edge definition)
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 800.0
    rim_light.data.spot_size = math.radians(45)
    rim_light.data.spot_blend = 0.15
    rim_light.location = (0.0, 3.0, 3.0)
    rim_light.rotation_euler = (math.radians(-45), 0, 0)
    rim_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(rim_light)
    
    print("Created studio neutral lighting setup")


def create_studio_warm_lighting():
    """Create a warm studio lighting setup with three-point lighting"""
    # Key light (main light)
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 1000.0
    key_light.data.size = 1.0
    key_light.data.shape = 'RECTANGLE'
    key_light.data.size_y = 0.5
    key_light.location = (3.0, -3.0, 3.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(45))
    key_light.data.color = (1.0, 0.9, 0.8)  # Warm tint
    bpy.context.collection.objects.link(key_light)
    
    # Fill light (softer light to fill shadows)
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 400.0
    fill_light.data.size = 2.0
    fill_light.data.shape = 'RECTANGLE'
    fill_light.data.size_y = 1.0
    fill_light.location = (-3.0, -2.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (1.0, 0.95, 0.9)  # Slight warm tint
    bpy.context.collection.objects.link(fill_light)
    
    # Rim light (backlight for edge definition)
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 800.0
    rim_light.data.spot_size = math.radians(45)
    rim_light.data.spot_blend = 0.15
    rim_light.location = (0.0, 3.0, 3.0)
    rim_light.rotation_euler = (math.radians(-45), 0, 0)
    rim_light.data.color = (1.0, 0.85, 0.7)  # Warmer rim light
    bpy.context.collection.objects.link(rim_light)
    
    print("Created studio warm lighting setup")


def create_studio_cool_lighting():
    """Create a cool studio lighting setup with three-point lighting"""
    # Key light (main light)
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 1000.0
    key_light.data.size = 1.0
    key_light.data.shape = 'RECTANGLE'
    key_light.data.size_y = 0.5
    key_light.location = (3.0, -3.0, 3.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(45))
    key_light.data.color = (0.8, 0.9, 1.0)  # Cool tint
    bpy.context.collection.objects.link(key_light)
    
    # Fill light (softer light to fill shadows)
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 400.0
    fill_light.data.size = 2.0
    fill_light.data.shape = 'RECTANGLE'
    fill_light.data.size_y = 1.0
    fill_light.location = (-3.0, -2.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (0.9, 0.95, 1.0)  # Slight cool tint
    bpy.context.collection.objects.link(fill_light)
    
    # Rim light (backlight for edge definition)
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 800.0
    rim_light.data.spot_size = math.radians(45)
    rim_light.data.spot_blend = 0.15
    rim_light.location = (0.0, 3.0, 3.0)
    rim_light.rotation_euler = (math.radians(-45), 0, 0)
    rim_light.data.color = (0.7, 0.85, 1.0)  # Cooler rim light
    bpy.context.collection.objects.link(rim_light)
    
    print("Created studio cool lighting setup")


def create_dramatic_lighting():
    """Create a dramatic lighting setup with high contrast"""
    # Strong key light
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='SPOT'))
    key_light.data.energy = 1500.0
    key_light.data.spot_size = math.radians(30)
    key_light.data.spot_blend = 0.1
    key_light.location = (4.0, -2.0, 4.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(30))
    key_light.data.color = (1.0, 0.95, 0.9)
    bpy.context.collection.objects.link(key_light)
    
    # Very subtle fill light
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 100.0
    fill_light.data.size = 3.0
    fill_light.location = (-3.0, -1.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (0.8, 0.9, 1.0)  # Slight blue tint
    bpy.context.collection.objects.link(fill_light)
    
    # Strong rim light
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 1200.0
    rim_light.data.spot_size = math.radians(25)
    rim_light.data.spot_blend = 0.1
    rim_light.location = (-1.0, 3.0, 3.0)
    rim_light.rotation_euler = (math.radians(-45), 0, math.radians(-15))
    rim_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(rim_light)
    
    print("Created dramatic lighting setup")


def create_cinematic_lighting():
    """Create a cinematic lighting setup with colored lights"""
    # Main key light (warm)
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 800.0
    key_light.data.size = 1.5
    key_light.data.shape = 'RECTANGLE'
    key_light.data.size_y = 0.75
    key_light.location = (3.0, -2.5, 2.5)
    key_light.rotation_euler = (math.radians(40), 0, math.radians(45))
    key_light.data.color = (1.0, 0.85, 0.7)  # Orange-ish
    bpy.context.collection.objects.link(key_light)
    
    # Fill light (cool)
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 300.0
    fill_light.data.size = 2.0
    fill_light.location = (-3.0, -1.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (0.7, 0.8, 1.0)  # Blue-ish
    bpy.context.collection.objects.link(fill_light)
    
    # Rim light (neutral)
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 1000.0
    rim_light.data.spot_size = math.radians(35)
    rim_light.data.spot_blend = 0.2
    rim_light.location = (0.0, 3.0, 3.0)
    rim_light.rotation_euler = (math.radians(-45), 0, 0)
    rim_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(rim_light)
    
    # Accent light (purple)
    accent_light = bpy.data.objects.new("Accent_Light", bpy.data.lights.new(name="Accent_Light", type='SPOT'))
    accent_light.data.energy = 500.0
    accent_light.data.spot_size = math.radians(20)
    accent_light.data.spot_blend = 0.1
    accent_light.location = (-2.0, 2.0, 0.5)
    accent_light.rotation_euler = (math.radians(10), 0, math.radians(-135))
    accent_light.data.color = (0.8, 0.6, 1.0)  # Purple-ish
    bpy.context.collection.objects.link(accent_light)
    
    print("Created cinematic lighting setup")


def create_dark_rim_lighting():
    """Create a dark lighting setup with strong rim light"""
    # Subtle key light
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 300.0
    key_light.data.size = 1.0
    key_light.location = (2.0, -2.0, 2.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(45))
    key_light.data.color = (0.9, 0.9, 1.0)  # Slightly cool
    bpy.context.collection.objects.link(key_light)
    
    # Very subtle fill light
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 100.0
    fill_light.data.size = 3.0
    fill_light.location = (-2.0, -1.0, 1.0)
    fill_light.rotation_euler = (math.radians(30), 0, math.radians(-45))
    fill_light.data.color = (0.8, 0.8, 0.9)
    bpy.context.collection.objects.link(fill_light)
    
    # Strong rim light
    rim_light = bpy.data.objects.new("Rim_Light", bpy.data.lights.new(name="Rim_Light", type='SPOT'))
    rim_light.data.energy = 1500.0
    rim_light.data.spot_size = math.radians(30)
    rim_light.data.spot_blend = 0.1
    rim_light.location = (0.0, 3.0, 2.5)
    rim_light.rotation_euler = (math.radians(-45), 0, 0)
    rim_light.data.color = (1.0, 0.95, 0.9)
    bpy.context.collection.objects.link(rim_light)
    
    print("Created dark rim lighting setup")


def create_soft_fill_lighting():
    """Create a soft, even lighting setup with minimal shadows"""
    # Soft key light
    key_light = bpy.data.objects.new("Key_Light", bpy.data.lights.new(name="Key_Light", type='AREA'))
    key_light.data.energy = 600.0
    key_light.data.size = 3.0
    key_light.data.shape = 'RECTANGLE'
    key_light.data.size_y = 2.0
    key_light.location = (2.0, -2.0, 3.0)
    key_light.rotation_euler = (math.radians(45), 0, math.radians(45))
    key_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(key_light)
    
    # Strong fill light
    fill_light = bpy.data.objects.new("Fill_Light", bpy.data.lights.new(name="Fill_Light", type='AREA'))
    fill_light.data.energy = 500.0
    fill_light.data.size = 3.0
    fill_light.data.shape = 'RECTANGLE'
    fill_light.data.size_y = 2.0
    fill_light.location = (-2.0, -2.0, 2.0)
    fill_light.rotation_euler = (math.radians(45), 0, math.radians(-45))
    fill_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(fill_light)
    
    # Soft top light
    top_light = bpy.data.objects.new("Top_Light", bpy.data.lights.new(name="Top_Light", type='AREA'))
    top_light.data.energy = 400.0
    top_light.data.size = 2.0
    top_light.location = (0.0, 0.0, 4.0)
    top_light.rotation_euler = (0, 0, 0)
    top_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(top_light)
    
    # Soft back light
    back_light = bpy.data.objects.new("Back_Light", bpy.data.lights.new(name="Back_Light", type='AREA'))
    back_light.data.energy = 300.0
    back_light.data.size = 2.0
    back_light.location = (0.0, 3.0, 2.0)
    back_light.rotation_euler = (math.radians(-45), 0, 0)
    back_light.data.color = (1.0, 1.0, 1.0)
    bpy.context.collection.objects.link(back_light)
    
    print("Created soft fill lighting setup")
