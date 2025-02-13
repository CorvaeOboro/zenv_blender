# MATERIAL REMOVE OPACITY ALL
# for each material in the scene remove all opacity nodes

bl_info = {
    "name": "MAT Remove Opacity",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV",
    "description": "Remove opacity from all materials",
    "category": "ZENV",
}

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator, Panel

class ZENV_OT_MATRemoveOpacity(Operator):
    """Remove opacity from materials"""
    bl_idname = "zenv.mat_remove_opacity"
    bl_label = "Remove Opacity"
    bl_options = {'REGISTER', 'UNDO'}

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

    def _remove_opacity_from_material(self, material):
        """Remove opacity from a single material"""
        if not material or not material.use_nodes:
            return False

        modified = False
        # Get the material output node
        output_node = None
        for node in material.node_tree.nodes:
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
                    material.node_tree.links.remove(alpha_input.links[0])
                    modified = True

            # Handle Transmission
            transmission_input = connected_node.inputs.get('Transmission')
            if transmission_input:
                if transmission_input.default_value > 0.0:
                    transmission_input.default_value = 0.0
                    modified = True
                if transmission_input.links:
                    material.node_tree.links.remove(transmission_input.links[0])
                    modified = True

        elif connected_node.type == 'MIX_SHADER':
            # Set mix factor to 1.0 to use only the second shader
            fac_input = connected_node.inputs.get('Fac')
            if fac_input:
                if fac_input.default_value != 1.0:
                    fac_input.default_value = 1.0
                    modified = True
                # Remove any links to the factor input
                if fac_input.links:
                    material.node_tree.links.remove(fac_input.links[0])
                    modified = True

        # Set material blend mode to opaque
        if material.blend_method != 'OPAQUE':
            material.blend_method = 'OPAQUE'
            modified = True

        return modified

    def execute(self, context):
        modified_count = 0
        skipped_count = 0

        if self.apply_to_all:
            # Process all materials
            for material in bpy.data.materials:
                if self._remove_opacity_from_material(material):
                    modified_count += 1
                else:
                    skipped_count += 1
        else:
            # Process single material
            material = bpy.data.materials.get(self.material_name)
            if material:
                if self._remove_opacity_from_material(material):
                    modified_count += 1
                else:
                    skipped_count += 1
            else:
                self.report({'WARNING'}, f"Material '{self.material_name}' not found")
                return {'CANCELLED'}

        # Report results
        if modified_count > 0:
            self.report({'INFO'}, f"Modified {modified_count} material{'s' if modified_count > 1 else ''}")
        if skipped_count > 0:
            self.report({'INFO'}, f"Skipped {skipped_count} material{'s' if skipped_count > 1 else ''}")

        return {'FINISHED'}

class ZENV_PT_MATRemoveOpacity_Panel(Panel):
    """Panel for opacity removal settings"""
    bl_label = "MAT Remove Opacity"
    bl_idname = "ZENV_PT_MATRemoveOpacity_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # Add operator properties to the panel
        op_props = layout.operator("zenv.mat_remove_opacity")
        layout.prop(op_props, "apply_to_all")
        
        # Only show material name field if not applying to all
        if not op_props.apply_to_all:
            layout.prop_search(op_props, "material_name", bpy.data, "materials")

def register():
    bpy.utils.register_class(ZENV_OT_MATRemoveOpacity)
    bpy.utils.register_class(ZENV_PT_MATRemoveOpacity_Panel)

def unregister():
    bpy.utils.unregister_class(ZENV_PT_MATRemoveOpacity_Panel)
    bpy.utils.unregister_class(ZENV_OT_MATRemoveOpacity)

if __name__ == "__main__":
    register()
