"""
MEDIEVAL STONE BLOCK GENERATOR
Generates weathered stone blocks with realistic damage, wear patterns, and battle damage
"""

bl_info = {
    "name": 'GEN Medieval Stone',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Medieval Stone Block Generator with Wear and Damage',
    "status": 'wip',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "location": 'View3D > Sidebar > ZENV > GEN Medieval Stone',
}

import bpy
import bmesh
import random
import math
import datetime
from mathutils import Vector, Matrix, noise, Euler, bvhtree
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty, FloatVectorProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_GenerateStoneBlock_Properties(PropertyGroup):
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
        default=2,
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
        default=3,
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
        description="Chance of damage per corner (0-1)",
        default=0.6,
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
        default=2,
        min=1,
        max=4
    )
    
    # Surface detail properties
    surface_detail: FloatProperty(
        name="Surface Detail",
        description="Amount of surface detail",
        default=1.0,
        min=0.1,
        max=2.0
    )
    erosion_scale: FloatProperty(
        name="Erosion Scale",
        description="Scale of erosion patterns",
        default=0.5,
        min=0.1,
        max=2.0
    )
    
    # Additional effects
    enable_fracture: BoolProperty(
        name="Fracture Pattern",
        description="Add fracture patterns to the stone",
        default=True
    )
    enable_sharpening: BoolProperty(
        name="Edge Sharpening",
        description="Apply edge sharpening effect",
        default=True
    )
    fracture_scale: FloatProperty(
        name="Fracture Scale",
        description="Scale of fracture patterns",
        default=1.0,
        min=0.1,
        max=3.0
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

    def draw_debug_layout(self, layout):
        """Draw debug mode UI elements"""
        box = layout.box()
        box.label(text="Debug Options:")
        row = box.row()
        row.prop(self, "debug_mode")
        row.prop(self, "complete_mesh")

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_GenerateStoneBlock(Operator):
    """Create a new medieval stone block"""
    bl_idname = "object.zenv_generate_stone_block"
    bl_label = "Generate Stone Block"
    bl_options = {'REGISTER', 'UNDO'}

    def create_base_block(self, props):
        """Create the base stone block"""
        # Create base cube
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            enter_editmode=False,
            align='WORLD'
        )
        block = bpy.context.active_object
        block.scale = Vector((props.width, props.depth, props.height))
        block.name = "Medieval_Stone"
        
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
        """Apply voxel remesh with optimized settings"""
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

    def apply_noise_displacement(self, obj, noise_scale=1.0, strength=1.0, detail=5):
        """Apply Python-based 3D noise displacement"""
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
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

    def generate_branching_crack(self, start_point, direction, length, depth, branches=3):
        """Generate a detailed branching crack"""
        bm = bmesh.new()
        
        # Parameters for crack detail
        segments = int(length * 20)  # More segments for higher detail
        width_start = length * 0.08  # Base width of crack
        depth_start = depth * 0.6  # Base depth
        
        def create_crack_segment(start, direction, length, width, depth, detail_level=1):
            """Create a detailed crack segment with surface variation"""
            # Calculate end point with natural curve
            curve_strength = random.uniform(0.1, 0.3) * length
            side_vec = direction.cross(Vector((0, 0, 1))).normalized()
            curve_offset = side_vec * math.sin(random.uniform(0, math.pi)) * curve_strength
            
            # Add noise to direction
            noise_scale = 0.3 * detail_level
            noise_vec = Vector((
                random.uniform(-noise_scale, noise_scale),
                random.uniform(-noise_scale, noise_scale),
                random.uniform(-noise_scale, noise_scale)
            ))
            end_point = start + direction * length + curve_offset + noise_vec
            
            # Create base vertices for the segment
            points = []
            num_sides = 6  # Hexagonal profile for better detail
            
            # Create profile points
            for i in range(num_sides):
                angle = (i / num_sides) * 2 * math.pi
                # Vary the radius slightly for each point
                radius = width * (0.8 + random.uniform(0, 0.4))
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
                bm.faces.new((start_verts[i], start_verts[i2], 
                            end_verts[i2], end_verts[i]))
            
            # Add interior detail
            center_start = bm.verts.new(start + Vector((0, 0, -depth * 1.2)))
            center_end = bm.verts.new(end_point + Vector((0, 0, -depth * 0.8)))
            
            for i in range(num_sides):
                i2 = (i + 1) % num_sides
                bm.faces.new((start_verts[i], start_verts[i2], center_start))
                bm.faces.new((end_verts[i], end_verts[i2], center_end))
            
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
            if random.random() < 0.3:  # 30% chance of branch
                # Calculate branch direction
                main_dir = (main_points[i+2] - main_points[i]).normalized()
                branch_dir = main_dir.cross(Vector((0, 0, 1)))
                if random.random() < 0.5:
                    branch_dir = -branch_dir
                
                # Rotate branch direction randomly
                angle = random.uniform(math.pi/6, math.pi/3)  # 30-60 degrees
                rot_mat = Matrix.Rotation(angle, 3, main_dir)
                branch_dir = rot_mat @ branch_dir
                
                # Create branch with reduced parameters
                branch_length = length * random.uniform(0.3, 0.5)
                branch_width = width_start * 0.6
                branch_depth = depth_start * 0.7
                
                create_crack_segment(point, branch_dir, branch_length, 
                                  branch_width, branch_depth, detail_level=0.7)
        
        # Add final surface detail
        bmesh.ops.subdivide_edges(bm,
            edges=bm.edges[:],
            cuts=1)
        
        for v in bm.verts:
            if not v.is_boundary:
                noise_val = noise.noise((v.co * 20.0).to_tuple()) * width_start * 0.3
                v.co += v.normal * noise_val
        
        return bm

    def apply_damage(self, obj, props):
        """Apply damage to the object"""
        # Create collection for damage objects if it doesn't exist
        damage_collection = bpy.data.collections.get("Damage_Objects")
        if not damage_collection:
            damage_collection = bpy.data.collections.new("Damage_Objects")
            bpy.context.scene.collection.children.link(damage_collection)
        
        # Debug collection for visualization
        debug_collection = None
        if props.debug_mode:
            debug_collection = bpy.data.collections.get("Debug_Damage")
            if not debug_collection:
                debug_collection = bpy.data.collections.new("Debug_Damage")
                bpy.context.scene.collection.children.link(debug_collection)
        
        # Apply sword damage
        if props.enable_sword_damage:
            sword_damages = []
            for i in range(props.sword_damage_count):
                # Create damage object
                size = random.uniform(props.width * 0.2, props.width * 0.3)
                damage_obj = self.create_sword_damage(size)
                
                # Random position on surface
                pos = self.get_random_surface_point(obj)
                damage_obj.location = pos
                
                # Random rotation
                damage_obj.rotation_euler = (
                    random.uniform(-math.pi/4, math.pi/4),
                    random.uniform(-math.pi/4, math.pi/4),
                    random.uniform(0, 2*math.pi)
                )
                
                # Project to surface
                self.project_to_surface(damage_obj, obj)
                
                # Debug visualization
                if props.debug_mode:
                    debug_obj = damage_obj.copy()
                    debug_obj.data = damage_obj.data.copy()
                    debug_obj.location.x += 3  # Offset to the right
                    debug_collection.objects.link(debug_obj)
                    self.create_debug_text(f"Sword Cut {i+1}", debug_obj.location + Vector((0, 0.5, 0)))
                
                # Add boolean modifier
                bool_mod = obj.modifiers.new(name=f"Sword_{i}", type='BOOLEAN')
                bool_mod.object = damage_obj
                bool_mod.operation = 'DIFFERENCE'
                bool_mod.solver = 'EXACT'
                
                # Hide damage object
                damage_obj.hide_viewport = True
                sword_damages.append(damage_obj)
                
                # Add to collection
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)
                if damage_obj.name in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.unlink(damage_obj)
        
        # Apply impact damage
        if props.enable_impact_damage:
            impact_damages = []
            for i in range(props.impact_damage_count):
                # Create damage object
                size = random.uniform(props.width * 0.1, props.width * 0.2)
                damage_obj = self.create_impact_damage(size)
                
                # Random position on surface
                pos = self.get_random_surface_point(obj)
                damage_obj.location = pos
                
                # Random rotation
                damage_obj.rotation_euler = (
                    random.uniform(0, 2*math.pi),
                    random.uniform(0, 2*math.pi),
                    random.uniform(0, 2*math.pi)
                )
                
                # Project to surface
                self.project_to_surface(damage_obj, obj)
                
                # Debug visualization
                if props.debug_mode:
                    debug_obj = damage_obj.copy()
                    debug_obj.data = damage_obj.data.copy()
                    debug_obj.location.x += 6  # Offset further right
                    debug_collection.objects.link(debug_obj)
                    self.create_debug_text(f"Impact {i+1}", debug_obj.location + Vector((0, 0.5, 0)))
                
                # Add boolean modifier
                bool_mod = obj.modifiers.new(name=f"Impact_{i}", type='BOOLEAN')
                bool_mod.object = damage_obj
                bool_mod.operation = 'DIFFERENCE'
                bool_mod.solver = 'EXACT'
                
                # Hide damage object
                damage_obj.hide_viewport = True
                impact_damages.append(damage_obj)
                
                # Add to collection
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)
                if damage_obj.name in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.unlink(damage_obj)
        
        # Apply remesh after all damage
        self.apply_voxel_remesh(obj, 0.035)

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
        voxel.voxel_size = size * 0.02
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
        voxel.voxel_size = size * 0.015  # Finer detail
        voxel.use_smooth_shade = True
        
        # Apply final remesh
        obj_eval = remesh1_obj.evaluated_get(depsgraph)
        final_mesh = bpy.data.meshes.new_from_object(obj_eval)
        final_mesh.name = "Impact_Final"
        steps.append((final_mesh, "5. Final Clean Mesh"))
        
        # Cleanup temporary object
        bpy.context.scene.collection.objects.unlink(remesh1_obj)
        bpy.data.objects.remove(remesh1_obj)
        
        # Create debug visualization
        debug_collection, debug_objects = self.create_debug_visualization(
            "Sword",
            steps,
            Vector((3, 0, 0)),  # Base location
            "Debug_Sword_Steps"
        )
        
        # Return final object and cleanup others
        final_obj = debug_objects[-2] if debug_objects else None  # Last mesh object
        
        if not debug_collection:
            # Cleanup if not in debug mode
            for mesh, _ in steps[:-1]:  # Keep final mesh
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        
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
        voxel.voxel_size = size * 0.02
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
        voxel.voxel_size = size * 0.015
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
            v.co += v.normal * abs(noise_val) * size * 0.01  # Very subtle
        
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
        
        # Create mesh and object
        mesh = bpy.data.meshes.new("Corner_Damage")
        bm.to_mesh(mesh)
        bm.free()
        
        obj = bpy.data.objects.new("Corner_Damage", mesh)
        
        # Add voxel remesh with larger voxels
        voxel = obj.modifiers.new(name="VoxelRemesh", type='REMESH')
        voxel.mode = 'VOXEL'
        voxel.voxel_size = size * 0.03  # Increased voxel size
        voxel.use_smooth_shade = True
        
        # Apply modifier
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = bpy.data.meshes.new_from_object(obj_eval)
        obj.data = mesh_eval
        obj.modifiers.clear()
        
        return obj

    def create_damage_object(self, damage_type, size):
        """Create damage object based on type"""
        if damage_type == 'SWORD':
            return self.create_sword_damage(size)
        elif damage_type == 'IMPACT':
            return self.create_impact_damage(size)
        else:  # CORNER
            return self.create_corner_damage(size)

    def apply_sharpening(self, obj, intensity=0.5, angle_threshold=30):
        """Apply a sharpening effect to enhance edges and surface details
        
        Args:
            obj: The object to sharpen
            intensity: How strong the sharpening effect should be (0.0-1.0)
            angle_threshold: Angle in degrees above which edges are considered sharp
        """
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        
        # Calculate vertex normals
        bm.normal_update()
        
        # Store original positions
        orig_positions = {v: v.co.copy() for v in bm.verts}
        
        # First pass: identify sharp edges and features
        sharp_verts = set()
        for edge in bm.edges:
            # Calculate angle between connected faces
            if len(edge.link_faces) == 2:
                angle = math.degrees(edge.calc_face_angle())
                if angle > angle_threshold:
                    sharp_verts.add(edge.verts[0])
                    sharp_verts.add(edge.verts[1])
        
        # Second pass: enhance sharp features
        for vert in bm.verts:
            if vert in sharp_verts:
                # Calculate average direction of sharp edges
                sharp_dir = Vector((0, 0, 0))
                edge_count = 0
                
                for edge in vert.link_edges:
                    if edge.other_vert(vert) in sharp_verts:
                        edge_vec = (edge.other_vert(vert).co - vert.co).normalized()
                        sharp_dir += edge_vec
                        edge_count += 1
                
                if edge_count > 0:
                    sharp_dir = sharp_dir.normalized()
                    
                    # Calculate displacement based on surrounding geometry
                    displacement = Vector((0, 0, 0))
                    for edge in vert.link_edges:
                        other = edge.other_vert(vert)
                        edge_vec = (other.co - vert.co)
                        edge_len = edge_vec.length
                        edge_vec.normalize()
                        
                        # Add displacement away from neighboring vertices
                        displacement -= edge_vec * (edge_len * 0.1)
                    
                    # Apply displacement along sharp direction
                    if displacement.length > 0:
                        displacement = displacement.project(sharp_dir)
                        vert.co += displacement * intensity
            
            # For non-sharp vertices, enhance surface detail
            else:
                # Calculate local curvature
                neighbor_normals = [f.normal for f in vert.link_faces]
                if neighbor_normals:
                    avg_normal = sum(neighbor_normals, Vector((0, 0, 0))).normalized()
                    curvature = sum((n - avg_normal).length for n in neighbor_normals)
                    
                    # Enhance areas of high curvature
                    if curvature > 0.1:
                        displacement = avg_normal * (curvature * 0.05 * intensity)
                        vert.co += displacement
        
        # Smooth transitions between sharp and non-sharp areas
        for vert in bm.verts:
            if vert in sharp_verts:
                smooth_co = Vector((0, 0, 0))
                weight_sum = 0
                
                for edge in vert.link_edges:
                    other = edge.other_vert(vert)
                    weight = 1.0 / (1.0 + (vert.co - other.co).length)
                    smooth_co += other.co * weight
                    weight_sum += weight
                
                if weight_sum > 0:
                    smooth_co /= weight_sum
                    # Blend between sharpened and smoothed position
                    blend_factor = 0.3  # 30% smoothing
                    vert.co = vert.co.lerp(smooth_co, blend_factor)
        
        # Update the mesh
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

    def project_to_surface(self, obj, target):
        """Project object vertices onto target surface using BVH tree"""
        # Create BVH tree for target
        depsgraph = bpy.context.evaluated_depsgraph_get()
        target_eval = target.evaluated_get(depsgraph)
        
        # Create BVH tree from evaluated object
        bvh = bvhtree.BVHTree.FromObject(target_eval, depsgraph, epsilon=0.00001)
        
        # Project vertices
        for v in obj.data.vertices:
            world_pos = obj.matrix_world @ v.co
            
            # Convert normal to world space and negate
            normal_world = (obj.matrix_world.to_3x3() @ v.normal).normalized()
            direction = -normal_world
            
            # Raycast from slightly above surface
            hit, loc, norm, _ = bvh.ray_cast(world_pos + direction * 0.1, direction)
            if hit:
                # Move vertex to hit location
                v.co = obj.matrix_world.inverted() @ loc

    def apply_cracks(self, obj, props):
        """Apply crack damage to the object"""
        # Get object's corners
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        corners = []
        for v in bm.verts:
            if len(v.link_edges) >= 3:  # Corner vertex
                corners.append(v.co.copy())
        bm.free()
        
        # Create collection for crack objects if it doesn't exist
        crack_collection = bpy.data.collections.get("Crack_Objects")
        if not crack_collection:
            crack_collection = bpy.data.collections.new("Crack_Objects")
            bpy.context.scene.collection.children.link(crack_collection)
        
        # Parameters for crack generation
        base_length = min(props.width, props.height, props.depth) * 0.4
        base_depth = min(props.width, props.height, props.depth) * 0.05
        
        # Create cracks at corners and random points
        num_cracks = props.crack_count  # Use property value
        for i in range(num_cracks):
            # Choose start position
            if random.random() < 0.7 and corners:  # 70% chance to start from corner
                start_pos = random.choice(corners)
            else:
                # Random position on surface
                start_pos = obj.location + Vector((
                    random.uniform(-props.width/2, props.width/2),
                    random.uniform(-props.depth/2, props.depth/2),
                    random.uniform(-props.height/2, props.height/2)
                ))
            
            # Calculate initial direction
            direction = Vector((
                random.uniform(-1, 1),
                random.uniform(-1, 1),
                random.uniform(-1, 1)
            )).normalized()
            
            # Vary crack parameters
            length = base_length * random.uniform(0.5, 1.2)
            depth = base_depth * random.uniform(0.8, 1.2)
            num_branches = random.randint(2, 4)
            
            # Generate crack mesh
            crack_bm = self.generate_branching_crack(
                start_pos, direction, length, depth, num_branches)
            
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
            
            # Add boolean modifier
            bool_mod = obj.modifiers.new(name=f"Crack_{i}", type='BOOLEAN')
            bool_mod.object = crack_obj
            bool_mod.operation = 'DIFFERENCE'
            bool_mod.solver = 'EXACT'
            
            # Hide crack object
            crack_obj.hide_viewport = True
            
            # Add solidify modifier to crack object for better boolean
            solid_mod = crack_obj.modifiers.new(name="Solidify", type='SOLIDIFY')
            solid_mod.thickness = 0.001
            solid_mod.offset = 0.0
            
            # Add bevel modifier for smoother edges
            bevel_mod = crack_obj.modifiers.new(name="Bevel", type='BEVEL')
            bevel_mod.width = 0.001
            bevel_mod.segments = 2
            
            # Add to cleanup collection
            if crack_obj.name not in crack_collection.objects:
                crack_collection.objects.link(crack_obj)
            if crack_obj.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(crack_obj)

    def apply_corner_damage(self, obj, props):
        """Apply damage to corners"""
        # Create collection for damage objects if it doesn't exist
        damage_collection = bpy.data.collections.get("Damage_Objects")
        if not damage_collection:
            damage_collection = bpy.data.collections.new("Damage_Objects")
            bpy.context.scene.collection.children.link(damage_collection)
        
        # Get corners from bound box
        corners = obj.bound_box
        
        # Apply damage to each corner
        for i, corner in enumerate(corners):
            if random.random() < props.corner_damage_chance:  # Use property value
                # Create smaller damage for corners
                size = random.uniform(props.width * 0.1, props.width * 0.15)  # Reduced size range
                damage_obj = self.create_damage_object('CORNER', size)
                
                # Position at corner with slight offset
                offset = Vector((
                    random.uniform(-0.05, 0.05),
                    random.uniform(-0.05, 0.05),
                    random.uniform(-0.05, 0.05)
                )) * size
                damage_obj.location = obj.matrix_world @ Vector(corner) + offset
                
                # Random rotation with more variation
                damage_obj.rotation_euler = (
                    random.uniform(-math.pi/2, math.pi/2),
                    random.uniform(-math.pi/2, math.pi/2),
                    random.uniform(0, 2*math.pi)
                )
                
                # Project to surface
                self.project_to_surface(damage_obj, obj)
                
                # Add boolean modifier
                bool_mod = obj.modifiers.new(name=f"Corner_{i}", type='BOOLEAN')
                bool_mod.object = damage_obj
                bool_mod.operation = 'DIFFERENCE'
                bool_mod.solver = 'EXACT'
                
                # Hide damage object
                damage_obj.hide_viewport = True
                
                # Add to collection
                if damage_obj.name not in damage_collection.objects:
                    damage_collection.objects.link(damage_obj)
                if damage_obj.name in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.unlink(damage_obj)

    def create_debug_text(self, text, location):
        """Create 3D text for debug visualization"""
        bpy.ops.object.text_add(location=location)
        text_obj = bpy.context.active_object
        text_obj.data.body = text
        text_obj.data.size = 0.2
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

    def cleanup_temp_objects(self, context):
        """Remove all temporary objects and collections used in generation"""
        # Clean up damage objects
        damage_collection = bpy.data.collections.get("Damage_Objects")
        if damage_collection:
            # First unlink all objects from the collection
            for obj in damage_collection.objects[:]:  # Use slice to avoid modification during iteration
                # Unlink from all collections first
                for coll in obj.users_collection:
                    coll.objects.unlink(obj)
                # Then delete the object and its data
                if obj.data:
                    bpy.data.meshes.remove(obj.data)
                bpy.data.objects.remove(obj)
            # Remove the collection
            bpy.data.collections.remove(damage_collection)
        
        # Clean up crack objects
        crack_collection = bpy.data.collections.get("Crack_Objects")
        if crack_collection:
            # First unlink all objects from the collection
            for obj in crack_collection.objects[:]:  # Use slice to avoid modification during iteration
                # Unlink from all collections first
                for coll in obj.users_collection:
                    coll.objects.unlink(obj)
                # Then delete the object and its data
                if obj.data:
                    bpy.data.meshes.remove(obj.data)
                bpy.data.objects.remove(obj)
            # Remove the collection
            bpy.data.collections.remove(crack_collection)

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
            except Exception as e:
                print(f"Failed to apply modifier {modifier.name}: {str(e)}")
                continue
        
        # Restore previous active object and mode
        obj.select_set(False)
        context.view_layer.objects.active = current_active
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=current_mode)

    def get_random_surface_point(self, obj):
        """Get a random point on the object's surface using BVH tree"""
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
                random.uniform(min_bound.x, max_bound.x),
                random.uniform(min_bound.y, max_bound.y),
                random.uniform(min_bound.z, max_bound.z)
            ))
            
            # Find nearest point on surface
            location, normal, index, distance = bvh.find_nearest(rand_point)
            
            if location:
                # Convert to world space
                return obj.matrix_world @ location
        
        # Fallback to a point on a random face
        if mesh.polygons:
            face = random.choice(mesh.polygons)
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
        """Execute the stone block generation"""
        props = context.scene.zenv_stone_block_generator
        
        # Create base block
        block = self.create_base_block(props)
        if props.debug_mode:
            self.create_debug_copy(block, (-3, 0, 0), "Base Block")
        
        # Add initial bevel for base shape
        self.add_bevel(block, props)
        
        # First voxel remesh for base detail
        self.apply_voxel_remesh(block, 0.04)
        if props.debug_mode:
            self.create_debug_copy(block, (-3, -3, 0), "After Initial Remesh")
        
        # Apply damage if enabled
        if props.enable_sword_damage or props.enable_impact_damage:
            self.apply_damage(block, props)
            if props.debug_mode:
                self.create_debug_copy(block, (-3, -6, 0), "After Damage")
        
        # Apply cracks if enabled
        if props.enable_cracks:
            self.apply_cracks(block, props)
            if props.debug_mode:
                self.create_debug_copy(block, (-3, -9, 0), "After Cracks")
        
        # Apply corner damage if enabled
        if props.enable_corner_damage:
            self.apply_corner_damage(block, props)
            if props.debug_mode:
                self.create_debug_copy(block, (-3, -12, 0), "After Corner Damage")
        
        # Apply surface noise
        self.apply_noise_displacement(block,
                                   noise_scale=0.7,
                                   strength=0.015,
                                   detail=3)
        
        if props.debug_mode:
            self.create_debug_copy(block, (-3, -15, 0), "Final Result")
        
        # If complete mesh option is enabled and not in debug mode
        if props.complete_mesh and not props.debug_mode:
            self.apply_all_modifiers(block)
            self.cleanup_temp_objects(context)
            
            # Add timestamp to object name
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            block.name = f"Stone_Block_{timestamp}"
            if block.data:
                block.data.name = block.name
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_GenerateStoneBlock_Panel(Panel):
    """Panel for Medieval Stone Generator"""
    bl_label = "GEN Medieval Stone"
    bl_idname = "ZENV_PT_medieval_stone"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
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
        layout.operator("object.zenv_generate_stone_block", text="Generate Stone Block")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_GenerateStoneBlock_Properties,
    ZENV_OT_GenerateStoneBlock,
    ZENV_PT_GenerateStoneBlock_Panel
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_stone_block_generator = PointerProperty(type=ZENV_PG_GenerateStoneBlock_Properties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_stone_block_generator

if __name__ == "__main__":
    register()
