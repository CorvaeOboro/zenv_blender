"""
ROCK BASALT GENERATOR
Generates stylized sharp rock meshes with tiered extrusions and directional bias
"""

bl_info = {
    "name": "GEN Rock Basalt Generator",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV > GEN Rock Basalt",
    "description": "Generate sharp, angular basalt rock formations",
    "category": "ZENV",
}

__addon_enabled__ = True

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix, noise
from bpy.props import FloatProperty, IntProperty, PointerProperty, BoolProperty, EnumProperty, FloatVectorProperty
from bpy.types import PropertyGroup, Operator, Panel

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_RockBasaltProperties(PropertyGroup):
    """Properties for the Rock Basalt Generator"""
    # Base Shape Properties
    base_width: FloatProperty(
        name="Base Width",
        description="Width of the base rock shape",
        default=1.0,
        min=0.1,
        max=10.0
    )
    base_length: FloatProperty(
        name="Base Length",
        description="Length of the base rock shape",
        default=1.0,
        min=0.1,
        max=10.0
    )
    max_height: FloatProperty(
        name="Max Height",
        description="Maximum height of the rock",
        default=2.0,
        min=0.1,
        max=10.0
    )
    
    # Pattern Properties
    pattern_scale: FloatProperty(
        name="Pattern Scale",
        description="Scale of the base pattern",
        default=1.0,
        min=0.1,
        max=5.0
    )
    bias_angle: FloatProperty(
        name="Bias Angle",
        description="Angle of directional bias in degrees",
        default=45.0,
        min=0.0,
        max=360.0
    )
    bias_strength: FloatProperty(
        name="Bias Strength",
        description="Strength of directional bias",
        default=0.5,
        min=0.0,
        max=1.0
    )
    edge_sharpness: FloatProperty(
        name="Edge Sharpness",
        description="Sharpness of the rock edges",
        default=0.5,
        min=0.0,
        max=1.0
    )
    noise_detail: FloatProperty(
        name="Noise Detail",
        description="Detail level of the 3D noise",
        default=2.0,
        min=0.1,
        max=5.0
    )
    noise_roughness: FloatProperty(
        name="Noise Roughness",
        description="Roughness of the 3D noise",
        default=0.5,
        min=0.0,
        max=1.0
    )
    noise_strength: FloatProperty(
        name="Noise Strength",
        description="Strength of the 3D noise displacement",
        default=0.3,
        min=0.0,
        max=1.0
    )
    fracture_density: FloatProperty(
        name="Fracture Density",
        description="Number of fracture points per meter in world space",
        default=10.0,
        min=1.0,
        max=20.0,
        subtype='NONE',
        unit='NONE'
    )
    
    # Debug Properties - Each step includes all previous steps
    enable_fracture: BoolProperty(
        name="Enable Fracturing",
        description="Apply fracturing to the base grid",
        default=True
    )
    enable_extrusion: BoolProperty(
        name="Enable Extrusion",
        description="Extrude faces with height variation",
        default=True
    )
    enable_noise: BoolProperty(
        name="Enable Noise",
        description="Apply 3D noise to the surface",
        default=True
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_RockBasaltAdd(Operator):
    """Create a new stylized rock basalt"""
    bl_idname = "zenv.rock_basalt_add"
    bl_label = "Add Rock Basalt"
    bl_options = {'REGISTER', 'UNDO'}

    def create_base_mesh(self, context, props):
        """Create a sharp, angular basalt rock mesh using fractured base shape and extrusion"""
        bm = bmesh.new()
        
        # Step 1: Create base grid
        mesh = self.create_base_grid(bm, props)
        if not props.enable_fracture:
            return self.finalize_mesh(context, bm, mesh)
        
        # Step 2: Apply fracturing
        self.apply_fracturing(bm, props)
        if not props.enable_extrusion:
            return self.finalize_mesh(context, bm, mesh)
        
        # Step 3: Extrude faces
        self.apply_extrusion(bm, props)
        if not props.enable_noise:
            return self.finalize_mesh(context, bm, mesh)
        
        # Step 4: Apply noise
        self.apply_noise(bm, props)
        
        return self.finalize_mesh(context, bm, mesh)
    
    def create_base_grid(self, bm, props):
        """Create initial grid of vertices and faces"""
        grid_size = 6
        cell_size = props.base_width / grid_size
        base_verts = []
        
        # Create vertices
        for i in range(grid_size + 1):
            row_verts = []
            for j in range(grid_size + 1):
                x_base = (i - grid_size/2) * cell_size
                y_base = (j - grid_size/2) * cell_size
                
                noise_scale = 2.0
                offset = noise.noise(Vector((x_base * noise_scale, y_base * noise_scale, 0)))
                x = x_base + offset * cell_size * 0.3
                y = y_base + offset * cell_size * 0.3
                
                vert = bm.verts.new((x, y, 0))
                row_verts.append(vert)
            base_verts.append(row_verts)
        
        # Create faces
        for i in range(grid_size):
            for j in range(grid_size):
                bm.faces.new((
                    base_verts[i][j],
                    base_verts[i][j+1],
                    base_verts[i+1][j+1],
                    base_verts[i+1][j]
                ))
        
        return bpy.data.meshes.new("ZENV_Rock_Basalt")
    
    def apply_fracturing(self, bm, props):
        """Apply fracture patterns to the mesh based on world-space density"""
        # Calculate area in square meters and target number of points
        area = props.base_width * props.base_length
        points_per_meter = props.fracture_density
        base_points = int(area * points_per_meter)
        
        # Create fracture points in concentric rings
        fracture_points = []
        
        # Calculate number of rings based on area, but keep it reasonable
        ring_count = max(2, min(4, int(math.sqrt(base_points) / 2)))
        points_per_ring = [max(4, int(base_points / ring_count * (i + 1) / ring_count)) 
                          for i in range(ring_count)]
        
        # Calculate ring radii based on base shape
        max_radius = min(props.base_width, props.base_length) * 0.45
        ring_radii = [max_radius * (i + 1) / ring_count for i in range(ring_count)]
        
        # Add ring points
        for ring_idx in range(ring_count):
            radius = ring_radii[ring_idx]
            num_points = min(points_per_ring[ring_idx], 8)  # Cap points per ring
            
            for i in range(num_points):
                # Add controlled randomness to angle and radius
                angle = (2 * math.pi * i / num_points) + random.uniform(-0.2, 0.2)
                r = radius * random.uniform(0.8, 1.2)
                x = math.cos(angle) * r
                y = math.sin(angle) * r
                fracture_points.append((x, y))
        
        # Add random interior points based on remaining density
        interior_points = max(3, min(6, int(base_points * 0.3)))  # Keep interior points reasonable
        for _ in range(interior_points):
            # Use random point within ellipse
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(0, max_radius * 0.8)  # Keep within 80% of max radius
            x = math.cos(angle) * r * (props.base_width / props.base_length)
            y = math.sin(angle) * r
            fracture_points.append((x, y))
        
        # Create fracture lines between nearby points
        for i, point1 in enumerate(fracture_points):
            # Find nearest points using spatial relationship
            distances = [(j, math.sqrt((p[0]-point1[0])**2 + (p[1]-point1[1])**2)) 
                        for j, p in enumerate(fracture_points) if p != point1]
            distances.sort(key=lambda x: x[1])
            
            # Connect to 2-3 nearest points only
            connections = random.randint(2, 3)
            for j_dist in distances[:connections]:
                j, dist = j_dist  # Unpack the tuple correctly
                if dist > max_radius * 0.7:  # Skip if points are too far apart
                    continue
                    
                point2 = fracture_points[j]
                
                # Create fracture line with controlled randomization
                mid_x = (point1[0] + point2[0])/2
                mid_y = (point1[1] + point2[1])/2
                
                # Calculate perpendicular offset for interesting fracture lines
                dir_x = point2[0] - point1[0]
                dir_y = point2[1] - point1[1]
                length = math.sqrt(dir_x**2 + dir_y**2)
                
                if length > 0:
                    # Create perpendicular vector for offset
                    perp_x = -dir_y/length
                    perp_y = dir_x/length
                    
                    # Scale offset based on world-space size but keep it subtle
                    offset_scale = random.uniform(-0.2, 0.2) * props.base_width/8
                    mid_x += perp_x * offset_scale
                    mid_y += perp_y * offset_scale
                    
                    # Only bisect if within base shape bounds
                    if math.sqrt(mid_x**2 + mid_y**2) < min(props.base_width, props.base_length) * 0.6:
                        bmesh.ops.bisect_plane(
                            bm,
                            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                            plane_co=(mid_x, mid_y, 0),
                            plane_no=(perp_x, perp_y, 0),
                            clear_outer=False,
                            clear_inner=False
                        )

    def apply_extrusion(self, bm, props):
        """Extrude faces with height variation"""
        for face in bm.faces[:]:
            center = face.calc_center_median()
            
            dist = math.sqrt(center.x**2 + center.y**2) / (props.base_width * 0.5)
            falloff = max(0, 1 - dist**1.5)
            
            noise_val = noise.noise(Vector((
                center.x * props.pattern_scale * 0.5,
                center.y * props.pattern_scale * 0.5,
                0
            )))
            base_height = props.max_height * (falloff + noise_val * 0.2)
            
            bias_angle_rad = math.radians(props.bias_angle)
            bias = (center.x * math.cos(bias_angle_rad) + 
                   center.y * math.sin(bias_angle_rad)) * props.bias_strength
            
            height = base_height * (1 + bias) * random.uniform(0.9, 1.1)
            
            normal = face.normal.copy()
            normal.x += random.uniform(-0.15, 0.15) * props.edge_sharpness
            normal.y += random.uniform(-0.15, 0.15) * props.edge_sharpness
            normal.z = max(0.7, normal.z)
            normal.normalize()
            
            ret = bmesh.ops.extrude_face_region(bm, geom=[face])
            extruded_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
            
            bmesh.ops.translate(
                bm,
                vec=normal * height,
                verts=extruded_verts
            )
    
    def apply_noise(self, bm, props):
        """Apply 3D noise to the mesh surface"""
        for vert in bm.verts:
            pos = vert.co * props.pattern_scale
            detail = props.noise_detail
            roughness = props.noise_roughness
            
            noise_val = noise.noise(pos)
            
            amplitude = 1.0
            frequency = 1.0
            max_val = 0
            
            for _ in range(int(detail)):
                noise_val += noise.noise(pos * frequency) * amplitude
                max_val += amplitude
                amplitude *= roughness
                frequency *= 2.0
            
            noise_val /= max_val
            displacement = vert.normal * noise_val * props.noise_strength
            vert.co += displacement
    
    def finalize_mesh(self, context, bm, mesh):
        """Create the final mesh object"""
        bm.to_mesh(mesh)
        bm.free()
        
        rock_obj = bpy.data.objects.new("ZENV_Rock_Basalt", mesh)
        context.collection.objects.link(rock_obj)
        
        return rock_obj

    def create_material(self, obj, props):
        """Create material for the rock with sharp, angular characteristics"""
        mat = bpy.data.materials.new(name="GEN_Rock_Basalt_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        bump = nodes.new('ShaderNodeBump')
        noise_tex = nodes.new('ShaderNodeTexNoise')
        voronoi = nodes.new('ShaderNodeTexVoronoi')
        mapping = nodes.new('ShaderNodeMapping')
        tex_coord = nodes.new('ShaderNodeTexCoord')
        color_ramp = nodes.new('ShaderNodeValToRGB')
        mix_rgb = nodes.new('ShaderNodeMixRGB')
        
        # Set node locations for organization
        output.location = (300, 0)
        principled.location = (0, 0)
        bump.location = (-200, -200)
        noise_tex.location = (-600, -200)
        voronoi.location = (-600, 100)
        mapping.location = (-800, 0)
        tex_coord.location = (-1000, 0)
        color_ramp.location = (-400, 100)
        mix_rgb.location = (-200, 100)
        
        # Set up basic material properties
        principled.inputs['Base Color'].default_value = (0.02, 0.02, 0.02, 1)  # Dark basalt color
        principled.inputs['Metallic'].default_value = 0.0
        principled.inputs['Specular IOR Level'].default_value = 0.5
        principled.inputs['Roughness'].default_value = 0.8
        
        # Configure noise texture for micro-detail
        noise_tex.inputs['Scale'].default_value = 20.0
        noise_tex.inputs['Detail'].default_value = 15.0
        noise_tex.inputs['Roughness'].default_value = 0.7
        
        # Configure Voronoi for crystalline structure
        voronoi.inputs['Scale'].default_value = 5.0
        voronoi.feature = 'DISTANCE_TO_EDGE'
        voronoi.distance = 'MANHATTAN'
        
        # Configure color ramp for sharp transitions
        color_ramp.color_ramp.elements[0].position = 0.4
        color_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
        color_ramp.color_ramp.elements[1].position = 0.6
        color_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
        
        # Configure bump settings
        bump.inputs['Strength'].default_value = 1.0
        bump.inputs['Distance'].default_value = 0.02
        
        # Configure mapping for directional detail
        mapping.inputs['Scale'].default_value[0] = 1.0
        mapping.inputs['Scale'].default_value[1] = 1.0
        mapping.inputs['Scale'].default_value[2] = 1.0
        
        # Mix noise and voronoi for complex surface detail
        mix_rgb.blend_type = 'MULTIPLY'
        mix_rgb.inputs['Fac'].default_value = 0.7
        
        # Link nodes
        links = mat.node_tree.links
        links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], noise_tex.inputs['Vector'])
        links.new(mapping.outputs['Vector'], voronoi.inputs['Vector'])
        links.new(voronoi.outputs['Distance'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], mix_rgb.inputs[1])
        links.new(noise_tex.outputs['Fac'], mix_rgb.inputs[2])
        links.new(mix_rgb.outputs['Color'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], principled.inputs['Normal'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        # Apply material to object
        obj.data.materials.append(mat)

    def execute(self, context):
        props = context.scene.zenv_rock_basalt_props
        
        # Create rock mesh
        rock_obj = self.create_base_mesh(context, props)
        
        # Set active object
        context.view_layer.objects.active = rock_obj
        rock_obj.select_set(True)
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RockBasaltPanel(Panel):
    """Panel for Rock Basalt Generator"""
    bl_label = "GEN Rock Basalt Generator"
    bl_idname = "ZENV_PT_rock_basalt"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_rock_basalt_props
        
        # Base properties
        box = layout.box()
        box.label(text="Base Properties:")
        box.prop(props, "base_width")
        box.prop(props, "base_length")
        box.prop(props, "max_height")
        
        # Pattern properties
        box = layout.box()
        box.label(text="Pattern Properties:")
        box.prop(props, "pattern_scale")
        box.prop(props, "bias_angle")
        box.prop(props, "bias_strength")
        box.prop(props, "edge_sharpness")
        box.prop(props, "noise_detail")
        box.prop(props, "noise_roughness")
        box.prop(props, "noise_strength")
        box.prop(props, "fracture_density")
        
        # Debug properties
        box = layout.box()
        box.label(text="Debug Properties:")
        box.prop(props, "enable_fracture")
        box.prop(props, "enable_extrusion")
        box.prop(props, "enable_noise")
        
        # Add button
        layout.operator("zenv.rock_basalt_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_RockBasaltProperties,
    ZENV_OT_RockBasaltAdd,
    ZENV_PT_RockBasaltPanel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_rock_basalt_props = PointerProperty(type=ZENV_PG_RockBasaltProperties)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.zenv_rock_basalt_props
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

def menu_func(self, context):
    """Add menu item to Add Mesh menu"""
    self.layout.operator("zenv.rock_basalt_add", text="GEN Rock Basalt")

if __name__ == "__main__":
    register()
