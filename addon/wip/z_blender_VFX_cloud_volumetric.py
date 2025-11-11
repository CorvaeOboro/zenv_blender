"""
VFX Volumetric Cloud Blender Addon
- Creates volumetric clouds using sphere clusters and point clouds
- using advection and noise to simulate cloud movement and shape
"""

bl_info = {
    "name": 'VFX Volumetric Cloud',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250312',
    "description": 'Creates volumetric clouds using sphere clusters and point clouds',
    "status": 'wip',
    "approved": True,
    "group": 'VFX',
    "group_prefix": 'VFX',
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
import random
import numpy as np
from mathutils import Vector, Matrix, noise, kdtree
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty, FloatVectorProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_VolumetricCloudProperties(PropertyGroup):
    """Properties for the Volumetric Cloud Generator"""
    resolution: IntProperty(
        name="Resolution",
        description="Resolution of the voxel grid",
        default=64,
        min=32,
        max=256
    )
    noise_scale: FloatProperty(
        name="Noise Scale",
        description="Scale of the noise pattern",
        default=1.0,
        min=0.1,
        max=5.0
    )
    noise_detail: IntProperty(
        name="Noise Detail",
        description="Detail level of noise",
        default=4,
        min=1,
        max=8
    )
    noise_roughness: FloatProperty(
        name="Noise Roughness",
        description="Roughness of the noise pattern",
        default=0.5,
        min=0.0,
        max=1.0
    )
    density_threshold: FloatProperty(
        name="Density Threshold",
        description="Threshold for density cutoff",
        default=0.5,
        min=0.0,
        max=1.0
    )
    sphere_count: IntProperty(
        name="Base Spheres",
        description="Number of spheres in the base cluster",
        default=15,
        min=5,
        max=50
    )
    point_count: IntProperty(
        name="Surface Points",
        description="Number of points for surface sampling",
        default=5000,
        min=100,
        max=50000
    )
    advection_steps: IntProperty(
        name="Advection Steps",
        description="Number of steps for advection simulation",
        default=10,
        min=0,
        max=50
    )
    advection_strength: FloatProperty(
        name="Advection Strength",
        description="Strength of advection effect",
        default=0.5,
        min=0.0,
        max=2.0
    )
    smoothing_iterations: IntProperty(
        name="Smoothing",
        description="Number of mesh smoothing iterations",
        default=3,
        min=0,
        max=10
    )
    output_type: EnumProperty(
        name="Output Type",
        description="Type of cloud output",
        items=[
            ('VOXELS', "Voxels", "Generate voxel mesh"),
            ('POINTS', "Points", "Generate point cloud"),
            ('BOTH', "Both", "Generate both outputs")
        ],
        default='BOTH'
    )
    cloud_type: EnumProperty(
        name="Cloud Type",
        description="Type of cloud formation",
        items=[
            ('CUMULUS', "Cumulus", "Dense, puffy clouds"),
            ('STRATUS', "Stratus", "Layered, flat clouds"),
            ('CIRRUS', "Cirrus", "High-altitude, wispy clouds")
        ],
        default='CUMULUS'
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_VolumetricCloudAdd(Operator):
    """Create a new volumetric cloud"""
    bl_idname = "zenv.volumetric_cloud_add"
    bl_label = "Add Volumetric Cloud"
    bl_options = {'REGISTER', 'UNDO'}

    def create_base_sphere_cluster(self, context, props):
        """Create initial sphere cluster with random warping"""
        spheres = []
        base_radius = 1.0
        
        # Create main sphere with type-specific size
        if props.cloud_type == 'STRATUS':
            base_radius *= 1.2  # Wider base for stratus
        elif props.cloud_type == 'CIRRUS':
            base_radius *= 0.8  # Thinner base for cirrus
        
        spheres.append((Vector((0, 0, 0)), base_radius))
        
        # Create formation-specific distribution
        for _ in range(props.sphere_count - 1):
            if props.cloud_type == 'STRATUS':
                # Horizontal plane distribution
                angle = random.uniform(0, math.pi * 2)
                radius = random.uniform(0.3, 1.0) * base_radius
                pos = Vector((
                    math.cos(angle) * radius,
                    math.sin(angle) * radius,
                    random.uniform(-0.2, 0.2)  # Limited vertical spread
                ))
                sphere_radius = base_radius * random.uniform(0.3, 0.7)
                
            elif props.cloud_type == 'CIRRUS':
                # Linear streak distribution
                main_angle = random.uniform(-math.pi/6, math.pi/6)  # Limited angle variation
                distance = random.uniform(0.5, 2.0) * base_radius
                pos = Vector((
                    math.cos(main_angle) * distance,
                    math.sin(main_angle) * distance,
                    random.uniform(-0.2, 0.2)  # Limited vertical spread
                ))
                sphere_radius = base_radius * random.uniform(0.2, 0.4)
                
            else:  # CUMULUS
                # Volumetric distribution with vertical bias
                angle = random.uniform(0, math.pi * 2)
                z = random.uniform(-0.5, 1.0)  # More upward spread
                r = math.sqrt(random.uniform(0, 1)) * base_radius  # Square root for better distribution
                pos = Vector((
                    r * math.cos(angle),
                    r * math.sin(angle),
                    z
                ))
                sphere_radius = base_radius * random.uniform(0.5, 0.9)
            
            # Add some natural variation
            turbulence = Vector((
                random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2),
                random.uniform(-0.1, 0.1)
            ))
            pos += turbulence
            
            spheres.append((pos, sphere_radius))
        
        return spheres

    def sample_sphere_surface(self, sphere_pos, radius, num_points, props):
        """Generate evenly distributed points on sphere surface with type-specific variations"""
        points = []
        golden_ratio = (1 + math.sqrt(5)) / 2
        
        for i in range(num_points):
            # Fibonacci sphere algorithm for even distribution
            theta = 2 * math.pi * i / golden_ratio
            phi = math.acos(1 - 2 * (i + 0.5) / num_points)
            
            # Add type-specific variations to the surface points
            if props.cloud_type == 'STRATUS':
                # Flatten distribution
                phi = math.acos(1 - (i + 0.5) / num_points) * 0.5
                
            elif props.cloud_type == 'CIRRUS':
                # Stretch horizontally
                theta *= 1.5
                phi = math.acos(1 - (i + 0.5) / num_points) * 0.3
            
            x = math.cos(theta) * math.sin(phi)
            y = math.sin(theta) * math.sin(phi)
            z = math.cos(phi)
            
            # Add small random displacement for natural variation
            displacement = Vector((
                random.uniform(-0.1, 0.1),
                random.uniform(-0.1, 0.1),
                random.uniform(-0.1, 0.1)
            ))
            
            pos = Vector((x, y, z)) * radius + sphere_pos + displacement
            points.append(pos)
        
        return points

    def apply_advection(self, points, props):
        """Apply advection simulation to points"""
        kd = kdtree.KDTree(len(points))
        for i, point in enumerate(points):
            kd.insert(point, i)
        kd.balance()
        
        # Get cloud-specific parameters
        if props.cloud_type == 'STRATUS':
            search_radius = props.advection_strength * 2.0  # Wider influence
            force_scale = 0.05  # Gentler movement
        elif props.cloud_type == 'CIRRUS':
            search_radius = props.advection_strength * 3.0  # Very wide influence
            force_scale = 0.15  # Stronger movement
        else:  # CUMULUS
            search_radius = props.advection_strength  # Normal influence
            force_scale = 0.1  # Normal movement
        
        # Simulate fluid-like motion
        for step in range(props.advection_steps):
            new_points = points.copy()
            for i, point in enumerate(points):
                # Find nearby points
                nearby = []
                for (co, index, dist) in kd.find_range(point, search_radius):
                    if index != i:
                        nearby.append((co, dist))
                
                if nearby:
                    # Calculate weighted direction
                    direction = Vector((0, 0, 0))
                    total_weight = 0
                    for co, dist in nearby:
                        weight = 1.0 - (dist / search_radius)  # Linear falloff
                        direction += (co - point).normalized() * weight
                        total_weight += weight
                    
                    if total_weight > 0:
                        direction = direction / total_weight
                        
                        # Apply cloud-type specific motion
                        if props.cloud_type == 'STRATUS':
                            direction.z *= 0.2  # Limit vertical movement
                        elif props.cloud_type == 'CIRRUS':
                            direction.z *= 0.1  # Very limited vertical
                            direction.x *= 1.5  # Emphasize horizontal
                            direction.y *= 1.5
                        
                        new_points[i] += direction * force_scale
            
            points = new_points
            
            # Update KD tree periodically
            if step % 3 == 0:
                kd = kdtree.KDTree(len(points))
                for i, point in enumerate(points):
                    kd.insert(point, i)
                kd.balance()
        
        return points

    def apply_noise_deformation(self, points, props):
        """Apply 3D noise deformation to points"""
        deformed_points = []
        
        # Get cloud-specific parameters
        if props.cloud_type == 'STRATUS':
            noise_scale = Vector((1.0, 1.0, 0.3))  # Flatten vertically
            displacement_scale = 0.3
        elif props.cloud_type == 'CIRRUS':
            noise_scale = Vector((2.0, 2.0, 0.2))  # Stretch horizontally
            displacement_scale = 0.8
        else:  # CUMULUS
            noise_scale = Vector((1.0, 1.0, 1.0))  # Uniform
            displacement_scale = 0.5
        
        for point in points:
            # Generate 3D offset using different noise frequencies
            offset = Vector((0, 0, 0))
            
            # Base noise
            base_noise = Vector((
                self.generate_3d_noise(props, point + Vector((0, 0, 0))),
                self.generate_3d_noise(props, point + Vector((1, 1, 1))),
                self.generate_3d_noise(props, point + Vector((2, 2, 2)))
            )) - Vector((0.5, 0.5, 0.5))
            offset += base_noise
            
            # Detail noise
            detail_scale = 2.0
            detail_noise = Vector((
                self.generate_3d_noise(props, (point + Vector((3, 3, 3))) * detail_scale),
                self.generate_3d_noise(props, (point + Vector((4, 4, 4))) * detail_scale),
                self.generate_3d_noise(props, (point + Vector((5, 5, 5))) * detail_scale)
            )) - Vector((0.5, 0.5, 0.5))
            offset += detail_noise * 0.5
            
            # Apply cloud-specific scaling
            offset = Vector((
                offset.x * noise_scale.x,
                offset.y * noise_scale.y,
                offset.z * noise_scale.z
            ))
            
            deformed_points.append(point + offset * displacement_scale)
        
        return deformed_points

    def generate_3d_noise(self, props, pos):
        """Generate 3D noise value at position"""
        base = noise.noise(pos * props.noise_scale)
        
        # Layer noise based on detail
        value = base
        amp = 1.0
        freq = 1.0
        
        for _ in range(props.noise_detail):
            freq *= 2.0
            amp *= props.noise_roughness
            value += noise.noise(pos * props.noise_scale * freq) * amp
        
        return (value + 1.0) * 0.5  # Normalize to 0-1

    def create_cloud_material(self, props):
        """Create cloud material with volumetric and surface settings"""
        mat = bpy.data.materials.new(name="Cloud_Material")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'HASHED'
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes
        node_output = nodes.new('ShaderNodeOutputMaterial')
        node_mix_shader = nodes.new('ShaderNodeMixShader')
        node_principled = nodes.new('ShaderNodeBsdfPrincipled')
        node_transparent = nodes.new('ShaderNodeBsdfTransparent')
        node_noise = nodes.new('ShaderNodeTexNoise')
        node_mapping = nodes.new('ShaderNodeMapping')
        node_tex_coord = nodes.new('ShaderNodeTexCoord')
        
        # Set locations
        node_output.location = (600, 0)
        node_mix_shader.location = (400, 0)
        node_principled.location = (200, 100)
        node_transparent.location = (200, -100)
        node_noise.location = (-200, 200)
        node_mapping.location = (-400, 200)
        node_tex_coord.location = (-600, 200)
        
        # Set up noise texture
        node_noise.inputs['Scale'].default_value = 2.0
        node_noise.inputs['Detail'].default_value = 8.0
        node_noise.inputs['Roughness'].default_value = 0.7
        
        # Set up mapping
        node_mapping.inputs['Scale'].default_value = (1.0, 1.0, 0.5)
        
        # Configure base material
        if props.cloud_type == 'STRATUS':
            base_color = (0.9, 0.9, 0.9, 1.0)
            mix_factor = 0.95
            roughness = 1.0
        elif props.cloud_type == 'CIRRUS':
            base_color = (0.95, 0.95, 1.0, 1.0)
            mix_factor = 0.98
            roughness = 0.9
        else:  # CUMULUS
            base_color = (1.0, 1.0, 1.0, 1.0)
            mix_factor = 0.93
            roughness = 1.0
        
        # Set material parameters
        node_principled.inputs['Base Color'].default_value = base_color
        node_principled.inputs['Roughness'].default_value = roughness
        node_principled.inputs['Specular IOR Level'].default_value = 0.0
        node_principled.inputs['Transmission Weight'].default_value = 0.8
        node_principled.inputs['Alpha'].default_value = 0.9
        
        node_mix_shader.inputs['Fac'].default_value = mix_factor
        
        # Create links
        links.new(node_tex_coord.outputs['Generated'], node_mapping.inputs['Vector'])
        links.new(node_mapping.outputs['Vector'], node_noise.inputs['Vector'])
        links.new(node_noise.outputs['Fac'], node_principled.inputs['Alpha'])
        links.new(node_principled.outputs[0], node_mix_shader.inputs[1])
        links.new(node_transparent.outputs[0], node_mix_shader.inputs[2])
        links.new(node_mix_shader.outputs[0], node_output.inputs['Surface'])
        
        return mat

    def create_mesh_from_points(self, context, points, props):
        """Create smooth mesh from points using metaballs"""
        # Create metaball object
        meta = bpy.data.metaballs.new("CloudMeta")
        meta.resolution = 0.1  # Higher resolution for denser surface
        meta.threshold = 0.8   # Lower threshold for larger volume
        meta_obj = bpy.data.objects.new("CloudMeta", meta)
        context.collection.objects.link(meta_obj)
        
        # Add metaball elements with size variation
        base_radius = 0.15  # Smaller radius for finer detail
        for point in points:
            element = meta.elements.new()
            element.co = point
            # Vary radius based on cloud type
            if props.cloud_type == 'STRATUS':
                element.radius = base_radius * 1.2
            elif props.cloud_type == 'CIRRUS':
                element.radius = base_radius * 0.6
            else:  # CUMULUS
                element.radius = base_radius * random.uniform(0.8, 1.0)
            element.stiffness = 1.5  # Lower stiffness for smoother blending
        
        # Ensure metaball is selected and active
        bpy.ops.object.select_all(action='DESELECT')
        meta_obj.select_set(True)
        context.view_layer.objects.active = meta_obj
        
        # Convert to mesh
        bpy.ops.object.convert(target='MESH')
        mesh_obj = context.active_object
        
        # Apply smoothing using vertex smoothing
        try:
            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Smooth multiple times for better results
            for _ in range(props.smoothing_iterations):
                # Select all vertices
                bpy.ops.mesh.select_all(action='SELECT')
                # Apply smoothing with multiple iterations
                bpy.ops.mesh.vertices_smooth(repeat=3, factor=0.3)
            
            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Set smooth shading
            bpy.ops.object.shade_smooth()
            mesh_obj.data.use_auto_smooth = True
            mesh_obj.data.auto_smooth_angle = math.radians(60)
            
        except Exception as e:
            # Ensure we return to object mode even if smoothing fails
            bpy.ops.object.mode_set(mode='OBJECT')
            print(f"Warning: Smoothing operation failed: {str(e)}")
        
        # Add material
        mat = self.create_cloud_material(props)
        mesh_obj.data.materials.append(mat)
        
        # Set object properties
        mesh_obj.show_transparent = True
        mesh_obj.display_type = 'TEXTURED'
        
        # Clean up
        bpy.data.metaballs.remove(meta)
        
        return mesh_obj

    def execute(self, context):
        """Create a new volumetric cloud"""
        try:
            props = context.scene.cloud_props
            
            # Step 1: Create base sphere cluster
            spheres = self.create_base_sphere_cluster(context, props)
            
            # Step 2: Sample points on sphere surfaces
            points = []
            points_per_sphere = max(1, props.point_count // len(spheres))
            for sphere_pos, radius in spheres:
                points.extend(self.sample_sphere_surface(sphere_pos, radius, points_per_sphere, props))
            
            # Step 3: Apply advection simulation
            if props.advection_steps > 0:
                points = self.apply_advection(points, props)
            
            # Step 4: Apply noise deformation
            points = self.apply_noise_deformation(points, props)
            
            # Step 5: Create final outputs
            if props.output_type in {'VOXELS', 'BOTH'}:
                mesh_obj = self.create_mesh_from_points(context, points, props)
                mesh_obj.name = "Cloud_Mesh"
            
            if props.output_type in {'POINTS', 'BOTH'}:
                # Create point cloud
                mesh = bpy.data.meshes.new("Cloud_Points")
                mesh.from_pydata(points, [], [])
                mesh.update()
                
                point_obj = bpy.data.objects.new("Cloud_Points", mesh)
                context.collection.objects.link(point_obj)
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error creating cloud: {str(e)}")
            return {'CANCELLED'}

    @classmethod
    def poll(cls, context):
        """Check if the operator can be called"""
        return context.mode == 'OBJECT'  # Only allow in Object mode

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_VolumetricCloudPanel(Panel):
    """Panel for Volumetric Cloud Generator"""
    bl_label = "VFX Volumetric Cloud"
    bl_idname = "ZENV_PT_volumetric_cloud"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.cloud_props
        
        layout.prop(props, "cloud_type")
        layout.prop(props, "output_type")
        
        box = layout.box()
        box.label(text="Base Shape:")
        box.prop(props, "sphere_count")
        box.prop(props, "point_count")
        
        box = layout.box()
        box.label(text="Noise Settings:")
        box.prop(props, "noise_scale")
        box.prop(props, "noise_detail")
        box.prop(props, "noise_roughness")
        
        box = layout.box()
        box.label(text="Advection:")
        box.prop(props, "advection_steps")
        box.prop(props, "advection_strength")
        
        box = layout.box()
        box.label(text="Mesh Settings:")
        box.prop(props, "smoothing_iterations")
        
        layout.operator("zenv.volumetric_cloud_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_VolumetricCloudProperties,
    ZENV_OT_VolumetricCloudAdd,
    ZENV_PT_VolumetricCloudPanel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.cloud_props = PointerProperty(type=ZENV_PG_VolumetricCloudProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.cloud_props

if __name__ == "__main__":
    register()
