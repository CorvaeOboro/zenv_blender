bl_info = {
    "name": 'GEN Stone Wall Physics Voronoi',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate layered stone walls using physics and voronoi subdivision',
    "status": 'wip',
    "approved": False,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['mesh', 'stone', 'wall', 'physics', 'procedural', 'voronoi'],
    "description_short": 'Generate layered stone walls using physics and voronoi subdivision',
    "description_medium": 'Generates stacked stone walls with large and filler stones, using rigid-body physics simulation for natural settling and BVH-accelerated overlap detection.',
    "description_long": """
    Stone Wall Physics Voronoi
Generates layered stone walls by creating individual stone meshes,
placing them with spatial-grid-accelerated BVH overlap detection,
adding rigid-body physics, and running a bullet physics simulation
so stones settle. Supports large stones and filler stones
per layer, configurable wall dimensions, and seed-based reproducibility.""",
    "location": 'View3D > ZENV',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}

import bpy
import bmesh
import random
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, IntProperty, PointerProperty
import logging

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

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_StoneWallProperties(PropertyGroup):
    """Properties for stone wall generation."""
    
    wall_width: FloatProperty(
        name="Wall Width",
        default=10.0,
        min=1.0,
        max=100.0,
        unit='LENGTH',
        description="Total width of the wall (X-axis extent)"
    )
    
    layers: IntProperty(
        name="Layers",
        default=3,
        min=1,
        max=10,
        description="Number of stone layers (levels)"
    )
    
    stones_per_layer: IntProperty(
        name="Large Stones per Layer",
        default=5,
        min=1,
        max=20,
        description="How many large stones to create in each layer"
    )
    
    stone_size_min: FloatProperty(
        name="Stone Size Min",
        default=1.0,
        min=0.1,
        max=10.0,
        unit='LENGTH',
        description="Minimum size of large stones"
    )

    stone_size_max: FloatProperty(
        name="Stone Size Max",
        default=2.0,
        min=0.1,
        max=10.0,
        unit='LENGTH',
        description="Maximum size of large stones"
    )

    filler_stone_size: FloatProperty(
        name="Filler Stone Size",
        default=0.5,
        min=0.1,
        max=5.0,
        unit='LENGTH',
        description="Size of the filler stones"
    )
    
    grid_divisions: IntProperty(
        name="Grid Divisions for Fillers",
        default=10,
        min=1,
        max=50,
        description="Number of grid cells along X used to place filler stones"
    )
    
    simulation_frames: IntProperty(
        name="Simulation Frames",
        default=20,
        min=1,
        max=100,
        description="How many frames to advance in the physics simulation"
    )
    
    wall_bound_min: FloatProperty(
        name="Wall Bound Min",
        default=-5.0,
        min=-50.0,
        max=50.0,
        unit='LENGTH',
        description="Minimum X-value for a stone to remain in the wall"
    )

    wall_bound_max: FloatProperty(
        name="Wall Bound Max",
        default=5.0,
        min=-50.0,
        max=50.0,
        unit='LENGTH',
        description="Maximum X-value for a stone to remain in the wall"
    )

    seed: IntProperty(
        name="Seed",
        default=0,
        min=0,
        max=10000,
        description="Random seed for reproducible walls (0 = random)"
    )

    z_bound_min: FloatProperty(
        name="Z Bound Min",
        default=-1.0,
        min=-50.0,
        max=0.0,
        unit='LENGTH',
        description="Minimum Z-value for a stone to remain (stones below this are removed)"
    )

    clump_strength: FloatProperty(
        name="Clump Force Strength",
        default=15.0,
        min=0.0,
        max=200.0,
        description="Strength of the Harmonic inward force that biases stones toward the wall center for clumping. Higher = stronger pull toward origin."
    )

    clump_frames: IntProperty(
        name="Clump Force Frames",
        default=30,
        min=1,
        max=200,
        description="Number of frames the inward clump force stays active before fading to zero. After this, only gravity affects the stones."
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_GenerateStoneWall(Operator):
    """Generate a stacked stone wall using physics and voronoi-like filler placement."""
    bl_idname = "zenv.generate_stone_wall"
    bl_label = "Generate Stone Wall"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.scene is not None

    @staticmethod
    def create_stone(context, rng, name, location, size, detail=0.2):
        """Create a rectangular stone mesh with proper detailing."""
        # Create mesh data first
        mesh = bpy.data.meshes.new(name=f"{name}_mesh")
        stone = bpy.data.objects.new(name, mesh)
        context.scene.collection.objects.link(stone)

        # Create base cube vertices
        stretch_x = rng.uniform(1.2, 1.5)
        stretch_y = rng.uniform(0.6, 0.8)
        verts = [
            (-0.5 * size * stretch_x, -0.5 * size * stretch_y, -0.5 * size),
            ( 0.5 * size * stretch_x, -0.5 * size * stretch_y, -0.5 * size),
            ( 0.5 * size * stretch_x,  0.5 * size * stretch_y, -0.5 * size),
            (-0.5 * size * stretch_x,  0.5 * size * stretch_y, -0.5 * size),
            (-0.5 * size * stretch_x, -0.5 * size * stretch_y,  0.5 * size),
            ( 0.5 * size * stretch_x, -0.5 * size * stretch_y,  0.5 * size),
            ( 0.5 * size * stretch_x,  0.5 * size * stretch_y,  0.5 * size),
            (-0.5 * size * stretch_x,  0.5 * size * stretch_y,  0.5 * size),
        ]
        
        # Define faces
        faces = [
            (0, 1, 2, 3),  # bottom
            (4, 5, 6, 7),  # top
            (0, 4, 7, 3),  # left
            (1, 5, 6, 2),  # right
            (0, 1, 5, 4),  # front
            (3, 2, 6, 7),  # back
        ]
        
        # Create the mesh
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        
        # Set location
        stone.location = location
        
        # Make active and select - deselect all first
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = stone
        stone.select_set(True)
        
        # Add slight random rotation (less on X and Y to keep stones more level)
        stone.rotation_euler = (
            rng.uniform(-0.1, 0.1),
            rng.uniform(-0.1, 0.1),
            rng.uniform(-0.3, 0.3)
        )
        
        # Apply rotation
        bpy.ops.object.transform_apply(rotation=True)

        # Wrap edit-mode operations in try/finally for cleanup
        noise_tex = None
        try:
            # --- Bevel FIRST on the clean cube edges so the chunky
            # chamfered corners are pristine.  Later operations are kept
            # subtle enough not to deform the bevel geometry. ---
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')

            # Low-poly single-face chamfer on all 12 cube edges.
            # segments=1 + profile=0.5 = a single flat cut at 45°,
            bpy.ops.mesh.bevel(
                offset=0.025,
                offset_type='WIDTH',
                segments=1,
                profile=0.5,
            )

            # Subdivide flat faces to give the displacement modifier
            # enough geometry for smooth natural surface variation.
            bpy.ops.mesh.subdivide(number_cuts=1)


            bpy.ops.object.mode_set(mode='OBJECT')

            # Subtle surface noise scaled by `detail` (≈2 mm for
            # large stones, ≈1 mm for fillers)  
            noise_tex = bpy.data.textures.new(name=f"{name}_noise", type='NOISE')
            displace = stone.modifiers.new(name="Displacement", type='DISPLACE')
            displace.texture = noise_tex
            displace.texture_coords = 'GLOBAL'
            displace.direction = 'NORMAL'
            displace.space = 'LOCAL'
            displace.strength = detail * 0.01
            displace.mid_level = 0.5
            bpy.ops.object.modifier_apply(modifier="Displacement")

            # Clean up any micro-doubles created by displacement.
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=0.0005)
            bpy.ops.mesh.delete_loose()
            bpy.ops.object.mode_set(mode='OBJECT')


            # Smooth shading so the bevel rounds read smoothly.
            bpy.ops.object.shade_smooth()

            # Area-weighted custom normals: large flat faces dominate
            # their vertices' normals (read as flat / chunky) while the
            # small bevel faces blend smoothly — the "flat faces with
            # solid chunky bevel" look.
            bpy.ops.object.mode_set(mode='EDIT')
            # No kwargs: the keep_custom/keep_sharp_edges arg only exists
            # in Blender 4.5+, but this addon targets 4.0 (see bl_info).
            bpy.ops.mesh.set_normals_from_faces()
            bpy.ops.object.mode_set(mode='OBJECT')

        finally:
            # Ensure we return to object mode
            if stone.mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            # Clean up noise texture even if modifier_apply failed
            if noise_tex is not None:
                try:
                    bpy.data.textures.remove(noise_tex)
                except Exception:
                    pass

        return stone

    @staticmethod
    def create_bvh_tree(context, obj):
        """Create a BVHTree from an object for precise collision detection."""
        # Get the mesh data in world space
        dg = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(dg)
        mesh = obj_eval.to_mesh()
        mesh.transform(obj.matrix_world)
        
        # Create BVHTree - must use triangulated faces
        mesh.calc_loop_triangles()
        bvh = BVHTree.FromPolygons(
            [v.co for v in mesh.vertices],
            [(tri.vertices[0], tri.vertices[1], tri.vertices[2]) for tri in mesh.loop_triangles],
            epsilon=0.0001
        )
        obj_eval.to_mesh_clear()
        return bvh

    @staticmethod
    def check_intersection(context, obj1, obj2):
        """Check if two objects intersect using precise BVHTree intersection."""
        # Create BVH trees for both objects
        bvh1 = ZENV_OT_GenerateStoneWall.create_bvh_tree(context, obj1)
        bvh2 = ZENV_OT_GenerateStoneWall.create_bvh_tree(context, obj2)
        
        # Find intersections
        intersect = bvh1.overlap(bvh2)
        return bool(intersect)

    @staticmethod
    def create_ground_plane(context, wall_width=10.0):
        """Create a volumetric ground plane for proper collision detection."""
        ground = next((obj for obj in bpy.data.objects if obj.name.startswith("Ground")), None)
        if ground is not None:
            return ground
        # Create ground plane - sized from wall_width
        plane_size = max(50.0, wall_width * 2.0)
        bpy.ops.mesh.primitive_plane_add(size=plane_size)
        ground = context.active_object
        ground.name = "Ground_Plane"

        # Convert to mesh for editing
        context.view_layer.objects.active = ground
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        # Extrude down to create volume
        bpy.ops.mesh.extrude_region_move()
        bpy.ops.transform.translate(value=(0, 0, -1))

        # Back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Add rigid body settings
        bpy.ops.rigidbody.object_add()
        if ground.rigid_body is None:
            raise RuntimeError(
                "create_ground_plane: bpy.ops.rigidbody.object_add() "
                "failed to create rigid body for ground plane."
            )
        ground.rigid_body.type = 'PASSIVE'
        ground.rigid_body.collision_shape = 'MESH'
        ground.rigid_body.friction = 1.0
        ground.rigid_body.restitution = 0.0
        ground.rigid_body.use_margin = True
        ground.rigid_body.collision_margin = 0.0001

        return ground

    @staticmethod
    def create_clump_force(context, strength, clump_frames):
        """Create a Harmonic force field at the origin that pulls stones inward
        for clumping, with its strength animated to zero after ``clump_frames``
        so only gravity acts afterwards.

        The force field is re-created each run (any previous
        ``StoneWall_ClumpForce`` object is removed first) so stale keyframes
        never accumulate.
        """
        scene = context.scene

        # Remove any previous clump force from earlier runs
        old = next((obj for obj in bpy.data.objects
                    if obj.name == "StoneWall_ClumpForce"), None)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        # Create the Empty via the data API rather than
        # bpy.ops.object.empty_add().  The operator relies on the 3D
        # viewport context (context.active_object / region) which is not
        # guaranteed when the operator is invoked from the sidebar panel —
        # in that case active_object is None and force_obj.field throws
        # "'NoneType' object has no attribute 'type'".  Building the
        # object directly from bpy.data is context-independent.
        force_obj = bpy.data.objects.new("StoneWall_ClumpForce", None)
        scene.collection.objects.link(force_obj)
        force_obj.empty_display_type = 'PLAIN_AXES'
        force_obj.location = (0.0, 0.0, 0.0)

        # Since Blender 3.0, Object.field is None by default and must be
        # initialized via the forcefield_toggle operator.
        # See: https://blender.stackexchange.com/questions/242846
        # We make the object active+selected first so the operator has a
        # valid target, then toggle the field on.
        for obj in scene.objects:
            obj.select_set(False)
        context.view_layer.objects.active = force_obj
        force_obj.select_set(True)
        bpy.ops.object.forcefield_toggle()

        # An Empty at the origin carries the Harmonic field.  Harmonic
        # pulls each rigid body toward the effector location with a
        # spring-like force proportional to distance, so stones far from
        # the center are pulled more — the clumping bias.
        field = force_obj.field
        if field is None:
            raise RuntimeError(
                f"create_clump_force: force_obj.field is still None after "
                f"forcefield_toggle (force_obj={force_obj!r})"
            )
        field.type = 'HARMONIC'
        field.strength = strength
        # No distance limits configured: the default Harmonic radius is
        # large enough to cover the wall.  (use_max/use_min/falloff_type
        # are not set because their enum/attribute availability varies
        # between Blender versions — see errors in this session.)

        # Animate strength: full at frame_start, zero at
        # frame_start + clump_frames.  Each layer's simulation resets to
        # frame_start, so every layer independently gets clump-then-gravity.
        start = scene.frame_start
        scene.frame_set(start)
        field.strength = strength
        field.keyframe_insert(data_path="strength")

        scene.frame_set(start + clump_frames)
        field.strength = 0.0
        field.keyframe_insert(data_path="strength")

        # Restore whatever frame we were on so we don't disturb callers
        scene.frame_set(start)

        for obj in scene.objects:
            obj.select_set(False)
        return force_obj

    @staticmethod
    def create_spatial_grid(cell_size=1.0):
        """Create a spatial grid for efficient neighbor finding."""
        return {}  # Dictionary with (x,y,z) grid coords as key, list of objects as value

    @staticmethod
    def get_grid_coords(location, cell_size=1.0):
        """Get grid coordinates for a location."""
        return (
            int(location.x / cell_size),
            int(location.y / cell_size),
            int(location.z / cell_size)
        )

    @staticmethod
    def add_to_grid(spatial_grid, obj, cell_size=1.0):
        """Add an object to the spatial grid."""
        grid_coords = ZENV_OT_GenerateStoneWall.get_grid_coords(obj.location, cell_size)
        if grid_coords not in spatial_grid:
            spatial_grid[grid_coords] = []
        spatial_grid[grid_coords].append(obj)

    @staticmethod
    def get_nearby_stones(spatial_grid, location, cell_size=1.0):
        """Get stones from neighboring grid cells."""
        grid_coords = ZENV_OT_GenerateStoneWall.get_grid_coords(location, cell_size)
        nearby = []
        
        # Check 27 neighboring cells (3x3x3 grid around point)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    check_coords = (
                        grid_coords[0] + dx,
                        grid_coords[1] + dy,
                        grid_coords[2] + dz
                    )
                    if check_coords in spatial_grid:
                        nearby.extend(spatial_grid[check_coords])
        return nearby

    @staticmethod
    def check_stone_overlap(context, new_stone, spatial_grid, ground_plane, margin=0.1, cell_size=1.0):
        """Check if a stone overlaps with nearby stones using spatial partitioning."""
        # First check against ground plane
        if ground_plane:
            original_z = new_stone.location.z
            new_stone.location.z += 0.001
            try:
                if ZENV_OT_GenerateStoneWall.check_intersection(context, new_stone, ground_plane):
                    return True
            finally:
                new_stone.location.z = original_z

        # Get nearby stones only
        nearby_stones = ZENV_OT_GenerateStoneWall.get_nearby_stones(spatial_grid, new_stone.location, cell_size)

        # Check against nearby stones
        for stone in nearby_stones:
            dx = abs(new_stone.location.x - stone.location.x)
            dy = abs(new_stone.location.y - stone.location.y)
            dz = abs(new_stone.location.z - stone.location.z)

            size_x = (new_stone.dimensions.x + stone.dimensions.x) * 0.5 + margin
            size_y = (new_stone.dimensions.y + stone.dimensions.y) * 0.5 + margin
            size_z = (new_stone.dimensions.z + stone.dimensions.z) * 0.5 + margin

            if dx < size_x and dy < size_y and dz < size_z:
                if ZENV_OT_GenerateStoneWall.check_intersection(context, new_stone, stone):
                    return True
        return False

    @staticmethod
    def create_layer_stones(context, rng, layer_z, wall_width, stone_size_range, count, is_large=True, spatial_grid=None, ground_plane=None, cell_size=1.0):
        """Create stones for one layer using spatial partitioning."""
        stones = []
        attempts = 0
        max_attempts = count * 5
        bounds = (-wall_width * 0.45, wall_width * 0.45)

        if spatial_grid is None:
            spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)

        while len(stones) < count and attempts < max_attempts:
            x = rng.uniform(bounds[0], bounds[1])
            y = rng.uniform(-0.2, 0.2)
            z = layer_z + rng.uniform(-0.1, 0.1)

            # Always treat stone_size_range as a (min, max) tuple
            if isinstance(stone_size_range, (tuple, list)):
                size = rng.uniform(stone_size_range[0], stone_size_range[1])
            else:
                # Scalar - apply small random variation for variety
                size = stone_size_range * rng.uniform(0.85, 1.15)
            stone = ZENV_OT_GenerateStoneWall.create_stone(
                context,
                rng,
                f"{'Large' if is_large else 'Filler'}Stone_{layer_z:.2f}_{len(stones)}",
                (x, y, z),
                size,
                detail=0.2 if is_large else 0.1,
            )

            if not ZENV_OT_GenerateStoneWall.check_stone_overlap(context, stone, spatial_grid, ground_plane, cell_size=cell_size):
                ZENV_OT_GenerateStoneWall.add_rigidbody(context, stone)
                ZENV_OT_GenerateStoneWall.add_to_grid(spatial_grid, stone, cell_size)
                stones.append(stone)
            else:
                bpy.data.objects.remove(stone, do_unlink=True)

            attempts += 1

        if len(stones) < count:
            logger.warning(f"Layer at z={layer_z:.2f}: placed {len(stones)}/{count} stones after {attempts} attempts")

        return stones, spatial_grid

    @staticmethod
    def add_rigidbody(context, stone, body_type='ACTIVE'):
        """Add rigid body physics with proper mesh collision."""
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = stone
        stone.select_set(True)
        
        # Ensure mesh is finalized
        stone.data.validate()
        stone.data.update()
        
        # Add rigid body
        if not stone.rigid_body:
            result = bpy.ops.rigidbody.object_add()
            # bpy.ops.rigidbody.object_add() can return without error
            # {'CANCELLED'} when invoked from the sidebar panel context
            # (no proper 3D viewport region), leaving rigid_body as
            # None.  Catch that here with a clear error instead of the
            # cryptic "'NoneType' object has no attribute 'type'".
            if stone.rigid_body is None:
                raise RuntimeError(
                    f"add_rigidbody: bpy.ops.rigidbody.object_add() failed "
                    f"to create rigid body for '{stone.name}' "
                    f"(result={result}). The operator may have been "
                    f"cancelled due to wrong context."
                )

        stone.rigid_body.type = body_type
        # CONVEX_HULL is the stable choice for active rigid bodies in Bullet.
        # MESH (GImpact) on active bodies causes violent self-resolving
        # intersections when shapes are concave/noisy (bevel+displace+decimate).
        stone.rigid_body.collision_shape = 'CONVEX_HULL'
        stone.rigid_body.mesh_source = 'FINAL'
        stone.rigid_body.use_deform = False

        # Collision settings
        stone.rigid_body.collision_margin = 0.001
        stone.rigid_body.use_margin = True
        stone.rigid_body.friction = 0.8
        stone.rigid_body.restitution = 0.1
        stone.rigid_body.linear_damping = 0.9
        stone.rigid_body.angular_damping = 0.9

        # Set mass from bounding-box volume times a stone density.
        # Real stone ~2700 kg/m^3; using 2000 as a sane default so impulses
        # don't fling light bodies around. Bounding-box volume overestimates
        # true volume, which partially compensates for the convex-hull gap.
        volume = stone.dimensions.x * stone.dimensions.y * stone.dimensions.z
        density = 2000.0 if stone.name.startswith("Large") else 1800.0
        stone.rigid_body.mass = max(volume * density, 0.1)
        
        stone.select_set(False)

    @staticmethod
    def simulate_physics(context, frames, bounds, z_bound=-1.0, clump_frames=30):
        """Run physics simulation with configured settings.

        ``clump_frames`` is the number of frames the inward Harmonic force
        stays active (see create_clump_force).  We always simulate at least
        ``clump_frames + 10`` frames so stones get a gravity-only settling
        tail after the clump force has faded to zero.
        """
        scene = context.scene

        # Ensure scene is in a clean state
        bpy.ops.object.select_all(action='DESELECT')

        # Set up physics scene
        scene.use_gravity = True
        scene.gravity = (0, 0, -9.81)

        if not scene.rigidbody_world:
            bpy.ops.rigidbody.world_add()
        scene.rigidbody_world.enabled = True
        scene.rigidbody_world.substeps_per_frame = 10
        scene.rigidbody_world.solver_iterations = 20

        # Always run past the clump-force fade so gravity settles the
        # stones on its own for at least 10 frames afterwards.
        effective_frames = max(frames, clump_frames + 10)

        # Run simulation in smaller chunks to prevent crashes
        chunk_size = 10
        for i in range(0, effective_frames, chunk_size):
            chunk_end = min(i + chunk_size, effective_frames)
            
            # Update scene to current frame
            scene.frame_set(scene.frame_start + i)
            
            # Step through frames in this chunk
            for frame in range(i, chunk_end):
                scene.frame_set(scene.frame_start + frame)
                
                # Check if any objects are out of bounds and remove them
                # Collect first, then remove - avoids mutation-during-iteration
                to_remove = [
                    obj for obj in bpy.data.objects
                    if obj.rigid_body and obj.type == 'MESH'
                    and (obj.location.x < bounds[0] or
                         obj.location.x > bounds[1] or
                         obj.location.z < z_bound)
                ]
                for obj in to_remove:
                    bpy.data.objects.remove(obj, do_unlink=True)
            
            # Force update of physics
            context.view_layer.update()

    def execute(self, context):
        # Track created objects for cleanup on failure
        created_objects = []
        # Save scene state for restoration
        scene = context.scene
        original_frame = scene.frame_current
        original_gravity = scene.gravity if scene.use_gravity else None
        original_use_gravity = scene.use_gravity

        try:
            props = context.scene.zenv_stone_wall_props

            # Use a local RNG to avoid polluting the global random state
            seed = props.seed if props.seed > 0 else None
            self._rng = random.Random(seed)

            # Clean up stones from a previous run
            old_stones = [obj for obj in bpy.data.objects
                          if obj.name.startswith(("Large", "Filler"))]
            for obj in old_stones:
                bpy.data.objects.remove(obj, do_unlink=True)

            # Create ground first
            ground_plane = ZENV_OT_GenerateStoneWall.create_ground_plane(context, props.wall_width)

            # Create the inward clump force (Harmonic field at origin,
            # strength fades to zero after props.clump_frames).
            clump_force = ZENV_OT_GenerateStoneWall.create_clump_force(
                context, props.clump_strength, props.clump_frames
            )

            # Initialize spatial grid
            cell_size = max(props.stone_size_max, 1.0)
            spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)

            # Generate wall layer by layer
            # Start at stone_size_max/2 so layer 0 stones rest on top of the ground
            layer_height = props.stone_size_max * 1.2
            for layer in range(props.layers):
                layer_z = layer_height * layer + props.stone_size_max * 0.5

                # Create large stones first
                large_stones, spatial_grid = ZENV_OT_GenerateStoneWall.create_layer_stones(
                    context,
                    self._rng,
                    layer_z,
                    props.wall_width,
                    (props.stone_size_min, props.stone_size_max),
                    props.stones_per_layer,
                    True,
                    spatial_grid,
                    ground_plane,
                    cell_size
                )
                created_objects.extend(large_stones)

                # Then create filler stones
                filler_stones, spatial_grid = ZENV_OT_GenerateStoneWall.create_layer_stones(
                    context,
                    self._rng,
                    layer_z,
                    props.wall_width,
                    props.filler_stone_size,
                    props.grid_divisions * 2,
                    False,
                    spatial_grid,
                    ground_plane,
                    cell_size
                )
                created_objects.extend(filler_stones)

                # Run physics simulation for this layer
                ZENV_OT_GenerateStoneWall.simulate_physics(
                    context,
                    props.simulation_frames,
                    (props.wall_bound_min, props.wall_bound_max),
                    props.z_bound_min,
                    clump_frames=props.clump_frames,
                )

                # Update spatial grid after physics
                spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)
                for obj in bpy.data.objects:
                    if obj.name.startswith(("Large", "Filler")):
                        ZENV_OT_GenerateStoneWall.add_to_grid(spatial_grid, obj, cell_size)

            logger.info("Stone wall generation complete")
            return {'FINISHED'}

        except Exception as e:
            logger.error(f"Error generating stone wall: {e}")
            # Clean up partial results on failure
            for obj in created_objects:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
            self.report({'ERROR'}, f"Error generating stone wall: {str(e)}")
            return {'CANCELLED'}
        finally:
            # Restore scene state
            try:
                scene.frame_set(original_frame)
            except Exception:
                pass

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_StoneWallPanel(Panel):
    """Panel for stone wall generation settings."""
    bl_label = "GEN Stone Wall Generator"
    bl_idname = "ZENV_PT_StoneWallPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ZENV"

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_stone_wall_props

        col = layout.column(align=True)
        col.prop(props, "wall_width")
        col.prop(props, "layers")
        col.prop(props, "stones_per_layer")
        
        box = layout.box()
        box.label(text="Stone Sizes")
        col = box.column(align=True)
        col.prop(props, "stone_size_min")
        col.prop(props, "stone_size_max")
        col.prop(props, "filler_stone_size")
        
        box = layout.box()
        box.label(text="Generation Settings")
        col = box.column(align=True)
        col.prop(props, "grid_divisions")
        col.prop(props, "simulation_frames")
        col.prop(props, "wall_bound_min")
        col.prop(props, "wall_bound_max")
        col.prop(props, "z_bound_min")
        col.prop(props, "seed")

        box = layout.box()
        box.label(text="Clump Force (Inward)")
        col = box.column(align=True)
        col.prop(props, "clump_strength")
        col.prop(props, "clump_frames")
        
        layout.operator("zenv.generate_stone_wall")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_StoneWallProperties,
    ZENV_OT_GenerateStoneWall,
    ZENV_PT_StoneWallPanel
)

def register():
    # Double-registration guard
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    if not hasattr(bpy.types.Scene, 'zenv_stone_wall_props'):
        bpy.types.Scene.zenv_stone_wall_props = PointerProperty(type=ZENV_PG_StoneWallProperties)

def unregister():
    # Unregister classes before deleting properties
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, 'zenv_stone_wall_props'):
        del bpy.types.Scene.zenv_stone_wall_props
    _uninstall_logger()

if __name__ == "__main__":
    register()
