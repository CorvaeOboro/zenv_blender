#region META
bl_info = {
    "name": 'TEX Texture Export Dated',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Save current painted texture(s) with a dated suffix into the matching project subfolder',
    "status": 'working',
    "approved": True,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 10,
    "addon_order": 70,
    "tags": ['texture', 'export', 'dated', 'paint', 'backup', 'versioned'],
    "description_short": 'Export painted textures to dated copies inside the matching project folder',
    "description_medium": 'one click export of currently painted textures with a YYYYMMDD_HHMMSS suffix into the texture/material folder discovered next to the current .blend file - intended for projects (e.g. EverQuest) where every material/texture has a matching folder in the blend base dir',
    "description_long": """\
TEXTURE EXPORT DATED
 Save the active painted texture(s) as a dated copy without the usual
 Image Editor save-as dialog clicking.
 The destination folder is auto-discovered by matching the texture or
 material name against subfolders next to the current .blend file. This
 fits naming conventions like the EverQuest project where every material
 and texture has a corresponding folder in the project's base directory.
 Includes a one-click "Export All Modified" for the active object so any
 dirty image used by its materials gets a versioned copy in one go.
""",
    "image_overview": 'zenv_blender_TEX_texture_export_dated.png',
    "addon_image": 'zenv_blender_TEX_texture_export_dated.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
import re
import shutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
_zenv_tex_export_dated_console_handler = None
#endregion


#region UTILS
class ZENV_TexExportDated_Utils:
    """Helpers for finding destination folders and writing dated copies."""

    DATE_FMT = "%Y%m%d%H%M%S"

    # Only blender's auto-duplicate suffix (.001) is stripped when matching
    # names to folders - the original version tag (e.g. _v003) is intentionally
    # preserved so 'stone_v003.png' resolves to a folder named 'stone_v003'.
    _STRIP_PATTERNS = (
        re.compile(r"\.\d{3}$"),               # blender duplicate suffix (.001)
    )

    @staticmethod
    def get_blend_dir():
        """Return the directory of the currently open .blend, or None."""
        path = bpy.data.filepath
        if not path:
            return None
        return os.path.dirname(os.path.abspath(path))

    @classmethod
    def normalize_name(cls, name):
        """Lowercase + strip file extension and Blender's .001 duplicate suffix.

        Version tags like '_v003' are intentionally preserved so the texture
        name maps 1:1 onto the project folder name.
        """
        if not name:
            return ""
        base = os.path.splitext(name)[0]
        prev = None
        while prev != base:
            prev = base
            for pat in cls._STRIP_PATTERNS:
                base = pat.sub("", base)
        return base.strip().lower()

    @classmethod
    def find_matching_subfolder(cls, blend_dir, candidate_names):
        """Walk blend_dir and return the first subfolder whose name matches
        any of the candidate names (case-insensitive, suffix-stripped).

        Search is case-insensitive and prefers exact normalized matches
        before falling back to "subfolder name is contained in candidate"
        or "candidate is contained in subfolder name".
        """
        if not blend_dir or not os.path.isdir(blend_dir):
            return None

        norm_candidates = [cls.normalize_name(n) for n in candidate_names if n]
        norm_candidates = [n for n in norm_candidates if n]
        if not norm_candidates:
            return None

        exact = []
        contains = []
        for root, dirs, _files in os.walk(blend_dir):
            # Skip hidden / VCS / blender backup folders quickly
            dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('__pycache__',)]
            for d in dirs:
                norm_d = cls.normalize_name(d)
                if not norm_d:
                    continue
                if norm_d in norm_candidates:
                    exact.append(os.path.join(root, d))
                else:
                    for cand in norm_candidates:
                        if norm_d == cand:
                            exact.append(os.path.join(root, d))
                            break
                        if norm_d in cand or cand in norm_d:
                            contains.append(os.path.join(root, d))
                            break

        if exact:
            # Prefer the shallowest match (closest to blend_dir).
            exact.sort(key=lambda p: (p.count(os.sep), len(p)))
            return exact[0]
        if contains:
            contains.sort(key=lambda p: (p.count(os.sep), len(p)))
            return contains[0]
        return None

    @staticmethod
    def collect_candidate_names(image, material=None):
        """Build the ordered list of names we will try to match folders against."""
        names = []
        if image is not None:
            # filename of the image on disk (without extension)
            if image.filepath:
                fname = os.path.basename(bpy.path.abspath(image.filepath))
                if fname:
                    names.append(os.path.splitext(fname)[0])
            # datablock name
            if image.name:
                names.append(image.name)
        if material is not None and material.name:
            names.append(material.name)
        # de-dup preserving order
        seen = set()
        out = []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    @staticmethod
    def get_image_extension(image):
        """Pick a sensible file extension for the saved copy."""
        # 1. existing filepath
        if image.filepath:
            ext = os.path.splitext(image.filepath)[1].lower()
            if ext in ('.png', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.exr', '.hdr'):
                return ext
        # 2. file_format
        ff = (image.file_format or '').upper()
        ff_map = {
            'PNG': '.png', 'TARGA': '.tga', 'TARGA_RAW': '.tga',
            'JPEG': '.jpg', 'JPEG2000': '.jp2', 'BMP': '.bmp',
            'TIFF': '.tif', 'OPEN_EXR': '.exr', 'OPEN_EXR_MULTILAYER': '.exr',
            'HDR': '.hdr',
        }
        if ff in ff_map:
            return ff_map[ff]
        return '.png'

    @classmethod
    def build_dated_filename(cls, image, material=None, ext_override=None):
        """Return only the filename portion (no directory) for the dated copy.

        Uses the texture name directly (preserving any version suffix like
        '_v003'). Example: 'stone_v003.png' -> 'stone_v003_20260519063102.png'.
        """
        candidates = cls.collect_candidate_names(image, material)
        base = candidates[0] if candidates else (image.name or 'texture')
        base = os.path.splitext(base)[0]
        stamp = datetime.now().strftime(cls.DATE_FMT)
        ext = ext_override or cls.get_image_extension(image)
        return f"{base}_{stamp}{ext}"

    @staticmethod
    def ensure_dir(path):
        if path and not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def resolve_target_dir(cls, image, material, prefer_blend_root, history_subfolder):
        """Decide which directory to save into.

        Order:
          1. matching subfolder under the blend dir based on texture/material name
          2. directory of the image's existing filepath
          3. blend dir itself
        Then optionally append a history subfolder (e.g. "_versions").
        """
        blend_dir = cls.get_blend_dir()
        candidates = cls.collect_candidate_names(image, material)
        target = cls.find_matching_subfolder(blend_dir, candidates) if blend_dir else None

        if target is None and image.filepath:
            abs_image = bpy.path.abspath(image.filepath)
            if abs_image:
                d = os.path.dirname(abs_image)
                if os.path.isdir(d):
                    target = d

        if target is None and blend_dir and prefer_blend_root:
            target = blend_dir

        if target is None:
            return None

        if history_subfolder:
            target = os.path.join(target, history_subfolder)
        return target

    @staticmethod
    def iter_object_images(obj):
        """Yield (material, image) pairs for every image used by obj's materials."""
        if obj is None or obj.type != 'MESH':
            return
        seen = set()
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image is not None:
                    key = (mat.name, node.image.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield mat, node.image

    @staticmethod
    def save_image_copy(image, target_path):
        """Write image pixels to target_path without altering the live datablock.

        We render via a copy so we never overwrite the user's working filepath.
        Returns True on success.
        """
        if image is None:
            return False
        # Make sure pixels are available even for packed/painted images
        try:
            if not image.has_data:
                logger.warning("Image '%s' has no data, skipping", image.name)
                return False
        except Exception:
            pass

        scene = bpy.context.scene
        prev_settings = scene.render.image_settings
        prev_format = prev_settings.file_format
        prev_color_mode = prev_settings.color_mode
        prev_color_depth = prev_settings.color_depth

        ext = os.path.splitext(target_path)[1].lower()
        fmt_for_ext = {
            '.png': ('PNG', 'RGBA', '8'),
            '.tga': ('TARGA', 'RGBA', '8'),
            '.jpg': ('JPEG', 'RGB', '8'),
            '.jpeg': ('JPEG', 'RGB', '8'),
            '.bmp': ('BMP', 'RGB', '8'),
            '.tif': ('TIFF', 'RGBA', '8'),
            '.tiff': ('TIFF', 'RGBA', '8'),
            '.exr': ('OPEN_EXR', 'RGBA', '32'),
            '.hdr': ('HDR', 'RGB', '32'),
        }
        fmt, color_mode, color_depth = fmt_for_ext.get(ext, ('PNG', 'RGBA', '8'))

        try:
            prev_settings.file_format = fmt
            prev_settings.color_mode = color_mode
            prev_settings.color_depth = color_depth
            ZENV_TexExportDated_Utils.ensure_dir(os.path.dirname(target_path))
            image.save_render(filepath=target_path, scene=scene)
            return True
        except Exception as exc:
            logger.error("Failed saving '%s' to '%s': %s", image.name, target_path, exc)
            return False
        finally:
            prev_settings.file_format = prev_format
            prev_settings.color_mode = prev_color_mode
            prev_settings.color_depth = prev_color_depth

    @staticmethod
    def find_active_paint_image(context):
        """Find the image the user is currently painting on, plus its material (if any).

        Priority:
          1. Image Editor's active image (if visible)
          2. Active object's active material -> active TEX_IMAGE node
          3. Texture Paint slots on the active object
        """
        # 1. image editor
        for area in context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                for space in area.spaces:
                    if space.type == 'IMAGE_EDITOR' and space.image is not None:
                        return space.image, None

        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return None, None

        mat = obj.active_material
        if mat is not None and mat.use_nodes:
            # active node first
            active = mat.node_tree.nodes.active
            if active is not None and active.type == 'TEX_IMAGE' and active.image is not None:
                return active.image, mat
            # selected image node
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.select and node.image is not None:
                    return node.image, mat
            # any image node
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image is not None:
                    return node.image, mat

        # 3. texture paint slots
        if obj.mode == 'TEXTURE_PAINT' or context.scene.tool_settings.image_paint:
            ips = context.scene.tool_settings.image_paint
            if ips and ips.canvas is not None:
                return ips.canvas, mat

        return None, mat
#endregion


#region PROPS
class ZENV_TexExportDated_Properties:

    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_texexp_history_subfolder = bpy.props.StringProperty(
            name="History Subfolder",
            description="Optional subfolder (under the resolved texture folder) to drop dated copies into. Leave blank to write next to the texture",
            default="paint",
        )
        bpy.types.Scene.zenv_texexp_only_dirty = bpy.props.BoolProperty(
            name="Only Modified",
            description="When exporting all images on the active object, only export images flagged as dirty (unsaved paint changes)",
            default=True,
        )
        bpy.types.Scene.zenv_texexp_prefer_blend_root = bpy.props.BoolProperty(
            name="Fallback To Blend Folder",
            description="If no matching texture/material subfolder is found, save next to the .blend file as a fallback",
            default=True,
        )
        bpy.types.Scene.zenv_texexp_show_advanced = bpy.props.BoolProperty(
            name="Advanced",
            description="Show advanced options and per-object export controls",
            default=False,
        )

    @classmethod
    def unregister(cls):
        for attr in (
            'zenv_texexp_history_subfolder',
            'zenv_texexp_only_dirty',
            'zenv_texexp_prefer_blend_root',
            'zenv_texexp_show_advanced',
        ):
            if hasattr(bpy.types.Scene, attr):
                delattr(bpy.types.Scene, attr)
#endregion


#region OP
class ZENV_OT_TexExportDated_ExportActive(bpy.types.Operator):
    """Export the currently active painted texture as a dated copy"""
    bl_idname = "zenv.texexp_export_active"
    bl_label = "Export Active Texture (Dated)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image, mat = ZENV_TexExportDated_Utils.find_active_paint_image(context)
        if image is None:
            self.report({'ERROR'}, "No active paint image found. Open one in the Image Editor or in the active material.")
            return {'CANCELLED'}

        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first - the destination folder is resolved relative to it.")
            return {'CANCELLED'}

        filename = ZENV_TexExportDated_Utils.build_dated_filename(image, mat)
        target_dir = ZENV_TexExportDated_Utils.resolve_target_dir(
            image,
            mat,
            prefer_blend_root=context.scene.zenv_texexp_prefer_blend_root,
            history_subfolder=context.scene.zenv_texexp_history_subfolder.strip(),
        )
        if target_dir is None:
            self.report({'ERROR'}, f"Could not resolve a destination folder for '{image.name}'.")
            return {'CANCELLED'}

        target_path = os.path.join(target_dir, filename)
        ok = ZENV_TexExportDated_Utils.save_image_copy(image, target_path)
        if not ok:
            self.report({'ERROR'}, f"Failed to save '{image.name}' (see console).")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Saved {os.path.basename(target_path)} -> {target_dir}")
        logger.info("Exported dated copy: %s", target_path)
        return {'FINISHED'}


class ZENV_OT_TexExportDated_ExportObject(bpy.types.Operator):
    """Export every image used by the active object's materials as a dated copy"""
    bl_idname = "zenv.texexp_export_object"
    bl_label = "Export Object Textures (Dated)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh.")
            return {'CANCELLED'}
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first - the destination folder is resolved relative to it.")
            return {'CANCELLED'}

        only_dirty = context.scene.zenv_texexp_only_dirty
        history = context.scene.zenv_texexp_history_subfolder.strip()
        prefer_root = context.scene.zenv_texexp_prefer_blend_root

        exported = 0
        skipped = 0
        failed = 0
        for mat, image in ZENV_TexExportDated_Utils.iter_object_images(obj):
            if only_dirty and not getattr(image, 'is_dirty', False):
                skipped += 1
                continue
            filename = ZENV_TexExportDated_Utils.build_dated_filename(image, mat)
            target_dir = ZENV_TexExportDated_Utils.resolve_target_dir(
                image, mat,
                prefer_blend_root=prefer_root,
                history_subfolder=history,
            )
            if target_dir is None:
                failed += 1
                logger.warning("No destination folder for '%s'", image.name)
                continue
            target_path = os.path.join(target_dir, filename)
            if ZENV_TexExportDated_Utils.save_image_copy(image, target_path):
                exported += 1
                logger.info("Exported dated copy: %s", target_path)
            else:
                failed += 1

        msg = f"Exported {exported} | Skipped {skipped} | Failed {failed}"
        self.report({'INFO' if failed == 0 else 'WARNING'}, msg)
        return {'FINISHED'}


class ZENV_OT_TexExportDated_OpenFolder(bpy.types.Operator):
    """Open the destination folder for the active texture in the system file browser"""
    bl_idname = "zenv.texexp_open_folder"
    bl_label = "Open Destination Folder"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image, mat = ZENV_TexExportDated_Utils.find_active_paint_image(context)
        if image is None:
            self.report({'ERROR'}, "No active paint image found.")
            return {'CANCELLED'}
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first.")
            return {'CANCELLED'}
        target_dir = ZENV_TexExportDated_Utils.resolve_target_dir(
            image, mat,
            prefer_blend_root=context.scene.zenv_texexp_prefer_blend_root,
            history_subfolder=context.scene.zenv_texexp_history_subfolder.strip(),
        )
        if target_dir is None:
            self.report({'ERROR'}, "No destination folder resolved.")
            return {'CANCELLED'}
        ZENV_TexExportDated_Utils.ensure_dir(target_dir)
        try:
            bpy.ops.wm.path_open(filepath=target_dir)
        except Exception as exc:
            self.report({'ERROR'}, f"Could not open folder: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}
#endregion


#region PANEL
class ZENV_PT_TexExportDated(bpy.types.Panel):
    """Panel for dated texture exports"""
    bl_label = "TEX Texture Export Dated"
    bl_idname = "ZENV_PT_texexp_dated"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        image, mat = ZENV_TexExportDated_Utils.find_active_paint_image(context)

        # 1) Active texture name (top)
        row = layout.row(align=True)
        if image is None:
            row.label(text="No active texture", icon='ERROR')
        else:
            icon = 'FILE_REFRESH' if getattr(image, 'is_dirty', False) else 'IMAGE_DATA'
            row.label(text=image.name, icon=icon)

        # 2) Export Active button
        layout.operator("zenv.texexp_export_active", text="Export Active Texture", icon='FILE_TICK')

        # 3) Collapsable Output Settings section
        header = layout.row(align=True)
        icon = 'TRIA_DOWN' if scene.zenv_texexp_show_advanced else 'TRIA_RIGHT'
        header.prop(scene, "zenv_texexp_show_advanced", text="Output Settings", icon=icon, emboss=False)
        if scene.zenv_texexp_show_advanced:
            box = layout.box()
            box.prop(scene, "zenv_texexp_only_dirty")
            box.prop(scene, "zenv_texexp_history_subfolder", text="Subfolder")
            box.prop(scene, "zenv_texexp_prefer_blend_root")
            box.operator("zenv.texexp_export_object", text="Export Object Textures", icon='OUTLINER_OB_MESH')
            box.operator("zenv.texexp_open_folder", text="Open Folder", icon='FILE_FOLDER')
#endregion


#region REG
classes = (
    ZENV_OT_TexExportDated_ExportActive,
    ZENV_OT_TexExportDated_ExportObject,
    ZENV_OT_TexExportDated_OpenFolder,
    ZENV_PT_TexExportDated,
)


def register():
    """Register the addon classes, properties, and logger."""
    global _zenv_tex_export_dated_console_handler
    if _zenv_tex_export_dated_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_tex_export_dated_console_handler = handler
    for cls in classes:
        bpy.utils.register_class(cls)
    ZENV_TexExportDated_Properties.register()


def unregister():
    """Unregister the addon classes, properties, and logger."""
    global _zenv_tex_export_dated_console_handler
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    ZENV_TexExportDated_Properties.unregister()
    if _zenv_tex_export_dated_console_handler is not None:
        try:
            logger.removeHandler(_zenv_tex_export_dated_console_handler)
        except ValueError:
            pass
        _zenv_tex_export_dated_console_handler = None


if __name__ == "__main__":
    register()
#endregion
