bl_info = {
    "name": "Mesh Cut World Bricker",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini.",
}

import bpy
import bmesh
from mathutils import Vector

GRIDFILL = True
# UI
class ZENV_PT_MeshBrickerPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Mesh Bricker"
    bl_idname = "ZENV_PT_MeshBricker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.mesh_bricker_cut", text="Brick Mesh")
        layout.prop(context.scene, "mesh_bricker_density")

class ZENV_OT_MeshBrickerCut(bpy.types.Operator):
    bl_idname = "zenv.mesh_bricker_cut"
    bl_label = "Brick Mesh"

    def execute(self, context):
        # Initial checks
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected.")
            return {'CANCELLED'}
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "The active object must be a mesh.")
            return {'CANCELLED'}

        # Apply mesh bricking
        self.bricker_mesh(context.active_object, context.scene.mesh_bricker_density)
        return {'FINISHED'}
    
    def bricker_mesh(self, mesh, density=0.01):  # Density fixed to 0.01 for 1 cm cuts
        """Cut the given mesh into a consistent world unit grid pattern using the knife tool."""
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Create a new bmesh to perform operations
        bm = bmesh.new()
        bm.from_mesh(mesh.data)

        # Align cuts to global grid starting from world origin
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])

        # Start at the nearest lower density grid point that is below the minimum bounds
        start_cuts = [density * (bounds_min[i] // density) for i in range(3)]

        # Calculate the number of cuts along each axis, spanning beyond the object's bounds
        num_cuts = [int((bounds_max[i] - start_cuts[i]) / density) + 1 for i in range(3)]

        # Cut each axis independently
        for axis in range(3):
            cut_coord = start_cuts[axis]
            for _ in range(num_cuts[axis]):
                plane_co = Vector([cut_coord if i == axis else 0 for i in range(3)])
                plane_no = Vector([1 if i == axis else 0 for i in range(3)])
                bmesh.ops.bisect_plane(bm, geom=bm.edges[:] + bm.faces[:], dist=0.01,
                                       plane_co=plane_co, plane_no=plane_no)
                cut_coord += density

        # Finish up
        bm.to_mesh(mesh.data)
        bm.free()
        bpy.ops.object.mode_set(mode='OBJECT')

def register():
    bpy.utils.register_class(ZENV_PT_MeshBrickerPanel)
    bpy.utils.register_class(ZENV_OT_MeshBrickerCut)
    bpy.types.Scene.mesh_bricker_density = bpy.props.FloatProperty(
        name="Bricker Density",
        description="Density for mesh bricking, in Blender units",
        default=0.1,
        min=0.01,
        max=1000.0
    )

def unregister():
    bpy.utils.unregister_class(ZENV_PT_MeshBrickerPanel)
    bpy.utils.unregister_class(ZENV_OT_MeshBrickerCut)
    del bpy.types.Scene.mesh_bricker_density

if __name__ == "__main__":
    register()
