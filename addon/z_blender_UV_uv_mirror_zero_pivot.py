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
    def flip_uvs(bm, horizontal=False, vertical=False, selected_only=False):
        """Mirror UVs around zero pivot point
        
        Args:
            bm: BMesh object
            horizontal: Mirror horizontally if True
            vertical: Mirror vertically if True
            selected_only: Only mirror selected faces if True
        """
        try:
            uv_layer = bm.loops.layers.uv.verify()
            for face in bm.faces:
                if not selected_only or face.select:
                    for loop in face.loops:
                        uv = loop[uv_layer].uv
                        if horizontal:
                            uv.x = -uv.x
                        if vertical:
                            uv.y = -uv.y
        except Exception as e:
            print(f"Error flipping UVs: {str(e)}")

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_UVMirror_Base:
    """Base class for UV mirror operators"""
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

class ZENV_OT_UVMirror_Horizontal_Selected(ZENV_OT_UVMirror_Base, Operator):
    """Mirror selected face UVs horizontally around zero pivot point"""
    bl_idname = "zenv.uvmirror_horizontal_selected"
    bl_label = "Mirror Selected Horizontal"
    
    def execute(self, context):
        try:
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            ZENV_UVMirror_Utils.flip_uvs(bm, horizontal=True, selected_only=True)
            bmesh.update_edit_mesh(obj.data)
            self.report({'INFO'}, "Selected UVs mirrored horizontally")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_Vertical_Selected(ZENV_OT_UVMirror_Base, Operator):
    """Mirror selected face UVs vertically around zero pivot point"""
    bl_idname = "zenv.uvmirror_vertical_selected"
    bl_label = "Mirror Selected Vertical"
    
    def execute(self, context):
        try:
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            ZENV_UVMirror_Utils.flip_uvs(bm, vertical=True, selected_only=True)
            bmesh.update_edit_mesh(obj.data)
            self.report({'INFO'}, "Selected UVs mirrored vertically")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_Horizontal_All(ZENV_OT_UVMirror_Base, Operator):
    """Mirror all UVs horizontally around zero pivot point"""
    bl_idname = "zenv.uvmirror_horizontal_all"
    bl_label = "Mirror All Horizontal"
    
    def execute(self, context):
        try:
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            ZENV_UVMirror_Utils.flip_uvs(bm, horizontal=True, selected_only=False)
            bmesh.update_edit_mesh(obj.data)
            self.report({'INFO'}, "All UVs mirrored horizontally")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to mirror UVs: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_UVMirror_Vertical_All(ZENV_OT_UVMirror_Base, Operator):
    """Mirror all UVs vertically around zero pivot point"""
    bl_idname = "zenv.uvmirror_vertical_all"
    bl_label = "Mirror All Vertical"
    
    def execute(self, context):
        try:
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            ZENV_UVMirror_Utils.flip_uvs(bm, vertical=True, selected_only=False)
            bmesh.update_edit_mesh(obj.data)
            self.report({'INFO'}, "All UVs mirrored vertically")
            return {'FINISHED'}
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
        col.operator("zenv.uvmirror_horizontal_selected", icon='ORIENTATION_LOCAL')
        col.operator("zenv.uvmirror_vertical_selected", icon='ORIENTATION_GLOBAL')
        
        # All faces section
        box = layout.box()
        box.label(text="Mirror All:", icon='UV')
        col = box.column(align=True)
        col.operator("zenv.uvmirror_horizontal_all", icon='ORIENTATION_LOCAL')
        col.operator("zenv.uvmirror_vertical_all", icon='ORIENTATION_GLOBAL')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_UVMirror_Horizontal_Selected,
    ZENV_OT_UVMirror_Vertical_Selected,
    ZENV_OT_UVMirror_Horizontal_All,
    ZENV_OT_UVMirror_Vertical_All,
    ZENV_PT_UVMirror_Panel,
)

def register():
    for current_class in classes:
        bpy.utils.register_class(current_class)

def unregister():
    for current_class in reversed(classes):
        bpy.utils.unregister_class(current_class)

if __name__ == "__main__":
    register()
