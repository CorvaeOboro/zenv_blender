# RENDER PLANE PROJECTION
# custom raytrace renderer using a plane as the image plane
# useful for projecting depth maps or textures from a plane

bl_info = {
    "name": "RENDER Plane Projection",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Custom raytrace renderer using a plane as the image plane",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import IntProperty
import os
from datetime import datetime

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_PlaneProjection_Properties(bpy.types.PropertyGroup):
    """Properties for plane projection rendering"""
    pixel_width: IntProperty(
        name="Pixel Width",
        description="Width of the rendered image in pixels",
        default=100,
        min=1,
        max=1000
    )
    pixel_height: IntProperty(
        name="Pixel Height",
        description="Height of the rendered image in pixels",
        default=100,
        min=1,
        max=1000
    )

# ------------------------------------------------------------------------
#    Utility Class
# ------------------------------------------------------------------------

class ZENV_Utils_PlaneProjection:
    """Utility class for plane projection operations"""
    
    @staticmethod
    def perform_ray_cast(context, plane, pixel_width, pixel_height):
        """Perform raycast from plane points and return results"""
        if plane.type != 'MESH':
            return None
        
        depsgraph = context.evaluated_depsgraph_get()
        scene = context.scene
        mat = plane.matrix_world
        size = plane.dimensions
        transformed_normal = mat.to_3x3() @ plane.data.polygons[0].normal
        transformed_normal.normalize()

        results = []
        offset = transformed_normal * 0.001  # Small offset along the normal to avoid self-intersection

        for x in range(pixel_width):
            for y in range(pixel_height):
                u = x / pixel_width - 0.5
                v = y / pixel_height - 0.5
                world_pos = mat @ Vector((u * size.x, v * size.y, 0)) + offset
                ray_direction = transformed_normal
                ray_end = world_pos + ray_direction * 10
                result, location, normal, index, object, matrix = scene.ray_cast(depsgraph, world_pos, ray_direction)

                # Check if the ray hits the plane itself and ignore this hit
                if result and object != plane:
                    results.append((world_pos, ray_end, True, location, normal, object))
                else:
                    results.append((world_pos, ray_end, False, location, normal, object))
        return results

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_PlaneProjection_Debug(bpy.types.Operator):
    """Debug visualization of plane projection raycasts"""
    bl_idname = "zenv.planeprojection_debug"
    bl_label = "Debug Raycast Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def create_line_object(context, start, end, hit):
        """Create a line object for debug visualization"""
        mesh = bpy.data.meshes.new(name="Ray Line")
        obj = bpy.data.objects.new("Ray Line", mesh)
        context.collection.objects.link(obj)
        mesh.from_pydata([start, end], [(0, 1)], [])
        mesh.update()
        material = bpy.data.materials.new(name="RayLineMat")
        obj.data.materials.append(material)
        if hit:
            material.diffuse_color = (1.0, 1.0, 1.0, 1.0)  # White for hit
        else:
            material.diffuse_color = (1.0, 0.0, 0.0, 0.5)  # Red for no hit, semi-transparent
        return obj

    @staticmethod
    def clear_debug_lines(context):
        """Remove all debug line objects from the scene"""
        for obj in context.scene.objects:
            if obj.name.startswith("Ray Line"):
                bpy.data.objects.remove(obj, do_unlink=True)

    def raycast_from_plane_debug(self, context, plane, pixel_width, pixel_height):
        """Debug visualization of plane projection raycasts"""
        results = ZENV_Utils_PlaneProjection.perform_ray_cast(context, plane, pixel_width, pixel_height)
        if not results:
            return {'CANCELLED'}

        self.clear_debug_lines(context)
        for start, end, hit, location, normal, obj in results:
            self.create_line_object(context, start, end if not hit else location, hit)
        return {'FINISHED'}

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}

        props = context.scene.zenv_planeprojection_props
        return self.raycast_from_plane_debug(context, active_obj, props.pixel_width, props.pixel_height)

class ZENV_OT_PlaneProjection_Render(bpy.types.Operator):
    """Render image from plane projection"""
    bl_idname = "zenv.planeprojection_render"
    bl_label = "Render from Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def save_rendered_image(render_image, base_path):
        """Save rendered image to file with timestamp"""
        render_dir = os.path.join(base_path, "render")
        os.makedirs(render_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        file_path = os.path.join(render_dir, f"{date_str}.png")
        render_image.filepath_raw = file_path
        render_image.file_format = 'PNG'
        render_image.save()

    def raycast_from_plane(self, context, plane, pixel_width, pixel_height):
        """Render image from plane projection"""
        results = ZENV_Utils_PlaneProjection.perform_ray_cast(context, plane, pixel_width, pixel_height)
        if not results:
            return {'CANCELLED'}

        # Create new image for rendering
        render_image = bpy.data.images.new(
            name="PlaneProjection",
            width=pixel_width,
            height=pixel_height,
            alpha=True
        )

        # Set pixels based on raycast results
        pixels = [0] * (4 * pixel_width * pixel_height)
        for i, (start, end, hit, location, normal, obj) in enumerate(results):
            pixel_idx = i * 4
            if hit:
                # Set white for hits, could be modified for different visualization
                pixels[pixel_idx:pixel_idx + 4] = [1.0, 1.0, 1.0, 1.0]

        render_image.pixels = pixels
        self.save_rendered_image(render_image, bpy.path.abspath("//"))
        bpy.data.images.remove(render_image)
        return {'FINISHED'}

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}

        props = context.scene.zenv_planeprojection_props
        return self.raycast_from_plane(context, active_obj, props.pixel_width, props.pixel_height)

class ZENV_OT_PlaneProjection_ClearDebug(bpy.types.Operator):
    """Clear debug visualization lines"""
    bl_idname = "zenv.planeprojection_clear_debug"
    bl_label = "Clear Debug Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ZENV_OT_PlaneProjection_Debug.clear_debug_lines(context)
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_PlaneProjection_Panel(bpy.types.Panel):
    """Panel for plane projection rendering tools"""
    bl_label = "Plane Projection"
    bl_idname = "ZENV_PT_planeprojection"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_planeprojection_props
        
        box = layout.box()
        box.label(text="Resolution:", icon='RESTRICT_RENDER_OFF')
        col = box.column(align=True)
        col.prop(props, "pixel_width", text="Width")
        col.prop(props, "pixel_height", text="Height")
        
        layout.separator()
        
        col = layout.column(align=True)
        col.operator("zenv.planeprojection_render", text="Render Image", icon='RENDER_STILL')
        col.operator("zenv.planeprojection_debug", text="Debug View", icon='SNAP_FACE')
        col.operator("zenv.planeprojection_clear_debug", text="Clear Debug", icon='CANCEL')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_PlaneProjection_Properties,
    ZENV_Utils_PlaneProjection,
    ZENV_OT_PlaneProjection_Debug,
    ZENV_OT_PlaneProjection_Render,
    ZENV_OT_PlaneProjection_ClearDebug,
    ZENV_PT_PlaneProjection_Panel,
)

def register():
    for current_class in classes:
        bpy.utils.register_class(current_class)
    bpy.types.Scene.zenv_planeprojection_props = bpy.props.PointerProperty(type=ZENV_PG_PlaneProjection_Properties)

def unregister():
    for current_class in reversed(classes):
        bpy.utils.unregister_class(current_class)
    del bpy.types.Scene.zenv_planeprojection_props

if __name__ == "__main__":
    register()
