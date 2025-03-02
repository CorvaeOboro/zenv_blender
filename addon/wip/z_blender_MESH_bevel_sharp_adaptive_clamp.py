"""
MESH Bevel Sharp Adaptive Clamp
Creates clean, non-overlapping bevels by detecting edge intersections and adaptively adjusting bevel widths
"""

import bpy
import bmesh
import math
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, BoolProperty, IntProperty, EnumProperty, PointerProperty

bl_info = {
    "name": "MESH Bevel Sharp Adaptive Clamp",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Add adaptive bevels to sharp edges with dynamic overlap prevention",
}

class ZENV_PG_bevel_sharp_adaptive_clamp(bpy.types.PropertyGroup):
    """Property group for adaptive bevel settings with angle-based clamping"""
    sharp_angle: FloatProperty(
        name="Sharp Angle",
        description="Angle threshold for sharp edges (degrees)",
        default=60.0,
        min=0.0,
        max=180.0
    )
    max_bevel_width: FloatProperty(
        name="Max Bevel Width",
        description="Maximum bevel width",
        default=1.0,
        min=0.0001,
        max=10.0
    )
    min_bevel_width: FloatProperty(
        name="Min Bevel Width",
        description="Minimum allowed bevel width",
        default=0.001,
        min=0.0001,
        max=0.1
    )
    segments: IntProperty(
        name="Segments",
        description="Number of bevel segments",
        default=1,
        min=1,
        max=10
    )

class ZENV_OT_BevelSharpAdaptiveClamp_Apply(bpy.types.Operator):
    """Add adaptive bevels to sharp edges with dynamic overlap prevention"""
    bl_idname = "zenv.bevel_sharp_adaptive_clamp"
    bl_label = "Bevel Sharp Adaptive Clamp"
    bl_options = {'REGISTER', 'UNDO'}

    def get_edge_angle(self, edge):
        """Get angle between faces connected to edge"""
        if len(edge.link_faces) != 2:
            return 0
        
        vec1 = edge.link_faces[0].normal
        vec2 = edge.link_faces[1].normal
        angle = vec1.angle(vec2)
        return math.degrees(angle)

    def get_edge_midpoint(self, edge):
        """Get the midpoint of an edge"""
        return (edge.verts[0].co + edge.verts[1].co) / 2

    def check_edge_intersection(self, edge1, edge2, width1, width2):
        """Check if two edges would intersect when beveled"""
        # Only check edges that share a vertex
        if not (set(edge1.verts) & set(edge2.verts)):
            return False
        
        # Get edge midpoints
        mid1 = self.get_edge_midpoint(edge1)
        mid2 = self.get_edge_midpoint(edge2)
        
        # Calculate distance between midpoints
        dist = (mid1 - mid2).length
        
        # Check if the combined bevel widths would overlap
        return dist < (width1 + width2)

    def create_bevel_geometry(self, bm, edge, width, segments):
        """Create bevel geometry for an edge using bmesh operators"""
        if not edge.is_valid:
            return
            
        # Use bmesh's built-in bevel operator
        result = bmesh.ops.bevel(
            bm,
            geom=[edge],
            offset=width,
            offset_type='WIDTH',
            segments=segments,
            profile=0.5,  # 0.5 gives a circular profile
            affect='EDGES'
        )
        
        # Mark new edges as sharp
        for new_edge in result['edges']:
            if new_edge.is_valid:
                new_edge.smooth = False
        
        # Ensure mesh topology is updated
        bm.edges.index_update()
        bm.faces.index_update()
        bm.verts.index_update()

    def calculate_adaptive_bevel_widths(self, bm, sharp_edges, max_width):
        """Calculate adaptive bevel widths for each edge"""
        edge_widths = {edge: max_width for edge in sharp_edges}
        props = bpy.context.scene.properties
        
        # Iteratively adjust widths to prevent intersections
        max_iterations = 20
        for iteration in range(max_iterations):
            changes_made = False
            
            for edge1 in sharp_edges:
                for edge2 in sharp_edges:
                    if edge1 != edge2:
                        if self.check_edge_intersection(edge1, edge2, edge_widths[edge1], edge_widths[edge2]):
                            # Reduce width more gradually
                            new_width1 = edge_widths[edge1] * 0.9
                            new_width2 = edge_widths[edge2] * 0.9
                            
                            if new_width1 >= props.min_bevel_width:
                                edge_widths[edge1] = new_width1
                                changes_made = True
                            
                            if new_width2 >= props.min_bevel_width:
                                edge_widths[edge2] = new_width2
                                changes_made = True
            
            if not changes_made:
                break
        
        return edge_widths

    def execute(self, context):
        try:
            active_obj = context.active_object
            
            if not active_obj or active_obj.type != 'MESH':
                self.report({'ERROR'}, "Active object must be a mesh")
                return {'CANCELLED'}
            
            # Store current mode
            current_mode = active_obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(active_obj.data)
            bm.edges.ensure_lookup_table()
            
            # Find sharp edges
            sharp_edges = []
            props = context.scene.properties
            for edge in bm.edges:
                angle = self.get_edge_angle(edge)
                if angle > props.sharp_angle:
                    sharp_edges.append(edge)
                    edge.smooth = False
            
            if not sharp_edges:
                self.report({'INFO'}, "No sharp edges found")
                bm.free()
                return {'CANCELLED'}
            
            # Calculate adaptive bevel widths
            edge_widths = self.calculate_adaptive_bevel_widths(
                bm, 
                sharp_edges, 
                props.max_bevel_width
            )
            
            # Bevel edges in order of width (largest first)
            sorted_edges = sorted(
                sharp_edges, 
                key=lambda e: edge_widths[e], 
                reverse=True
            )
            
            # Process each edge
            for edge in sorted_edges:
                if edge.is_valid:
                    self.create_bevel_geometry(
                        bm, 
                        edge, 
                        edge_widths[edge],
                        props.segments
                    )
            
            # Final cleanup
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0001)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            
            # Update mesh
            bm.to_mesh(active_obj.data)
            active_obj.data.update()
            bm.free()
            
            # Restore original mode
            bpy.ops.object.mode_set(mode=current_mode)
            
            self.report({'INFO'}, f"Applied adaptive bevel to {len(sharp_edges)} edges")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, str(e))
            if 'bm' in locals():
                bm.free()
            return {'CANCELLED'}

class ZENV_PT_BevelSharpAdaptiveClamp_Panel(bpy.types.Panel):
    """Panel for controlling adaptive bevel settings with angle-based clamping for sharp edges"""
    bl_label = "MESH Bevel Sharp Adaptive"
    bl_idname = "ZENV_PT_bevel_sharp_adaptive_clamp"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.properties
        
        col = layout.column(align=True)
        col.prop(props, "sharp_angle")
        col.prop(props, "max_bevel_width")
        col.prop(props, "min_bevel_width")
        col.prop(props, "segments")
        
        layout.operator("zenv.bevel_sharp_adaptive_clamp")

classes = (
    ZENV_PG_bevel_sharp_adaptive_clamp,
    ZENV_OT_BevelSharpAdaptiveClamp_Apply,
    ZENV_PT_BevelSharpAdaptiveClamp_Panel
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.properties = PointerProperty(type=ZENV_PG_bevel_sharp_adaptive_clamp)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.properties

if __name__ == "__main__":
    register()
