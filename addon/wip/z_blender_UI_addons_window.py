# UI ADDONS WINDOW
# Customizable UI panel with dynamic operator buttons

bl_info = {
    "name": "UI Addon Window",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Customizable UI panel with dynamic operator buttons"
}

import bpy
import json
import os
import logging
from bpy.props import StringProperty, BoolProperty, EnumProperty, CollectionProperty, IntProperty
from bpy.types import Panel, Operator, PropertyGroup, UIList

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class UIUtils:
    """Utility functions for UI management"""
    
    @staticmethod
    def get_settings_path():
        """Get path to settings file"""
        return os.path.join(
            bpy.utils.user_resource('SCRIPTS'),
            "presets",
            "zenv_ui_settings.json"
        )
    
    @staticmethod
    def load_settings():
        """Load settings from file"""
        settings_path = UIUtils.get_settings_path()
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Settings loaded from {settings_path}")
                    return data
            except Exception as e:
                logger.error(f"Error loading settings: {str(e)}")
                return []
        logger.info("No settings file found, using defaults")
        return []
    
    @staticmethod
    def save_settings(buttons):
        """Save settings to file"""
        settings_path = UIUtils.get_settings_path()
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        try:
            with open(settings_path, 'w') as f:
                json.dump(buttons, f, indent=4)
            logger.info(f"Settings saved to {settings_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
            return False
    
    @staticmethod
    def get_operator_categories():
        """Get list of operator categories"""
        categories = set()
        for op in bpy.types.Operator.__subclasses__():
            if hasattr(op, 'bl_idname'):
                categories.add(op.bl_idname.split('.')[0])
        return sorted(list(categories))
    
    @staticmethod
    def get_operators_in_category(category):
        """Get list of operators in category"""
        operators = []
        for op in bpy.types.Operator.__subclasses__():
            if hasattr(op, 'bl_idname') and op.bl_idname.startswith(category + '.'):
                operators.append((
                    op.bl_idname,
                    op.bl_label if hasattr(op, 'bl_label') else op.bl_idname,
                    op.__doc__ if op.__doc__ else ""
                ))
        return sorted(operators)
    
    @staticmethod
    def validate_operator(operator_id):
        """Validate if operator exists"""
        try:
            op = operator_id.split('.')
            return hasattr(getattr(bpy.ops, op[0]), op[1])
        except:
            return False

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_UIAddonButtonItem(PropertyGroup):
    """Properties for a UI button"""
    operator: StringProperty(
        name="Operator",
        description="Operator to call",
        default=""
    )
    
    category: StringProperty(
        name="Category",
        description="Button category",
        default=""
    )
    
    show_label: BoolProperty(
        name="Show Label",
        description="Show operator label instead of name",
        default=True
    )
    
    custom_label: StringProperty(
        name="Custom Label",
        description="Custom label for the button",
        default=""
    )
    
    icon: StringProperty(
        name="Icon",
        description="Icon to display with the button",
        default="NONE"
    )
    
    tooltip: StringProperty(
        name="Tooltip",
        description="Custom tooltip for the button",
        default=""
    )

# ------------------------------------------------------------------------
#    UI List
# ------------------------------------------------------------------------

class ZENV_UL_UIAddonButtonList(UIList):
    """List of UI buttons"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "operator", text="")
            row.prop(item, "category", text="")
            row.prop(item, "show_label", text="", icon='SHORTDISPLAY')
            if item.show_label:
                row.prop(item, "custom_label", text="")
            row.prop(item, "icon", text="", icon=item.icon)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.operator)

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_UIAddonAddButton(Operator):
    """Add a new UI button"""
    bl_idname = "zenv.add_button"
    bl_label = "Add Button"
    bl_description = "Add a new button to the UI panel"
    bl_options = {'REGISTER', 'UNDO'}
    
    operator: StringProperty(
        name="Operator",
        description="Operator to call",
        default=""
    )
    
    category: StringProperty(
        name="Category",
        description="Button category",
        default=""
    )
    
    def execute(self, context):
        if not UIUtils.validate_operator(self.operator):
            self.report({'ERROR'}, f"Invalid operator: {self.operator}")
            return {'CANCELLED'}
            
        item = context.scene.zenv_ui_buttons.add()
        item.operator = self.operator
        item.category = self.category
        UIUtils.save_settings([{
            'operator': btn.operator,
            'category': btn.category,
            'show_label': btn.show_label,
            'custom_label': btn.custom_label,
            'icon': btn.icon,
            'tooltip': btn.tooltip
        } for btn in context.scene.zenv_ui_buttons])
        return {'FINISHED'}

class ZENV_OT_UIAddonRemoveButton(Operator):
    """Remove a UI button"""
    bl_idname = "zenv.remove_button"
    bl_label = "Remove Button"
    bl_description = "Remove selected button from the UI panel"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.scene.zenv_ui_buttons
    
    def execute(self, context):
        buttons = context.scene.zenv_ui_buttons
        index = context.scene.zenv_ui_active_button
        
        if 0 <= index < len(buttons):
            buttons.remove(index)
            context.scene.zenv_ui_active_button = min(
                max(0, index - 1),
                len(buttons) - 1
            )
            UIUtils.save_settings([{
                'operator': btn.operator,
                'category': btn.category,
                'show_label': btn.show_label,
                'custom_label': btn.custom_label,
                'icon': btn.icon,
                'tooltip': btn.tooltip
            } for btn in buttons])
            
        return {'FINISHED'}

class ZENV_OT_UIAddonMoveButton(Operator):
    """Move a UI button up or down"""
    bl_idname = "zenv.move_button"
    bl_label = "Move Button"
    bl_description = "Move button up or down in the list"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: EnumProperty(
        name="Direction",
        items=[
            ('UP', "Up", "Move button up"),
            ('DOWN', "Down", "Move button down")
        ],
        default='UP'
    )
    
    @classmethod
    def poll(cls, context):
        return context.scene.zenv_ui_buttons
    
    def execute(self, context):
        buttons = context.scene.zenv_ui_buttons
        index = context.scene.zenv_ui_active_button
        
        if 0 <= index < len(buttons):
            if self.direction == 'UP' and index > 0:
                buttons.move(index, index - 1)
                context.scene.zenv_ui_active_button -= 1
            elif self.direction == 'DOWN' and index < len(buttons) - 1:
                buttons.move(index, index + 1)
                context.scene.zenv_ui_active_button += 1
            
            UIUtils.save_settings([{
                'operator': btn.operator,
                'category': btn.category,
                'show_label': btn.show_label,
                'custom_label': btn.custom_label,
                'icon': btn.icon,
                'tooltip': btn.tooltip
            } for btn in buttons])
                
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panels
# ------------------------------------------------------------------------

class ZENV_PT_UIAddonButtonEditor(Panel):
    """Panel for editing UI buttons"""
    bl_idname = "ZENV_PT_button_editor"
    bl_label = "UI Button Editor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Button list
        row = layout.row()
        row.template_list(
            "ZENV_UL_UIAddonButtonList",
            "buttons",
            scene,
            "zenv_ui_buttons",
            scene,
            "zenv_ui_active_button"
        )
        
        # List operations
        col = row.column(align=True)
        col.operator("zenv.add_button", text="", icon='ADD')
        col.operator("zenv.remove_button", text="", icon='REMOVE')
        col.separator()
        col.operator("zenv.move_button", text="", icon='TRIA_UP').direction = 'UP'
        col.operator("zenv.move_button", text="", icon='TRIA_DOWN').direction = 'DOWN'
        
        # Button settings
        if len(scene.zenv_ui_buttons) > 0:
            item = scene.zenv_ui_buttons[scene.zenv_ui_active_button]
            box = layout.box()
            box.label(text="Button Settings")
            col = box.column(align=True)
            col.prop(item, "operator")
            col.prop(item, "category")
            col.prop(item, "show_label")
            if item.show_label:
                col.prop(item, "custom_label")
            col.prop(item, "icon")
            col.prop(item, "tooltip")

class ZENV_PT_UIAddonDynamicUI(Panel):
    """Dynamic UI panel with custom buttons"""
    bl_idname = "ZENV_PT_dynamic_ui"
    bl_label = "UI Dynamic Interface"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        buttons = context.scene.zenv_ui_buttons
        
        if not buttons:
            layout.label(text="No buttons configured")
            layout.operator("zenv.add_button", text="Add Button", icon='ADD')
            return
        
        # Group buttons by category
        categories = {}
        for item in buttons:
            if item.category not in categories:
                categories[item.category] = []
            categories[item.category].append(item)
        
        # Draw buttons by category
        for category in sorted(categories.keys()):
            box = layout.box()
            box.label(text=category if category else "Uncategorized")
            for item in categories[category]:
                if UIUtils.validate_operator(item.operator):
                    op = box.operator(
                        item.operator,
                        text=item.custom_label if item.show_label and item.custom_label else "",
                        icon=item.icon if item.icon != "NONE" else 'NONE'
                    )
                    if item.tooltip:
                        op.description = item.tooltip
                else:
                    row = box.row()
                    row.alert = True
                    row.label(text=f"Invalid: {item.operator}", icon='ERROR')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_UIAddonButtonItem,
    ZENV_UL_UIAddonButtonList,
    ZENV_OT_UIAddonAddButton,
    ZENV_OT_UIAddonRemoveButton,
    ZENV_OT_UIAddonMoveButton,
    ZENV_PT_UIAddonButtonEditor,
    ZENV_PT_UIAddonDynamicUI,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    
    bpy.types.Scene.zenv_ui_buttons = CollectionProperty(type=ZENV_PG_UIAddonButtonItem)
    bpy.types.Scene.zenv_ui_active_button = IntProperty(default=0)
    
    # Load saved settings
    buttons = UIUtils.load_settings()
    if buttons:
        for button_data in buttons:
            item = bpy.context.scene.zenv_ui_buttons.add()
            for key, value in button_data.items():
                setattr(item, key, value)

def unregister():
    # Save current settings
    if hasattr(bpy.context.scene, "zenv_ui_buttons"):
        UIUtils.save_settings([{
            'operator': btn.operator,
            'category': btn.category,
            'show_label': btn.show_label,
            'custom_label': btn.custom_label,
            'icon': btn.icon,
            'tooltip': btn.tooltip
        } for btn in bpy.context.scene.zenv_ui_buttons])
    
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    
    del bpy.types.Scene.zenv_ui_buttons
    del bpy.types.Scene.zenv_ui_active_button

if __name__ == "__main__":
    register()