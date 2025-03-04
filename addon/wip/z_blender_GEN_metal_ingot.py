"""
GEN Metal Ingot Generator - Creates metal ingots with surface imperfections
a trapezoidal base shape with beveled edges . UV mapping to hide seam along base .
surface is cut by world unit slices then uses multiple noise layers for surface detail .
lastly optimized .
Generation processing time at gridsize 1.0 = 12s 
"""

bl_info = {
    "name": "Metal Ingot Generator",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV > GEN Metal Ingot",
    "description": "Generate metal ingot meshes",
    "category": "ZENV"
}

import bpy
import bmesh
import math
import random
import logging
import time
from mathutils import Vector, Matrix, noise
from bpy.props import (
    FloatProperty,
    BoolProperty,
    IntProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

class ZENV_PG_MetalIngotProps(PropertyGroup):
    """Properties for metal ingot generation"""
    
    # Base shape properties
    length: FloatProperty(
        name="Length",
        description="Length of the ingot",
        default=0.2,  # 20cm
        min=0.05,
        max=1.0,
        unit='LENGTH'
    )
    width: FloatProperty(
        name="Width",
        description="Width of the ingot at the base",
        default=0.1,  # 10cm
        min=0.025,
        max=0.5,
        unit='LENGTH'
    )
    height: FloatProperty(
        name="Height",
        description="Height of the ingot",
        default=0.05,  # 5cm
        min=0.01,
        max=0.25,
        unit='LENGTH'
    )
    taper: FloatProperty(
        name="Taper",
        description="Amount of tapering from base to top",
        default=0.2,
        min=0.0,
        max=0.5
    )
    variation_scale: FloatProperty(
        name="Variation Range",
        description="Scale of random variations in base shape , 0.3 default",
        default=0.3,
        min=0.0,
        max=1.0
    )
    
    # Surface detail properties
    detail_scale: FloatProperty(
        name="Detail Intensity",
        description="Scale of surface imperfections",
        default=1.0,
        min=0.1,
        max=10.0
    )
    roughness: FloatProperty(
        name="Roughness",
        description="Intensity of surface roughness",
        default=0.001,  # 1mm
        min=0.0,
        max=0.01,
        precision=4
    )
    bubble_density: IntProperty(
        name="Bubble Density",
        description="Number of smelting bubbles/imperfections",
        default=15,
        min=0,
        max=100
    )
    micro_detail: FloatProperty(
        name="Micro Intensity",
        description="Intensity of centimeter-scale surface imperfections",
        default=0.0005,  # 0.3mm
        min=-1.000,
        max=1.000,
        precision=5
    )
    micro_scale: FloatProperty(
        name="Micro Scale",
        description="Scale of micro surface details (in centimeters)",
        default=0.5,  # 0.5cm scale
        min=0.1,
        max=5.0
    )
    
    # Remesh properties
    grid_size: FloatProperty(
        name="Grid Size",
        description="Size of grid cutting in centimeters",
        default=1.0,  # 1.0 1cm default
        min=0.1,
        max=2.0,
        precision=2
    )
    
    # Bevel properties
    bevel_width: FloatProperty(
        name="Bevel Width",
        description="Width of edge bevels",
        default=0.005,  # 5mm
        min=0.001,
        max=0.02,
        precision=4
    )
    bevel_segments: IntProperty(
        name="Bevel Segments",
        description="Number of bevel segments",
        default=4,
        min=2,
        max=6
    )
    
    # Step control properties
    do_bevel: BoolProperty(
        name="Apply Bevel",
        description="Apply bevel modifier to edges",
        default=True
    )
    do_grid_cut: BoolProperty(
        name="Apply Grid Cut",
        description="Cut mesh into grid pattern",
        default=True
    )
    do_micro_detail: BoolProperty(
        name="Apply Micro Detail",
        description="Add micro surface imperfections",
        default=True
    )
    do_optimize: BoolProperty(
        name="Optimize Mesh",
        description="Apply smart mesh optimization",
        default=True
    )
    do_random_uv: BoolProperty(
        name="Random UV Transform",
        description="Randomly transform UVs for variation",
        default=True
    )
    
# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_MetalIngot(Operator):
    """Generate a metal ingot with realistic surface details"""
    bl_idname = "zenv.metal_ingot"
    bl_label = "Generate Metal Ingot"
    bl_options = {'REGISTER', 'UNDO'}
    
    def generate_base_shape(self, bm, props):
        """Create the basic trapezoidal ingot shape"""
        # Get time-based random seed
        random.seed(int(time.time() * 1000))
        
        # Create vertices for the trapezoid with subtle random variations
        l, w, h = props.length, props.width, props.height
        t = props.taper
        v_scale = props.variation_scale * 0.02  # Scale down variations
        
        def random_offset():
            return random.uniform(-v_scale, v_scale)
        
        # Bottom vertices (keep flat for stability)
        v1 = bm.verts.new((-l/2, -w/2, 0))
        v2 = bm.verts.new((l/2, -w/2, 0))
        v3 = bm.verts.new((l/2, w/2, 0))
        v4 = bm.verts.new((-l/2, w/2, 0))
        
        # Top vertices (with taper and subtle random variations)
        top_rand = props.variation_scale * 0.01  # Smaller variations for top
        v5 = bm.verts.new((-l/2 * (1-t) + random_offset(), -w/2 * (1-t) + random_offset(), h + random.uniform(-top_rand, top_rand)))
        v6 = bm.verts.new((l/2 * (1-t) + random_offset(), -w/2 * (1-t) + random_offset(), h + random.uniform(-top_rand, top_rand)))
        v7 = bm.verts.new((l/2 * (1-t) + random_offset(), w/2 * (1-t) + random_offset(), h + random.uniform(-top_rand, top_rand)))
        v8 = bm.verts.new((-l/2 * (1-t) + random_offset(), w/2 * (1-t) + random_offset(), h + random.uniform(-top_rand, top_rand)))
        
        # Create faces
        faces = [
            [v1, v2, v3, v4],  # bottom
            [v5, v6, v7, v8],  # top
            [v1, v5, v6, v2],  # front
            [v2, v6, v7, v3],  # right
            [v3, v7, v8, v4],  # back
            [v4, v8, v5, v1],  # left
        ]
        
        for f in faces:
            bm.faces.new(f)
        
        # Ensure normals are correct
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        return bm
    
    def add_surface_undulations(self, bm, props):
        """Add surface imperfections using multiple noise layers"""
        # Time based random seed
        noise_seed = int(time.time() * 1000) 
        
        for v in bm.verts:
            # Layer 1: Large-scale undulations (reduced intensity)
            noise1 = noise.noise(v.co * props.detail_scale + Vector((noise_seed, 0, 0))) * props.roughness * 0.8
            
            # Layer 2: Medium details
            noise2 = noise.noise(v.co * props.detail_scale * 4 + Vector((0, noise_seed, 0))) * props.roughness * 0.4
            
            # Layer 3: Fine surface texture
            noise3 = noise.noise(v.co * props.detail_scale * 16 + Vector((0, 0, noise_seed))) * props.roughness * 0.2
            
            # Combine layers with reduced intensity for top face
            total_displacement = (noise1 + noise2 + noise3)
            if v.co.z > props.height * 0.9:  # Reduce displacement on top surface
                total_displacement *= 0.5
            v.co += v.normal * total_displacement
    
    def add_smelting_bubbles(self, bm, props):
        """Add random bubble-like imperfections"""
        for _ in range(props.bubble_density):
            # Random position on surface
            x = random.uniform(-props.length/2, props.length/2)
            y = random.uniform(-props.width/2, props.width/2)
            z = random.uniform(0, props.height)
            
            # Create small sphere-like deformation
            for v in bm.verts:
                dist = (Vector((x, y, z)) - v.co).length
                if dist < props.roughness * 2:
                    factor = 1 - (dist / (props.roughness * 2))
                    v.co += v.normal * factor * props.roughness
    
    def add_micro_detail(self, bm, props):
        """Add final pass of cellular noise for micro surface imperfections"""
        noise_seed = int(time.time() * 1000)
        scale = 100 * props.micro_scale  # Convert to ~1cm scale
        
        # Ensure correct normals before starting
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Create vertex groups for edge detection
        edge_vertices = set()
        for edge in bm.edges:
            if edge.calc_face_angle_signed() > math.radians(30):
                edge_vertices.add(edge.verts[0])
                edge_vertices.add(edge.verts[1])
        
        def cellular_noise(pos, offset):
            """Enhanced Manhattan distance cellular noise with second-closest point"""
            scaled_pos = (pos * scale) + Vector((offset, offset, offset))
            p = Vector((int(scaled_pos.x), int(scaled_pos.y), int(scaled_pos.z)))
            
            # Track both closest and second closest distances
            min_dist = float('inf')
            second_min_dist = float('inf')
            
            # Check neighboring cells in larger area for more crystalline patterns
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    for dz in range(-2, 3):
                        cell_pos = p + Vector((dx, dy, dz))
                        # Generate stable random point in cell
                        random.seed(hash((cell_pos.x, cell_pos.y, cell_pos.z, noise_seed)))
                        point = cell_pos + Vector((random.random(), random.random(), random.random()))
                        
                        # Manhattan distance
                        dist = abs(point.x - scaled_pos.x) + abs(point.y - scaled_pos.y) + abs(point.z - scaled_pos.z)
                        
                        if dist < min_dist:
                            second_min_dist = min_dist
                            min_dist = dist
                        elif dist < second_min_dist:
                            second_min_dist = dist
            
            # Use difference between closest and second closest for sharper features
            diff = (second_min_dist - min_dist) / scale
            # Normalize to [-1, 1] range and enhance contrast
            return math.tanh(diff * 3.0) * 2.0 - 1.0

        # Calculate vertex normals
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        
        # Store original positions
        orig_positions = {v: v.co.copy() for v in bm.verts}
        
        # First pass to calculate noise range for normalization
        noise_values = []
        for v in bm.verts:
            # Generate three offset cellular patterns
            n1 = cellular_noise(v.co, 0)
            n2 = cellular_noise(v.co, 100) * 0.6
            n3 = cellular_noise(v.co, -100) * 0.3
            
            total = (n1 + n2 + n3) * 0.5
            noise_values.append(total)
        
        # Calculate noise range for normalization
        noise_min = min(noise_values)
        noise_max = max(noise_values)
        noise_range = noise_max - noise_min
        
        # Apply normalized noise
        for v, noise_val in zip(bm.verts, noise_values):
            # Normalize to [-1, 1] range
            if noise_range > 0:
                total = 2.0 * ((noise_val - noise_min) / noise_range) - 1.0
            else:
                total = 0
                
            # Scale by micro detail intensity
            total *= props.micro_detail
            
            # Reduce effect near edges
            if v in edge_vertices:
                total *= 0.3
            
            # Calculate average normal from connected faces
            normal = Vector((0, 0, 0))
            num_faces = 0
            for face in v.link_faces:
                normal += face.normal
                num_faces += 1
            if num_faces > 0:
                normal.normalize()
            else:
                normal = v.normal
            
            # Apply displacement along normal
            v.co = orig_positions[v] + normal * total
        
        # Final normal recalculation and smoothing
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=0.1, use_axis_x=True, use_axis_y=True, use_axis_z=True)

    def setup_uv_mapping(self, bm):
        """Set up UV mapping with bottom edge seams"""
        # Ensure UV layer exists
        if not bm.loops.layers.uv:
            bm.loops.layers.uv.new()
        
        # Mark bottom edges as seams
        for edge in bm.edges:
            # Find edges near the bottom
            verts_z = [v.co.z for v in edge.verts]
            if max(verts_z) < 0.01:  # Bottom edges
                edge.seam = True
        
        return bm

    def create_base_mesh(self, context):
        """Create the base mesh"""
        # Create new bmesh
        bm = bmesh.new()
        
        # Get properties
        props = context.scene.zenv_metal_ingot_props
        
        # Generate base shape
        self.generate_base_shape(bm, props)
        
        # Add large-scale surface undulations
        self.add_surface_undulations(bm, props)
        
        # Add smelting bubbles
        self.add_smelting_bubbles(bm, props)
        
        # Create object and link to scene
        mesh = bpy.data.meshes.new("Metal_Ingot")
        obj = bpy.data.objects.new(mesh.name, mesh)
        
        # Link object to scene
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Apply bmesh to object
        bm.to_mesh(mesh)
        bm.free()
        
        return obj

    def apply_bevel(self, obj, props, context):
        """Apply bevel modifier"""
        bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
        bevel.width = props.bevel_width
        bevel.segments = props.bevel_segments
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = math.radians(30)
        
        context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=bevel.name)

    def get_mesh_bounds(self, bm: bmesh.types.BMesh) -> tuple[Vector, Vector]:
        """Calculate mesh bounds in world space"""
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        return bounds_min, bounds_max

    def calculate_grid_cuts(self, bounds_min: Vector, bounds_max: Vector, density: float) -> list[list[float]]:
        """Calculate grid cut positions for each axis"""
        cuts = []
        for axis in range(3):
            start = density * (bounds_min[axis] // density)
            num_cuts = int((bounds_max[axis] - start) / density) + 1
            axis_cuts = [start + (i * density) for i in range(num_cuts)]
            cuts.append(axis_cuts)
        return cuts

    def apply_grid_cut(self, obj, props, context):
        """Apply grid cutting using world-space coordinates"""
        # Store active object and mode
        original_mode = obj.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Apply all transforms to ensure proper cutting
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        
        # Create BMesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        # Get bounds
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        
        # Convert grid size to meters (Blender units)
        grid_size = props.grid_size * 0.01
        
        # Function to perform a single cut
        def make_cut(axis, position):
            # Create cutting plane
            plane_co = Vector((0, 0, 0))
            plane_co[axis] = position
            plane_no = Vector((0, 0, 0))
            plane_no[axis] = 1.0
            
            # Perform multiple cuts at slightly offset positions for robustness
            offsets = [-0.00001, 0, 0.00001]  # Multiple cuts at slightly different positions
            for offset in offsets:
                plane_co_offset = plane_co.copy()
                plane_co_offset[axis] += offset
                
                try:
                    # Cut with bisect_plane
                    bmesh.ops.bisect_plane(
                        bm,
                        geom=bm.edges[:] + bm.faces[:],
                        dist=0.00001,
                        plane_co=plane_co_offset,
                        plane_no=plane_no,
                        use_snap_center=False,
                        clear_outer=False,
                        clear_inner=False
                    )
                    
                    # Clean up after each cut
                    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00001)
                    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                    
                except Exception as e:
                    continue  # Try next offset if this one fails
        
        # Perform cuts along each axis
        for axis in range(3):
            # Calculate number of cuts needed
            start = grid_size * (bounds_min[axis] // grid_size)
            end = bounds_max[axis]
            num_cuts = int((end - start) / grid_size) + 2  # Add extra cut for safety
            
            # Make cuts
            for i in range(num_cuts):
                cut_pos = start + (i * grid_size)
                make_cut(axis, cut_pos)
                
                # Update mesh between major axis changes for stability
                bm.to_mesh(obj.data)
                obj.data.update()
        
        # Final cleanup pass
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00001)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Update mesh
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()
        
        # Add weighted normal modifier for clean shading
        weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
        weighted_normal.keep_sharp = True
        weighted_normal.weight = 50
        weighted_normal.thresh = 0.01
        
        # Restore original mode
        bpy.ops.object.mode_set(mode=original_mode)

    def optimize_mesh(self, obj, props):
        """Smart mesh optimization using planar decimation and proper triangulation"""
        try:
            # Ensure we're in object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Set as active object
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # Add planar decimate modifier
            decimate = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate.decimate_type = 'DISSOLVE'  # Planar mode
            decimate.angle_limit = math.radians(1.0)  # 1 degree
            decimate.use_dissolve_boundaries = False
            decimate.delimit = {'SHARP'}  # Delimit by sharp edges
            
            # Apply decimate
            bpy.ops.object.modifier_apply(modifier="Decimate")
            
            # Add triangulate modifier with beauty settings
            triangulate = obj.modifiers.new(name="Triangulate", type='TRIANGULATE')
            triangulate.quad_method = 'BEAUTY'
            triangulate.ngon_method = 'BEAUTY'
            
            # Apply triangulate
            bpy.ops.object.modifier_apply(modifier="Triangulate")
            
            # Add weighted normal modifier
            weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
            weighted_normal.mode = 'FACE_AREA'
            weighted_normal.weight = 50  # Maximum weight for stronger effect
            weighted_normal.thresh = 0.01
            weighted_normal.keep_sharp = False
            
            # Apply weighted normal
            bpy.ops.object.modifier_apply(modifier="Weighted Normal")
            
        except Exception as e:
            self.report({'ERROR'}, f"Optimization failed: {str(e)}")
            return
        
        # Ensure proper shading
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(60)

    def randomize_uvs(self, obj):
        """Apply random transformation to UVs by directly modifying UV coordinates"""
        try:
            self.report({'INFO'}, "Starting UV randomization...")
            
            # Ensure we're in object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            
            # Ensure UV layer exists
            uv_layer = bm.loops.layers.uv.verify()
            if not uv_layer:
                self.report({'ERROR'}, "No UV layer found!")
                return
            
            self.report({'INFO'}, f"Found UV layer: {uv_layer.name}")
            
            # Generate random transformation values
            random.seed(int(time.time() * 1000))
            angle = random.uniform(0, math.radians(360))
            scale = random.uniform(0.9, 1.1)
            offset_x = random.uniform(-1, 1)
            offset_y = random.uniform(-1, 1)
            
            # Random mirroring
            mirror_x = random.choice([-1, 1])
            mirror_y = random.choice([-1, 1])
            
            self.report({'INFO'}, f"Generated random values: rot={math.degrees(angle):.1f}°, scale={scale:.2f}, offset=({offset_x:.2f}, {offset_y:.2f}), mirror=({mirror_x}, {mirror_y})")
            
            # Create rotation matrix
            cos_angle = math.cos(angle)
            sin_angle = math.sin(angle)
            
            # Count affected UVs
            affected_uvs = 0
            
            # Transform each UV coordinate
            for face in bm.faces:
                for loop in face.loops:
                    # Get UV coordinate
                    uv = loop[uv_layer].uv
                    old_uv = uv.copy()
                    
                    # Center UVs for transformation
                    x = uv.x - 0.5
                    y = uv.y - 0.5
                    
                    # Apply mirroring
                    x *= mirror_x
                    y *= mirror_y
                    
                    # Rotate
                    rotated_x = x * cos_angle - y * sin_angle
                    rotated_y = x * sin_angle + y * cos_angle
                    
                    # Scale
                    scaled_x = rotated_x * scale
                    scaled_y = rotated_y * scale
                    
                    # Offset and recenter
                    final_x = scaled_x + 0.5 + offset_x
                    final_y = scaled_y + 0.5 + offset_y
                    
                    # Apply transformed coordinates
                    loop[uv_layer].uv = Vector((final_x, final_y))
                    affected_uvs += 1
                    
                    if affected_uvs == 1:  # Log first UV transformation
                        self.report({'INFO'}, f"First UV transform: ({old_uv.x:.2f}, {old_uv.y:.2f}) -> ({final_x:.2f}, {final_y:.2f})")
            
            self.report({'INFO'}, f"Transformed {affected_uvs} UV coordinates")
            
            # Update mesh
            bm.to_mesh(obj.data)
            obj.data.update()  # Ensure mesh updates
            bm.free()
            
            self.report({'INFO'}, "UV randomization complete")
            
        except Exception as e:
            self.report({'ERROR'}, f"UV randomization failed: {str(e)}")
            import traceback
            self.report({'ERROR'}, traceback.format_exc())

    def execute(self, context):
        try:
            # Get properties
            props = context.scene.zenv_metal_ingot_props
            
            # Create base mesh
            obj = self.create_base_mesh(context)
            if not obj:
                return {'CANCELLED'}
            
            # Set as active object
            context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # Set up UV mapping immediately after base shape
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm = self.setup_uv_mapping(bm)
            bm.to_mesh(obj.data)
            bm.free()
            
            # Perform initial UV unwrap
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.unwrap(method='CONFORMAL', margin=0.001)
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Apply bevel first
            if props.do_bevel:
                self.apply_bevel(obj, props, context)
            
            # Then apply grid cutting
            if props.do_grid_cut:
                self.apply_grid_cut(obj, props, context)
            
            # Add micro surface details if enabled
            if props.do_micro_detail:
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                self.add_micro_detail(bm, props)
                bm.to_mesh(obj.data)
                bm.free()
            
            # Add subsurf modifier for final smoothing
            subsurf = obj.modifiers.new(name="Subdivision", type='SUBSURF')
            subsurf.levels = 1
            subsurf.render_levels = 2
            
            # Apply all modifiers
            for modifier in obj.modifiers[:]:
                try:
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
                except Exception as e:
                    self.report({'WARNING'}, f"Could not apply modifier {modifier.name}: {str(e)}")
                    continue
            
            # Only run optimization if enabled
            if props.do_optimize:
                self.optimize_mesh(obj, props)
            
            # Pack UVs after all modifications
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(margin=0.001)
            bpy.ops.object.mode_set(mode='OBJECT')  # Switch back to object mode
            
            # Apply random UV transformation if enabled
            if props.do_random_uv:
                self.report({'INFO'}, "Random UV transformation enabled, applying...")
                self.randomize_uvs(obj)
            
            # Add weighted normal modifier with corner angle mode
            weighted_normal = obj.modifiers.new(name="Weighted Normal", type='WEIGHTED_NORMAL')
            weighted_normal.mode = 'CORNER_ANGLE'
            weighted_normal.weight = 50  # Maximum weight for stronger effect
            weighted_normal.thresh = 0.01
            weighted_normal.keep_sharp = False
            
            # Apply weighted normal modifier
            bpy.ops.object.modifier_apply(modifier="Weighted Normal")
            
            # Ensure proper shading
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(60)
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to generate metal ingot: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_MetalIngot_Panel(Panel):
    """Panel for metal ingot generation"""
    bl_label = "GEN Metal Ingot Generator"
    bl_idname = "ZENV_PT_MetalIngot"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_metal_ingot_props

        # Process control box
        proc_box = layout.box()
        proc_box.label(text="Process Steps", icon='MODIFIER')
        proc_box.prop(props, "do_bevel")
        proc_box.prop(props, "do_grid_cut")
        proc_box.prop(props, "do_micro_detail")
        proc_box.prop(props, "do_optimize")
        proc_box.prop(props, "do_random_uv")

        # Base shape settings
        shape_box = layout.box()
        shape_box.label(text="Base Shape", icon='MESH_CUBE')
        shape_box.prop(props, "length")
        shape_box.prop(props, "width")
        shape_box.prop(props, "height")
        shape_box.prop(props, "taper")
        shape_box.prop(props, "variation_scale")

        # Detail settings
        if props.do_grid_cut:
            grid_box = layout.box()
            grid_box.label(text="Grid Settings", icon='MESH_GRID')
            grid_box.prop(props, "grid_size")

        if props.do_bevel:
            bevel_box = layout.box()
            bevel_box.label(text="Bevel Settings", icon='MOD_BEVEL')
            bevel_box.prop(props, "bevel_width")
            bevel_box.prop(props, "bevel_segments")

        if props.do_micro_detail:
            detail_box = layout.box()
            detail_box.label(text="Surface Detail", icon='FORCE_TURBULENCE')
            detail_box.prop(props, "micro_detail")
            detail_box.prop(props, "micro_scale")

        # Generate button
        layout.operator(ZENV_OT_MetalIngot.bl_idname, icon='MOD_CAST')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_MetalIngotProps,
    ZENV_OT_MetalIngot,
    ZENV_PT_MetalIngot_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_metal_ingot_props = PointerProperty(type=ZENV_PG_MetalIngotProps)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_metal_ingot_props

if __name__ == "__main__":
    register()
