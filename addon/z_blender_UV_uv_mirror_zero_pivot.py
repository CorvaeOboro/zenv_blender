"""
UV MIRROR ZERO PIVOT
Mirror UVs around zero pivot point
Flips UVs horizontally or vertically in UV editor, with options for selected faces or entire UV
"""

bl_info = {
    "name": "UV Mirror Zero Pivot",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Mirror UVs around zero pivot point horizontally or vertically",
}

import bpy
import bmesh
from bpy.types import Operator, Panel

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_UVMirror_Utils:
    """Utility functions for UV mirroring"""
    
    @staticmethod
    def flip_uvs_edit_mode(bm, horizontal=False, vertical=False, selected_only=False):
        """Mirror UVs in Edit Mode"""
        try:
            uv_layer = bm.loops.layers.uv.active
            if not uv_layer:
                uv_layer = bm.loops.layers.uv.new()
            for face in bm.faces:
                if not selected_only or face.select:
                    for loop in face.loops:
                        uv = loop[uv_layer].uv
                        if horizontal:
                            uv.x = -uv.x
                        if vertical:
                            uv.y = -uv.y
        except Exception as e:
            print(f"Error flipping UVs in Edit Mode: {str(e)}")

    @staticmethod
    def flip_uvs_object_mode(obj, horizontal=False, vertical=False):
        """Mirror UVs in Object Mode"""
        try:
            if not obj.data.uv_layers.active:
                obj.data.uv_layers.new()
            
            for uv_layer in obj.data.uv_layers:
                for polygon in obj.data.polygons:
                    for loop_index in polygon.loop_indices:
                        uv = uv_layer.data[loop_index].uv
                        if horizontal:
                            uv.x = -uv.x
                        if vertical:
                            uv.y = -uv.y
        except Exception as e:
            print(f"Error flipping UVs in Object Mode: {str(e)}")

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_UVMirror_Base:
    """Base class for UV mirror operators"""
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH'

    def execute_edit_mode(self, context, horizontal=False, vertical=False, selected_only=False):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        ZENV_UVMirror_Utils.flip_uvs_edit_mode(bm, horizontal, vertical, selected_only)
        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

    def execute_object_mode(self, context, horizontal=False, vertical=False):
        obj = context.active_object
        ZENV_UVMirror_Utils.flip_uvs_object_mode(obj, horizontal, vertical)
        return {'FINISHED'}

class ZENV_OT_UVMirror_X_Selected(ZENV_OT_UVMirror_Base, Operator):
    """Mirror selected face UVs horizontally around zero pivot point"""
    bl_idname = "zenv.uvmirror_x_selected"
    bl_label = "Mirror X Selected"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            if context.object.mode == 'EDIT':
                return self.execute_edit_mode(context, horizontal=True, selected_only=True)
            else:
                self.report({'WARNING'}, "Select faces in Edit Mode to mirror selected UVs")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_Y_Selected(ZENV_OT_UVMirror_Base, Operator):
    """Mirror selected face UVs vertically around zero pivot point"""
    bl_idname = "zenv.uvmirror_y_selected"
    bl_label = "Mirror Y Selected"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            if context.object.mode == 'EDIT':
                return self.execute_edit_mode(context, vertical=True, selected_only=True)
            else:
                self.report({'WARNING'}, "Select faces in Edit Mode to mirror selected UVs")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_X_All(ZENV_OT_UVMirror_Base, Operator):
    """Mirror all UVs horizontally around zero pivot point"""
    bl_idname = "zenv.uvmirror_x_all"
    bl_label = "Mirror X All"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            if context.object.mode == 'EDIT':
                return self.execute_edit_mode(context, horizontal=True, selected_only=False)
            else:
                return self.execute_object_mode(context, horizontal=True)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_Y_All(ZENV_OT_UVMirror_Base, Operator):
    """Mirror all UVs vertically around zero pivot point"""
    bl_idname = "zenv.uvmirror_y_all"
    bl_label = "Mirror Y All"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            if context.object.mode == 'EDIT':
                return self.execute_edit_mode(context, vertical=True, selected_only=False)
            else:
                return self.execute_object_mode(context, vertical=True)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_UVMirror_Panel(Panel):
    """Panel for UV mirroring tools"""
    bl_label = "UV Mirror"
    bl_idname = "ZENV_PT_uvmirror"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        
        # Selected faces section
        box = layout.box()
        box.label(text="Mirror Selected:", icon='UV_SYNC_SELECT')
        col = box.column(align=True)
        col.operator("zenv.uvmirror_x_selected", icon='ORIENTATION_LOCAL')
        col.operator("zenv.uvmirror_y_selected", icon='ORIENTATION_GLOBAL')
        
        # All faces section
        box = layout.box()
        box.label(text="Mirror All:", icon='UV')
        col = box.column(align=True)
        col.operator("zenv.uvmirror_x_all", icon='ORIENTATION_LOCAL')
        col.operator("zenv.uvmirror_y_all", icon='ORIENTATION_GLOBAL')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_UVMirror_X_Selected,
    ZENV_OT_UVMirror_Y_Selected,
    ZENV_OT_UVMirror_X_All,
    ZENV_OT_UVMirror_Y_All,
    ZENV_PT_UVMirror_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
