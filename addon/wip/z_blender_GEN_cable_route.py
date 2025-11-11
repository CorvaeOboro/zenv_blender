"""
CABLE ROUTE GENERATOR
Projects and routes cables along surfaces with proper overlapping and stacking behavior
"""

bl_info = {
    "name": 'GEN Cable Route',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Generate cable routes with proper overlapping',
    "status": 'wip',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_line
from mathutils.kdtree import KDTree
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty, CollectionProperty, FloatVectorProperty
from bpy.types import PropertyGroup, Operator, Panel, Object

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_CableProperties(PropertyGroup):
    """Properties for individual cables"""
    thickness: FloatProperty(
        name="Cable Thickness",
        description="Thickness of the cable",
        default=0.02,
        min=0.001,
        max=0.1
    )
    color: FloatVectorProperty(
        name="Cable Color",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8),
        min=0,
        max=1
    )
    subdivision: IntProperty(
        name="Subdivision",
        description="Number of subdivisions along cable",
        default=100,
        min=10,
        max=500
    )
    priority: IntProperty(
        name="Priority",
        description="Cable stacking priority (higher numbers stack on top)",
        default=1,
        min=1,
        max=100
    )

class ZENV_PG_CableRouteProperties(PropertyGroup):
    """Properties for the Cable Route Generator"""
    floor_object: StringProperty(
        name="Floor Object",
        description="Object to project cables onto"
    )
    spacing_factor: FloatProperty(
        name="Spacing Factor",
        description="Factor for spacing between overlapping cables",
        default=1.2,
        min=1.0,
        max=2.0
    )
    smooth_iterations: IntProperty(
        name="Smooth Iterations",
        description="Number of smoothing iterations for cable paths",
        default=5,
        min=0,
        max=20
    )
    use_gravity_points: BoolProperty(
        name="Use Gravity Points",
        description="Add extra weight points to keep cables down",
        default=True
    )
    gravity_strength: FloatProperty(
        name="Gravity Strength",
        description="Strength of downward force on cables",
        default=0.5,
        min=0.0,
        max=1.0
    )
    bevel_resolution: IntProperty(
        name="Bevel Resolution",
        description="Resolution of cable beveling",
        default=6,
        min=2,
        max=12
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_CableRouteAdd(Operator):
    """Create cable routes with proper overlapping"""
    bl_idname = "zenv.cable_route_add"
    bl_label = "Generate Cable Routes"
    bl_options = {'REGISTER', 'UNDO'}

    def subdivide_curve(self, curve_obj, subdivisions):
        """Subdivide curve to increase point density"""
        curve = curve_obj.data
        
        # Convert to mesh to subdivide
        mesh = bpy.data.meshes.new("temp_mesh")
        bm = bmesh.new()
        bm.from_object(curve_obj, bpy.context.evaluated_depsgraph_get())
        
        # Subdivide
        for _ in range(subdivisions):
            bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1)
        
        # Convert back to curve
        bm.to_mesh(mesh)
        bm.free()
        
        # Create new curve from mesh points
        new_curve = bpy.data.curves.new(name="Dense_Curve", type='CURVE')
        new_curve.dimensions = '3D'
        
        spline = new_curve.splines.new('POLY')
        spline.points.add(len(mesh.vertices) - 1)
        
        for i, vert in enumerate(mesh.vertices):
            spline.points[i].co = (*vert.co, 1)
        
        bpy.data.meshes.remove(mesh)
        return new_curve

    def project_to_surface(self, point, surface_obj):
        """Project point onto surface using raycast"""
        # Convert point to surface local space
        local_point = surface_obj.matrix_world.inverted() @ Vector(point)
        
        # Cast ray from above point
        hit, location, normal, _ = surface_obj.ray_cast(
            local_point + Vector((0, 0, 1)),
            Vector((0, 0, -2))
        )
        
        if hit:
            # Convert back to world space
            return surface_obj.matrix_world @ location, surface_obj.matrix_world.to_3x3() @ normal
        return None, None

    def find_intersections(self, curves):
        """Find intersection points between curves"""
        intersections = []
        
        for i, curve1 in enumerate(curves):
            for j, curve2 in enumerate(curves):
                if i >= j:
                    continue
                    
                # Check each segment pair
                for k in range(len(curve1.points) - 1):
                    for l in range(len(curve2.points) - 1):
                        p1 = curve1.points[k].co.xyz
                        p2 = curve1.points[k+1].co.xyz
                        p3 = curve2.points[l].co.xyz
                        p4 = curve2.points[l+1].co.xyz
                        
                        # Find intersection
                        intersection = intersect_line_line(p1, p2, p3, p4)
                        if intersection:
                            intersections.append({
                                'point': (intersection[0] + intersection[1]) / 2,
                                'curves': (i, j),
                                'segments': (k, l)
                            })
        
        return intersections

    def adjust_heights(self, curves, intersections, props):
        """Adjust curve heights at intersections"""
        # Sort curves by priority
        curve_priorities = [(i, c.cable_props.priority) for i, c in enumerate(curves)]
        curve_priorities.sort(key=lambda x: x[1])
        
        # Create height map for each curve
        height_maps = [np.zeros(len(c.points)) for c in curves]
        
        # Process intersections
        for intersection in intersections:
            point = intersection['point']
            curve1_idx, curve2_idx = intersection['curves']
            
            # Determine which curve goes on top
            if curve_priorities.index((curve1_idx, curves[curve1_idx].cable_props.priority)) > \
               curve_priorities.index((curve2_idx, curves[curve2_idx].cable_props.priority)):
                top_curve = curve1_idx
                bottom_curve = curve2_idx
            else:
                top_curve = curve2_idx
                bottom_curve = curve1_idx
            
            # Calculate offset
            offset = (curves[bottom_curve].cable_props.thickness + 
                     curves[top_curve].cable_props.thickness) * props.spacing_factor
            
            # Apply height offset around intersection
            radius = max(curves[top_curve].cable_props.thickness,
                        curves[bottom_curve].cable_props.thickness) * 5
            
            for i, curve_points in enumerate(curves[top_curve].points):
                dist = (curve_points.co.xyz - point).length
                if dist < radius:
                    falloff = 1 - (dist / radius)
                    height_maps[top_curve][i] = max(
                        height_maps[top_curve][i],
                        offset * falloff
                    )
        
        # Apply height maps to curves
        for i, curve in enumerate(curves):
            for j, point in enumerate(curve.points):
                point.co.z += height_maps[i][j]

    def smooth_curves(self, curves, iterations):
        """Smooth curve points"""
        for curve in curves:
            for _ in range(iterations):
                points = [p.co.copy() for p in curve.points]
                
                for i in range(1, len(curve.points) - 1):
                    curve.points[i].co = (points[i-1] + points[i] + points[i+1]) / 3

    def create_cable_mesh(self, curve, props):
        """Create final cable mesh with thickness"""
        # Create curve object
        curve_obj = bpy.data.objects.new("Cable_Curve", curve)
        bpy.context.collection.objects.link(curve_obj)
        
        # Add bevel
        curve.bevel_depth = curve.cable_props.thickness
        curve.bevel_resolution = props.bevel_resolution
        
        # Create material
        mat = bpy.data.materials.new(name="Cable_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Set material properties
        principled.inputs['Base Color'].default_value = (*curve.cable_props.color, 1)
        principled.inputs['Roughness'].default_value = 0.3
        principled.inputs['Specular'].default_value = 0.5
        
        # Link nodes
        mat.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        curve_obj.data.materials.append(mat)
        
        return curve_obj

    def execute(self, context):
        props = context.scene.cable_route_props
        
        # Get floor object
        floor_obj = bpy.data.objects.get(props.floor_object)
        if not floor_obj:
            self.report({'ERROR'}, "Please select a floor object")
            return {'CANCELLED'}
        
        # Get selected curves
        curves = [obj for obj in context.selected_objects 
                 if obj.type == 'CURVE' and obj != floor_obj]
        
        if not curves:
            self.report({'ERROR'}, "Please select at least one curve")
            return {'CANCELLED'}
        
        # Process each curve
        dense_curves = []
        for curve_obj in curves:
            # Subdivide curve
            dense_curve = self.subdivide_curve(
                curve_obj,
                curve_obj.cable_props.subdivision
            )
            
            # Project points onto surface
            for point in dense_curve.splines[0].points:
                hit_point, normal = self.project_to_surface(point.co, floor_obj)
                if hit_point:
                    point.co = (*hit_point, 1)
            
            dense_curves.append(dense_curve)
        
        # Find intersections
        intersections = self.find_intersections(dense_curves)
        
        # Adjust heights at intersections
        self.adjust_heights(dense_curves, intersections, props)
        
        # Smooth curves
        if props.smooth_iterations > 0:
            self.smooth_curves(dense_curves, props.smooth_iterations)
        
        # Create final cable meshes
        cable_objects = []
        for curve in dense_curves:
            cable_obj = self.create_cable_mesh(curve, props)
            cable_objects.append(cable_obj)
        
        # Select cable objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in cable_objects:
            obj.select_set(True)
        context.view_layer.objects.active = cable_objects[0]
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_CableRoutePanel(Panel):
    """Panel for Cable Route Generator"""
    bl_label = "GEN Cable Route"
    bl_idname = "ZENV_PT_cable_route"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.cable_route_props

        # Floor object selection
        layout.prop_search(props, "floor_object", bpy.data, "objects")
        
        # Selected curve properties
        box = layout.box()
        box.label(text="Selected Cable Properties:")
        
        for obj in context.selected_objects:
            if obj.type == 'CURVE':
                row = box.row()
                row.label(text=obj.name)
                col = row.column()
                col.prop(obj.cable_props, "thickness")
                col.prop(obj.cable_props, "color")
                col.prop(obj.cable_props, "priority")
                col.prop(obj.cable_props, "subdivision")
        
        # Route parameters
        box = layout.box()
        box.label(text="Route Parameters:")
        box.prop(props, "spacing_factor")
        box.prop(props, "smooth_iterations")
        box.prop(props, "bevel_resolution")
        
        # Gravity parameters
        box = layout.box()
        box.label(text="Gravity Settings:")
        box.prop(props, "use_gravity_points")
        if props.use_gravity_points:
            box.prop(props, "gravity_strength")
        
        # Generate button
        layout.operator("zenv.cable_route_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_CableProperties,
    ZENV_PG_CableRouteProperties,
    ZENV_OT_CableRouteAdd,
    ZENV_PT_CableRoutePanel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cable_route_props = PointerProperty(type=ZENV_PG_CableRouteProperties)
    bpy.types.Curve.cable_props = PointerProperty(type=ZENV_PG_CableProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cable_route_props
    del bpy.types.Curve.cable_props

if __name__ == "__main__":
    register()
