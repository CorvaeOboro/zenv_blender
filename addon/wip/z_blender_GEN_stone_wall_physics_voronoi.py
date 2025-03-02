"""
GEN Stone Wall Physics Voronoi
- A Blender addon for generating layered stone walls using physics simulation and voronoi-like subdivision.
Creates realistic stone walls with large stones and filler stones, using physics for natural settling.
"""

bl_info = {
    "name": "GEN Stone Wall Physics Voronoi",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Generate layered stone walls using physics and voronoi subdivision",
    "category": "ZENV",
}

import bpy
import bmesh
import random
import math
import mathutils
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, IntProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_StoneWall_Properties(PropertyGroup):
    """Properties for stone wall generation."""
    
    wall_width: FloatProperty(
        name="Wall Width",
        default=10.0,
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
        description="Minimum size of large stones"
    )
    
    stone_size_max: FloatProperty(
        name="Stone Size Max",
        default=2.0,
        description="Maximum size of large stones"
    )
    
    filler_stone_size: FloatProperty(
        name="Filler Stone Size",
        default=0.5,
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
        description="Minimum X-value for a stone to remain in the wall"
    )
    
    wall_bound_max: FloatProperty(
        name="Wall Bound Max",
        default=5.0,
        description="Maximum X-value for a stone to remain in the wall"
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_GenerateStoneWall(Operator):
    """Generate a stacked stone wall using physics and voronoi-like filler placement."""
    bl_idname = "zenv.generate_stone_wall"
    bl_label = "Generate Stone Wall"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def create_stone(name, location, size, detail=0.2, is_large=True):
        """Create a rectangular stone mesh with proper detailing."""
        # Create mesh data first
        mesh = bpy.data.meshes.new(name=f"{name}_mesh")
        stone = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(stone)
        
        # Create base cube vertices
        stretch_x = random.uniform(1.2, 1.5)
        stretch_y = random.uniform(0.6, 0.8)
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
        
        # Make active and select
        bpy.context.view_layer.objects.active = stone
        stone.select_set(True)
        
        # Add slight random rotation (less on X and Y to keep stones more level)
        stone.rotation_euler = (
            random.uniform(-0.1, 0.1),
            random.uniform(-0.1, 0.1),
            random.uniform(-0.3, 0.3)
        )
        
        # Apply rotation
        bpy.ops.object.transform_apply(rotation=True)
        
        # Switch to edit mode for modifications
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Add bevel (2cm)
        bpy.ops.mesh.bevel(
            offset=0.02,
            offset_type='WIDTH',
            segments=3,
            profile=0.7
        )
        
        # Subdivide for detail
        bpy.ops.mesh.subdivide(number_cuts=1)
        
        # Add subtle random displacement
        bpy.ops.transform.vertex_random(
            offset=detail * 0.15,
            uniform=0.1,
            normal=0.0,
            seed=random.randint(0, 1000)
        )
        
        # Add 3D noise displacement
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create noise texture for displacement
        noise_tex = bpy.data.textures.new(name=f"{name}_noise", type='NOISE')
        
        # Add displacement modifier
        displace = stone.modifiers.new(name="Displacement", type='DISPLACE')
        displace.texture = noise_tex
        displace.texture_coords = 'GLOBAL'
        displace.direction = 'NORMAL'
        displace.space = 'LOCAL'
        displace.strength = 0.005
        displace.mid_level = 0.5
        
        # Apply displacement
        bpy.ops.object.modifier_apply(modifier="Displacement")
        
        # Clean up texture
        bpy.data.textures.remove(noise_tex)
        
        # Reduce polygons
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.decimate(ratio=0.5)
        
        # Remove doubles and clean up mesh
        bpy.ops.mesh.remove_doubles(threshold=0.001)
        bpy.ops.mesh.delete_loose()
        
        # Back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Add smooth shading
        bpy.ops.object.shade_smooth()
        
        # Ensure clean normals
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return stone

    @staticmethod
    def create_bvh_tree(obj):
        """Create a BVHTree from an object for precise collision detection."""
        # Get the mesh data in world space
        dg = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(dg)
        mesh = obj_eval.to_mesh()
        mesh.transform(obj.matrix_world)
        
        # Create BVHTree
        bvh = BVHTree.FromPolygons(
            [v.co for v in mesh.vertices],
            [(p.vertices[0], p.vertices[1], p.vertices[2]) for p in mesh.polygons],
            epsilon=0.0001
        )
        obj_eval.to_mesh_clear()
        return bvh

    @staticmethod
    def check_intersection(obj1, obj2):
        """Check if two objects intersect using precise BVHTree intersection."""
        # Create BVH trees for both objects
        bvh1 = ZENV_OT_GenerateStoneWall.create_bvh_tree(obj1)
        bvh2 = ZENV_OT_GenerateStoneWall.create_bvh_tree(obj2)
        
        # Find intersections
        intersect = bvh1.overlap(bvh2)
        return bool(intersect)

    @staticmethod
    def create_ground_plane():
        """Create a volumetric ground plane for proper collision detection."""
        if not any(obj.name.startswith("Ground") for obj in bpy.data.objects):
            # Create ground plane
            bpy.ops.mesh.primitive_plane_add(size=50)
            ground = bpy.context.active_object
            ground.name = "Ground_Plane"
            
            # Convert to mesh for editing
            bpy.context.view_layer.objects.active = ground
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Extrude down to create volume
            bpy.ops.mesh.extrude_region_move()
            bpy.ops.transform.translate(value=(0, 0, -1))
            
            # Back to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Add rigid body settings
            bpy.ops.rigidbody.object_add()
            ground.rigid_body.type = 'PASSIVE'
            ground.rigid_body.collision_shape = 'MESH'
            ground.rigid_body.friction = 1.0
            ground.rigid_body.restitution = 0.0
            ground.rigid_body.use_margin = True
            ground.rigid_body.collision_margin = 0.0001
            
            return ground
        return next(obj for obj in bpy.data.objects if obj.name.startswith("Ground"))

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
    def check_stone_overlap(new_stone, spatial_grid, ground_plane, margin=0.1, cell_size=1.0):
        """Check if a stone overlaps with nearby stones using spatial partitioning."""
        # First check against ground plane
        if ground_plane:
            original_z = new_stone.location.z
            new_stone.location.z += 0.001
            if ZENV_OT_GenerateStoneWall.check_intersection(new_stone, ground_plane):
                new_stone.location.z = original_z
                return True
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
                if ZENV_OT_GenerateStoneWall.check_intersection(new_stone, stone):
                    return True
        return False

    @staticmethod
    def create_layer_stones(layer_z, wall_width, stone_size_range, count, is_large=True, spatial_grid=None, ground_plane=None, cell_size=1.0):
        """Create stones for one layer using spatial partitioning."""
        stones = []
        attempts = 0
        max_attempts = count * 5
        bounds = (-wall_width * 0.45, wall_width * 0.45)
        
        if spatial_grid is None:
            spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)
        
        while len(stones) < count and attempts < max_attempts:
            x = random.uniform(bounds[0], bounds[1])
            y = random.uniform(-0.2, 0.2)
            z = layer_z + random.uniform(-0.1, 0.1)
            
            size = random.uniform(*stone_size_range) if is_large else stone_size_range
            stone = ZENV_OT_GenerateStoneWall.create_stone(
                f"{'Large' if is_large else 'Filler'}Stone_{layer_z:.2f}_{len(stones)}",
                (x, y, z),
                size,
                detail=0.2 if is_large else 0.1,
                is_large=is_large
            )
            
            if not ZENV_OT_GenerateStoneWall.check_stone_overlap(stone, spatial_grid, ground_plane, cell_size=cell_size):
                ZENV_OT_GenerateStoneWall.add_rigidbody(stone)
                ZENV_OT_GenerateStoneWall.add_to_grid(spatial_grid, stone, cell_size)
                stones.append(stone)
            else:
                bpy.data.objects.remove(stone, do_unlink=True)
            
            attempts += 1
        
        return stones, spatial_grid

    @staticmethod
    def add_rigidbody(stone, body_type='ACTIVE'):
        """Add rigid body physics with proper mesh collision."""
        bpy.context.view_layer.objects.active = stone
        stone.select_set(True)
        
        # Ensure mesh is finalized
        stone.data.validate()
        stone.data.update()
        
        # Add rigid body
        if not stone.rigid_body:
            bpy.ops.rigidbody.object_add()
        
        stone.rigid_body.type = body_type
        stone.rigid_body.collision_shape = 'MESH'
        stone.rigid_body.mesh_source = 'FINAL'
        stone.rigid_body.use_deform = False
        
        # Collision settings
        stone.rigid_body.collision_margin = 0.001
        stone.rigid_body.use_margin = True
        stone.rigid_body.friction = 0.8
        stone.rigid_body.restitution = 0.1
        stone.rigid_body.linear_damping = 0.9
        stone.rigid_body.angular_damping = 0.9
        
        # Set mass based on volume
        volume = stone.dimensions.x * stone.dimensions.y * stone.dimensions.z
        stone.rigid_body.mass = volume * (2.0 if stone.name.startswith("Large") else 1.5)
        
        stone.select_set(False)

    @staticmethod
    def simulate_physics(frames, bounds):
        """Run physics simulation with improved settings."""
        scene = bpy.context.scene
        
        # Ensure scene is in a clean state
        bpy.ops.object.select_all(action='DESELECT')
        
        # Set up physics scene
        scene.use_gravity = True
        scene.gravity = (0, 0, -9.81)
        
        if not scene.rigidbody_world:
            bpy.ops.rigidbody.world_add()
        scene.rigidbody_world.enabled = True
        scene.rigidbody_world.substeps_per_frame = 10
        scene.rigidbody_world.solver_iterations = 100
        
        # Run simulation in smaller chunks to prevent crashes
        chunk_size = 10
        for i in range(0, frames, chunk_size):
            chunk_end = min(i + chunk_size, frames)
            
            # Update scene to current frame
            scene.frame_set(scene.frame_start + i)
            
            # Step through frames in this chunk
            for frame in range(i, chunk_end):
                scene.frame_set(scene.frame_start + frame)
                
                # Check if any objects are out of bounds and remove them
                for obj in bpy.data.objects:
                    if obj.rigid_body and obj.type == 'MESH':
                        if (obj.location.x < bounds[0] or 
                            obj.location.x > bounds[1] or 
                            obj.location.z < -1):
                            bpy.data.objects.remove(obj, do_unlink=True)
            
            # Force update of physics
            bpy.context.view_layer.update()

    def execute(self, context):
        try:
            props = context.scene.zenv_stone_wall_props
            
            # Create ground first
            ground_plane = ZENV_OT_GenerateStoneWall.create_ground_plane()
            
            # Initialize spatial grid
            cell_size = max(props.stone_size_max, 1.0)
            spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)
            
            # Generate wall layer by layer
            layer_height = props.stone_size_max * 1.2
            for layer in range(props.layers):
                layer_z = layer_height * layer
                
                # Create large stones first
                large_stones, spatial_grid = ZENV_OT_GenerateStoneWall.create_layer_stones(
                    layer_z,
                    props.wall_width,
                    (props.stone_size_min, props.stone_size_max),
                    props.stones_per_layer,
                    True,
                    spatial_grid,
                    ground_plane,
                    cell_size
                )
                
                # Then create filler stones
                filler_stones, spatial_grid = ZENV_OT_GenerateStoneWall.create_layer_stones(
                    layer_z,
                    props.wall_width,
                    props.filler_stone_size,
                    props.grid_divisions * 2,
                    False,
                    spatial_grid,
                    ground_plane,
                    cell_size
                )
                
                # Run physics simulation for this layer
                ZENV_OT_GenerateStoneWall.simulate_physics(props.simulation_frames, (props.wall_bound_min, props.wall_bound_max))
                
                # Update spatial grid after physics
                spatial_grid = ZENV_OT_GenerateStoneWall.create_spatial_grid(cell_size)
                for obj in bpy.data.objects:
                    if obj.name.startswith(("Large", "Filler")):
                        ZENV_OT_GenerateStoneWall.add_to_grid(spatial_grid, obj, cell_size)
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error generating stone wall: {str(e)}")
            return {'CANCELLED'}

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
        
        layout.operator("zenv.generate_stone_wall")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_StoneWall_Properties,
    ZENV_OT_GenerateStoneWall,
    ZENV_PT_StoneWallPanel
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_stone_wall_props = PointerProperty(type=ZENV_PG_StoneWall_Properties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_stone_wall_props

if __name__ == "__main__":
    register()
