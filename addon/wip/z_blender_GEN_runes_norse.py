#region META
bl_info = {
    "name": 'GEN Runes Norse',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate procedural rune-like symbols as extruded meshes with stroke thickness, taper, and optional secondary stroke.',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['generative', 'rune', 'norse', 'procedural', 'mesh', 'symbol'],
    "description_short": 'Generate procedural rune-like symbols as extruded meshes',
    "description_medium": 'Generates rune-like symbols by creating a random orthogonal polyline, expanding it into a constant-thickness 2D stroke, filling it into a face, extruding to 3D, and tapering the top face for a stone-carved look. Supports optional secondary stroke and deterministic output via random seed.',
    "description_long": """
    GEN Runes Norse
    Generates procedural rune-like symbols as extruded meshes. The main
    stroke is a random orthogonal polyline that is expanded into a
    constant-thickness 2D outline using miter joins, filled into a face,
    extruded to 3D, and tapered at the top for a carved-stone appearance.
    An optional secondary stroke can be attached. Output is deterministic
    via a configurable random seed.""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_GEN_runes_norse.png',
    "addon_image": 'zenv_blender_GEN_runes_norse.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import random
import logging
from mathutils import Vector
from bpy.props import (
    IntProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
)
from bpy.types import (
    Operator,
    PropertyGroup,
    Panel,
)

logger = logging.getLogger(__name__)
_zenv_runes_console_handler = None

#endregion
#region PROPS
class ZENV_PG_RuneGenerator(PropertyGroup):
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
        max=2.0,
        description="2D line thickness of the rune"
    )
    extrude_depth: FloatProperty(
        name="Extrude Depth",
        default=0.1,
        min=0.001,
        max=2.0,
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
    second_stroke_length: FloatProperty(
        name="Second Stroke Length",
        default=1.0,
        min=0.1,
        max=5.0,
        description="Length of the secondary stroke"
    )
    random_seed: IntProperty(
        name="Random Seed",
        default=42,
        min=0,
        max=999999,
        description="Seed for deterministic rune generation"
    )

#endregion
#region UTILS
class ZENV_Rune_Utils:
    """Utility functions for rune generation."""

    @staticmethod
    def compute_offset_for_vertex(poly, i, thickness):
        """For vertex i in poly, compute left and right offsets using miter join.

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
            d1 = (poly[i] - poly[i - 1]).normalized()
            d2 = (poly[i + 1] - poly[i]).normalized()
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
        """Given a polyline, compute the closed outline for a constant-thickness stroke.

        The outline is a closed polygon: left offsets forward, then right
        offsets reversed.
        """
        if not poly or len(poly) < 2:
            return []

        left_offsets = []
        right_offsets = []
        for i in range(len(poly)):
            l, r = ZENV_Rune_Utils.compute_offset_for_vertex(poly, i, thickness)
            left_offsets.append(l)
            right_offsets.append(r)
        outline = left_offsets + list(reversed(right_offsets))
        return outline

    @staticmethod
    def create_extruded_stroke_mesh(outline_points, depth, taper):
        """Create an extruded mesh from a closed 2D outline.

        Creates side faces (quads), a bottom cap, and a tapered top cap.
        The taper scales vertices toward the outline's centroid.
        """
        if not outline_points or len(outline_points) < 3:
            return None

        # Compute centroid for proper tapering.
        cx = sum(p.x for p in outline_points) / len(outline_points)
        cy = sum(p.y for p in outline_points) / len(outline_points)
        centroid = Vector((cx, cy, 0))

        mesh = bpy.data.meshes.new(name="RuneStroke")
        bm = bmesh.new()

        try:
            # Create base (bottom) vertices.
            base_verts = []
            for p in outline_points:
                x = max(min(p.x, 10), -10)
                y = max(min(p.y, 10), -10)
                base_verts.append(bm.verts.new((x, y, 0)))

            # Create top vertices - tapered toward centroid.
            safe_taper = max(min(taper, 1.0), 0.1)
            top_verts = []
            for v in base_verts:
                offset = v.co - centroid
                tapered = centroid + offset * safe_taper
                top_verts.append(bm.verts.new((tapered.x, tapered.y, depth)))

            n = len(base_verts)

            # Create side faces (quads).
            for i in range(n):
                next_i = (i + 1) % n
                bm.faces.new((
                    base_verts[i],
                    base_verts[next_i],
                    top_verts[next_i],
                    top_verts[i],
                ))

            # Create bottom cap face (reversed for correct normal).
            bm.faces.new(list(reversed(base_verts)))

            # Create top cap face.
            bm.faces.new(top_verts)

            bm.normal_update()
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()

            return mesh

        except Exception:
            try:
                bm.free()
            except Exception:
                pass
            try:
                bpy.data.meshes.remove(mesh)
            except Exception:
                pass
            return None

    @staticmethod
    def generate_main_polyline(num_segments, rng):
        """Generate a rune-like orthogonal polyline.

        Prevents immediate backtracking. Returns a list of Vector points
        centered around the origin.
        """
        points = []
        current = Vector((0, 0, 0))
        points.append(current)

        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        last_dir = None

        for _ in range(num_segments - 1):
            # Filter out the reverse of the last direction to prevent
            # immediate backtracking.
            available = directions
            if last_dir is not None:
                reverse = (-last_dir[0], -last_dir[1])
                available = [d for d in directions if d != reverse]

            dx, dy = rng.choice(available)
            length = 1.0
            new_point = current + Vector((dx * length, dy * length, 0))
            points.append(new_point)
            current = new_point
            last_dir = (dx, dy)

        # Center the points around the origin.
        center = Vector((0, 0, 0))
        for p in points:
            center += p
        center /= len(points)

        for i in range(len(points)):
            points[i] = points[i] - center

        return points

    @staticmethod
    def generate_secondary_polyline(main_points, length, rng):
        """Generate a secondary stroke from the first point of the main stroke.

        Uses the provided length and a random orthogonal direction.
        """
        if not main_points or len(main_points) < 2:
            return None

        start = main_points[0]
        # Choose a random orthogonal direction.
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        dx, dy = rng.choice(directions)
        end = start + Vector((dx * length, dy * length, 0))

        return [start, end]

#endregion
#region OP
class ZENV_OT_GenerateRune(Operator):
    """Generate a procedural rune-like symbol as an extruded mesh,
    with main stroke, optional secondary stroke, and endpoint decorations."""
    bl_idname = "zenv.generate_rune"
    bl_label = "Generate Rune Mesh"
    bl_description = "Generate a procedural rune-like symbol as an extruded mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        try:
            props = context.scene.zenv_rune_generator

            # Seed the RNG for deterministic output.
            rng = random.Random(props.random_seed)

            # Generate main stroke polyline.
            main_poly = ZENV_Rune_Utils.generate_main_polyline(props.num_segments, rng)

            if not main_poly or len(main_poly) < 2:
                self.report({'ERROR'}, "Failed to generate main stroke")
                return {'CANCELLED'}

            # Expand polyline into a thick outline.
            outline = ZENV_Rune_Utils.create_stroke_outline(
                main_poly, props.stroke_thickness
            )

            if not outline or len(outline) < 3:
                self.report({'ERROR'}, "Failed to create stroke outline")
                return {'CANCELLED'}

            # Create extruded mesh from outline.
            main_mesh = ZENV_Rune_Utils.create_extruded_stroke_mesh(
                outline, props.extrude_depth, props.taper_factor
            )
            if not main_mesh:
                self.report({'ERROR'}, "Failed to create main stroke mesh")
                return {'CANCELLED'}

            # Create main object.
            main_obj = bpy.data.objects.new("RuneMainStroke", main_mesh)
            context.scene.collection.objects.link(main_obj)

            # Generate secondary stroke if enabled.
            if props.enable_second_stroke:
                second_poly = ZENV_Rune_Utils.generate_secondary_polyline(
                    main_poly, props.second_stroke_length, rng
                )
                if second_poly and len(second_poly) >= 2:
                    second_outline = ZENV_Rune_Utils.create_stroke_outline(
                        second_poly, props.stroke_thickness
                    )
                    if second_outline and len(second_outline) >= 3:
                        second_mesh = ZENV_Rune_Utils.create_extruded_stroke_mesh(
                            second_outline, props.extrude_depth, props.taper_factor
                        )
                        if second_mesh:
                            second_obj = bpy.data.objects.new("RuneSecondStroke", second_mesh)
                            context.scene.collection.objects.link(second_obj)
                            second_obj.parent = main_obj

            # Select the main object (headless-safe).
            for obj in context.selected_objects:
                obj.select_set(False)
            main_obj.select_set(True)
            context.view_layer.objects.active = main_obj

            logger.info("Generated rune: segments=%d, outline_verts=%d, faces=%d",
                        props.num_segments, len(outline), len(main_mesh.polygons))
            self.report({'INFO'}, "Rune generated (%d faces)" % len(main_mesh.polygons))
            return {'FINISHED'}

        except Exception as e:
            logger.error("Error generating rune: %s", e)
            self.report({'ERROR'}, "Rune generation failed: %s" % e)
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_RuneGenerator(Panel):
    """Panel for rune generation settings"""
    bl_label = "GEN Rune Generator"
    bl_idname = "ZENV_PT_RuneGenerator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ZENV"

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_rune_generator

        # Main generation settings
        layout.prop(props, "num_segments")
        layout.prop(props, "random_seed")

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
        box = layout.box()
        box.label(text="Second Stroke:")
        box.prop(props, "enable_second_stroke")
        if props.enable_second_stroke:
            box.prop(props, "second_stroke_length")

        # Generate button
        layout.operator("zenv.generate_rune")

#endregion
#region REG
classes = (
    ZENV_PG_RuneGenerator,
    ZENV_OT_GenerateRune,
    ZENV_PT_RuneGenerator,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_runes_console_handler
    if _zenv_runes_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_runes_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_runes_console_handler
    if _zenv_runes_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_runes_console_handler)
    except ValueError:
        pass
    _zenv_runes_console_handler = None


def register():
    """Register all addon classes, scene property, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.zenv_rune_generator = PointerProperty(type=ZENV_PG_RuneGenerator)


def unregister():
    """Unregister all addon classes, remove scene property, and remove the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_rune_generator"):
        delattr(bpy.types.Scene, "zenv_rune_generator")
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
