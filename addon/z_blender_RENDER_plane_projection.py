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
#    Utility Functions
# ------------------------------------------------------------------------

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

def save_rendered_image(render_image, base_path):
    """Save rendered image to file with timestamp"""
    render_dir = os.path.join(base_path, "render")
    os.makedirs(render_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = os.path.join(render_dir, f"{date_str}.png")
    render_image.filepath_raw = file_path
    render_image.file_format = 'PNG'
    render_image.save()

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

def clear_debug_lines(context):
    """Remove all debug line objects from the scene"""
    for obj in list(context.collection.objects):
        if "Ray Line" in obj.name:
            bpy.data.objects.remove(obj, do_unlink=True)

def raycast_from_plane_debug(context, plane, pixel_width, pixel_height):
    """Debug visualization of plane projection raycasts"""
    results = perform_ray_cast(context, plane, pixel_width, pixel_height)
    if not results:
        return

    clear_debug_lines(context)
    for world_pos, ray_end, result, location, normal, object in results:
        create_line_object(context, world_pos, ray_end, result)

def raycast_from_plane(context, plane, pixel_width, pixel_height):
    """Render image from plane projection"""
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

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_PlaneProjection_Debug(bpy.types.Operator):
    """Debug visualization of plane projection raycasts"""
    bl_idname = "zenv.planeprojection_debug"
    bl_label = "Debug Raycast Plane"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            plane = context.active_object
            if not plane or plane.type != 'MESH':
                self.report({'ERROR'}, "No active mesh object selected")
                return {'CANCELLED'}
                
            props = context.scene.zenv_planeprojection_props
            raycast_from_plane_debug(context, plane, props.pixel_width, props.pixel_height)
            self.report({'INFO'}, "Debug raycast visualization complete")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error in debug raycast: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_PlaneProjection_Render(bpy.types.Operator):
    """Render image from plane projection"""
    bl_idname = "zenv.planeprojection_render"
    bl_label = "Render from Plane"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            plane = context.active_object
            if not plane or plane.type != 'MESH':
                self.report({'ERROR'}, "No active mesh object selected")
                return {'CANCELLED'}
                
            props = context.scene.zenv_planeprojection_props
            image = raycast_from_plane(context, plane, props.pixel_width, props.pixel_height)
            if image is None:
                self.report({'ERROR'}, "Failed to render from the plane")
                return {'CANCELLED'}
                
            self.report({'INFO'}, "Render complete")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error in rendering: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_PlaneProjection_ClearDebug(bpy.types.Operator):
    """Clear debug visualization lines"""
    bl_idname = "zenv.planeprojection_clear_debug"
    bl_label = "Clear Debug Lines"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            clear_debug_lines(context)
            self.report({'INFO'}, "Debug lines cleared")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error clearing debug lines: {str(e)}")
            return {'CANCELLED'}

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
