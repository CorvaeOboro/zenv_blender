"""
Fungus Mushroom Generator - Creates procedural mushrooms with detailed gills
"""

bl_info = {
    "name": 'PLANT Fungus Mushroom',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250413',
    "description": 'Creates  mushrooms with mesh-based geometry',
    "status": 'wip',
    "approved": True,
    "group": 'Plant',
    "group_prefix": 'PLANT',
    "location": 'View3D > ZENV',
}

import bpy
import bmesh
import math
import random
import numpy as np
from mathutils import Vector, Matrix, noise
from bpy.props import (
    FloatProperty,
    BoolProperty,
    IntProperty,
    FloatVectorProperty,
    EnumProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup

# ------------------------------------------------------------------------
#    Property Group
# ------------------------------------------------------------------------

class ZENV_PG_FungusMushProperties(PropertyGroup):
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
        default=(0.8, 0.4, 0.3),
        min=0.0,
        max=1.0
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_FungusMushAdd(Operator):
    """Create a new procedural mushroom"""
    bl_idname = "zenv.fungus_mush_add"
    bl_label = "Add Fungus Mushroom"
    bl_options = {'REGISTER', 'UNDO'}
    
    def noise3d(self, x, y, z, scale, octaves=3):
        """Generate 3D noise value"""
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        
        for _ in range(octaves):
            v = Vector((x * frequency / scale, y * frequency / scale, z * frequency / scale))
            value += noise.noise(v) * amplitude
            max_value += amplitude
            amplitude *= 0.5
            frequency *= 2.0
            
        return value / max_value

    def create_base_mesh(self, verts, faces):
        """Create base mesh from vertices and faces"""
        mesh = bpy.data.meshes.new("Mushroom_Base")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new("Mushroom", mesh)
        bpy.context.collection.objects.link(obj)
        return obj

    def generate_cap_points(self, props):
        """Generate cap vertices and faces"""
        segments = 32
        rings = 16
        verts = []
        faces = []
        
        # Generate cap vertices
        for ring in range(rings + 1):
            ring_radius = math.sin(ring * math.pi / rings) * props.cap_radius
            ring_height = math.cos(ring * math.pi / rings) * props.cap_height
            
            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                x = math.cos(angle) * ring_radius
                y = math.sin(angle) * ring_radius
                z = ring_height + props.stem_height
                
                # Apply 3D noise
                noise_value = self.noise3d(x, y, z, props.detail_scale)
                x += noise_value * props.noise_strength
                y += noise_value * props.noise_strength
                z += noise_value * props.noise_strength
                
                verts.append((x, y, z))
        
        # Generate faces
        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                
                faces.append((current, next_segment, next_ring_segment, next_ring))
        
        return verts, faces

    def generate_stem_points(self, props):
        """Generate stem vertices and faces"""
        segments = 16
        rings = 8
        verts = []
        faces = []
        
        # Generate stem vertices
        for ring in range(rings + 1):
            ring_height = ring * props.stem_height / rings
            # Vary stem radius along height
            stem_radius = props.stem_radius * (1 + 0.2 * math.sin(ring * math.pi / rings))
            
            for segment in range(segments):
                angle = segment * 2 * math.pi / segments
                x = math.cos(angle) * stem_radius
                y = math.sin(angle) * stem_radius
                z = ring_height
                
                # Apply 3D noise
                noise_value = self.noise3d(x, y, z, props.detail_scale * 0.5)
                x += noise_value * props.noise_strength * 0.5
                y += noise_value * props.noise_strength * 0.5
                
                verts.append((x, y, z))
        
        # Generate faces
        for ring in range(rings):
            for segment in range(segments):
                current = ring * segments + segment
                next_segment = ring * segments + (segment + 1) % segments
                next_ring = (ring + 1) * segments + segment
                next_ring_segment = (ring + 1) * segments + (segment + 1) % segments
                
                faces.append((current, next_segment, next_ring_segment, next_ring))
        
        return verts, faces

    def apply_voxel_remesh(self, obj, props):
        """Apply voxel remesh to ensure watertight mesh"""
        # Set object as active
        bpy.context.view_layer.objects.active = obj
        
        # Add remesh modifier
        mod = obj.modifiers.new(name="Voxel_Remesh", type='REMESH')
        mod.mode = 'VOXEL'
        mod.voxel_size = props.voxel_size
        mod.use_smooth_shade = True
        
        # Apply modifier
        bpy.ops.object.modifier_apply(modifier="Voxel_Remesh")
        
        # Add subdivision surface for smoothness
        mod = obj.modifiers.new(name="Smooth", type='SUBSURF')
        mod.levels = 2
        mod.render_levels = 3

    def create_material(self, obj, props):
        """Create material with proper nodes"""
        mat = bpy.data.materials.new(name="Mushroom_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        
        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        
        # Set material properties
        principled.inputs['Base Color'].default_value = (*props.cap_color, 1)
        principled.inputs['Roughness'].default_value = 0.6
        principled.inputs['Specular IOR Level'].default_value = 0.3
        
        # Link nodes
        links = mat.node_tree.links
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        
        obj.data.materials.append(mat)

    def execute(self, context):
        props = context.scene.fungus_props
        
        # Generate cap mesh
        cap_verts, cap_faces = self.generate_cap_points(props)
        cap_obj = self.create_base_mesh(cap_verts, cap_faces)
        
        # Generate stem mesh
        stem_verts, stem_faces = self.generate_stem_points(props)
        stem_obj = self.create_base_mesh(stem_verts, stem_faces)
        
        # Join meshes
        cap_obj.select_set(True)
        stem_obj.select_set(True)
        bpy.context.view_layer.objects.active = cap_obj
        bpy.ops.object.join()
        
        # Apply voxel remesh
        self.apply_voxel_remesh(cap_obj, props)
        
        # Create material
        self.create_material(cap_obj, props)
        
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_FungusMushPanel(Panel):
    """Panel for Fungus Mushroom Generator"""
    bl_label = "PLANT Fungus Mushroom"
    bl_idname = "ZENV_PT_fungus_mush"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.fungus_props
        
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
        
        # Color
        box = layout.box()
        box.label(text="Appearance")
        box.prop(props, "cap_color")
        
        # Generate button
        layout.operator("zenv.fungus_mush_add")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_FungusMushProperties,
    ZENV_OT_FungusMushAdd,
    ZENV_PT_FungusMushPanel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.fungus_props = PointerProperty(type=ZENV_PG_FungusMushProperties)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.fungus_props

if __name__ == "__main__":
    register()
