#region META
bl_info = {
    "name": 'MESH Separate by Axis',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Separates mesh into two parts by slicing along chosen axis',
    "status": 'working',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 20,
    "addon_order": 40,
    "tags": ['mesh separate', 'axis', 'slice', 'bisect'],
    "description_short": 'separate mesh parts by axis',
    "description_medium": 'separates mesh into two parts by slicing along chosen axis',
    "description_long": """
MESH SEPARATE BY AXIS
 separates mesh into two parts by slicing along chosen axis
""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_MESH_separate_by_axis.png',
    "addon_image": 'zenv_blender_MESH_separate_by_axis.png',
}

#region IMPORT
import bpy
import bmesh
import logging
from mathutils import Vector
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import EnumProperty, PointerProperty

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region PROPS
class ZENV_PG_SeparateByAxis(PropertyGroup):
    """Properties for axis separation"""
    axis: EnumProperty(
        name="Axis",
        description="Choose axis for separation",
        items=[
            ('X', 'X Axis', 'Slice along the X axis', 'AXIS_SIDE', 0),
            ('Y', 'Y Axis', 'Slice along the Y axis', 'AXIS_FRONT', 1),
            ('Z', 'Z Axis', 'Slice along the Z axis', 'AXIS_TOP', 2),
        ],
        default='X'
    )

#endregion
#region OP
class ZENV_OT_SeparateByAxis(Operator):
    """Separate mesh into two parts by slicing along chosen axis"""
    bl_idname = "zenv.separatebyaxis_slice"
    bl_label = "Slice Along Axis"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def slice_and_separate(self, context, obj, axis):
        """Slice and separate the mesh along the specified axis.

        Returns ``True`` on success, ``False`` on failure.
        """
        # Store original name before renaming so the negative-side
        # name can be built without fragile string splitting.
        original_name = obj.name
        # Track original mode for restoration.
        original_mode = obj.mode

        try:
            # Get into edit mode
            if obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')

            # Get bmesh
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.faces.ensure_lookup_table()

            # Deselect everything first
            bpy.ops.mesh.select_all(action='DESELECT')

            # Define plane normal based on axis
            plane_no = {
                'X': (1.0, 0.0, 0.0),
                'Y': (0.0, 1.0, 0.0),
                'Z': (0.0, 0.0, 1.0)
            }[axis]

            # First, bisect the mesh
            bmesh.ops.bisect_plane(
                bm,
                geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                plane_co=(0, 0, 0),
                plane_no=plane_no,
                clear_inner=False,
                clear_outer=False
            )

            # Get axis index for selection
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]

            # Select faces on negative side using calc_center_median
            for face in bm.faces:
                center = face.calc_center_median()
                if center[axis_idx] < 0:
                    face.select = True

            # Update mesh
            bmesh.update_edit_mesh(me)

            # Separate selected geometry
            bpy.ops.mesh.separate(type='SELECTED')

            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Get the new objects - use passed context, not bpy.context
            new_objects = [o for o in context.selected_objects
                           if o != context.active_object]

            if new_objects:
                # Name the objects based on their position
                obj.name = f"{original_name}_positive"
                new_objects[0].name = f"{original_name}_negative"

                # Select both objects
                obj.select_set(True)
                new_objects[0].select_set(True)
                context.view_layer.objects.active = obj

            # Restore original mode if it wasn't OBJECT
            if original_mode != 'OBJECT' and context.view_layer.objects.active is not None:
                try:
                    bpy.ops.object.mode_set(mode=original_mode)
                except RuntimeError:
                    pass

            return True

        except Exception:
            logger.exception("Failed to slice and separate along %s axis", axis)
            # Ensure we exit edit mode on failure
            try:
                if obj.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
            return False

    def execute(self, context):
        obj = None
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "No valid mesh object selected")
                return {'CANCELLED'}

            # Get properties
            props = context.scene.zenv_separatebyaxis_props

            # Perform separation
            if not self.slice_and_separate(context, obj, props.axis):
                self.report({'ERROR'}, f"Failed to separate mesh along {props.axis} axis")
                return {'CANCELLED'}

            self.report({'INFO'}, f"Successfully separated mesh along {props.axis} axis")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to separate mesh by axis")
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            if obj is not None and obj.mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except RuntimeError:
                    pass
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_SeparateByAxis(Panel):
    """Panel for axis separation tools"""
    bl_label = "MESH Separate by Axis"
    bl_idname = "ZENV_PT_separatebyaxis"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_separatebyaxis_props

        box = layout.box()
        box.label(text="Choose Axis:", icon='OBJECT_ORIGIN')
        row = box.row(align=True)
        row.prop(props, "axis", expand=True)
        
        layout.separator()
        op = layout.operator("zenv.separatebyaxis_slice", icon='MOD_BOOLEAN')

#endregion
#region REG
classes = (
    ZENV_PG_SeparateByAxis,
    ZENV_OT_SeparateByAxis,
    ZENV_PT_SeparateByAxis,
)

def register():
    """Register all addon classes, the scene property, and configure the logger."""
    global _logger_handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_separatebyaxis_props = PointerProperty(type=ZENV_PG_SeparateByAxis)
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
        bpy.utils.unregister_class(current_class_to_unregister)
    if hasattr(bpy.types.Scene, 'zenv_separatebyaxis_props'):
        delattr(bpy.types.Scene, 'zenv_separatebyaxis_props')
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
