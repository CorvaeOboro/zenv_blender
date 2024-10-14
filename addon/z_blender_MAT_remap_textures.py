bl_info = {
    "name": "Texture Remap",
    "blender": (2, 80, 0),
    "category": "ZENV",
}

import bpy
import os
from bpy.props import StringProperty, PointerProperty
from bpy.types import Panel, Operator, PropertyGroup

class ZENV_OT_UpdateTextures(Operator):
    bl_idname = "zenv.update_textures"
    bl_label = "Update Textures"
    bl_description = "Updates all textures to point to images in the specified folder"

    def execute(self, context):
        scn = context.scene
        dir_path = scn.zenv_tool_props.folder_path

        if not os.path.isdir(dir_path):
            self.report({'ERROR'}, "Invalid directory path.")
            return {'CANCELLED'}

        # Update textures by file match
        for image in bpy.data.images:
            if image.source == 'FILE':
                image_path = os.path.join(dir_path, f"{image.name}.png")
                if os.path.exists(image_path):
                    image.filepath = image_path
                else:
                    self.report({'WARNING'}, f"No matching PNG file found for {image.name}")

        self.report({'INFO'}, "Textures updated successfully.")
        return {'FINISHED'}

class ZENV_OT_AssignTexturesByMaterial(Operator):
    bl_idname = "zenv.assign_textures_by_material"
    bl_label = "Assign Textures by Material"
    bl_description = "Assigns textures based on material names by removing a specified suffix"

    def execute(self, context):
        scn = context.scene
        dir_path = scn.zenv_tool_props.folder_path
        suffix = scn.zenv_tool_props.material_suffix

        if not os.path.isdir(dir_path):
            self.report({'ERROR'}, "Invalid directory path.")
            return {'CANCELLED'}

        # Update textures based on material name
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                base_name = mat.name.removesuffix(suffix)
                image_path = os.path.join(dir_path, f"{base_name}.png")
                if os.path.exists(image_path):
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            node.image = bpy.data.images.load(image_path, check_existing=True)
                else:
                    self.report({'WARNING'}, f"No matching PNG file found for {mat.name} as {base_name} in {image_path}")

        self.report({'INFO'}, "Materials updated successfully.")
        return {'FINISHED'}

class ZENV_PG_ToolProps(PropertyGroup):
    folder_path: StringProperty(
        name="Folder Path",
        description="Directory path where the .png files are located",
        subtype='DIR_PATH'
    )
    material_suffix: StringProperty(
        name="Material Suffix",
        description="Suffix to remove from material names when matching textures",
        default="_MI"
    )

class ZENV_PT_MainPanel(Panel):
    bl_label = "Texture Remap"
    bl_idname = "ZENV_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        layout.prop(scn.zenv_tool_props, "folder_path")
        layout.prop(scn.zenv_tool_props, "material_suffix")
        layout.operator("zenv.update_textures", icon='FILE_REFRESH')
        layout.operator("zenv.assign_textures_by_material", icon='MATERIAL')

def register():
    bpy.utils.register_class(ZENV_OT_UpdateTextures)
    bpy.utils.register_class(ZENV_OT_AssignTexturesByMaterial)
    bpy.utils.register_class(ZENV_PG_ToolProps)
    bpy.utils.register_class(ZENV_PT_MainPanel)
    bpy.types.Scene.zenv_tool_props = PointerProperty(type=ZENV_PG_ToolProps)

def unregister():
    bpy.utils.unregister_class(ZENV_OT_UpdateTextures)
    bpy.utils.unregister_class(ZENV_OT_AssignTexturesByMaterial)
    bpy.utils.unregister_class(ZENV_PG_ToolProps)
    bpy.utils.unregister_class(ZENV_PT_MainPanel)
    del bpy.types.Scene.zenv_tool_props

if __name__ == "__main__":
    register()
