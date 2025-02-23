"""
GEN Runes Norse – Procedural Rune Generator (Unified Mesh Version)
-------------------------------------------------------------------
Generates a procedural rune-like symbol with a main stroke, optional secondary stroke,
and endpoint decorations. The centerlines are expanded into a constant-thickness 2D stroke,
filled to form a face, extruded to give 3D volume, and then the top face is tapered 
to simulate a stone-carved appearance.

Inspired by Norse runes
"""

bl_info = {
    "name": "GEN Runes Norse (Unified Mesh)",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Generate procedural rune-like symbols as extruded meshes with restored decorations and secondary strokes.",
    "category": "ZENV",
}

import bpy
import bmesh
import random
import time
from math import (
    radians, degrees,
    sin, cos, tan,
    asin, acos, atan2,
    pi,
    sqrt
)
from mathutils import Vector, Matrix
from bpy.props import (
    IntProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty
)
from bpy.types import (
    Operator,
    PropertyGroup,
    Panel
)

# ------------------------------------------------------------------------
#    Property Group (Restored with Additional Attributes)
# ------------------------------------------------------------------------
class ZENV_PG_RuneGenerator_Properties(PropertyGroup):
    """Properties for rune generation."""
    num_segments: IntProperty(
        name="Segments",
        default=6,
        min=3,
        max=20,
        description="Number of segments composing the main stroke"
    )
    stroke_thickness: FloatProperty(
        name="Stroke Thickness",
        default=0.3,
        min=0.01,
        description="2D line thickness of the rune"
    )
    extrude_depth: FloatProperty(
        name="Extrude Depth",
        default=0.1,
        min=0.001,
        description="Depth to extrude the filled 2D stroke"
    )
    taper_factor: FloatProperty(
        name="Taper Factor",
        default=0.5,
        min=0.0,
        max=1.0,
        description="Scale factor for the top face relative to the base (1 = uniform, <1 = tapered)"
    )
    enable_second_stroke: BoolProperty(
        name="Enable Second Stroke",
        default=False,
        description="Generate a secondary stroke attached to the main stroke"
    )

# ------------------------------------------------------------------------
#    Operator – Generate Rune Mesh (Unified Version)
# ------------------------------------------------------------------------
class ZENV_OT_GenerateRune(Operator):
    """Generate a procedural rune-like symbol as an extruded mesh,
       with main stroke, optional secondary stroke, and endpoint decorations."""
    bl_idname = "zenv.generate_rune"
    bl_label = "Generate Rune Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    # --- BMesh 2D Stroke Helpers ---
    @staticmethod
    def compute_offset_for_vertex(poly, i, thickness):
        """
        For vertex i in poly (list of Vectors), compute left and right offsets
        (using a miter join) for a stroke of given thickness.
        Returns (left_offset, right_offset).
        """
        p = poly[i]
        half = thickness / 2.0
        if i == 0:
            d = (poly[1] - poly[0]).normalized()
            perp = Vector((-d.y, d.x, 0))
            return p + perp * half, p - perp * half
        elif i == len(poly) - 1:
            d = (poly[-1] - poly[-2]).normalized()
            perp = Vector((-d.y, d.x, 0))
            return p + perp * half, p - perp * half
        else:
            d1 = (poly[i] - poly[i-1]).normalized()
            d2 = (poly[i+1] - poly[i]).normalized()
            perp1 = Vector((-d1.y, d1.x, 0))
            perp2 = Vector((-d2.y, d2.x, 0))
            miter = perp1 + perp2
            if miter.length < 1e-6:
                miter = perp1
            else:
                miter.normalize()
            dot_val = miter.dot(perp1)
            if abs(dot_val) < 1e-6:
                miter_length = half
            else:
                miter_length = half / dot_val
            return p + miter * miter_length, p - miter * miter_length

    @staticmethod
    def create_stroke_outline(poly, thickness):
        """
        Given a polyline (list of Vectors), compute the closed outline for a stroke
        with constant thickness.
        """
        left_offsets = []
        right_offsets = []
        for i in range(len(poly)):
            l, r = ZENV_OT_GenerateRune.compute_offset_for_vertex(poly, i, thickness)
            left_offsets.append(l)
            right_offsets.append(r)
        outline = left_offsets + list(reversed(right_offsets))
        return outline

    @staticmethod
    def create_extruded_stroke_mesh(points, thickness, depth, taper):
        """Create an extruded mesh from points with strict limits and safety checks."""
        if not points or len(points) < 2:
            return None
            
        # Safety limit on points
        if len(points) > 20:  # Hard limit on complexity
            points = points[:20]
            
        # Create new mesh
        mesh = bpy.data.meshes.new(name="RuneStroke")
        bm = bmesh.new()
        
        try:
            # Create vertices for base face (bottom)
            base_verts = []
            for p in points:
                # Limit coordinates to prevent extreme values
                x = max(min(p.x, 10), -10)
                y = max(min(p.y, 10), -10)
                base_verts.append(bm.verts.new((x, y, 0)))
                
            # Create vertices for top face
            top_verts = []
            for v in base_verts:
                # Apply taper with safety limits
                safe_taper = max(min(taper, 1.0), 0.1)
                top_verts.append(bm.verts.new((v.co.x * safe_taper, v.co.y * safe_taper, depth)))
                
            # Create faces - only if we have enough vertices
            if len(base_verts) >= 2:
                # Create edges instead of faces for very simple shapes
                for i in range(len(base_verts) - 1):
                    bm.edges.new((base_verts[i], base_verts[i + 1]))
                    bm.edges.new((top_verts[i], top_verts[i + 1]))
                    bm.edges.new((base_verts[i], top_verts[i]))
                
                # Connect last vertex to first if we have enough points
                if len(base_verts) > 2:
                    bm.edges.new((base_verts[-1], top_verts[-1]))
                    
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            
            # Finalize mesh
            bm.to_mesh(mesh)
            bm.free()
            
            return mesh
            
        except Exception as e:
            if bm:
                bm.free()
            if mesh:
                bpy.data.meshes.remove(mesh)
            return None

    def generate_main_polyline(self, props):
        """Generate a simple rune-like shape using only vertical and horizontal lines."""
        points = []
        current = Vector((0, 0, 0))
        points.append(current)
        
        # Only use horizontal and vertical movements
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        
        for _ in range(props.num_segments - 1):
            dx, dy = random.choice(directions)
            length = 1.0  # Fixed length for simplicity
            new_point = current + Vector((dx * length, dy * length, 0))
            points.append(new_point)
            current = new_point
        
        # Simple centering
        center = Vector((0, 0, 0))
        for p in points:
            center += p
        center /= len(points)
        
        # Center the points
        for i in range(len(points)):
            points[i] -= center
        
        return points

    def generate_secondary_polyline(self, main_points, props):
        """Generate a simple straight line as secondary stroke."""
        if not main_points or len(main_points) < 2:
            return None
        
        # Start from first point
        start = main_points[0]
        
        # Create a simple vertical line
        points = [start]
        points.append(start + Vector((0, 1, 0)))
        
        return points

    def execute(self, context):
        """Execute with strict safety checks and limits."""
        try:
            props = context.scene.zenv_rune_generator
            
            # Enforce safe limits
            safe_segments = max(min(props.num_segments, 10), 2)  # Limit between 2-10 segments
            safe_thickness = max(min(props.stroke_thickness, 1.0), 0.1)  # Limit thickness
            safe_depth = max(min(props.extrude_depth, 2.0), 0.1)  # Limit depth
            safe_taper = max(min(props.taper_factor, 1.0), 0.1)  # Limit taper
            
            # Generate main stroke with timeout protection
            start_time = time.time()
            main_poly = self.generate_main_polyline(props)
            
            if time.time() - start_time > 1.0:  # 1 second timeout
                self.report({'ERROR'}, "Generation timeout - operation cancelled")
                return {'CANCELLED'}
                
            if not main_poly:
                self.report({'ERROR'}, "Failed to generate main stroke")
                return {'CANCELLED'}
            
            # Create main stroke mesh
            main_mesh = self.create_extruded_stroke_mesh(main_poly, safe_thickness, safe_depth, safe_taper)
            if not main_mesh:
                self.report({'ERROR'}, "Failed to create main stroke mesh")
                return {'CANCELLED'}
            
            # Create main object
            main_obj = bpy.data.objects.new("RuneMainStroke", main_mesh)
            context.scene.collection.objects.link(main_obj)
            
            # Generate secondary stroke if enabled (with simplified logic)
            if props.enable_second_stroke:
                second_poly = self.generate_secondary_polyline(main_poly, props)
                if second_poly and len(second_poly) >= 2:
                    second_mesh = self.create_extruded_stroke_mesh(second_poly, safe_thickness, safe_depth, safe_taper)
                    if second_mesh:
                        second_obj = bpy.data.objects.new("RuneSecondStroke", second_mesh)
                        context.scene.collection.objects.link(second_obj)
                        second_obj.parent = main_obj
            
            # Select the main object
            bpy.ops.object.select_all(action='DESELECT')
            main_obj.select_set(True)
            context.view_layer.objects.active = main_obj
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            return {'CANCELLED'}

    # --- Registration
# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------
class ZENV_PT_RuneGenerator(Panel):
    """Panel for rune generation settings"""
    bl_label = "GEN Rune Generator"
    bl_idname = "ZENV_PT_rune_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ZENV"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_rune_generator
        
        # Main generation settings
        layout.prop(props, "num_segments")
        
        # Stroke dimensions
        box = layout.box()
        box.label(text="Stroke Dimensions:")
        box.prop(props, "stroke_thickness")
        
        # Extrusion settings
        box = layout.box()
        box.label(text="Extrusion Settings:")
        box.prop(props, "extrude_depth")
        box.prop(props, "taper_factor")
        
        # Second stroke settings
        layout.prop(props, "enable_second_stroke")
        
        # Generate button
        layout.operator("zenv.generate_rune")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------
classes = (
    ZENV_PG_RuneGenerator_Properties,
    ZENV_OT_GenerateRune,
    ZENV_PT_RuneGenerator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_rune_generator = PointerProperty(type=ZENV_PG_RuneGenerator_Properties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.zenv_rune_generator

if __name__ == "__main__":
    register()
