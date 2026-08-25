#region META
bl_info = {
    "name": 'MESH Cut World Bricker',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini',
    "status": 'working',
    "approved": True,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 20,
    "addon_order": 70,
    "tags": ['mesh', 'cut', 'bricker', 'grid', 'bisect', 'slice'],
    "description_short": 'Cut mesh into brick like segments',
    "description_medium": 'Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini',
    "description_long": """
MESH Cut World Bricker
 Cut mesh by grid of world unit size, 1 per centimeter, similar to Bricker in Houdini.
""",
    "image_overview": 'zenv_blender_MESH_cut_world_bricker.png',
    "addon_image": 'zenv_blender_MESH_cut_world_bricker.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import bmesh
import time
from mathutils import Vector
import logging
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)
_zenv_bricker_console_handler = None
#endregion


#region UTILS
# Utility class with estimation, formatting, and bounding-box helpers.

class ZENV_MeshBricker_Utils:
    """Static utility methods and tuning constants for the bricker addon."""

    # these are estimates from slicing cube , it varies based on existing mesh density
    MS_PER_CELL = 0.002
    WARN_CELLS = 5_000_000
    DANGER_CELLS = 10_000_000

    @staticmethod
    def get_target_objects(context) -> List[bpy.types.Object]:
        """Return the mesh objects the operator will act on (active object).

        The operator only acts on the active mesh; selected mesh objects are
        used as a fallback when there is no valid active mesh, so the bbox
        preview still works in that case.
        """
        objs: List[bpy.types.Object] = []
        act = context.active_object
        if act and act.type == 'MESH' and not act.hide_viewport:
            objs.append(act)
        else:
            for o in context.selected_objects:
                if o.type == 'MESH' and not o.hide_viewport:
                    objs.append(o)
        return objs

    @staticmethod
    def world_bounds(objs: List[bpy.types.Object]) -> Tuple[Optional[Vector], Optional[Vector]]:
        """Compute combined world-space bounding box from object bound_box corners."""
        if not objs:
            return None, None
        mins = [float('inf')] * 3
        maxs = [float('-inf')] * 3
        for obj in objs:
            for corner in obj.bound_box:
                wc = obj.matrix_world @ Vector(corner)
                for i in range(3):
                    if wc[i] < mins[i]:
                        mins[i] = wc[i]
                    if wc[i] > maxs[i]:
                        maxs[i] = wc[i]
        return Vector(mins), Vector(maxs)

    @classmethod
    def estimate(cls, context) -> Optional[Dict[str, Any]]:
        """Estimate cut counts, cell counts and processing time for the current selection.

        Returns a dict with keys: size, nx, ny, nz, total_cuts, cells, est_seconds,
        severity ('ok'|'warn'|'danger'), or None if no valid target.
        """
        objs = cls.get_target_objects(context)
        bmin, bmax = cls.world_bounds(objs)
        if bmin is None:
            return None
        density = context.scene.zenv_bricker_density
        if density <= 0.0:
            return None

        size = bmax - bmin
        # Number of cut planes along each axis covering the bbox at the given density
        nx = max(0, int(size.x / density) + 1)
        ny = max(0, int(size.y / density) + 1)
        nz = max(0, int(size.z / density) + 1)
        total_cuts = nx + ny + nz
        # Resulting cell count is the dominant cost driver for sequential bisects
        cells = max(1, nx) * max(1, ny) * max(1, nz)

        est_seconds = (cells * cls.MS_PER_CELL) / 1000.0

        if cells >= cls.DANGER_CELLS:
            severity = 'danger'
        elif cells >= cls.WARN_CELLS:
            severity = 'warn'
        else:
            severity = 'ok'

        return {
            'objects': [o.name for o in objs],
            'size': size,
            'nx': nx, 'ny': ny, 'nz': nz,
            'total_cuts': total_cuts,
            'cells': cells,
            'est_seconds': est_seconds,
            'severity': severity,
        }

    @staticmethod
    def format_time(seconds: float) -> str:
        if seconds < 1.0:
            return f"{seconds * 1000.0:.0f} ms"
        if seconds < 60.0:
            return f"{seconds:.1f} s"
        if seconds < 3600.0:
            return f"{seconds / 60.0:.1f} min"
        return f"{seconds / 3600.0:.2f} h"

    @staticmethod
    def format_count(n: int) -> str:
        """Format a large integer as a short 3-digit string with a magnitude suffix.

        Examples: 466_000 -> '466K', 8_000_000 -> '8.00M', 1_234 -> '1.23K', 42 -> '42'.
        """
        n = int(n)
        if n < 1_000:
            return str(n)
        for suffix, scale in (('B', 1_000_000_000), ('M', 1_000_000), ('K', 1_000)):
            if n >= scale:
                v = n / scale
                if v >= 100:
                    return f"{v:.0f}{suffix}"
                if v >= 10:
                    return f"{v:.1f}{suffix}"
                return f"{v:.2f}{suffix}"
        return str(n)


#region OP
# Operator that cuts the active mesh along a world-space grid.

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
        import numpy as np
        coords = np.array([v.co[:] for v in bm.verts])
        bounds_min = Vector(coords.min(axis=0))
        bounds_max = Vector(coords.max(axis=0))
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
            # Generate cuts from start up to and including bounds_max,
            # but not beyond. The +1 ensures we include the boundary
            # cut if it falls exactly on bounds_max.
            num_cuts = int((bounds_max[axis] - start) / density) + 1
            axis_cuts = [start + (i * density) for i in range(num_cuts)
                         if start + (i * density) <= bounds_max[axis] + density * 0.5]
            cuts.append(axis_cuts)
        return cuts

    def invoke(self, context, event):
        """Show a confirmation dialog when the estimated workload is in the danger zone."""
        info = ZENV_MeshBricker_Utils.estimate(context)
        if info is not None:
            logger.info(
                "Bricker pre-run estimate: cuts X=%d Y=%d Z=%d (total=%d), cells=%d, est=%s, severity=%s",
                info['nx'], info['ny'], info['nz'], info['total_cuts'],
                info['cells'], ZENV_MeshBricker_Utils.format_time(info['est_seconds']),
                info['severity'],
            )
            if info['severity'] == 'danger':
                return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Please select a mesh object")
                return {'CANCELLED'}

            pre_estimate = ZENV_MeshBricker_Utils.estimate(context)
            logger.info(f"Starting mesh bricking for object: {obj.name}")

            t_start = time.perf_counter()

            # Store active object and mode
            original_mode = obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Apply scale to ensure proper cutting
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            bm = bmesh.new()
            try:
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

                # Apply changes
                bm.to_mesh(obj.data)
            finally:
                bm.free()

            # Restore original mode
            bpy.ops.object.mode_set(mode=original_mode)

            elapsed = time.perf_counter() - t_start
            total_cuts = sum(len(c) for c in cuts)
            nx_a = max(1, len(cuts[0]))
            ny_a = max(1, len(cuts[1]))
            nz_a = max(1, len(cuts[2]))
            cells_a = nx_a * ny_a * nz_a
            ms_per_cell_actual = (elapsed * 1000.0) / max(1, cells_a)

            logger.info("=" * 60)
            logger.info("Mesh bricking COMPLETED")
            logger.info(
                "  Object: %s | cuts X=%d Y=%d Z=%d (total=%d) | cells=%d",
                obj.name, len(cuts[0]), len(cuts[1]), len(cuts[2]), total_cuts, cells_a,
            )
            logger.info(
                "  Elapsed: %s (%.3fs) | actual ms/cell = %.5f",
                ZENV_MeshBricker_Utils.format_time(elapsed), elapsed, ms_per_cell_actual,
            )
            if pre_estimate is not None:
                est_s = pre_estimate['est_seconds']
                ratio = (elapsed / est_s) if est_s > 0 else float('inf')
                logger.info(
                    "  Pre-run estimate: %s | actual/est ratio = %.2fx",
                    ZENV_MeshBricker_Utils.format_time(est_s), ratio,
                )
            logger.info(
                "  Tip: to refine the estimate, edit ZENV_MeshBricker_Utils.MS_PER_CELL = %.5f",
                ms_per_cell_actual,
            )
            logger.info("=" * 60)

            self.report(
                {'INFO'},
                f"Bricked '{obj.name}': {total_cuts} cuts, "
                f"{ZENV_MeshBricker_Utils.format_count(cells_a)} cells "
                f"in {ZENV_MeshBricker_Utils.format_time(elapsed)}",
            )

            return {'FINISHED'}

        except Exception as e:
            logger.error(f"Error during mesh bricking: {str(e)}")
            self.report({'ERROR'}, f"Failed to brick mesh: {str(e)}")
            return {'CANCELLED'}

#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_MeshBricker(bpy.types.Panel):
    """Panel for world bricker mesh cutting tools"""
    bl_label = "MESH Cut World Bricker"
    bl_idname = "ZENV_PT_cut_world_bricker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel UI"""
        layout = self.layout
        layout.prop(context.scene, "zenv_bricker_density")

        info = ZENV_MeshBricker_Utils.estimate(context)
        if info is not None:
            col = layout.column(align=True)
            col.label(text=f"Cuts: {info['total_cuts']}", icon='MOD_BEVEL')
            sev = info['severity']
            row = col.row()
            if sev == 'danger':
                row.alert = True
                row.label(
                    text=f"Cells: {ZENV_MeshBricker_Utils.format_count(info['cells'])}  (DANGER)",
                    icon='ERROR',
                )
            elif sev == 'warn':
                row.label(
                    text=f"Cells: {ZENV_MeshBricker_Utils.format_count(info['cells'])}  (heavy)",
                    icon='ERROR',
                )
            else:
                row.label(
                    text=f"Cells: {ZENV_MeshBricker_Utils.format_count(info['cells'])}",
                    icon='MESH_GRID',
                )
            col.label(
                text=f"Est: {ZENV_MeshBricker_Utils.format_time(info['est_seconds'])}",
                icon='TIME',
            )

        run_row = layout.row(align=True)
        if info is not None and info['severity'] == 'danger':
            run_row.alert = True
        run_row.operator(ZENV_OT_MeshBricker_Cut.bl_idname, icon='MOD_BEVEL')

#region REG
classes = (
    ZENV_OT_MeshBricker_Cut,
    ZENV_PT_MeshBricker,
)

def register():
    """Register the addon"""
    global _zenv_bricker_console_handler
    if _zenv_bricker_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_bricker_console_handler = handler
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
    global _zenv_bricker_console_handler
    # Unregister classes
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

    # Unregister property
    if hasattr(bpy.types.Scene, "zenv_bricker_density"):
        del bpy.types.Scene.zenv_bricker_density
    logger.info("Mesh Bricker unregistered")
    if _zenv_bricker_console_handler is not None:
        try:
            logger.removeHandler(_zenv_bricker_console_handler)
        except ValueError:
            pass
        _zenv_bricker_console_handler = None

if __name__ == "__main__":
    register()
#endregion
