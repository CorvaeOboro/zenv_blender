#region META
bl_info = {
    "name": 'GEN Tooth Generator',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate monster teeth with realistic features',
    "status": 'wip',
    "approved": False,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['mesh', 'tooth', 'procedural', 'monster', 'organic'],
    "description_short": 'Generate monster teeth with realistic features',
    "description_medium": 'Generates procedural monster teeth (canine, molar, incisor) with surface noise, striations, root extrusion, and optional voxel remeshing.',
    "description_long": """
    Tooth Generator
Generates detailed monster teeth with realistic striations and patterns.
Supports three tooth types (canine, molar, incisor), each with type-specific
shaping, surface noise displacement, random asymmetry, root extrusion, and
optional voxel remeshing for clean topology.""",
    "location": 'View3D > ZENV > GEN Tooth Generator',
    "image_overview": 'zenv_blender_GEN_tooth_generator.png',
    "addon_image": 'zenv_blender_GEN_tooth_generator.png',
    "warning": '',
    "doc_url": '',
}

#region IMPORT
import bpy
import bmesh
import math
import random
import logging
from mathutils import Vector
from bpy.props import (
    FloatProperty,
    IntProperty,
    EnumProperty,
    PointerProperty,
    BoolProperty,
)
from bpy.types import PropertyGroup, Panel, Operator

logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None

#endregion
#region PROPS

# Tooth type enum items shared between the operator property and the UI.
_TOOTH_TYPE_ITEMS = [
    ('CANINE', "Canine", "Pointed cone-shaped tooth", 'MESH_CONE', 0),
    ('MOLAR', "Molar", "Flat-topped chewing tooth", 'MESH_CUBE', 1),
    ('INCISOR', "Incisor", "Flat rectangular cutting tooth", 'MESH_PLANE', 2),
]


class ZENV_PG_ToothGenerator(PropertyGroup):
    """Property group for tooth generator settings"""
    tooth_size: FloatProperty(
        name="Size",
        description="Overall size of the generated tooth",
        default=1.0,
        min=0.1,
        max=10.0
    )
    tooth_detail: IntProperty(
        name="Detail Level",
        description="Amount of surface detail (number of subdivision passes)",
        default=2,
        min=0,
        max=4
    )
    tooth_roughness: FloatProperty(
        name="Surface Roughness",
        description="Amount of surface irregularities and texture",
        default=0.1,
        min=0.0,
        max=1.0
    )
    tooth_asymmetry: FloatProperty(
        name="Asymmetry",
        description="Amount of random asymmetry in the tooth shape",
        default=0.1,
        min=0.0,
        max=1.0
    )
    seed: IntProperty(
        name="Seed",
        description="Random seed for reproducible teeth (0 = random)",
        default=0,
        min=0,
        max=10000
    )
    use_voxel_remesh: BoolProperty(
        name="Voxel Remesh",
        description="Apply voxel remesh for final mesh topology",
        default=True
    )

#endregion
#region OP
class ZENV_OT_GenerateTooth(Operator):
    """Generate a detailed tooth mesh with realistic features"""
    bl_idname = "zenv.generate_tooth"
    bl_label = "Generate Tooth"
    bl_options = {'REGISTER', 'UNDO'}

    tooth_type: EnumProperty(
        name="Tooth Type",
        description="Type of tooth to generate",
        items=_TOOTH_TYPE_ITEMS,
        default='CANINE'
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def _get_props(self, context):
        """Return the scene PropertyGroup for this addon."""
        return context.scene.zenv_tooth_generator_props

    def apply_molar_details(self, bm, context):
        """Add realistic molar-specific features with optimized complexity.

        Fixes from review:
        - Collect top-face edges before subdividing to avoid invalidating
          face references mid-iteration.
        - Raise the *original* corner vertices (high |x| and |y|) rather than
          the newly-created mid-edge vertices.
        - Use a relative threshold for the central depression based on the
          actual mesh bounds.
        """
        props = self._get_props(context)
        size = props.tooth_size

        # Snapshot top-face edges before any modification.
        top_face_edges = set()
        for f in bm.faces:
            if f.normal.z > 0.5:
                for e in f.edges:
                    top_face_edges.add(e)

        if top_face_edges:
            bmesh.ops.subdivide_edges(
                bm,
                edges=list(top_face_edges),
                cuts=1
            )
            bmesh.ops.recalc_face_normals(bm)

        # Raise the four corner vertices of the top face to form cusps.
        # After subdivision the corners are the verts with max |x| and |y|.
        if bm.verts:
            max_xy = max(abs(v.co.x) + abs(v.co.y) for v in bm.verts)
            corner_threshold = max_xy * 0.8
            for v in bm.verts:
                if v.co.z > 0 and (abs(v.co.x) + abs(v.co.y)) > corner_threshold:
                    v.co.z += 0.2 * size
                    v.co.x *= 0.9
                    v.co.y *= 0.9

        # Create central depression using a relative threshold.
        center_threshold = max_xy * 0.15 if max_xy > 0 else 0.1
        for v in bm.verts:
            if v.co.z > 0 and abs(v.co.x) < center_threshold and abs(v.co.y) < center_threshold:
                v.co.z -= 0.1 * size

    def apply_canine_details(self, bm, context):
        """Add realistic canine-specific features with improved shape.

        Fixes from review:
        - Compute the ridge angle *after* the twist so the ridge aligns
          with the twisted geometry.
        - Recalculate normals before using v.normal for displacement.
        """
        props = self._get_props(context)
        size = props.tooth_size

        # First pass: curve and twist (no normal-based displacement yet).
        for v in bm.verts:
            height_ratio = (v.co.z + size) / (2.0 * size)

            # Create slight curve
            v.co.y += math.sin(height_ratio * math.pi) * 0.15 * size

            # Add slight twist
            twist = height_ratio * math.pi * 0.1
            new_x = v.co.x * math.cos(twist) - v.co.y * math.sin(twist)
            new_y = v.co.x * math.sin(twist) + v.co.y * math.cos(twist)
            v.co.x = new_x
            v.co.y = new_y

        # Recalculate normals after coordinate changes.
        bmesh.ops.recalc_face_normals(bm)

        # Second pass: ridge along the front (angle computed from post-twist coords).
        for v in bm.verts:
            height_ratio = (v.co.z + size) / (2.0 * size)
            angle = math.atan2(v.co.x, v.co.y)
            if abs(angle) < 0.5:
                v.co += v.normal * 0.1 * size * (1 - height_ratio)

        # Sharpen the tip more naturally
        top_verts = [v for v in bm.verts if v.co.z > size * 0.8]
        for v in top_verts:
            tip_factor = (v.co.z - size * 0.8) / (size * 1.2)
            # Progressive narrowing
            v.co.x *= (1.0 - tip_factor)
            v.co.y *= (1.0 - tip_factor)
            # Slight forward lean at tip
            v.co.y += tip_factor * 0.2 * size

    def apply_incisor_details(self, bm, context):
        """Add realistic incisor-specific features.

        Fixes from review:
        - Derive the width divisor from the actual mesh bounds instead of
          the hardcoded 1.5 * tooth_size.
        """
        props = self._get_props(context)
        size = props.tooth_size

        # Scale to create rectangular front face
        for v in bm.verts:
            v.co.x *= 1.5  # Make wider
            v.co.y *= 0.7  # Make thinner

        # Derive actual half-width from the mesh after scaling.
        max_x = max(abs(v.co.x) for v in bm.verts) if bm.verts else size

        # Create cutting edge and front curve
        top_verts = [v for v in bm.verts if v.co.z > 0]
        for v in top_verts:
            # Create slightly curved cutting edge
            edge_curve = math.sin(v.co.x * math.pi / max_x) * 0.1 * size if max_x > 0 else 0.0
            v.co.z = size + edge_curve

            # Tilt the cutting edge forward slightly
            v.co.y += 0.2 * size

        # Create back scoop
        back_verts = [v for v in bm.verts if v.co.y > 0]
        for v in back_verts:
            # Calculate scoop depth based on height and position
            height_factor = (v.co.z + size) / (2.0 * size)
            width_factor = abs(v.co.x) / max_x if max_x > 0 else 0.0
            scoop = math.sin(height_factor * math.pi) * (1 - width_factor) * 0.3 * size
            v.co.y -= scoop

    def apply_surface_noise(self, bm, context):
        """Add realistic surface imperfections and micro-detail.

        Fixes from review:
        - Scale noise frequencies by tooth_size so texture is consistent
          across different sizes.
        - Recalculate normals before normal-based displacement.
        """
        props = self._get_props(context)
        size = props.tooth_size

        # Frequency scaled by size so larger teeth get proportionally fewer cycles.
        freq = 20.0 / size if size > 0 else 20.0

        bmesh.ops.recalc_face_normals(bm)
        for v in bm.verts:
            # Layered noise for more natural look
            large_noise = math.sin(v.co.x * freq) * math.cos(v.co.y * freq) * math.sin(v.co.z * freq)
            medium_noise = math.sin(v.co.x * freq * 2) * math.cos(v.co.y * freq * 2) * math.sin(v.co.z * freq * 2) * 0.5
            small_noise = math.sin(v.co.x * freq * 4) * math.cos(v.co.y * freq * 4) * math.sin(v.co.z * freq * 4) * 0.25

            combined_noise = (large_noise + medium_noise + small_noise) * props.tooth_roughness * 0.05 * size
            v.co += v.normal * combined_noise

    def create_base_mesh(self, context):
        """Create the basic tooth shape based on type"""
        props = self._get_props(context)
        bm = bmesh.new()

        if self.tooth_type == 'CANINE':
            # Create more detailed base for canine
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                segments=16,
                radius1=0.6 * props.tooth_size,
                radius2=0.15 * props.tooth_size,
                depth=2.0 * props.tooth_size
            )
            # Add extra loop cuts for better deformation
            bmesh.ops.subdivide_edges(
                bm,
                edges=[e for e in bm.edges if any(v.co.z > 0 for v in e.verts)],
                cuts=2
            )
            self.apply_canine_details(bm, context)

        elif self.tooth_type == 'MOLAR':
            # Create optimized base for molar
            bmesh.ops.create_cube(
                bm,
                size=props.tooth_size
            )
            # Single subdivision for base shape
            bmesh.ops.subdivide_edges(
                bm,
                edges=bm.edges[:],
                cuts=1
            )
            self.apply_molar_details(bm, context)

        else:  # INCISOR
            # Create rectangular base for incisor
            bmesh.ops.create_cube(
                bm,
                size=props.tooth_size
            )
            # Add more subdivisions for better deformation
            bmesh.ops.subdivide_edges(
                bm,
                edges=bm.edges[:],
                cuts=2
            )
            self.apply_incisor_details(bm, context)

        # Apply common surface details
        self.apply_surface_noise(bm, context)
        return bm

    def add_surface_detail(self, bm, context):
        """Add realistic surface details.

        Fixes from review:
        - Use a local random.Random(seed) instead of the global random module.
        - Fix `in {'CANINE'}` to `== 'CANINE'`.
        - Recalculate normals before normal-based striation displacement.
        """
        props = self._get_props(context)
        size = props.tooth_size
        rng = random.Random(props.seed if props.seed > 0 else None)

        # Subdivide for detail
        for _ in range(props.tooth_detail):
            bmesh.ops.subdivide_edges(
                bm,
                edges=bm.edges[:],
                cuts=1,
                use_grid_fill=True
            )

        # Add surface irregularities
        for v in bm.verts:
            # Random displacement
            noise = Vector((
                rng.uniform(-1, 1),
                rng.uniform(-1, 1),
                rng.uniform(-1, 1)
            )) * props.tooth_roughness * 0.1 * size

            # Add asymmetry
            if rng.random() < props.tooth_asymmetry:
                asymm = Vector((
                    rng.uniform(-1, 1),
                    rng.uniform(-1, 1),
                    rng.uniform(-1, 1)
                )) * props.tooth_asymmetry * 0.2 * size
                noise += asymm

            v.co += noise

        # Add striations (vertical grooves) for canine teeth
        if self.tooth_type == 'CANINE':
            bmesh.ops.recalc_face_normals(bm)
            for v in bm.verts:
                angle = math.atan2(v.co.x, v.co.y)
                striation = math.sin(angle * 8) * 0.05 * size * props.tooth_roughness
                v.co += v.normal * striation

    def create_root(self, bm, context):
        """Create tooth root by extruding bottom faces downward.

        Each bottom face is extruded separately, creating separate root prongs
        (multi-rooted teeth). The root tapers to 60% of the original cross-section.
        """
        props = self._get_props(context)
        # Find bottom faces
        bottom_faces = [f for f in bm.faces if f.normal.z < -0.5]

        # Extrude downward for root
        root_depth = 1.2 * props.tooth_size
        root_taper = 0.6  # Taper root to 60% of original cross-section
        for face in bottom_faces:
            result = bmesh.ops.extrude_face_region(bm, geom=[face])
            new_faces = [f for f in result['geom'] if isinstance(f, bmesh.types.BMFace)]

            # Move new faces down and taper
            for f in new_faces:
                for v in f.verts:
                    v.co.z -= root_depth
                    v.co.x *= root_taper
                    v.co.y *= root_taper

    def execute(self, context):
        """Generate a tooth mesh and link it to the scene.

        Fixes from review:
        - try/except with bm.free() in finally to prevent memory leaks.
        - self.report() on success and error.
        - Deselect other objects before selecting the new tooth.
        - Scale voxel_size by tooth_size.
        - Guard modifier_apply with try/except.
        """
        props = self._get_props(context)
        bm = None
        obj = None
        try:
            # Create base mesh
            bm = self.create_base_mesh(context)

            # Add root
            self.create_root(bm, context)

            # Add surface details
            self.add_surface_detail(bm, context)

            # Create mesh and object
            mesh = bpy.data.meshes.new("Tooth")
            bm.to_mesh(mesh)
            bm.free()
            bm = None

            obj = bpy.data.objects.new("Tooth", mesh)
            context.collection.objects.link(obj)

            # Deselect all, then select and make active
            for o in context.view_layer.objects:
                o.select_set(False)
            context.view_layer.objects.active = obj
            obj.select_set(True)

            if props.use_voxel_remesh:
                # Add and apply remesh modifier
                mod = obj.modifiers.new(name="Remesh", type='REMESH')
                mod.mode = 'VOXEL'
                mod.voxel_size = 0.075 * props.tooth_size
                context.view_layer.objects.active = obj
                try:
                    bpy.ops.object.modifier_apply(modifier="Remesh")
                except Exception as e:
                    logger.warning("Voxel remesh failed: %s", e)
                    self.report({'WARNING'}, f"Voxel remesh failed: {e}")

            logger.info("Generated %s tooth (%d verts)",
                        self.tooth_type, len(obj.data.vertices))
            self.report({'INFO'}, f"Generated {self.tooth_type.lower()} tooth ({len(obj.data.vertices)} verts)")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Tooth generation failed: %s", e)
            self.report({'ERROR'}, f"Tooth generation failed: {e}")
            # Clean up partially-created object on failure.
            if obj is not None:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
            return {'CANCELLED'}
        finally:
            if bm is not None:
                bm.free()

#endregion
#region PANEL
class ZENV_PT_ToothGenerator(Panel):
    """Panel for procedural tooth generation"""
    bl_label = "GEN Tooth Generator"
    bl_idname = "ZENV_PT_ToothGenerator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_tooth_generator_props

        # Property controls
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Tooth Settings:", icon='MODIFIER')
        col.prop(props, "tooth_size")
        col.prop(props, "tooth_detail")
        col.prop(props, "tooth_roughness")
        col.prop(props, "tooth_asymmetry")
        col.prop(props, "seed")
        col.prop(props, "use_voxel_remesh")

        # Tooth type buttons
        box = layout.box()
        box.label(text="Generate Tooth Type:", icon='MESH_DATA')
        col = box.column(align=True)

        op = col.operator("zenv.generate_tooth", text="Generate Canine", icon='MESH_CONE')
        op.tooth_type = 'CANINE'

        op = col.operator("zenv.generate_tooth", text="Generate Molar", icon='MESH_CUBE')
        op.tooth_type = 'MOLAR'

        op = col.operator("zenv.generate_tooth", text="Generate Incisor", icon='MESH_PLANE')
        op.tooth_type = 'INCISOR'

#endregion
#region REG
classes = (
    ZENV_PG_ToothGenerator,
    ZENV_OT_GenerateTooth,
    ZENV_PT_ToothGenerator,
)

def menu_func(self, context):
    """Add menu item to Add Mesh menu."""
    self.layout.operator("zenv.generate_tooth", text="Tooth", icon='MESH_CONE')

def register():
    """Register all addon classes, the scene property, the menu entry, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, "zenv_tooth_generator_props"):
        bpy.types.Scene.zenv_tooth_generator_props = PointerProperty(type=ZENV_PG_ToothGenerator)
    try:
        bpy.types.VIEW3D_MT_mesh_add.append(menu_func)
    except Exception:
        pass

def unregister():
    """Unregister all addon classes, remove the scene property, the menu entry, and the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, "zenv_tooth_generator_props"):
        delattr(bpy.types.Scene, "zenv_tooth_generator_props")
    try:
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except Exception:
        pass
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
