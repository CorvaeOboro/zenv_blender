#region META
bl_info = {
    "name": 'MESH Rename Objects By Material',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Rename objects based on material names',
    "status": 'working',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 20,
    "addon_order": 50,
    "tags": ['rename', 'material', 'object naming'],
    "description_short": 'rename objects by material name',
    "description_medium": 'Renames selected mesh objects based on their primary material, with optional prefix/suffix and _MI removal.',
    "description_long": """
MESH Rename Objects By Material - A Blender addon for consistent object naming.
Renames objects based on their primary material, with optional suffix/prefix adjustments.
""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_MESH_rename_objects_by_material.png',
    "addon_image": 'zenv_blender_MESH_rename_objects_by_material.png',
}

#region IMPORT
import bpy
import logging
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region PROPS
class ZENV_PG_RenameByMaterial(PropertyGroup):
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

#endregion
#region OP
class ZENV_OT_RenameObjectsByMaterial(Operator):
    """Rename objects based on their primary material."""
    bl_idname = "zenv.rename_objects_by_material"
    bl_label = "Rename Objects By Material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when at least one mesh object is selected."""
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def get_primary_material(self, obj):
        """Get the primary (most used) material of an object."""
        if not obj or obj.type != 'MESH' or not obj.data or not obj.data.materials:
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

            # Snapshot selected objects to avoid mutation during iteration
            objects = list(context.selected_objects)

            # Track mesh data already renamed to avoid overwriting
            # when multiple objects share the same mesh data.
            renamed_mesh_data = set()

            # Process selected objects
            for obj in objects:
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

                # Apply object name
                obj.name = obj_name

                # Only rename mesh data if it hasn't been renamed already
                # (multiple objects may share the same mesh data).
                if obj.data not in renamed_mesh_data:
                    obj.data.name = obj_name
                    renamed_mesh_data.add(obj.data)

                renamed += 1

            # Report results
            if renamed > 0:
                self.report({'INFO'}, f"Renamed {renamed} objects")
            else:
                self.report({'INFO'}, "No objects renamed")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to rename objects by material")
            self.report({'ERROR'}, f"Error renaming objects: {str(e)}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_RenameByMaterial(Panel):
    """Panel for material-based object renaming."""
    bl_label = "MESH Rename By Material"
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

#endregion
#region REG
classes = (
    ZENV_PG_RenameByMaterial,
    ZENV_OT_RenameObjectsByMaterial,
    ZENV_PT_RenameByMaterial,
)

def register():
    """Register all addon classes, the scene property, and configure the logger."""
    global _logger_handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_rename_props = PointerProperty(
        type=ZENV_PG_RenameByMaterial
    )
    if _logger_handler is None:
        _logger_handler = logging.StreamHandler()
        _logger_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
        logger.addHandler(_logger_handler)
    if not logger.level:
        logger.setLevel(logging.INFO)

def unregister():
    """Unregister all addon classes, remove the scene property, and remove the logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, "zenv_rename_props"):
        delattr(bpy.types.Scene, "zenv_rename_props")
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
