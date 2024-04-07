bl_info = {
    "name": "Emission Material Converter",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Converts all materials to emission-based materials and reverts them back",
}

import bpy
class OBJECT_OT_ConvertToEmission(bpy.types.Operator):
    bl_idname = "object.convert_to_emission"
    bl_label = "Convert to Emission"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        for material in bpy.data.materials:
            self.report({'INFO'},f"Processing material: {material.name}")
            if not material.use_nodes:
                self.report({'INFO'},"Enabling use_nodes for material")
                material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links

            # Log all node types in the material
            for node in nodes:
                self.report({'INFO'},f"Node: {node.name}, Type: {node.type}")

            # Create an Emission node and connect it to the Output node
            emission_node = nodes.new(type='ShaderNodeEmission')
            self.report({'INFO'},"Created Emission node")
            output_node = next(node for node in nodes if node.type == 'OUTPUT_MATERIAL')


            # Disconnect any existing connections to the Material Output node
            for input_socket in output_node.inputs:
                if input_socket.is_linked:
                    for link in input_socket.links:
                        links.remove(link)
                        self.report({'INFO'},"Disconnected existing links to Material Output node")

            links.new(emission_node.outputs[0], output_node.inputs[0])
            self.report({'INFO'},"Connected Emission node to Output node")

            # Find the Principled BSDF node and its connected Image Texture node
            #principled_node = next((node for node in nodes if node.type == 'ShaderNodeBsdfPrincipled'), None)
            principled_node = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)

            if principled_node:
                self.report({'INFO'},"Found Principled BSDF node")
                base_color_input = principled_node.inputs['Base Color']
                if base_color_input.is_linked:
                    texture_node = next((link.from_node for link in base_color_input.links if link.from_node.type == 'TEX_IMAGE'), None)
                    if texture_node:
                        self.report({'INFO'},f"Found Image Texture node: {texture_node.image.name}")
                        # Connect the texture node to the Emission node
                        links.new(texture_node.outputs['Color'], emission_node.inputs['Color'])
                        self.report({'INFO'},"Connected Image Texture node to Emission node")
                    else:
                        self.report({'INFO'},"No Image Texture node connected to Base Color")
                else:
                    self.report({'INFO'},"Base Color input of Principled BSDF node is not linked")
            else:
                self.report({'INFO'},"No Principled BSDF node found")

        self.report({'INFO'}, "Materials converted to emission")
        return {'FINISHED'}



class OBJECT_OT_RevertToBasic(bpy.types.Operator):
    bl_idname = "object.revert_to_basic"
    bl_label = "Revert to Basic"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        for material in bpy.data.materials:
            if not material.use_nodes:
                continue
            nodes = material.node_tree.nodes
            links = material.node_tree.links

            # Remove all existing links and nodes except the Output node
            for node in nodes:
                if node.type != 'OUTPUT_MATERIAL':
                    nodes.remove(node)

            # Create a Diffuse BSDF node and connect it to the Output node
            diffuse_node = nodes.new(type='ShaderNodeBsdfDiffuse')
            output_node = next(node for node in nodes if node.type == 'OUTPUT_MATERIAL')
            links.new(diffuse_node.outputs[0], output_node.inputs[0])

            # Check if there was a stored texture in the material
            if "original_texture" in material:
                image_name = material["original_texture"]
                if image_name in bpy.data.images:
                    texture_node = nodes.new(type='ShaderNodeTexImage')
                    texture_node.image = bpy.data.images[image_name]
                    links.new(texture_node.outputs[0], diffuse_node.inputs[0])

        self.report({'INFO'}, "Materials reverted to basic")
        return {'FINISHED'}

class ZENV_PT_MaterialConverterPanel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport"""
    bl_label = "Material Converter"
    bl_idname = "ZENV_PT_material_converter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("object.convert_to_emission")
        layout.operator("object.revert_to_basic")

def register():
    bpy.utils.register_class(OBJECT_OT_ConvertToEmission)
    bpy.utils.register_class(OBJECT_OT_RevertToBasic)
    bpy.utils.register_class(ZENV_PT_MaterialConverterPanel)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_ConvertToEmission)
    bpy.utils.unregister_class(OBJECT_OT_RevertToBasic)
    bpy.utils.unregister_class(ZENV_PT_MaterialConverterPanel)

if __name__ == "__main__":
    register()
