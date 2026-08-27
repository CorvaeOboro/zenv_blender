#region META
bl_info = {
    "name": 'MAT Rename Material Suffix',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Add or remove customizable prefix and suffix to material names',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 40,
    "tags": ['material', 'rename', 'prefix', 'suffix', 'affix', 'name'],
    "description_short": 'add or remove prefix or suffix on materials',
    "description_medium": 'Provides two operators (Add Affix and Remove Affix) that add or remove a configurable prefix or suffix to/from material names. Supports both prefix and suffix modes, and can apply to all materials in the file or the active object materials. Shared logic via a mixin class.',
    "description_long": """
MATERIAL RENAME AFFIX
 prefix and suffix addition or removal for material names
""",
    "image_overview": 'zenv_blender_MAT_rename_material_suffix.png',
    "addon_image": 'zenv_blender_MAT_rename_material_suffix.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Panel, Operator, PropertyGroup
#endregion


#region MIXIN
# Mixin class with shared logic for add/remove affix operators.
# Not registered with Blender.

class ZENV_MaterialRename_Mixin:
    """Shared functionality for material renaming operators"""

    @staticmethod
    def apply_affix_to_material(material, affix_type, operation, affix):
        """Add or remove an affix (prefix/suffix) on a single material.

        Args:
            material: the material datablock to modify.
            affix_type: either ``"prefix"`` or ``"suffix"``.
            operation: either ``"add"`` or ``"remove"``.
            affix: the affix string to add or remove.

        Returns:
            True if the material name was changed, False otherwise.
        """
        if not material:
            return False

        name = material.name

        if affix_type == "prefix":
            if operation == "add" and not name.startswith(affix):
                material.name = affix + name
                return True
            elif operation == "remove" and name.startswith(affix):
                material.name = name[len(affix):]
                return True
        elif affix_type == "suffix":
            if operation == "add" and not name.endswith(affix):
                material.name = name + affix
                return True
            elif operation == "remove" and name.endswith(affix):
                material.name = name[:-len(affix)]
                return True

        return False

    def process_materials(self, context, operation="add"):
        """Process materials based on settings"""
        settings = context.scene.zenv_rename_props
        processed = 0

        # Affix string required otherwise the "remove" phase reduces
        # all names to empty string.
        if self.affix_type == "prefix":
            affix = settings.prefix
        elif self.affix_type == "suffix":
            affix = settings.suffix
        else:
            self.report({'WARNING'}, f"Invalid affix type: {self.affix_type}")
            return 0

        if not affix:
            self.report({'WARNING'}, f"{self.affix_type.capitalize()} is empty; nothing to do.")
            return 0

        # Process materials based on scope
        if settings.apply_to_all:
            for material in bpy.data.materials:
                if self.apply_affix_to_material(material, self.affix_type,
                                                operation, affix):
                    processed += 1
        else:
            obj = context.active_object
            if obj and obj.type == 'MESH':
                for slot in obj.material_slots:
                    if self.apply_affix_to_material(slot.material,
                                                    self.affix_type,
                                                    operation, affix):
                        processed += 1

        return processed
#endregion


#region OP
# Operators that add and remove prefix/suffix affixes on materials.

class ZENV_OT_AddAffix(Operator, ZENV_MaterialRename_Mixin):
    """Add prefix or suffix to material names"""
    bl_idname = "zenv.add_material_affix"
    bl_label = "Add"
    bl_description = "Add prefix or suffix to material names"
    bl_options = {'REGISTER', 'UNDO'}

    affix_type: EnumProperty(
        name="Affix Type",
        description="Whether to add a prefix or suffix",
        items=[
            ('prefix', "Prefix", "Add/remove a prefix"),
            ('suffix', "Suffix", "Add/remove a suffix"),
        ],
        default='prefix'
    )

    def execute(self, context):
        try:
            processed = self.process_materials(context, "add")
            self.report({'INFO'}, f"Added {self.affix_type} to {processed} materials")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error adding affix: {str(e)}")
            return {'CANCELLED'}


class ZENV_OT_RemoveAffix(Operator, ZENV_MaterialRename_Mixin):
    """Remove prefix or suffix from material names"""
    bl_idname = "zenv.remove_material_affix"
    bl_label = "Remove"
    bl_description = "Remove prefix or suffix from material names"
    bl_options = {'REGISTER', 'UNDO'}

    affix_type: EnumProperty(
        name="Affix Type",
        description="Whether to remove a prefix or suffix",
        items=[
            ('prefix', "Prefix", "Add/remove a prefix"),
            ('suffix', "Suffix", "Add/remove a suffix"),
        ],
        default='prefix'
    )

    def execute(self, context):
        try:
            processed = self.process_materials(context, "remove")
            self.report({'INFO'}, f"Removed {self.affix_type} from {processed} materials")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error removing affix: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PROPS
# Property group for material affix settings, registered on the Scene.

class ZENV_PG_RenameByMaterialProps(PropertyGroup):
    """Properties for material renaming"""
    prefix: StringProperty(
        name="Prefix",
        description="Prefix to add to material names",
        default="d_"
    )
    suffix: StringProperty(
        name="Suffix",
        description="Suffix to add to material names",
        default="_MI"
    )
    apply_to_all: BoolProperty(
        name="Apply to All Materials",
        description="Apply changes to all materials in the scene instead of the selected object",
        default=False
    )
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_MaterialRenameSuffix(Panel):
    """Panel for material name prefix/suffix operations"""
    bl_label = "MAT Rename Affix"
    bl_idname = "ZENV_PT_material_rename_suffix"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_rename_props

        # Prefix section
        box = layout.box()
        box.label(text="Prefix Operations")
        row = box.row()
        row.prop(props, "prefix", text="")
        row = box.row(align=True)
        op = row.operator("zenv.add_material_affix", text="Add")
        op.affix_type = 'prefix'
        op = row.operator("zenv.remove_material_affix", text="Remove")
        op.affix_type = 'prefix'

        # Suffix section
        box = layout.box()
        box.label(text="Suffix Operations")
        row = box.row()
        row.prop(props, "suffix", text="")
        row = box.row(align=True)
        op = row.operator("zenv.add_material_affix", text="Add")
        op.affix_type = 'suffix'
        op = row.operator("zenv.remove_material_affix", text="Remove")
        op.affix_type = 'suffix'

        # Settings
        box = layout.box()
        box.label(text="Settings")
        box.prop(props, "apply_to_all")
#endregion


#region REG
classes = (
    ZENV_PG_RenameByMaterialProps,
    ZENV_OT_AddAffix,
    ZENV_OT_RemoveAffix,
    ZENV_PT_MaterialRenameSuffix,
)


def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_rename_props = bpy.props.PointerProperty(
        type=ZENV_PG_RenameByMaterialProps
    )


def unregister():
    if hasattr(bpy.types.Scene, "zenv_rename_props"):
        del bpy.types.Scene.zenv_rename_props
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)


if __name__ == "__main__":
    register()
#endregion
