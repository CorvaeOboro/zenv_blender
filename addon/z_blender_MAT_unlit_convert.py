bl_info = {
    "name": 'MAT Unlit Convert',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Convert materials to unlit',
    "status": 'working',
    "approved": True,
    "sort_priority": '70',
    "group": 'Material',
    "group_prefix": 'MAT',
    "description_short": 'convert all materials to emission for unlit render',
    "description_long": """
MAT Unlit Convert 
Convert materials to unlit by removing all nodes except basecolor and opacity textures and
connecting them directly to the emission material output.
""",
    "location": 'View3D > ZENV',
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_UnlitConvert_Properties(PropertyGroup):
    """Properties for unlit material conversion."""
    preserve_alpha: BoolProperty(
        name="Preserve Alpha",
        description="Keep alpha/transparency connections",
        default=False
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_UnlitConvert(Operator):
    """Convert materials to unlit by connecting textures directly to output."""
    bl_idname = "zenv.unlit_convert"
    bl_label = "Convert to Unlit"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the material conversion."""
        try:
            props = context.scene.zenv_unlit_props
            converted_count = 0
            
            # Process all materials
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                
                # Store texture nodes and their connections
                texture_nodes = []
                alpha_connections = []
                
                # Find texture nodes connected to Base Color
                for node in nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        if node.inputs['Base Color'].is_linked:
                            from_node = node.inputs['Base Color'].links[0].from_node
                            if from_node.type == 'TEX_IMAGE':
                                texture_nodes.append(from_node)
                                # Store alpha connections if needed
                                if props.preserve_alpha and node.inputs['Alpha'].is_linked:
                                    alpha_node = node.inputs['Alpha'].links[0].from_node
                                    if alpha_node.type == 'TEX_IMAGE':
                                        alpha_connections.append(
                                            (alpha_node, node, node.inputs['Alpha'])
                                        )
                
                if not texture_nodes:
                    continue
                
                # Clear all nodes
                nodes.clear()
                
                # Create new nodes
                output = nodes.new('ShaderNodeOutputMaterial')
                emission = nodes.new('ShaderNodeEmission')
                output.location = (300, 0)
                emission.location = (0, 0)
                
                # Add back texture nodes
                for i, tex_node in enumerate(texture_nodes):
                    if not tex_node.image:
                        continue
                        
                    new_tex = nodes.new('ShaderNodeTexImage')
                    new_tex.image = tex_node.image
                    new_tex.location = (-300, i * -300)
                    
                    # Copy texture node settings with valid enum values
                    if hasattr(tex_node, 'interpolation') and tex_node.interpolation in {'Linear', 'Closest', 'Cubic', 'Smart'}:
                        new_tex.interpolation = tex_node.interpolation
                    if hasattr(tex_node, 'projection') and tex_node.projection in {'FLAT', 'BOX', 'SPHERE', 'TUBE'}:
                        new_tex.projection = tex_node.projection
                    if hasattr(tex_node, 'extension') and tex_node.extension in {'REPEAT', 'EXTEND', 'CLIP'}:
                        new_tex.extension = tex_node.extension
                    
                    # Connect color to emission
                    links.new(new_tex.outputs['Color'], emission.inputs['Color'])
                    
                    # Restore alpha connections if needed
                    if props.preserve_alpha:
                        for old_node, to_node, to_socket in alpha_connections:
                            if old_node == tex_node:
                                # Recreate alpha connection
                                if to_node.name in nodes:
                                    new_to_node = nodes[to_node.name]
                                    if to_socket.name in new_to_node.inputs:
                                        links.new(
                                            new_tex.outputs['Alpha'],
                                            new_to_node.inputs[to_socket.name]
                                        )
                
                # Connect emission to output
                links.new(emission.outputs['Emission'], output.inputs['Surface'])
                converted_count += 1
            
            self.report(
                {'INFO'}, 
                f"Converted {converted_count} materials to unlit"
            )
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error converting materials: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_UnlitConvertPanel(Panel):
    """Panel for unlit material conversion."""
    bl_label = "MAT Convert to Unlit"
    bl_idname = "ZENV_PT_unlit_convert"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_unlit_props
        
        box = layout.box()
        box.label(text="Settings:", icon='MATERIAL')
        box.prop(props, "preserve_alpha")
        
        box = layout.box()
        box.label(text="Convert:", icon='SHADERFX')
        box.operator(ZENV_OT_UnlitConvert.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_UnlitConvert_Properties,
    ZENV_OT_UnlitConvert,
    ZENV_PT_UnlitConvertPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_unlit_props = PointerProperty(
        type=ZENV_PG_UnlitConvert_Properties
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_unlit_props

if __name__ == "__main__":
    register()