bl_info = {
    "name": 'EXPORT All Objects to FBX Files for UE4',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260418',
    "description": 'Save each object in the scene to its own FBX file with UE4-optimized settings',
    "status": 'working',
    "approved": True,
    "sort_priority": '2',
    "group": 'Export',
    "group_prefix": 'EXPORT',
    "description_short": 'batch export selected objects to separate FBX files',
    "description_long": """
EXPORT Objects to FBX Files 
batch export each object in the current scene to its own separate .fbx file. 
This is useful for:
- Creating individual assets for game engines like Unreal Engine
- Preparing objects for use in other 3D applications
- Exporting models with proper scale and orientation for external use
""",
    "location": 'File > Export > All Objects to FBX Files',
}

import bpy
import os
import re


# Characters invalid in filenames on Windows (superset of POSIX invalids).
_FBX_FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _sanitize_fbx_filename(name, fallback="object"):
    """Sanitize ``name`` into something safe to use as a filename stem."""
    cleaned = _FBX_FILENAME_INVALID_RE.sub('_', name).strip().rstrip('. ')
    if not cleaned:
        cleaned = fallback
    RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if cleaned.upper() in RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:200]


class ZENV_OT_save_to_separate_fbx_ue4(bpy.types.Operator):
    """Export each object in the scene to a separate FBX file with UE4-compatible settings.
    
    This operator creates individual .fbx files for each object in the current
    scene, with export settings optimized for Unreal Engine 4. Each file will
    contain only the exported object with proper scale and orientation.
    The files are saved in the same directory as the current blend file.
    
    Note:
        The blend file must be saved before using this operator.
        
    Warning:
        Existing files with the same names will be overwritten.
    """
    bl_idname = "zenv.save_to_separate_fbx_ue4"
    bl_label = "Save Objects to FBX Files for UE4 (.fbx)"
    bl_options = {'REGISTER', 'UNDO'}

    overwrite: bpy.props.BoolProperty(
        name="Overwrite Existing",
        description="Overwrite existing FBX files instead of skipping them",
        default=False,
    )

    def invoke(self, context, event):
        # Let the user see / flip the overwrite option before running.
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Exports to folder of current .blend file.", icon='INFO')
        layout.prop(self, 'overwrite')

    def execute(self, context):
        """Execute the FBX export operation.
        
        Creates a new .fbx file for each object in the scene with UE4-optimized
        settings.
        
        Args:
            context: Blender's context object
            
        Returns:
            {'FINISHED'} if successful, {'CANCELLED'} if the blend file isn't saved
        """
        basedir = os.path.dirname(bpy.data.filepath)

        if not basedir:
            self.report({'ERROR'}, "Blend file is not saved")
            return {'CANCELLED'}

        view_layer = context.view_layer

        # Store the current selection and active object so we can restore
        # the viewport state after we are done.
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

        used_filenames = set()
        exported = 0
        skipped_existing = 0
        failures = 0

        for obj in candidates:
            # Build a safe filename with the _SM suffix.
            base = _sanitize_fbx_filename(obj.name, fallback="object")
            filename = f"{base}_SM.fbx"
            disambiguation = 1
            while filename in used_filenames:
                filename = f"{base}_SM_{disambiguation:03d}.fbx"
                disambiguation += 1
            used_filenames.add(filename)

            filepath = os.path.join(basedir, filename)
            if os.path.exists(filepath) and not self.overwrite:
                skipped_existing += 1
                continue

            # Select only this object and make it active
            try:
                obj.select_set(True)
                view_layer.objects.active = obj
            except RuntimeError:
                # Object is not in this view layer; skip cleanly instead of
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
                    bake_anim=True,
                    bake_anim_use_all_bones=True,
                    bake_anim_use_nla_strips=False,
                    bake_anim_use_all_actions=True,
                    bake_anim_force_startend_keying=True,
                    bake_anim_step=1.0,
                    bake_anim_simplify_factor=1.0,
                    path_mode='RELATIVE',
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


def menu_func_export(self, context):
    self.layout.operator(ZENV_OT_save_to_separate_fbx_ue4.bl_idname, text="All Objects to FBX for Unreal Engine")


def register():
    bpy.utils.register_class(ZENV_OT_save_to_separate_fbx_ue4)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(ZENV_OT_save_to_separate_fbx_ue4)


if __name__ == "__main__":
    register()
