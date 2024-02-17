
bl_info = {
    "name": "EXPORT Save Objects to Separate Blend Files",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "File > Export > Save Objects to Blend Files",
    "description": "Save each object in the scene to its own blend file",
}   

import bpy
import os

class OBJECT_OT_save_to_separate_blends(bpy.types.Operator):
    bl_idname = "export.save_to_separate_blends"
    bl_label = "Save Objects to Separate Blend Files"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        basedir = os.path.dirname(bpy.data.filepath)

        if not basedir:
            self.report({'ERROR'}, "Blend file is not saved")
            return {'CANCELLED'}

        # Save the original scene
        original_scene = context.scene

        for obj in bpy.data.objects:
            # Create a new scene
            new_scene = bpy.data.scenes.new(name=obj.name)

            # Set the new scene as the active scene
            bpy.context.window.scene = new_scene

            # Copy the object
            obj_copy = obj.copy()
            obj_copy.data = obj.data.copy()

            # Link the copied object to the new scene
            new_scene.collection.objects.link(obj_copy)

            # Construct the filename
            filename = f"{obj.name}.blend"
            filepath = os.path.join(basedir, filename)

            # Save the new scene with the copied object in its own blend file
            bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True, compress=False)

        # Restore the original scene
        bpy.context.window.scene = original_scene

        # Clean up: Remove the created scenes
        for scn in bpy.data.scenes:
            if scn != original_scene:
                bpy.data.scenes.remove(scn)

        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(OBJECT_OT_save_to_separate_blends.bl_idname, text="Save Objects to Blend Files")


def register():
    bpy.utils.register_class(OBJECT_OT_save_to_separate_blends)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_save_to_separate_blends)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
