#region META
bl_info = {
    "name": 'VIEW Scale Clipping',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Adjust viewport clipping based on object size',
    "status": 'working',
    "approved": True,
    "group": 'View',
    "group_prefix": 'VIEW',
    "group_order": 70,
    "addon_order": 20,
    "tags": ['viewport', 'clipping', 'bounds', 'view fit'],
    "description_short": 'uses bounds of objects in scene to set near and far clipping',
    "description_medium": 'Adjusts viewport near/far clipping planes and view distance based on the aggregated bounding box of all scene objects.',
    "description_long": """
VIEW Scale Clipping
 adjusts viewport clipping and view settings based on object size
""",
    "location": 'View3D > Sidebar > ZENV > VIEW Scale Clipping',
    "image_overview": 'zenv_blender_VIEW_view_scale_clipping.png',
    "addon_image": 'zenv_blender_VIEW_view_scale_clipping.png',
}

#region IMPORT
import bpy
import logging
import mathutils
from bpy.types import Panel, Operator

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region OP
class ZENV_OT_ViewAutoClippingBounds(Operator):
    """Update viewport settings based on object size across all viewports"""
    bl_idname = "zenv.update_viewport"
    bl_label = "View Fit Bounds"
    bl_description = "Adjust viewport clipping to fit scene bounds in all viewports"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return bool(context.scene.objects)

    def get_object_bounds(self, obj, depsgraph):
        """Return ``(bounds_min, bounds_max)`` for ``obj`` in world space.

        The evaluated mesh from ``depsgraph`` is used so modifiers and
        shape keys are honored. Returns ``None`` when the object has no
        geometry available to sample.
        """
        if not obj:
            return None

        world_matrix = obj.matrix_world
        points = []

        if obj.type == 'MESH':
            obj_eval = obj.evaluated_get(depsgraph)
            mesh_eval = obj_eval.to_mesh()
            try:
                if mesh_eval is not None and len(mesh_eval.vertices) > 0:
                    points.extend(world_matrix @ v.co for v in mesh_eval.vertices)
            finally:
                try:
                    obj_eval.to_mesh_clear()
                except Exception:
                    pass

        elif obj.type == 'CURVE':
            # Use depsgraph evaluation so curve modifiers (bevel,
            # extrude, etc.) are honored, consistent with mesh handling.
            obj_eval = obj.evaluated_get(depsgraph)
            curve_eval = obj_eval.data
            if curve_eval is not None:
                for spline in curve_eval.splines:
                    if spline.type == 'BEZIER':
                        points.extend(world_matrix @ p.co for p in spline.bezier_points)
                    else:
                        points.extend(world_matrix @ p.co.xyz for p in spline.points)
            else:
                for spline in obj.data.splines:
                    if spline.type == 'BEZIER':
                        points.extend(world_matrix @ p.co for p in spline.bezier_points)
                    else:
                        points.extend(world_matrix @ p.co.xyz for p in spline.points)

        elif obj.type in {'EMPTY', 'CAMERA', 'LIGHT'}:
            loc = world_matrix.translation
            size = obj.empty_display_size if obj.type == 'EMPTY' else 1.0
            points.append(loc)
            points.extend([
                world_matrix @ mathutils.Vector((size, 0, 0)),
                world_matrix @ mathutils.Vector((0, size, 0)),
                world_matrix @ mathutils.Vector((0, 0, size)),
            ])

        else:
            # Fallback: use the 8 bounding-box corners transformed to
            # world space, which works for every object type Blender
            # exposes local bbox_corners on.
            try:
                points.extend(world_matrix @ mathutils.Vector(corner)
                              for corner in obj.bound_box)
            except Exception:
                points.append(world_matrix.translation)

        if not points:
            return None

        bounds_min = mathutils.Vector((
            min(p.x for p in points),
            min(p.y for p in points),
            min(p.z for p in points),
        ))
        bounds_max = mathutils.Vector((
            max(p.x for p in points),
            max(p.y for p in points),
            max(p.z for p in points),
        ))
        return bounds_min, bounds_max

    def update_viewport_settings(self, context):
        """Update viewport settings based on true scene bounds."""
        # Tuning constants.
        CLIP_START_FACTOR = 0.001   # Near clip as a fraction of scene diagonal.
        CLIP_END_FACTOR = 5.0       # Far clip as a multiple of scene diagonal.
        VIEW_LENS = 50.0

        depsgraph = context.evaluated_depsgraph_get()

        # Aggregate an overall axis-aligned bounding box across every
        # object in the current scene. 
        overall_min = None
        overall_max = None

        for obj in context.scene.objects:
            bounds = self.get_object_bounds(obj, depsgraph)
            if bounds is None:
                continue
            bmin, bmax = bounds
            if overall_min is None:
                overall_min = bmin.copy()
                overall_max = bmax.copy()
            else:
                overall_min.x = min(overall_min.x, bmin.x)
                overall_min.y = min(overall_min.y, bmin.y)
                overall_min.z = min(overall_min.z, bmin.z)
                overall_max.x = max(overall_max.x, bmax.x)
                overall_max.y = max(overall_max.y, bmax.y)
                overall_max.z = max(overall_max.z, bmax.z)

        if overall_min is None:
            return False

        extent = overall_max - overall_min
        scene_diagonal = max(extent.length, 1e-6)  # Real measure of scene size.
        bounds_center = (overall_min + overall_max) * 0.5

        clip_start = max(scene_diagonal * CLIP_START_FACTOR, 0.001)
        clip_end = scene_diagonal * CLIP_END_FACTOR
        view_distance = scene_diagonal

        # Walk every 3D viewport, but dedupe so the same space is only
        # touched once 
        processed_count = 0
        seen_spaces = set()
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                for space in area.spaces:
                    if space.type != 'VIEW_3D':
                        continue
                    if space.as_pointer() in seen_spaces:
                        continue
                    seen_spaces.add(space.as_pointer())

                    space.clip_start = clip_start
                    space.clip_end = clip_end
                    space.lens = VIEW_LENS

                    region3d = space.region_3d
                    if region3d:
                        region3d.view_distance = view_distance
                        region3d.view_location = bounds_center

                    processed_count += 1

        return processed_count
        
    def execute(self, context):
        """Execute the viewport clipping update operation."""
        try:
            # Update all viewports
            processed_count = self.update_viewport_settings(context)

            if processed_count:
                self.report({'INFO'}, f"Updated {processed_count} viewports to fit scene bounds")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No objects found to calculate bounds")
                return {'CANCELLED'}

        except Exception as e:
            logger.exception("Failed to update viewport clipping")
            self.report({'ERROR'}, f"Error updating viewport: {str(e)}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_ViewAutoClippingBounds(Panel):
    """Panel for viewport settings"""
    bl_label = "VIEW Bounds Scale"
    bl_idname = "ZENV_PT_viewport"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        layout.operator(ZENV_OT_ViewAutoClippingBounds.bl_idname)

#endregion
#region REG
classes = (
    ZENV_OT_ViewAutoClippingBounds,
    ZENV_PT_ViewAutoClippingBounds,
)

def register():
    """Register all addon classes and configure the module logger handler."""
    global _logger_handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    if _logger_handler is None:
        _logger_handler = logging.StreamHandler()
        _logger_handler.setFormatter(logging.Formatter('%(name)s: %(levelname)s: %(message)s'))
        logger.addHandler(_logger_handler)
    if not logger.level:
        logger.setLevel(logging.INFO)

def unregister():
    """Unregister all addon classes and remove the module logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if _logger_handler is not None:
        logger.removeHandler(_logger_handler)
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
