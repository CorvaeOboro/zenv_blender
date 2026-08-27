#region META
bl_info = {
    "name": 'PLANT Fungus Mushroom',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Creates mushrooms with mesh-based geometry',
    "status": 'wip',
    "approved": False,
    "group": 'Plant',
    "group_prefix": 'PLANT',
    "group_order": 50,
    "addon_order": 10,
    "tags": ['plant', 'fungus', 'mushroom', 'procedural', 'mesh'],
    "description_short": 'Creates procedural mushrooms with mesh-based geometry',
    "description_medium": 'Generates procedural mushroom meshes (cap + stem) with 3D noise displacement, voxel remeshing, subdivision smoothing, and a Principled BSDF material.',
    "description_long": """
    Fungus Mushroom Generator
Creates procedural mushrooms with mesh-based geometry.
Generates a cap (hemisphere with noise displacement) and stem (tapered cylinder),
joins them, applies Voxel Remesh for watertight geometry, adds Subdivision Surface
for smoothness, and assigns a Principled BSDF material.""",
    "location": 'View3D > ZENV > PLANT Fungus Mushroom',
    "image_overview": 'zenv_blender_PLANT_fungus_mushroom.png',
    "addon_image": 'zenv_blender_PLANT_fungus_mushroom.png',
    "warning": '',
    "doc_url": '',
}

#region IMPORT
import bpy
import math
import logging
from mathutils import Vector, noise
from bpy.props import (
    FloatProperty,
    IntProperty,
    FloatVectorProperty,
    EnumProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

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
class ZENV_PG_FungusMush(PropertyGroup):
    """Properties for the Fungus Mushroom Generator"""

    cap_radius: FloatProperty(
        name="Cap Radius",
        description="Radius of the mushroom cap",
        default=0.5,
        min=0.1,
        max=2.0,
        unit='LENGTH'
    )
    cap_height: FloatProperty(
        name="Cap Height",
        description="Height of the mushroom cap",
        default=0.3,
        min=0.1,
        max=1.0,
        unit='LENGTH'
    )
    stem_height: FloatProperty(
        name="Stem Height",
        description="Height of the mushroom stem",
        default=1.0,
        min=0.1,
        max=3.0,
        unit='LENGTH'
    )
    stem_radius: FloatProperty(
        name="Stem Radius",
        description="Radius of the mushroom stem",
        default=0.1,
        min=0.02,
        max=0.5,
        unit='LENGTH'
    )
    detail_scale: FloatProperty(
        name="Detail Scale",
        description="Scale of surface details",
        default=1.0,
        min=0.1,
        max=5.0
    )
    noise_strength: FloatProperty(
        name="Noise Strength",
        description="Strength of surface noise",
        default=0.1,
        min=0.0,
        max=0.5
    )
    voxel_size: FloatProperty(
        name="Voxel Size",
        description="Size of voxels for remeshing",
        default=0.02,
        min=0.01,
        max=0.1,
        unit='LENGTH'
    )
    mushroom_type: EnumProperty(
        name="Mushroom Type",
        description="Type of mushroom to generate",
        items=[
            ('AMANITA', "Amanita", "Classic toadstool with spots"),
            ('MOREL', "Morel", "Honeycomb textured cap"),
            ('SHELF', "Shelf", "Bracket fungus growing on side")
        ],
        default='AMANITA'
    )
    cap_color: FloatVectorProperty(
        name="Cap Color",
        description="Color of the mushroom cap",
        subtype='COLOR',
        size=3,
        default=(0.8, 0.4, 0.3),
        min=0.0,
        max=1.0
    )
    seed: IntProperty(
        name="Seed",
        description="Random seed for reproducible noise variation (0 = no offset)",
        default=0,
        min=0,
        max=10000
    )
    resolution: IntProperty(
        name="Resolution",
        description="Number of segments around the cap/stem circumference",
        default=32,
        min=8,
        max=128
    )

#endregion
#region OP
class ZENV_OT_FungusMush(Operator):
    """Create a new procedural mushroom"""
    bl_idname = "zenv.fungus_mush_add"
    bl_label = "Add Fungus Mushroom"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @staticmethod
    def noise3d(x, y, z, scale, octaves=3, seed=0):
        """Generate a fractal 3D noise value (fBm).

        ``seed`` offsets the input coordinates so that different seeds
        produce different but reproducible noise patterns.
        """
        if scale == 0:
            return 0.0
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        # Seed offset - shifts the noise sampling domain.
        sx, sy, sz = x + seed * 17.3, y + seed * 23.7, z + seed * 41.1
        for _ in range(octaves):
            v = Vector((sx * frequency / scale, sy * frequency / scale, sz * frequency / scale))
            value += noise.noise(v) * amplitude
            max_value += amplitude
            amplitude *= 0.5
            frequency *= 2.0
        if max_value == 0:
            return 0.0
        return value / max_value

    def create_base_mesh(self, context, verts, faces, name):
        """Create a base mesh object from vertices and faces."""
        mesh = bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        return obj

    # ------------------------------------------------------------------
    #  Cap generation - dispatches by mushroom type
    # ------------------------------------------------------------------
    def generate_cap_points(self, props):
        """Generate cap vertices and faces based on mushroom type."""
        mtype = props.mushroom_type
        if mtype == 'MOREL':
            return self._generate_morel_cap(props)
        elif mtype == 'SHELF':
            return self._generate_shelf_cap(props)
        return self._generate_amanita_cap(props)

    def _generate_amanita_cap(self, props):
        """Amanita cap - hemisphere dome sitting on top of the stem."""
        segments = props.resolution
        rings = max(8, segments // 2)
        verts = []
        faces = []

        for ring in range(rings + 1):
            cap_angle = ring * math.pi / (2 * rings)
            ring_radius = math.sin(cap_angle) * props.cap_radius
            ring_height = math.cos(cap_angle) * props.cap_height

            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                x = math.cos(angle) * ring_radius
                y = math.sin(angle) * ring_radius
                z = ring_height + props.stem_height

                noise_value = self.noise3d(x, y, z, props.detail_scale, seed=props.seed)
                x += noise_value * props.noise_strength
                y += noise_value * props.noise_strength
                z += noise_value * props.noise_strength
                verts.append((x, y, z))

        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                faces.append((current, next_segment, next_ring_segment, next_ring))

        # Close underside for watertight solid (voxel remesh).
        rim_start = rings * segments
        rim_face = tuple(range(rim_start, rim_start + segments))
        faces.append(rim_face[::-1])
        return verts, faces

    def _generate_morel_cap(self, props):
        """Morel cap - tall conical cap with honeycomb pit texture."""
        segments = props.resolution
        rings = max(12, segments)  # morel caps are tall - need more vertical rings
        verts = []
        faces = []
        cap_tall = props.cap_height * 2.5  # morels are taller than wide
        angular_cells = 10
        vertical_cells = 8
        pit_depth = props.cap_radius * 0.18

        for ring in range(rings + 1):
            t = ring / rings  # 0 at bottom, 1 at top
            # Cone profile: wide at bottom, narrowing to rounded top.
            cone_r = props.cap_radius * (1.0 - t ** 1.3)
            cone_r *= 0.75 + 0.25 * math.sin(t * math.pi)  # slight bulge
            z = props.stem_height + t * cap_tall

            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                # Honeycomb pits: indent inward at cell centres, ridges at borders.
                cell_u = (segment / segments * angular_cells) % 1.0
                cell_v = (ring / rings * vertical_cells) % 1.0
                pit_factor = 4.0 * cell_u * (1.0 - cell_u) * cell_v * (1.0 - cell_v)
                r = max(0.001, cone_r - pit_depth * pit_factor)

                x = math.cos(angle) * r
                y = math.sin(angle) * r
                # Subtle surface noise on top of honeycomb.
                n = self.noise3d(x, y, z, props.detail_scale * 2, seed=props.seed)
                x += n * props.noise_strength * 0.5
                y += n * props.noise_strength * 0.5
                z += n * props.noise_strength * 0.3
                verts.append((x, y, z))

        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                faces.append((current, next_segment, next_ring_segment, next_ring))

        # Close bottom (open underside where stem enters) for watertight solid.
        rim_start = 0  # ring 0 is the bottom rim
        rim_face = tuple(range(rim_start, rim_start + segments))
        faces.append(rim_face[::-1])
        return verts, faces

    def _generate_shelf_cap(self, props):
        """Shelf/bracket cap - semicircular fan extending horizontally in +X.

        The flat back lies along the Y axis (x=0) where it would attach to
        a tree trunk.  Top and bottom faces plus rim and back edges are
        all closed so the result is a watertight solid for voxel remesh.
        """
        n_seg = max(8, props.resolution // 2)
        n_ring = max(6, n_seg // 2)
        verts = []
        faces = []
        top_base = 0
        bot_base = (n_ring + 1) * (n_seg + 1)

        # Top surface (domed, thicker near apex) and bottom surface (flat).
        for ring in range(n_ring + 1):
            t_ring = ring / n_ring  # 0 at apex, 1 at outer edge
            radius = t_ring * props.cap_radius
            for seg in range(n_seg + 1):
                angle = -math.pi / 2 + seg * math.pi / n_seg  # semicircle in +X
                x = math.cos(angle) * radius
                y = math.sin(angle) * radius
                # Top: thicker near apex, thinning toward the rim.
                z_top = props.cap_height * (1.0 - 0.6 * t_ring ** 2)
                # Concentric growth-ring ridges on top surface.
                z_top += 0.04 * props.cap_height * math.sin(t_ring * 18.0)
                # Subtle noise.
                n = self.noise3d(x, y, z_top, props.detail_scale, seed=props.seed)
                z_top += n * props.noise_strength
                verts.append((x, y, z_top))

        for ring in range(n_ring + 1):
            t_ring = ring / n_ring
            radius = t_ring * props.cap_radius
            for seg in range(n_seg + 1):
                angle = -math.pi / 2 + seg * math.pi / n_seg
                x = math.cos(angle) * radius
                y = math.sin(angle) * radius
                z_bot = 0.0
                n = self.noise3d(x, y, z_bot, props.detail_scale, seed=props.seed)
                z_bot += n * props.noise_strength * 0.3
                verts.append((x, y, z_bot))

        # Top surface faces (normal up).
        for ring in range(n_ring):
            for seg in range(n_seg):
                v0 = top_base + ring * (n_seg + 1) + seg
                v1 = top_base + ring * (n_seg + 1) + seg + 1
                v2 = top_base + (ring + 1) * (n_seg + 1) + seg + 1
                v3 = top_base + (ring + 1) * (n_seg + 1) + seg
                faces.append((v0, v1, v2, v3))

        # Bottom surface faces (normal down - reversed winding).
        for ring in range(n_ring):
            for seg in range(n_seg):
                v0 = bot_base + ring * (n_seg + 1) + seg
                v1 = bot_base + ring * (n_seg + 1) + seg + 1
                v2 = bot_base + (ring + 1) * (n_seg + 1) + seg + 1
                v3 = bot_base + (ring + 1) * (n_seg + 1) + seg
                faces.append((v0, v3, v2, v1))

        # Outer rim (ring = n_ring) - connect top to bottom.
        for seg in range(n_seg):
            v0_t = top_base + n_ring * (n_seg + 1) + seg
            v1_t = top_base + n_ring * (n_seg + 1) + seg + 1
            v0_b = bot_base + n_ring * (n_seg + 1) + seg
            v1_b = bot_base + n_ring * (n_seg + 1) + seg + 1
            faces.append((v0_t, v1_t, v1_b, v0_b))

        # Back edge seg=0 (angle=-pi/2, the -Y side, x=0) - connect top to bottom.
        for ring in range(n_ring):
            v0_t = top_base + ring * (n_seg + 1)
            v1_t = top_base + (ring + 1) * (n_seg + 1)
            v0_b = bot_base + ring * (n_seg + 1)
            v1_b = bot_base + (ring + 1) * (n_seg + 1)
            faces.append((v1_t, v0_t, v0_b, v1_b))

        # Back edge seg=n_seg (angle=pi/2, the +Y side, x=0) - connect top to bottom.
        for ring in range(n_ring):
            v0_t = top_base + ring * (n_seg + 1) + n_seg
            v1_t = top_base + (ring + 1) * (n_seg + 1) + n_seg
            v0_b = bot_base + ring * (n_seg + 1) + n_seg
            v1_b = bot_base + (ring + 1) * (n_seg + 1) + n_seg
            faces.append((v0_t, v1_t, v1_b, v0_b))

        return verts, faces

    # ------------------------------------------------------------------
    #  Stem generation - dispatches by mushroom type
    # ------------------------------------------------------------------
    def generate_stem_points(self, props):
        """Generate stem vertices and faces based on mushroom type.

        Returns (verts, faces) or None when the type has no stem (SHELF).
        """
        mtype = props.mushroom_type
        if mtype == 'SHELF':
            return None  # bracket fungi have no stem
        if mtype == 'MOREL':
            return self._generate_morel_stem(props)
        return self._generate_amanita_stem(props)

    def _generate_amanita_stem(self, props):
        """Amanita stem - bulbous volva base tapering to narrower top."""
        segments = max(8, props.resolution // 2)
        rings = max(4, segments // 2)
        verts = []
        faces = []

        for ring in range(rings + 1):
            t = ring / rings
            ring_height = ring * props.stem_height / rings
            base_scale = 1.8 - 0.9 * (1 - (1 - t) ** 2)
            stem_radius = props.stem_radius * base_scale

            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                x = math.cos(angle) * stem_radius
                y = math.sin(angle) * stem_radius
                z = ring_height
                n = self.noise3d(x, y, z, props.detail_scale * 0.5, seed=props.seed)
                x += n * props.noise_strength * 0.5
                y += n * props.noise_strength * 0.5
                verts.append((x, y, z))

        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                faces.append((current, next_segment, next_ring_segment, next_ring))

        # Cap top and bottom for watertight solid.
        bottom_face = tuple(range(segments))
        faces.append(bottom_face[::-1])
        top_start = rings * segments
        top_face = tuple(range(top_start, top_start + segments))
        faces.append(top_face)
        return verts, faces

    def _generate_morel_stem(self, props):
        """Morel stem - thin, fairly uniform with slight taper, no bulbous base."""
        segments = max(8, props.resolution // 2)
        rings = max(4, segments // 2)
        verts = []
        faces = []

        for ring in range(rings + 1):
            t = ring / rings
            ring_height = ring * props.stem_height / rings
            # Gentle taper: slightly wider at base, narrower at top.
            stem_radius = props.stem_radius * (1.1 - 0.3 * t)

            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                x = math.cos(angle) * stem_radius
                y = math.sin(angle) * stem_radius
                z = ring_height
                n = self.noise3d(x, y, z, props.detail_scale * 0.5, seed=props.seed)
                x += n * props.noise_strength * 0.3
                y += n * props.noise_strength * 0.3
                verts.append((x, y, z))

        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                faces.append((current, next_segment, next_ring_segment, next_ring))

        # Cap top and bottom for watertight solid.
        bottom_face = tuple(range(segments))
        faces.append(bottom_face[::-1])
        top_start = rings * segments
        top_face = tuple(range(top_start, top_start + segments))
        faces.append(top_face)
        return verts, faces

    def apply_voxel_remesh(self, context, obj, props):
        """Apply voxel remesh to ensure watertight mesh, then add subsurf."""
        context.view_layer.objects.active = obj

        # Add remesh modifier
        mod = obj.modifiers.new(name="Voxel_Remesh", type='REMESH')
        mod.mode = 'VOXEL'
        mod.voxel_size = props.voxel_size
        mod.use_smooth_shade = True

        # Apply modifier
        bpy.ops.object.modifier_apply(modifier="Voxel_Remesh")

        # Add subdivision surface for smoothness (left as a live modifier
        # so the user can adjust or remove it after generation).
        mod = obj.modifiers.new(name="Smooth", type='SUBSURF')
        mod.levels = 2
        mod.render_levels = 3

    def create_material(self, obj, props):
        """Create material with proper nodes."""
        mat = bpy.data.materials.new(name="FungusMushroom_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()

        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')

        # Set material properties - cap_color is a 3-component RGB
        # FloatVectorProperty (size=3), so append alpha here.
        color = list(props.cap_color)
        if len(color) == 3:
            color.append(1.0)
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Roughness'].default_value = 0.6
        principled.inputs['Specular IOR Level'].default_value = 0.3

        # Link nodes
        links = mat.node_tree.links
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

        obj.data.materials.append(mat)

    def _cleanup_objects(self, context, objs):
        """Remove created objects and their orphaned mesh datablocks."""
        for obj in objs:
            if obj is None:
                continue
            if obj.name in context.scene.collection.objects:
                context.scene.collection.objects.unlink(obj)
            mesh = obj.data
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def execute(self, context):
        props = context.scene.zenv_fungus_mush_props
        created_objs = []

        try:
            # Generate cap mesh
            cap_verts, cap_faces = self.generate_cap_points(props)
            cap_obj = self.create_base_mesh(context, cap_verts, cap_faces, "FungusMushroom")
            created_objs.append(cap_obj)

            # Generate stem mesh (SHELF type returns None - no stem).
            stem_data = self.generate_stem_points(props)
            if stem_data is not None:
                stem_verts, stem_faces = stem_data
                stem_obj = self.create_base_mesh(context, stem_verts, stem_faces, "FungusMushroom_Stem")
                created_objs.append(stem_obj)

                # Deselect everything first so only cap+stem are joined.
                bpy.ops.object.select_all(action='DESELECT')
                cap_obj.select_set(True)
                stem_obj.select_set(True)
                context.view_layer.objects.active = cap_obj
                bpy.ops.object.join()

                # The stem_obj is now merged into cap_obj; remove it from
                # the cleanup list so we don't try to delete it twice.
                created_objs.remove(stem_obj)

            # Apply voxel remesh
            self.apply_voxel_remesh(context, cap_obj, props)

            # Create material
            self.create_material(cap_obj, props)

            logger.info("Generated fungus mushroom '%s'", cap_obj.name)
            self.report({'INFO'}, "Generated fungus mushroom")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Fungus mushroom generation failed: %s", e)
            self.report({'ERROR'}, f"Fungus mushroom generation failed: {e}")
            self._cleanup_objects(context, created_objs)
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_FungusMush(Panel):
    """Panel for Fungus Mushroom Generator"""
    bl_label = "PLANT Fungus Mushroom"
    bl_idname = "ZENV_PT_fungus_mush"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_fungus_mush_props

        # Mushroom type
        layout.prop(props, "mushroom_type")

        # Basic properties
        box = layout.box()
        box.label(text="Basic Properties")
        box.prop(props, "cap_radius")
        box.prop(props, "cap_height")
        box.prop(props, "stem_height")
        box.prop(props, "stem_radius")

        # Detail properties
        box = layout.box()
        box.label(text="Detail Properties")
        box.prop(props, "detail_scale")
        box.prop(props, "noise_strength")
        box.prop(props, "voxel_size")
        box.prop(props, "resolution")

        # Color
        box = layout.box()
        box.label(text="Appearance")
        box.prop(props, "cap_color")
        box.prop(props, "seed")

        # Generate button
        layout.operator("zenv.fungus_mush_add")

#endregion
#region REG
classes = (
    ZENV_PG_FungusMush,
    ZENV_OT_FungusMush,
    ZENV_PT_FungusMush,
)

def menu_func(self, context):
    """Add menu item to Add Mesh menu."""
    self.layout.operator("zenv.fungus_mush_add", text="PLANT Fungus Mushroom")

def register():
    """Register all addon classes, the scene property, the menu entry, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, "zenv_fungus_mush_props"):
        bpy.types.Scene.zenv_fungus_mush_props = PointerProperty(type=ZENV_PG_FungusMush)
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
    if hasattr(bpy.types.Scene, "zenv_fungus_mush_props"):
        delattr(bpy.types.Scene, "zenv_fungus_mush_props")
    try:
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except Exception:
        pass
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
