bl_info = {
    "name": 'TEX Texture Variant View',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Quickly view and organize texture variants on a model',
    "status": 'working',
    "approved": True,
    "sort_priority": '2',
    "branch": 'Texture',
    "branch_prefix": 'TEX',
    "description_short": 'Quickly view and organize texture variants on a model',
    "description_long": 'specify a folder of textures , then with a mesh selected can quickly cycle through them applied to the mesh , ranking them into subfolders . useful for visualizing and choosing the best from many synthesized texture variants',
    "location": 'View3D > ZENV',
}

import bpy
import os
import shutil
from bpy.props import StringProperty, PointerProperty, IntProperty
from bpy.types import PropertyGroup, Panel, Operator

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_TextureVariantViewRank_Properties(PropertyGroup):
    """Properties for texture variant viewer"""
    folder_path: StringProperty(
        name="Folder Path",
        description="Folder containing texture images",
        subtype='DIR_PATH'
    )
    texture_files: StringProperty(
        name="Texture Files",
        description="List of texture files",
        default=""
    )
    material_index: IntProperty(
        name="Material Index",
        description="Index of the current texture",
        default=0
    )

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_TextureVariantViewRank_Utils:
    """Utility functions for texture variant viewing"""
    
    @staticmethod
    def load_textures(context):
        """Load textures from the specified folder"""
        props = context.scene.zenv_TextureVariantViewRank_props
        folder_path = props.folder_path
        props.texture_files = ""
        props.material_index = 0

        if folder_path:
            image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
                         if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            props.texture_files = '|'.join(image_files)

        # Store original texture
        obj = context.active_object
        if obj and obj.material_slots and obj.material_slots[0].material and obj.material_slots[0].material.use_nodes:
            bsdf = obj.material_slots[0].material.node_tree.nodes.get('Principled BSDF')
            if bsdf and bsdf.inputs['Base Color'].links:
                img_tex_node = bsdf.inputs['Base Color'].links[0].from_node
                if img_tex_node and img_tex_node.type == 'TEX_IMAGE' and img_tex_node.image:
                    original_texture_path = bpy.path.abspath(img_tex_node.image.filepath)
                    props.texture_files = original_texture_path + '|' + props.texture_files

    @staticmethod
    def assign_texture(context):
        """Assign the current texture to the active object"""
        props = context.scene.zenv_TextureVariantViewRank_props
        obj = context.active_object

        if props.texture_files and obj and obj.material_slots and obj.material_slots[0].material:
            textures = props.texture_files.split('|')
            current_texture = textures[props.material_index]

            mat = obj.material_slots[0].material
            if mat.use_nodes:
                bsdf = mat.node_tree.nodes.get('Principled BSDF')
                if bsdf:
                    if 'Image Texture' not in mat.node_tree.nodes:
                        img_tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    else:
                        img_tex_node = mat.node_tree.nodes['Image Texture']
                    img_tex_node.image = bpy.data.images.load(current_texture, check_existing=True)
                    mat.node_tree.links.new(bsdf.inputs['Base Color'], img_tex_node.outputs['Color'])
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

    @staticmethod
    def cycle_texture(context, direction):
        """Cycle to next or previous texture"""
        props = context.scene.zenv_TextureVariantViewRank_props

        if props.texture_files:
            textures = props.texture_files.split('|')
            num_textures = len(textures)
            if direction == 'NEXT':
                props.material_index = (props.material_index + 1) % num_textures
            elif direction == 'PREVIOUS':
                props.material_index = (props.material_index - 1) % num_textures
            ZENV_TextureVariantViewRank_Utils.assign_texture(context)

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_TextureVariantViewRank_Load(Operator):
    """Load textures from the specified folder"""
    bl_idname = "zenv.texturevariant_load"
    bl_label = "Load Textures"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        try:
            ZENV_TextureVariantViewRank_Utils.load_textures(context)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load textures: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_TextureVariantViewRank_CopyPath(Operator):
    """Copy current texture path to clipboard"""
    bl_idname = "zenv.texturevariant_copy_path"
    bl_label = "Copy Path"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.zenv_TextureVariantViewRank_props
        return props.texture_files != ""

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = props.texture_files.split('|')
            current_texture = textures[props.material_index]
            context.window_manager.clipboard = current_texture
            self.report({'INFO'}, "Texture path copied to clipboard")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy path: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_TextureVariantViewRank_CyclePrevious(Operator):
    """View previous texture variant"""
    bl_idname = "zenv.texturevariant_previous"
    bl_label = "Previous"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.zenv_TextureVariantViewRank_props
        return props.texture_files != ""

    def execute(self, context):
        try:
            ZENV_TextureVariantViewRank_Utils.cycle_texture(context, 'PREVIOUS')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to cycle texture: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_TextureVariantViewRank_CycleNext(Operator):
    """View next texture variant"""
    bl_idname = "zenv.texturevariant_next"
    bl_label = "Next"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.zenv_TextureVariantViewRank_props
        return props.texture_files != ""

    def execute(self, context):
        try:
            ZENV_TextureVariantViewRank_Utils.cycle_texture(context, 'NEXT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to cycle texture: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_TextureVariantViewRank_CopyToFolder(Operator):
    """Copy current texture to subfolder"""
    bl_idname = "zenv.texturevariant_copy_to_folder"
    bl_label = "Rank 01"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.zenv_TextureVariantViewRank_props
        return props.texture_files != "" and props.folder_path != ""

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = props.texture_files.split('|')
            current_texture_path = textures[props.material_index]

            target_folder = bpy.path.abspath(props.folder_path)
            subfolder_path = os.path.join(target_folder, "01")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)
            shutil.copyfile(current_texture_path, new_texture_path)

            self.report({'INFO'}, f"Texture copied to {new_texture_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy texture: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_TextureVariantViewRank_MoveToFolder(Operator):
    """Move current texture to subfolder"""
    bl_idname = "zenv.texturevariant_move_to_folder"
    bl_label = "Rank 02"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.zenv_TextureVariantViewRank_props
        return props.texture_files != "" and props.folder_path != ""

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = props.texture_files.split('|')
            current_texture_path = textures[props.material_index]

            target_folder = bpy.path.abspath(props.folder_path)
            subfolder_path = os.path.join(target_folder, "02")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)
            shutil.move(current_texture_path, new_texture_path)

            textures[props.material_index] = new_texture_path
            props.texture_files = '|'.join(textures)

            self.report({'INFO'}, f"Texture moved to {new_texture_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to move texture: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_TextureVariantViewRank_Panel(Panel):
    """Panel for texture variant viewing tools"""
    bl_label = "TEX Texture Variants"
    bl_idname = "ZENV_PT_texturevariant"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_TextureVariantViewRank_props

        # Folder selection
        box = layout.box()
        box.label(text="Texture Folder:", icon='FILE_FOLDER')
        box.prop(props, "folder_path", text="")
        box.operator("zenv.texturevariant_load", icon='FILE_REFRESH')

        # Navigation
        if props.texture_files:
            box = layout.box()
            box.label(text="Navigation:", icon='TEXTURE')
            row = box.row(align=True)
            row.operator("zenv.texturevariant_previous", icon='TRIA_LEFT')
            row.operator("zenv.texturevariant_next", icon='TRIA_RIGHT')
            box.operator("zenv.texturevariant_copy_path", icon='COPYDOWN')

            # Texture organization
            box = layout.box()
            box.label(text="Organize:", icon='NEWFOLDER')
            row = box.row(align=True)
            row.operator("zenv.texturevariant_copy_to_folder", icon='DUPLICATE')
            row.operator("zenv.texturevariant_move_to_folder", icon='FILE_PARENT')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_TextureVariantViewRank_Properties,
    ZENV_OT_TextureVariantViewRank_Load,
    ZENV_OT_TextureVariantViewRank_CopyPath,
    ZENV_OT_TextureVariantViewRank_CyclePrevious,
    ZENV_OT_TextureVariantViewRank_CycleNext,
    ZENV_OT_TextureVariantViewRank_CopyToFolder,
    ZENV_OT_TextureVariantViewRank_MoveToFolder,
    ZENV_PT_TextureVariantViewRank_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_TextureVariantViewRank_props = PointerProperty(type=ZENV_PG_TextureVariantViewRank_Properties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_TextureVariantViewRank_props

if __name__ == "__main__":
    register()
