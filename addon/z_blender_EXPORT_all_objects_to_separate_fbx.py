"""
EXPORT Objects to FBX Files 
batch export each object in the current scene to its own separate .fbx file. 
This is useful for:
- Creating individual assets for game engines like Unreal Engine
- Preparing objects for use in other 3D applications
- Exporting models with proper scale and orientation for external use
"""

bl_info = {
    "name": "EXPORT All Objects to FBX Files for UE4",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "File > Export > All Objects to FBX Files",
    "description": "Save each object in the scene to its own FBX file with UE4-optimized settings",
}   

import bpy
import os


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

        # Store the current selection and active object
        original_selection = context.selected_objects[:]
        original_active = context.active_object

        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')

        for obj in bpy.data.objects:
            if obj.type not in {'MESH', 'ARMATURE', 'EMPTY'}:
                continue

            # Select only this object and make it active
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # Construct the filename and filepath with _SM suffix
            filename = f"{obj.name}_SM.fbx"
            filepath = os.path.join(basedir, filename)

            # Export FBX with UE4-optimized settings
            bpy.ops.export_scene.fbx(
                filepath=filepath,
                use_selection=True,
                use_active_collection=False,
                global_scale=1.0,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_NONE',
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

            # Deselect the object
            obj.select_set(False)

        # Restore original selection and active object
        for obj in original_selection:
            obj.select_set(True)
        context.view_layer.objects.active = original_active

        self.report({'INFO'}, f"Exported {len(bpy.data.objects)} objects to FBX")
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
