# MESH SEPARATE BY AXIS
# separates mesh into two parts by slicing along chosen axis

bl_info = {
    "name": "MESH Separate by Axis",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 5),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Separates mesh into two parts by slicing along chosen axis",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import EnumProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_SeparateByAxis_Properties(PropertyGroup):
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

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_SeparateByAxis_Slice(Operator):
    """Separate mesh into two parts by slicing along chosen axis"""
    bl_idname = "zenv.separatebyaxis_slice"
    bl_label = "Slice Along Axis"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def slice_and_separate(self, context, obj, axis):
        """Slice and separate the mesh along the specified axis"""
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
        ret = bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=(0, 0, 0),
            plane_no=plane_no,
            clear_inner=False,
            clear_outer=False
        )
        
        # Get axis index for selection
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        
        # Select faces on negative side
        for face in bm.faces:
            center = Vector((0, 0, 0))
            for vert in face.verts:
                center += vert.co
            center /= len(face.verts)
            
            # Select faces on negative side
            if center[axis_idx] < 0:
                face.select = True
        
        # Update mesh
        bmesh.update_edit_mesh(me)
        
        # Separate selected geometry
        bpy.ops.mesh.separate(type='SELECTED')
        
        # Return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get the new objects
        new_objects = [obj for obj in bpy.context.selected_objects if obj != context.active_object]
        
        if new_objects:
            # Name the objects based on their position
            obj.name = f"{obj.name}_positive"
            new_objects[0].name = f"{obj.name.split('_positive')[0]}_negative"
            
            # Select both objects
            obj.select_set(True)
            new_objects[0].select_set(True)
            context.view_layer.objects.active = obj

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "No valid mesh object selected")
                return {'CANCELLED'}

            # Get properties
            props = context.scene.zenv_separatebyaxis_props
            
            # Perform separation
            self.slice_and_separate(context, obj, props.axis)
            
            self.report({'INFO'}, f"Successfully separated mesh along {props.axis} axis")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error separating mesh: {str(e)}")
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_SeparateByAxis_Panel(Panel):
    """Panel for axis separation tools"""
    bl_label = "Separate by Axis"
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

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_SeparateByAxis_Properties,
    ZENV_OT_SeparateByAxis_Slice,
    ZENV_PT_SeparateByAxis_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_separatebyaxis_props = PointerProperty(type=ZENV_PG_SeparateByAxis_Properties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_separatebyaxis_props

if __name__ == "__main__":
    register()
