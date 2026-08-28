#region blinfo
bl_info = {
    "name": 'RENDER Plane Projection',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Custom raytrace renderer using a plane as the image plane',
    "status": 'wip',
    "approved": False,
    "group": 'Render',
    "group_prefix": 'RENDER',
    "group_order": 60,
    "addon_order": 60,
    "location": 'View3D > ZENV',
    "tags": ['render', 'raycast', 'projection', 'depth'],
    "description_short": 'Raycast from a plane to render a hit/miss image.',
    "description_medium": 'Casts rays from a selected plane along its normal and '
                          'produces a PNG hit/miss mask or debug line visualisation.',
    "description_long": 'Custom raytrace renderer that uses a mesh (typically a '
                        'plane) as an image plane. Rays are cast from each pixel '
                        'on the plane along the plane normal. Hits are recorded '
                        'and either visualised as debug line objects or written '
                        'to a timestamped PNG file.',
    "image_overview": '',
    "addon_image": '',
    "warning": 'Debug mode creates one mesh with all rays - keep resolution low.',
    "doc_url": '',
}
#endregion

#region imports
import bpy
from mathutils import Vector, Euler
from bpy.props import IntProperty
from bpy.types import Operator, Panel, PropertyGroup
import os
import logging
from datetime import datetime
#endregion

#region logging
# Module logger setup - stream handler install / uninstall
logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler for this module's logger."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _uninstall_logger():
    """Remove the stream handler."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region utils
# Core raycast helper - cast rays from plane pixels along normal, plus debug cleanup
class ZENV_Utils_PlaneProjection:
    """Utility class for plane projection operations"""

    @staticmethod
    def perform_ray_cast(context, plane, pixel_width, pixel_height):
        """Perform raycast from plane points and return results"""
        if plane.type != 'MESH':
            return []

        if not plane.data.polygons:
            return []

        depsgraph = context.evaluated_depsgraph_get()
        scene = context.scene
        mat = plane.matrix_world

        # Derive local-space extents from the mesh's vertex bounds so that
        # matrix_world handles scale/rotation/translation
        # (plane.dimensions would double-apply the object scale).
        local_coords = [v.co for v in plane.data.vertices]
        if not local_coords:
            return []
        local_min_x = min(co.x for co in local_coords)
        local_max_x = max(co.x for co in local_coords)
        local_min_y = min(co.y for co in local_coords)
        local_max_y = max(co.y for co in local_coords)
        local_size_x = local_max_x - local_min_x
        local_size_y = local_max_y - local_min_y
        local_center_x = (local_min_x + local_max_x) * 0.5
        local_center_y = (local_min_y + local_max_y) * 0.5

        # Transform normal correctly via inverse-transpose for non-uniform scale
        normal_mat = mat.to_3x3().inverted_safe().transposed()
        transformed_normal = (normal_mat @ plane.data.polygons[0].normal).normalized()

        results = []
        offset = transformed_normal * 0.001  # Small offset along the normal to avoid self-intersection
        max_distance = 10.0  # Max ray travel distance

        # Progress feedback for long ray casts
        wm = context.window_manager
        wm.progress_begin(0, pixel_width)

        for x in range(pixel_width):
            if x % max(1, pixel_width // 20) == 0:
                wm.progress_update(x)
            for y in range(pixel_height):
                u = x / pixel_width - 0.5
                v = y / pixel_height - 0.5
                local_pos = Vector((
                    local_center_x + u * local_size_x,
                    local_center_y + v * local_size_y,
                    0.0,
                ))
                world_pos = mat @ local_pos + offset
                ray_direction = transformed_normal
                ray_end = world_pos + ray_direction * max_distance
                result, location, normal, index, hit_object, matrix = scene.ray_cast(
                    depsgraph, world_pos, ray_direction
                )

                # Check if the ray hits the plane itself and ignore this hit
                if result and hit_object != plane:
                    # Enforce max distance (scene.ray_cast has no max-distance param)
                    if (location - world_pos).length <= max_distance:
                        results.append((world_pos, ray_end, True, location, normal, hit_object))
                    else:
                        results.append((world_pos, ray_end, False, location, normal, hit_object))
                else:
                    results.append((world_pos, ray_end, False, location, normal, hit_object))
        wm.progress_end()
        return results

    @staticmethod
    def create_default_plane(context):
        """Create a default plane at the camera/viewport position, oriented
        so its normal points along the view direction.

        The plane's local +X maps to the camera's right, +Y to the camera's
        up, and +Z (the normal / ray direction) to the camera's forward
        (-Z).  This is achieved by copying the camera rotation and applying
        a negative Z scale, which flips the normal without requiring an
        improper rotation matrix.

        The plane is sized to give a ~50° horizontal FOV given the
        hardcoded ``max_distance`` of 10 and matched to the render
        resolution aspect ratio.
        """
        props = context.scene.zenv_planeprojection_props
        pixel_width = max(1, props.pixel_width)
        pixel_height = max(1, props.pixel_height)

        # --- determine view source -------------------------------------------
        cam_matrix = None
        if context.scene.camera:
            cam_matrix = context.scene.camera.matrix_world.copy()
        elif (context.space_data is not None
              and context.space_data.type == 'VIEW_3D'
              and context.space_data.region_3d is not None):
            # view_matrix is world->view; invert for view->world
            cam_matrix = context.space_data.region_3d.view_matrix.inverted()

        if cam_matrix is not None:
            loc = cam_matrix.translation
            rot = cam_matrix.to_euler()
        else:
            # Fallback: origin, facing -Z
            loc = Vector((0.0, 0.0, 0.0))
            rot = Euler((0.0, 0.0, 0.0), 'XYZ')

        # --- create plane ----------------------------------------------------
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=loc)
        plane = context.active_object
        plane.name = "PlaneProjection_Default"

        # Copy camera rotation so local axes match the camera axes.
        plane.rotation_euler = rot

        # Scale to match aspect ratio and give a reasonable FOV.
        # base=5 -> 10 m plane -> atan(5/10) ≈ 26.6° half-angle ≈ 53° FOV
        # (matches the default 50 mm Blender camera fairly closely).
        aspect = pixel_width / pixel_height
        base = 5.0
        if aspect >= 1.0:
            plane.scale = (base * aspect, base, -1.0)
        else:
            plane.scale = (base, base / aspect, -1.0)

        # Negative Z scale flips the face normal to point along the
        # camera's forward direction (camera -Z) so rays travel into
        # the scene the user is looking at.
        return plane

    @staticmethod
    def clear_debug_lines(context):
        """Remove all debug line objects and their orphaned data.

        Iterates over a list copy and cleans up mesh + material data
        when unreferenced.
        """
        for obj in list(context.scene.objects):
            if obj.name.startswith("Ray Line"):
                mesh = obj.data
                mats = [m for m in obj.data.materials if m] if hasattr(obj.data, "materials") else []
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
                for m in mats:
                    if m.users == 0:
                        bpy.data.materials.remove(m)
#endregion

#region ops
# Operators - render image, debug raycast visualisation, clear debug lines

#region ops-render
# Render hit/miss image to a timestamped PNG via plane-projection raycast
class ZENV_OT_PlaneProjection_Render(Operator):
    """Render image from plane projection.

    If no mesh is active, a default plane is created at the current
    camera (or viewport) position, oriented so its normal points along
    the view direction – producing a render similar to what the user sees.
    """
    bl_idname = "zenv.planeprojection_render"
    bl_label = "Render from Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def save_rendered_image(render_image, base_path, scene_name):
        """Save rendered image to file with timestamp.

        Filename format: ``<SceneName>_RENDER_plane_projection_<YYYYMMDDHHMMSS>.png``
        """
        render_dir = os.path.join(base_path, "render")
        try:
            os.makedirs(render_dir, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Cannot create render directory '{render_dir}': {e}") from e
        # Sanitise the scene name so it is safe to use as a filename prefix.
        safe_name = "".join(
            c for c in scene_name if c.isalnum() or c in ('_', '-')
        ) or "Scene"
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"{safe_name}_RENDER_plane_projection_{date_str}.png"
        file_path = os.path.join(render_dir, file_name)
        render_image.filepath_raw = file_path
        render_image.file_format = 'PNG'
        render_image.save()
        logger.info("Saved render to %s", file_path)
        return file_path

    def raycast_from_plane(self, context, plane, pixel_width, pixel_height):
        """Render image from plane projection"""
        results = ZENV_Utils_PlaneProjection.perform_ray_cast(context, plane, pixel_width, pixel_height)
        if not results:
            return {'CANCELLED'}

        # Check that the blend file is saved before writing next to it
        if not bpy.data.is_saved:
            self.report({'WARNING'}, "Blend file is not saved - rendering to working directory")

        # Create new image for rendering
        render_image = bpy.data.images.new(
            name="PlaneProjection",
            width=pixel_width,
            height=pixel_height,
            alpha=True
        )

        try:
            # Set pixels based on raycast results.
            # Pixel layout is row-major: pixel(x, y) -> (y * pixel_width + x) * 4
            # (x-outer/y-inner loop order would transpose the image).
            # Background is opaque black.
            pixels = [0.0, 0.0, 0.0, 1.0] * (pixel_width * pixel_height)
            for i, (start, end, hit, location, normal, obj) in enumerate(results):
                x = i // pixel_height
                y = i % pixel_height
                pixel_idx = (y * pixel_width + x) * 4
                if hit:
                    pixels[pixel_idx:pixel_idx + 4] = [1.0, 1.0, 1.0, 1.0]

            render_image.pixels = pixels
            base_path = bpy.path.abspath("//") if bpy.data.is_saved else bpy.app.tempdir
            saved_path = self.save_rendered_image(render_image, base_path, context.scene.name)
            self.report({'INFO'}, f"Saved: {saved_path}")
        finally:
            bpy.data.images.remove(render_image)
        return {'FINISHED'}

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            # No plane selected – create a default one at the camera position
            try:
                active_obj = ZENV_Utils_PlaneProjection.create_default_plane(context)
                self.report({'INFO'}, f"Created default plane '{active_obj.name}' at camera position")
            except Exception as e:
                logger.error("Failed to create default plane: %s", e)
                self.report({'ERROR'}, f"Could not create default plane: {e}")
                return {'CANCELLED'}

        props = context.scene.zenv_planeprojection_props
        try:
            return self.raycast_from_plane(context, active_obj, props.pixel_width, props.pixel_height)
        except Exception as e:
            logger.error("Render failed: %s", e)
            self.report({'ERROR'}, f"Render failed: {e}")
            return {'CANCELLED'}
#endregion

#region ops-debug
# Debug raycast - create hit/miss line meshes to visualise the rays in 3D
class ZENV_OT_PlaneProjection_Debug(Operator):
    """Debug visualization of plane projection raycasts"""
    bl_idname = "zenv.planeprojection_debug"
    bl_label = "Debug Raycast Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        active = context.active_object
        return active is not None and active.type == 'MESH'

    @staticmethod
    def create_debug_mesh(context, results):
        """Create debug mesh(es) containing all ray lines.

        All hit lines are batched into one mesh and all miss lines into
        another, each with a single shared material. (Blender's MeshEdge
        has no material_index, so two objects are used instead of per-edge
        material assignment.)
        """
        if not results:
            return None

        hit_verts = []
        hit_edges = []
        miss_verts = []
        miss_edges = []

        for start, end, hit, location, normal, hit_obj in results:
            if hit:
                v0 = len(hit_verts)
                hit_verts.append(start)
                hit_verts.append(location)
                hit_edges.append((v0, v0 + 1))
            else:
                v0 = len(miss_verts)
                miss_verts.append(start)
                miss_verts.append(end)
                miss_edges.append((v0, v0 + 1))

        # Create hit mesh
        if hit_verts:
            hit_mesh = bpy.data.meshes.new(name="Ray Line Hit Mesh")
            hit_obj = bpy.data.objects.new("Ray Line", hit_mesh)
            context.collection.objects.link(hit_obj)
            hit_mesh.from_pydata(hit_verts, hit_edges, [])
            hit_mesh.update()
            mat_hit = bpy.data.materials.new(name="RayLineMat_Hit")
            mat_hit.diffuse_color = (1.0, 1.0, 1.0, 1.0)  # White for hit
            hit_mesh.materials.append(mat_hit)

        # Create miss mesh
        if miss_verts:
            miss_mesh = bpy.data.meshes.new(name="Ray Line Miss Mesh")
            miss_obj = bpy.data.objects.new("Ray Line Miss", miss_mesh)
            context.collection.objects.link(miss_obj)
            miss_mesh.from_pydata(miss_verts, miss_edges, [])
            miss_mesh.update()
            mat_miss = bpy.data.materials.new(name="RayLineMat_Miss")
            mat_miss.diffuse_color = (1.0, 0.0, 0.0, 0.5)  # Red for no hit
            miss_mesh.materials.append(mat_miss)

        return context.scene.objects.get("Ray Line")

    def raycast_from_plane_debug(self, context, plane, pixel_width, pixel_height):
        """Debug visualization of plane projection raycasts"""
        results = ZENV_Utils_PlaneProjection.perform_ray_cast(context, plane, pixel_width, pixel_height)
        if not results:
            return {'CANCELLED'}

        ZENV_Utils_PlaneProjection.clear_debug_lines(context)
        self.create_debug_mesh(context, results)
        return {'FINISHED'}

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}

        props = context.scene.zenv_planeprojection_props
        try:
            return self.raycast_from_plane_debug(context, active_obj, props.pixel_width, props.pixel_height)
        except Exception as e:
            logger.error("Debug raycast failed: %s", e)
            self.report({'ERROR'}, f"Debug failed: {e}")
            return {'CANCELLED'}
#endregion

#region ops-clear
# Clear all debug ray line objects and their orphaned mesh/material data
class ZENV_OT_PlaneProjection_ClearDebug(Operator):
    """Clear debug visualization lines"""
    bl_idname = "zenv.planeprojection_cleardebug"
    bl_label = "Clear Debug Lines"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        try:
            ZENV_Utils_PlaneProjection.clear_debug_lines(context)
        except Exception as e:
            logger.error("Clear debug failed: %s", e)
            self.report({'ERROR'}, f"Clear failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}
#endregion

#endregion

#region props
# Property group - render resolution (pixel width / height)
class ZENV_PG_PlaneProjection_Properties(PropertyGroup):
    """Properties for plane projection rendering"""
    pixel_width: IntProperty(
        name="Pixel Width",
        description="Width of the rendered image in pixels",
        default=100,
        min=1,
        max=1000
    )
    pixel_height: IntProperty(
        name="Pixel Height",
        description="Height of the rendered image in pixels",
        default=100,
        min=1,
        max=1000
    )
#endregion

#region panel
# View3D panel UI - resolution settings and render / debug / clear buttons
class ZENV_PT_PlaneProjection(Panel):
    """Panel for configuring plane projection rendering settings"""
    bl_label = "RENDER Plane Projection"
    bl_idname = "ZENV_PT_PlaneProjection"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_planeprojection_props

        box = layout.box()
        box.label(text="Resolution:", icon='RESTRICT_RENDER_OFF')
        col = box.column(align=True)
        col.prop(props, "pixel_width", text="Width")
        col.prop(props, "pixel_height", text="Height")

        layout.separator()

        active = context.active_object
        if not active or active.type != 'MESH':
            layout.label(text="No plane selected – Render will auto-create one", icon='INFO')

        col = layout.column(align=True)
        col.operator("zenv.planeprojection_render", text="Render Image", icon='RENDER_STILL')
        col.operator("zenv.planeprojection_debug", text="Debug View", icon='SNAP_FACE')
        col.operator("zenv.planeprojection_cleardebug", text="Clear Debug", icon='CANCEL')
#endregion

#region register
# Class registration and module load / unload
classes = (
    ZENV_PG_PlaneProjection_Properties,
    ZENV_OT_PlaneProjection_Debug,
    ZENV_OT_PlaneProjection_Render,
    ZENV_OT_PlaneProjection_ClearDebug,
    ZENV_PT_PlaneProjection,
)

def register():
    _install_logger()
    for current_class in classes:
        try:
            bpy.utils.register_class(current_class)
        except ValueError:
            pass  # Already registered
    if not hasattr(bpy.types.Scene, "zenv_planeprojection_props"):
        bpy.types.Scene.zenv_planeprojection_props = bpy.props.PointerProperty(type=ZENV_PG_PlaneProjection_Properties)
    logger.info("Registered RENDER Plane Projection")

def unregister():
    for current_class in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class)
        except (ValueError, RuntimeError):
            pass  # Not registered or already unregistered
    if hasattr(bpy.types.Scene, "zenv_planeprojection_props"):
        del bpy.types.Scene.zenv_planeprojection_props
    logger.info("Unregistered RENDER Plane Projection")
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
