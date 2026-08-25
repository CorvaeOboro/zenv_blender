#region META
bl_info = {
    "name": 'TEX Camera Projection',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Create camera from current view and bake projected textures',
    "status": 'working',
    "approved": True,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 10,
    "addon_order": 10,
    "tags": ['texture', 'projection', 'camera', 'bake', 'uv', 'visibility', 'mask'],
    "description_short": 'Create camera from current view and bake projected textures',
    "description_medium": 'texture projection from camera - creates square orthographic camera from current view , and the camera projects image onto mesh baking to texture . workflow similar to "quick edits" in texture paint mode , now with permanent cameras',
    "description_long": """
TEXTURE PROJECTION FROM CAMERA
 create camera from current view and project textures
 bake textures using camera projection and visibility masks
""",
    "image_overview": 'zenv_blender_TEX_texture_proj_cam.png',
    "addon_image": 'zenv_blender_TEX_texture_proj_cam.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
import shutil
import math
import time
import json
import random
import logging
import bmesh
import numpy as np
from datetime import datetime
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

logger = logging.getLogger(__name__)
_zenv_tex_proj_cam_console_handler = None
#endregion

#region PROPS
class ZENV_TextureProj_Properties:
    """Property management for texture projection addon"""
    
    @staticmethod
    def update_ortho_scale(self, context):
        """Update orthographic scale of active camera"""
        camera = context.scene.camera
        if camera and camera.data.type == 'ORTHO':
            camera.data.ortho_scale = self.zenv_ortho_scale
    
    @staticmethod
    def clean_filepath(filepath):
        """Clean filepath by removing quotes and normalizing path"""
        if not filepath:
            return filepath
        
        # Strip leading/trailing whitespace
        cleaned = filepath.strip()
        
        # Remove surrounding quotes (single or double)
        if (cleaned.startswith('"') and cleaned.endswith('"')) or \
           (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1]
        
        # Normalize path separators for the OS
        cleaned = os.path.normpath(cleaned)
        
        return cleaned
    
    @staticmethod
    def update_texture_path(self, context):
        """Update callback for texture path - cleans pasted paths with quotes"""
        if context.scene.zenv_texture_path:
            cleaned_path = ZENV_TextureProj_Properties.clean_filepath(context.scene.zenv_texture_path)
            
            # Only update if the path actually changed (avoid infinite recursion)
            if cleaned_path != context.scene.zenv_texture_path:
                # Temporarily disable the update callback to avoid recursion
                context.scene.zenv_texture_path = cleaned_path
                logger.info(f"Cleaned filepath: {cleaned_path}")

    @classmethod
    def register(cls):
        """Register all properties"""
        bpy.types.Scene.zenv_ortho_scale = bpy.props.FloatProperty(
            name="Ortho Scale",
            description="Scale of the orthographic camera view",
            default=5.0,
            min=0.1,
            update=cls.update_ortho_scale
        )
        bpy.types.Scene.zenv_bake_margin = bpy.props.IntProperty(
            name="Bake Margin",
            description="Bake padding in pixels (0 = no padding)",
            default=16,
            min=0,
            max=256
        )
        bpy.types.Scene.zenv_texture_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_texture_path = bpy.props.StringProperty(
            name="Texture Path",
            description="Path to the texture file (paste paths with quotes will be auto-cleaned)",
            subtype='FILE_PATH',
            update=cls.update_texture_path
        )
        bpy.types.Scene.zenv_debug_mode = bpy.props.BoolProperty(
            name="Debug Mode",
            description="Keep temporary objects for debugging",
            default=False
        )
        bpy.types.Scene.zenv_square_texture = bpy.props.BoolProperty(
            name="Square Texture",
            description="Use square texture resolution (legacy mode). Disable for non-square images",
            default=True
        )
        bpy.types.Scene.zenv_orthographic = bpy.props.BoolProperty(
            name="Orthographic Camera",
            description="Use orthographic camera projection. Disable for perspective camera",
            default=True
        )
        bpy.types.Scene.zenv_texture_resolution_x = bpy.props.IntProperty(
            name="Resolution X",
            description="Horizontal resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_texture_resolution_y = bpy.props.IntProperty(
            name="Resolution Y",
            description="Vertical resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_square_camera = bpy.props.BoolProperty(
            name="Square Camera",
            description="Use square camera resolution (legacy mode). Disable for non-square camera viewport",
            default=True
        )
        bpy.types.Scene.zenv_camera_resolution_x = bpy.props.IntProperty(
            name="Camera Res X",
            description="Horizontal resolution of the camera viewport",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_camera_resolution_y = bpy.props.IntProperty(
            name="Camera Res Y",
            description="Vertical resolution of the camera viewport",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_mask_margin = bpy.props.IntProperty(
            name="Mask Margin",
            description="Margin in pixels to erode from mask edges to avoid stretched areas",
            default=16,
            min=0,
            max=128
        )
        bpy.types.Scene.zenv_mask_falloff = bpy.props.IntProperty(
            name="Mask Falloff",
            description="Distance in pixels for gradient falloff from mask edges (0 = sharp edge)",
            default=32,
            min=0,
            max=256
        )
        bpy.types.Scene.zenv_mask_sample_count = bpy.props.IntProperty(
            name="Ray Sample Count",
            description="Number of rays to cast from camera (creates NxN grid)",
            default=10000,
            min=100
        )
        bpy.types.Scene.zenv_mask_sample_density = bpy.props.FloatProperty(
            name="Sample Density",
            description="Ray sampling density multiplier (1.0 = one ray per camera pixel, 0.5 = half resolution, 2.0 = double)",
            default=1.0,
            min=0.1,
            max=4.0,
            step=10
        )
        bpy.types.Scene.zenv_use_mask_as_alpha = bpy.props.BoolProperty(
            name="Use Visibility Mask as Alpha",
            description="Composite visibility mask as alpha channel onto color texture",
            default=False
        )
        bpy.types.Scene.zenv_mask_dilation = bpy.props.IntProperty(
            name="Mask Dilation",
            description="Number of pixels to expand white mask areas (0 = no expansion)",
            default=1,
            min=0,
            max=10
        )

    @classmethod
    def unregister(cls):
        """Unregister all properties"""
        _props = (
            'zenv_ortho_scale', 'zenv_bake_margin', 'zenv_texture_resolution',
            'zenv_texture_path', 'zenv_debug_mode', 'zenv_square_texture',
            'zenv_orthographic', 'zenv_texture_resolution_x',
            'zenv_texture_resolution_y', 'zenv_square_camera',
            'zenv_camera_resolution_x', 'zenv_camera_resolution_y',
            'zenv_mask_margin', 'zenv_mask_falloff', 'zenv_mask_sample_count',
            'zenv_mask_sample_density', 'zenv_use_mask_as_alpha',
            'zenv_mask_dilation',
        )
        scene_type = bpy.types.Scene
        for _name in _props:
            if hasattr(scene_type, _name):
                delattr(scene_type, _name)
#endregion

#region UTILS
class ZENV_TextureProj_Utils:
    """Utility functions for texture projection"""
    
    @staticmethod
    def get_texture_resolution(context):
        """
        Get texture resolution based on square_texture setting.
        Returns (width, height) tuple.
        """
        if context.scene.zenv_square_texture:
            # Legacy mode: use square resolution
            res = context.scene.zenv_texture_resolution
            return (res, res)
        else:
            # Non-square mode: use separate X and Y resolutions
            return (context.scene.zenv_texture_resolution_x, 
                    context.scene.zenv_texture_resolution_y)
    
    @staticmethod
    def get_camera_resolution(context):
        """
        Get camera resolution based on square_camera setting.
        Returns (width, height) tuple.
        """
        if context.scene.zenv_square_camera:
            # Legacy mode: use square resolution (from texture resolution for backward compat)
            res = context.scene.zenv_texture_resolution
            return (res, res)
        else:
            # Non-square mode: use separate camera X and Y resolutions
            return (context.scene.zenv_camera_resolution_x, 
                    context.scene.zenv_camera_resolution_y)
    
    @staticmethod
    def get_camera_aspect_ratio(context):
        """
        Get camera aspect ratio based on current settings.
        Returns width/height ratio.
        """
        cam_res_x, cam_res_y = ZENV_TextureProj_Utils.get_camera_resolution(context)
        if cam_res_y > 0:
            return cam_res_x / cam_res_y
        return 1.0
    
    @staticmethod
    def is_square_camera(context):
        """
        Check if camera is using square aspect ratio.
        Returns True if square, False if non-square.
        """
        if context.scene.zenv_square_camera:
            return True
        
        # Check if resolution is actually square even in non-square mode
        cam_res_x, cam_res_y = ZENV_TextureProj_Utils.get_camera_resolution(context)
        return cam_res_x == cam_res_y
    
    @staticmethod
    def get_image_aspect_ratio(image_path):
        """
        Get aspect ratio of an image file.
        Returns width/height ratio, or 1.0 if unable to determine.
        """
        try:
            image = bpy.data.images.load(image_path, check_existing=True)
            if image.size[0] > 0 and image.size[1] > 0:
                aspect = image.size[0] / image.size[1]
                return aspect
        except Exception as e:
            logger.warning(f"Could not determine image aspect ratio: {e}")
        return 1.0

    @staticmethod
    def load_or_refresh_image(image_path):
        """Return a ``bpy.data.images`` entry that points at ``image_path``.

        ``bpy.data.images`` is keyed by data-block name
        (typically the basename), but ``image.reload()`` reads from
        ``image.filepath``. If the scene already contains a block named
        ``texture.png`` whose ``filepath`` is missing,
        the naive ``if name in bpy.data.images: image.reload()`` pattern
        will silently reload the *wrong* (or broken) file, and the
        subsequent bake a pink/empty image.

        This helper:
        - Looks up an existing block by name and compares its absolute
          filepath against the requested path.
        - Repoints ``filepath`` and forces ``source='FILE'`` before
          reloading, so a name collision with a different/missing file
          is recovered rather than silently baked.
        - Falls back to ``bpy.data.images.load`` with
          ``check_existing=False`` so we don't get handed a broken block.
        - Returns the image; the caller should verify ``image.size``
          (not ``has_data``: Blender loads pixel data lazily, so
          ``has_data`` can be ``False`` on a  valid image
          until something samples it).
        """
        abs_path = os.path.abspath(bpy.path.abspath(image_path))
        image_name = os.path.basename(abs_path)

        existing = bpy.data.images.get(image_name)
        if existing is not None:
            existing_abs = ""
            if existing.filepath:
                try:
                    existing_abs = os.path.abspath(bpy.path.abspath(existing.filepath))
                except Exception:
                    existing_abs = ""
            same_file = existing_abs.lower() == abs_path.lower()
            if not same_file:
                logger.info(
                    f"Image '{image_name}' already exists with filepath "
                    f"'{existing.filepath}'; repointing to '{abs_path}'."
                )
            existing.source = 'FILE'
            existing.filepath = abs_path
            try:
                existing.reload()
            except RuntimeError as e:
                logger.warning(f"reload() failed for '{image_name}': {e}")
            image = existing
        else:
            image = bpy.data.images.load(abs_path, check_existing=False)
            image.source = 'FILE'

        # Recovery pass: if the header still didn't decode (size is 0),
        # force one more reload from the explicit path before giving up.
        # Note: ``has_data`` is intentionally NOT checked here -- pixel
        # data is loaded lazily, so ``has_data`` can legitimately be
        # ``False`` on a valid image until first sample.
        if image.size[0] == 0 or image.size[1] == 0:
            try:
                image.filepath = abs_path
                image.source = 'FILE'
                image.reload()
            except RuntimeError as e:
                logger.error(f"Final reload attempt failed for '{image_name}': {e}")

        return image
    
    @staticmethod
    def setup_material_nodes(material, image=None):
        """Set up material nodes for texture projection or baking"""
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        
        # Create basic node setup
        tex_coord = nodes.new('ShaderNodeTexCoord')
        uv_map = nodes.new('ShaderNodeUVMap')
        mapping = nodes.new('ShaderNodeMapping')
        tex_image = nodes.new('ShaderNodeTexImage')
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')
        
        # Set image
        if image:
            tex_image.image = image
            tex_image.extension = 'CLIP'  # Prevent texture repeating
        
        # Position nodes
        tex_coord.location = (-800, 100)
        uv_map.location = (-800, -100)
        mapping.location = (-600, 0)
        tex_image.location = (-400, 0)
        bsdf.location = (-200, 0)
        output.location = (0, 0)
        
        # Link nodes
        links = material.node_tree.links
        links.new(uv_map.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])
        links.new(tex_image.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        return nodes

    @staticmethod
    def ensure_texture_directory():
        """Ensure texture output directory exists"""
        texture_dir = bpy.path.abspath("//textures")
        if not os.path.exists(texture_dir):
            os.makedirs(texture_dir)
        return texture_dir

    @staticmethod
    def generate_texture_filename(prefix="bake"):
        """Generate unique texture filename"""
        return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.png"

    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking"""
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.device = 'GPU'
        context.scene.cycles.samples = 32  # Increased samples for better quality
        context.scene.cycles.bake_type = 'DIFFUSE'
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = False
        context.scene.render.bake.use_pass_color = True
        context.scene.render.bake.margin = context.scene.zenv_bake_margin
        context.scene.render.bake.use_clear = True  # Clear image before baking
        
        # Set high quality settings
        context.scene.cycles.use_denoising = True
        context.scene.cycles.preview_denoiser = 'OPTIX'
        context.scene.cycles.use_high_quality_normals = True

    @staticmethod
    def find_any_camera(scene):
        if not scene:
            return None
        for obj in scene.objects:
            if obj.type == 'CAMERA':
                return obj
        return None
#endregion

#region OP
class ZENV_OT_TextureProj_CreateCamera(bpy.types.Operator):
    """Create orthographic camera from current view"""
    bl_idname = "zenv.textureproj_create_camera"
    bl_label = "Create Camera"
    bl_description = "Creates an orthographic camera matching the current view"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def execute(self, context):
        try:
            if not self.create_orthographic_camera(context):
                return {'CANCELLED'}
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create camera: {str(e)}")
            return {'CANCELLED'}

    def create_orthographic_camera(self, context):
        """Create and set up camera (orthographic or perspective based on settings)"""
        # Generate appropriate camera name based on type
        if context.scene.zenv_orthographic:
            camera_name = self.generate_unique_camera_name("CAM_ORTHO_PROJ_")
        else:
            camera_name = self.generate_unique_camera_name("CAM_PERSP_PROJ_")
            
        bpy.ops.object.camera_add()
        camera = context.active_object
        camera.name = camera_name
        context.scene.camera = camera

        # Set up camera properties
        if not self.match_camera_to_view(camera, context):
            return False
        if not self.setup_camera_properties(camera, context):
            return False

        # Set render resolution based on square_camera setting (camera viewport)
        # This is separate from texture resolution to allow independent control
        cam_res_x, cam_res_y = ZENV_TextureProj_Utils.get_camera_resolution(context)
        context.scene.render.resolution_x = cam_res_x
        context.scene.render.resolution_y = cam_res_y

        return True

    def match_camera_to_view(self, camera, context):
        """Match camera to current 3D view"""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                camera.matrix_world = area.spaces.active.region_3d.view_matrix.inverted()
                return True
        return False

    def setup_camera_properties(self, camera, context):
        """
        Set up camera properties based on orthographic setting.
        Branches to isolated functions for each camera type.
        """
        if context.scene.zenv_orthographic:
            return self.setup_orthographic_camera(camera, context)
        else:
            return self.setup_perspective_camera(camera, context)
    
    def setup_orthographic_camera(self, camera, context):
        """Set up orthographic camera properties (legacy mode)"""
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = context.scene.zenv_ortho_scale

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                camera.data.clip_start = space.clip_start
                camera.data.clip_end = space.clip_end
                return True
        return False
    
    def setup_perspective_camera(self, camera, context):
        """Set up perspective camera properties, matching viewport lens when possible."""
        camera.data.type = 'PERSP'

        # Match FOV to current view if possible
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                region_3d = space.region_3d

                # Set clip distances
                camera.data.clip_start = space.clip_start
                camera.data.clip_end = space.clip_end

                # Match lens from the viewport when it is in perspective mode.
                # ``region_3d.lens`` holds the focal length used by the
                # viewport editor, so copying it gives a camera that
                # matches what the user sees.
                if region_3d.view_perspective == 'PERSP':
                    camera.data.lens = getattr(region_3d, 'lens', 50)
                else:
                    # Ortho or camera view: use the viewport's stored lens
                    # value (Blender keeps one even in ortho mode) or fall
                    # back to 50 mm.
                    camera.data.lens = getattr(region_3d, 'lens', 50)

                return True
        return False

    def generate_unique_camera_name(self, base_name):
        """Generate unique camera name"""
        cameras = {cam.name for cam in bpy.data.objects if cam.type == 'CAMERA'}
        i = 1
        while f"{base_name}{i}" in cameras:
            i += 1
        return f"{base_name}{i}"

class ZENV_OT_TextureProj_GetCameraResolution(bpy.types.Operator):
    """Get camera resolution from current scene render settings"""
    bl_idname = "zenv.textureproj_get_camera_resolution"
    bl_label = "Get Resolution"
    bl_description = "Get camera resolution from current scene render settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Read current render resolution
        context.scene.zenv_camera_resolution_x = context.scene.render.resolution_x
        context.scene.zenv_camera_resolution_y = context.scene.render.resolution_y
        
        self.report({'INFO'}, f"Got resolution: {context.scene.render.resolution_x}x{context.scene.render.resolution_y}")
        return {'FINISHED'}

class ZENV_OT_TextureProj_DropImage(bpy.types.Operator):
    """Open file browser to select an image"""
    bl_idname = "zenv.textureproj_drop_image"
    bl_label = "Select Image"
    bl_description = "Open file browser to select an image file"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.bmp;*.tga;*.tiff;*.tif;*.exr;*.hdr",
        options={'HIDDEN'}
    )

    def execute(self, context):
        # Clean the filepath (remove quotes, normalize path)
        cleaned_filepath = ZENV_TextureProj_Properties.clean_filepath(self.filepath)
        
        # Validate that the file is an image
        valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tga', '.tiff', '.tif', '.exr', '.hdr'}
        file_ext = os.path.splitext(cleaned_filepath)[1].lower()
        
        if file_ext not in valid_extensions:
            self.report({'ERROR'}, f"Invalid file type: {file_ext}. Please select an image file.")
            return {'CANCELLED'}
        
        # Check if file exists
        if not os.path.isfile(cleaned_filepath):
            self.report({'ERROR'}, f"File not found: {cleaned_filepath}")
            return {'CANCELLED'}
        
        # Set the texture path
        context.scene.zenv_texture_path = cleaned_filepath
        self.report({'INFO'}, f"Loaded image: {os.path.basename(cleaned_filepath)}")
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ZENV_OT_TextureProj_BakeTexture(bpy.types.Operator):
    """Bake texture using camera projection"""
    bl_idname = "zenv.textureproj_bake"
    bl_label = "Bake Texture"
    bl_description = "Bake texture using camera projection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        """
        Baking workflow:
        1. TEMP_SOURCE_MESH (bake FROM):
           - Gets UV Project modifier with camera
           - Gets source material with projected texture
           - Shows how texture looks when projected
        
        2. TEMP_TARGET_MESH (bake TO):
           - Keeps original mesh's UVs
           - Gets simple material with only empty image node
           - NO camera projection
           - Just shell modifier for better baking
           - Receives bake using original UVs
        """
        if not self.initial_checks(context):
            return {'CANCELLED'}

        try:
            # Save current state and create bake image
            state = self.save_current_state(context)
            
            # Step 0: Auto-bake visibility mask FIRST if checkbox is enabled (while object is still selected)
            if context.scene.zenv_use_mask_as_alpha:
                self.report({'INFO'}, "Auto-baking visibility mask...")
                logger.info("Auto-baking visibility mask for alpha compositing...")
                logger.info("\n=== AUTO-BAKING VISIBILITY MASK ===")
                mask_result = self.auto_bake_visibility_mask(context, state['original_obj'])
                if not mask_result:
                    self.report({'WARNING'}, "Failed to auto-bake visibility mask, continuing without alpha")
                    logger.warning("Mask auto-bake failed")
                else:
                    self.report({'INFO'}, "Visibility mask baked successfully")
                    logger.info("Mask auto-bake succeeded")
            
            bake_image = self.create_bake_image(context)
            
            # Step 1: Create source mesh (what we bake FROM)
            source_mesh = self.create_source_mesh(context, context.active_object)
            if not source_mesh:
                self.restore_state(context, state)
                return {'CANCELLED'}
            
            # Step 2: Create target mesh (what we bake TO)
            target_mesh = self.create_target_mesh(context, context.active_object, bake_image)
            if not target_mesh:
                self.restore_state(context, state)
                return {'CANCELLED'}
            
            # Step 3: Perform the bake
            baked_path = self.perform_baking(context, source_mesh, target_mesh)
            if not baked_path:
                self.restore_state(context, state)
                return {'CANCELLED'}

            # Composite visibility mask as alpha if enabled
            if context.scene.zenv_use_mask_as_alpha:
                self.report({'INFO'}, "Compositing visibility mask as alpha...")
                logger.info("Compositing visibility mask as alpha...")
                logger.info("\n=== COMPOSITING MASK AS ALPHA ===")
                logger.info(f"Color texture path: {baked_path}")
                
                composited_path = self.composite_mask_as_alpha(context, baked_path, state['original_obj'])
                
                if composited_path and composited_path != baked_path:
                    baked_path = composited_path
                    self.report({'INFO'}, f"Composited with alpha: {baked_path}")
                    logger.info(f"Composite succeeded: {baked_path}")
                else:
                    self.report({'WARNING'}, "Failed to composite mask, using color texture only")
                    logger.warning("Composite failed or returned same path")
            
            # Apply result to original object
            self.apply_baked_texture(context, state['original_obj'], baked_path)
            
            # Cleanup
            if not context.scene.zenv_debug_mode:
                bpy.data.objects.remove(source_mesh, do_unlink=True)
                bpy.data.objects.remove(target_mesh, do_unlink=True)
            
            self.report({'INFO'}, f"Texture baked successfully to {baked_path}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}

    def initial_checks(self, context):
        """Perform initial checks before baking"""
        if not (context.active_object and context.active_object.type == 'MESH'):
            self.report({'ERROR'}, "Select a mesh object")
            return False

        if not context.scene.camera:
            fallback_cam = ZENV_TextureProj_Utils.find_any_camera(context.scene)
            if fallback_cam:
                context.scene.camera = fallback_cam
                self.report({'INFO'}, f"No active camera set. Using: {fallback_cam.name}")
            else:
                self.report({'ERROR'}, "No camera found in the scene")
                return False
        if not context.scene.zenv_texture_path:
            self.report({'ERROR'}, "No texture path specified")
            return False
        return True

    def create_source_mesh(self, context, original):
        """
        Create the source mesh that we bake FROM:
        - Has UV Project modifier with camera
        - Has material with projected texture
        - Shows how the texture looks when projected
        """
        bpy.ops.object.select_all(action='DESELECT')
        original.select_set(True)
        context.view_layer.objects.active = original
        
        # Create source mesh
        bpy.ops.object.duplicate(linked=False)
        source = context.active_object
        source.name = "TEMP_SOURCE_MESH"
        
        # Clear any existing materials
        while source.data.materials:
            source.data.materials.pop()
            
        # Create source material with projected texture
        source_mat = bpy.data.materials.new(name="TEMP_SOURCE_MATERIAL")
        source_mat.use_nodes = True
        nodes = source_mat.node_tree.nodes
        links = source_mat.node_tree.links
        nodes.clear()
        
        # Load and setup texture
        image_path = bpy.path.abspath(context.scene.zenv_texture_path)
        if not os.path.isfile(image_path):
            self.report({'ERROR'}, "Image file not found")
            return None

        # Load image and ensure it's fresh. ``load_or_refresh_image``
        # repairs the case where a stale data-block of the same name
        # already exists with a missing/different filepath -- otherwise
        # ``image.reload()`` would silently reload nothing and the bake
        # would produce a pink texture.
        image = ZENV_TextureProj_Utils.load_or_refresh_image(image_path)
        # Validate via ``size`` only -- ``has_data`` is lazy and may be
        # ``False`` on a valid image until the bake actually samples it.
        if image.size[0] == 0 or image.size[1] == 0:
            self.report(
                {'ERROR'},
                f"Source image failed to decode after reload: {image_path}"
            )
            return None

        # Create material nodes
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = image
        tex.extension = 'CLIP'
        
        bsdf = nodes.new('ShaderNodeBsdfDiffuse')  # Use simple diffuse for baking
        output = nodes.new('ShaderNodeOutputMaterial')
        
        # Link nodes
        links.new(tex.outputs['Color'], bsdf.inputs['Color'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        # Assign material
        source.data.materials.append(source_mat)
        
        # Add camera projection modifier with aspect ratio handling
        if not self.setup_uv_projection(context, source):
            self.report({'ERROR'}, "Failed to setup UV projection")
            return None
        
        return source
    
    def setup_uv_projection(self, context, mesh_obj):
        """
        Setup UV projection modifier based on camera aspect ratio.
        Branches to isolated functions for square vs non-square cameras.
        """
        if ZENV_TextureProj_Utils.is_square_camera(context):
            return self.setup_square_uv_projection(context, mesh_obj)
        else:
            return self.setup_nonsquare_uv_projection(context, mesh_obj)
    
    def setup_square_uv_projection(self, context, mesh_obj):
        """
        Setup UV projection for square camera (legacy mode).
        Simple 1:1 aspect ratio projection.
        """
        uvmod = mesh_obj.modifiers.new(name="UVProject", type='UV_PROJECT')
        uvmod.projector_count = 1
        uvmod.projectors[0].object = context.scene.camera
        # Square cameras don't need aspect ratio correction
        uvmod.aspect_x = 1.0
        uvmod.aspect_y = 1.0
        return True
    
    def setup_nonsquare_uv_projection(self, context, mesh_obj):
        """
        Setup UV projection for non-square camera.
        Adjusts aspect ratio to match camera resolution.
        """
        uvmod = mesh_obj.modifiers.new(name="UVProject", type='UV_PROJECT')
        uvmod.projector_count = 1
        uvmod.projectors[0].object = context.scene.camera
        
        # Get camera aspect ratio
        aspect_ratio = ZENV_TextureProj_Utils.get_camera_aspect_ratio(context)
        
        # Set aspect ratio for UV projection
        # If camera is wider than tall (landscape), adjust X
        # If camera is taller than wide (portrait), adjust Y
        if aspect_ratio > 1.0:
            # Landscape: wider than tall
            uvmod.aspect_x = aspect_ratio
            uvmod.aspect_y = 1.0
        else:
            # Portrait: taller than wide
            uvmod.aspect_x = 1.0
            uvmod.aspect_y = 1.0 / aspect_ratio
        
        logger.info(f"Non-square UV projection: aspect_ratio={aspect_ratio:.3f}, aspect_x={uvmod.aspect_x:.3f}, aspect_y={uvmod.aspect_y:.3f}")
        return True

    def create_target_mesh(self, context, original, bake_image):
        """
        Create the target mesh that we bake TO:
        - Keeps original mesh's UVs
        - Gets simple material with only empty image node
        - NO camera projection
        - Just shell modifier for better baking
        - Receives bake using original UVs
        """
        bpy.ops.object.select_all(action='DESELECT')
        original.select_set(True)
        context.view_layer.objects.active = original
        
        # Create target mesh
        bpy.ops.object.duplicate(linked=False)
        target = context.active_object
        target.name = "TEMP_TARGET_MESH"
        
        # Remove any UV Project modifiers (in case they were copied)
        for mod in target.modifiers:
            if mod.type == 'UV_PROJECT':
                target.modifiers.remove(mod)
        
        # Clear any existing materials
        while target.data.materials:
            target.data.materials.pop()
            
        # Create target material (just an empty image texture node)
        target_mat = bpy.data.materials.new(name="TEMP_TARGET_MATERIAL")
        target_mat.use_nodes = True
        nodes = target_mat.node_tree.nodes
        nodes.clear()
        
        # Add image texture node for baking
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bake_image
        tex.location = (0, 0)
        
        # Assign material
        target.data.materials.append(target_mat)
        
        # Add shell modifier for better baking
        shell = target.modifiers.new(name="Shell", type='SOLIDIFY')
        shell.thickness = 0.001  # Very small thickness for better results
        shell.offset = 1.0
        shell.use_rim = False
        
        # Apply modifier
        context.view_layer.objects.active = target
        bpy.ops.object.modifier_apply(modifier="Shell")
        
        return target

    def create_bake_image(self, context):
        """Create new image for baking with support for non-square resolutions"""
        image_name = f"bake_{datetime.now():%Y%m%d_%H%M%S}"
        
        # Get resolution based on square_texture setting
        res_x, res_y = ZENV_TextureProj_Utils.get_texture_resolution(context)
        
        bake_image = bpy.data.images.new(
            name=image_name,
            width=res_x,
            height=res_y,
            alpha=True,
            float_buffer=True
        )
        
        # Setup save path
        textures_folder = bpy.path.abspath("//textures/")
        if not os.path.exists(textures_folder):
            os.makedirs(textures_folder)
        bake_image.filepath_raw = os.path.join(textures_folder, f"{image_name}.png")
        bake_image.file_format = 'PNG'
        
        return bake_image

    def perform_baking(self, context, source_mesh, target_mesh):
        """Perform the actual bake operation"""
        bake_margin = context.scene.zenv_bake_margin

        # Setup render settings
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.device = 'GPU'
        context.scene.cycles.samples = 1
        context.scene.cycles.bake_type = 'DIFFUSE'
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = False
        context.scene.render.bake.use_pass_color = True
        context.scene.render.bake.margin = bake_margin
        
        # Set color management to Standard for exact texture colors (no color transform)
        context.scene.view_settings.view_transform = 'Standard'
        
        # Select objects for baking
        bpy.ops.object.select_all(action='DESELECT')
        source_mesh.select_set(True)
        target_mesh.select_set(True)
        context.view_layer.objects.active = target_mesh  # Active object receives the bake
        
        # Get bake image
        bake_image = target_mesh.data.materials[0].node_tree.nodes['Image Texture'].image
        
        # Perform bake with tiny cage extrusion
        bpy.ops.object.bake(
            type='DIFFUSE',
            pass_filter={'COLOR'},
            use_selected_to_active=True,
            cage_extrusion=0.001,  # Tiny extrusion for  baking
            margin=bake_margin
        )
        
        # Save result
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath_raw)
            return bake_image.filepath_raw
            
        return None

    def auto_bake_visibility_mask(self, context, target_obj):
        """Automatically bake visibility mask for the target object"""
        try:
            logger.info(f"Auto-bake visibility mask starting...")
            logger.info(f"  Target object: {target_obj.name}")
            logger.info(f"  Camera: {context.scene.camera}")
            logger.info(f"  Has UV layers: {len(target_obj.data.uv_layers) > 0 if target_obj.data.uv_layers else False}")
            
            # Save current selection
            original_active = context.view_layer.objects.active
            original_selected = [obj for obj in context.selected_objects]
            
            logger.info(f"  Original active: {original_active.name if original_active else None}")
            logger.info(f"  Original selected: {[o.name for o in original_selected]}")
            
            # Select target object
            bpy.ops.object.select_all(action='DESELECT')
            target_obj.select_set(True)
            context.view_layer.objects.active = target_obj
            
            logger.info(f"  Set active to: {context.view_layer.objects.active.name}")
            logger.info(f"  Calling bake mask operator...")
            
            # Call the visibility mask bake operator
            result = bpy.ops.zenv.textureproj_bake_mask()
            
            logger.info(f"  Operator result: {result}")
            
            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                obj.select_set(True)
            context.view_layer.objects.active = original_active
            
            if result == {'FINISHED'}:
                logger.info("Auto-baked visibility mask successfully")
                logger.info("  SUCCESS: Mask baked")
                return True
            else:
                logger.warning(f"Visibility mask bake returned: {result}")
                logger.info(f"  FAILED: Operator returned {result}")
                return False
                
        except Exception as e:
            logger.exception(f"Error auto-baking visibility mask: {e}")
            logger.info(f"  EXCEPTION: {e}")
            traceback.print_exc()
            return False
    
    def composite_mask_as_alpha(self, context, color_texture_path, target_obj):
        """Composite visibility mask as alpha channel - brute force with JSON tracking"""
        try:
            
            logger.info(f"Composite called with:")
            logger.info(f"  Color texture: {color_texture_path}")
            logger.info(f"  Target object: {target_obj.name}")
            
            # Find the visibility mask file
            mask_image_name = f"{target_obj.name}_visibility_mask"
            textures_folder = bpy.path.abspath("//textures/")
            mask_path = os.path.join(textures_folder, f"{mask_image_name}.png")
            
            logger.info(f"  Looking for mask: {mask_path}")
            logger.info(f"  Mask exists: {os.path.exists(mask_path)}")
            
            if not os.path.exists(mask_path):
                logger.warning(f"Visibility mask file not found: {mask_path}")
                logger.info(f"ERROR: Mask file not found!")
                return color_texture_path
            
            # Load color texture into Blender
            color_img = bpy.data.images.load(color_texture_path, check_existing=False)
            mask_img = bpy.data.images.load(mask_path, check_existing=False)
            
            width, height = color_img.size
            logger.info(f"Color: {width}x{height}, {color_img.channels} channels")
            logger.info(f"Mask: {mask_img.size[0]}x{mask_img.size[1]}, {mask_img.channels} channels")
            
            # Get raw pixel data
            color_pixels = list(color_img.pixels[:])
            mask_pixels = list(mask_img.pixels[:])
            
            # Find interesting sample pixels
            max_saturation = 0
            max_sat_coord = (width // 2, height // 2)
            white_mask_coord = None
            black_mask_coord = None
            zero_opacity_coord = None
            
            for y in range(height):
                for x in range(width):
                    pixel_idx = y * width + x
                    color_idx = pixel_idx * color_img.channels
                    mask_idx = pixel_idx * mask_img.channels
                    
                    # Get color RGB
                    if color_img.channels >= 3:
                        r = color_pixels[color_idx]
                        g = color_pixels[color_idx + 1]
                        b = color_pixels[color_idx + 2]
                    else:
                        r = g = b = color_pixels[color_idx]
                    
                    # Get mask value
                    mask_val = mask_pixels[mask_idx]
                    
                    # Find most saturated color pixel
                    saturation = max(r, g, b) - min(r, g, b)
                    if saturation > max_saturation:
                        max_saturation = saturation
                        max_sat_coord = (x, y)
                    
                    # Find white mask pixel (close to 1.0)
                    if white_mask_coord is None and mask_val > 0.9:
                        white_mask_coord = (x, y)
                    
                    # Find black mask pixel (close to 0.0)
                    if black_mask_coord is None and mask_val < 0.1:
                        black_mask_coord = (x, y)
                    
                    # Find zero opacity pixel (alpha channel if exists)
                    if zero_opacity_coord is None and color_img.channels == 4:
                        alpha = color_pixels[color_idx + 3]
                        if alpha < 0.1:
                            zero_opacity_coord = (x, y)
            
            # Fallback coordinates if not found
            if white_mask_coord is None:
                white_mask_coord = (width // 4, height // 4)
            if black_mask_coord is None:
                black_mask_coord = (width // 2, height // 4)
            if zero_opacity_coord is None:
                zero_opacity_coord = (3 * width // 4, height // 4)
            
            # Track sample pixels for JSON with labels
            sample_coords = {
                "top_left": (width // 4, height // 4),
                "center": (width // 2, height // 2),
                "bottom_right": (3 * width // 4, 3 * height // 4),
                "white_mask": white_mask_coord,
                "black_mask": black_mask_coord,
                "most_saturated": max_sat_coord,
                "zero_opacity": zero_opacity_coord
            }
            
            # Create output RGBA array
            total_pixels = width * height
            output_pixels = []
            debug_samples = {}
            
            # Process each pixel
            for y in range(height):
                for x in range(width):
                    pixel_idx = y * width + x
                    
                    # Color texture indices (RGB or RGBA)
                    color_idx = pixel_idx * color_img.channels
                    
                    # Mask texture indices (RGB or RGBA)
                    mask_idx = pixel_idx * mask_img.channels
                    
                    # Get RGB from color texture
                    if color_img.channels >= 3:
                        r = color_pixels[color_idx]
                        g = color_pixels[color_idx + 1]
                        b = color_pixels[color_idx + 2]
                    else:
                        # Grayscale
                        r = g = b = color_pixels[color_idx]
                    
                    # Get alpha from mask (use first channel)
                    alpha = mask_pixels[mask_idx]
                    
                    # Write RGBA
                    output_pixels.extend([r, g, b, alpha])
                    
                    # Track sample pixels
                    for label, coord in sample_coords.items():
                        if (x, y) == coord:
                            debug_samples[label] = {
                                "coord": [x, y],
                                "color_rgb": [r, g, b],
                                "mask_value": alpha,
                                "output_rgba": [r, g, b, alpha]
                            }
            
            # Create output image
            output_name = f"{target_obj.name}_baked_with_alpha"
            if output_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[output_name])
            
            output_img = bpy.data.images.new(
                name=output_name,
                width=width,
                height=height,
                alpha=True
            )
            
            # Write pixels
            output_img.pixels[:] = output_pixels
            output_img.update()
            
            # Save with alpha
            output_path = os.path.join(textures_folder, f"{output_name}.png")
            output_img.filepath_raw = output_path
            output_img.file_format = 'PNG'
            output_img.alpha_mode = 'STRAIGHT'
            output_img.save()
            
            # Write debug JSON only if debug mode is enabled
            if context.scene.zenv_debug_mode:
                debug_data = {
                    "color_texture": color_texture_path,
                    "mask_texture": mask_path,
                    "output_texture": output_path,
                    "dimensions": [width, height],
                    "color_channels": color_img.channels,
                    "mask_channels": mask_img.channels,
                    "sample_pixels": debug_samples,
                    "statistics": {
                        "total_pixels": total_pixels,
                        "color_min": min(color_pixels),
                        "color_max": max(color_pixels),
                        "mask_min": min(mask_pixels),
                        "mask_max": max(mask_pixels),
                        "output_alpha_min": min(output_pixels[3::4]),
                        "output_alpha_max": max(output_pixels[3::4])
                    }
                }
                
                debug_json_path = os.path.join(textures_folder, "debug_composite.json")
                with open(debug_json_path, 'w') as f:
                    json.dump(debug_data, f, indent=2)
                
                logger.info(f"Debug JSON: {debug_json_path}")
            
            logger.info(f"Composited mask as alpha: {output_path}")
            
            # Cleanup temp images
            bpy.data.images.remove(color_img)
            bpy.data.images.remove(mask_img)
            
            return output_path
            
        except Exception as e:
            logger.exception(f"Error compositing mask as alpha: {e}")
            return color_texture_path
    
    def apply_baked_texture(self, context, obj, texture_path):
        """Apply baked texture to original object"""
        mat = bpy.data.materials.new(name=f"MAT_BAKED_{os.path.basename(texture_path)}")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        
        # Create nodes
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        tex_image = nodes.new('ShaderNodeTexImage')
        output = nodes.new('ShaderNodeOutputMaterial')
        tex_coord = nodes.new('ShaderNodeTexCoord')
        mapping = nodes.new('ShaderNodeMapping')
        
        # Load and set image -  handle existing images. 
        # ``load_or_refresh_image`` contains more info 
        image = ZENV_TextureProj_Utils.load_or_refresh_image(texture_path)
        tex_image.image = image
        
        # Position nodes
        tex_coord.location = (-600, 0)
        mapping.location = (-400, 0)
        tex_image.location = (-200, 0)
        bsdf.location = (200, 0)
        output.location = (400, 0)
        
        # Link nodes
        links = mat.node_tree.links
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])
        links.new(tex_image.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Only wire the alpha channel when the user explicitly opted in
        # via "Use Visibility Mask as Alpha". Our bake images are always
        # created with ``alpha=True`` (RGBA), so a plain
        # ``image.channels == 4`` test would force every bake into a
        # transparent material -- and ``blend_method='BLEND'`` is the
        # EEVEE mode that produces per-face sorting artifacts on
        # concave / overlapping geometry. ``'CLIP'`` is alpha-tested and
        # has no sorting issues; 
        if context.scene.zenv_use_mask_as_alpha:
            links.new(tex_image.outputs['Alpha'], bsdf.inputs['Alpha'])
            mat.blend_method = 'CLIP'
            mat.shadow_method = 'CLIP'
            if hasattr(mat, 'surface_render_method'):
                mat.surface_render_method = 'DITHERED'
            logger.info("Connected alpha channel; material set to CLIP (alpha tested)")
        else:
            # Keep the material fully opaque so EEVEE renders without
            # transparency sorting.
            mat.blend_method = 'OPAQUE'
            if hasattr(mat, 'surface_render_method'):
                mat.surface_render_method = 'DITHERED'
        
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    def save_current_state(self, context):
        """Save current scene state"""
        return {
            'original_obj': context.active_object,
            'render_engine': context.scene.render.engine,
            'materials': {obj: list(obj.data.materials) for obj in context.selected_objects}
        }

    def restore_state(self, context, state):
        """Restore previous scene state"""
        context.scene.render.engine = state['render_engine']
        for obj, mats in state['materials'].items():
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)

class ZENV_OT_TextureProj_BakeVisibilityMask(bpy.types.Operator):
    """Bake visibility mask using camera ray casting"""
    bl_idname = "zenv.textureproj_bake_mask"
    bl_label = "Bake Visibility Mask"
    bl_description = "Bake a mask showing visible areas from camera using ray casting"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        """Bake visibility mask using pure ray casting - EXACT COPY from debug addon"""
        scene = context.scene
        if not scene.camera:
            fallback_cam = ZENV_TextureProj_Utils.find_any_camera(scene)
            if fallback_cam:
                scene.camera = fallback_cam
                self.report({'INFO'}, f"No active camera set. Using: {fallback_cam.name}")
            else:
                self.report({'ERROR'}, "No active camera and no camera found in scene")
                return {'CANCELLED'}

        camera = scene.camera
        target_obj = context.active_object
        
        if not camera:
            self.report({'ERROR'}, "No active camera in scene")
            return {'CANCELLED'}
        
        if not target_obj or target_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        # Check UV layer
        if not target_obj.data.uv_layers:
            self.report({'ERROR'}, "Mesh has no UV layers")
            return {'CANCELLED'}
        
        # Get settings
        num_rays = scene.zenv_mask_sample_count
        
        # Use texture resolution (supports non-square)
        texture_width, texture_height = ZENV_TextureProj_Utils.get_texture_resolution(context)
        
        # Get camera location
        cam_location = camera.matrix_world.to_translation()
        
        # Build BVH tree with triangulated mesh for clean geometry
        depsgraph = context.evaluated_depsgraph_get()
        mesh_eval = target_obj.evaluated_get(depsgraph)
        
        # Create a temporary triangulated copy of the mesh
        bm = bmesh.new()
        bm.from_mesh(mesh_eval.data)
        
        # Triangulate all faces
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        
        # Create temporary mesh
        temp_mesh = bpy.data.meshes.new("TEMP_TRIANGULATED")
        bm.to_mesh(temp_mesh)
        bm.free()
        
        # Apply world transform and build BVH
        vertices = [target_obj.matrix_world @ v.co for v in temp_mesh.vertices]
        polygons = [[v for v in poly.vertices] for poly in temp_mesh.polygons]
        bvh = BVHTree.FromPolygons(vertices, polygons)
        
        # Use triangulated mesh for UV mapping
        mesh_data = temp_mesh
        
        logger.info(f"Triangulated mesh: {len(temp_mesh.polygons)} triangles (was {len(mesh_eval.data.polygons)} faces)")
        
        # Generate camera rays using shared function
        ray_samples, samples_per_axis = self.generate_camera_rays(camera, context, num_rays)
        
        # Cast rays and collect hit points with UVs
        actual_ray_count = len(ray_samples)
        logger.info(f"\n=== Baking visibility mask: {actual_ray_count} rays ({samples_per_axis}x{samples_per_axis} grid) ===")
        
        hit_points_uv = []  # List of (uv_x, uv_y, visibility) tuples
        uv_layer = mesh_data.uv_layers.active.data
        
        start_time = time.time()
        last_report = start_time
        
        for i, ray_data in enumerate(ray_samples):
            # Progress reporting every 2 seconds
            current_time = time.time()
            if current_time - last_report > 2.0:
                progress = (i / actual_ray_count) * 100
                logger.info(f"  Progress: {progress:.1f}% ({i}/{actual_ray_count} rays)")
                last_report = current_time

            # Perspective rays are plain Vector directions; orthographic
            # rays are (origin_offset, direction) tuples.
            if isinstance(ray_data, tuple):
                ray_origin_offset, ray_direction = ray_data
                ray_origin = cam_location + ray_origin_offset
            else:
                ray_direction = ray_data
                ray_origin = cam_location

            hit_location, hit_normal, hit_index, hit_distance = bvh.ray_cast(
                ray_origin, ray_direction, 10000.0
            )
            
            if hit_location and hit_index is not None:
                # Get the hit polygon
                poly = mesh_data.polygons[hit_index]
                
                # Get UV coordinates for this polygon
                poly_uvs = []
                poly_verts = []
                for loop_idx in poly.loop_indices:
                    uv = uv_layer[loop_idx].uv
                    poly_uvs.append(Vector((uv.x, uv.y)))
                    vert_idx = mesh_data.loops[loop_idx].vertex_index
                    poly_verts.append(vertices[vert_idx])
                
                # Find barycentric coordinates of hit point in the polygon
                # Check all triangles in the polygon (for quads and n-gons)
                if len(poly_verts) >= 3:
                    uv_found = False
                    # For triangle: check (0,1,2)
                    # For quad: check (0,1,2) and (0,2,3)
                    # For n-gon: check (0,1,2), (0,2,3), (0,3,4), etc.
                    num_triangles = len(poly_verts) - 2
                    for tri_idx in range(num_triangles):
                        # Triangle fan from first vertex
                        v0 = poly_verts[0]
                        v1 = poly_verts[tri_idx + 1]
                        v2 = poly_verts[tri_idx + 2]
                        
                        uv0 = poly_uvs[0]
                        uv1 = poly_uvs[tri_idx + 1]
                        uv2 = poly_uvs[tri_idx + 2]
                        
                        # Calculate barycentric coordinates
                        bary = self.barycentric_coords_3d(hit_location, v0, v1, v2)
                        
                        if bary and all(b >= -0.001 for b in bary):  # Check if inside triangle
                            # Interpolate UV coordinates
                            uv_hit = bary[0] * uv0 + bary[1] * uv1 + bary[2] * uv2
                            hit_points_uv.append((uv_hit.x, uv_hit.y, 1.0))
                            uv_found = True
                            break
                    
                    # Fallback: if barycentric failed but we checked all triangles, use polygon center UV
                    if not uv_found and tri_idx == num_triangles - 1:
                        # Use average of all UV coordinates as fallback
                        uv_center = Vector((0, 0))
                        for uv in poly_uvs:
                            uv_center += uv
                        uv_center /= len(poly_uvs)
                        
                        hit_points_uv.append((uv_center.x, uv_center.y, 1.0))
        
        elapsed = time.time() - start_time
        logger.info(f"Ray casting complete in {elapsed:.2f}s")
        logger.info(f"Found {len(hit_points_uv)} visible UV points ({100*len(hit_points_uv)/actual_ray_count:.1f}% hit rate)")
        
        # Create fresh image (remove old one if exists)
        image_name = f"{target_obj.name}_visibility_mask"
        if image_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[image_name])
        
        image = bpy.data.images.new(image_name, texture_width, texture_height, alpha=False)
        
        # Initialize to black
        pixels = np.zeros(texture_width * texture_height * 4, dtype=np.float32)
        
        # Write hit points to texture with small radius to fill gaps
        # Use average of width and height for splat radius calculation
        avg_texture_size = (texture_width + texture_height) / 2
        dilation_amount = context.scene.zenv_mask_dilation
        if dilation_amount == 0:
            splat_radius = 0
        else:
            splat_radius = max(1, int(avg_texture_size / (samples_per_axis * 2)))  # Adaptive radius
        logger.info(f"Using splat radius: {splat_radius} pixels (texture: {texture_width}x{texture_height})")
        
        for uv_x, uv_y, visibility in hit_points_uv:
            # Convert UV to pixel coordinates (don't flip Y - Blender handles it)
            px = int(uv_x * (texture_width - 1))
            py = int(uv_y * (texture_height - 1))  # No flip
            
            # Splat in a small radius around the hit point
            for dy in range(-splat_radius, splat_radius + 1):
                for dx in range(-splat_radius, splat_radius + 1):
                    write_x = px + dx
                    write_y = py + dy
                    
                    if 0 <= write_x < texture_width and 0 <= write_y < texture_height:
                        # Optional: use distance falloff for softer edges
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist <= splat_radius:
                            idx = (write_y * texture_width + write_x) * 4
                            # Use max to avoid overwriting brighter values
                            pixels[idx] = max(pixels[idx], visibility)
                            pixels[idx + 1] = max(pixels[idx + 1], visibility)
                            pixels[idx + 2] = max(pixels[idx + 2], visibility)
                            pixels[idx + 3] = 1.0
        
        # Dilate mask - expand white pixels
        if dilation_amount > 0:
            logger.info(f"Dilating mask (expanding white pixels by {dilation_amount})...")
            pixels_2d = pixels.reshape((texture_height, texture_width, 4))
            
            # Perform dilation multiple times for larger expansion
            for iteration in range(dilation_amount):
                dilated = pixels_2d.copy()
                
                for y in range(texture_height):
                    for x in range(texture_width):
                        # Check if current pixel is black (< 0.5)
                        if pixels_2d[y, x, 0] < 0.5:
                            # Check 8 neighbors
                            for dy in [-1, 0, 1]:
                                for dx in [-1, 0, 1]:
                                    if dx == 0 and dy == 0:
                                        continue
                                    nx, ny = x + dx, y + dy
                                    if 0 <= nx < texture_width and 0 <= ny < texture_height:
                                        # If neighbor is white (>= 0.5), make current pixel white
                                        if pixels_2d[ny, nx, 0] >= 0.5:
                                            dilated[y, x, 0] = 1.0
                                            dilated[y, x, 1] = 1.0
                                            dilated[y, x, 2] = 1.0
                                            dilated[y, x, 3] = 1.0
                                            break
                                if dilated[y, x, 0] >= 0.5:
                                    break
                
                # Update for next iteration
                pixels_2d = dilated
            
            # Flatten back to 1D
            pixels = pixels_2d.flatten()
        else:
            logger.info("Mask dilation disabled (set to 0)")
        
        # Update image
        image.pixels[:] = pixels
        image.update()
        
        # Save image
        textures_folder = bpy.path.abspath("//textures/")
        if not os.path.exists(textures_folder):
            os.makedirs(textures_folder)
        image_path = os.path.join(textures_folder, f"{image_name}.png")
        image.filepath_raw = image_path
        image.file_format = 'PNG'
        image.save()
        
        logger.info(f"Saved visibility mask to: {image_path}")

        # Apply gradient falloff / margin erosion if requested.
        if context.scene.zenv_mask_falloff > 0 or context.scene.zenv_mask_margin > 0:
            self.apply_mask_falloff(
                image_path,
                context.scene.zenv_mask_margin,
                context.scene.zenv_mask_falloff
            )

        # Clean up temporary mesh
        bpy.data.meshes.remove(temp_mesh)

        self.report({'INFO'}, f"Baked visibility mask: {len(hit_points_uv)} visible points -> {image_path}")
        return {'FINISHED'}
    
    def generate_camera_rays(self, camera, context, num_rays):
        """Generate ray directions through camera pixels.

        For perspective cameras the rays fan out from the camera origin
        using the field of view.  For orthographic cameras the rays are
        parallel and evenly spaced across the orthographic scale, which
        matches how an orthographic projection actually works.
        """
        render = context.scene.render
        res_x = render.resolution_x
        res_y = render.resolution_y

        samples_per_axis = int(num_rays ** 0.5)

        # Get camera parameters
        sensor_width = camera.data.sensor_width
        sensor_height = camera.data.sensor_height
        focal_length = camera.data.lens
        aspect_ratio = res_x / res_y if res_y > 0 else 1.0

        if camera.data.sensor_fit == 'AUTO':
            sensor_fit = 'HORIZONTAL' if aspect_ratio > 1.0 else 'VERTICAL'
        else:
            sensor_fit = camera.data.sensor_fit

        ray_samples = []
        cam_matrix = camera.matrix_world

        if camera.data.type == 'ORTHO':
            # Orthographic: parallel rays, evenly spaced across the
            # orthographic scale.  The ray origin is offset in the
            # camera's local X/Y plane and the direction is straight
            # forward (-Z in camera space).
            ortho_scale = camera.data.ortho_scale
            if aspect_ratio >= 1.0:
                half_w = ortho_scale / 2.0
                half_h = ortho_scale / (2.0 * aspect_ratio)
            else:
                half_w = ortho_scale * aspect_ratio / 2.0
                half_h = ortho_scale / 2.0

            forward_cam = Vector((0.0, 0.0, -1.0))
            forward_world = (cam_matrix.to_3x3() @ forward_cam).normalized()
            right_world = (cam_matrix.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
            up_world = (cam_matrix.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()

            for y in range(samples_per_axis):
                for x in range(samples_per_axis):
                    ndc_x = (x + 0.5) / samples_per_axis * 2.0 - 1.0
                    ndc_y = (y + 0.5) / samples_per_axis * 2.0 - 1.0
                    offset = (right_world * ndc_x * half_w) + (up_world * ndc_y * half_h)
                    # Store (origin_offset, direction) tuples for ortho
                    ray_samples.append((offset, forward_world))
            return ray_samples, samples_per_axis

        # Perspective: rays fan out from the camera origin.
        if sensor_fit == 'HORIZONTAL':
            fov = 2.0 * math.atan(sensor_width / (2.0 * focal_length))
        else:
            fov = 2.0 * math.atan(sensor_height / (2.0 * focal_length))

        for y in range(samples_per_axis):
            for x in range(samples_per_axis):
                pixel_x = (x + 0.5) / samples_per_axis
                pixel_y = (y + 0.5) / samples_per_axis

                ndc_x = pixel_x * 2.0 - 1.0
                ndc_y = pixel_y * 2.0 - 1.0

                if sensor_fit == 'HORIZONTAL':
                    ndc_x *= math.tan(fov / 2.0)
                    ndc_y *= math.tan(fov / 2.0) / aspect_ratio
                else:
                    ndc_x *= math.tan(fov / 2.0) * aspect_ratio
                    ndc_y *= math.tan(fov / 2.0)

                ray_dir_cam = Vector((ndc_x, ndc_y, -1.0)).normalized()
                ray_dir_world = (cam_matrix.to_3x3() @ ray_dir_cam).normalized()

                ray_samples.append(ray_dir_world)

        return ray_samples, samples_per_axis
    
    def barycentric_coords_3d(self, p, a, b, c):
        """Calculate barycentric coordinates of point p in 3D triangle abc"""
        v0 = b - a
        v1 = c - a
        v2 = p - a

        d00 = v0.dot(v0)
        d01 = v0.dot(v1)
        d11 = v1.dot(v1)
        d20 = v2.dot(v0)
        d21 = v2.dot(v1)

        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-8:
            return None

        v = (d11 * d20 - d01 * d21) / denom
        w = (d00 * d21 - d01 * d20) / denom
        u = 1.0 - v - w

        return (u, v, w)

    def barycentric_coords(self, p, a, b, c):
        """Calculate barycentric coordinates of 2D point p in 2D triangle abc.

        Uses the Vector 2D cross-product approach.  Each argument may be a
        ``mathutils.Vector`` or any sequence of two floats (UV coordinates).
        Returns ``(u, v, w)`` or ``None`` for degenerate triangles.
        """
        # Extract x/y so we work with plain floats regardless of input type.
        px, py = p[0], p[1]
        ax, ay = a[0], a[1]
        bx, by = b[0], b[1]
        cx, cy = c[0], c[1]

        # Vectors from a
        v0x, v0y = bx - ax, by - ay   # ab
        v1x, v1y = cx - ax, cy - ay   # ac
        v2x, v2y = px - ax, py - ay   # ap

        # 2D dot products
        d00 = v0x * v0x + v0y * v0y
        d01 = v0x * v1x + v0y * v1y
        d11 = v1x * v1x + v1y * v1y
        d20 = v2x * v0x + v2y * v0y
        d21 = v2x * v1x + v2y * v1y

        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-12:
            return None

        v = (d11 * d20 - d01 * d21) / denom
        w = (d00 * d21 - d01 * d20) / denom
        u = 1.0 - v - w

        return (u, v, w)

    def apply_mask_falloff(self, image_path, margin_pixels, falloff_pixels):
        """
        Apply gradient falloff from mask edges using distance transform.
        Creates smooth transition from white to black.
        """
        try:
            from scipy import ndimage
            
            # Load image using Blender
            img = bpy.data.images.load(image_path, check_existing=True)
            width = img.size[0]
            height = img.size[1]
            
            # Get pixels
            pixels = np.array(img.pixels[:]).reshape((height, width, img.channels))
            
            # Extract grayscale (take R channel)
            img_array = pixels[:, :, 0]
            
            # Flip Y (Blender images are bottom-up)
            img_array = np.flipud(img_array)
            
            # Create binary mask (threshold at 0.5)
            binary_mask = (img_array > 0.5).astype(np.uint8)
            
            # Apply margin erosion first
            if margin_pixels > 0:
                for i in range(margin_pixels // 2):
                    binary_mask = ndimage.binary_erosion(binary_mask).astype(np.uint8)
            
            # Calculate distance transform from edges
            # Distance from white areas (inverted for falloff calculation)
            distance_from_edge = ndimage.distance_transform_edt(binary_mask)
            
            # Normalize distance to falloff range
            if falloff_pixels > 0:
                # Create gradient: 1.0 at center, 0.0 at falloff distance
                gradient = np.clip(distance_from_edge / falloff_pixels, 0, 1)
            else:
                # No falloff, just use binary mask
                gradient = binary_mask.astype(np.float32)
            
            # Flip back for Blender
            gradient = np.flipud(gradient)
            
            # Flatten and convert to RGBA
            gradient_flat = gradient.flatten()
            pixels_out = np.zeros(width * height * 4, dtype=np.float32)
            pixels_out[0::4] = gradient_flat  # R
            pixels_out[1::4] = gradient_flat  # G
            pixels_out[2::4] = gradient_flat  # B
            pixels_out[3::4] = 1.0            # A
            
            # Write back to image
            img.pixels[:] = pixels_out
            img.update()
            img.save_render(image_path)
            
            logger.info(f"Applied mask falloff: margin={margin_pixels}px, falloff={falloff_pixels}px")
            return image_path
            
        except ImportError as e:
            logger.warning(f"scipy not available for gradient falloff: {e}")
            logger.warning("Install scipy for gradient falloff support: pip install scipy")
            return image_path
        except Exception as e:
            logger.exception(f"Error applying mask falloff: {e}")
            return image_path

    def save_current_state(self, context):
        """Save current scene state"""
        return {
            'original_obj': context.active_object,
            'render_engine': context.scene.render.engine,
            'view_transform': context.scene.view_settings.view_transform,
        }

    def restore_state(self, context, state):
        """Restore previous scene state"""
        context.scene.render.engine = state['render_engine']
        context.scene.view_settings.view_transform = state['view_transform']
#endregion

#region PANEL
class ZENV_PT_TextureProj(bpy.types.Panel):
    """Panel for texture projection tools"""
    bl_label = "TEX Texture Projection"
    bl_idname = "ZENV_PT_textureproj"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout

        # Camera settings
        box = layout.box()
        box.label(text="Camera:", icon='CAMERA_DATA')
        box.prop(context.scene, "zenv_orthographic")
        box.prop(context.scene, "zenv_square_camera")
        box.operator("zenv.textureproj_create_camera", icon='ADD')
        
        # Show ortho scale only for orthographic cameras
        if context.scene.zenv_orthographic:
            box.prop(context.scene, "zenv_ortho_scale")
        
        # Show appropriate camera resolution controls based on square_camera setting
        if context.scene.zenv_square_camera:
            box.prop(context.scene, "zenv_texture_resolution", text="Camera Resolution")
        else:
            box.label(text="Camera Resolution:")
            row = box.row(align=True)
            row.prop(context.scene, "zenv_camera_resolution_x")
            row.prop(context.scene, "zenv_camera_resolution_y")
            row.operator("zenv.textureproj_get_camera_resolution", text="", icon='IMPORT')

        # Texture settings
        box = layout.box()
        box.label(text="Texture:", icon='TEXTURE')
        
        col = box.column(align=True)
        
        # File path property with browse button
        row = col.row(align=True)
        row.prop(context.scene, "zenv_texture_path", text="")
        row.operator("zenv.textureproj_drop_image", text="", icon='FILEBROWSER')
        
        # Display current image info if available
        if context.scene.zenv_texture_path:
            image_path = bpy.path.abspath(context.scene.zenv_texture_path)
            if os.path.isfile(image_path):
                filename = os.path.basename(image_path)
                col.separator()
                info_col = col.column(align=True)
                info_col.label(text=f"File: {filename}", icon='IMAGE_DATA')
                
                # Try to get image dimensions
                try:
                    img = bpy.data.images.load(image_path, check_existing=True)
                    if img and img.size[0] > 0:
                        info_col.label(text=f"Size: {img.size[0]}x{img.size[1]}px")
                except RuntimeError:
                    pass
        
        box.prop(context.scene, "zenv_square_texture")
        
        # Show appropriate texture resolution controls based on square_texture setting
        if context.scene.zenv_square_texture:
            box.prop(context.scene, "zenv_texture_resolution")
        else:
            box.label(text="Texture Resolution:")
            row = box.row(align=True)
            row.prop(context.scene, "zenv_texture_resolution_x")
            row.prop(context.scene, "zenv_texture_resolution_y")

        # Baking
        box = layout.box()
        box.label(text="Baking:", icon='RENDER_RESULT')
        box.operator("zenv.textureproj_bake", icon='RENDER_STILL')
        active_obj = context.active_object
        if not (active_obj and active_obj.type == 'MESH'):
            box.label(text="No Selected Mesh", icon='INFO')
        else:
            if not context.scene.zenv_texture_path:
                box.label(text="No Texture Selected", icon='INFO')

            if not context.scene.camera:
                fallback_cam = ZENV_TextureProj_Utils.find_any_camera(context.scene)
                if fallback_cam:
                    box.label(text=f"No Active Camera (will use {fallback_cam.name})", icon='INFO')
                else:
                    box.label(text="No Camera In Scene", icon='INFO')
        box.prop(context.scene, "zenv_bake_margin")
        box.prop(context.scene, "zenv_use_mask_as_alpha")

        # Visibility Mask
        box.operator("zenv.textureproj_bake_mask", icon='TEXTURE')
        box.prop(context.scene, "zenv_mask_sample_count")
        box.prop(context.scene, "zenv_mask_dilation")
        box.prop(context.scene, "zenv_debug_mode")
#endregion

#region REG
classes = (
    ZENV_OT_TextureProj_CreateCamera,
    ZENV_OT_TextureProj_GetCameraResolution,
    ZENV_OT_TextureProj_DropImage,
    ZENV_OT_TextureProj_BakeTexture,
    ZENV_OT_TextureProj_BakeVisibilityMask,
    ZENV_PT_TextureProj,
)

def register():
    """Register the addon classes, properties, and logger."""
    global _zenv_tex_proj_cam_console_handler
    if _zenv_tex_proj_cam_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_tex_proj_cam_console_handler = handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_TextureProj_Properties.register()

def unregister():
    """Unregister the addon classes, properties, and logger."""
    global _zenv_tex_proj_cam_console_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_TextureProj_Properties.unregister()
    if _zenv_tex_proj_cam_console_handler is not None:
        try:
            logger.removeHandler(_zenv_tex_proj_cam_console_handler)
        except ValueError:
            pass
        _zenv_tex_proj_cam_console_handler = None

if __name__ == "__main__":
    register()
#endregion
