bl_info = {
    "name": "MAT create from textures",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Sidebar > ZENV",
    "description": "Creates materials from selected texture files in folder",
}  

import bpy
import os

def create_material_from_texture(texture_path):
    # Create a new material
    mat_name = os.path.splitext(os.path.basename(texture_path))[0] + "_MI"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create Principled BSDF shader
    shader = nodes.new(type='ShaderNodeBsdfPrincipled')
    shader.location = (0, 0)

    # Create Texture node
    tex_image = nodes.new('ShaderNodeTexImage')
    tex_image.location = (-300, 0)
    tex_image.image = bpy.data.images.load(texture_path)

    # Link Texture node to Principled BSDF
    mat.node_tree.links.new(shader.inputs['Base Color'], tex_image.outputs['Color'])

    # Set material output
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (200, 0)
    mat.node_tree.links.new(output.inputs['Surface'], shader.outputs['BSDF'])

    return mat

class ZENV_OT_CreateMatsFromTextures(bpy.types.Operator):
    bl_idname = "zenv.create_mats_from_textures"
    bl_label = "Create Mats from Textures"
    bl_description = "Create materials from selected texture files"
    bl_options = {'REGISTER', 'UNDO'}

    # Define the file selection properties
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        for file_elem in self.files:
            texture_path = os.path.join(self.directory, file_elem.name)
            create_material_from_texture(texture_path)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ZENV_PT_Panel(bpy.types.Panel):
    bl_label = "ZENV"
    bl_idname = "ZENV_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_CreateMatsFromTextures.bl_idname)

def register():
    bpy.utils.register_class(ZENV_OT_CreateMatsFromTextures)
    bpy.utils.register_class(ZENV_PT_Panel)

def unregister():
    bpy.utils.unregister_class(ZENV_OT_CreateMatsFromTextures)
    bpy.utils.unregister_class(ZENV_PT_Panel)

if __name__ == "__main__":
    register()
