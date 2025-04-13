"""
TOOTH GENERATOR
generates detailed monster teeth with realistic striations and patterns
useful for creating hyper realistic monster teeth with various types and styles
"""

bl_info = {
    "name": "GEN Tooth Generator",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV > GEN Tooth Generator",
    "description": "Generate monster teeth with  features",
}

import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, IntProperty, StringProperty, PointerProperty, BoolProperty
from bpy.types import PropertyGroup, Panel, Operator

class ZENV_OT_GenerateTooth(Operator):
    """Generate a detailed tooth mesh with realistic features"""
    bl_idname = "zenv.generate_tooth"
    bl_label = "Generate Tooth"
    bl_options = {'REGISTER', 'UNDO'}
    
    tooth_type: StringProperty(
        name="Tooth Type",
        description="Type of tooth to generate",
        default='CANINE'
    )

    def apply_molar_details(self, bm, context):
        """Add realistic molar-specific features with optimized complexity"""
        props = context.scene.tooth_generator_props
        
        # Find top face and create simpler chewing surface
        top_faces = [f for f in bm.faces if f.normal.z > 0.5]
        for face in top_faces:
            # Create 4 main cusps instead of random number
            result = bmesh.ops.subdivide_edges(
                bm,
                edges=face.edges[:],
                cuts=1
            )
            
            # Create main cusps at corners
            corner_verts = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
            for v in corner_verts:
                if v.co.z > 0:
                    # Raise corners for cusps
                    v.co.z += 0.2 * props.tooth_size
                    # Add slight inward tilt for realistic shape
                    v.co.x *= 0.9
                    v.co.y *= 0.9
            
            # Create central depression
            center_verts = [v for v in bm.verts if v.co.z > 0 and abs(v.co.x) < 0.1 and abs(v.co.y) < 0.1]
            for v in center_verts:
                v.co.z -= 0.1 * props.tooth_size

    def apply_canine_details(self, bm, context):
        """Add realistic canine-specific features with improved shape"""
        props = context.scene.tooth_generator_props
        
        # Reshape the cone for more realistic canine shape
        for v in bm.verts:
            height_ratio = (v.co.z + props.tooth_size) / (2.0 * props.tooth_size)
            
            # Create slight curve
            v.co.y += math.sin(height_ratio * math.pi) * 0.15 * props.tooth_size
            
            # Add slight twist
            angle = math.atan2(v.co.x, v.co.y)
            twist = height_ratio * math.pi * 0.1
            new_x = v.co.x * math.cos(twist) - v.co.y * math.sin(twist)
            new_y = v.co.x * math.sin(twist) + v.co.y * math.cos(twist)
            v.co.x = new_x
            v.co.y = new_y
            
            # Create ridge along the front
            if abs(angle) < 0.5:
                v.co += v.normal * 0.1 * props.tooth_size * (1 - height_ratio)
        
        # Sharpen the tip more naturally
        top_verts = [v for v in bm.verts if v.co.z > props.tooth_size * 0.8]
        for v in top_verts:
            tip_factor = (v.co.z - props.tooth_size * 0.8) / (props.tooth_size * 1.2)
            # Progressive narrowing
            v.co.x *= (1.0 - tip_factor)
            v.co.y *= (1.0 - tip_factor)
            # Slight forward lean at tip
            v.co.y += tip_factor * 0.2 * props.tooth_size

    def apply_incisor_details(self, bm, context):
        """Add realistic incisor-specific features"""
        props = context.scene.tooth_generator_props
        
        # Scale to create rectangular front face
        for v in bm.verts:
            v.co.x *= 1.5  # Make wider
            v.co.y *= 0.7  # Make thinner
        
        # Create cutting edge and front curve
        top_verts = [v for v in bm.verts if v.co.z > 0]
        for v in top_verts:
            # Create slightly curved cutting edge
            edge_curve = math.sin(v.co.x * math.pi / (1.5 * props.tooth_size)) * 0.1 * props.tooth_size
            v.co.z = props.tooth_size + edge_curve
            
            # Tilt the cutting edge forward slightly
            v.co.y += 0.2 * props.tooth_size
        
        # Create back scoop
        back_verts = [v for v in bm.verts if v.co.y > 0]
        for v in back_verts:
            # Calculate scoop depth based on height and position
            height_factor = (v.co.z + props.tooth_size) / (2.0 * props.tooth_size)
            width_factor = abs(v.co.x) / (1.5 * props.tooth_size)
            scoop = math.sin(height_factor * math.pi) * (1 - width_factor) * 0.3 * props.tooth_size
            v.co.y -= scoop

    def apply_surface_noise(self, bm, context):
        """Add realistic surface imperfections and micro-detail"""
        props = context.scene.tooth_generator_props
        
        for v in bm.verts:
            # Layered noise for more natural look
            large_noise = math.sin(v.co.x * 20) * math.cos(v.co.y * 20) * math.sin(v.co.z * 20)
            medium_noise = math.sin(v.co.x * 40) * math.cos(v.co.y * 40) * math.sin(v.co.z * 40) * 0.5
            small_noise = math.sin(v.co.x * 80) * math.cos(v.co.y * 80) * math.sin(v.co.z * 80) * 0.25
            
            combined_noise = (large_noise + medium_noise + small_noise) * props.tooth_roughness * 0.05 * props.tooth_size
            v.co += v.normal * combined_noise

    def create_base_mesh(self, context):
        """Create the basic tooth shape based on type"""
        props = context.scene.tooth_generator_props
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
        """Add realistic surface details"""
        props = context.scene.tooth_generator_props
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
                random.uniform(-1, 1),
                random.uniform(-1, 1),
                random.uniform(-1, 1)
            )) * props.tooth_roughness * 0.1 * props.tooth_size

            # Add asymmetry
            if random.random() < props.tooth_asymmetry:
                asymm = Vector((
                    random.uniform(-1, 1),
                    random.uniform(-1, 1),
                    random.uniform(-1, 1)
                )) * props.tooth_asymmetry * 0.2 * props.tooth_size
                noise += asymm

            v.co += noise

        # Add striations (vertical grooves)
        if self.tooth_type in {'CANINE'}:
            for v in bm.verts:
                angle = math.atan2(v.co.x, v.co.y)
                striation = math.sin(angle * 8) * 0.05 * props.tooth_size * props.tooth_roughness
                v.co += v.normal * striation

    def create_root(self, bm, context):
        """Create tooth root"""
        props = context.scene.tooth_generator_props
        # Find bottom faces
        bottom_faces = [f for f in bm.faces if f.normal.z < -0.5]
        
        # Extrude downward for root
        root_depth = 1.2 * props.tooth_size
        for face in bottom_faces:
            result = bmesh.ops.extrude_face_region(bm, geom=[face])
            new_faces = [f for f in result['geom'] if isinstance(f, bmesh.types.BMFace)]
            
            # Move new faces down and taper
            for f in new_faces:
                for v in f.verts:
                    v.co.z -= root_depth
                    # Taper root
                    xyscale = 0.6
                    v.co.x *= xyscale
                    v.co.y *= xyscale

    def execute(self, context):
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
        
        obj = bpy.data.objects.new("Tooth", mesh)
        context.collection.objects.link(obj)
        
        # Select and make active
        context.view_layer.objects.active = obj
        obj.select_set(True)
        
        props = context.scene.tooth_generator_props
        if props.use_voxel_remesh:
            # Add and apply remesh modifier
            mod = obj.modifiers.new(name="Remesh", type='REMESH')
            mod.mode = 'VOXEL'
            mod.voxel_size = 0.075
            context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier="Remesh")
        
        return {'FINISHED'}

class ZENV_PG_GenerateTooth_Props(PropertyGroup):
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
        description="Amount of surface detail",
        default=2,
        min=1,
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
    use_voxel_remesh: BoolProperty(
        name="Voxel Remesh",
        description="Apply voxel remesh for final mesh topology",
        default=True
    )

class ZENV_PT_GenerateTooth_Panel(Panel):
    """Panel for procedural tooth generation"""
    bl_label = "GEN Tooth Generator"
    bl_idname = "ZENV_PT_tooth_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.tooth_generator_props
        
        # Property controls
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Tooth Settings:", icon='MODIFIER')
        col.prop(props, "tooth_size")
        col.prop(props, "tooth_detail")
        col.prop(props, "tooth_roughness")
        col.prop(props, "tooth_asymmetry")
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

classes = (
    ZENV_PG_GenerateTooth_Props,
    ZENV_OT_GenerateTooth,
    ZENV_PT_GenerateTooth_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.tooth_generator_props = PointerProperty(type=ZENV_PG_GenerateTooth_Props)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.tooth_generator_props

if __name__ == "__main__":
    register()
