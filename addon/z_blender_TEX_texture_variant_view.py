#region META
bl_info = {
    "name": 'TEX Texture Variant View',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Quickly view and organize texture variants on a model',
    "status": 'working',
    "approved": True,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 10,
    "addon_order": 20,
    "tags": ['texture', 'variant', 'view', 'cycle', 'organize', 'rank'],
    "description_short": 'Quickly view and organize texture variants on a model',
    "description_medium": 'specify a folder of textures, then with a mesh selected cycle through them applied to the mesh, ranking them into subfolders - useful for visualizing and choosing the best from many synthesized texture variants',
    "description_long": 'specify a folder of textures , then with a mesh selected can quickly cycle through them applied to the mesh , ranking them into subfolders . useful for visualizing and choosing the best from many synthesized texture variants , supports valid_exts = .png ,.jpg, .jpeg, .tga, .tif, .tiff, .bmp, .webp',
    "image_overview": 'zenv_blender_TEX_texture_variant_view.png',
    "addon_image": 'zenv_blender_TEX_texture_variant_view.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
import shutil
import logging
from bpy.props import StringProperty, PointerProperty, IntProperty, CollectionProperty
from bpy.types import PropertyGroup, Panel, Operator

logger = logging.getLogger(__name__)
_zenv_texture_variant_view_console_handler = None

_ZENV_TEX_NODE_NAME = "ZENV_TEX_variant"
#endregion


#region PROPS
class ZENV_PG_TextureVariantFilePath(PropertyGroup):
    """One entry in the texture variant list.
    Using a CollectionProperty of path items trying to avoid the pitfall of
    packing filesystem paths into a single delimited string 
    """
    path: StringProperty(
        name="Path",
        description="Absolute path to a texture image on disk",
        subtype='FILE_PATH',
        default="",
    )


class ZENV_PG_TextureVariantViewRank_Properties(PropertyGroup):
    """Properties for texture variant viewer"""
    folder_path: StringProperty(
        name="Folder Path",
        description="Folder containing texture images",
        subtype='DIR_PATH'
    )
    texture_files: CollectionProperty(
        name="Texture Files",
        description="List of texture files discovered in the folder, in order",
        type=ZENV_PG_TextureVariantFilePath,
    )
    material_index: IntProperty(
        name="Material Index",
        description="Index of the current texture",
        default=0
    )

#endregion


#region UTILS
class ZENV_TextureVariantViewRank_Utils:
    """Utility functions for texture variant viewing"""
    
    @staticmethod
    def _set_texture_list(props, paths):
        """Replace the CollectionProperty contents with ``paths``."""
        props.texture_files.clear()
        for p in paths:
            item = props.texture_files.add()
            item.path = p

    @staticmethod
    def _get_texture_list(props):
        return [item.path for item in props.texture_files]

    @staticmethod
    def load_textures(context):
        """Load textures from the specified folder"""
        props = context.scene.zenv_TextureVariantViewRank_props
        folder_path = props.folder_path
        props.material_index = 0

        image_paths = []

        # Capture the material's currently assigned texture (if any) so the
        # user can cycle back to the original without losing it.
        obj = context.active_object
        if (obj and obj.material_slots and obj.material_slots[0].material
                and obj.material_slots[0].material.use_nodes):
            bsdf = obj.material_slots[0].material.node_tree.nodes.get('Principled BSDF')
            if bsdf and bsdf.inputs['Base Color'].links:
                img_tex_node = bsdf.inputs['Base Color'].links[0].from_node
                if img_tex_node and img_tex_node.type == 'TEX_IMAGE' and img_tex_node.image:
                    original_texture_path = bpy.path.abspath(img_tex_node.image.filepath)
                    if original_texture_path:
                        image_paths.append(original_texture_path)
                        logger.info("Captured original texture: %s", original_texture_path)

        # Enumerate only actual files in the folder -- never subdirectories
        # finding images of type extensions
        if folder_path:
            abs_folder = bpy.path.abspath(folder_path)
            valid_exts = ('.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.bmp', '.webp')
            try:
                entries = os.listdir(abs_folder)
            except (FileNotFoundError, PermissionError) as exc:
                logger.warning("Could not list folder '%s': %s", abs_folder, exc)
                entries = []
            for f in entries:
                full = os.path.join(abs_folder, f)
                if not os.path.isfile(full):
                    continue
                if f.lower().endswith(valid_exts):
                    image_paths.append(full)

        ZENV_TextureVariantViewRank_Utils._set_texture_list(props, image_paths)
        logger.info("Loaded %d texture variants from '%s'", len(image_paths), folder_path)

    @staticmethod
    def assign_texture(context):
        """Assign the current texture to the active object"""
        props = context.scene.zenv_TextureVariantViewRank_props
        obj = context.active_object

        textures = ZENV_TextureVariantViewRank_Utils._get_texture_list(props)
        if not textures or not obj or not obj.material_slots or not obj.material_slots[0].material:
            return
        if not (0 <= props.material_index < len(textures)):
            return
        current_texture = textures[props.material_index]

        mat = obj.material_slots[0].material
        if not mat.use_nodes:
            return
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf is None:
            return

        # Using specific stable name we control so that
        # repeated runs find (and update) the same node instead of
        # spawning ``Image Texture.001``, ``.002`` etc.
        img_tex_node = mat.node_tree.nodes.get(_ZENV_TEX_NODE_NAME)
        if img_tex_node is None:
            img_tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            img_tex_node.name = _ZENV_TEX_NODE_NAME
            img_tex_node.label = _ZENV_TEX_NODE_NAME

        img_tex_node.image = bpy.data.images.load(current_texture, check_existing=True)
        mat.node_tree.links.new(bsdf.inputs['Base Color'], img_tex_node.outputs['Color'])

        # Force the 3D viewport to pick up the new texture. Just swapping the
        # image on an existing TexImage node does not always trigger a
        # viewport redraw -- the user had to manually select the node in the
        # Shader editor to make it appear. Replicate that here by:
        #   1. making our node the active/selected node of the material tree
        #   2. tagging the node tree + material for depsgraph update
        #   3. forcing every 3D viewport region to redraw
        for node in mat.node_tree.nodes:
            node.select = False
        img_tex_node.select = True
        mat.node_tree.nodes.active = img_tex_node
        mat.node_tree.update_tag()
        mat.update_tag()
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    region.tag_redraw()
        logger.info("Assigned texture: %s", current_texture)

    @staticmethod
    def cycle_texture(context, direction):
        """Cycle to next or previous texture"""
        props = context.scene.zenv_TextureVariantViewRank_props

        textures = ZENV_TextureVariantViewRank_Utils._get_texture_list(props)
        num_textures = len(textures)
        if num_textures == 0:
            return
        if direction == 'NEXT':
            props.material_index = (props.material_index + 1) % num_textures
        elif direction == 'PREVIOUS':
            props.material_index = (props.material_index - 1) % num_textures
        logger.info("Cycled %s to index %d", direction, props.material_index)
        ZENV_TextureVariantViewRank_Utils.assign_texture(context)
#endregion


#region OP
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
        return len(props.texture_files) > 0

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = ZENV_TextureVariantViewRank_Utils._get_texture_list(props)
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
        return len(props.texture_files) > 0

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
        return len(props.texture_files) > 0

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
        return len(props.texture_files) > 0 and props.folder_path != ""

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = ZENV_TextureVariantViewRank_Utils._get_texture_list(props)
            current_texture_path = textures[props.material_index]

            target_folder = bpy.path.abspath(props.folder_path)
            subfolder_path = os.path.join(target_folder, "01")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)
            # Don't silently clobber an earlier ranking decision.
            if os.path.exists(new_texture_path):
                self.report({'WARNING'}, f"Skipped: '{new_texture_path}' already exists.")
                return {'CANCELLED'}
            if os.path.abspath(current_texture_path) == os.path.abspath(new_texture_path):
                self.report({'WARNING'}, "Source and destination are the same file.")
                return {'CANCELLED'}
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
        return len(props.texture_files) > 0 and props.folder_path != ""

    def execute(self, context):
        try:
            props = context.scene.zenv_TextureVariantViewRank_props
            textures = ZENV_TextureVariantViewRank_Utils._get_texture_list(props)
            current_texture_path = textures[props.material_index]

            target_folder = bpy.path.abspath(props.folder_path)
            subfolder_path = os.path.join(target_folder, "02")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)
            if os.path.exists(new_texture_path):
                self.report({'WARNING'}, f"Skipped: '{new_texture_path}' already exists.")
                return {'CANCELLED'}
            if os.path.abspath(current_texture_path) == os.path.abspath(new_texture_path):
                self.report({'WARNING'}, "Source and destination are the same file.")
                return {'CANCELLED'}
            shutil.move(current_texture_path, new_texture_path)

            # Update the in-memory list so subsequent cycle and copy ops
            # still find this texture at its new location.
            textures[props.material_index] = new_texture_path
            ZENV_TextureVariantViewRank_Utils._set_texture_list(props, textures)

            self.report({'INFO'}, f"Texture moved to {new_texture_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to move texture: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
class ZENV_PT_TextureVariantViewRank(Panel):
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
        if len(props.texture_files) > 0:
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
#endregion


#region REG
classes = (
    ZENV_PG_TextureVariantFilePath,
    ZENV_PG_TextureVariantViewRank_Properties,
    ZENV_OT_TextureVariantViewRank_Load,
    ZENV_OT_TextureVariantViewRank_CopyPath,
    ZENV_OT_TextureVariantViewRank_CyclePrevious,
    ZENV_OT_TextureVariantViewRank_CycleNext,
    ZENV_OT_TextureVariantViewRank_CopyToFolder,
    ZENV_OT_TextureVariantViewRank_MoveToFolder,
    ZENV_PT_TextureVariantViewRank,
)

def register():
    """Register the addon classes, properties, and logger."""
    global _zenv_texture_variant_view_console_handler
    if _zenv_texture_variant_view_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_texture_variant_view_console_handler = handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_TextureVariantViewRank_props = PointerProperty(type=ZENV_PG_TextureVariantViewRank_Properties)

def unregister():
    """Unregister the addon classes, properties, and logger."""
    global _zenv_texture_variant_view_console_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if hasattr(bpy.types.Scene, 'zenv_TextureVariantViewRank_props'):
        delattr(bpy.types.Scene, 'zenv_TextureVariantViewRank_props')
    if _zenv_texture_variant_view_console_handler is not None:
        try:
            logger.removeHandler(_zenv_texture_variant_view_console_handler)
        except ValueError:
            pass
        _zenv_texture_variant_view_console_handler = None

if __name__ == "__main__":
    register()
#endregion
