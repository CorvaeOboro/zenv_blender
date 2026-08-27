#region META
bl_info = {
    "name": 'GEN Medieval Stone',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Medieval Stone Block Generator with Wear and Damage',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['mesh', 'stone', 'procedural', 'medieval', 'damage', 'weathered'],
    "description_short": 'Medieval Stone Block Generator with Wear and Damage',
    "description_medium": 'Generates weathered medieval stone blocks with sword cuts, impact marks, corner chips, branching cracks, surface noise, and voxel remeshing.',
    "description_long": """
    Medieval Stone Block Generator
Generates weathered stone blocks with damage, wear patterns, and battle damage.
Supports sword cuts, impact marks, corner chips, branching cracks, surface noise
displacement, edge bevels, voxel remeshing, and optional debug visualization.""",
    "location": 'View3D > Sidebar > ZENV > GEN Medieval Stone',
    "image_overview": 'zenv_blender_GEN_stone_block.png',
    "addon_image": 'zenv_blender_GEN_stone_block.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import bmesh
import logging
import random
import math
import datetime
from mathutils import Vector, Matrix, noise, bvhtree
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty, FloatVectorProperty
from bpy.types import PropertyGroup, Operator, Panel

logger = logging.getLogger(__name__)
_zenv_stone_block_console_handler = None


def _install_logger():
    """Attach a single StreamHandler to the addon logger (idempotent)."""
    global _zenv_stone_block_console_handler
    if _zenv_stone_block_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_stone_block_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_stone_block_console_handler
    if _zenv_stone_block_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_stone_block_console_handler)
    except ValueError:
        pass
    _zenv_stone_block_console_handler = None

#endregion
#region PROPS
class ZENV_PG_StoneBlock(PropertyGroup):
    """Properties for the Medieval Stone Generator"""
    # Base shape properties
    width: FloatProperty(
        name="Width",
        description="Width of the stone block",
        default=1.0,
        min=0.2,
        max=3.0,
        unit='LENGTH'
    )
    height: FloatProperty(
        name="Height",
        description="Height of the stone block",
        default=0.5,
        min=0.2,
        max=2.0,
        unit='LENGTH'
    )
    depth: FloatProperty(
        name="Depth",
        description="Depth of the stone block",
        default=0.7,
        min=0.2,
        max=2.0,
        unit='LENGTH'
    )
    bevel_width: FloatProperty(
        name="Bevel Width",
        description="Width of edge bevels",
        default=0.02,
        min=0.001,
        max=0.1,
        precision=3
    )
    
    # Damage and wear properties
    enable_sword_damage: BoolProperty(
        name="Sword Damage",
        description="Add sword cut damage to the stone",
        default=True
    )
    sword_damage_count: IntProperty(
        name="Sword Cuts",
        description="Number of sword cuts to add",
        default=1,
        min=1,
        max=5
    )
    enable_impact_damage: BoolProperty(
        name="Impact Damage",
        description="Add impact/chip damage to the stone",
        default=True
    )
    impact_damage_count: IntProperty(
        name="Impact Marks",
        description="Number of impact marks to add",
        default=2,
        min=1,
        max=6
    )
    enable_corner_damage: BoolProperty(
        name="Corner Damage",
        description="Add damage to corners",
        default=True
    )
    corner_damage_chance: FloatProperty(
        name="Corner Damage Chance",
        description="Chance of damage per corner (0-1). Each corner runs a voxel remesh and a boolean, so keep this low for fast generation",
        default=0.25,
        min=0,
        max=1
    )
    enable_cracks: BoolProperty(
        name="Cracks",
        description="Add cracks to the stone",
        default=True
    )
    crack_count: IntProperty(
        name="Crack Count",
        description="Number of cracks to add",
        default=1,
        min=1,
        max=4
    )
    
    # Debug mode
    debug_mode: BoolProperty(
        name="Debug Mode",
        description="Show intermediate steps and damage objects",
        default=False
    )
    
    # Completion option
    complete_mesh: BoolProperty(
        name="Complete Mesh",
        description="Apply all modifiers and cleanup temporary objects",
        default=True
    )

    # Per-generation seed - tags every created object/mesh/collection so
    # re-runs cannot collide with leftover data from a previous failed run.
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed for this generation. 0 = pick a fresh random seed each click. Used as a suffix on all created data-blocks for unique naming",
        default=0,
        min=0,
        max=999999,
    )

    def draw_debug_layout(self, layout):
        """Draw debug mode UI elements"""
        box = layout.box()
        box.label(text="Debug Options:")
        row = box.row()
        row.prop(self, "debug_mode")
        row.prop(self, "complete_mesh")

#endregion
#region OP
class ZENV_OT_StoneBlock(Operator):
    """Create a new medieval stone block"""
    bl_idname = "zenv.generate_stone_block"
    bl_label = "Generate Stone Block"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    @staticmethod
    def make_seed_suffix(generation_seed):
        """Format a generation seed into a stable, sortable name suffix."""
        return f"seed{int(generation_seed):06d}"

    def create_base_block(self, props, seed_suffix):
        """Create the base stone block, tagged with the per-generation suffix."""
        # Create base cube
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            enter_editmode=False,
            align='WORLD'
        )
        block = bpy.context.active_object
        block.scale = Vector((props.width, props.depth, props.height))
        block.name = f"Medieval_Stone_{seed_suffix}"
        if block.data is not None:
            block.data.name = f"Medieval_Stone_{seed_suffix}"

        # Apply scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        return block

    def add_bevel(self, obj, props):
        """Add beveled edges"""
        bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
        bevel.width = props.bevel_width
        bevel.segments = 3
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = math.radians(45)

    def apply_voxel_remesh(self, obj, voxel_size):
        """Apply voxel remesh with tuned settings"""
        mod = obj.modifiers.new(name="VoxelRemesh", type='REMESH')
        mod.mode = 'VOXEL'
        mod.voxel_size = voxel_size
        mod.use_smooth_shade = True
        
        # Apply modifier
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = bpy.data.meshes.new_from_object(obj_eval)
        old_mesh = obj.data
        obj.data = mesh_eval
        obj.modifiers.remove(mod)
        
        # Remove old mesh
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    def _apply_boolean_immediately(self, target_obj, cutter_obj, modifier_name, solver='FLOAT', operation='DIFFERENCE'):
        """Add a boolean modifier referencing cutter_obj and bake it into target_obj immediately.

        Baking each boolean step in isolation is more stable than
        stacking N booleans and applying them later: a single bad cutter
        cannot poison the whole stack, and the depsgraph evaluates
        a single boolean against a known-good mesh each time.

        The cutter must be visible to the depsgraph (linked into a scene
        collection) for the boolean to evaluate. We auto-link it into the
        scene collection if it has no users yet, and clean that link up
        afterwards so the caller's own collection management is preserved.
        """
        scene_collection = bpy.context.scene.collection
        we_linked_cutter = False
        if not cutter_obj.users_collection:
            scene_collection.objects.link(cutter_obj)
            we_linked_cutter = True

        bool_mod = target_obj.modifiers.new(name=modifier_name, type='BOOLEAN')
        bool_mod.object = cutter_obj
        bool_mod.operation = operation
        bool_mod.solver = solver

        depsgraph = bpy.context.evaluated_depsgraph_get()
        target_eval = target_obj.evaluated_get(depsgraph)
        baked_mesh = bpy.data.meshes.new_from_object(target_eval)
        old_mesh = target_obj.data
        target_obj.data = baked_mesh
        target_obj.modifiers.remove(bool_mod)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

        if we_linked_cutter:
            scene_collection.objects.unlink(cutter_obj)

    def set_normals_by_face_area(self, obj):
        """Recalculate face normals for correct shading on the post-boolean mesh.

        After boolean operations, the mesh can have irregular face sizes and
        inconsistent normals. This recalculates face normals via BMesh and
        enables smooth shading so the stone surface looks weathered rather
        than faceted.
        """
        if not obj.data or not isinstance(obj.data, bpy.types.Mesh):
            return

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()

        # Enable smooth shading for the weathered stone look.
        for poly in obj.data.polygons:
            poly.use_smooth = True
        obj.data.update()

    def apply_noise_displacement(self, obj, noise_scale=1.0, strength=1.0, detail=5):
        """Apply Python-based 3D noise displacement"""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        # Recalculate normals before using them for displacement direction.
        bm.normal_update()

        # Apply noise to each vertex
        for vert in bm.verts:
            point = Vector((
                vert.co.x * noise_scale,
                vert.co.y * noise_scale,
                vert.co.z * noise_scale
            ))
            
            displacement = 0.0
            amplitude = strength
            freq = 1.0
            
            # Add multiple octaves of noise
            for _ in range(detail):
                # Combine different noise types for more interesting results
                value = (
                    noise.noise(point) * 0.5 +                     # Regular noise
                    noise.turbulence_vector(point, 2, True).x * 0.3 +    # Turbulence with hard transitions
                    noise.fractal(point * 1.5, 0.5, 2.0, 2) * 0.2  # Fractal noise with H=0.5, lacunarity=2.0, octaves=2
                )
                
                displacement += value * amplitude
                amplitude *= 0.5
                point *= 2.0  # Double frequency each octave
            
            # Apply displacement along vertex normal
            vert.co += vert.normal * displacement
        
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

    def generate_branching_crack(self, start_point, direction, length, depth, branches=3, rng=None):
        """Generate a detailed branching crack.

        If ``rng`` is provided, uses it for all random calls (deterministic).
        Otherwise falls back to the global random module.
        """
        if rng is None:
            rng = random
        bm = bmesh.new()

        # Parameters for crack detail. Segment count is derived from
        # ``length * 6`` instead of the earlier ``int(length * 20)``, which
        # produced thousands of bmesh faces per crack and dominated
        # generation time. ``length * 6`` keeps visual detail while running
        # ~3x faster.
        segments = max(2, int(length * 6))
        width_start = length * 0.08  # Base width of crack
        depth_start = depth * 0.6  # Base depth

        def create_crack_segment(start, direction, length, width, depth, detail_level=1):
            """Create a detailed crack segment with surface variation"""
            # Calculate end point with natural curve
            curve_strength = rng.uniform(0.1, 0.3) * length
            side_vec = direction.cross(Vector((0, 0, 1))).normalized()
            curve_offset = side_vec * math.sin(rng.uniform(0, math.pi)) * curve_strength

            # Add noise to direction
            noise_scale = 0.3 * detail_level
            noise_vec = Vector((
                rng.uniform(-noise_scale, noise_scale),
                rng.uniform(-noise_scale, noise_scale),
                rng.uniform(-noise_scale, noise_scale)
            ))
            end_point = start + direction * length + curve_offset + noise_vec

            # Create base vertices for the segment
            points = []
            num_sides = 6  # Hexagonal profile for finer detail

            # Create profile points
            for i in range(num_sides):
                angle = (i / num_sides) * 2 * math.pi
                # Vary the radius slightly for each point
                radius = width * (0.8 + rng.uniform(0, 0.4))
                x = math.cos(angle) * radius
                z = math.sin(angle) * radius
                points.append(Vector((x, 0, z)))
            
            # Create vertices for start and end
            start_verts = []
            end_verts = []
            
            # Transform matrix for profile alignment
            rot_mat = direction.to_track_quat('-Y', 'Z').to_matrix()
            
            # Create vertices with surface detail
            for p in points:
                # Add surface detail using noise
                noise_val = noise.noise((p * 10.0).to_tuple()) * width * 0.5
                surface_detail = Vector((noise_val, 0, noise_val))
                
                # Create start vertex
                start_p = start + rot_mat @ (p + surface_detail)
                start_p.z -= depth * (1 + noise.noise((start_p * 5.0).to_tuple()) * 0.3)
                start_verts.append(bm.verts.new(start_p))
                
                # Create end vertex with reduced width and depth
                end_p = end_point + rot_mat @ (p + surface_detail) * 0.7  # Taper the crack
                end_p.z -= depth * 0.7 * (1 + noise.noise((end_p * 5.0).to_tuple()) * 0.3)
                end_verts.append(bm.verts.new(end_p))
            
            # Create faces between vertices
            for i in range(num_sides):
                i2 = (i + 1) % num_sides
                try:
                    bm.faces.new((start_verts[i], start_verts[i2],
                                end_verts[i2], end_verts[i]))
                except ValueError:
                    pass  # Face already exists (overlapping verts)

            # Add interior detail
            center_start = bm.verts.new(start + Vector((0, 0, -depth * 1.2)))
            center_end = bm.verts.new(end_point + Vector((0, 0, -depth * 0.8)))

            for i in range(num_sides):
                i2 = (i + 1) % num_sides
                try:
                    bm.faces.new((start_verts[i], start_verts[i2], center_start))
                    bm.faces.new((end_verts[i], end_verts[i2], center_end))
                except ValueError:
                    pass  # Face already exists
            
            # Calculate new direction for next segment
            new_direction = (end_point - start).normalized()
            
            return end_point, new_direction, end_verts
        
        # Create main crack
        prev_point = start_point
        prev_direction = direction
        main_points = [prev_point]
        
        for i in range(segments):
            # Calculate segment parameters
            segment_length = length / segments
            current_width = width_start * (1 - (i / segments) * 0.7)  # Taper the crack
            current_depth = depth_start * (1 - (i / segments) * 0.5)
            
            # Create segment
            end_point, new_direction, end_verts = create_crack_segment(
                prev_point, prev_direction, segment_length, 
                current_width, current_depth, detail_level=1.0)
            
            # Update for next segment
            prev_point = end_point
            prev_direction = new_direction
            main_points.append(prev_point)
        
        # Create branches
        for i, point in enumerate(main_points[1:-1]):  # Skip first and last points
            if rng.random() < 0.3:  # 30% chance of branch
                # Calculate branch direction
                main_dir = (main_points[i+2] - main_points[i]).normalized()
                branch_dir = main_dir.cross(Vector((0, 0, 1)))
                if rng.random() < 0.5:
                    branch_dir = -branch_dir

                # Rotate branch direction randomly
                angle = rng.uniform(math.pi/6, math.pi/3)  # 30-60 degrees
                rot_mat = Matrix.Rotation(angle, 3, main_dir)
                branch_dir = rot_mat @ branch_dir

                # Create branch with reduced parameters
                branch_length = length * rng.uniform(0.3, 0.5)
                branch_width = width_start * 0.6
                branch_depth = depth_start * 0.7

                create_crack_segment(point, branch_dir, branch_length,
                                  branch_width, branch_depth, detail_level=0.7)
        
        # Add final surface detail
        bmesh.ops.subdivide_edges(bm,
            edges=bm.edges[:],
            cuts=1)

        # Recalculate normals and ensure lookup tables are valid after subdivision.
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.normal_update()

        for v in bm.verts:
            if not v.is_boundary:
                noise_val = noise.noise((v.co * 20.0).to_tuple()) * width_start * 0.3
                v.co += v.normal * noise_val

        return bm

    def apply_damage(self, obj, props, seed_suffix, rng=None):
        """Apply damage to the object. Collections are tagged with seed_suffix.

        Uses ``rng`` (a random.Random instance) for all random calls if provided.
        """
        if rng is None:
            rng = random
        # Create collection for damage objects if it doesn't exist
        damage_collection_name = f"Damage_Objects_{seed_suffix}"
        damage_collection = bpy.data.collections.get(damage_collection_name)
        if not damage_collection:
            damage_collection = bpy.data.collections.new(damage_collection_name)
            bpy.context.scene.collection.children.link(damage_collection)

        # Debug collection for visualization
        debug_collection = None
        if props.debug_mode:
            debug_collection_name = f"Debug_Damage_{seed_suffix}"
            debug_collection = bpy.data.collections.get(debug_collection_name)
            if not debug_collection:
                debug_collection = bpy.data.collections.new(debug_collection_name)
                bpy.context.scene.collection.children.link(debug_collection)
        
        # Apply sword damage. Each cut is baked into the block immediately
        # so a single bad cutter cannot poison the modifier stack and we
        # never re-evaluate N stacked booleans together.
        if props.enable_sword_damage:
            for i in range(props.sword_damage_count):
                size = rng.uniform(props.width * 0.2, props.width * 0.3)
                damage_obj = self.create_sword_damage(size)
                if damage_obj is None:
                    logger.warning("Sword damage %d skipped: create_sword_damage returned None", i)
                    continue

                damage_obj.name = f"SwordCutter_{i}"
                damage_obj.location = self.get_random_surface_point(obj, rng)
                damage_obj.rotation_euler = (
                    rng.uniform(-math.pi / 4, math.pi / 4),
                    rng.uniform(-math.pi / 4, math.pi / 4),
                    rng.uniform(0, 2 * math.pi),
                )

                # Invariant: do NOT call project_to_surface here. That call
                # raycasts every cutter vertex onto the target and snaps it
                # to the hit, which collapses the 3D wedge into a
                # non-manifold zero-thickness sheet. The FAST boolean
                # solver on such a sheet returns the cutter as the result
                # instead of subtracting it - exactly the "sheet planes"
                # output bug. The cutter is positioned half-in / half-out
                # of the surface already, which produces the correct
                # slice-into-block when boolean DIFFERENCE is applied.

                # Link to damage collection so depsgraph can evaluate it.
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)

                if props.debug_mode:
                    debug_obj = damage_obj.copy()
                    debug_obj.data = damage_obj.data.copy()
                    debug_obj.location.x += 3
                    debug_collection.objects.link(debug_obj)
                    self.create_debug_text(
                        f"Sword Cut {i + 1}",
                        debug_obj.location + Vector((0, 0.5, 0)),
                    )

                self._apply_boolean_immediately(
                    obj, damage_obj, f"Sword_{i}", solver='FLOAT'
                )
                damage_obj.hide_viewport = True

        # Apply impact damage (same isolated-bake pattern as sword).
        if props.enable_impact_damage:
            for i in range(props.impact_damage_count):
                size = rng.uniform(props.width * 0.1, props.width * 0.2)
                damage_obj = self.create_impact_damage(size)
                if damage_obj is None:
                    logger.warning("Impact damage %d skipped: create_impact_damage returned None", i)
                    continue

                damage_obj.name = f"ImpactCutter_{i}"
                damage_obj.location = self.get_random_surface_point(obj, rng)
                damage_obj.rotation_euler = (
                    rng.uniform(0, 2 * math.pi),
                    rng.uniform(0, 2 * math.pi),
                    rng.uniform(0, 2 * math.pi),
                )

                # No project_to_surface (see Sword comment above).
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)

                if props.debug_mode:
                    debug_obj = damage_obj.copy()
                    debug_obj.data = damage_obj.data.copy()
                    debug_obj.location.x += 6
                    debug_collection.objects.link(debug_obj)
                    self.create_debug_text(
                        f"Impact {i + 1}",
                        debug_obj.location + Vector((0, 0.5, 0)),
                    )

                self._apply_boolean_immediately(
                    obj, damage_obj, f"Impact_{i}", solver='FLOAT'
                )
                damage_obj.hide_viewport = True

        # Final voxel remesh heals any FAST-solver seams from the bakes.
        self.apply_voxel_remesh(obj, 0.05)

    def create_sword_damage(self, size):
        """Create sword slash damage object with debug visualization"""
        bm = bmesh.new()
        steps = []
        
        # 1. Create base wedge shape
        length = size * 1.0  # Reduced length
        width = size * 0.12  # Thinner cut
        depth = size * 0.25  # Shallower cut
        
        # Create wedge shape vertices
        points = [
            Vector((-width/2, -length/2, depth/2)),   # Front top left
            Vector((width/2, -length/2, depth/2)),    # Front top right
            Vector((0, -length/2, -depth/2)),         # Front bottom center
            Vector((-width/2, length/2, depth/2)),    # Back top left
            Vector((width/2, length/2, depth/2)),     # Back top right
            Vector((0, length/2, -depth/2))           # Back bottom center
        ]
        
        # Create vertices and faces
        verts = [bm.verts.new(p) for p in points]
        bm.faces.new((verts[0], verts[1], verts[2]))  # Front face
        bm.faces.new((verts[3], verts[4], verts[5]))  # Back face
        bm.faces.new((verts[0], verts[3], verts[5], verts[2]))  # Left side
        bm.faces.new((verts[1], verts[4], verts[5], verts[2]))  # Right side
        bm.faces.new((verts[0], verts[1], verts[4], verts[3]))  # Top face

        # Recalculate face normals for consistent winding.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Create base mesh
        base_mesh = bpy.data.meshes.new("Sword_Base")
        bm.to_mesh(base_mesh)
        steps.append((base_mesh, "1. Base Shape"))
        
        # 2. Add subdivisions for detail
        bmesh.ops.subdivide_edges(bm,
            edges=bm.edges[:],
            cuts=2)
        
        subdiv_mesh = bpy.data.meshes.new("Sword_Subdiv")
        bm.to_mesh(subdiv_mesh)
        steps.append((subdiv_mesh, "2. Subdivided"))
        
        # 3. Add edge wear
        for v in bm.verts:
            if not v.is_boundary:
                pos = v.co * 15.0
                noise_val = noise.noise(pos.to_tuple())
                # Add more displacement near edges
                edge_factor = min(1.0, sum(1 for e in v.link_edges if e.is_boundary) / 2.0)
                v.co += v.normal * abs(noise_val) * size * 0.05 * (1 + edge_factor)
        
        wear_mesh = bpy.data.meshes.new("Sword_Wear")
        bm.to_mesh(wear_mesh)
        steps.append((wear_mesh, "3. Edge Wear"))
        
        # 4. First remesh to unify geometry
        wear_obj = bpy.data.objects.new("Sword_Wear_Temp", wear_mesh)
        bpy.context.scene.collection.objects.link(wear_obj)
        
        voxel = wear_obj.modifiers.new(name="VoxelRemesh1", type='REMESH')
        voxel.mode = 'VOXEL'
        # Coarsened (was 0.02). The sword wedge spans ~size, so at 0.04 we
        # still get ~25 voxels along the long axis - enough resolution for
        # the post-boolean voxel remesh on the block to absorb the cut.
        voxel.voxel_size = size * 0.04
        voxel.use_smooth_shade = True

        # Apply first remesh
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = wear_obj.evaluated_get(depsgraph)
        remesh1_mesh = bpy.data.meshes.new_from_object(obj_eval)
        remesh1_mesh.name = "Impact_Remesh1"
        steps.append((remesh1_mesh, "4. First Remesh"))

        # Cleanup temporary object
        bpy.context.scene.collection.objects.unlink(wear_obj)
        bpy.data.objects.remove(wear_obj)

        # 5. Final remesh for clean boolean
        remesh1_obj = bpy.data.objects.new("Sword_Remesh1_Temp", remesh1_mesh)
        bpy.context.scene.collection.objects.link(remesh1_obj)

        voxel = remesh1_obj.modifiers.new(name="VoxelRemesh2", type='REMESH')
        voxel.mode = 'VOXEL'
        # Coarsened (was 0.015).
        voxel.voxel_size = size * 0.03
        voxel.use_smooth_shade = True
        
        # Apply final remesh
        obj_eval = remesh1_obj.evaluated_get(depsgraph)
        final_mesh = bpy.data.meshes.new_from_object(obj_eval)
        final_mesh.name = "Impact_Final"
        steps.append((final_mesh, "5. Final Clean Mesh"))
        
        # Cleanup temporary object
        bpy.context.scene.collection.objects.unlink(remesh1_obj)
        bpy.data.objects.remove(remesh1_obj)
        
        # Create debug visualization (independent copies so the returned
        # final object is not coupled to debug-mode being on).
        debug_collection, debug_objects = self.create_debug_visualization(
            "Sword",
            steps,
            Vector((3, 0, 0)),  # Base location
            "Debug_Sword_Steps"
        )

        # Always build the actual final object from final_mesh regardless of
        # debug mode. Pulling the final object out of ``debug_objects`` (which
        # is empty when debug mode is off) would cause ``apply_damage`` to
        # dereference ``None``.
        final_obj = None
        if final_mesh is not None:
            actual_final_mesh = final_mesh.copy()
            actual_final_mesh.name = "Sword_Actual_Final"
            final_obj = bpy.data.objects.new("Sword_Actual_Final", actual_final_mesh)

        if not debug_collection:
            # Cleanup intermediate meshes if not in debug mode.
            for intermediate_mesh, _ in steps[:-1]:
                if intermediate_mesh.users == 0:
                    bpy.data.meshes.remove(intermediate_mesh)

        bm.free()
        return final_obj

    def create_impact_damage(self, size):
        """Create impact/chip damage object with debug visualization"""
        steps = []
        final_mesh = None
        
        # 1. Create base shape
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm,
            subdivisions=2,
            radius=size * 0.15
        )
        
        base_mesh = bpy.data.meshes.new("Impact_Base")
        bm.to_mesh(base_mesh)
        steps.append((base_mesh, "1. Base Shape"))
        bm.free()
        
        # 2. First remesh to unify geometry
        base_obj = bpy.data.objects.new("Impact_Base_Temp", base_mesh)
        bpy.context.scene.collection.objects.link(base_obj)
        
        voxel = base_obj.modifiers.new(name="VoxelRemesh1", type='REMESH')
        voxel.mode = 'VOXEL'
        # Coarsened (was 0.02).
        voxel.voxel_size = size * 0.04
        voxel.use_smooth_shade = True
        
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = base_obj.evaluated_get(depsgraph)
        remesh1_mesh = bpy.data.meshes.new_from_object(obj_eval)
        remesh1_mesh.name = "Impact_Remesh1"
        steps.append((remesh1_mesh, "2. First Remesh"))
        
        # Cleanup
        bpy.context.scene.collection.objects.unlink(base_obj)
        bpy.data.objects.remove(base_obj)
        
        # 3. Add crystalline features
        bm = bmesh.new()
        bm.from_mesh(remesh1_mesh)
        
        for v in bm.verts:
            pos = v.co * 8.0
            noise_val = noise.noise(pos.to_tuple())
            # Controlled displacement
            displacement = v.normal * abs(noise_val) * size * 0.08  # Reduced strength
            # Add angular features
            displacement.x = round(displacement.x * 4) / 4
            displacement.y = round(displacement.y * 4) / 4
            displacement.z = round(displacement.z * 4) / 4
            v.co += displacement
        
        crystal_mesh = bpy.data.meshes.new("Impact_Crystal")
        bm.to_mesh(crystal_mesh)
        steps.append((crystal_mesh, "3. Crystal Features"))
        bm.free()
        
        # 4. Second remesh to clean up
        crystal_obj = bpy.data.objects.new("Impact_Crystal_Temp", crystal_mesh)
        bpy.context.scene.collection.objects.link(crystal_obj)
        
        voxel = crystal_obj.modifiers.new(name="VoxelRemesh2", type='REMESH')
        voxel.mode = 'VOXEL'
        # Coarsened (was 0.015).
        voxel.voxel_size = size * 0.03
        voxel.use_smooth_shade = True
        
        obj_eval = crystal_obj.evaluated_get(depsgraph)
        remesh2_mesh = bpy.data.meshes.new_from_object(obj_eval)
        remesh2_mesh.name = "Impact_Remesh2"
        steps.append((remesh2_mesh, "4. Clean Mesh"))
        
        # Cleanup
        bpy.context.scene.collection.objects.unlink(crystal_obj)
        bpy.data.objects.remove(crystal_obj)
        
        # 5. Final subtle detail
        bm = bmesh.new()
        bm.from_mesh(remesh2_mesh)
        
        for v in bm.verts:
            pos = v.co * 20.0
            noise_val = noise.noise(pos.to_tuple())
            v.co += v.normal * abs(noise_val) * size * 0.01  # Subtle displacement
        
        final_mesh = bpy.data.meshes.new("Impact_Final")
        bm.to_mesh(final_mesh)
        steps.append((final_mesh, "5. Final Detail"))
        bm.free()
        
        # Create debug visualization with independent copies
        debug_collection, debug_objects = self.create_debug_visualization(
            "Impact",
            steps,
            Vector((6, 0, 0)),
            "Debug_Impact_Steps"
        )
        
        # Create the actual final object for boolean
        final_obj = None
        if final_mesh:
            actual_final_mesh = final_mesh.copy()
            actual_final_mesh.name = "Impact_Actual_Final"
            final_obj = bpy.data.objects.new("Impact_Actual_Final", actual_final_mesh)
        
        # Cleanup intermediate meshes
        for mesh, _ in steps:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        
        return final_obj

    def create_corner_damage(self, size):
        """Create corner chip damage object"""
        bm = bmesh.new()
        
        # Create simplified tetrahedron
        scale = size * 0.25
        verts = [
            Vector((0, 0, 0)),
            Vector((scale, 0, 0)),
            Vector((0, scale, 0)),
            Vector((0, 0, scale))
        ]
        
        # Create faces directly
        bmverts = [bm.verts.new(v) for v in verts]
        bm.faces.new((bmverts[0], bmverts[1], bmverts[2]))
        bm.faces.new((bmverts[0], bmverts[2], bmverts[3]))
        bm.faces.new((bmverts[0], bmverts[3], bmverts[1]))
        bm.faces.new((bmverts[1], bmverts[3], bmverts[2]))

        # Recalculate face normals for consistent winding.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Create mesh and object
        mesh = bpy.data.meshes.new("Corner_Damage")
        bm.to_mesh(mesh)
        bm.free()
        
        obj = bpy.data.objects.new("Corner_Damage", mesh)
        
        # Add voxel remesh with larger voxels (coarsened from 0.03 to 0.05).
        voxel = obj.modifiers.new(name="VoxelRemesh", type='REMESH')
        voxel.mode = 'VOXEL'
        voxel.voxel_size = size * 0.05
        voxel.use_smooth_shade = True
        
        # Apply modifier
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = bpy.data.meshes.new_from_object(obj_eval)
        obj.data = mesh_eval
        obj.modifiers.clear()

        return obj

    def apply_cracks(self, obj, props, seed_suffix, rng=None):
        """Apply crack damage to the object. Collection is tagged with seed_suffix.

        Uses ``rng`` (a random.Random instance) for all random calls if provided.
        """
        if rng is None:
            rng = random
        # Get object's corners
        bm = bmesh.new()
        bm.from_mesh(obj.data)

        corners = []
        for v in bm.verts:
            if len(v.link_edges) >= 3:  # Corner vertex
                corners.append(v.co.copy())
        bm.free()

        # Create collection for crack objects if it doesn't exist
        crack_collection_name = f"Crack_Objects_{seed_suffix}"
        crack_collection = bpy.data.collections.get(crack_collection_name)
        if not crack_collection:
            crack_collection = bpy.data.collections.new(crack_collection_name)
            bpy.context.scene.collection.children.link(crack_collection)
        
        # Parameters for crack generation
        base_length = min(props.width, props.height, props.depth) * 0.4
        base_depth = min(props.width, props.height, props.depth) * 0.05
        
        # Create cracks at corners and random points
        num_cracks = props.crack_count  # Use property value
        for i in range(num_cracks):
            # Choose start position
            if rng.random() < 0.7 and corners:  # 70% chance to start from corner
                start_pos = rng.choice(corners)
            else:
                # Random position on surface
                start_pos = obj.location + Vector((
                    rng.uniform(-props.width/2, props.width/2),
                    rng.uniform(-props.depth/2, props.depth/2),
                    rng.uniform(-props.height/2, props.height/2)
                ))

            # Calculate initial direction
            direction = Vector((
                rng.uniform(-1, 1),
                rng.uniform(-1, 1),
                rng.uniform(-1, 1)
            )).normalized()

            # Vary crack parameters
            length = base_length * rng.uniform(0.5, 1.2)
            depth = base_depth * rng.uniform(0.8, 1.2)
            num_branches = rng.randint(2, 4)

            # Generate crack mesh
            crack_bm = self.generate_branching_crack(
                start_pos, direction, length, depth, num_branches, rng=rng)
            
            # Create mesh and object
            crack_mesh = bpy.data.meshes.new(f"Crack_{i}")
            crack_bm.to_mesh(crack_mesh)
            crack_bm.free()
            
            crack_obj = bpy.data.objects.new(f"Crack_{i}", crack_mesh)
            crack_collection.objects.link(crack_obj)
            
            def project_crack_to_surface(crack_obj, target, base_depth):
                """Project crack vertices onto target surface and add depth variation"""
                # Create BVH tree for target
                depsgraph = bpy.context.evaluated_depsgraph_get()
                target_eval = target.evaluated_get(depsgraph)
                bvh = bvhtree.BVHTree.FromObject(target_eval, depsgraph, epsilon=0.00001)
                
                # Project each vertex
                for v in crack_obj.data.vertices:
                    # Get world space position
                    world_pos = crack_obj.matrix_world @ v.co
                    
                    # Convert normal to world space
                    normal_world = (crack_obj.matrix_world.to_3x3() @ v.normal).normalized()
                    
                    # Raycast from slightly above surface
                    hit, loc, hit_normal, _ = bvh.ray_cast(world_pos + normal_world * 0.1, normal_world)
                    
                    if hit:
                        # Calculate depth factor based on distance from center
                        center = crack_obj.location
                        dist = (world_pos - center).length
                        max_dist = max(crack_obj.dimensions) * 0.5
                        depth_factor = 1.0 - (dist / max_dist if max_dist > 0 else 0)
                        depth_factor = max(0, min(1, depth_factor))  # Clamp between 0 and 1
                        
                        # Create offset vector for depth
                        try:
                            # Try to create vector from components
                            normal_vec = Vector((hit_normal[0], hit_normal[1], hit_normal[2]))
                        except (TypeError, IndexError):
                            # Fallback to default up vector if hit_normal is invalid
                            normal_vec = Vector((0, 0, 1))
                        
                        offset_vec = normal_vec * (depth_factor * base_depth * 0.7)
                        
                        # Move vertex to hit location plus offset
                        v.co = crack_obj.matrix_world.inverted() @ (loc - offset_vec)
                
                # Update mesh
                crack_obj.data.update()
            
            # Project crack onto surface
            project_crack_to_surface(crack_obj, obj, base_depth)

            # Bake the boolean immediately (consistent with apply_damage).
            self._apply_boolean_immediately(
                obj, crack_obj, f"Crack_{i}", solver='FLOAT'
            )
            crack_obj.hide_viewport = True

    def apply_corner_damage(self, obj, props, seed_suffix, rng=None):
        """Apply damage to corners. Collection is tagged with seed_suffix.

        Uses ``rng`` (a random.Random instance) for all random calls if provided.
        """
        if rng is None:
            rng = random
        # Create collection for damage objects if it doesn't exist (shared
        # with apply_damage for the same generation).
        damage_collection_name = f"Damage_Objects_{seed_suffix}"
        damage_collection = bpy.data.collections.get(damage_collection_name)
        if not damage_collection:
            damage_collection = bpy.data.collections.new(damage_collection_name)
            bpy.context.scene.collection.children.link(damage_collection)
        
        # Get corners from bound box
        corners = obj.bound_box
        
        # Apply damage to each corner
        for i, corner in enumerate(corners):
            if rng.random() < props.corner_damage_chance:  # Use property value
                # Create smaller damage for corners
                size = rng.uniform(props.width * 0.1, props.width * 0.15)  # Reduced size range
                damage_obj = self.create_corner_damage(size)
                if damage_obj is None:
                    logger.warning("Corner damage %d skipped: create_corner_damage returned None", i)
                    continue

                # Position at corner with slight offset
                offset = Vector((
                    rng.uniform(-0.05, 0.05),
                    rng.uniform(-0.05, 0.05),
                    rng.uniform(-0.05, 0.05)
                )) * size
                damage_obj.location = obj.matrix_world @ Vector(corner) + offset

                # Random rotation with more variation
                damage_obj.rotation_euler = (
                    rng.uniform(-math.pi/2, math.pi/2),
                    rng.uniform(-math.pi/2, math.pi/2),
                    rng.uniform(0, 2*math.pi)
                )
                
                # No project_to_surface here either - flattening the
                # tetrahedron into a triangle sheet on the surface invalidates
                # the boolean. The tetra is already positioned at the
                # corner with random rotation so it bites into the corner
                # by construction.

                damage_obj.name = f"CornerCutter_{i}"
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)

                self._apply_boolean_immediately(
                    obj, damage_obj, f"Corner_{i}", solver='FLOAT'
                )
                damage_obj.hide_viewport = True

    def create_debug_text(self, text, location):
        """Create 3D text for debug visualization.

        Uses bpy.data.curves.new + bpy.data.objects.new instead of
        bpy.ops.object.text_add so it works in headless/non-viewport contexts.
        """
        text_curve = bpy.data.curves.new(name=f"DebugText_{text}", type='FONT')
        text_curve.body = text
        text_curve.size = 0.2
        text_obj = bpy.data.objects.new(f"DebugText_{text}", text_curve)
        text_obj.location = location
        return text_obj
    
    def create_debug_copy(self, obj, offset, label):
        """Create a copy of object for debug visualization"""
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.location = obj.location + Vector(offset)
        bpy.context.scene.collection.objects.link(copy)
        
        # Add label
        text = self.create_debug_text(label, copy.location + Vector((0, 1, 0)))
        text.parent = copy
        
        return copy

    def cleanup_temp_objects(self, context, seed_suffix=""):
        """Remove all temporary objects and collections used in generation.

        The cleanup removes obj.data *before* obj, which
        can trigger a side-effect free of the Object data-block when the
        mesh is the object's only user (the object then has 0 users and
        Blender garbage-collects it as part of the mesh removal). The next
        bpy.data.objects.remove(obj) call would then raise
        ReferenceError: StructRNA of type Object has been removed. Removing
        the Object first (with do_unlink=True for atomic collection unlink)
        avoids that race.
        """

        def _purge_collection(collection_name):
            target_collection = bpy.data.collections.get(collection_name)
            if target_collection is None:
                return
            # Snapshot mesh refs before removing objects so orphans can be purged
            # afterwards even if the Object struct goes away.
            orphan_meshes = []
            for child_object in list(target_collection.objects):
                child_mesh = getattr(child_object, "data", None)
                try:
                    bpy.data.objects.remove(child_object, do_unlink=True)
                except (ReferenceError, RuntimeError) as remove_object_error:
                    logger.warning(
                        "Could not remove temp object: %s",
                        remove_object_error,
                    )
                if child_mesh is not None:
                    orphan_meshes.append(child_mesh)

            for orphan_mesh in orphan_meshes:
                try:
                    if orphan_mesh.users == 0:
                        bpy.data.meshes.remove(orphan_mesh)
                except (ReferenceError, RuntimeError):
                    # Mesh was already freed as a side-effect of its last
                    # user being removed - nothing to do.
                    pass

            try:
                bpy.data.collections.remove(target_collection)
            except (ReferenceError, RuntimeError) as remove_collection_error:
                logger.warning(
                    "Could not remove collection %s: %s",
                    collection_name,
                    remove_collection_error,
                )

        if seed_suffix:
            _purge_collection(f"Damage_Objects_{seed_suffix}")
            _purge_collection(f"Crack_Objects_{seed_suffix}")
        else:
            # Fallback for callers that don't pass a suffix.
            _purge_collection("Damage_Objects")
            _purge_collection("Crack_Objects")

    def apply_all_modifiers(self, obj):
        """Apply all modifiers on the object in the correct order"""
        # Get current context and mode
        context = bpy.context
        current_active = context.active_object
        current_mode = current_active.mode if current_active else 'OBJECT'
        
        # Ensure we're in object mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Make our object active
        context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Apply all modifiers in reverse order (bottom to top)
        for modifier in reversed(obj.modifiers):
            try:
                # Ensure the modifier is visible and enabled
                modifier.show_viewport = True
                modifier.show_render = True
                
                # Apply the modifier
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except Exception as modifier_apply_error:
                logger.warning(
                    "Failed to apply modifier %s: %s",
                    modifier.name,
                    modifier_apply_error,
                )
                continue
        
        # Restore previous active object and mode
        obj.select_set(False)
        context.view_layer.objects.active = current_active
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=current_mode)

    def get_random_surface_point(self, obj, rng=None):
        """Get a random point on the object's surface using BVH tree.

        Uses ``rng`` (a random.Random instance) for all random calls if provided.
        """
        if rng is None:
            rng = random
        # Ensure object has mesh data
        if not obj.data or not isinstance(obj.data, bpy.types.Mesh):
            return obj.location
        
        # Get mesh data in world space
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh = obj.evaluated_get(depsgraph).data
        
        # Create BVH tree
        bvh = bvhtree.BVHTree.FromPolygons(
            [v.co for v in mesh.vertices],
            [p.vertices for p in mesh.polygons],
            epsilon=0.0
        )
        
        # Get object bounds
        bounds = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        min_bound = Vector((
            min(v[0] for v in bounds),
            min(v[1] for v in bounds),
            min(v[2] for v in bounds)
        ))
        max_bound = Vector((
            max(v[0] for v in bounds),
            max(v[1] for v in bounds),
            max(v[2] for v in bounds)
        ))
        
        # Try to find a valid surface point
        max_attempts = 20
        for _ in range(max_attempts):
            # Generate random point within bounds
            rand_point = Vector((
                rng.uniform(min_bound.x, max_bound.x),
                rng.uniform(min_bound.y, max_bound.y),
                rng.uniform(min_bound.z, max_bound.z)
            ))

            # Find nearest point on surface
            location, normal, index, distance = bvh.find_nearest(rand_point)

            if location:
                # Convert to world space
                return obj.matrix_world @ location

        # Fallback to a point on a random face
        if mesh.polygons:
            face = rng.choice(mesh.polygons)
            center = face.center
            return obj.matrix_world @ center
        
        # Final fallback to object location
        return obj.location

    def get_object_bounds(self, obj):
        """Get object bounds in world space"""
        bounds = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        min_bound = Vector((
            min(v[0] for v in bounds),
            min(v[1] for v in bounds),
            min(v[2] for v in bounds)
        ))
        max_bound = Vector((
            max(v[0] for v in bounds),
            max(v[1] for v in bounds),
            max(v[2] for v in bounds)
        ))
        size = max_bound - min_bound
        return min_bound, max_bound, size

    def position_debug_step(self, mesh_obj, text_obj, prev_obj, spacing=0.2):
        """Position debug step relative to previous object"""
        if prev_obj:
            # Get bounds of previous object
            prev_min, prev_max, prev_size = self.get_object_bounds(prev_obj)
            
            # Position current object next to previous
            mesh_obj.location.y = prev_max.y + spacing + prev_size.y/2
        
        # Get current object bounds
        min_bound, max_bound, size = self.get_object_bounds(mesh_obj)
        
        # Position text above object, centered
        text_obj.location = Vector((
            (min_bound.x + max_bound.x) / 2,  # Center X
            mesh_obj.location.y,               # Same Y as mesh
            max_bound.z + 0.1                  # Slightly above mesh
        ))
        text_obj.parent = mesh_obj

    def create_debug_visualization(self, obj_name, steps, base_location, collection_name):
        """Create debug visualization for a series of steps"""
        # Create or get debug collection
        debug_collection = None
        if bpy.context.scene.zenv_stone_block_generator.debug_mode:
            debug_collection = bpy.data.collections.get(collection_name)
            if not debug_collection:
                debug_collection = bpy.data.collections.new(collection_name)
                bpy.context.scene.collection.children.link(debug_collection)
        
        if not debug_collection:
            return None, []
        
        # Track objects for cleanup
        debug_objects = []
        prev_obj = None
        
        # Create each step
        for i, (mesh, label) in enumerate(steps):
            # Create a copy of the mesh for debug display
            debug_mesh = mesh.copy()
            debug_mesh.name = f"{obj_name}_Debug_{i+1}"
            
            # Create mesh object
            debug_obj = bpy.data.objects.new(f"{obj_name}_Debug_{i+1}", debug_mesh)
            debug_obj.location = base_location
            debug_collection.objects.link(debug_obj)
            
            # Create text
            text_obj = self.create_debug_text(label, Vector((0, 0, 0)))
            debug_collection.objects.link(text_obj)
            
            # Position objects
            self.position_debug_step(debug_obj, text_obj, prev_obj)
            
            debug_objects.extend([debug_obj, text_obj])
            prev_obj = debug_obj
        
        return debug_collection, debug_objects

    def execute(self, context):
        """Execute the stone block generation.

        Wraps the entire pipeline in try/except so that any failure reports
        an error to the user and cleans up temporary collections/objects
        rather than crashing Blender.
        """
        props = context.scene.zenv_stone_block_generator

        # Resolve a specific generation seed. When ``random_seed=0`` a
        # fresh integer is drawn per click so every run gets a unique suffix
        # and cannot collide with leftover collections from a previous run.
        if props.random_seed > 0:
            generation_seed = int(props.random_seed)
        else:
            generation_seed = random.randint(1, 999999)
        # Use a local RNG instance so we don't mutate the global random state.
        rng = random.Random(generation_seed)
        seed_suffix = self.make_seed_suffix(generation_seed)
        logger.info("Stone block generation starting (seed=%d)", generation_seed)

        block = None
        try:
            # Create base block (tagged with seed suffix).
            block = self.create_base_block(props, seed_suffix)
            if props.debug_mode:
                self.create_debug_copy(block, (-3, 0, 0), "Base Block")

            # Add initial bevel for base shape
            self.add_bevel(block, props)

            # First voxel remesh for base detail. 0.05 (was 0.04) cuts voxel
            # count by ~2x while preserving the post-bevel silhouette.
            self.apply_voxel_remesh(block, 0.05)
            if props.debug_mode:
                self.create_debug_copy(block, (-3, -3, 0), "After Initial Remesh")

            # Apply damage if enabled
            if props.enable_sword_damage or props.enable_impact_damage:
                self.apply_damage(block, props, seed_suffix, rng)
                if props.debug_mode:
                    self.create_debug_copy(block, (-3, -6, 0), "After Damage")

            # Apply cracks if enabled
            if props.enable_cracks:
                self.apply_cracks(block, props, seed_suffix, rng)
                if props.debug_mode:
                    self.create_debug_copy(block, (-3, -9, 0), "After Cracks")

            # Apply corner damage if enabled
            if props.enable_corner_damage:
                self.apply_corner_damage(block, props, seed_suffix, rng)
                if props.debug_mode:
                    self.create_debug_copy(block, (-3, -12, 0), "After Corner Damage")

            # Apply surface noise
            self.apply_noise_displacement(
                block,
                noise_scale=0.7,
                strength=0.015,
                detail=3,
            )

            if props.debug_mode:
                self.create_debug_copy(block, (-3, -15, 0), "Final Result")

            # If complete mesh option is enabled and not in debug mode.
            if props.complete_mesh and not props.debug_mode:
                self.apply_all_modifiers(block)

                # Rename the block BEFORE cleanup. The previous ordering ran
                # cleanup first, and any unrelated failure in cleanup that
                # invalidated the ``block`` Python reference would crash the
                # subsequent ``block.name = ...`` line. Renaming first means a
                # cleanup hiccup at most leaves stray temp objects in the
                # outliner instead of aborting the whole operator.
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                final_name = f"Stone_Block_{timestamp}_{seed_suffix}"
                try:
                    block.name = final_name
                    if block.data is not None:
                        block.data.name = final_name
                except (ReferenceError, RuntimeError) as rename_error:
                    logger.warning(
                        "Could not rename block to %s: %s",
                        final_name,
                        rename_error,
                    )

                # Now safe to purge temp collections - scoped to this seed so
                # we cannot accidentally delete unrelated user collections.
                self.cleanup_temp_objects(context, seed_suffix)

            # Final step: recalculate normals for correct shading
            # on the post-boolean mesh.
            self.set_normals_by_face_area(block)

            self.report({'INFO'}, f"Stone block generated (seed={generation_seed})")
            logger.info("Stone block generation complete (seed=%d)", generation_seed)
            return {'FINISHED'}

        except Exception as generation_error:
            logger.exception("Stone block generation failed (seed=%d)", generation_seed)
            # Clean up the partially-created block if it exists.
            if block is not None:
                try:
                    bpy.data.objects.remove(block, do_unlink=True)
                except (ReferenceError, RuntimeError):
                    pass
            # Purge any temp collections from this seed.
            try:
                self.cleanup_temp_objects(context, seed_suffix)
            except Exception:
                pass
            self.report({'ERROR'}, f"Stone block generation failed: {generation_error}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_StoneBlock(Panel):
    """Panel for Medieval Stone Generator"""
    bl_label = "GEN Medieval Stone"
    bl_idname = "ZENV_PT_StoneBlock"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_stone_block_generator
        
        # Base shape parameters
        box = layout.box()
        box.label(text="Base Shape:")
        box.prop(props, "width")
        box.prop(props, "height")
        box.prop(props, "depth")
        box.prop(props, "bevel_width")
        
        # Seed
        box = layout.box()
        box.label(text="Generation:")
        box.prop(props, "random_seed")

        # Damage parameters
        box = layout.box()
        box.label(text="Damage:")
        box.prop(props, "enable_sword_damage")
        if props.enable_sword_damage:
            box.prop(props, "sword_damage_count")
        
        box.prop(props, "enable_impact_damage")
        if props.enable_impact_damage:
            box.prop(props, "impact_damage_count")
        
        box.prop(props, "enable_corner_damage")
        if props.enable_corner_damage:
            box.prop(props, "corner_damage_chance")
        
        box.prop(props, "enable_cracks")
        if props.enable_cracks:
            box.prop(props, "crack_count")
        
        # Debug mode
        props.draw_debug_layout(layout)
        
        # Generate button
        layout.operator("zenv.generate_stone_block", text="Generate Stone Block")

#endregion
#region REG
classes = (
    ZENV_PG_StoneBlock,
    ZENV_OT_StoneBlock,
    ZENV_PT_StoneBlock,
)

def menu_func(self, context):
    """Add menu item to Add Mesh menu."""
    self.layout.operator("zenv.generate_stone_block", text="Stone Block", icon='MESH_ICOSPHERE')

def register():
    """Register all addon classes, the scene property, the menu entry, and configure the logger."""
    _install_logger()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_stone_block_generator = PointerProperty(type=ZENV_PG_StoneBlock)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    """Unregister all addon classes, remove the scene property, the menu entry, and the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_stone_block_generator"):
        delattr(bpy.types.Scene, "zenv_stone_block_generator")
    try:
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except Exception:
        pass
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
