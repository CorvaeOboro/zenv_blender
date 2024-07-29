bl_info = {
    "name": "Parabola Slash Mesh Generator",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 93, 0),
    "location": "View3D > Tool",
    "description": "Parabola Slash Mesh Generator"
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector
from bpy.props import FloatProperty, IntProperty, PointerProperty

def create_curve_data(length, angle, curve_resolution):
    # Create a new curve object
    curve_data = bpy.data.curves.new('ParabolaCurve', type='CURVE')
    curve_data.dimensions = '3D'
    spline.bezier_points.add(curve_resolution - 1)

    
    # Define parabola control points
    start_point = Vector((0, 0, 0))
    control_point = Vector((length / 2, length * angle, 0))
    end_point = Vector((length, 0, 0))

    
    # Set points of the Bézier curve with handles
    set_bezier_points_with_handles(spline, start_point, control_point, end_point)
    return curve_data

def create_parabola_object(context, curve_data, rotation):
    # Create an object with the curve data
    curve_object = bpy.data.objects.new('ParabolaCurve', curve_data)
    bpy.context.collection.objects.link(curve_object)
    

    # Apply rotation
    curve_object.rotation_euler = (0, 0, rotation)

    return curve_object

def create_parabola_mesh(context, angle, rotation, length, curve_resolution):
    curve_data = create_curve_data(length, angle, curve_resolution)
    parabola_object = create_parabola_object(context, curve_data, rotation)
    # Convert curve to mesh
    bpy.context.view_layer.objects.active = parabola_object
    bpy.ops.object.convert(target='MESH')
    # Add UV mapping
    add_uv_mapping(parabola_object)
    return parabola_object

def set_bezier_points_with_handles(spline, start, control, end):
    spline.bezier_points[0].co = start
    spline.bezier_points[1].co = control
    spline.bezier_points[2].co = end
    for point in spline.bezier_points:
        point.handle_right_type = 'AUTO'
        point.handle_left_type = 'AUTO'

def add_uv_mapping(curve_object):
    if curve_object.type == 'MESH':
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.uv.unwrap()
        bpy.ops.object.mode_set(mode='OBJECT')

def get_zenv_properties(context):
    return context.scene.zenv_properties

def draw_properties(layout, props):
    layout.prop(props, "angle")
    layout.prop(props, "rotation")
    layout.prop(props, "length")
    layout.prop(props, "curve_resolution")


def convert_curve_to_mesh(curve_object):
    # Convert curve to mesh
    bpy.context.view_layer.objects.active = curve_object
    bpy.ops.object.convert(target='MESH')
    return curve_object


class ZENVProperties(PropertyGroup):
    angle: FloatProperty(
        name="Angle",
        description="Angle of the parabola",
        default=0.5,
        min=-2.0,
        max=2.0
    )
    rotation: FloatProperty(
        name="Rotation",
        description="Rotation of the parabola",
        default=0.0,
        min=-3.14,
        max=3.14
    )
    length: FloatProperty(
        name="Length",
        description="Length of the parabola",
        default=2.0,
        min=0.1,
        max=10.0
    )
    curve_resolution: IntProperty(
        name="Curve Resolution",
        description="Resolution of the curve",
        default=12,
        min=3,
        max=64
    )

class OBJECT_OT_add_parabola_mesh(Operator):
    bl_idname = "object.add_parabola_mesh"
    bl_label = "Add Parabola Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    
    def execute(self, context):
        props = get_zenv_properties(context)
        parabola_object = create_parabola_mesh(context, props.angle, props.rotation, props.length, props.curve_resolution)
        if parabola_object:
            self.report({'INFO'}, "Parabola mesh created successfully.")
        else:
            self.report({'ERROR'}, "Failed to create parabola mesh.")
        return {'FINISHED'}

#===================================================================
# UI PANEL
class ZENV_PT_panel(Panel):
    bl_idname = "ZENV_PT_panel"
    bl_label = "Parabola Slash Mesh Generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.zenv_properties
        
        draw_properties(layout, props)
        layout.operator("object.add_parabola_mesh")

def register():
    bpy.utils.register_class(ZENVProperties)
    bpy.types.Scene.zenv_properties = PointerProperty(type=ZENVProperties)
    bpy.utils.register_class(OBJECT_OT_add_parabola_mesh)
    bpy.utils.register_class(ZENV_PT_panel)

def unregister():
    bpy.utils.unregister_class(ZENVProperties)
    del bpy.types.Scene.zenv_properties
    bpy.utils.unregister_class(OBJECT_OT_add_parabola_mesh)
    bpy.utils.unregister_class(ZENV_PT_panel)

if __name__ == "__main__":
    register()
