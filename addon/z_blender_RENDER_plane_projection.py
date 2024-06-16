bl_info = {
    "name": "Custom Raytrace Renderer",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 92, 0),
    "location": "View3D > Tools",
    "description": "Implements a custom raytrace renderer using a plane as the image plane.",
    "warning": "",
    "wiki_url": "",
    "category": "Rendering"
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import IntProperty
import os
from datetime import datetime

def perform_ray_cast(context, plane, pixel_width, pixel_height):
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

def save_rendered_image(render_image, base_path):
    render_dir = os.path.join(base_path, "render")
    os.makedirs(render_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = os.path.join(render_dir, f"{date_str}.png")
    render_image.filepath_raw = file_path
    render_image.file_format = 'PNG'
    render_image.save()

def create_line_object(context, start, end, hit):
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

def raycast_from_plane_debug(context, plane, pixel_width, pixel_height):
    results = perform_ray_cast(context, plane, pixel_width, pixel_height)
    if not results:
        return

    clear_debug_lines(context)
    for world_pos, ray_end, result, location, normal, object in results:
        create_line_object(context, world_pos, ray_end, result)

def raycast_from_plane(context, plane, pixel_width, pixel_height):
    results = perform_ray_cast(context, plane, pixel_width, pixel_height)
    if not results:
        return None

    render_image = bpy.data.images.new("Render Result", width=pixel_width, height=pixel_height)
    pixels = [0.0] * (4 * pixel_width * pixel_height)

    for i, (world_pos, ray_end, result, location, normal, object) in enumerate(results):
        idx = (i % pixel_height * pixel_width + i // pixel_height) * 4
        if result:
            pixels[idx:idx+4] = [1.0, 1.0, 1.0, 1.0]
        else:
            pixels[idx:idx+4] = [0.0, 0.0, 0.0, 1.0]

    render_image.pixels = pixels
    render_image.update()

    base_path = bpy.path.abspath("//")
    save_rendered_image(render_image, base_path)
    return render_image


def clear_debug_lines(context):
    for obj in list(context.collection.objects):
        if "Ray Line" in obj.name:
            bpy.data.objects.remove(obj, do_unlink=True)

class RENDER_OT_custom_raytracer_debug(bpy.types.Operator):
    bl_idname = "render.custom_raytracer_debug"
    bl_label = "Debug Raycast Plane"
    
    def execute(self, context):
        plane = context.active_object
        if not plane:
            self.report({'ERROR'}, "No active mesh object selected")
            return {'CANCELLED'}
        raycast_from_plane_debug(context, plane, context.scene.pixel_width, context.scene.pixel_height)
        self.report({'INFO'}, "Debug raycast complete")
        return {'FINISHED'}

class RENDER_OT_custom_raytracer(bpy.types.Operator):
    bl_idname = "render.custom_raytracer"
    bl_label = "Render from Plane"
    
    def execute(self, context):
        plane = context.active_object
        if not plane:
            self.report({'ERROR'}, "No active mesh object selected")
            return {'CANCELLED'}
        image = raycast_from_plane(context, plane, context.scene.pixel_width, context.scene.pixel_height)
        if image is None:
            self.report({'ERROR'}, "Failed to render from the plane")
            return {'CANCELLED'}
        self.report({'INFO'}, "Render complete")
        return {'FINISHED'}

class RENDER_OT_clear_debug_lines(bpy.types.Operator):
    bl_idname = "render.clear_debug_lines"
    bl_label = "Clear Debug Lines"
    
    def execute(self, context):
        clear_debug_lines(context)
        self.report({'INFO'}, "Debug lines cleared")
        return {'FINISHED'}

class ZENV_PT_Panel(bpy.types.Panel):
    bl_label = "ZENV"
    bl_idname = "ZENV_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Raycast Settings:")
        layout.prop(context.scene, "pixel_width", text="Pixel Width")
        layout.prop(context.scene, "pixel_height", text="Pixel Height")
        layout.separator()
        layout.operator("render.custom_raytracer", text="Render Image from Plane")
        layout.operator("render.custom_raytracer_debug", text="Debug Image from Plane")
        layout.operator("render.clear_debug_lines", text="Clear Debug Lines")

def register():
    bpy.utils.register_class(RENDER_OT_custom_raytracer)
    bpy.utils.register_class(RENDER_OT_custom_raytracer_debug)
    bpy.utils.register_class(RENDER_OT_clear_debug_lines)
    bpy.utils.register_class(ZENV_PT_Panel)
    bpy.types.Scene.pixel_width = IntProperty(name="Pixel Width", default=100, min=1, max=1000)
    bpy.types.Scene.pixel_height = IntProperty(name="Pixel Height", default=100, min=1, max=1000)

def unregister():
    bpy.utils.unregister_class(RENDER_OT_custom_raytracer)
    bpy.utils.unregister_class(RENDER_OT_custom_raytracer_debug)
    bpy.utils.unregister_class(RENDER_OT_clear_debug_lines)
    bpy.utils.unregister_class(ZENV_PT_Panel)
    del bpy.types.Scene.pixel_width
    del bpy.types.Scene.pixel_height

if __name__ == "__main__":
    register()
