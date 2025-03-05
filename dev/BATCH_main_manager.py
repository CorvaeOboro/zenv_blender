"""
BATCH_main_manager.py

Main Task Manager for the Metal Ingot Batch Renderer.
This module sets global configuration, loads the external metal ingot addon,
sets up the scene and camera, calls into the BATCH_light_manager and BATCH_material_manager,
handles file naming and rendering, and runs the main generation loop.

Example command:
& "C:\Program Files\Blender Foundation\Blender 4.0\blender.exe" --background --python "d:\BLENDER\dev\BATCH_main_manager.py"
"""

import bpy
import os
import sys
import random
import datetime
import math
import time
import re
import tempfile
from mathutils import Vector, Euler

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import BATCH modular managers
import BATCH_light_manager 
import BATCH_material_manager 

# Global Settings / Configuration
SCRIPT_FOLDER = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "metal_ingot_renders"))
TEXTURE_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "textures"))
HDRI_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "hdri"))
LIGHTING_PRESET_FOLDER = os.path.abspath(os.path.join(SCRIPT_FOLDER, "lighting_presets"))

NUMBER_OF_GENERATIONS = 500
USE_CUSTOM_PRESETS = True
CAMERA_ANGLE = 'LEFT_LOWER'  # Options: 'LEFT_LOWER' or 'RIGHT_LOWER'
LIGHTING_PRESETS = [
    "studio_bright", 
    "dark_rim", 
    "blacksmith_forge", 
    "night_scene", 
    "magical", 
    "cinematic"
]

# Global variables to track material and lighting information
CURRENT_HDRI_NAME = None
CURRENT_TEXTURE_NAME = None
CURRENT_MATERIAL_TYPE = None
CURRENT_MATERIAL_NAME = None
CURRENT_LIGHTING_PRESET = None

# Path to the metal ingot addon
METAL_INGOT_ADDON_PATH = os.path.abspath(os.path.join(os.path.dirname(SCRIPT_FOLDER), "addon", "wip", "z_blender_GEN_metal_ingot.py"))

def load_metal_ingot_addon():
    """
    Load the metal ingot addon if it's not already loaded
    
    Returns:
        bool: True if the addon is loaded successfully, False otherwise
    """
    try:
        # Print debug information
        print(f"\n--- LOADING METAL INGOT ADDON ---")
        print(f"Addon path: {METAL_INGOT_ADDON_PATH}")
        
        # Check if the addon file exists
        if not os.path.exists(METAL_INGOT_ADDON_PATH):
            print(f"ERROR: Metal Ingot addon not found at {METAL_INGOT_ADDON_PATH}")
            print(f"Current directory: {os.getcwd()}")
            print(f"Script directory: {SCRIPT_FOLDER}")
            return False
        
        print(f"Addon file exists: {METAL_INGOT_ADDON_PATH}")
        
        # Try to unregister the addon if it's already registered
        try:
            if hasattr(bpy.ops, 'zenv') and hasattr(bpy.ops.zenv, 'metal_ingot'):
                print("Metal Ingot addon is already registered, unregistering first...")
                # Import the module directly from the file path
                addon_name = os.path.basename(METAL_INGOT_ADDON_PATH).split('.')[0]
                if addon_name in sys.modules:
                    addon_module = sys.modules[addon_name]
                    if hasattr(addon_module, 'unregister'):
                        addon_module.unregister()
                        print(f"Successfully unregistered Metal Ingot addon")
        except Exception as unreg_err:
            print(f"WARNING: Error unregistering addon: {unreg_err}")
        
        # Add the addon directory to sys.path if not already there
        addon_dir = os.path.dirname(METAL_INGOT_ADDON_PATH)
        if addon_dir not in sys.path:
            sys.path.append(addon_dir)
            print(f"Added addon directory to sys.path: {addon_dir}")
        
        # Direct module loading approach
        addon_name = os.path.basename(METAL_INGOT_ADDON_PATH).split('.')[0]
        print(f"Loading addon module: {addon_name}")
        
        # Remove the module from sys.modules if it exists
        if addon_name in sys.modules:
            del sys.modules[addon_name]
            print(f"Removed existing module from sys.modules: {addon_name}")
        
        # Import the module directly from the file path
        import importlib.util
        spec = importlib.util.spec_from_file_location(addon_name, METAL_INGOT_ADDON_PATH)
        if not spec:
            print(f"ERROR: Failed to create module spec for {addon_name}")
            return False
            
        addon_module = importlib.util.module_from_spec(spec)
        sys.modules[addon_name] = addon_module
        spec.loader.exec_module(addon_module)
        print(f"Successfully loaded module: {addon_name}")
        
        # Register the addon
        if hasattr(addon_module, 'register'):
            print(f"Calling register() function from addon module")
            addon_module.register()
            print(f"Successfully registered Metal Ingot addon")
            
            # Verify registration was successful
            if hasattr(bpy.ops, 'zenv') and hasattr(bpy.ops.zenv, 'metal_ingot'):
                print("Verified: Metal Ingot addon is now registered")
                print("Available zenv operators:", dir(bpy.ops.zenv))
                return True
            else:
                print("WARNING: Register function completed but operator not found")
                print("Available operators in bpy.ops:", dir(bpy.ops))
                if hasattr(bpy.ops, 'zenv'):
                    print("Available zenv operators:", dir(bpy.ops.zenv))
                return False
        else:
            print(f"ERROR: Metal Ingot addon does not have a register function")
            print(f"Available attributes in module: {dir(addon_module)}")
            return False
    except Exception as e:
        print(f"ERROR: Failed to load Metal Ingot addon: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print(f"--- END LOADING METAL INGOT ADDON ---\n")


def create_metal_ingot():
    """Create a metal ingot using the addon operator with default parameters"""
    try:
        print("\n--- CREATING METAL INGOT ---")
        
        # Load the metal ingot addon if it's not already loaded
        if not load_metal_ingot_addon():
            print("ERROR: Failed to load Metal Ingot addon, cannot create ingot")
            return None
        
        # Print available operators for debugging
        print("Available operators in bpy.ops:", [op for op in dir(bpy.ops) if not op.startswith('_')])
        if hasattr(bpy.ops, 'zenv'):
            print("Available zenv operators:", [op for op in dir(bpy.ops.zenv) if not op.startswith('_')])
        else:
            print("ERROR: 'zenv' namespace not found in bpy.ops")
            return None
            
        # Use the addon operator to create the ingot with its default parameters
        print("Attempting to call bpy.ops.zenv.metal_ingot()")
        try:
            bpy.ops.zenv.metal_ingot()
            print("Successfully called metal_ingot operator")
        except Exception as op_error:
            print(f"ERROR: Failed to call metal_ingot operator: {op_error}")
            import traceback
            traceback.print_exc()
            return None
        
        # Find the created ingot object
        ingot_obj = None
        print("Searching for Metal_Ingot object...")
        for obj in bpy.context.scene.objects:
            print(f"Found object: {obj.name} (type: {obj.type})")
            if obj.type == 'MESH' and 'Metal_Ingot' in obj.name:
                ingot_obj = obj
                break
                
        if ingot_obj:
            print(f"Created metal ingot using addon operator: {ingot_obj.name}")
            print("--- END CREATING METAL INGOT ---\n")
            return ingot_obj
        else:
            print("ERROR: Metal Ingot object not found after running operator")
            print("Objects in scene:", [obj.name for obj in bpy.context.scene.objects])
            return None
    except Exception as e:
        print(f"ERROR: Failed to create metal ingot using addon: {e}")
        import traceback
        traceback.print_exc()
        return None


# Create output and asset directories if they don't exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEXTURE_FOLDER, exist_ok=True)
os.makedirs(HDRI_FOLDER, exist_ok=True)
os.makedirs(LIGHTING_PRESET_FOLDER, exist_ok=True)

# Add BLENDER ADDON directory to Python path
blender_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if blender_root not in sys.path:
    sys.path.append(blender_root)

def setup_scene():
    """Set up a basic scene for rendering, with a camera and environment"""
    global CURRENT_HDRI_NAME
    
    print("\n--- SETUP SCENE DEBUG ---")
    print(f"Before setup - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Set up rendering parameters
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'GPU'
    bpy.context.scene.cycles.samples = 512
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.film_transparent = True
    
    # Set up world environment
    hdri_result = BATCH_light_manager.find_hdri_texture()
    hdri_path = None
    hdri_name = None
    
    if isinstance(hdri_result, tuple) and len(hdri_result) >= 1:
        hdri_path = hdri_result[0]
        if len(hdri_result) > 1:
            hdri_name = hdri_result[1]
            CURRENT_HDRI_NAME = hdri_name
            print(f"Set CURRENT_HDRI_NAME to: '{CURRENT_HDRI_NAME}'")
    
    if hdri_path:
        hdri_name_from_env = BATCH_light_manager.setup_hdri_environment(hdri_path)
        if hdri_name_from_env:
            CURRENT_HDRI_NAME = hdri_name_from_env
            print(f"Updated CURRENT_HDRI_NAME to: '{CURRENT_HDRI_NAME}'")
    else:
        BATCH_light_manager.create_default_environment()
    
    # Validate that the world texture is properly set up
    print("\nValidating world texture setup:")
    BATCH_light_manager.validate_world_texture()
    
    print(f"After setup - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print("--- END SETUP SCENE DEBUG ---\n")


def reset_scene():
    """Reset the scene to a clean state"""
    global CURRENT_HDRI_NAME
    
    print("\n--- RESET SCENE DEBUG ---")
    print(f"Before reset - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Set up rendering parameters
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'GPU'
    bpy.context.scene.cycles.samples = 512
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.film_transparent = True
    
    # Set up world environment
    BATCH_light_manager.create_default_environment()
    
    # Validate that the world texture is properly set up
    print("\nValidating world texture setup:")
    BATCH_light_manager.validate_world_texture()
    
    print(f"After reset - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print("--- END RESET SCENE DEBUG ---\n")


def create_camera():
    """Create and position a camera for proper ingot viewing"""
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera_hoffset_distance = 0.3
    camera_voffset_distance = 0.42
    if CAMERA_ANGLE == 'LEFT_LOWER':
        camera.location = Vector(((-0.313492),(-0.36858), 0.349892))
        camera.rotation_euler = Euler((math.radians(54.2), 0, math.radians(-40.2)))
    else:  # 'RIGHT_LOWER'
        camera.location = Vector((camera_hoffset_distance, (camera_hoffset_distance*-1), camera_voffset_distance))
        camera.rotation_euler = Euler((math.radians(45), 0, math.radians(45)))
    camera_to_object_distance = math.sqrt(camera_hoffset_distance**2 + camera_hoffset_distance**2 + camera_voffset_distance**2)
    camera.data.type = 'PERSP'
    camera.data.lens = 85
    camera.data.clip_start = 0.01
    camera.data.clip_end = 100
    camera.data.dof.use_dof = False
    camera.data.dof.focus_distance = camera_to_object_distance
    camera.data.dof.aperture_fstop = 5.6
    bpy.context.scene.camera = camera
    return camera


def setup_render_settings():
    """Set up render settings"""
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'GPU'
    bpy.context.scene.cycles.samples = 512
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.film_transparent = True


def generate_filename(material_type, material_name, texture_name=None):
    """
    Generate a filename for the render based on material and texture information
    
    Format: metal_ingot_YYYYMMDD_HHMMSS_HDRI_name_TEXTURE_name_LIGHT_preset
    Example: metal_ingot_20250303_160006_HDRI_workshop_8k_TEXTURE_Layer_75_c49_LIGHT_warm_sunlight
    """
    global CURRENT_HDRI_NAME, CURRENT_LIGHTING_PRESET
    
    print("\n--- GENERATE FILENAME DEBUG ---")
    print(f"Starting generate_filename with:")
    print(f"  material_type: '{material_type}'")
    print(f"  material_name: '{material_name}'")
    print(f"  texture_name: '{texture_name}'")
    print(f"  CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print(f"  CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
    
    # Get current date and time
    import datetime
    now = datetime.datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    
    print(f"  Date: {date_str}")
    print(f"  Time: {time_str}")
    
    # Object name is always "metal_ingot"
    object_name = "metal_ingot"
    
    # Clean up HDRI name - could be None if no HDRI is used
    hdri_part = "HDRI_none"
    if CURRENT_HDRI_NAME is not None and CURRENT_HDRI_NAME:
        hdri_name_str = str(CURRENT_HDRI_NAME)
        # Remove file extension if present
        hdri_name_str = hdri_name_str.split('.')[0]
        # Clean up HDRI name to prevent compounding
        hdri_name_str = hdri_name_str.replace(' ', '_')
        hdri_part = f"HDRI_{hdri_name_str}"
        print(f"  HDRI part: '{hdri_part}'")
    
    # Handle texture_name - could be None for procedural materials
    texture_part = "TEXTURE_none"
    if texture_name is not None and texture_name:
        texture_name_str = str(texture_name)
        # Clean up texture name
        texture_name_str = texture_name_str.replace(' ', '_')
        texture_part = f"TEXTURE_{texture_name_str}"
        print(f"  Texture part: '{texture_part}'")
    
    # Handle lighting preset - could be None if no preset is used
    lighting_part = "LIGHT_none"
    if CURRENT_LIGHTING_PRESET is not None and CURRENT_LIGHTING_PRESET:
        lighting_preset_str = str(CURRENT_LIGHTING_PRESET)
        # Clean up lighting preset
        lighting_preset_str = lighting_preset_str.replace(' ', '_')
        lighting_part = f"LIGHT_{lighting_preset_str}"
        print(f"  Lighting part: '{lighting_part}'")
    
    # Construct the filename - follow the requested convention
    # Format: metal_ingot_YYYYMMDD_HHMMSS_HDRI_name_TEXTURE_name_LIGHT_preset
    filename = f"{object_name}_{date_str}_{time_str}_{hdri_part}_{texture_part}_{lighting_part}"
    
    # Clean the filename to remove any invalid characters
    filename = filename.replace(".", "_").lower()
    
    print(f"Generated filename: '{filename}'")
    print("--- END GENERATE FILENAME DEBUG ---\n")
    
    return filename


def generate_and_render(output_folder, texture_folder=None, hdri_folder=None, number_of_generations=5):
    """Generate and render multiple metal ingots with different materials and lighting"""
    print("\n=== STARTING BATCH RENDERING ===")
    print(f"Output folder: {output_folder}")
    print(f"Texture folder: {texture_folder}")
    print(f"HDRI folder: {hdri_folder}")
    print(f"Number of generations: {number_of_generations}")
    
    # Set global variables
    global OUTPUT_FOLDER, TEXTURE_FOLDER, HDRI_FOLDER, NUMBER_OF_GENERATIONS
    global CURRENT_HDRI_NAME, CURRENT_LIGHTING_PRESET, CURRENT_MATERIAL_TYPE, CURRENT_MATERIAL_NAME, CURRENT_TEXTURE_NAME
    
    # Store original values for debugging
    original_hdri_name = CURRENT_HDRI_NAME
    original_lighting_preset = CURRENT_LIGHTING_PRESET
    
    print(f"\n--- GENERATE_AND_RENDER GLOBAL VARIABLE DEBUG ---")
    print(f"Initial CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print(f"Initial CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
    
    OUTPUT_FOLDER = output_folder
    TEXTURE_FOLDER = texture_folder
    HDRI_FOLDER = hdri_folder
    NUMBER_OF_GENERATIONS = number_of_generations
    
    # Initialize other global variables
    CURRENT_HDRI_NAME = None
    CURRENT_LIGHTING_PRESET = None
    CURRENT_MATERIAL_TYPE = None
    CURRENT_MATERIAL_NAME = None
    CURRENT_TEXTURE_NAME = None
    
    print(f"Initial CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print(f"Initial CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
    
    # Create output folder if it doesn't exist
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        
    # Create a new scene
    setup_scene()
        
    print(f"After setup_scene - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
    print(f"After setup_scene - CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        
    # Create ingot
    print("\n--- METAL INGOT CREATION ---")
    ingot_obj = create_metal_ingot()
        
    # Check if ingot creation was successful
    if ingot_obj is None:
        print("\nERROR: Failed to create metal ingot")
        print("Cannot continue without a valid metal ingot object")
        return None
        
    print(f"Successfully created metal ingot: {ingot_obj.name}")
        
    # Set up camera
    camera = create_camera()
        
    # Set up render settings
    setup_render_settings()
        
    try:
        # Loop through the number of generations
        for i in range(NUMBER_OF_GENERATIONS):
            print(f"\n--- GENERATION {i+1}/{NUMBER_OF_GENERATIONS} ---")
            print(f"Before iteration {i+1} - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
            print(f"Before iteration {i+1} - CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
                
            # Apply random material to the ingot
            print("\nApplying random material:")
            print(f"Ingot object: {ingot_obj.name} (type: {ingot_obj.type})")
            material_type, material_name, texture_name = BATCH_material_manager.apply_random_material(ingot_obj)
            print(f"Applied material - Type: {material_type}, Name: {material_name}, Texture: {texture_name}")
                
            # Update global material variables
            CURRENT_MATERIAL_TYPE = material_type
            CURRENT_MATERIAL_NAME = material_name
            CURRENT_TEXTURE_NAME = texture_name
                
            # Set up lighting and HDRI
            print("\nSetting up lighting:")
            hdri_name, lighting_preset = BATCH_light_manager.setup_lighting()
            print(f"Applied lighting - HDRI: {hdri_name}, Preset: {lighting_preset}")
                
            # Update global lighting variables
            CURRENT_HDRI_NAME = hdri_name
            CURRENT_LIGHTING_PRESET = lighting_preset
                
            print(f"After lighting setup - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
            print(f"After lighting setup - CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
            
            # Validate that the world texture is properly set up
            print("\nValidating world texture setup:")
            BATCH_light_manager.validate_world_texture()
                
            # Generate filename
            filename = generate_filename(material_type, material_name, texture_name)
                
            # Save blend file
            blend_filepath = os.path.join(OUTPUT_FOLDER, f"{filename}.blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend_filepath)
            print(f"Saved blend file: {blend_filepath}")
                
            # Render and save image
            render_filepath = os.path.join(OUTPUT_FOLDER, f"{filename}.png")
            bpy.context.scene.render.filepath = render_filepath
            bpy.ops.render.render(write_still=True)
            print(f"Rendered image: {render_filepath}")
                
            print(f"Completed generation {i+1}/{NUMBER_OF_GENERATIONS}")
            print(f"After iteration {i+1} - CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
            print(f"After iteration {i+1} - CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        
        print("\n=== BATCH RENDERING COMPLETE ===")
        print(f"Generated {NUMBER_OF_GENERATIONS} renders in {OUTPUT_FOLDER}")
        print(f"Final CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
        print(f"Final CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        print(f"--- END GENERATE_AND_RENDER GLOBAL VARIABLE DEBUG ---\n")
        return True
        
    except Exception as e:
        print(f"\n=== ERROR IN GENERATE_AND_RENDER ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"Original HDRI_NAME: '{original_hdri_name}'")
        print(f"Current HDRI_NAME: '{CURRENT_HDRI_NAME}'")
        print(f"Original LIGHTING_PRESET: '{original_lighting_preset}'")
        print(f"Current LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        print(f"=== END ERROR REPORT ===\n")
        return None
        

def main():
    """Main function to run the batch rendering process"""
    try:
        print("\n=== STARTING METAL INGOT BATCH RENDERER ===")
        print(f"Output folder: {OUTPUT_FOLDER}")
        print(f"Texture folder: {TEXTURE_FOLDER}")
        print(f"HDRI folder: {HDRI_FOLDER}")
        print(f"Number of generations: {NUMBER_OF_GENERATIONS}")
        
        # Track global variables
        global CURRENT_HDRI_NAME, CURRENT_LIGHTING_PRESET
        print(f"Initial CURRENT_HDRI_NAME: '{CURRENT_HDRI_NAME}'")
        print(f"Initial CURRENT_LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        
        # Create a new scene
        reset_scene()
        
        # Create ingot
        print("\n--- METAL INGOT CREATION ---")
        print(f"Metal Ingot Addon Path: {METAL_INGOT_ADDON_PATH}")
        print(f"Addon exists: {os.path.exists(METAL_INGOT_ADDON_PATH)}")
        
        # Ensure the metal ingot addon is loaded
        if not load_metal_ingot_addon():
            print("ERROR: Failed to load Metal Ingot addon, cannot proceed")
            return None
        
        # Generate and render multiple ingots
        generate_and_render(
            output_folder=OUTPUT_FOLDER,
            texture_folder=TEXTURE_FOLDER,
            hdri_folder=HDRI_FOLDER,
            number_of_generations=NUMBER_OF_GENERATIONS
        )
        
        print("\n=== METAL INGOT BATCH RENDERER COMPLETED SUCCESSFULLY ===")
        return True
        
    except Exception as e:
        print(f"\n=== ERROR IN METAL INGOT BATCH RENDERER ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"Current HDRI_NAME: '{CURRENT_HDRI_NAME}'")
        print(f"Current LIGHTING_PRESET: '{CURRENT_LIGHTING_PRESET}'")
        print(f"=== END ERROR REPORT ===\n")
        return None


if __name__ == "__main__":
    result = main()
    if result is None:
        print("Batch rendering failed")
        sys.exit(1)
    else:
        print("Batch rendering completed successfully")
        sys.exit(0)
