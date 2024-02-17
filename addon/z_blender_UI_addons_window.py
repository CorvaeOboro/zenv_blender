bl_info = {
    "name": "UI addon window ",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " addon window ui buttons  ",
}
#//==================================================================================================
import bpy
import json
import os
# Path to store the settings file
settings_file = os.path.join(bpy.utils.user_resource('SCRIPTS'), "presets", "addon_settings.json")

# Global storage for dynamic operator names
dynamic_operators = []
#//========================================================================================================

def save_settings():
    global dynamic_operators
    with open(settings_file, 'w') as outfile:
        json.dump(dynamic_operators, outfile)

def load_settings():
    global dynamic_operators
    if os.path.isfile(settings_file):
        with open(settings_file, 'r') as infile:
            dynamic_operators = json.load(infile)

# Operator for adding a new button
class AddButtonOperator(bpy.types.Operator):
    bl_idname = "wm.add_button_operator"
    bl_label = "Add Button"
    operator_name: bpy.props.StringProperty(name="Operator Name")
    category: bpy.props.StringProperty(name="Category")

    def execute(self, context):
        global dynamic_operators
        dynamic_operators.append({"operator": self.operator_name, "category": self.category})
        save_settings()
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}

# Operator for saving settings manually
class SaveSettingsOperator(bpy.types.Operator):
    bl_idname = "wm.save_settings_operator"
    bl_label = "Save Settings"
    
    def execute(self, context):
        save_settings()
        self.report({'INFO'}, "Settings saved")
        return {'FINISHED'}

# ZENV_UI Panel
class ZENV_UI_Panel(bpy.types.Panel):
    bl_label = "ZENV_UI"
    bl_idname = "ZENV_UI_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV_UI'

    def draw(self, context):
        load_settings()
        layout = self.layout

        # Predefined buttons
        view_box = layout.box()
        view_box.label(text="VIEW")
        view_box.operator("zenv.set_camera_view", text="Set Camera View")

        mesh_box = layout.box()
        mesh_box.label(text="MESH")
        mesh_box.operator("zenv.mesh_mat_remove", text="MAT Remove")

        # Dynamic buttons
        dynamic_categories = set([item['category'] for item in dynamic_operators])
        for category in dynamic_categories:
            box = layout.box()
            box.label(text=category)
            for item in dynamic_operators:
                if item['category'] == category:
                    box.operator(item['operator'])

        # Input fields and button to add new operator
        row = layout.row()
        row.prop(context.window_manager, "new_operator_name", text="")
        row.prop(context.window_manager, "new_operator_category", text="")
        row.operator("wm.add_button_operator")

        # Button to save settings manually
        layout.operator("wm.save_settings_operator")

def register():
    bpy.types.WindowManager.new_operator_name = bpy.props.StringProperty(name="New Operator Name")
    bpy.types.WindowManager.new_operator_category = bpy.props.StringProperty(name="New Operator Category")
    bpy.utils.register_class(AddButtonOperator)
    bpy.utils.register_class(SaveSettingsOperator)
    bpy.utils.register_class(ZENV_UI_Panel)
    load_settings()

def unregister():
    del bpy.types.WindowManager.new_operator_name
    del bpy.types.WindowManager.new_operator_category
    bpy.utils.unregister_class(AddButtonOperator)
    bpy.utils.unregister_class(SaveSettingsOperator)
    bpy.utils.unregister_class(ZENV_UI_Panel)

if __name__ == "__main__":
    register()