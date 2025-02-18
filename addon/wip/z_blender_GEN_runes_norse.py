"""
GEN Runes Norse – Procedural Rune Generator (Unified Mesh Version)
-------------------------------------------------------------------
Generates a procedural rune-like symbol with a main stroke, optional secondary stroke,
and endpoint decorations. The centerlines are expanded into a constant-thickness 2D stroke,
filled to form a face, extruded to give 3D volume, and then the top face is tapered 
to simulate a stone-carved appearance.

Inspired by Norse runes, Japanese calligraphy, and Orcish carvings.
"""

bl_info = {
    "name": "GEN Runes Norse (Unified Mesh)",
    "author": "CorvaeOboro / Updated by ChatGPT",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Generate procedural rune-like symbols as extruded meshes with restored decorations and secondary strokes.",
    "category": "ZENV",
}

import bpy, bmesh, math, random
from math import radians, cos, sin
from mathutils import Vector
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    IntProperty,
    FloatProperty,
    EnumProperty,
    BoolProperty,
    PointerProperty,
)

# ------------------------------------------------------------------------
#    BMesh 2D Stroke Helpers
# ------------------------------------------------------------------------
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

def create_stroke_outline(poly, thickness):
    """
    Given a polyline (list of Vectors), compute the closed outline for a stroke
    with constant thickness.
    """
    left_offsets = []
    right_offsets = []
    for i in range(len(poly)):
        l, r = compute_offset_for_vertex(poly, i, thickness)
        left_offsets.append(l)
        right_offsets.append(r)
    outline = left_offsets + list(reversed(right_offsets))
    return outline

def create_extruded_stroke_mesh(poly, thickness, extrude_depth, taper_factor):
    """
    Given a polyline (list of Vectors), create a 3D mesh by:
      1. Expanding the centerline into a 2D outline with constant thickness.
      2. Filling the outline to form a face.
      3. Extruding the face upward by extrude_depth.
      4. Tapering (scaling) the top face by taper_factor.
    Returns a new Mesh data-block.
    """
    bm = bmesh.new()
    outline = create_stroke_outline(poly, thickness)
    bm_verts = []
    for co in outline:
        bm_verts.append(bm.verts.new(co))
    bm.faces.new(bm_verts)
    bm.faces.ensure_lookup_table()
    face = bm.faces[0]
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    bm.verts.ensure_lookup_table()
    extruded_verts = [elem for elem in ret["geom"] if isinstance(elem, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=extruded_verts, vec=Vector((0, 0, extrude_depth)))
    bm.verts.ensure_lookup_table()
    top_verts = [v for v in extruded_verts if abs(v.co.z - extrude_depth) < 1e-3]
    if top_verts:
        centroid = Vector((0, 0, 0))
        for v in top_verts:
            centroid += v.co
        centroid /= len(top_verts)
        for v in top_verts:
            offset = v.co.xy - centroid.xy
            v.co.xy = centroid.xy + offset * taper_factor
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("RuneMesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh

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
    min_length: FloatProperty(
        name="Min Length",
        default=0.8,
        min=0.1,
        description="Minimum length of each segment"
    )
    max_length: FloatProperty(
        name="Max Length",
        default=1.5,
        min=0.1,
        description="Maximum length of each segment"
    )
    style: EnumProperty(
        name="Style",
        items=[
            ('NORSE', "Norse", "Use Norse-style allowed angles"),
            ('JAPANESE', "Japanese", "Use Japanese-style allowed angles")
        ],
        default='NORSE'
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
    endpoint_decoration: EnumProperty(
        name="Endpoint Decoration",
        items=[
            ('NONE', "None", "No endpoint decoration"),
            ('SERIF', "Serif", "Add a classic serif"),
            ('HOOK', "Hook", "Add a curved hook"),
            ('FOOT', "Foot", "Add a curved foot")
        ],
        default='NONE'
    )
    decorate_start: BoolProperty(
        name="Decorate Start",
        default=True,
        description="Apply endpoint decoration to the starting point"
    )
    decorate_end: BoolProperty(
        name="Decorate End",
        default=True,
        description="Apply endpoint decoration to the ending point"
    )
    enable_second_stroke: BoolProperty(
        name="Enable Second Stroke",
        default=False,
        description="Generate a secondary stroke attached to the main stroke"
    )
    second_stroke_segments: IntProperty(
        name="Second Stroke Segments",
        default=3,
        min=1,
        max=10,
        description="Number of segments for the secondary stroke"
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

    # --- Intersection Tests ---
    @staticmethod
    def orientation(p, q, r):
        val = (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)
        return 0 if abs(val) < 1e-6 else (1 if val > 0 else 2)

    @staticmethod
    def on_segment(p, q, r):
        return (min(p.x, r.x) - 1e-6 <= q.x <= max(p.x, r.x) + 1e-6 and
                min(p.y, r.y) - 1e-6 <= q.y <= max(p.y, r.y) + 1e-6)

    @staticmethod
    def segments_intersect(p1, q1, p2, q2):
        o1 = ZENV_OT_GenerateRune.orientation(p1, q1, p2)
        o2 = ZENV_OT_GenerateRune.orientation(p1, q1, q2)
        o3 = ZENV_OT_GenerateRune.orientation(p2, q2, p1)
        o4 = ZENV_OT_GenerateRune.orientation(p2, q2, q1)
        if o1 != o2 and o3 != o4:
            return True
        if o1 == 0 and ZENV_OT_GenerateRune.on_segment(p1, p2, q1): return True
        if o2 == 0 and ZENV_OT_GenerateRune.on_segment(p1, q2, q1): return True
        if o3 == 0 and ZENV_OT_GenerateRune.on_segment(p2, p1, q2): return True
        if o4 == 0 and ZENV_OT_GenerateRune.on_segment(p2, q1, q2): return True
        return False

    @staticmethod
    def check_new_segment_intersections(a, b, segments):
        for (p, q) in segments:
            if (a - p).length < 1e-6 or (a - q).length < 1e-6 or (b - p).length < 1e-6 or (b - q).length < 1e-6:
                continue
            if ZENV_OT_GenerateRune.segments_intersect(a, b, p, q):
                return True
        return False

    # --- Polyline Generation for Main Stroke ---
    def generate_main_polyline(self, props, MAX_ASPECT_RATIO=1.5, TARGET_SIZE=2.0):
        points = []
        segments = []
        current_point = Vector((0, 0, 0))
        points.append(current_point.copy())
        current_direction = Vector((1, 0, 0))
        if props.style == 'NORSE':
            allowed_angles = [0,45,90,135,180,225,270,315]
        else:
            allowed_angles = [0,45,90,135,180]
        for i in range(props.num_segments):
            valid_segment = False
            attempts = 0
            while not valid_segment and attempts < 12:
                attempts += 1
                min_x, max_x, min_y, max_y = self.compute_bounding_box(points)
                width = max_x - min_x
                height = max_y - min_y
                candidate_angles = allowed_angles.copy()
                if width > height * MAX_ASPECT_RATIO:
                    candidate_angles = [a for a in allowed_angles if abs(sin(radians(a))) >= 0.7]
                    if not candidate_angles:
                        candidate_angles = allowed_angles.copy()
                elif height > width * MAX_ASPECT_RATIO:
                    candidate_angles = [a for a in allowed_angles if abs(cos(radians(a))) >= 0.7]
                    if not candidate_angles:
                        candidate_angles = allowed_angles.copy()
                angle = random.choice(candidate_angles)
                direction = Vector((cos(radians(angle)), sin(radians(angle)), 0))
                direction = (direction + current_direction * 0.3).normalized()
                scale_factor = 1.0
                if max(width, height) > TARGET_SIZE:
                    scale_factor = 0.5
                length = random.uniform(props.min_length, props.max_length) * scale_factor
                candidate_point = current_point + direction * length
                if self.check_new_segment_intersections(current_point, candidate_point, segments):
                    continue
                new_points = points + [candidate_point]
                nmin_x, nmax_x, nmin_y, nmax_y = self.compute_bounding_box(new_points)
                new_width = nmax_x - nmin_x
                new_height = nmax_y - nmin_y
                if new_width > 0 and new_height > 0:
                    aspect = new_width / new_height if new_width > new_height else new_height / new_width
                    if aspect > MAX_ASPECT_RATIO:
                        continue
                segments.append((current_point.copy(), candidate_point.copy()))
                points.append(candidate_point.copy())
                current_point = candidate_point.copy()
                current_direction = direction.copy()
                valid_segment = True
            if not valid_segment:
                self.report({'WARNING'}, f"Stopped main stroke at segment {i} due to constraints.")
                break
        points = self.normalize_and_scale_points(points, TARGET_SIZE)
        return points

    # --- Polyline Generation for Secondary Stroke ---
    def generate_secondary_polyline(self, main_points, props):
        if len(main_points) < 3:
            return None
        anchor_index = random.randint(1, len(main_points)-2)
        anchor = main_points[anchor_index].copy()
        if anchor_index < len(main_points)-1:
            init_dir = (main_points[anchor_index+1] - anchor).normalized()
        else:
            init_dir = (anchor - main_points[anchor_index-1]).normalized()
        current_point = anchor.copy()
        sec_points = [current_point.copy()]
        sec_segments = []
        current_direction = init_dir.copy()
        if props.style == 'NORSE':
            allowed_angles = [0,45,90,135,180,225,270,315]
        else:
            allowed_angles = [0,45,90,135,180]
        for i in range(props.second_stroke_segments):
            valid = False
            attempts = 0
            while not valid and attempts < 12:
                attempts += 1
                angle = random.choice(allowed_angles)
                direction = Vector((cos(radians(angle)), sin(radians(angle)), 0))
                direction = (direction + current_direction * 0.3).normalized()
                length = random.uniform(props.min_length, props.max_length) * 0.8
                candidate = current_point + direction * length
                if self.check_new_segment_intersections(current_point, candidate, sec_segments):
                    continue
                sec_segments.append((current_point.copy(), candidate.copy()))
                sec_points.append(candidate.copy())
                current_point = candidate.copy()
                current_direction = direction.copy()
                valid = True
            if not valid:
                self.report({'WARNING'}, f"Stopped second stroke at segment {i} due to constraints.")
                break
        return sec_points

    # --- Endpoint Decoration ---
    def generate_decoration_polyline(self, anchor, direction, deco_type, bevel_depth):
        return self.create_decoration_points(anchor, direction, deco_type, bevel_depth)

    # --- Utility: Bounding Box and Normalization ---
    def compute_bounding_box(self, points):
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        return min_x, max_x, min_y, max_y

    def normalize_and_scale_points(self, points, target_size=2.0):
        min_x, max_x, min_y, max_y = self.compute_bounding_box(points)
        center = Vector(((min_x+max_x)*0.5, (min_y+max_y)*0.5, 0))
        for i in range(len(points)):
            points[i] -= center
        width = max_x - min_x
        height = max_y - min_y
        scale = target_size / max(width, height) if max(width, height) > 0 else 1.0
        for i in range(len(points)):
            points[i] *= scale
        return points

    # --- Decoration Function ---
    def create_decoration_points(self, location, direction, decoration_type, bevel_depth):
        if direction.length == 0:
            direction = Vector((1,0,0))
        else:
            direction.normalize()
        if decoration_type == 'SERIF':
            perp = Vector((-direction.y, direction.x, 0))
            scale = bevel_depth * 4
            pts = [location + direction * scale * 0.5,
                   location + perp * scale * 0.3,
                   location - direction * scale * 0.2]
        elif decoration_type == 'HOOK':
            perp = Vector((-direction.y, direction.x, 0))
            scale = bevel_depth * 5
            pts = [location + direction * scale * 0.8,
                   location + direction * scale * 0.4 + perp * scale * 0.6,
                   location + perp * scale * 0.8,
                   location - direction * scale * 0.2 + perp * scale * 0.4]
        elif decoration_type == 'FOOT':
            perp = Vector((-direction.y, direction.x, 0))
            scale = bevel_depth * 4
            pts = [location + direction * scale * 0.5,
                   location + direction * scale * 0.2 - perp * scale * 0.4,
                   location - direction * scale * 0.3 - perp * scale * 0.6,
                   location - direction * scale * 0.6 - perp * scale * 0.3]
        else:
            pts = []
        return pts

    # --- Main Execute ---
    def execute(self, context):
        try:
            props = context.scene.zenv_rune_props
            MAX_ASPECT_RATIO = 1.5
            TARGET_SIZE = 2.0

            mesh_objs = []

            # Generate main stroke polyline.
            main_poly = self.generate_main_polyline(props, MAX_ASPECT_RATIO, TARGET_SIZE)
            if not main_poly or len(main_poly) < 2:
                self.report({'ERROR'}, "Insufficient points for main stroke.")
                return {'CANCELLED'}
            main_mesh = create_extruded_stroke_mesh(main_poly, props.stroke_thickness, props.extrude_depth, props.taper_factor)
            main_obj = bpy.data.objects.new("RuneMain", main_mesh)
            context.collection.objects.link(main_obj)
            mesh_objs.append(main_obj)

            # Generate secondary stroke if enabled.
            sec_poly = None
            if props.enable_second_stroke:
                sec_poly = self.generate_secondary_polyline(main_poly, props)
                if sec_poly and len(sec_poly) >= 2:
                    sec_mesh = create_extruded_stroke_mesh(sec_poly, props.stroke_thickness, props.extrude_depth, props.taper_factor)
                    sec_obj = bpy.data.objects.new("RuneSecond", sec_mesh)
                    context.collection.objects.link(sec_obj)
                    mesh_objs.append(sec_obj)

            # Generate endpoint decorations if enabled.
            if props.endpoint_decoration != 'NONE' and len(main_poly) >= 2:
                # Start decoration.
                if props.decorate_start:
                    start_dir = (main_poly[1] - main_poly[0]).normalized()
                    start_deco = self.generate_decoration_polyline(main_poly[0].copy(), start_dir, props.endpoint_decoration, props.bevel_depth)
                    if start_deco and len(start_deco) >= 2:
                        deco_mesh = create_extruded_stroke_mesh(start_deco, props.stroke_thickness, props.extrude_depth, props.taper_factor)
                        deco_obj = bpy.data.objects.new("RuneDecoStart", deco_mesh)
                        context.collection.objects.link(deco_obj)
                        mesh_objs.append(deco_obj)
                # End decoration.
                if props.decorate_end:
                    end_dir = (main_poly[-1] - main_poly[-2]).normalized()
                    end_deco = self.generate_decoration_polyline(main_poly[-1].copy(), end_dir, props.endpoint_decoration, props.bevel_depth)
                    if end_deco and len(end_deco) >= 2:
                        deco_mesh = create_extruded_stroke_mesh(end_deco, props.stroke_thickness, props.extrude_depth, props.taper_factor)
                        deco_obj = bpy.data.objects.new("RuneDecoEnd", deco_mesh)
                        context.collection.objects.link(deco_obj)
                        mesh_objs.append(deco_obj)

            # Join all generated parts into one mesh if more than one exists.
            if len(mesh_objs) > 1:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in mesh_objs:
                    obj.select_set(True)
                context.view_layer.objects.active = mesh_objs[0]
                bpy.ops.object.join()

            final_obj = context.view_layer.objects.active
            final_obj.name = "RuneMesh"
            bpy.ops.object.select_all(action='DESELECT')
            final_obj.select_set(True)
            context.view_layer.objects.active = final_obj

            self.report({'INFO'}, "Generated rune mesh successfully.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error generating rune: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------
class ZENV_PT_RuneGeneratorPanel(Panel):
    """Panel for rune generation settings."""
    bl_label = "Rune Generator (Mesh)"
    bl_idname = "ZENV_PT_rune_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_rune_props

        col = layout.column(align=True)
        col.prop(props, "num_segments")
        col.prop(props, "min_length")
        col.prop(props, "max_length")
        col.prop(props, "style")
        layout.prop(props, "stroke_thickness")
        layout.prop(props, "extrude_depth")
        layout.prop(props, "taper_factor")
        layout.prop(props, "endpoint_decoration")
        if props.endpoint_decoration != 'NONE':
            row = layout.row(align=True)
            row.prop(props, "decorate_start")
            row.prop(props, "decorate_end")
        layout.prop(props, "enable_second_stroke")
        if props.enable_second_stroke:
            layout.prop(props, "second_stroke_segments")
        layout.operator("zenv.generate_rune", text="Generate Rune Mesh")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------
classes = (
    ZENV_PG_RuneGenerator_Properties,
    ZENV_OT_GenerateRune,
    ZENV_PT_RuneGeneratorPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_rune_props = PointerProperty(type=ZENV_PG_RuneGenerator_Properties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.zenv_rune_props

if __name__ == "__main__":
    register()
