"""
MESH Noise Surface Displacement - A Blender addon for realistic surface effects.

Applies world-space 3D noise patterns using bricker-style resolution.
"""

bl_info = {
    "name": "MESH Noise Surface Displacement",
    "author": "CorvaeOboro",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Apply world-space 3D noise patterns to mesh surfaces",
    "category": "ZENV",
}

import bpy
import bmesh
from mathutils import Vector, noise
from bpy.props import FloatProperty, EnumProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup
import logging

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ZENV_NoiseDisplacementUtils:
    """Utility functions for noise displacement"""
    
    NOISE_TYPES = [
        ('WOOD_GRAIN', "Wood Grain", "Natural wood grain pattern (1-5mm depth)"),
        ('CRACKS', "Cracks", "Surface cracks and fissures (1-10mm depth)"),
        ('CHIPPED_PAINT', "Chipped Paint", "Paint chipping effect (0.1-1mm depth)"),
        ('ROCK_SURFACE', "Rock Surface", "Natural rock texture (5-50mm depth)")
    ]
    
    @staticmethod
    def get_world_matrix(obj):
        """Get the world matrix considering the entire parent hierarchy."""
        if obj.parent:
            parent_matrix = ZENV_NoiseDisplacementUtils.get_world_matrix(obj.parent)
            return parent_matrix @ obj.matrix_local
        return obj.matrix_local

    @staticmethod
    def get_mesh_bounds(bm):
        """Calculate mesh bounds in world space."""
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        return bounds_min, bounds_max

    @staticmethod
    def calculate_grid_cuts(bounds_min, bounds_max, density):
        """Calculate grid cut positions for each axis."""
        cuts = []
        for axis in range(3):
            start = density * (bounds_min[axis] // density)
            num_cuts = int((bounds_max[axis] - start) / density) + 1
            axis_cuts = [start + (i * density) for i in range(num_cuts)]
            cuts.append(axis_cuts)
        return cuts

    @staticmethod
    def get_noise_value(coord, noise_type, scale):
        """Calculate 3D noise value based on world-space coordinates."""
        world_coord = coord * scale
        
        if noise_type == 'WOOD_GRAIN':
            # Wood grain with 3D variation
            x = noise.noise(world_coord * Vector((5, 1, 5)))
            y = noise.noise(world_coord * Vector((1, 5, 1)))
            z = noise.noise(world_coord * Vector((2, 2, 5)))
            return (x * 0.5 + y * 0.3 + z * 0.2) * 0.005  # 5mm max depth
            
        elif noise_type == 'CRACKS':
            # 3D cracks with sharp edges
            x = noise.noise(world_coord * 0.5)
            y = noise.noise(world_coord * 2.0)
            z = noise.noise(world_coord * 4.0)
            return ((x * 0.6 + y * 0.3 + z * 0.1) ** 3) * 0.01  # 10mm max depth
            
        elif noise_type == 'CHIPPED_PAINT':
            # Layered paint chipping
            base = noise.noise(world_coord * 2)
            detail = noise.noise(world_coord * 4)
            sharp = noise.noise(world_coord * 8)
            return (base * 0.4 + detail * 0.4 + sharp ** 4 * 0.2) * 0.001  # 1mm max depth
            
        elif noise_type == 'ROCK_SURFACE':
            # Natural rock formations
            large = noise.noise(world_coord * 0.2)
            medium = noise.noise(world_coord * 1.0)
            small = noise.noise(world_coord * 5.0)
            return (large * 0.5 + medium * 0.3 + small * 0.2) * 0.05  # 50mm max depth
            
        return 0

class ZENV_PG_NoiseDisplaceProps(PropertyGroup):
    """Properties for noise displacement"""
    scale: FloatProperty(
        name="Pattern Scale",
        description="Scale of the noise pattern (smaller = more detail)",
        default=1.0,
        min=0.1,
        max=10.0,
        subtype='DISTANCE'
    )
    
    strength: FloatProperty(
        name="Effect Strength",
        description="Multiplier for displacement depth",
        default=1.0,
        min=0.0,
        max=20.0,
        precision=3
    )
    
    grid_density: FloatProperty(
        name="Grid Density",
        description="World-space grid density in meters (smaller = more detail)",
        default=0.01,  # 1cm default
        min=0.001,
        max=1.0,
        precision=3,
        subtype='DISTANCE'
    )
    
    noise_type: EnumProperty(
        name="Surface Effect",
        description="Choose a surface effect preset",
        items=ZENV_NoiseDisplacementUtils.NOISE_TYPES
    )
    
    use_normal: BoolProperty(
        name="Use Normal",
        description="Displace along vertex normals for more natural effect",
        default=True
    )

class ZENV_OT_NoiseDisplace(Operator):
    """Apply realistic surface effects using world-space 3D noise"""
    bl_idname = "zenv.noise_displace"
    bl_label = "Apply Effect"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Please select a mesh object")
                return {'CANCELLED'}
            
            props = context.scene.zenv_noise_props
            
            # Store original mode and ensure object mode
            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Apply scale to ensure proper cutting
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            
            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            
            # Get world matrix and bounds
            world_matrix = ZENV_NoiseDisplacementUtils.get_world_matrix(obj)
            bounds_min, bounds_max = ZENV_NoiseDisplacementUtils.get_mesh_bounds(bm)
            
            # Calculate grid cuts
            cuts = ZENV_NoiseDisplacementUtils.calculate_grid_cuts(
                bounds_min, bounds_max, props.grid_density
            )
            
            # Perform cuts for each axis
            for axis in range(3):
                for cut_pos in cuts[axis]:
                    plane_co = Vector([cut_pos if i == axis else 0 for i in range(3)])
                    plane_no = Vector([1 if i == axis else 0 for i in range(3)])
                    
                    try:
                        bmesh.ops.bisect_plane(
                            bm,
                            geom=bm.edges[:] + bm.faces[:],
                            dist=0.0001,
                            plane_co=plane_co,
                            plane_no=plane_no
                        )
                    except Exception as e:
                        logger.error(f"Error during cut: {str(e)}")
            
            # Apply noise displacement
            for vert in bm.verts:
                # Get world space position
                world_pos = world_matrix @ vert.co
                
                # Calculate noise value
                noise_val = ZENV_NoiseDisplacementUtils.get_noise_value(
                    world_pos, props.noise_type, props.scale
                )
                
                # Apply displacement
                displacement = (
                    vert.normal if props.use_normal else Vector((0, 0, 1))
                ) * noise_val * props.strength
                
                vert.co += displacement
            
            # Update mesh
            bm.to_mesh(obj.data)
            bm.free()
            
            # Restore original mode
            bpy.ops.object.mode_set(mode=original_mode)
            
            self.report({'INFO'}, "Successfully applied surface effect")
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Error applying surface effect: {str(e)}")
            self.report({'ERROR'}, f"Failed to apply surface effect: {str(e)}")
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

class ZENV_PT_NoiseDisplacePanel(Panel):
    """Panel for surface effect settings"""
    bl_label = "Surface Effects"
    bl_idname = "ZENV_PT_noise_displace"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_noise_props
        
        box = layout.box()
        box.label(text="Effect Settings:", icon='TEXTURE')
        
        col = box.column(align=True)
        col.prop(props, "noise_type")
        col.prop(props, "scale")
        col.prop(props, "strength")
        
        box = layout.box()
        box.label(text="Grid Settings:", icon='MESH_GRID')
        col = box.column(align=True)
        col.prop(props, "grid_density")
        col.prop(props, "use_normal")
        
        box.operator(ZENV_OT_NoiseDisplace.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_NoiseDisplaceProps,
    ZENV_OT_NoiseDisplace,
    ZENV_PT_NoiseDisplacePanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_noise_props = bpy.props.PointerProperty(
        type=ZENV_PG_NoiseDisplaceProps
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_noise_props

if __name__ == "__main__":
    register()
