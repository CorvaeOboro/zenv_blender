"""
MAT Create From Textures - A Blender addon for creating materials from textures.

Create PBR materials from texture files using common naming conventions.
"""

bl_info = {
    "name": "MAT Create From Textures",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Create materials from texture files",
    "category": "ZENV",
}

import bpy
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_CreateFromTextures_Properties(PropertyGroup):
    """Properties for material creation from textures."""
    
    texture_dir: StringProperty(
        name="Texture Directory",
        description="Directory containing texture files",
        default="",
        subtype='DIR_PATH'
    )
    
    use_pbr: BoolProperty(
        name="Use PBR",
        description="Create PBR materials with normal, roughness, etc.",
        default=True
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_CreateFromTextures(Operator):
    """Create materials from texture files in directory."""
    bl_idname = "zenv.create_from_textures"
    bl_label = "Create Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the material creation."""
        try:
            props = context.scene.zenv_create_textures_props
            texture_dir = props.texture_dir
            
            if not texture_dir or not os.path.exists(texture_dir):
                self.report({'ERROR'}, "Invalid texture directory")
                return {'CANCELLED'}
            
            # Track created materials
            created_count = 0
            
            # Get all files in directory
            files = [f for f in os.listdir(texture_dir) if os.path.isfile(os.path.join(texture_dir, f))]
            
            # Group files by base name (remove _suffix and extension)
            texture_groups = {}
            for file in files:
                base_name = file.split('.')[0]  # Remove extension
                
                # Remove common PBR suffixes
                for suffix in ['_color', '_albedo', '_diffuse', '_normal', '_nrm', 
                             '_roughness', '_rough', '_metallic', '_metal', 
                             '_height', '_displacement', '_disp', '_ao', 
                             '_ambient', '_opacity', '_alpha']:
                    base_name = base_name.replace(suffix, '')
                
                if base_name not in texture_groups:
                    texture_groups[base_name] = []
                texture_groups[base_name].append(file)
            
            # Create materials for each group
            for base_name, texture_files in texture_groups.items():
                # Create new material
                mat = bpy.data.materials.new(name=base_name)
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                
                # Clear default nodes
                nodes.clear()
                
                # Create PBR nodes if enabled
                if props.use_pbr:
                    # Create main nodes
                    output = nodes.new('ShaderNodeOutputMaterial')
                    principled = nodes.new('ShaderNodeBsdfPrincipled')
                    output.location = (300, 0)
                    principled.location = (0, 0)
                    
                    # Link main nodes
                    links.new(principled.outputs[0], output.inputs[0])
                    
                    # Process textures
                    for file in texture_files:
                        # Create image texture node
                        tex = nodes.new('ShaderNodeTexImage')
                        img_path = os.path.join(texture_dir, file)
                        img = bpy.data.images.load(img_path)
                        tex.image = img
                        
                        # Position node
                        tex.location = (-300, len(nodes) * -300)
                        
                        # Connect based on suffix
                        file_lower = file.lower()
                        if any(x in file_lower for x in ['_color', '_albedo', '_diffuse']):
                            links.new(tex.outputs['Color'], principled.inputs['Base Color'])
                        elif any(x in file_lower for x in ['_normal', '_nrm']):
                            normal_map = nodes.new('ShaderNodeNormalMap')
                            normal_map.location = (-150, len(nodes) * -300)
                            links.new(tex.outputs['Color'], normal_map.inputs['Color'])
                            links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                        elif any(x in file_lower for x in ['_roughness', '_rough']):
                            links.new(tex.outputs['Color'], principled.inputs['Roughness'])
                        elif any(x in file_lower for x in ['_metallic', '_metal']):
                            links.new(tex.outputs['Color'], principled.inputs['Metallic'])
                        elif any(x in file_lower for x in ['_height', '_displacement', '_disp']):
                            displacement = nodes.new('ShaderNodeDisplacement')
                            displacement.location = (0, -300)
                            links.new(tex.outputs['Color'], displacement.inputs['Height'])
                            links.new(displacement.outputs['Displacement'], output.inputs['Displacement'])
                        elif any(x in file_lower for x in ['_opacity', '_alpha']):
                            links.new(tex.outputs['Color'], principled.inputs['Alpha'])
                else:
                    # Create simple diffuse setup
                    output = nodes.new('ShaderNodeOutputMaterial')
                    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
                    output.location = (300, 0)
                    diffuse.location = (0, 0)
                    links.new(diffuse.outputs[0], output.inputs[0])
                    
                    # Add first texture as diffuse
                    if texture_files:
                        tex = nodes.new('ShaderNodeTexImage')
                        img_path = os.path.join(texture_dir, texture_files[0])
                        img = bpy.data.images.load(img_path)
                        tex.image = img
                        tex.location = (-300, 0)
                        links.new(tex.outputs['Color'], diffuse.inputs['Color'])
                
                created_count += 1
            
            self.report({'INFO'}, f"Created {created_count} materials")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error creating materials: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_CreateFromTexturesPanel(Panel):
    """Panel for creating materials from textures."""
    bl_label = "MAT Create From Textures"
    bl_idname = "ZENV_PT_create_from_textures"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_create_textures_props
        
        box = layout.box()
        box.label(text="Settings:", icon='TEXTURE')
        box.prop(props, "texture_dir")
        box.prop(props, "use_pbr")
        
        box = layout.box()
        box.label(text="Create:", icon='MATERIAL')
        box.operator(ZENV_OT_CreateFromTextures.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_CreateFromTextures_Properties,
    ZENV_OT_CreateFromTextures,
    ZENV_PT_CreateFromTexturesPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_create_textures_props = PointerProperty(
        type=ZENV_PG_CreateFromTextures_Properties
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_create_textures_props

if __name__ == "__main__":
    register()
