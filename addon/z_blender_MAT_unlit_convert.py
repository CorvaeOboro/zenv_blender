#region META
bl_info = {
    "name": 'MAT Unlit Convert',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Convert materials to unlit',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 70,
    "tags": ['material', 'unlit', 'emission', 'convert', 'shader', 'nodes'],
    "description_short": 'convert all materials to emission for unlit render',
    "description_medium": 'Converts all materials in the blend file to unlit (emission-only) by removing all nodes except base color and opacity textures and connecting them directly to the emission material output. Useful for game asset pipelines where unlit rendering is needed. Optionally preserves alpha transparency.',
    "description_long": """
MAT Unlit Convert
Convert materials to unlit by removing all nodes except basecolor and opacity textures and
connecting them directly to the emission material output.
""",
    "image_overview": 'zenv_blender_MAT_unlit_convert.png',
    "addon_image": 'zenv_blender_MAT_unlit_convert.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import logging
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, PointerProperty

logger = logging.getLogger(__name__)
_zenv_unlit_console_handler = None
#endregion

#region PROPS
# Property group for unlit conversion settings, registered on the Scene.

class ZENV_PG_UnlitConvert_Properties(PropertyGroup):
    """Properties for unlit material conversion."""
    preserve_alpha: BoolProperty(
        name="Preserve Alpha",
        description="Keep alpha/transparency connections",
        default=False
    )
#endregion

#region OP
# Operator that converts all materials to unlit (emission-only).

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
            logger.info("Starting unlit conversion (preserve_alpha=%s)",
                        props.preserve_alpha)

            # Process all materials
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue

                nodes = mat.node_tree.nodes
                links = mat.node_tree.links

                # Store image references and settings BEFORE clearing nodes.
                # This avoids relying on destroyed node objects remaining
                # accessible in Python.
                color_image = None
                color_settings = {}
                alpha_image = None
                alpha_settings = {}

                # Find the first BSDF_PRINCIPLED node with a texture
                # connected to Base Color.
                for node in nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        if node.inputs['Base Color'].is_linked:
                            from_node = node.inputs['Base Color'].links[0].from_node
                            if from_node.type == 'TEX_IMAGE' and from_node.image:
                                color_image = from_node.image
                                color_settings = {
                                    'interpolation': getattr(from_node, 'interpolation', 'Linear'),
                                    'projection': getattr(from_node, 'projection', 'FLAT'),
                                    'extension': getattr(from_node, 'extension', 'REPEAT'),
                                }
                                # Store alpha texture if preserve_alpha is enabled
                                if props.preserve_alpha and node.inputs['Alpha'].is_linked:
                                    alpha_node = node.inputs['Alpha'].links[0].from_node
                                    if alpha_node.type == 'TEX_IMAGE' and alpha_node.image:
                                        alpha_image = alpha_node.image
                                        alpha_settings = {
                                            'interpolation': getattr(alpha_node, 'interpolation', 'Linear'),
                                            'projection': getattr(alpha_node, 'projection', 'FLAT'),
                                            'extension': getattr(alpha_node, 'extension', 'REPEAT'),
                                        }
                                break  # Only process the first BSDF with a texture

                if color_image is None:
                    continue

                # Clear all nodes - safe now that we stored image references
                nodes.clear()

                # Create new nodes
                output = nodes.new('ShaderNodeOutputMaterial')
                emission = nodes.new('ShaderNodeEmission')
                output.location = (300, 0)
                emission.location = (0, 0)

                # Create color texture node
                new_tex = nodes.new('ShaderNodeTexImage')
                new_tex.image = color_image
                new_tex.location = (-300, 0)

                # Copy texture node settings with valid enum values
                if color_settings.get('interpolation') in {'Linear', 'Closest', 'Cubic', 'Smart'}:
                    new_tex.interpolation = color_settings['interpolation']
                if color_settings.get('projection') in {'FLAT', 'BOX', 'SPHERE', 'TUBE'}:
                    new_tex.projection = color_settings['projection']
                if color_settings.get('extension') in {'REPEAT', 'EXTEND', 'CLIP'}:
                    new_tex.extension = color_settings['extension']

                # Connect color to emission
                links.new(new_tex.outputs['Color'], emission.inputs['Color'])

                # Restore alpha transparency if needed
                if alpha_image is not None:
                    alpha_tex = nodes.new('ShaderNodeTexImage')
                    alpha_tex.image = alpha_image
                    alpha_tex.location = (-300, -300)

                    if alpha_settings.get('interpolation') in {'Linear', 'Closest', 'Cubic', 'Smart'}:
                        alpha_tex.interpolation = alpha_settings['interpolation']
                    if alpha_settings.get('projection') in {'FLAT', 'BOX', 'SPHERE', 'TUBE'}:
                        alpha_tex.projection = alpha_settings['projection']
                    if alpha_settings.get('extension') in {'REPEAT', 'EXTEND', 'CLIP'}:
                        alpha_tex.extension = alpha_settings['extension']

                    # Connect alpha to emission strength so transparent
                    # areas emit no light.
                    links.new(alpha_tex.outputs['Alpha'], emission.inputs['Strength'])

                # Connect emission to output
                links.new(emission.outputs['Emission'], output.inputs['Surface'])
                converted_count += 1
                logger.info("Converted material '%s' to unlit", mat.name)

            self.report(
                {'INFO'},
                f"Converted {converted_count} materials to unlit"
            )
            logger.info("Converted %d materials to unlit", converted_count)
            return {'FINISHED'}

        except Exception as e:
            logger.error("Error converting materials: %s", str(e))
            self.report({'ERROR'}, f"Error converting materials: {str(e)}")
            return {'CANCELLED'}
#endregion

#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_UnlitConvert(Panel):
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
        box.prop(props, "preserve_alpha")
        box.operator(ZENV_OT_UnlitConvert.bl_idname)
#endregion

#region REG
classes = (
    ZENV_PG_UnlitConvert_Properties,
    ZENV_OT_UnlitConvert,
    ZENV_PT_UnlitConvert,
)

def register():
    """Register the addon classes."""
    global _zenv_unlit_console_handler
    if _zenv_unlit_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_unlit_console_handler = handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_unlit_props = PointerProperty(
        type=ZENV_PG_UnlitConvert_Properties
    )

def unregister():
    """Unregister the addon classes."""
    global _zenv_unlit_console_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if hasattr(bpy.types.Scene, "zenv_unlit_props"):
        del bpy.types.Scene.zenv_unlit_props
    if _zenv_unlit_console_handler is not None:
        try:
            logger.removeHandler(_zenv_unlit_console_handler)
        except ValueError:
            pass
        _zenv_unlit_console_handler = None

if __name__ == "__main__":
    register()
#endregion