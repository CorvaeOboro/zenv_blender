bl_info = {
    "name": 'EXPORT All Objects to Separate Blend Files',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Save each object in the scene to its own blend file',

    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Export',
    "group_prefix": 'EXPORT',
    "description_short": 'batch export selected objects to separate blend files',
    "description_medium": 'batch export selected objects to separate blend files',
    "description_long": """
EXPORT Objects to Blend Files 
batch export each object in the current scene to its own separate .blend file. 
This is useful for:
- Creating individual asset files from a collection of objects
- Splitting large scenes into smaller, more manageable files
- Preparing objects for use in other projects
""",
    "location": 'File > Export > All Objects to Blend Files',
}

import bpy
import os
from bpy.props import BoolProperty, StringProperty


class ZENV_PG_export_properties(bpy.types.PropertyGroup):
    """Property group for export settings"""
    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Path to export blend files",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )
    current_object_index: bpy.props.IntProperty(
        name="Current Object Index",
        default=0
    )
    total_objects: bpy.props.IntProperty(
        name="Total Objects",
        default=0
    )
    is_running: bpy.props.BoolProperty(
        name="Is Export Running",
        default=False
    )
    files_saved: bpy.props.IntProperty(
        name="Files Saved",
        default=0
    )
    files_skipped: bpy.props.IntProperty(
        name="Files Skipped",
        default=0
    )


class ZENV_OT_SaveToSeparateBlends(bpy.types.Operator):
    """Export each object in the scene to a separate .blend file.
    Skips any existing files without overwriting."""
    bl_idname = "zenv.save_to_separate_blends"
    bl_label = "Save Objects to Separate Blend Files"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to export blend files to",
        subtype='DIR_PATH'
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        props = context.window_manager.zenv_export_main_operator
        
        # Only initialize if we're starting fresh
        if not props.is_running:
            props.export_path = self.directory
            props.current_object_index = 0
            props.total_objects = len(bpy.data.objects)
            props.is_running = True
            props.files_saved = 0
            props.files_skipped = 0
            self.report({'INFO'}, f"Starting export of {props.total_objects} objects...")
        
        return self.process_next_object(context)

    def process_next_object(self, context):
        props = context.window_manager.zenv_export_main_operator
        if not props.is_running:
            return {'FINISHED'}

        if props.current_object_index >= props.total_objects:
            props.is_running = False
            self.report({'INFO'}, f"Export complete: {props.files_saved} files saved, {props.files_skipped} files skipped")
            return {'FINISHED'}

        obj = bpy.data.objects[props.current_object_index]
        filepath = os.path.join(props.export_path, f"{obj.name}.blend")

        # Skip if file exists
        if os.path.exists(filepath):
            props.files_skipped += 1
            props.current_object_index += 1
            return self.process_next_object(context)

        return self.export_object(context, obj, filepath)

    def export_object(self, context, obj, filepath):
        # Store original scene
        original_scene = context.scene
        
        # Create a new scene
        new_scene = bpy.data.scenes.new(name=obj.name)
        
        # Create new collection for the object
        new_collection = bpy.data.collections.new(name=obj.name)
        new_scene.collection.children.link(new_collection)
        
        # Create a copy of the object and its data
        obj_copy = obj.copy()
        if obj.data:
            obj_copy.data = obj.data.copy()
        
        # Link the object to the new collection
        new_collection.objects.link(obj_copy)
        
        # Make the new scene active
        context.window.scene = new_scene
        
        # Save the blend file with only this object
        bpy.ops.wm.save_as_mainfile(
            filepath=filepath,
            copy=True,
            compress=True,
            relative_remap=True
        )
        
        # Clean up - proper order is important!
        # First unlink object from collection
        if obj_copy.name in new_collection.objects:
            new_collection.objects.unlink(obj_copy)
            
        # Then unlink collection from scene
        if new_collection.name in new_scene.collection.children:
            new_scene.collection.children.unlink(new_collection)
            
        # Now remove scene which removes its collections
        bpy.data.scenes.remove(new_scene, do_unlink=True)
        
        # Remove object data if it exists
        if obj_copy.data and obj_copy.data.users == 0:
            bpy.data.meshes.remove(obj_copy.data, do_unlink=True)
            
        # Finally remove the object
        if obj_copy.users == 0:
            bpy.data.objects.remove(obj_copy, do_unlink=True)
            
        # And the collection
        if new_collection.users == 0:
            bpy.data.collections.remove(new_collection, do_unlink=True)
        
        # Restore original scene
        context.window.scene = original_scene
        
        props = context.window_manager.zenv_export_main_operator
        props.current_object_index += 1
        props.files_saved += 1
        
        return self.process_next_object(context)


def menu_func_export(self, context):
    self.layout.operator(ZENV_OT_SaveToSeparateBlends.bl_idname, text="All Objects to separate Blend Files")


classes = (
    ZENV_PG_export_properties,
    ZENV_OT_SaveToSeparateBlends,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    # Register window manager properties
    bpy.types.WindowManager.zenv_export_main_operator = bpy.props.PointerProperty(
        type=ZENV_PG_export_properties)

def unregister():
    # Unregister window manager properties
    if hasattr(bpy.types.WindowManager, "zenv_export_main_operator"):
        del bpy.types.WindowManager.zenv_export_main_operator
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)


if __name__ == "__main__":
    register()
