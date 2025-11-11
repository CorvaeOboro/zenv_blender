"""
Curl Flow Generator - Creates mesh geometry with curl flow patterns
"""

bl_info = {
    "name": 'MESH Curl Flow',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Creates mesh geometry with curl flow patterns',
    "status": 'wip',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
import random
import numpy as np
from mathutils import Vector, Matrix, noise
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_CurlFlowProperties(PropertyGroup):
    """Properties for the Curl Flow Generator"""
    num_lines: IntProperty(
        name="Number of Lines",
        description="Number of flow lines to generate",
        default=20,
        min=1,
        max=100
    )
    line_length: IntProperty(
        name="Line Length",
        description="Number of segments per line",
        default=50,
        min=10,
        max=200
    )
    curl_scale: FloatProperty(
        name="Curl Scale",
        description="Scale of the curl noise",
        default=1.0,
        min=0.1,
        max=5.0
    )
    curl_strength: FloatProperty(
        name="Curl Strength",
        description="Strength of the curl effect",
        default=0.5,
        min=0.1,
        max=2.0
    )
    flow_speed: FloatProperty(
        name="Flow Speed",
        description="Speed of the flow movement",
        default=1.0,
        min=0.1,
        max=5.0
    )
    convergence: FloatProperty(
        name="Convergence",
        description="How much lines tend to converge",
        default=0.3,
        min=0.0,
        max=1.0
    )
    surface_type: EnumProperty(
        name="Surface Type",
        description="Type of surface to generate lines on",
        items=[
            ('PLANE', "Plane", "Generate on a plane"),
            ('SPHERE', "Sphere", "Generate on a sphere"),
            ('CYLINDER', "Cylinder", "Generate on a cylinder")
        ],
        default='PLANE'
    )
    surface_scale: FloatProperty(
        name="Surface Scale",
        description="Scale of the base surface",
        default=2.0,
        min=0.1,
        max=10.0
    )
    line_thickness: FloatProperty(
        name="Line Thickness",
        description="Thickness of the flow lines",
        default=0.02,
        min=0.001,
        max=0.1
    )
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed for random generation",
        default=1,
        min=1,
        max=1000
    )
    use_color_gradient: BoolProperty(
        name="Use Color Gradient",
        description="Apply color gradient to lines",
        default=True
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_CurlFlowAdd(Operator):
    """Create new curl flow lines"""
    bl_idname = "zenv.curl_flow_add"
    bl_label = "Add Curl Flow"
    bl_options = {'REGISTER', 'UNDO'}

    def get_surface_point(self, u, v, props):
        """Get point on surface based on UV coordinates"""
        if props.surface_type == 'PLANE':
            x = (u - 0.5) * props.surface_scale
            y = (v - 0.5) * props.surface_scale
            return Vector((x, y, 0))
        elif props.surface_type == 'SPHERE':
            phi = u * 2 * math.pi
            theta = v * math.pi
            x = math.sin(theta) * math.cos(phi)
            y = math.sin(theta) * math.sin(phi)
            z = math.cos(theta)
            return Vector((x, y, z)) * props.surface_scale
        else:  # CYLINDER
            phi = u * 2 * math.pi
            h = (v - 0.5) * props.surface_scale
            x = math.cos(phi)
            y = math.sin(phi)
            return Vector((x, y, h)) * props.surface_scale

    def get_surface_normal(self, u, v, props):
        """Get normal vector at surface point"""
        if props.surface_type == 'PLANE':
            return Vector((0, 0, 1))
        elif props.surface_type == 'SPHERE':
            point = self.get_surface_point(u, v, props)
            return point.normalized()
        else:  # CYLINDER
            phi = u * 2 * math.pi
            return Vector((math.cos(phi), math.sin(phi), 0))

    def curl_noise(self, p, props):
        """Generate curl noise vector"""
        eps = 0.0001
        # Get noise values at offset positions
        nx = noise.noise(Vector((p.x + eps, p.y, p.z))) - noise.noise(Vector((p.x - eps, p.y, p.z)))
        ny = noise.noise(Vector((p.x, p.y + eps, p.z))) - noise.noise(Vector((p.x, p.y - eps, p.z)))
        nz = noise.noise(Vector((p.x, p.y, p.z + eps))) - noise.noise(Vector((p.x, p.y, p.z - eps)))
        
        # Create curl vector
        curl = Vector((
            (ny - nz) * props.curl_strength,
            (nz - nx) * props.curl_strength,
            (nx - ny) * props.curl_strength
        ))
        
        return curl * (1.0 / (2.0 * eps))

    def generate_flow_line(self, start_u, start_v, props):
        """Generate a single flow line"""
        points = []
        u, v = start_u, start_v
        
        for i in range(props.line_length):
            # Get current point on surface
            point = self.get_surface_point(u, v, props)
            normal = self.get_surface_normal(u, v, props)
            points.append(point)
            
            # Calculate curl noise
            curl = self.curl_noise(point * props.curl_scale, props)
            
            # Project curl vector onto surface
            if props.surface_type != 'PLANE':
                curl = curl - curl.dot(normal) * normal
            
            # Update UV coordinates
            step = props.flow_speed * 0.01
            u += curl.x * step
            v += curl.y * step
            
            # Wrap UV coordinates
            u = u % 1.0
            v = v % 1.0
            
            # Add convergence effect
            if props.convergence > 0:
                center_u, center_v = 0.5, 0.5
                u = u + (center_u - u) * props.convergence * 0.01
                v = v + (center_v - v) * props.convergence * 0.01
        
        return points

    def create_curve_from_points(self, points, name):
        """Create curve object from points"""
        # Create curve data
        curve_data = bpy.data.curves.new(name=name, type='CURVE')
        curve_data.dimensions = '3D'
        
        # Create spline
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(len(points) - 1)
        
        # Set points
        for i, point in enumerate(points):
            spline.bezier_points[i].co = point
            spline.bezier_points[i].handle_left = point
            spline.bezier_points[i].handle_right = point
        
        # Create object
        curve_obj = bpy.data.objects.new(name, curve_data)
        bpy.context.collection.objects.link(curve_obj)
        
        # Set curve properties
        props = bpy.context.scene.curl_flow_props
        curve_data.bevel_depth = props.line_thickness
        curve_data.bevel_resolution = 2
        
        return curve_obj

    def create_material(self, props):
        """Create material for flow lines"""
        mat = bpy.data.materials.new(name="Flow_Line_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
        color_ramp = nodes.new('ShaderNodeValToRGB')
        
        if props.use_color_gradient:
            # Setup color gradient
            color_ramp.color_ramp.elements[0].position = 0.0
            color_ramp.color_ramp.elements[0].color = (0.0, 0.5, 1.0, 1)
            color_ramp.color_ramp.elements[1].position = 1.0
            color_ramp.color_ramp.elements[1].color = (1.0, 0.2, 0.0, 1)
        else:
            # Single color
            emission.inputs[0].default_value = (0.0, 0.8, 1.0, 1)
        
        # Link nodes
        links = mat.node_tree.links
        if props.use_color_gradient:
            links.new(color_ramp.outputs[0], emission.inputs[0])
        links.new(emission.outputs[0], output.inputs[0])
        
        return mat

    def execute(self, context):
        props = context.scene.curl_flow_props
        random.seed(props.random_seed)
        
        # Create collection for flow lines
        flow_collection = bpy.data.collections.new("Flow_Lines")
        bpy.context.scene.collection.children.link(flow_collection)
        
        # Create material
        material = self.create_material(props)
        
        # Generate flow lines
        for i in range(props.num_lines):
            # Random starting position
            start_u = random.random()
            start_v = random.random()
            
            # Generate line points
            points = self.generate_flow_line(start_u, start_v, props)
            
            # Create curve object
            curve = self.create_curve_from_points(points, f"Flow_Line_{i}")
            curve.data.materials.append(material)
            
            # Add to collection
            flow_collection.objects.link(curve)
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_CurlFlowPanel(Panel):
    """Panel for Curl Flow Generator"""
    bl_label = "MESH Curl Flow"
    bl_idname = "ZENV_PT_curl_flow"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.curl_flow_props

        # Surface parameters
        box = layout.box()
        box.label(text="Surface:")
        box.prop(props, "surface_type")
        box.prop(props, "surface_scale")
        
        # Line parameters
        box = layout.box()
        box.label(text="Lines:")
        box.prop(props, "num_lines")
        box.prop(props, "line_length")
        box.prop(props, "line_thickness")
        box.prop(props, "use_color_gradient")
        
        # Flow parameters
        box = layout.box()
        box.label(text="Flow:")
        box.prop(props, "curl_scale")
        box.prop(props, "curl_strength")
        box.prop(props, "flow_speed")
        box.prop(props, "convergence")
        
        # Generation parameters
        box = layout.box()
        box.label(text="Generation:")
        box.prop(props, "random_seed")
        
        # Generate button
        layout.operator("zenv.curl_flow_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_CurlFlowProperties,
    ZENV_OT_CurlFlowAdd,
    ZENV_PT_CurlFlowPanel
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.curl_flow_props = PointerProperty(type=ZENV_PG_CurlFlowProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.curl_flow_props

if __name__ == "__main__":
    register()
