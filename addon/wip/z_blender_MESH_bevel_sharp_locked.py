"""
Smart Sharp Bevel
Creates clean, non-overlapping bevels by detecting edge intersections and locking them at specified minimum distances
"""

import bpy
import bmesh
import math
from mathutils import Vector, geometry
from bpy.props import FloatProperty, IntProperty, EnumProperty, BoolProperty

bl_info = {
    "name": "MESH Bevel Sharp Locked",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 2),
    "location": "View3D > ZENV",
    "description": "Create sharp, non-overlapping bevels with locked minimum distances"
}

def get_edge_angle(edge):
    """Calculate angle between faces connected to an edge"""
    if len(edge.link_faces) != 2:
        return 0
    
    face1, face2 = edge.link_faces
    return math.degrees(face1.normal.angle(face2.normal))

def find_intersecting_edges(bm, edges, min_distance):
    """Find edges that might intersect when beveled"""
    intersections = {}
    edges = set(edges)
    
    for edge1 in edges:
        for edge2 in edges:
            if edge1 != edge2:
                # Get edge vectors and midpoints
                v1 = edge1.verts[1].co - edge1.verts[0].co
                v2 = edge2.verts[1].co - edge2.verts[0].co
                m1 = (edge1.verts[0].co + edge1.verts[1].co) / 2
                m2 = (edge2.verts[0].co + edge2.verts[1].co) / 2
                
                # Check distance between edges
                dist = geometry.distance_point_to_plane(m2, m1, v1.normalized())
                if abs(dist) < min_distance:
                    key = tuple(sorted([edge1.index, edge2.index]))
                    intersections[key] = dist
    
    return intersections

def adjust_bevel_width(edge, base_width, intersections, min_distance):
    """Calculate adjusted bevel width based on intersections"""
    width = base_width
    for key in intersections:
        if edge.index in key:
            dist = abs(intersections[key])
            if dist < min_distance:
                width = min(width, dist / 2)
    return width

class ZENV_OT_BevelSharpLocked(bpy.types.Operator):
    bl_idname = "mesh.bevel_sharp_locked"
    bl_label = "Bevel Sharp Locked"
    bl_description = "Apply non-overlapping sharp bevel"
    bl_options = {'REGISTER', 'UNDO'}
    
    width: FloatProperty(
        name="Width",
        description="Bevel width",
        min=0.0001,
        max=10.0,
        default=0.1,
        unit='LENGTH'
    )
    
    segments: IntProperty(
        name="Segments",
        description="Number of bevel segments",
        min=1,
        max=10,
        default=3
    )
    
    min_distance: FloatProperty(
        name="Minimum Distance",
        description="Minimum distance between opposing bevels",
        min=0.0001,
        max=1.0,
        default=0.02,
        unit='LENGTH'
    )
    
    profile_type: EnumProperty(
        name="Profile",
        description="Bevel profile shape",
        items=[
            ('SHARP', "Sharp", "Sharp angular profile"),
            ('SMOOTH', "Smooth", "Smooth curved profile"),
            ('CUSTOM', "Custom", "Custom profile curve")
        ],
        default='SHARP'
    )
    
    auto_smooth_angle: FloatProperty(
        name="Auto Smooth Angle",
        description="Angle threshold for edge detection",
        min=0.0,
        max=180.0,
        default=30.0,
        subtype='ANGLE'
    )
    
    def execute(self, context):
        obj = context.active_object
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}
        
        # Get mesh data
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        
        # Find edges to bevel based on angle
        edges_to_bevel = [e for e in bm.edges if get_edge_angle(e) >= self.auto_smooth_angle]
        if not edges_to_bevel:
            self.report({'WARNING'}, "No edges found matching angle criteria")
            return {'CANCELLED'}
        
        # Find potential intersections
        intersections = find_intersecting_edges(bm, edges_to_bevel, self.min_distance)
        
        # Create vertex groups for varying bevel widths
        width_groups = {}
        for edge in edges_to_bevel:
            width = adjust_bevel_width(edge, self.width, intersections, self.min_distance)
            if width not in width_groups:
                width_groups[width] = []
            width_groups[width].append(edge)
        
        # Apply bevels for each width group
        for width, edges in width_groups.items():
            # Select edges for this group
            bm.select_mode = {'EDGE'}
            for edge in bm.edges:
                edge.select = edge in edges
            
            # Apply bevel
            result = bmesh.ops.bevel(
                bm,
                edges=[e for e in edges],
                offset=width,
                segments=self.segments,
                profile=1.0 if self.profile_type == 'SHARP' else 0.5,
                affect='EDGES'
            )
        
        # Update mesh
        bmesh.update_edit_mesh(obj.data)
        
        return {'FINISHED'}

class ZENV_PT_BevelSharpPanel(bpy.types.Panel):
    bl_label = "Bevel Sharp Locked"
    bl_idname = "ZENV_PT_BevelSharp"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        
        # Main operator properties
        layout.operator_context = 'INVOKE_DEFAULT'
        op = layout.operator("mesh.bevel_sharp_locked")
        
        # Bevel settings
        box = layout.box()
        box.label(text="Bevel Settings")
        box.prop(op, "width")
        box.prop(op, "segments")
        box.prop(op, "min_distance")
        box.prop(op, "profile_type")
        
        # Edge detection settings
        box = layout.box()
        box.label(text="Edge Detection")
        box.prop(op, "auto_smooth_angle")

# Registration
classes = (
    ZENV_OT_BevelSharpLocked,
    ZENV_PT_BevelSharpPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
