#region META
bl_info = {
    "name": 'EXPORT All Objects to Separate Blend Files',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Save each object in the scene to its own blend file',
    "status": 'working',
    "approved": True,
    "group": 'Export',
    "group_prefix": 'EXPORT',
    "group_order": 50,
    "addon_order": 10,
    "tags": ['export', 'batch', 'blend', 'asset', 'separate', 'split'],
    "description_short": 'batch export selected objects to separate blend files',
    "description_medium": 'Batch-export each object in the current scene (or current selection) to its own standalone .blend file via bpy.data.libraries.write. Handles filename sanitization, collision disambiguation, overwrite control, compression, and path remapping options.',
    "description_long": """
EXPORT Objects to Blend Files
batch export each object in the current scene to its own separate .blend file.
This is useful for:
- Creating individual asset files from a collection of objects
- Splitting large scenes into smaller, more manageable files
- Preparing objects for use in other projects
""",
    "image_overview": 'zenv_blender_EXPORT_all_objects_to_separate_blend.png',
    "addon_image": 'zenv_blender_EXPORT_all_objects_to_separate_blend.png',
    "location": 'File > Export > All Objects to Blend Files',
}
#endregion

#region IMPORT
import bpy
import os
import re
#endregion

#region CONSTS
# Characters not allowed in filenames on Windows (a strict superset of what
# POSIX filesystems object to). Control characters and anything outside this
# list are mapped to a single underscore.
_FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

# DOS reserved device names that cannot be used as filenames on Windows.
_RESERVED_DOS_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
#endregion


#region OP
# Export operator - the core logic that batch-writes each object to its
# own .blend file via bpy.data.libraries.write.

class ZENV_OT_SaveToSeparateBlends(bpy.types.Operator):
    """Export each object in the current scene to its own .blend file.

    :func:`bpy.data.libraries.write` each output file contains ONLY the
    exported object and its dependencies, not a full copy of the current
    blend. Existing files are skipped unless ``overwrite`` is enabled.
    """
    bl_idname = "zenv.save_to_separate_blends"
    bl_label = "Save Objects to Separate Blend Files"
    bl_options = {'REGISTER', 'UNDO'}

    #region PROPS
    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to export blend files to",
        subtype='DIR_PATH'
    )
    overwrite: bpy.props.BoolProperty(
        name="Overwrite Existing",
        description="Overwrite any .blend files that already exist in the target directory",
        default=False,
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Only export currently selected objects instead of every object in the scene",
        default=False,
    )
    compress: bpy.props.BoolProperty(
        name="Compress",
        description="Compress the saved .blend files",
        default=False,
    )
    path_remap: bpy.props.EnumProperty(
        name="Path Remap",
        description="How to remap file paths in the exported .blend files",
        items=[
            ('RELATIVE', "Relative", "Remap paths relative to the exported file location"),
            ('NONE', "None", "Keep absolute paths as-is"),
            ('STRIP', "Strip", "Strip all external file paths (textures, etc.)"),
        ],
        default='RELATIVE',
    )
    unique_data: bpy.props.BoolProperty(
        name="Unique Data Only",
        description="Skip objects whose mesh/curve data was already exported by a previous object in this run (avoids duplicate data in multi-user scenarios)",
        default=False,
    )
    #endregion

    #region SANITIZE
    @classmethod
    def _sanitize_filename(cls, name, fallback="object"):
        """Return ``name`` with characters that are invalid in filenames replaced.

        Trailing dots / spaces (which Windows Explorer strips) and
        reserved DOS device names (``CON``, ``PRN``, ``AUX``, ``NUL``,
        ``COM1`` .. ``LPT9``) are also handled.
        """
        cleaned = _FILENAME_INVALID_RE.sub('_', name).strip().rstrip('. ')
        if not cleaned:
            cleaned = fallback
        if cleaned.upper() in _RESERVED_DOS_NAMES:
            cleaned = f"_{cleaned}"
        # Hard-cap length so we never hit MAX_PATH style errors.
        return cleaned[:200]
    #endregion

    #region EXEC
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'selected_only')
        layout.prop(self, 'overwrite')
        layout.prop(self, 'compress')
        layout.prop(self, 'path_remap')
        layout.prop(self, 'unique_data')

    def execute(self, context):
        export_path = bpy.path.abspath(self.directory) if self.directory else ""
        if not export_path or not os.path.isdir(export_path):
            self.report({'ERROR'}, f"Invalid export directory: {export_path!r}")
            return {'CANCELLED'}

        # Respect the user's scope: the current scene (optionally
        # further narrowed to the active selection). Avoid iterate
        # ``bpy.data.objects`` blindly -- that pulls in other scenes and
        # library-linked data.
        if self.selected_only:
            source_objects = [o for o in context.selected_objects
                              if o is not None and o.name in context.scene.objects]
        else:
            source_objects = list(context.scene.objects)

        if not source_objects:
            self.report({'WARNING'}, "No objects to export")
            return {'CANCELLED'}

        used_filenames = set()
        exported_data = set()  # data-block names already written (for unique_data)
        saved = 0
        skipped_existing = 0
        skipped_linked = 0
        skipped_dup_data = 0
        failures = 0

        wm = context.window_manager
        wm.progress_begin(0, len(source_objects))

        for i, obj in enumerate(source_objects):
            wm.progress_update(i)

            # Skip library-linked source data; writing a proxy would
            # produce a broken output. Track separately from failures so
            # the report is honest about what went wrong.
            if obj.library is not None:
                skipped_linked += 1
                continue

            # If unique_data is enabled, skip objects whose data was already
            # exported by a previous object in this run. This prevents
            # multi-user mesh data from being duplicated across files.
            if self.unique_data and obj.data is not None:
                data_key = obj.data.name
                if data_key in exported_data:
                    skipped_dup_data += 1
                    continue

            base = self._sanitize_filename(obj.name, fallback="object")
            filename = f"{base}.blend"
            # If sanitization collapses two names to the same base,
            # disambiguate with a numeric suffix.
            disambiguation = 1
            while filename in used_filenames:
                filename = f"{base}_{disambiguation:03d}.blend"
                disambiguation += 1
            used_filenames.add(filename)

            filepath = os.path.join(export_path, filename)

            if os.path.exists(filepath) and not self.overwrite:
                skipped_existing += 1
                continue

            # Build the set of data-blocks to write: the object itself
            # plus its data (mesh/curve/armature/light/...) when present.
            # ``libraries.write`` pulls in further dependencies (materials,
            # images, ...) automatically.
            datablocks = {obj}
            if obj.data is not None:
                datablocks.add(obj.data)

            try:
                bpy.data.libraries.write(
                    filepath,
                    datablocks,
                    path_remap=self.path_remap,
                    fake_user=False,
                    compress=self.compress,
                )
                saved += 1
                if obj.data is not None:
                    exported_data.add(obj.data.name)
            except Exception as e:
                failures += 1
                self.report({'WARNING'}, f"Could not export '{obj.name}': {e}")

        wm.progress_end()

        parts = [f"Saved {saved} file(s)"]
        if skipped_existing:
            parts.append(f"skipped {skipped_existing} existing")
        if skipped_linked:
            parts.append(f"skipped {skipped_linked} linked")
        if skipped_dup_data:
            parts.append(f"skipped {skipped_dup_data} dup data")
        if failures:
            parts.append(f"{failures} failed")
        self.report({'INFO'}, ", ".join(parts))
        return {'FINISHED'}
    #endregion
#endregion


#region MENU
def menu_func_export(self, context):
    self.layout.operator(ZENV_OT_SaveToSeparateBlends.bl_idname, text="All Objects to separate Blend Files")
#endregion


#region REG
classes = (
    ZENV_OT_SaveToSeparateBlends,
)


def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)


if __name__ == "__main__":
    register()
#endregion
