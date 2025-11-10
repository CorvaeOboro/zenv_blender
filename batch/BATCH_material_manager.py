"""
BATCH_material_manager.py

This module handles material creation and modification.
It creates dull and procedural metal materials, applies random textures,
and includes helper functions for shader node adjustments.
"""

import bpy
import os
import random
import math
import traceback
from mathutils import Vector, Euler

# Import global state from BATCH_main_manager so we can update tracking variables
import BATCH_main_manager


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
        node.inputs['Specular'].default_value = value
        return True
    except (KeyError, IndexError):
        try:
            node.inputs['Specular IOR Level'].default_value = value
            return True
        except (KeyError, IndexError):
            for input_idx, input_socket in enumerate(node.inputs):
                if 'specular' in input_socket.name.lower():
                    node.inputs[input_idx].default_value = value
                    print(f"Found specular input as '{input_socket.name}'")
                    return True
            print("Could not set specular value - no matching input found")
            return False


def create_metal_material(obj):
    """Create and apply a dull metal material to the given object"""
    # Create material
    material = bpy.data.materials.new(name="Dull_Metal")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    links.new(principled.outputs[0], output.inputs[0])
    principled.inputs['Metallic'].default_value = 1.0
    principled.inputs['Roughness'].default_value = random.uniform(0.3, 0.7)
    set_specular_value(principled, random.uniform(0.2, 0.5))
    principled.inputs['Base Color'].default_value = (
        random.uniform(0.2, 0.8),
        random.uniform(0.2, 0.8),
        random.uniform(0.2, 0.8),
        1.0
    )
    
    # Apply material to object if it's a mesh
    if obj and obj.type == 'MESH' and hasattr(obj.data, 'materials'):
        try:
            if obj.data.materials:
                obj.data.materials[0] = material
            else:
                obj.data.materials.append(material)
            print(f"Successfully applied material to {obj.name}")
        except Exception as e:
            print(f"ERROR: Failed to apply material to {obj.name}: {e}")
    else:
        print(f"WARNING: Cannot apply material to object: {obj.name if obj else 'None'} (not a mesh or no materials attribute)")
        
    return material


def create_procedural_fantasy_metal(material):
    """Create a procedural shader setup for fantasy metal materials with enhanced micro displacement"""
    fantasy_metals = ["Bismuth", "Orichalcum", "Aged Copper", "Mythril", "Adamantium"]
    selected_type = random.choice(fantasy_metals)
    BATCH_main_manager.CURRENT_MATERIAL_TYPE = selected_type
    print(f"Creating procedural fantasy metal: {selected_type}")
    print(f"Setting CURRENT_MATERIAL_TYPE to: {BATCH_main_manager.CURRENT_MATERIAL_TYPE}")
    material.node_tree.nodes.clear()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (1200, 0)
    principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled_node.location = (900, 0)
    links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = (-800, 0)
    mapping = nodes.new(type='ShaderNodeMapping')
    mapping.location = (-600, 0)
    mapping.inputs['Scale'].default_value = (2.0, 2.0, 2.0)
    links.new(tex_coord.outputs['Object'], mapping.inputs['Vector'])
    noise_tex = nodes.new(type='ShaderNodeTexNoise')
    noise_tex.location = (-400, 0)
    color_ramp = nodes.new(type='ShaderNodeValToRGB')
    color_ramp.location = (-200, 0)
    links.new(mapping.outputs['Vector'], noise_tex.inputs['Vector'])
    links.new(noise_tex.outputs['Fac'], color_ramp.inputs['Fac'])
    links.new(color_ramp.outputs['Color'], principled_node.inputs['Base Color'])
    micro_noise = nodes.new(type='ShaderNodeTexNoise')
    micro_noise.location = (-400, -200)
    micro_noise.inputs['Scale'].default_value = 50.0
    micro_noise.inputs['Detail'].default_value = 15.0
    micro_noise.inputs['Roughness'].default_value = 0.7
    links.new(mapping.outputs['Vector'], micro_noise.inputs['Vector'])
    micro_ramp = nodes.new(type='ShaderNodeValToRGB')
    micro_ramp.location = (-200, -200)
    micro_ramp.color_ramp.elements[0].position = 0.4
    micro_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    micro_ramp.color_ramp.elements[1].position = 0.6
    micro_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    links.new(micro_noise.outputs['Fac'], micro_ramp.inputs['Fac'])
    
    bump_node = nodes.new(type='ShaderNodeBump')
    bump_node.location = (500, -200)
    bump_node.inputs['Strength'].default_value = 0.2
    bump_node.inputs['Distance'].default_value = 0.01
    
    # Connect micro_ramp directly to bump height input instead of multiplying with noise texture
    links.new(micro_ramp.outputs['Color'], bump_node.inputs['Height'])
    links.new(bump_node.outputs['Normal'], principled_node.inputs['Normal'])
    roughness_ramp = nodes.new(type='ShaderNodeValToRGB')
    roughness_ramp.location = (500, -100)
    roughness_math = nodes.new(type='ShaderNodeMath')
    roughness_math.location = (700, -100)
    roughness_math.operation = 'MULTIPLY'
    
    if selected_type == 'Bismuth':
        noise_tex.inputs['Scale'].default_value = 10.0
        noise_tex.inputs['Detail'].default_value = 12.0
        color_ramp.color_ramp.elements.remove(color_ramp.color_ramp.elements[0])
        pos = 0.0
        for color in [(0.8, 0.0, 0.8, 1.0), (0.0, 0.5, 0.8, 1.0),
                      (0.0, 0.8, 0.2, 1.0), (0.8, 0.8, 0.0, 1.0), (0.8, 0.2, 0.0, 1.0)]:
            element = color_ramp.color_ramp.elements.new(pos)
            element.color = color
            pos += 0.25
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.2
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.4, 0.4, 0.4, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.1, 0.1, 0.1, 1.0)
        set_specular_value(principled_node, 1.0)
    elif selected_type == 'Orichalcum':
        noise_tex.inputs['Scale'].default_value = 5.0
        noise_tex.inputs['Detail'].default_value = 8.0
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.8, 0.3, 0.0, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (1.0, 0.6, 0.1, 1.0)
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.1
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.3, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.05, 0.05, 0.05, 1.0)
        set_specular_value(principled_node, 1.0)
    elif selected_type == 'Aged Copper':
        noise_tex.inputs['Scale'].default_value = 15.0
        noise_tex.inputs['Detail'].default_value = 10.0
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.0, 0.4, 0.2, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.8, 0.4, 0.2, 1.0)
        mid_element = color_ramp.color_ramp.elements.new(0.6)
        mid_element.color = (0.2, 0.5, 0.3, 1.0)
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.5
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.7, 0.7, 0.7, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.3, 1.0)
        set_specular_value(principled_node, 0.6)
    elif selected_type == 'Mythril':
        noise_tex.inputs['Scale'].default_value = 8.0
        noise_tex.inputs['Detail'].default_value = 6.0
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.5, 0.8, 1.0, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.8, 0.9, 1.0, 1.0)
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.1
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.3, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.05, 0.05, 0.05, 1.0)
        set_specular_value(principled_node, 1.0)
    else:  # Adamantium
        noise_tex.inputs['Scale'].default_value = 12.0
        noise_tex.inputs['Detail'].default_value = 4.0
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.1, 0.1, 0.1, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.4, 1.0)
        principled_node.inputs['Metallic'].default_value = 1.0
        roughness_math.inputs[1].default_value = 0.3
        roughness_ramp.color_ramp.elements[0].position = 0.0
        roughness_ramp.color_ramp.elements[0].color = (0.5, 0.5, 0.5, 1.0)
        roughness_ramp.color_ramp.elements[1].position = 1.0
        roughness_ramp.color_ramp.elements[1].color = (0.2, 0.2, 0.2, 1.0)
        set_specular_value(principled_node, 0.8)
    
    links.new(noise_tex.outputs['Fac'], roughness_ramp.inputs['Fac'])
    links.new(roughness_ramp.outputs['Color'], roughness_math.inputs[0])
    links.new(roughness_math.outputs['Value'], principled_node.inputs['Roughness'])
    material.cycles.displacement_method = 'BUMP'
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.active_material == material:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(60)
    print(f"Created enhanced procedural {selected_type} material with bump mapping")
    return selected_type


def apply_random_texture(material, texture_folder):
    """
    Apply a random texture from the specified folder to the material
    
    Args:
        material: The material to apply the texture to
        texture_folder: Folder containing texture files
        
    Returns:
        tuple: (success, texture_path)
            success: True if texture was successfully applied, False otherwise
            texture_path: Path to the texture file if successful, None otherwise
    """
    BATCH_main_manager.CURRENT_TEXTURE_NAME = None
    texture_path = None
    
    if not os.path.exists(texture_folder):
        print(f"WARNING: Texture folder not found: {texture_folder}")
        print("Falling back to procedural material")
        create_procedural_fantasy_metal(material)
        return False, None
        
    print(f"Searching for textures in folder: {texture_folder}")
    image_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
    image_files = []
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
        return False, None
        
    random.shuffle(image_files)
    print("Shuffled texture files for random selection")
    print(f"First few textures to try: {', '.join(image_files[:min(3, len(image_files))])}")
    
    success = False
    tried_images = []
    
    for image_file in image_files:
        image_path = os.path.join(texture_folder, image_file)
        print(f"Attempting to load texture: {image_file}")
        print(f"Full texture path: {image_path}")
        
        if image_path in tried_images:
            print(f"Skipping already tried texture: {image_file}")
            continue
            
        tried_images.append(image_path)
        
        try:
            if not os.path.exists(image_path):
                print(f"ERROR: Texture file does not exist: {image_path}")
                texture_dir = os.path.dirname(image_path)
                if os.path.exists(texture_dir):
                    print(f"Texture directory exists: {texture_dir}")
                    print("Files in the directory:")
                    for file in os.listdir(texture_dir):
                        print(f"  - {file}")
                else:
                    print(f"Texture directory does not exist: {texture_dir}")
                continue
                
            if not os.access(image_path, os.R_OK):
                print(f"ERROR: Texture file is not readable: {image_path}")
                try:
                    file_stat = os.stat(image_path)
                    print(f"File permissions: {oct(file_stat.st_mode)}")
                except Exception as perm_error:
                    print(f"Error checking file permissions: {perm_error}")
                continue
                
            print(f"Preparing material node tree for texture: {image_file}")
            BATCH_main_manager.CURRENT_TEXTURE_NAME = os.path.splitext(image_file)[0]
            print(f"Setting current texture name to: {BATCH_main_manager.CURRENT_TEXTURE_NAME}")
            
            success = apply_enhanced_material_with_texture(material, image_path)
            
            if success:
                print(f"Successfully applied enhanced material with texture: {image_file}")
                texture_path = image_path
                break
                
        except Exception as e:
            print(f"ERROR: Failed to apply texture {image_file}: {str(e)}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Stack trace: {traceback.format_exc()}")
            continue
            
    if not success:
        print("WARNING: All textures failed to load. Falling back to procedural material")
        material_type = create_procedural_fantasy_metal(material)
        BATCH_main_manager.CURRENT_MATERIAL_TYPE = material_type
        print(f"Created fallback {material_type} material")
        return False, None
        
    return success, texture_path


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
        material.node_tree.nodes.clear()
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (1200, 0)
        principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        principled_node.location = (900, 0)
        principled_node.inputs['Metallic'].default_value = 1.0
        principled_node.inputs['Roughness'].default_value = 0.3
        set_specular_value(principled_node, 0.5)
        links.new(principled_node.outputs[0], output_node.inputs[0])
        base_color_node = nodes.new(type='ShaderNodeTexImage')
        base_color_node.location = (300, 200)
        base_color_image = bpy.data.images.load(texture_path)
        base_color_node.image = base_color_image
        base_color_node.name = "Base_Color_Texture"
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-800, 0)
        mapping = nodes.new(type='ShaderNodeMapping')
        mapping.location = (-600, 0)
        mapping.inputs['Scale'].default_value = (2.0, 2.0, 2.0)
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], base_color_node.inputs['Vector'])
        color_adjust = nodes.new(type='ShaderNodeBrightContrast')
        color_adjust.location = (500, 200)
        color_adjust.inputs['Contrast'].default_value = random.uniform(0.02, 0.05)
        color_adjust.inputs['Bright'].default_value = random.uniform(-0.05, 0.05)
        mix_rgb = nodes.new(type='ShaderNodeMixRGB')
        mix_rgb.location = (700, 200)
        mix_rgb.blend_type = 'MULTIPLY'
        mix_rgb.inputs['Fac'].default_value = random.uniform(0.1, 0.2)
        r = random.uniform(0.8, 0.95)
        g = random.uniform(0.8, 0.95)
        b = random.uniform(0.8, 0.95)
        tint_type = random.randint(0, 4)
        if tint_type == 0:
            r *= 1.05; g *= 0.95; b *= 0.9
        elif tint_type == 1:
            r *= 1.05; g *= 1.0; b *= 0.9
        elif tint_type == 2:
            r *= 0.98; g *= 1.0; b *= 1.02
        elif tint_type == 3:
            r *= 0.95; g *= 0.98; b *= 1.05
        mix_rgb.inputs[2].default_value = (r, g, b, 1.0)
        print(f"Applied subtle random tint: RGB({r:.2f}, {g:.2f}, {b:.2f})")
        links.new(base_color_node.outputs['Color'], color_adjust.inputs['Color'])
        links.new(color_adjust.outputs['Color'], mix_rgb.inputs[1])
        links.new(mix_rgb.outputs['Color'], principled_node.inputs['Base Color'])
        print(f"Connected texture {texture_path} to material's Base Color input")
        separate_rgb = nodes.new(type='ShaderNodeSeparateRGB')
        separate_rgb.location = (300, -100)
        links.new(base_color_node.outputs['Color'], separate_rgb.inputs['Image'])
        roughness_math = nodes.new(type='ShaderNodeMath')
        roughness_math.location = (700, -100)
        roughness_math.operation = 'MULTIPLY'
        roughness_math.inputs[0].default_value = 0.3
        roughness_math.inputs[1].default_value = 0.15
        roughness_add = nodes.new(type='ShaderNodeMath')
        roughness_add.location = (500, -100)
        roughness_add.operation = 'ADD'
        roughness_add.inputs[0].default_value = 1.0
        roughness_scale = nodes.new(type='ShaderNodeMath')
        roughness_scale.location = (500, -200)
        roughness_scale.operation = 'MULTIPLY'
        roughness_scale.inputs[1].default_value = 0.1
        links.new(separate_rgb.outputs['G'], roughness_scale.inputs[0])
        links.new(roughness_scale.outputs['Value'], roughness_add.inputs[1])
        links.new(roughness_add.outputs['Value'], roughness_math.inputs[0])
        links.new(roughness_math.outputs['Value'], principled_node.inputs['Roughness'])
        
        # Noise textures for micro detail normal
        noise_tex = nodes.new(type='ShaderNodeTexNoise')
        noise_tex.location = (-300, -300)
        noise_tex.inputs['Scale'].default_value = 50.0
        noise_tex.inputs['Detail'].default_value = 15.0
        noise_tex.inputs['Roughness'].default_value = 0.7
        links.new(mapping.outputs['Vector'], noise_tex.inputs['Vector'])
        
        micro_noise_tex = nodes.new(type='ShaderNodeTexNoise')
        micro_noise_tex.location = (-300, -450)
        micro_noise_tex.inputs['Scale'].default_value = 200.0
        micro_noise_tex.inputs['Detail'].default_value = 16.0
        micro_noise_tex.inputs['Roughness'].default_value = 0.9
        micro_noise_tex.inputs['Distortion'].default_value = 0.4
        mapping_scale = nodes.new(type='ShaderNodeMapping')
        mapping_scale.location = (-500, -450)
        mapping_scale.inputs['Scale'].default_value = (5.0, 5.0, 5.0)
        links.new(mapping.outputs['Vector'], mapping_scale.inputs['Vector'])
        links.new(mapping_scale.outputs['Vector'], micro_noise_tex.inputs['Vector'])
        
        micro_ramp = nodes.new(type='ShaderNodeValToRGB')
        micro_ramp.location = (-100, -450)
        micro_ramp.color_ramp.elements[0].position = 0.47
        micro_ramp.color_ramp.elements[0].color = (0.47, 0.47, 0.47, 1.0)
        micro_ramp.color_ramp.elements[1].position = 0.53
        micro_ramp.color_ramp.elements[1].color = (0.53, 0.53, 0.53, 1.0)
        links.new(micro_noise_tex.outputs['Fac'], micro_ramp.inputs['Fac'])
        
        noise_ramp = nodes.new(type='ShaderNodeValToRGB')
        noise_ramp.location = (-100, -300)
        noise_ramp.color_ramp.elements[0].position = 0.45
        noise_ramp.color_ramp.elements[0].color = (0.45, 0.45, 0.45, 1.0)
        noise_ramp.color_ramp.elements[1].position = 0.55
        noise_ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1.0)
        links.new(noise_tex.outputs['Fac'], noise_ramp.inputs['Fac'])
        
        noise_detail_mix = nodes.new(type='ShaderNodeMixRGB')
        noise_detail_mix.location = (50, -370)
        noise_detail_mix.blend_type = 'ADD'
        noise_detail_mix.inputs['Fac'].default_value = 0.3
        links.new(noise_ramp.outputs['Color'], noise_detail_mix.inputs[1])
        links.new(micro_ramp.outputs['Color'], noise_detail_mix.inputs[2])
        
        # Create bump node with direct connection to noise textures
        bump_node = nodes.new(type='ShaderNodeBump')
        bump_node.location = (600, -300)
        bump_node.inputs['Strength'].default_value = 0.2  # Set strength to 0.2 as requested
        bump_node.inputs['Distance'].default_value = 0.01
        
        # Connect noise directly to bump height input instead of multiplying with color texture
        links.new(noise_detail_mix.outputs['Color'], bump_node.inputs['Height'])
        links.new(bump_node.outputs['Normal'], principled_node.inputs['Normal'])
        
        displacement_node = nodes.new(type='ShaderNodeDisplacement')
        displacement_node.location = (900, -300)
        displacement_node.inputs['Scale'].default_value = 0.005
        displacement_node.inputs['Midlevel'].default_value = 0.0
        disp_math = nodes.new(type='ShaderNodeMath')
        disp_math.location = (700, -400)
        disp_math.operation = 'MULTIPLY'
        disp_math.inputs[1].default_value = 0.01
        links.new(separate_rgb.outputs['R'], disp_math.inputs[0])
        links.new(disp_math.outputs['Value'], displacement_node.inputs['Height'])
        links.new(displacement_node.outputs['Displacement'], output_node.inputs['Displacement'])
        material.cycles.displacement_method = 'BOTH'
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
        print(f"Stack trace: {traceback.format_exc()}")
        return False


def apply_random_material(target_obj=None):
    """
    Apply a random material to the specified object or active object.
    This function handles both procedural and texture-based materials.
    
    Args:
        target_obj: The object to apply the material to. If None, will try to find a Metal_Ingot object.
    
    Returns:
        tuple: (material_type, material_name, texture_name)
            material_type: Type of material (procedural or texture)
            material_name: Name of the material or procedural type
            texture_name: Name of the texture if used, None otherwise
    """
    print("\n--- APPLY RANDOM MATERIAL DEBUG ---")
    
    obj = target_obj
    
    # If no target object was provided, find the metal ingot object specifically
    if obj is None:
        for o in bpy.context.scene.objects:
            if o.type == 'MESH' and 'Metal_Ingot' in o.name:
                obj = o
                bpy.context.view_layer.objects.active = obj
                print(f"Found metal ingot object: {obj.name}")
                break
                
    if not obj:
        print("No metal ingot object found. Looking for any mesh object...")
        for o in bpy.context.scene.objects:
            if o.type == 'MESH' and not o.hide_viewport and not o.hide_render:
                obj = o
                bpy.context.view_layer.objects.active = obj
                print(f"Selected mesh object: {obj.name}")
                break
    
    if not obj or obj.type != 'MESH':
        print("ERROR: No suitable mesh object found to apply material to")
        return "unknown", "unknown", None
    
    print(f"Applying material to mesh object: {obj.name}")
    
    # Create base material
    material = create_metal_material(obj)
    material_type = "procedural"
    material_name = "unknown"
    texture_name = None
    
    # Decide between texture-based or procedural material
    if (BATCH_main_manager.TEXTURE_FOLDER and 
        os.path.exists(BATCH_main_manager.TEXTURE_FOLDER) and 
        random.random() < 0.7):
        
        print("Choosing texture-based material")
        texture_success, texture_path = apply_random_texture(material, BATCH_main_manager.TEXTURE_FOLDER)
        
        if texture_success and texture_path:
            material_type = "texture"
            # Extract texture name from path
            texture_name = os.path.splitext(os.path.basename(texture_path))[0]
            material_name = f"tex_{texture_name}"
            print(f"Applied texture-based material with texture: {texture_name}")
            
            # Store texture name in global variable
            BATCH_main_manager.CURRENT_TEXTURE_NAME = texture_name
        else:
            print("Texture application failed, falling back to procedural material")
            material_type = "procedural"
            material_name = create_procedural_fantasy_metal(material)
            print(f"Created fallback procedural material: {material_name}")
    else:
        print("Choosing procedural material")
        material_name = create_procedural_fantasy_metal(material)
        material_type = "procedural"
        print(f"Created procedural material: {material_name}")
    
    # Store material info in global variables
    BATCH_main_manager.CURRENT_MATERIAL_TYPE = material_type
    BATCH_main_manager.CURRENT_MATERIAL_NAME = material_name
    
    print(f"Final material info - Type: {material_type}, Name: {material_name}, Texture: {texture_name}")
    print("--- END APPLY RANDOM MATERIAL DEBUG ---\n")
    
    return material_type, material_name, texture_name
