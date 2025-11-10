bl_info = {
    "name": 'MAT Rename Material Suffix',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Add or remove customizable prefix and suffix to material names',
    "status": 'working',
    "approved": True,
    "sort_priority": '20',
    "group": 'Material',
    "group_prefix": 'MAT',
    "description_short": 'add or remove prefix or suffix on materials',
    "description_long": """
MATERIAL RENAME AFFIX
 prefix and suffix addition or removal for material names
""",
    "location": 'View3D > ZENV',
}

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup

class ZENV_MaterialRename_Mixin:
    """Shared functionality for material renaming operators"""
    
    def process_materials(self, context, operation="add"):
        """Process materials based on settings"""
        settings = context.scene.zenv_rename_props
        processed = 0
        
        def process_material(material):
            if not material:
                return False
                
            name = material.name
            changed = False
            
            if self.type == "prefix":
                if operation == "add" and not name.startswith(settings.prefix):
                    material.name = settings.prefix + name
                    changed = True
                elif operation == "remove" and name.startswith(settings.prefix):
                    material.name = name[len(settings.prefix):]
                    changed = True
            else:  # suffix
                if operation == "add" and not name.endswith(settings.suffix):
                    material.name = name + settings.suffix
                    changed = True
                elif operation == "remove" and name.endswith(settings.suffix):
                    material.name = name[:-len(settings.suffix)]
                    changed = True
                    
            return changed
        
        # Process materials based on scope
        if settings.apply_to_all:
            for material in bpy.data.materials:
                if process_material(material):
                    processed += 1
        else:
            obj = context.active_object
            if obj and obj.type == 'MESH':
                for slot in obj.material_slots:
                    if process_material(slot.material):
                        processed += 1
                        
        return processed

class ZENV_OT_AddAffix(Operator, ZENV_MaterialRename_Mixin):
    """Add prefix or suffix to material names"""
    bl_idname = "zenv.add_material_affix"
    bl_label = "Add"
    bl_description = "Add prefix or suffix to material names"
    bl_options = {'REGISTER', 'UNDO'}
    
    type: StringProperty()  # "prefix" or "suffix"
    
    def execute(self, context):
        processed = self.process_materials(context, "add")
        self.report({'INFO'}, f"Added {self.type} to {processed} materials")
        return {'FINISHED'}

class ZENV_OT_RemoveAffix(Operator, ZENV_MaterialRename_Mixin):
    """Remove prefix or suffix from material names"""
    bl_idname = "zenv.remove_material_affix"
    bl_label = "Remove"
    bl_description = "Remove prefix or suffix from material names"
    bl_options = {'REGISTER', 'UNDO'}
    
    type: StringProperty()  # "prefix" or "suffix"
    
    def execute(self, context):
        processed = self.process_materials(context, "remove")
        self.report({'INFO'}, f"Removed {self.type} from {processed} materials")
        return {'FINISHED'}

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
        description="Apply changes to all materials in the scene instead of just selected object",
        default=False
    )
    remove_mi: BoolProperty(
        name="Remove _MI",
        description="Remove _MI suffix from material names",
        default=False
    )

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
        op.type = "prefix"
        op = row.operator("zenv.remove_material_affix", text="Remove")
        op.type = "prefix"
        
        # Suffix section
        box = layout.box()
        box.label(text="Suffix Operations")
        row = box.row()
        row.prop(props, "suffix", text="")
        row = box.row(align=True)
        op = row.operator("zenv.add_material_affix", text="Add")
        op.type = "suffix"
        op = row.operator("zenv.remove_material_affix", text="Remove")
        op.type = "suffix"
        
        # Settings
        box = layout.box()
        box.label(text="Settings")
        box.prop(props, "apply_to_all")
        box.prop(props, "remove_mi")

def register():
    # Register classes in the correct order
    bpy.utils.register_class(ZENV_PG_RenameByMaterialProps)
    bpy.utils.register_class(ZENV_OT_AddAffix)
    bpy.utils.register_class(ZENV_OT_RemoveAffix)
    bpy.utils.register_class(ZENV_PT_MaterialRenameSuffix)
    # Create the scene property
    bpy.types.Scene.zenv_rename_props = bpy.props.PointerProperty(type=ZENV_PG_RenameByMaterialProps)

def unregister():
    # Remove the scene property first
    if hasattr(bpy.types.Scene, "zenv_rename_props"):
        del bpy.types.Scene.zenv_rename_props
    # Unregister classes in reverse order
    bpy.utils.unregister_class(ZENV_PT_MaterialRenameSuffix)
    bpy.utils.unregister_class(ZENV_OT_RemoveAffix)
    bpy.utils.unregister_class(ZENV_OT_AddAffix)
    bpy.utils.unregister_class(ZENV_PG_RenameByMaterialProps)

if __name__ == "__main__":
    register()
