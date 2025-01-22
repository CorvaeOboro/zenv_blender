bl_info = {
    "name": "MESH Fix Everquest mesh export",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " mirror x global , flip uv vertical 0,0 centered , merge verts by distance , flat shading by face , flip normals . Fix Everquest mesh export from s3d zone exporter",
}
#//==================================================================================================
import bpy
import logging
import bmesh

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#//============== MESH
def mirror_x(context):
    logger.debug("Mirroring X Global")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.mirror(constraint_axis=(True, False, False))
    bpy.ops.object.mode_set(mode='OBJECT')

def merge_vertices_by_distance(obj, distance):
    logger.debug("Merge vertices by distance: " + str(distance))
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=distance)
    bpy.ops.object.mode_set(mode='OBJECT')

#//============== UV
def flip_uvs_vertically(obj):
    logger.debug("Flipping UVs vertically")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        for loop in face.loops:
            uv = loop[uv_layer].uv
            uv.y = 1 - uv.y
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

#//============== NORMALS
def set_shading_flat(obj):
    logger.debug("Normals set Flat")
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_flat()

def transfer_shading():
    bpy.ops.object.data_transfer(use_reverse_transfer=True, data_type='SHADING')

def flip_normals(obj):
    logger.debug("Reversing normals")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode='OBJECT')

def add_smoothing_groups(obj):
    logger.debug("Adding smoothing groups")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()

def fix_tangents_and_binormals(obj):
    logger.debug("Fixing nearly zero tangents and bi-normals")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_add(type='NORMAL_EDIT')
    obj.modifiers["NormalEdit"].use_direction_parallel = True
    bpy.ops.object.modifier_apply(apply_as='DATA', modifier="NormalEdit")

def apply_weighted_normals(obj):
    logger.debug("Applying face area weights for smoothing normals")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_add(type='WEIGHTED_NORMAL')
    bpy.ops.object.modifier_apply(apply_as='DATA', modifier="WeightedNormal")

def deselect_all(obj):
    logger.debug("Deselecting all subcomponents")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')


#//==================================================================================================
class ZENV_OT_MeshFixEverquest(bpy.types.Operator):
    bl_idname = "zenv.zenv_mesh_everquest_fix"
    bl_label = "MESH FIX EQ"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if obj.type != 'MESH':
            self.report({'WARNING'}, "Active object is not a mesh")
            return {'CANCELLED'}

        # select faces
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        # mirror x global
        mirror_x(context)
        bpy.ops.object.mode_set(mode='OBJECT')

        # face normals , flat , reverse normal
        set_shading_flat(obj)
        #transfer_shading()

        # merge verts by distance
        bpy.ops.object.mode_set(mode='EDIT')
        merge_distance = 0.01  # vert distance
        merge_vertices_by_distance(obj,merge_distance)

        # flip uv vertical
        flip_uvs_vertically(obj)

        # reverse normal
        #flip_normals(obj)

        # smoothing normals , tangents , binormals
        add_smoothing_groups(obj)
        fix_tangents_and_binormals(obj)
        apply_weighted_normals(obj)

        deselect_all(obj)

        # Set to layout mode, object mode, 3D viewport
        bpy.ops.object.mode_set(mode='OBJECT')
        context.area.type = 'VIEW_3D'

        return {'FINISHED'}

#//==================================================================================================
class ZENV_PT_MeshFixEverquest_Panel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "MESH fix"
    bl_idname = "ZENV_MESH_fix_everquest_panel_a"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_MeshFixEverquest.bl_idname)

#//==================================================================================================
def register():
    bpy.utils.register_class(ZENV_OT_MeshFixEverquest)
    bpy.utils.register_class(ZENV_PT_MeshFixEverquest_Panel)

def unregister():
    bpy.utils.unregister_class(ZENV_OT_MeshFixEverquest)
    bpy.utils.unregister_class(ZENV_PT_MeshFixEverquest_Panel)

if __name__ == "__main__":
    register()
