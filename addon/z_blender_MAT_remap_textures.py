#region META
bl_info = {
    "name": 'MAT Remap Textures',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Remap texture paths in materials',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 80,
    "tags": ['material', 'texture', 'remap', 'path', 'relink', 'repair'],
    "description_short": 'remap texture paths in materials',
    "description_medium": 'Scans all materials in the blend file, finds image texture nodes whose filepath contains a user-specified old path prefix, and replaces that prefix with a new path while optionally changing the file extension. Only remaps if the target file exists on disk. Forces image updates and area redraws after remapping.',
    "description_long": """
MAT Remap Textures - A Blender addon for texture path remapping.
remap texture paths in materials, switch between texture sets.
""",
    "image_overview": 'zenv_blender_MAT_remap_textures.png',
    "addon_image": 'zenv_blender_MAT_remap_textures.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, EnumProperty, PointerProperty
#endregion


#region PROPS
# Property group for texture remapping, registered on the Scene.

class ZENV_PG_RemapTextures_Properties(PropertyGroup):
    """Properties for texture remapping."""
    old_path: StringProperty(
        name="Old Path",
        description="Path to replace in texture references",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )
    new_path: StringProperty(
        name="New Path",
        description="New path to use for texture references",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )
    image_ext: EnumProperty(
        name="Image Extension",
        description="Image file extension to use",
        items=[
            ('.keep', "Keep Original", "Keep the original file extension"),
            ('.png', "PNG", "Use PNG format"),
            ('.bmp', "BMP", "Use BMP format"),
            ('.jpg', "JPG", "Use JPG format"),
            ('.tga', "TGA", "Use TGA format"),
            ('.tif', "TIF", "Use TIF format"),
        ],
        default='.keep'
    )
#endregion


#region OP
# Operator that remaps texture filepaths in all materials.

class ZENV_OT_RemapTextures(Operator):
    """Remap texture paths in materials."""
    bl_idname = "zenv.remap_textures"
    bl_label = "Remap Textures"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def normalize_path(cls, path):
        """Normalize a directory path for matching.

        Converts to absolute path, replaces backslashes with forward
        slashes, and strips trailing slashes.
        """
        path = os.path.abspath(path)
        path = path.replace('\\', '/')
        if path.endswith('/'):
            path = path[:-1]
        return path

    @classmethod
    def compute_new_filepath(cls, old_filepath, old_path, new_path, ext):
        """Compute the remapped filepath for a given image.

        Uses prefix matching (``startswith``) so the old path must
        appear at the start of the filepath, not as a substring in
        the middle.

        Args:
            old_filepath: the image's current absolute filepath
                (forward-slash normalized).
            old_path: the normalized old path prefix to replace.
            new_path: the normalized new path prefix.
            ext: the target extension (e.g. '.png'), or '.keep' to
                preserve the original extension.

        Returns:
            The new filepath string, or None if old_path is not a
            prefix of old_filepath.
        """
        if not old_filepath.startswith(old_path):
            return None

        rel_path = old_filepath[len(old_path):].lstrip('/')

        if ext == '.keep':
            new_filepath = f"{new_path}/{rel_path}"
        else:
            base_path = os.path.splitext(rel_path)[0]
            new_filepath = f"{new_path}/{base_path}{ext}"

        return new_filepath

    @classmethod
    def remap_all_textures(cls, old_path, new_path, ext):
        """Remap texture filepaths across all materials in the blend file.

        Only remaps images whose filepath starts with ``old_path`` and
        whose target file exists on disk.

        Returns a tuple ``(remapped_images, missing_files)`` where
        ``remapped_images`` is a list of the image datablocks that were
        successfully remapped and ``missing_files`` is a list of
        filepath strings for target files that did not exist.
        """
        old_path = cls.normalize_path(old_path)
        new_path = cls.normalize_path(new_path)

        remapped_images = []
        missing_files = []

        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue

            for node in mat.node_tree.nodes:
                if node.type != 'TEX_IMAGE' or node.image is None:
                    continue

                img = node.image
                if not img.filepath:
                    continue

                old_filepath = bpy.path.abspath(img.filepath).replace('\\', '/')

                new_filepath = cls.compute_new_filepath(
                    old_filepath, old_path, new_path, ext
                )
                if new_filepath is None:
                    continue

                if os.path.exists(new_filepath):
                    img.filepath = new_filepath
                    img.filepath_raw = new_filepath
                    img.reload()
                    if img not in remapped_images:
                        remapped_images.append(img)
                else:
                    missing_files.append(new_filepath)

        return remapped_images, missing_files

    def execute(self, context):
        """Execute the texture remapping operation."""
        try:
            props = context.scene.zenv_remap_props
            old_path = props.old_path
            new_path = props.new_path
            ext = props.image_ext

            # Validate paths
            if not old_path or not new_path:
                self.report({'ERROR'}, "Both old and new paths must be specified")
                return {'CANCELLED'}

            remapped_images, missing_files = self.remap_all_textures(
                old_path, new_path, ext
            )

            remapped_count = len(remapped_images)

            # Update only the remapped images (not all images).
            for img in remapped_images:
                try:
                    img.update_tag()
                except (ReferenceError, RuntimeError):
                    pass

            # Redraw all areas to show changes (guard for background mode).
            screen = getattr(context, 'screen', None)
            if screen is not None:
                for area in screen.areas:
                    area.tag_redraw()

            # Report a single summary of missing files.
            if missing_files:
                self.report(
                    {'WARNING'},
                    f"{len(missing_files)} file(s) not found at new path"
                )

            if remapped_count > 0:
                self.report(
                    {'INFO'},
                    f"Remapped {remapped_count} texture paths"
                )
                return {'FINISHED'}
            else:
                self.report(
                    {'INFO'},
                    "No textures were remapped. Check paths and files."
                )
                return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error remapping textures: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_RemapTexturesPanel(Panel):
    """Panel for texture remapping tools."""
    bl_label = "MAT Remap Textures"
    bl_idname = "ZENV_PT_remap_textures"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_remap_props

        # Path inputs
        box = layout.box()

        box.prop(props, "old_path")
        box.prop(props, "new_path")
        box.prop(props, "image_ext")

        box.operator(ZENV_OT_RemapTextures.bl_idname)
#endregion


#region REG
classes = (
    ZENV_PG_RemapTextures_Properties,
    ZENV_OT_RemapTextures,
    ZENV_PT_RemapTexturesPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_remap_props = PointerProperty(
        type=ZENV_PG_RemapTextures_Properties
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_remap_props

if __name__ == "__main__":
    register()
#endregion
