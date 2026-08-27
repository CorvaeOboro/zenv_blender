#region META
bl_info = {
    "name": 'EXPORT All Objects to FBX Files for UE4',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Save each object in the scene to its own FBX file with UE4-tuned settings',
    "status": 'working',
    "approved": True,
    "group": 'Export',
    "group_prefix": 'EXPORT',
    "group_order": 50,
    "addon_order": 20,
    "tags": ['export', 'batch', 'fbx', 'ue4', 'unreal', 'asset'],
    "description_short": 'batch export selected objects to separate FBX files',
    "description_medium": 'Batch-export each object in the current scene (or current selection) to its own standalone .fbx file with Unreal Engine 4-tuned settings via bpy.ops.export_scene.fbx. Handles filename sanitization, collision disambiguation, overwrite control, suffix customization, animation baking, and path remapping options.',
    "description_long": """
EXPORT Objects to FBX Files
batch export each object in the current scene to its own separate .fbx file.
This is useful for:
- Creating individual assets for game engines like Unreal Engine
- Preparing objects for use in other 3D applications
- Exporting models with proper scale and orientation for external use
""",
    "image_overview": 'zenv_blender_EXPORT_all_objects_to_separate_fbx.png',
    "addon_image": 'zenv_blender_EXPORT_all_objects_to_separate_fbx.png',
    "location": 'File > Export > All Objects to FBX Files',
}
#endregion

#region IMPORT
import bpy
import os
import re
#endregion

#region CONSTS
# Characters invalid in filenames on Windows (superset of POSIX invalids).
_FBX_FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

# DOS reserved device names that cannot be used as filenames on Windows.
_RESERVED_DOS_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
#endregion


#region OP
# FBX export operator - batch-writes each object to its own .fbx file with
# UE4-tuned settings via bpy.ops.export_scene.fbx.

class ZENV_OT_SaveToSeparateFbxUE4(bpy.types.Operator):
    """Export each object in the scene to a separate FBX file with UE4-compatible settings.

    This operator creates individual .fbx files for each object in the current
    scene, with export settings tuned for Unreal Engine 4. Each file will
    contain only the exported object with proper scale and orientation.

    If no export directory is chosen, files are saved in the same
        directory as the current blend file (which must be saved first).

    Warning:
        Existing files with the same names will be overwritten if the
        overwrite option is enabled.
    """
    bl_idname = "zenv.save_to_separate_fbx_ue4"
    bl_label = "Save Objects to FBX Files for UE4 (.fbx)"
    bl_options = {'REGISTER', 'UNDO'}

    #region PROPS
    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to export FBX files to (defaults to the blend file's directory)",
        subtype='DIR_PATH',
        default="",
    )
    overwrite: bpy.props.BoolProperty(
        name="Overwrite Existing",
        description="Overwrite existing FBX files instead of skipping them",
        default=False,
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Only export currently selected objects instead of every eligible object in the scene",
        default=False,
    )
    suffix: bpy.props.StringProperty(
        name="Filename Suffix",
        description="Suffix appended to each filename before the .fbx extension (e.g. _SM for Static Mesh, _SK for Skeletal Mesh)",
        default="_SM",
    )
    bake_animation: bpy.props.BoolProperty(
        name="Bake Animation",
        description="Bake animation into the exported FBX files (disable for static meshes to save time)",
        default=True,
    )
    path_mode: bpy.props.EnumProperty(
        name="Path Mode",
        description="How to remap file paths in the exported FBX files",
        items=[
            ('AUTO', "Auto", "Use relative paths if the file is in a subdirectory of the current blend, absolute otherwise"),
            ('ABSOLUTE', "Absolute", "Always use absolute paths"),
            ('RELATIVE', "Relative", "Always use relative paths"),
            ('MATCH', "Match", "Match the path mode of the linked file"),
            ('STRIP', "Strip", "Strip all external file paths (textures, etc.)"),
            ('COPY', "Copy", "Copy external files to the export directory"),
        ],
        default='RELATIVE',
    )
    #endregion

    #region SANITIZE
    @classmethod
    def _sanitize_filename(cls, name, fallback="object"):
        """Sanitize ``name`` into something safe to use as a filename stem."""
        cleaned = _FBX_FILENAME_INVALID_RE.sub('_', name).strip().rstrip('. ')
        if not cleaned:
            cleaned = fallback
        if cleaned.upper() in _RESERVED_DOS_NAMES:
            cleaned = f"_{cleaned}"
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
        layout.prop(self, 'suffix')
        layout.prop(self, 'bake_animation')
        layout.prop(self, 'path_mode')

    def execute(self, context):
        """Execute the FBX export operation.

        Creates a new .fbx file for each object in the scene with UE4-tuned
        settings.

        Args:
            context: Blender's context object

        Returns:
            {'FINISHED'} if successful, {'CANCELLED'} if the directory is invalid
        """
        # Use the chosen directory, or fall back to the blend file's directory.
        export_dir = (
            bpy.path.abspath(self.directory) if self.directory
            else os.path.dirname(bpy.data.filepath)
        )

        if not export_dir or not os.path.isdir(export_dir):
            self.report({'ERROR'}, f"Invalid export directory: {export_dir!r}")
            return {'CANCELLED'}

        view_layer = context.view_layer

        # Store the current selection and active object so the viewport
        # state can be restored afterwards.
        original_selection = [o for o in context.selected_objects if o]
        original_active = view_layer.objects.active

        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')

        # Iterate the active view layer only; that guarantees ``select_set``
        # will succeed. Objects from other scenes, hidden collections, or
        # other view layers are left alone.
        candidates = [o for o in view_layer.objects
                      if o.type in {'MESH', 'ARMATURE', 'EMPTY'}
                      and o.library is None]

        # If selected_only is enabled, further narrow to the original selection.
        if self.selected_only:
            selected_names = {o.name for o in original_selection}
            candidates = [o for o in candidates if o.name in selected_names]

        used_filenames = set()
        exported = 0
        skipped_existing = 0
        failures = 0

        wm = context.window_manager
        wm.progress_begin(0, len(candidates))

        for i, obj in enumerate(candidates):
            wm.progress_update(i)

            # Build a safe filename with the configurable suffix.
            base = self._sanitize_filename(obj.name, fallback="object")
            suffix = self.suffix
            filename = f"{base}{suffix}.fbx"
            disambiguation = 1
            while filename in used_filenames:
                filename = f"{base}{suffix}_{disambiguation:03d}.fbx"
                disambiguation += 1
            used_filenames.add(filename)

            filepath = os.path.join(export_dir, filename)
            if os.path.exists(filepath) and not self.overwrite:
                skipped_existing += 1
                continue

            # Select only this object and make it active
            try:
                obj.select_set(True)
                view_layer.objects.active = obj
            except RuntimeError:
                # Object is not in this view layer; skip instead of
                # failing the whole batch.
                failures += 1
                continue

            try:
                # Export FBX with UE-friendly settings. ``FBX_SCALE_ALL``
                # bakes the unit scale into the exported transform so the
                # resulting file lands at the expected scale in Unreal
                # regardless of what the Blender unit scale is set to.
                bpy.ops.export_scene.fbx(
                    filepath=filepath,
                    use_selection=True,
                    use_active_collection=False,
                    global_scale=1.0,
                    apply_unit_scale=True,
                    apply_scale_options='FBX_SCALE_ALL',
                    bake_space_transform=False,
                    object_types={'MESH', 'ARMATURE', 'EMPTY'},
                    use_mesh_modifiers=True,
                    mesh_smooth_type='FACE',
                    use_mesh_edges=False,
                    use_tspace=False,
                    use_custom_props=False,
                    add_leaf_bones=False,
                    primary_bone_axis='Y',
                    secondary_bone_axis='X',
                    use_armature_deform_only=True,
                    armature_nodetype='NULL',
                    bake_anim=self.bake_animation,
                    bake_anim_use_all_bones=True,
                    bake_anim_use_nla_strips=False,
                    bake_anim_use_all_actions=True,
                    bake_anim_force_startend_keying=True,
                    bake_anim_step=1.0,
                    bake_anim_simplify_factor=1.0,
                    path_mode=self.path_mode,
                    embed_textures=False,
                    batch_mode='OFF',
                    use_batch_own_dir=True,
                    axis_forward='-Z',
                    axis_up='Y'
                )
                exported += 1
            except Exception as e:
                failures += 1
                self.report({'WARNING'}, f"Failed to export '{obj.name}': {e}")
            finally:
                try:
                    obj.select_set(False)
                except RuntimeError:
                    pass

        wm.progress_end()

        # Restore original selection and active object
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            if obj and obj.name in view_layer.objects:
                try:
                    obj.select_set(True)
                except RuntimeError:
                    pass
        if original_active is not None and original_active.name in view_layer.objects:
            view_layer.objects.active = original_active

        parts = [f"Exported {exported} FBX file(s)"]
        if skipped_existing:
            parts.append(f"skipped {skipped_existing} existing")
        if failures:
            parts.append(f"{failures} failed")
        self.report({'INFO'}, ", ".join(parts))
        return {'FINISHED'}
    #endregion
#endregion


#region MENU
def menu_func_export(self, context):
    self.layout.operator(ZENV_OT_SaveToSeparateFbxUE4.bl_idname, text="All Objects to FBX for Unreal Engine")
#endregion


#region REG
classes = (
    ZENV_OT_SaveToSeparateFbxUE4,
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
