"""
MAT Set Textures by Material Name 
- A Blender addon for fixing texture paths in materials.
Recreates material nodes with correct texture paths based on material names.
"""

bl_info = {
    "name": "MAT Set Textures by Material Name",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Set textures to materials based on material names",
    "category": "ZENV",
}

import bpy
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_SetTextureByMaterialName_Properties(PropertyGroup):
    """Properties for setting textures by material name."""
    
    texture_dir: StringProperty(
        name="Texture Folder",
        description="Directory containing texture files",
        default="",
        subtype='DIR_PATH'
    )
    
    material_suffix: StringProperty(
        name="Suffix of Material",
        description="Suffix to remove from material names _MI",
        default="_MI"
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_SetTextureByMaterialName(Operator):
    """Set textures to materials based on material names."""
    bl_idname = "zenv.set_textures_by_material_name"
    bl_label = "Set Textures by Material Name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the texture set operation."""
        try:
            props = context.scene.zenv_set_textures_props
            texture_dir = os.path.normpath(props.texture_dir)
            suffix = props.material_suffix
            
            if not texture_dir or not os.path.exists(texture_dir):
                self.report({'ERROR'}, f"Texture directory does not exist: {texture_dir}")
                return {'CANCELLED'}

            processed_count = 0
            skipped_count = 0
            
            for material in bpy.data.materials:
                if not material.use_nodes:
                    continue
                    
                material_name = material.name.strip()
                if not material_name:
                    self.report({'WARNING'}, "Skipping material with empty name")
                    skipped_count += 1
                    continue
                    
                if suffix and suffix in material_name:
                    material_name = material_name.replace(suffix, '')

                # Process the material
                if self.process_material(material, material_name, texture_dir):
                    processed_count += 1
                else:
                    skipped_count += 1

            if processed_count > 0:
                msg = f"Processed {processed_count} materials"
                if skipped_count > 0:
                    msg += f", skipped {skipped_count}"
                self.report({'INFO'}, msg)
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, f"No materials were processed, {skipped_count} skipped")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            return {'CANCELLED'}

    def process_material(self, material, material_name, texture_dir):
        """Process a single material and set up its textures.
        
        Args:
            material: The material to process
            material_name: Base name of the material (without suffix)
            texture_dir: Directory containing texture files
            
        Returns:
            bool: True if material was processed successfully
        """
        # Define texture type mappings
        TEXTURE_TYPES = {
            'color': ['color', 'albedo', 'diffuse', 'basecolor'],
            'normal': ['normal', 'nrm', 'norm'],
            'roughness': ['rough', 'roughness', 'rgh'],
            'metallic': ['metal', 'metallic', 'metalness'],
            'height': ['height', 'displacement', 'disp'],
            'ao': ['ao', 'ambient', 'occlusion']
        }
        
        # Get list of texture files
        try:
            texture_files = [f for f in os.listdir(texture_dir) 
                           if os.path.isfile(os.path.join(texture_dir, f)) and 
                           any(f.lower().endswith(ext) for ext in 
                               ('.png', '.jpg', '.jpeg', '.tga', '.bmp', '.exr'))]
        except (PermissionError, FileNotFoundError) as e:
            self.report({'ERROR'}, f"Cannot access texture directory: {str(e)}")
            return False
        
        # Find matching textures
        matching_textures = {}
        for tex_file in texture_files:
            tex_base = os.path.splitext(tex_file)[0].lower()
            
            # Check for exact match or prefixed match
            if tex_base == material_name.lower() or tex_base.startswith(material_name.lower() + '_'):
                # Determine texture type
                tex_type = None
                for type_name, keywords in TEXTURE_TYPES.items():
                    if any(keyword in tex_base for keyword in keywords):
                        tex_type = type_name
                        break
                
                if tex_type:
                    matching_textures[tex_type] = tex_file
                elif len(matching_textures) == 0:  # If no type detected and no textures yet, assume color
                    matching_textures['color'] = tex_file
        
        if not matching_textures:
            return False
        
        # Clear and recreate nodes
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        
        # Create main nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output.location = (300, 0)
        principled.location = (0, 0)
        
        # Link main nodes
        links.new(principled.outputs[0], output.inputs[0])
        
        # Process each texture type
        for i, (tex_type, tex_file) in enumerate(matching_textures.items()):
            try:
                # Create texture node
                tex = nodes.new('ShaderNodeTexImage')
                img_path = os.path.join(texture_dir, tex_file)
                img = bpy.data.images.load(img_path, check_existing=True)
                tex.image = img
                tex.location = (-300, i * -300)
                
                # Connect based on texture type
                if tex_type == 'color':
                    links.new(tex.outputs['Color'], principled.inputs['Base Color'])
                elif tex_type == 'normal':
                    normal_map = nodes.new('ShaderNodeNormalMap')
                    normal_map.location = (-150, i * -300)
                    links.new(tex.outputs['Color'], normal_map.inputs['Color'])
                    links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                elif tex_type == 'roughness':
                    links.new(tex.outputs['Color'], principled.inputs['Roughness'])
                elif tex_type == 'metallic':
                    links.new(tex.outputs['Color'], principled.inputs['Metallic'])
                elif tex_type == 'height':
                    # Add displacement setup
                    disp = nodes.new('ShaderNodeDisplacement')
                    disp.location = (0, -300)
                    links.new(tex.outputs['Color'], disp.inputs['Height'])
                    links.new(disp.outputs['Displacement'], output.inputs['Displacement'])
                elif tex_type == 'ao':
                    # Create mix RGB node for AO
                    mix = nodes.new('ShaderNodeMixRGB')
                    mix.blend_type = 'MULTIPLY'
                    mix.inputs[0].default_value = 1.0
                    mix.location = (-150, i * -300)
                    # Connect if base color exists
                    if 'Base Color' in principled.inputs and principled.inputs['Base Color'].links:
                        base_color = principled.inputs['Base Color'].links[0].from_socket
                        links.new(base_color, mix.inputs[1])
                        links.new(tex.outputs['Color'], mix.inputs[2])
                        links.new(mix.outputs['Color'], principled.inputs['Base Color'])
            
            except Exception as e:
                self.report({'WARNING'}, f"Failed to process texture {tex_file}: {str(e)}")
                continue
        
        return True

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_SetTextureByMaterialNamePanel(Panel):
    """Panel for fixing texture paths."""
    bl_label = "MAT Set Textures by Material Name"
    bl_idname = "ZENV_PT_set_textures_by_material_name"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_set_textures_props
        
        box = layout.box()

        box.prop(props, "texture_dir")
        box.prop(props, "material_suffix")

        box.operator(ZENV_OT_SetTextureByMaterialName.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_SetTextureByMaterialName_Properties,
    ZENV_OT_SetTextureByMaterialName,
    ZENV_PT_SetTextureByMaterialNamePanel,
)

def register():
    """Register the addon classes and properties."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_set_textures_props = PointerProperty(
        type=ZENV_PG_SetTextureByMaterialName_Properties
    )

def unregister():
    """Unregister the addon classes and properties."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_set_textures_props

if __name__ == "__main__":
    register()
