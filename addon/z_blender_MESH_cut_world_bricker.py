# MESH Cut World Bricker
# Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini.

bl_info = {
    "name": "MESH Cut World Bricker",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini",
}

import bpy
import bmesh
from mathutils import Vector
import logging
from typing import List, Tuple, Optional

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_MeshBricker_Cut(bpy.types.Operator):
    """Cut mesh into grid pattern based on world units"""
    bl_idname = "zenv.mesh_bricker_cut"
    bl_label = "Brick Mesh"
    bl_description = "Cut mesh by world unit grid"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if operator can be executed"""
        return (context.active_object and 
                context.active_object.type == 'MESH' and 
                not context.active_object.hide_viewport)

    def get_mesh_bounds(self, bm: bmesh.types.BMesh) -> Tuple[Vector, Vector]:
        """Calculate mesh bounds in world space
        
        Args:
            bm: BMesh object to analyze
            
        Returns:
            Tuple of Vector(min_x, min_y, min_z), Vector(max_x, max_y, max_z)
        """
        bounds_min = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        bounds_max = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        return bounds_min, bounds_max

    def calculate_grid_cuts(self, bounds_min: Vector, bounds_max: Vector, density: float) -> List[List[float]]:
        """Calculate grid cut positions for each axis
        
        Args:
            bounds_min: Minimum bounds vector
            bounds_max: Maximum bounds vector
            density: Grid density in Blender units
            
        Returns:
            List of cut positions for each axis [x_cuts, y_cuts, z_cuts]
        """
        cuts = []
        for axis in range(3):
            start = density * (bounds_min[axis] // density)
            num_cuts = int((bounds_max[axis] - start) / density) + 1
            axis_cuts = [start + (i * density) for i in range(num_cuts)]
            cuts.append(axis_cuts)
        return cuts

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Please select a mesh object")
                return {'CANCELLED'}
            
            logger.info(f"Starting mesh bricking for object: {obj.name}")
            
            # Store active object and mode
            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Apply scale to ensure proper cutting
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            
            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            
            # Get bounds and calculate cuts
            bounds_min, bounds_max = self.get_mesh_bounds(bm)
            density = context.scene.zenv_bricker_density
            cuts = self.calculate_grid_cuts(bounds_min, bounds_max, density)
            
            logger.info(f"Cutting mesh with density: {density}")
            logger.info(f"Bounds: min={bounds_min}, max={bounds_max}")
            
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
                        logger.error(f"Error during cut at axis {axis}, position {cut_pos}: {str(e)}")
            
            # Apply changes and cleanup
            bm.to_mesh(obj.data)
            bm.free()
            
            # Restore original mode
            bpy.ops.object.mode_set(mode=original_mode)
            
            logger.info("Mesh bricking completed successfully")
            self.report({'INFO'}, f"Successfully bricked mesh with {sum(len(c) for c in cuts)} cuts")
            
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Error during mesh bricking: {str(e)}")
            self.report({'ERROR'}, f"Failed to brick mesh: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_MeshBricker_Panel(bpy.types.Panel):
    """Panel for world bricker mesh cutting tools"""
    bl_label = "MESH Cut World Bricker"
    bl_idname = "ZENV_PT_cut_world_bricker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel UI"""
        layout = self.layout
        box = layout.box()
        box.label(text="Grid Settings", icon='MESH_GRID')
        box.prop(context.scene, "zenv_bricker_density")
        
        # Add operator with proper icon
        op_box = layout.box()
        op_box.label(text="Operations", icon='MOD_BOOLEAN')
        row = op_box.row(align=True)
        row.operator(ZENV_OT_MeshBricker_Cut.bl_idname, icon='MOD_BEVEL')

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_MeshBricker_Cut,
    ZENV_PT_MeshBricker_Panel,
)

def register():
    """Register the addon"""
    # Register property
    bpy.types.Scene.zenv_bricker_density = bpy.props.FloatProperty(
        name="Bricker Density",
        description="Density for mesh bricking, in Blender units (1 = 1 meter)",
        default=0.01,  # 1cm default
        min=0.001,     # 1mm minimum
        max=1.0,       # 1m maximum
        precision=3,
        subtype='DISTANCE'
    )
    
    # Register classes
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    logger.info("Mesh Bricker registered successfully")

def unregister():
    """Unregister the addon"""
    # Unregister classes
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    
    # Unregister property
    del bpy.types.Scene.zenv_bricker_density
    logger.info("Mesh Bricker unregistered")

if __name__ == "__main__":
    register()
