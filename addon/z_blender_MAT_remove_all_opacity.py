#region META
bl_info = {
    "name": 'MAT Remove Opacity',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Remove opacity from all materials',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 50,
    "tags": ['material', 'opacity', 'alpha', 'remove', 'cleanup', 'opaque'],
    "description_short": 'remove all opacity textures in materials',
    "description_medium": 'Scans materials (all or a single named material), finds the shader connected to the Material Output Surface input, and removes opacity-related settings: resets Principled BSDF Alpha to 1.0 and Transmission Weight to 0.0 (removing texture links), bypasses Mix Shader opacity by relinking the opaque shader directly to the output, and sets blend_method to OPAQUE.',
    "description_long": """
MATERIAL REMOVE OPACITY ALL
 for each material in the scene remove all opacity nodes
""",
    "image_overview": 'zenv_blender_MAT_remove_all_opacity.png',
    "addon_image": 'zenv_blender_MAT_remove_all_opacity.png',
    "location": 'View3D > Sidebar > ZENV',
}
#endregion

#region IMPORT
import bpy
from bpy.props import BoolProperty, StringProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup
#endregion


#region PROPS
# Property group for opacity removal settings, registered on the Scene.

class ZENV_PG_RemoveOpacity_Properties(PropertyGroup):
    """Properties for opacity removal, registered on the Scene."""

    apply_to_all: BoolProperty(
        name="Apply to All Materials",
        description="Apply to all materials in the file",
        default=True
    )

    material_name: StringProperty(
        name="Material Name",
        description="Name of material to remove opacity from",
        default=""
    )
#endregion


#region OP
# Operator that removes opacity from materials.

class ZENV_OT_MATRemoveOpacity(Operator):
    """Remove opacity from materials"""
    bl_idname = "zenv.mat_remove_opacity"
    bl_label = "Remove Opacity"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def remove_opacity_from_material(cls, material):
        """Remove opacity from a single material.

        Returns True if the material was modified, False otherwise.
        """
        if not material or not material.use_nodes:
            return False

        modified = False
        node_tree = material.node_tree
        links = node_tree.links

        # Get the material output node
        output_node = None
        for node in node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break

        if not output_node:
            return False

        # Get the connected node to the surface input
        surface_input = output_node.inputs.get('Surface')
        if not surface_input or not surface_input.links:
            return False

        connected_node = surface_input.links[0].from_node

        # Handle different shader types
        if connected_node.type == 'BSDF_PRINCIPLED':
            # Handle Alpha
            alpha_input = connected_node.inputs.get('Alpha')
            if alpha_input:
                if alpha_input.default_value < 1.0:
                    alpha_input.default_value = 1.0
                    modified = True
                # Remove alpha texture links if present
                if alpha_input.links:
                    links.remove(alpha_input.links[0])
                    modified = True

            # Handle Transmission Weight (Blender 4.x API name).
            # Fall back to the legacy 'Transmission' name for older
            # Blender versions.
            transmission_input = connected_node.inputs.get('Transmission Weight')
            if transmission_input is None:
                transmission_input = connected_node.inputs.get('Transmission')
            if transmission_input:
                if transmission_input.default_value > 0.0:
                    transmission_input.default_value = 0.0
                    modified = True
                if transmission_input.links:
                    links.remove(transmission_input.links[0])
                    modified = True

        elif connected_node.type == 'MIX_SHADER':
            # Bypass the mix shader by relinking the first non-transparent
            # shader directly to the output. This is safer than blindly
            # setting Fac=1.0, which assumes the second shader is opaque.
            # Inspect both shader inputs to find the opaque one.
            shader1_input = connected_node.inputs.get('Shader')
            shader2_input = connected_node.inputs.get('Shader_001')
            opaque_shader = None

            for shader_input in (shader1_input, shader2_input):
                if shader_input is None or not shader_input.links:
                    continue
                candidate = shader_input.links[0].from_node
                # Prefer a Principled BSDF with Alpha >= 1.0 and no
                # transmission, or any non-transparent shader.
                if candidate.type == 'BSDF_PRINCIPLED':
                    alpha = candidate.inputs.get('Alpha')
                    transmission = candidate.inputs.get('Transmission Weight')
                    if transmission is None:
                        transmission = candidate.inputs.get('Transmission')
                    alpha_ok = alpha is None or alpha.default_value >= 1.0
                    trans_ok = transmission is None or transmission.default_value <= 0.0
                    if alpha_ok and trans_ok:
                        opaque_shader = candidate
                        break
                elif candidate.type not in ('BSDF_VELVET', 'BSDF_TRANSPARENT',
                                            'BSDF_GLASS', 'BSDF_REFRACTION'):
                    # Assume non-transparent BSDF types are opaque
                    opaque_shader = candidate
                    break

            if opaque_shader is not None and opaque_shader != connected_node:
                # Relink the opaque shader directly to the output
                links.new(opaque_shader.outputs[0], surface_input)
                modified = True
            else:
                # Fallback: set mix factor to 1.0 (use second shader)
                fac_input = connected_node.inputs.get('Fac')
                if fac_input:
                    if fac_input.default_value != 1.0:
                        fac_input.default_value = 1.0
                        modified = True
                    if fac_input.links:
                        links.remove(fac_input.links[0])
                        modified = True

        # Set material blend mode to opaque. On Blender 5.1+ the
        # 'OPAQUE' blend_method may be coerced to 'HASHED' (a
        # Blender API limitation where setting OPAQUE resets
        # surface_render_method to DITHERED). Only flag modified when
        # the value changes so the return value stays honest.
        if material.blend_method != 'OPAQUE':
            previous = material.blend_method
            material.blend_method = 'OPAQUE'
            if material.blend_method != previous:
                modified = True

        return modified

    def execute(self, context):
        try:
            props = context.scene.zenv_remove_opacity_props
            apply_to_all = props.apply_to_all
            material_name = props.material_name

            modified_count = 0
            skipped_count = 0

            if apply_to_all:
                # Process all materials
                for material in bpy.data.materials:
                    if self.remove_opacity_from_material(material):
                        modified_count += 1
                    else:
                        skipped_count += 1
            else:
                # Process single material
                material = bpy.data.materials.get(material_name)
                if material:
                    if self.remove_opacity_from_material(material):
                        modified_count += 1
                    else:
                        skipped_count += 1
                else:
                    self.report({'WARNING'}, f"Material '{material_name}' not found")
                    return {'CANCELLED'}

            # Report results
            if modified_count > 0:
                self.report({'INFO'}, f"Modified {modified_count} material{'s' if modified_count > 1 else ''}")
            if skipped_count > 0:
                self.report({'INFO'}, f"Skipped {skipped_count} material{'s' if skipped_count > 1 else ''}")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error removing opacity: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_MATRemoveOpacity(Panel):
    """Panel for opacity removal settings"""
    bl_label = "MAT Remove Opacity"
    bl_idname = "ZENV_PT_MATRemoveOpacity"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_remove_opacity_props

        box = layout.box()
        box.prop(props, "apply_to_all")

        # Only show material name field if not applying to all
        if not props.apply_to_all:
            box.prop_search(props, "material_name", bpy.data, "materials")

        box.operator("zenv.mat_remove_opacity")
#endregion


#region REG
classes = (
    ZENV_PG_RemoveOpacity_Properties,
    ZENV_OT_MATRemoveOpacity,
    ZENV_PT_MATRemoveOpacity,
)


def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_remove_opacity_props = PointerProperty(
        type=ZENV_PG_RemoveOpacity_Properties
    )


def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_remove_opacity_props


if __name__ == "__main__":
    register()
#endregion
