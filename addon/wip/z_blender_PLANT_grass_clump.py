"""
PLANT Grass Cluster - a blender addon creates clusters of grass avoiding intersection 
grass blade is wide and stylized , a subtle bend and twist , 
like a tall leaf where the top and bot are pinched and its sides bend inward 
"""

bl_info = {
    "name": 'PLANT Grass Cluster',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Generate plant grass clusters',
    "status": 'wip',
    "approved": True,
    "group": 'Plant',
    "group_prefix": 'PLANT',
    "location": 'View3D > Sidebar > ZENV > PLANT Grass Cluster',
    "doc_url": '',
}

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix
from bpy.props import (
    FloatProperty,
    IntProperty,
    EnumProperty,
    PointerProperty
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup
)

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_GrassCluster_Props(PropertyGroup):
    """Properties for grass cluster generation"""
    radius: FloatProperty(
        name="Cluster Radius",
        description="Radius of the grass cluster",
        default=0.5,  # 50cm
        min=0.1,
        max=2.0,
        unit='LENGTH'
    )
    density: IntProperty(
        name="Strand Density",
        description="Number of grass strands per square meter",
        default=200,
        min=50,
        max=1000
    )
    density_falloff: FloatProperty(
        name="Density Falloff",
        description="How quickly density decreases from center",
        default=0.7,
        min=0.1,
        max=1.0
    )
    min_distance: FloatProperty(
        name="Minimum Distance",
        description="Minimum distance between grass strands",
        default=0.02,  # 2cm
        min=0.01,
        max=0.1,
        unit='LENGTH'
    )
    intersection_checks: IntProperty(
        name="Intersection Checks",
        description="Number of nearby strands to check for intersection",
        default=5,
        min=1,
        max=10
    )
    variation_seed: IntProperty(
        name="Variation Seed",
        description="Seed for random variations",
        default=1,
        min=1,
        max=1000
    )
    grass_type: EnumProperty(
        name="Grass Type",
        description="Type of grass to generate",
        items=[
            ('MEADOW', "Meadow Grass", "Thin, delicate grass blades"),
            ('WHEAT', "Wheat Grass", "Thicker, more robust grass"),
            ('TUSSOCK', "Tussock Grass", "Dense, clustering grass")
        ],
        default='MEADOW'
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_GrassCluster(Operator):
    """Generate a cluster of grass with realistic distribution"""
    bl_idname = "zenv.plant_grass_cluster"
    bl_label = "Generate Grass Cluster"
    bl_options = {'REGISTER', 'UNDO'}
    
    def create_base_strand_mesh(self, context, length, width, segments):
        """Create a single grass strand mesh with UVs"""
        # Increase resolution for better shaping
        segments = max(segments * 2, 8)  # Minimum 8 segments
        side_segments = 3  # Segments across width for better edge detail
        
        # Create vertices
        verts = []
        uvs = []
        
        for i in range(segments):
            t = i / (segments - 1)
            
            # Create profile curve that pinches at bottom and top
            profile_width = width * (1 - (2*t - 1)**2)  # Parabolic profile
            
            # Add slight S-curve using sine waves
            x_offset = math.sin(t * math.pi) * width * 0.3
            # Add secondary wave for more natural shape
            x_offset += math.sin(t * math.pi * 2) * width * 0.15
            
            # Add subtle thickness variation
            z_offset = math.sin(t * math.pi * 1.5) * width * 0.1
            
            # Create vertices across width
            for j in range(side_segments):
                s = j / (side_segments - 1)
                # Create curved cross-section
                curve_in = math.sin(s * math.pi) * 0.3  # 30% curve inward
                
                # Calculate vertex position
                x = (-profile_width/2 + profile_width * s) * (1 - curve_in) + x_offset
                y = z_offset * curve_in
                z = t * length
                
                verts.append((x, y, z))
                uvs.append((s, t))
        
        # Create faces
        faces = []
        for i in range(segments - 1):
            for j in range(side_segments - 1):
                # Calculate vertex indices
                i0 = i * side_segments + j
                i1 = i0 + 1
                i2 = (i + 1) * side_segments + j
                i3 = i2 + 1
                faces.append((i0, i1, i3, i2))
        
        # Create mesh
        mesh = bpy.data.meshes.new(name="GrassStrand")
        mesh.from_pydata(verts, [], faces)
        
        # Create UV layer
        uv_layer = mesh.uv_layers.new()
        for i, loop in enumerate(mesh.loops):
            uv_layer.data[i].uv = uvs[loop.vertex_index]
        
        # Add modifiers for final shaping
        obj = bpy.data.objects.new("GrassStrand", mesh)
        
        # Add subtle twist
        twist = obj.modifiers.new(name="Twist", type='SIMPLE_DEFORM')
        twist.deform_method = 'TWIST'
        twist.angle = math.radians(random.uniform(-15, 15))
        twist.deform_axis = 'Z'
        
        # Add main bend
        bend = obj.modifiers.new(name="Bend", type='SIMPLE_DEFORM')
        bend.deform_method = 'BEND'
        bend.angle = math.radians(random.uniform(10, 25))
        bend.deform_axis = 'Y'
        
        # Add subtle taper
        taper = obj.modifiers.new(name="Taper", type='SIMPLE_DEFORM')
        taper.deform_method = 'TAPER'
        taper.factor = random.uniform(0.1, 0.3)
        taper.deform_axis = 'Z'
        
        # Apply modifiers
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = bpy.data.meshes.new_from_object(obj_eval)
        
        # Clean up temporary objects
        bpy.data.objects.remove(obj)
        mesh.user_clear()
        bpy.data.meshes.remove(mesh)
        
        return mesh_eval

    def create_strand_variations(self, context, props):
        """Create different variations of grass strands"""
        variations = []
        
        # Base dimensions based on grass type
        if props.grass_type == 'MEADOW':
            base_length = 0.2  # 20cm
            base_width = 0.008  # 8mm
            segments = 6
        elif props.grass_type == 'WHEAT':
            base_length = 0.3  # 30cm
            base_width = 0.012  # 12mm
            segments = 7
        else:  # TUSSOCK
            base_length = 0.25  # 25cm
            base_width = 0.01  # 10mm
            segments = 6
        
        # Create 9 variations (3 for each zone: inner, middle, outer)
        random.seed(props.variation_seed)
        
        # Inner zone variations (longer)
        for i in range(3):
            length = base_length * random.uniform(0.95, 1.15)
            width = base_width * random.uniform(0.9, 1.1)
            mesh = self.create_base_strand_mesh(context, length * 1.2, width, segments + 1)
            variations.append(mesh)
        
        # Middle zone variations (medium)
        for i in range(3):
            length = base_length * random.uniform(0.85, 1.0)
            width = base_width * random.uniform(0.9, 1.1)
            mesh = self.create_base_strand_mesh(context, length, width, segments)
            variations.append(mesh)
        
        # Outer zone variations (shorter)
        for i in range(3):
            length = base_length * random.uniform(0.7, 0.85)
            width = base_width * random.uniform(0.8, 1.0)
            mesh = self.create_base_strand_mesh(context, length * 0.8, width, segments)
            variations.append(mesh)
        
        return variations

    def check_intersection(self, location, existing_strands, min_distance):
        """Check if a new strand would intersect with existing ones"""
        if not existing_strands:
            return False
            
        for strand in existing_strands:
            dist = (location - strand).length
            if dist < min_distance:
                return True
        return False

    def distribute_strands(self, context, props, strand_variations):
        """Distribute grass strands in a cluster pattern"""
        strands = []
        target_strands = int(props.density * math.pi * props.radius * props.radius)  # Calculate based on area
        max_attempts = target_strands * 10  # Maximum attempts to place strands
        attempts = 0
        
        # Create collection for grass cluster
        cluster_name = f"GrassCluster_{len(context.scene.collection.children) + 1}"
        cluster_collection = bpy.data.collections.new(cluster_name)
        context.scene.collection.children.link(cluster_collection)
        
        while len(strands) < target_strands and attempts < max_attempts:
            attempts += 1
            
            # Generate random position within circle
            angle = random.uniform(0, math.pi * 2)
            dist = math.sqrt(random.uniform(0, 1)) * props.radius  # Square root for uniform distribution
            
            # Apply density falloff
            falloff = math.pow(1 - dist/props.radius, 1/props.density_falloff)
            if random.random() > falloff:
                continue
                
            location = Vector((
                math.cos(angle) * dist,
                math.sin(angle) * dist,
                0
            ))
            
            # Check for intersections with recent strands
            check_count = min(props.intersection_checks, len(strands))
            if check_count > 0 and self.check_intersection(location, strands[-check_count:], props.min_distance):
                continue
            
            # Select strand variation based on distance from center
            if dist < props.radius * 0.3:
                # Inner area - prefer longer strands
                variation = random.choice(strand_variations[:3])
            elif dist < props.radius * 0.7:
                # Middle area - prefer medium strands
                variation = random.choice(strand_variations[3:6])
            else:
                # Outer area - prefer shorter strands
                variation = random.choice(strand_variations[6:])
            
            # Add random rotation and tilt
            rotation_z = random.uniform(0, math.pi * 2)
            tilt_angle = random.uniform(-0.2, 0.2)
            tilt_direction = random.uniform(0, math.pi * 2)
            
            # Create rotation matrices
            mat_rot_z = Matrix.Rotation(rotation_z, 4, 'Z')
            mat_rot_x = Matrix.Rotation(math.cos(tilt_direction) * tilt_angle, 4, 'X')
            mat_rot_y = Matrix.Rotation(math.sin(tilt_direction) * tilt_angle, 4, 'Y')
            mat_loc = Matrix.Translation(location)
            transform = mat_loc @ mat_rot_z @ mat_rot_x @ mat_rot_y
            
            strands.append(location)
            
            # Create instance
            instance = bpy.data.objects.new(
                name=f"Grass_Strand_{len(strands)}",
                object_data=variation
            )
            instance.matrix_world = transform
            cluster_collection.objects.link(instance)
        
        return strands

    def execute(self, context):
        """Execute the grass cluster generation"""
        try:
            # Get properties from context
            props = context.scene.grass_cluster_props
            
            # Create strand variations
            strand_variations = self.create_strand_variations(context, props)
            
            if not strand_variations:
                self.report({'ERROR'}, "Failed to create grass strand variations")
                return {'CANCELLED'}
            
            # Distribute strands
            strands = self.distribute_strands(context, props, strand_variations)
            
            if not strands:
                self.report({'ERROR'}, "Failed to distribute grass strands")
                # Clean up variations
                for mesh in strand_variations:
                    if mesh.users == 0:
                        mesh.user_clear()
                        bpy.data.meshes.remove(mesh)
                return {'CANCELLED'}
            
            # Clean up variations
            for mesh in strand_variations:
                if mesh.users == 0:
                    mesh.user_clear()
                    bpy.data.meshes.remove(mesh)
            
            self.report({'INFO'}, f"Created grass cluster with {len(strands)} strands")
            return {'FINISHED'}
            
        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Error creating grass cluster: {str(e)}\n{traceback.format_exc()}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_GrassCluster_Panel(Panel):
    """Panel for grass cluster generation"""
    bl_label = "PLANT Grass Cluster"
    bl_idname = "ZENV_PT_GrassCluster"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.grass_cluster_props

        # Grass Type
        layout.prop(props, "grass_type")
        
        # Basic Parameters
        box = layout.box()
        box.label(text="Basic Parameters:")
        box.prop(props, "radius")
        box.prop(props, "density")
        
        # Advanced Parameters
        box = layout.box()
        box.label(text="Advanced Parameters:")
        box.prop(props, "density_falloff")
        box.prop(props, "min_distance")
        box.prop(props, "intersection_checks")
        box.prop(props, "variation_seed")
        
        # Generate Button
        layout.operator("zenv.plant_grass_cluster", text="Generate Grass Cluster")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_GrassCluster_Props,
    ZENV_OT_GrassCluster,
    ZENV_PT_GrassCluster_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.grass_cluster_props = PointerProperty(type=ZENV_PG_GrassCluster_Props)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.grass_cluster_props

if __name__ == "__main__":
    register()
