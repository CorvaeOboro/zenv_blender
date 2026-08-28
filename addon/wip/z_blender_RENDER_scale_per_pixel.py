#region META
bl_info = {
    "name": 'RENDER Scale Per Pixel',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Calculate render scale based on target texel pixels per unit',
    "status": 'working',
    "approved": True,
    "group": 'Render',
    "group_prefix": 'RENDER',
    "group_order": 60,
    "addon_order": 60,
    "tags": ['render', 'scale', 'pixel', 'resolution', 'texel', 'camera'],
    "description_short": 'Calculate render scale based on target texel pixels per unit',
    "description_medium": 'Calculates render resolution from a desired texel density (pixels per Blender unit) and camera distance, or sets a target resolution. Supports perspective and orthographic cameras with optional aspect-ratio preservation.',
    "description_long": """
    RENDER SCALE PER PIXEL
    Calculates the render resolution needed to achieve a target texel density
    (pixels per Blender unit) at a given camera distance. Supports both
    perspective and orthographic cameras. Optionally maintains the existing
    aspect ratio when updating the resolution. Also provides a direct
    target-resolution setter.""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_RENDER_scale_per_pixel.png',
    "addon_image": 'zenv_blender_RENDER_scale_per_pixel.png',
    "warning": '',
    "doc_url": '',
}

#endregion
#region IMPORT
import bpy
import math
import logging
from bpy.props import FloatProperty, IntProperty, BoolProperty, PointerProperty
from bpy.types import PropertyGroup, Operator, Panel

# ``logger`` is for developer/console diagnostics only. A single
# ``StreamHandler`` is attached in ``register()`` and detached in
# ``unregister()`` (idempotent, no duplicate-stacking on reload).
# ``propagate = False`` isolates this addon from other addons' root
# loggers. User-visible messages go through ``self.report({...})``
# on the owning operator, not through the logger.
logger = logging.getLogger(__name__)
_zenv_render_scale_console_handler = None

#endregion
#region PROPS
class ZENV_PG_RenderScale(PropertyGroup):
    """Properties for the Render Scale Per Pixel addon."""
    pixels_per_unit: IntProperty(
        name="Pixels Per Unit",
        description="Desired number of pixels per Blender unit",
        default=512,
        min=1,
        max=4096
    )
    target_width: IntProperty(
        name="Target Width",
        description="Target width in pixels",
        default=2048,
        min=1,
        max=16384
    )
    target_height: IntProperty(
        name="Target Height",
        description="Target height in pixels",
        default=2048,
        min=1,
        max=16384
    )
    maintain_aspect: BoolProperty(
        name="Maintain Aspect Ratio",
        description="Maintain aspect ratio when adjusting dimensions",
        default=True
    )
    camera_distance: FloatProperty(
        name="Camera Distance",
        description="Distance from camera to subject",
        default=1.0,
        min=0.01,
        precision=3
    )

#endregion
#region UTILS
class ZENV_RenderScale_Utils:
    """Utility functions for render scale calculations."""

    # Blender's maximum render resolution (per axis).
    MAX_RESOLUTION = 65536

    @staticmethod
    def get_camera_fov(camera):
        """Get camera field of view in radians (perspective only).

        Returns ``None`` for orthographic cameras - callers should use
        :meth:`get_visible_width` instead, which handles both types.
        """
        if camera.type != 'CAMERA':
            return None

        if camera.data.type == 'PERSP':
            return camera.data.angle
        return None

    @staticmethod
    def get_visible_width(camera, distance):
        """Get the visible world-space width at the given distance.

        For perspective cameras, the visible width depends on distance
        and FOV.  For orthographic cameras, the visible width is
        ``ortho_scale`` and is independent of distance.
        """
        if camera.type != 'CAMERA':
            return None

        if camera.data.type == 'PERSP':
            fov = camera.data.angle
            return 2.0 * distance * math.tan(fov / 2.0)
        elif camera.data.type == 'ORTHO':
            # Orthographic visible width is the ortho_scale, independent
            # of distance.
            return camera.data.ortho_scale
        return None

    @staticmethod
    def calculate_render_scale(context):
        """Calculate render scale based on pixels per unit.

        Returns ``True`` on success, ``False`` on failure.
        """
        scene = context.scene
        props = scene.zenv_render_scale
        camera = scene.camera

        if not camera:
            logger.info("No active camera found")
            return False

        # Get visible width (handles both PERSP and ORTHO).
        distance = props.camera_distance
        visible_width = ZENV_RenderScale_Utils.get_visible_width(camera, distance)
        if visible_width is None:
            logger.info("Invalid camera type")
            return False

        # Calculate required resolution.
        pixels_per_unit = props.pixels_per_unit
        required_pixels = int(visible_width * pixels_per_unit)

        # Clamp to Blender's maximum render resolution.
        required_pixels = max(1, min(required_pixels, ZENV_RenderScale_Utils.MAX_RESOLUTION))

        # Update render settings.
        render = scene.render
        if props.maintain_aspect:
            # Compute aspect ratio BEFORE modifying resolution_x to avoid
            # the critical bug where the ratio was computed from the new
            # width (which kept the old height instead of scaling it).
            if render.resolution_x > 0:
                aspect_ratio = render.resolution_y / render.resolution_x
            else:
                aspect_ratio = 1.0
            render.resolution_x = required_pixels
            render.resolution_y = max(1, int(required_pixels * aspect_ratio))
        else:
            render.resolution_x = required_pixels
            render.resolution_y = required_pixels

        logger.info("Updated render resolution to %dx%d",
                     render.resolution_x, render.resolution_y)
        return True

    @staticmethod
    def update_target_resolution(context):
        """Update render resolution to match target dimensions.

        Returns ``True`` on success, ``False`` on failure.
        """
        scene = context.scene
        props = scene.zenv_render_scale
        render = scene.render

        target_w = max(1, min(props.target_width, ZENV_RenderScale_Utils.MAX_RESOLUTION))
        target_h = max(1, min(props.target_height, ZENV_RenderScale_Utils.MAX_RESOLUTION))

        if props.maintain_aspect:
            # Compute aspect ratio BEFORE modifying resolution_x.
            if render.resolution_x > 0:
                aspect_ratio = render.resolution_y / render.resolution_x
            else:
                aspect_ratio = 1.0
            render.resolution_x = target_w
            render.resolution_y = max(1, int(target_w * aspect_ratio))
        else:
            render.resolution_x = target_w
            render.resolution_y = target_h

        logger.info("Updated render resolution to %dx%d",
                     render.resolution_x, render.resolution_y)
        return True

#endregion
#region OP
class ZENV_OT_RenderScaleCalculate(Operator):
    """Calculate render scale based on pixels per unit"""
    bl_idname = "zenv.renderscale_calculate"
    bl_label = "Calculate Scale"
    bl_description = "Calculate render scale based on pixels per unit"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.camera is not None

    def execute(self, context):
        try:
            if ZENV_RenderScale_Utils.calculate_render_scale(context):
                return {'FINISHED'}
            self.report({'WARNING'}, "Could not calculate render scale")
            return {'CANCELLED'}
        except Exception as e:
            logger.error("Error calculating render scale: %s", e)
            self.report({'ERROR'}, "Calculation failed: %s" % e)
            return {'CANCELLED'}


class ZENV_OT_RenderScaleUpdateResolution(Operator):
    """Update render resolution to match target dimensions"""
    bl_idname = "zenv.renderscale_update_resolution"
    bl_label = "Update Resolution"
    bl_description = "Update render resolution to match target dimensions"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        try:
            if ZENV_RenderScale_Utils.update_target_resolution(context):
                return {'FINISHED'}
            self.report({'WARNING'}, "Could not update resolution")
            return {'CANCELLED'}
        except Exception as e:
            logger.error("Error updating resolution: %s", e)
            self.report({'ERROR'}, "Update failed: %s" % e)
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_RenderScale(Panel):
    """Panel for render scale tools"""
    bl_label = "RENDER Scale Per Pixel"
    bl_idname = "ZENV_PT_RenderScale"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.zenv_render_scale

        # Settings
        box = layout.box()
        box.label(text="Scale Settings:")
        box.prop(props, "pixels_per_unit")
        box.prop(props, "camera_distance")
        box.prop(props, "maintain_aspect")
        box.operator("zenv.renderscale_calculate")

        # Target Resolution
        box = layout.box()
        box.label(text="Target Resolution:")
        box.prop(props, "target_width")
        if not props.maintain_aspect:
            box.prop(props, "target_height")
        box.operator("zenv.renderscale_update_resolution")

        # Current Resolution
        box = layout.box()
        box.label(text="Current Resolution:")
        box.label(text="Width: %dpx" % scene.render.resolution_x)
        box.label(text="Height: %dpx" % scene.render.resolution_y)

#endregion
#region REG
classes = (
    ZENV_PG_RenderScale,
    ZENV_OT_RenderScaleCalculate,
    ZENV_OT_RenderScaleUpdateResolution,
    ZENV_PT_RenderScale,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_render_scale_console_handler
    if _zenv_render_scale_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_render_scale_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_render_scale_console_handler
    if _zenv_render_scale_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_render_scale_console_handler)
    except ValueError:
        pass
    _zenv_render_scale_console_handler = None


def register():
    """Register all addon classes, scene property, and configure the logger."""
    _install_logger()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.zenv_render_scale = PointerProperty(type=ZENV_PG_RenderScale)


def unregister():
    """Unregister all addon classes, remove scene property, and remove the logger handler."""
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "zenv_render_scale"):
        delattr(bpy.types.Scene, "zenv_render_scale")
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
