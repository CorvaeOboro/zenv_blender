#region META
bl_info = {
    "name": 'PLANT Leaf Generator',
    "blender": (4, 0, 2),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate procedural leaf meshes with biological growth simulation',
    "status": 'working',
    "approved": True,
    "group": 'Plant',
    "group_prefix": 'PLANT',
    "group_order": 80,
    "addon_order": 80,
    "tags": ['plant', 'leaf', 'procedural', 'mesh', 'biology', 'generator'],
    "description_short": 'Generate procedural leaf meshes with biological growth simulation',
    "description_medium": 'Generates leaf meshes by simulating biological growth processes including primordium formation, vascular system development, blade expansion, tissue differentiation, and surface features. Supports simple, compound, palmate, and pinnate leaf types.',
    "description_long": """
    PLANT Leaf Generator
    Generates procedural leaf meshes by simulating biological growth processes.
    Supports four leaf types (simple, compound, palmate, pinnate), customizable
    dimensions, petiole (stem), vein branching, surface detail, and deterministic
    output via random seed. Creates vertex groups for tissue layers.""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_PLANT_leaf.png',
    "addon_image": 'zenv_blender_PLANT_leaf.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import math
import random
import logging
from mathutils import Vector, noise
from bpy.props import (
    FloatProperty, IntProperty, EnumProperty,
    BoolProperty, PointerProperty,
)
from bpy.types import PropertyGroup, Operator, Panel

logger = logging.getLogger(__name__)
_zenv_leaf_console_handler = None

#endregion
#region PROPS
class ZENV_PG_LeafBiological(PropertyGroup):
    """Property group for biological characteristics of the leaf."""

    auxin_concentration: FloatProperty(
        name="Auxin Concentration",
        description="Plant hormone controlling growth direction",
        default=0.5, min=0.0, max=1.0
    )
    cytokinin_balance: FloatProperty(
        name="Cytokinin Balance",
        description="Hormone balance affecting cell division",
        default=0.3, min=0.0, max=1.0
    )
    vein_density: FloatProperty(
        name="Vein Density",
        description="Density of minor veins (controls segment count)",
        default=0.7, min=0.1, max=1.0
    )
    vein_branching: IntProperty(
        name="Vein Branching",
        description="Number of vein branching iterations",
        default=4, min=1, max=8
    )


class ZENV_PG_LeafProperties(PropertyGroup):
    """Property group for general leaf properties and customization."""

    leaf_type: EnumProperty(
        name="Leaf Type",
        description="Biological leaf classification",
        items=[
            ('SIMPLE', "Simple", "Single blade leaf"),
            ('COMPOUND', "Compound", "Multiple leaflets"),
            ('PALMATE', "Palmate", "Palm-like arrangement"),
            ('PINNATE', "Pinnate", "Feather-like arrangement"),
        ],
        default='SIMPLE'
    )
    leaf_length: FloatProperty(
        name="Length", default=6.0, min=4.0, max=20.0,
        description="Overall length of leaf"
    )
    leaf_width: FloatProperty(
        name="Width", default=3.0, min=2.0, max=10.0,
        description="Maximum width of leaf"
    )
    petiole_length: FloatProperty(
        name="Petiole Length",
        description="Length of leaf stem",
        default=2.0, min=0.0, max=5.0
    )
    petiole_angle: FloatProperty(
        name="Petiole Angle",
        description="Angle of leaf stem (degrees from vertical)",
        default=45.0, min=0.0, max=90.0
    )
    surface_detail_scale: FloatProperty(
        name="Surface Detail",
        description="Scale of surface microstructure",
        default=0.5, min=0.1, max=1.0
    )
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed for deterministic generation",
        default=42, min=0, max=999999
    )
    show_growth_stages: BoolProperty(
        name="Show Growth Stages",
        description="Visualize leaf development stages",
        default=False
    )
    debug_vein_generation: BoolProperty(
        name="Debug Vein Generation",
        description="Show vein generation process",
        default=False
    )

#endregion
#region UTILS
class ZENV_Leaf_Utils:
    """Utility functions for leaf generation."""

    @staticmethod
    def create_leaf_blade(bm, props, bio_props, rng):
        """Create the main leaf blade as a filled mesh.

        Generates an oval/elliptical blade with faces, centered along
        the Y axis.  The blade width tapers from base to tip.
        """
        length = props.leaf_length
        width = props.leaf_width
        vein_density = bio_props.vein_density

        # Number of segments along the length - controlled by vein_density.
        length_segments = max(4, int(length * vein_density * 2))
        width_segments = 6  # Half-width segments on each side.

        # Generate blade vertices in a grid.
        verts_grid = []
        for i in range(length_segments + 1):
            t = i / length_segments  # 0 at base, 1 at tip.
            # Width tapers: full width in middle, narrow at base and tip.
            width_factor = math.sin(t * math.pi) * 0.8 + 0.2
            if t < 0.1:
                width_factor *= t / 0.1  # Taper at base.
            current_width = width * width_factor

            row = []
            y = t * length
            for j in range(-width_segments, width_segments + 1):
                s = j / width_segments  # -1 to 1.
                x = s * current_width
                # Slight curvature for a natural leaf shape.
                z = 0.0
                # Add slight upward curl at edges.
                if abs(s) > 0.7:
                    z = (abs(s) - 0.7) * 0.1 * width_factor
                # Add auxin-based variation.
                variation = bio_props.auxin_concentration * rng.uniform(-0.05, 0.05)
                z += variation
                row.append(bm.verts.new(Vector((x, y, z))))
            verts_grid.append(row)

        # Create faces between grid rows.
        for i in range(length_segments):
            for j in range(width_segments * 2):
                v1 = verts_grid[i][j]
                v2 = verts_grid[i][j + 1]
                v3 = verts_grid[i + 1][j + 1]
                v4 = verts_grid[i + 1][j]
                bm.faces.new((v1, v2, v3, v4))

        return verts_grid

    @staticmethod
    def create_midrib(bm, props, bio_props, rng):
        """Create the central vein (midrib) along the leaf length.

        Returns a list of midrib vertex positions for branching.
        """
        length = props.leaf_length
        segments = max(4, int(length * bio_props.vein_density * 2))

        midrib_verts = []
        for i in range(segments + 1):
            t = i / segments
            y = t * length
            # Slight Z raise for the midrib.
            z = 0.02 * math.sin(t * math.pi)
            v = bm.verts.new(Vector((0, y, z)))
            midrib_verts.append(v)

        # Connect midrib with edges.
        for i in range(segments):
            bm.edges.new((midrib_verts[i], midrib_verts[i + 1]))

        return midrib_verts

    @staticmethod
    def create_lateral_veins(bm, midrib_verts, props, bio_props, rng):
        """Create lateral veins branching from the midrib."""
        if len(midrib_verts) < 3:
            return

        branching = bio_props.vein_branching
        length = props.leaf_length
        width = props.leaf_width

        # Create lateral veins at intervals along the midrib.
        step = max(1, len(midrib_verts) // (branching + 2))
        for i in range(step, len(midrib_verts) - step, step):
            mid_v = midrib_verts[i]
            t = i / max(1, len(midrib_verts) - 1)
            # Width at this point (matches blade taper).
            width_factor = math.sin(t * math.pi) * 0.8 + 0.2
            current_width = width * width_factor * 0.8

            for side in (-1, 1):
                # Vein goes from midrib outward and slightly toward tip.
                vein_end = mid_v.co + Vector((
                    side * current_width,
                    current_width * 0.3 * rng.uniform(0.5, 1.0),
                    0.01
                ))
                end_v = bm.verts.new(vein_end)
                bm.edges.new((mid_v, end_v))

                # Secondary branching.
                if branching > 2:
                    sub_count = min(branching - 1, 3)
                    for s in range(sub_count):
                        st = (s + 1) / (sub_count + 1)
                        sub_start = mid_v.co.lerp(vein_end, st)
                        sub_offset = Vector((
                            side * current_width * 0.15 * rng.uniform(-0.5, 0.5),
                            current_width * 0.1 * rng.uniform(-0.5, 0.5),
                            0.005
                        ))
                        sub_end_v = bm.verts.new(sub_start + sub_offset)
                        sub_start_v = bm.verts.new(sub_start)
                        bm.edges.new((sub_start_v, sub_end_v))

    @staticmethod
    def create_petiole(bm, props, rng):
        """Create the petiole (leaf stem) at the base of the leaf."""
        petiole_len = props.petiole_length
        if petiole_len <= 0:
            return

        angle_rad = math.radians(props.petiole_angle)
        segments = max(2, int(petiole_len))

        # Petiole goes from origin downward at the petiole angle.
        direction = Vector((
            math.sin(angle_rad),
            -math.cos(angle_rad),
            0
        ))

        petiole_verts = []
        for i in range(segments + 1):
            t = i / segments
            pos = direction * (t * petiole_len)
            v = bm.verts.new(pos)
            petiole_verts.append(v)

        # Connect petiole with edges.
        for i in range(segments):
            bm.edges.new((petiole_verts[i], petiole_verts[i + 1]))

        # Connect petiole to leaf base (first midrib vertex at origin).
        # The leaf base is at (0, 0, 0), petiole starts at origin too.
        # Add a connecting edge if petiole doesn't start at origin.
        if petiole_verts:
            base_v = bm.verts.new(Vector((0, 0, 0)))
            bm.edges.new((base_v, petiole_verts[0]))

    @staticmethod
    def apply_surface_features(bm, props, bio_props, rng):
        """Apply surface displacement and trichomes to the mesh."""
        noise_scale = props.surface_detail_scale

        for vert in bm.verts:
            # Micro-surface displacement using noise.
            displacement = noise.noise(vert.co * 10) * noise_scale * 0.1
            vert.co.z += displacement

            # Add trichomes (leaf hairs) on some vertices.
            if rng.random() < 0.05:
                height = rng.uniform(0.05, 0.15)
                trichome_tip = vert.co + Vector((0, 0, height))
                new_vert = bm.verts.new(trichome_tip)
                bm.edges.new((vert, new_vert))

    @staticmethod
    def create_tissue_vertex_groups(obj, bm):
        """Create vertex groups for different tissue layers."""
        # Define tissue categories based on Z position.
        tissue_defs = [
            ('epidermis_upper', 0.05, float('inf')),
            ('epidermis_lower', float('-inf'), -0.05),
            ('palisade_mesophyll', 0.0, 0.05),
            ('spongy_mesophyll', -0.05, 0.0),
        ]

        for name, z_min, z_max in tissue_defs:
            vg = obj.vertex_groups.new(name=name)
            indices = []
            for vert in bm.verts:
                if z_min <= vert.co.z < z_max:
                    indices.append(vert.index)
            if indices:
                vg.add(indices, 1.0, 'REPLACE')

    @staticmethod
    def generate_compound_leaf(bm, props, bio_props, rng):
        """Generate a compound leaf with multiple leaflets."""
        leaflet_count = max(3, bio_props.vein_branching + 1)
        leaflet_length = props.leaf_length / leaflet_count * 1.5
        leaflet_width = props.leaf_width * 0.6

        for i in range(leaflet_count):
            t = i / max(1, leaflet_count - 1)
            offset_y = t * props.leaf_length
            offset_x = math.sin(t * math.pi) * props.leaf_width * 0.3

            # Create a smaller leaflet.
            sub_props = type('SubProps', (), {
                'leaf_length': leaflet_length,
                'leaf_width': leaflet_width,
            })()
            sub_bio = type('SubBio', (), {
                'auxin_concentration': bio_props.auxin_concentration,
                'vein_density': bio_props.vein_density,
            })()

            # Generate leaflet at offset.
            original_verts = list(bm.verts)
            ZENV_Leaf_Utils.create_leaf_blade(bm, sub_props, sub_bio, rng)
            # Translate new verts to leaflet position.
            for v in bm.verts:
                if v not in original_verts:
                    v.co.x += offset_x
                    v.co.y += offset_y

    @staticmethod
    def generate_palmate_leaf(bm, props, bio_props, rng):
        """Generate a palmate leaf with lobes radiating from base."""
        lobe_count = max(3, bio_props.vein_branching)
        lobe_length = props.leaf_length * 0.8
        lobe_width = props.leaf_width / lobe_count * 1.5

        for i in range(lobe_count):
            angle = -math.pi / 2 + (i - (lobe_count - 1) / 2) * math.pi / lobe_count
            direction = Vector((math.cos(angle), math.sin(angle), 0))

            sub_props = type('SubProps', (), {
                'leaf_length': lobe_length,
                'leaf_width': lobe_width,
            })()
            sub_bio = type('SubBio', (), {
                'auxin_concentration': bio_props.auxin_concentration,
                'vein_density': bio_props.vein_density,
            })()

            original_verts = list(bm.verts)
            ZENV_Leaf_Utils.create_leaf_blade(bm, sub_props, sub_bio, rng)
            # Rotate and position new verts.
            for v in bm.verts:
                if v not in original_verts:
                    # Rotate around origin.
                    co = v.co.copy()
                    v.co.x = co.x * direction.x - co.y * direction.y
                    v.co.y = co.x * direction.y + co.y * direction.x

    @staticmethod
    def generate_pinnate_leaf(bm, props, bio_props, rng):
        """Generate a pinnate leaf with leaflets along a central rachis."""
        leaflet_count = max(3, bio_props.vein_branching + 1)
        leaflet_length = props.leaf_length / leaflet_count * 0.8
        leaflet_width = props.leaf_width * 0.5

        for i in range(leaflet_count):
            t = i / max(1, leaflet_count - 1)
            y = t * props.leaf_length

            for side in (-1, 1):
                sub_props = type('SubProps', (), {
                    'leaf_length': leaflet_length,
                    'leaf_width': leaflet_width,
                })()
                sub_bio = type('SubBio', (), {
                    'auxin_concentration': bio_props.auxin_concentration,
                    'vein_density': bio_props.vein_density,
                })()

                original_verts = list(bm.verts)
                ZENV_Leaf_Utils.create_leaf_blade(bm, sub_props, sub_bio, rng)
                for v in bm.verts:
                    if v not in original_verts:
                        v.co.x += side * leaflet_width * 0.5
                        v.co.y += y

#endregion
#region OP
class ZENV_OT_GenerateLeaf(Operator):
    """Generate a procedural leaf mesh with customizable biological and physical properties"""
    bl_idname = "zenv.generate_leaf"
    bl_label = "Generate Leaf"
    bl_description = "Generate a procedural leaf mesh with biological growth simulation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        props = context.scene.leaf_props
        bio_props = context.scene.leaf_bio

        # Seed the RNG for deterministic output.
        rng = random.Random(props.random_seed)

        mesh = bpy.data.meshes.new(name="Leaf")
        obj = bpy.data.objects.new("Leaf", mesh)
        context.collection.objects.link(obj)
        context.view_layer.objects.active = obj
        obj.select_set(True)

        bm = bmesh.new()

        try:
            # Generate petiole (stem) if length > 0.
            if props.petiole_length > 0:
                ZENV_Leaf_Utils.create_petiole(bm, props, rng)

            # Generate leaf blade based on leaf_type.
            leaf_type = props.leaf_type
            if leaf_type == 'SIMPLE':
                ZENV_Leaf_Utils.create_leaf_blade(bm, props, bio_props, rng)
                # Create midrib and lateral veins.
                midrib = ZENV_Leaf_Utils.create_midrib(bm, props, bio_props, rng)
                ZENV_Leaf_Utils.create_lateral_veins(bm, midrib, props, bio_props, rng)
            elif leaf_type == 'COMPOUND':
                ZENV_Leaf_Utils.generate_compound_leaf(bm, props, bio_props, rng)
            elif leaf_type == 'PALMATE':
                ZENV_Leaf_Utils.generate_palmate_leaf(bm, props, bio_props, rng)
            elif leaf_type == 'PINNATE':
                ZENV_Leaf_Utils.generate_pinnate_leaf(bm, props, bio_props, rng)

            # Apply surface features (noise displacement + trichomes).
            ZENV_Leaf_Utils.apply_surface_features(bm, props, bio_props, rng)

            # Finalize mesh.
            bm.normal_update()
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()

            # Create vertex groups for tissue layers.
            bm2 = bmesh.new()
            bm2.from_mesh(mesh)
            bm2.verts.ensure_lookup_table()
            ZENV_Leaf_Utils.create_tissue_vertex_groups(obj, bm2)
            bm2.free()

            logger.info("Generated leaf: type=%s, verts=%d, faces=%d",
                        leaf_type, len(mesh.vertices), len(mesh.polygons))
            self.report({'INFO'}, "Leaf generated (%d faces)" % len(mesh.polygons))
            return {'FINISHED'}

        except Exception as e:
            logger.error("Error generating leaf: %s", e)
            self.report({'ERROR'}, "Leaf generation failed: %s" % e)
            # Clean up BMesh on failure.
            try:
                bm.free()
            except Exception:
                pass
            # Remove the partially-created object.
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_Leaf(Panel):
    """UI panel for the leaf generator"""
    bl_label = "PLANT Generate Leaf"
    bl_idname = "ZENV_PT_Leaf"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.leaf_props
        bio_props = context.scene.leaf_bio

        # Basic Parameters
        box = layout.box()
        box.label(text="Basic Parameters")
        box.prop(props, "leaf_type")
        box.prop(props, "leaf_length")
        box.prop(props, "leaf_width")

        # Biological Controls
        box = layout.box()
        box.label(text="Biological Controls")
        box.prop(bio_props, "auxin_concentration")
        box.prop(bio_props, "cytokinin_balance")
        box.prop(bio_props, "vein_density")
        box.prop(bio_props, "vein_branching")

        # Structure Controls
        box = layout.box()
        box.label(text="Structure")
        box.prop(props, "petiole_length")
        box.prop(props, "petiole_angle")
        box.prop(props, "surface_detail_scale")
        box.prop(props, "random_seed")

        # Debug Options
        box = layout.box()
        box.label(text="Debug")
        box.prop(props, "show_growth_stages")
        box.prop(props, "debug_vein_generation")

        # Generate Button
        layout.operator("zenv.generate_leaf", text="Generate Leaf")

#endregion
#region REG
classes = (
    ZENV_PG_LeafBiological,
    ZENV_PG_LeafProperties,
    ZENV_OT_GenerateLeaf,
    ZENV_PT_Leaf,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_leaf_console_handler
    if _zenv_leaf_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_leaf_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_leaf_console_handler
    if _zenv_leaf_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_leaf_console_handler)
    except ValueError:
        pass
    _zenv_leaf_console_handler = None


def register():
    """Register all addon classes, scene properties, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.leaf_bio = PointerProperty(type=ZENV_PG_LeafBiological)
    bpy.types.Scene.leaf_props = PointerProperty(type=ZENV_PG_LeafProperties)


def unregister():
    """Unregister all addon classes, remove scene properties, and remove the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "leaf_bio"):
        delattr(bpy.types.Scene, "leaf_bio")
    if hasattr(bpy.types.Scene, "leaf_props"):
        delattr(bpy.types.Scene, "leaf_props")
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
