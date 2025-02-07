"""
MESH Rename Objects By Material - A Blender addon for consistent object naming.

Renames objects based on their primary material, with optional suffix/prefix adjustments.
"""

bl_info = {
    "name": "MESH Rename Objects By Material",
    "author": "CorvaeOboro",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Rename objects based on material names",
    "category": "ZENV",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty

class ZENV_PG_RenameByMaterialProps(PropertyGroup):
    """Properties for material-based renaming."""
    prefix: StringProperty(
        name="Prefix",
        description="Prefix to add to object names",
        default=""
    )
    
    suffix: StringProperty(
        name="Suffix",
        description="Suffix to add to object names",
        default=""
    )
    
    remove_mi: BoolProperty(
        name="Remove '_MI'",
        description="Remove '_MI' from material names",
        default=True
    )
    
    add_sm: BoolProperty(
        name="Add '_SM' to Object",
        description="Add '_SM' suffix to object names",
        default=False
    )

class ZENV_OT_RenameObjectsByMaterial(Operator):
    """Rename objects based on their primary material."""
    bl_idname = "zenv.rename_objects_by_material"
    bl_label = "Rename Objects By Material"
    bl_options = {'REGISTER', 'UNDO'}

    def get_primary_material(self, obj):
        """Get the primary (most used) material of an object."""
        if not obj.data or not obj.data.materials:
            return None
            
        # Count face assignments
        mat_counts = {}
        for poly in obj.data.polygons:
            mat_idx = poly.material_index
            if mat_idx < len(obj.data.materials):
                mat = obj.data.materials[mat_idx]
                if mat:
                    mat_counts[mat] = mat_counts.get(mat, 0) + 1
        
        # Return most used material
        if mat_counts:
            return max(mat_counts.items(), key=lambda x: x[1])[0]
        
        # Fallback to first material
        return obj.data.materials[0] if obj.data.materials else None

    def format_name(self, base_name, props):
        """Format the name with prefix/suffix and cleanup."""
        name = base_name
        
        # Remove _MI if requested
        if props.remove_mi and name.endswith("_MI"):
            name = name[:-3]
        
        # Add prefix/suffix
        if props.prefix:
            name = f"{props.prefix}{name}"
        if props.suffix:
            name = f"{name}{props.suffix}"
            
        return name

    def execute(self, context):
        """Execute the renaming operation."""
        try:
            props = context.scene.zenv_rename_props
            renamed = 0
            
            # Process selected objects
            for obj in context.selected_objects:
                if obj.type != 'MESH':
                    continue
                    
                # Get primary material
                material = self.get_primary_material(obj)
                if not material:
                    continue
                
                # Format names
                base_name = material.name
                obj_name = self.format_name(base_name, props)
                if props.add_sm:
                    obj_name = f"{obj_name}_SM"
                
                # Apply names
                obj.name = obj_name
                obj.data.name = obj_name
                renamed += 1
            
            # Report results
            if renamed > 0:
                self.report({'INFO'}, f"Renamed {renamed} objects")
            else:
                self.report({'INFO'}, "No objects renamed")
                
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error renaming objects: {str(e)}")
            return {'CANCELLED'}

class ZENV_PT_RenameByMaterialPanel(Panel):
    """Panel for material-based object renaming."""
    bl_label = "Rename By Material"
    bl_idname = "ZENV_PT_rename_by_material"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_rename_props
        
        box = layout.box()
        box.label(text="Name Settings:", icon='OBJECT_DATA')
        
        # Basic inputs
        col = box.column(align=True)
        col.prop(props, "prefix")
        col.prop(props, "suffix")
        
        # Options
        col = box.column(align=True)
        col.prop(props, "remove_mi")
        col.prop(props, "add_sm")
        
        # Operator
        box.operator(ZENV_OT_RenameObjectsByMaterial.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_RenameByMaterialProps,
    ZENV_OT_RenameObjectsByMaterial,
    ZENV_PT_RenameByMaterialPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_rename_props = bpy.props.PointerProperty(
        type=ZENV_PG_RenameByMaterialProps
    )

def unregister():
    """Unregister the addon classes."""
    try:
        for current_class_to_unregister in reversed(classes):
            try:
                bpy.utils.unregister_class(current_class_to_unregister)
            except RuntimeError:
                pass
        
        if hasattr(bpy.types.Scene, "zenv_rename_props"):
            delattr(bpy.types.Scene, "zenv_rename_props")
    except Exception as e:
        print(f"Error during unregister: {str(e)}")

if __name__ == "__main__":
    register()
