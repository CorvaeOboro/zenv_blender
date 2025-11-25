bl_info = {
    "name": 'TEX Camera Projection',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250124',
    "description": 'Create camera from current view and bake projected textures',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Texture',
    "group_prefix": 'TEX',
    "description_short": 'Create camera from current view and bake projected textures',
    "description_medium": 'texture projection from camera - creates square orthographic camera from current view , and the camera projects image onto mesh baking to texture . workflow similar to "quick edits" in texture paint mode , now with permanent cameras',
    "description_long": """
TEXTURE PROJECTION FROM CAMERA
 create camera from current view and project textures
 bake textures using camera projection and visibility masks
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
import shutil
import numpy as np
from datetime import datetime
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
import math
import logging

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_TextureProj_Properties:
    """Property management for texture projection addon"""
    
    @staticmethod
    def update_ortho_scale(self, context):
        """Update orthographic scale of active camera"""
        camera = context.scene.camera
        if camera and camera.data.type == 'ORTHO':
            camera.data.ortho_scale = self.zenv_ortho_scale

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
        bpy.types.Scene.zenv_texture_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        bpy.types.Scene.zenv_texture_path = bpy.props.StringProperty(
            name="Texture Path",
            description="Path to the texture file",
            subtype='FILE_PATH'
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
        del bpy.types.Scene.zenv_ortho_scale
        del bpy.types.Scene.zenv_texture_resolution
        del bpy.types.Scene.zenv_texture_path
        del bpy.types.Scene.zenv_debug_mode
        del bpy.types.Scene.zenv_square_texture
        del bpy.types.Scene.zenv_orthographic
        del bpy.types.Scene.zenv_texture_resolution_x
        del bpy.types.Scene.zenv_texture_resolution_y
        del bpy.types.Scene.zenv_square_camera
        del bpy.types.Scene.zenv_camera_resolution_x
        del bpy.types.Scene.zenv_camera_resolution_y
        del bpy.types.Scene.zenv_mask_margin
        del bpy.types.Scene.zenv_mask_falloff
        del bpy.types.Scene.zenv_mask_sample_count
        del bpy.types.Scene.zenv_mask_sample_density
        del bpy.types.Scene.zenv_use_mask_as_alpha
        del bpy.types.Scene.zenv_mask_dilation

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

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
        context.scene.render.bake.margin = 16
        context.scene.render.bake.use_clear = True  # Clear image before baking
        
        # Set high quality settings
        context.scene.cycles.use_denoising = True
        context.scene.cycles.preview_denoiser = 'OPTIX'
        context.scene.cycles.use_high_quality_normals = True

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

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
        """Set up perspective camera properties"""
        camera.data.type = 'PERSP'
        
        # Match FOV to current view if possible
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                region_3d = space.region_3d
                
                # Set clip distances
                camera.data.clip_start = space.clip_start
                camera.data.clip_end = space.clip_end
                
                # Try to match lens/FOV from viewport
                if region_3d.view_perspective == 'PERSP':
                    # Calculate lens from view distance and perspective
                    camera.data.lens = 50  # Default lens
                else:
                    # Use default perspective settings
                    camera.data.lens = 50
                    
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

class ZENV_OT_TextureProj_BakeTexture(bpy.types.Operator):
    """Bake texture using camera projection"""
    bl_idname = "zenv.textureproj_bake"
    bl_label = "Bake Texture"
    bl_description = "Bake texture using camera projection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'MESH' and 
                context.scene.camera and
                context.scene.zenv_texture_path)

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
                print("\n=== AUTO-BAKING VISIBILITY MASK ===")
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
                print("\n=== COMPOSITING MASK AS ALPHA ===")
                print(f"Color texture path: {baked_path}")
                
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
        if not context.scene.camera:
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
        
        # Load image and ensure it's fresh
        image_name = os.path.basename(image_path)
        if image_name in bpy.data.images:
            image = bpy.data.images[image_name]
            # Reload from disk to ensure we have the latest version
            image.reload()
        else:
            image = bpy.data.images.load(image_path, check_existing=True)
        
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
        # Setup render settings
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.device = 'GPU'
        context.scene.cycles.samples = 1
        context.scene.cycles.bake_type = 'DIFFUSE'
        context.scene.render.bake.use_pass_direct = True
        context.scene.render.bake.use_pass_indirect = False
        context.scene.render.bake.use_pass_color = True
        context.scene.render.bake.margin = 16
        
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
            margin=16
        )
        
        # Save result
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath_raw)
            return bake_image.filepath_raw
            
        return None

    def auto_bake_visibility_mask(self, context, target_obj):
        """Automatically bake visibility mask for the target object"""
        try:
            print(f"Auto-bake visibility mask starting...")
            print(f"  Target object: {target_obj.name}")
            print(f"  Camera: {context.scene.camera}")
            print(f"  Has UV layers: {len(target_obj.data.uv_layers) > 0 if target_obj.data.uv_layers else False}")
            
            # Save current selection
            original_active = context.view_layer.objects.active
            original_selected = [obj for obj in context.selected_objects]
            
            print(f"  Original active: {original_active.name if original_active else None}")
            print(f"  Original selected: {[o.name for o in original_selected]}")
            
            # Select target object
            bpy.ops.object.select_all(action='DESELECT')
            target_obj.select_set(True)
            context.view_layer.objects.active = target_obj
            
            print(f"  Set active to: {context.view_layer.objects.active.name}")
            print(f"  Calling bake mask operator...")
            
            # Call the visibility mask bake operator
            result = bpy.ops.zenv.textureproj_bake_mask()
            
            print(f"  Operator result: {result}")
            
            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                obj.select_set(True)
            context.view_layer.objects.active = original_active
            
            if result == {'FINISHED'}:
                logger.info("Auto-baked visibility mask successfully")
                print("  SUCCESS: Mask baked")
                return True
            else:
                logger.warning(f"Visibility mask bake returned: {result}")
                print(f"  FAILED: Operator returned {result}")
                return False
                
        except Exception as e:
            logger.exception(f"Error auto-baking visibility mask: {e}")
            print(f"  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def composite_mask_as_alpha(self, context, color_texture_path, target_obj):
        """Composite visibility mask as alpha channel - brute force with JSON tracking"""
        try:
            import json
            
            print(f"Composite called with:")
            print(f"  Color texture: {color_texture_path}")
            print(f"  Target object: {target_obj.name}")
            
            # Find the visibility mask file
            mask_image_name = f"{target_obj.name}_visibility_mask"
            textures_folder = bpy.path.abspath("//textures/")
            mask_path = os.path.join(textures_folder, f"{mask_image_name}.png")
            
            print(f"  Looking for mask: {mask_path}")
            print(f"  Mask exists: {os.path.exists(mask_path)}")
            
            if not os.path.exists(mask_path):
                logger.warning(f"Visibility mask file not found: {mask_path}")
                print(f"ERROR: Mask file not found!")
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
        
        # Load and set image - properly handle existing images
        image_name = os.path.basename(texture_path)
        
        # Check if image already exists in Blender's data
        if image_name in bpy.data.images:
            image = bpy.data.images[image_name]
            # Reload from disk to get fresh data
            image.reload()
        else:
            # Load new image
            image = bpy.data.images.load(texture_path, check_existing=True)
        
        # Ensure image is packed or has valid filepath
        image.filepath = texture_path
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
        
        # Connect alpha if image has it
        if image.channels == 4 or 'alpha' in texture_path.lower():
            links.new(tex_image.outputs['Alpha'], bsdf.inputs['Alpha'])
            # Enable transparency in material
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'CLIP'
            logger.info("Connected alpha channel and enabled transparency")
        
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

    def cleanup(self, context, state):
        """Clean up temporary objects"""
        if not context.scene.zenv_debug_mode:
            bpy.data.objects.remove(bpy.data.objects.get("temp_camera_proj_mesh"), do_unlink=True)
            bpy.data.objects.remove(bpy.data.objects.get("temp_bake_setup_mesh"), do_unlink=True)

class ZENV_OT_TextureProj_BakeVisibilityMask(bpy.types.Operator):
    """Bake visibility mask using camera ray casting"""
    bl_idname = "zenv.textureproj_bake_mask"
    bl_label = "Bake Visibility Mask"
    bl_description = "Bake a mask showing visible areas from camera using ray casting"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'MESH' and 
                context.scene.camera)

    def execute(self, context):
        """Bake visibility mask using pure ray casting - EXACT COPY from debug addon"""
        scene = context.scene
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
        texture_size = scene.zenv_texture_resolution
        
        # Get camera location
        cam_location = camera.matrix_world.to_translation()
        
        # Build BVH tree with triangulated mesh for clean geometry
        depsgraph = context.evaluated_depsgraph_get()
        mesh_eval = target_obj.evaluated_get(depsgraph)
        
        # Create a temporary triangulated copy of the mesh
        import bmesh
        from mathutils.bvhtree import BVHTree
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
        
        print(f"Triangulated mesh: {len(temp_mesh.polygons)} triangles (was {len(mesh_eval.data.polygons)} faces)")
        
        # Generate camera rays using shared function
        ray_samples, samples_per_axis = self.generate_camera_rays(camera, context, num_rays)
        
        # Cast rays and collect hit points with UVs
        actual_ray_count = len(ray_samples)
        print(f"\n=== Baking visibility mask: {actual_ray_count} rays ({samples_per_axis}×{samples_per_axis} grid) ===")
        
        hit_points_uv = []  # List of (uv_x, uv_y, visibility) tuples
        uv_layer = mesh_data.uv_layers.active.data
        
        import time
        start_time = time.time()
        last_report = start_time
        
        for i, ray_direction in enumerate(ray_samples):
            # Progress reporting every 2 seconds
            current_time = time.time()
            if current_time - last_report > 2.0:
                progress = (i / actual_ray_count) * 100
                print(f"  Progress: {progress:.1f}% ({i}/{actual_ray_count} rays)")
                last_report = current_time
            
            hit_location, hit_normal, hit_index, hit_distance = bvh.ray_cast(
                cam_location, ray_direction, 10000.0
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
        print(f"Ray casting complete in {elapsed:.2f}s")
        print(f"Found {len(hit_points_uv)} visible UV points ({100*len(hit_points_uv)/actual_ray_count:.1f}% hit rate)")
        
        # Create fresh image (remove old one if exists)
        image_name = f"{target_obj.name}_visibility_mask"
        if image_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[image_name])
        
        image = bpy.data.images.new(image_name, texture_size, texture_size, alpha=False)
        
        # Initialize to black
        pixels = np.zeros(texture_size * texture_size * 4, dtype=np.float32)
        
        # Write hit points to texture with small radius to fill gaps
        splat_radius = max(1, int(texture_size / (samples_per_axis * 2)))  # Adaptive radius
        print(f"Using splat radius: {splat_radius} pixels")
        
        for uv_x, uv_y, visibility in hit_points_uv:
            # Convert UV to pixel coordinates (don't flip Y - Blender handles it)
            px = int(uv_x * (texture_size - 1))
            py = int(uv_y * (texture_size - 1))  # No flip
            
            # Splat in a small radius around the hit point
            for dy in range(-splat_radius, splat_radius + 1):
                for dx in range(-splat_radius, splat_radius + 1):
                    write_x = px + dx
                    write_y = py + dy
                    
                    if 0 <= write_x < texture_size and 0 <= write_y < texture_size:
                        # Optional: use distance falloff for softer edges
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist <= splat_radius:
                            idx = (write_y * texture_size + write_x) * 4
                            # Use max to avoid overwriting brighter values
                            pixels[idx] = max(pixels[idx], visibility)
                            pixels[idx + 1] = max(pixels[idx + 1], visibility)
                            pixels[idx + 2] = max(pixels[idx + 2], visibility)
                            pixels[idx + 3] = 1.0
        
        # Dilate mask - expand white pixels
        dilation_amount = context.scene.zenv_mask_dilation
        if dilation_amount > 0:
            print(f"Dilating mask (expanding white pixels by {dilation_amount})...")
            pixels_2d = pixels.reshape((texture_size, texture_size, 4))
            
            # Perform dilation multiple times for larger expansion
            for iteration in range(dilation_amount):
                dilated = pixels_2d.copy()
                
                for y in range(texture_size):
                    for x in range(texture_size):
                        # Check if current pixel is black (< 0.5)
                        if pixels_2d[y, x, 0] < 0.5:
                            # Check 8 neighbors
                            for dy in [-1, 0, 1]:
                                for dx in [-1, 0, 1]:
                                    if dx == 0 and dy == 0:
                                        continue
                                    nx, ny = x + dx, y + dy
                                    if 0 <= nx < texture_size and 0 <= ny < texture_size:
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
            print("Mask dilation disabled (set to 0)")
        
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
        
        print(f"Saved visibility mask to: {image_path}")
        
        # Clean up temporary mesh
        bpy.data.meshes.remove(temp_mesh)
        
        self.report({'INFO'}, f"Baked visibility mask: {len(hit_points_uv)} visible points -> {image_path}")
        return {'FINISHED'}
    
    def generate_camera_rays(self, camera, context, num_rays):
        """Generate ray directions through camera pixels"""
        # Get render resolution
        if camera.data.type == 'PERSP':
            render = context.scene.render
            res_x = render.resolution_x
            res_y = render.resolution_y
        else:
            res_x = res_y = 1024
        
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
        
        if sensor_fit == 'HORIZONTAL':
            fov = 2.0 * math.atan(sensor_width / (2.0 * focal_length))
        else:
            fov = 2.0 * math.atan(sensor_height / (2.0 * focal_length))
        
        ray_samples = []
        cam_matrix = camera.matrix_world
        
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
    
    def transfer_camera_to_uv_space(self, context, mask_mesh, camera_mask_path, uv_mask_image):
        """
        UV-space sampling with geometric ray casting for visibility:
        1. For each UV pixel, find its world position
        2. Cast ray from camera to check visibility (not occluded, facing camera)
        3. Write visibility to UV texture
        """
        import numpy as np
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        
        # Get UV resolution
        uv_width = uv_mask_image.size[0]
        uv_height = uv_mask_image.size[1]
        
        # Create UV mask array
        uv_array = np.zeros((uv_height, uv_width), dtype=np.float32)
        
        # Get camera and mesh data
        camera = context.scene.camera
        depsgraph = context.evaluated_depsgraph_get()
        mesh_eval = mask_mesh.evaluated_get(depsgraph)
        
        # Get UV layer
        if not mesh_eval.data.uv_layers:
            self.report({'ERROR'}, "Mesh has no UV layers! Please unwrap the mesh first.")
            logger.error("Mesh has no UV layers")
            return
        
        uv_layer = mesh_eval.data.uv_layers.active.data
        
        # Validate UVs - check if they're all at the same position
        logger.info("Validating UV layout...")
        uv_positions = set()
        for loop in mesh_eval.data.loops:
            uv = uv_layer[loop.index].uv
            uv_positions.add((round(uv.x, 4), round(uv.y, 4)))
        
        if len(uv_positions) < 10:
            self.report({'ERROR'}, f"Invalid UV layout! Only {len(uv_positions)} unique UV positions found. Please unwrap the mesh properly.")
            logger.error(f"Invalid UV layout - only {len(uv_positions)} unique positions")
            return
        
        logger.info(f"UV validation passed - {len(uv_positions)} unique UV positions")
        
        # Build BVH tree for ray casting (occlusion testing)
        logger.info("Building BVH tree for ray casting...")
        bvh = BVHTree.FromObject(mask_mesh, context.evaluated_depsgraph_get())
        
        # Get camera world position
        cam_location = camera.matrix_world.to_translation()
        
        # Optional: Create debug objects to visualize ray hits
        if context.scene.zenv_debug_mode:
            debug_hits = []
        
        # Build lookup: for each polygon, store its vertices and UVs
        logger.info(f"Building UV-to-world lookup with spatial acceleration...")
        
        # Build spatial grid for fast UV lookup
        grid_size = 32  # 32x32 grid
        uv_grid = [[[] for _ in range(grid_size)] for _ in range(grid_size)]
        
        poly_data = []
        for poly_idx, poly in enumerate(mesh_eval.data.polygons):
            # Get UV coordinates for this polygon
            poly_uvs = []
            for loop_idx in poly.loop_indices:
                uv = uv_layer[loop_idx].uv
                poly_uvs.append(Vector((uv.x, uv.y)))
            
            # Get world space vertices for this polygon
            poly_verts = [mesh_eval.matrix_world @ mesh_eval.data.vertices[v].co for v in poly.vertices]
            
            # Calculate polygon normal
            if len(poly_verts) >= 3:
                edge1 = poly_verts[1] - poly_verts[0]
                edge2 = poly_verts[2] - poly_verts[0]
                normal = edge1.cross(edge2).normalized()
            else:
                normal = Vector((0, 0, 1))
            
            poly_info = {
                'uvs': poly_uvs,
                'verts': poly_verts,
                'normal': normal
            }
            poly_data.append(poly_info)
            
            # Add to spatial grid based on UV bounding box
            if poly_uvs:
                min_u = min(uv.x for uv in poly_uvs)
                max_u = max(uv.x for uv in poly_uvs)
                min_v = min(uv.y for uv in poly_uvs)
                max_v = max(uv.y for uv in poly_uvs)
                
                # Add to all grid cells this polygon overlaps
                grid_min_x = max(0, int(min_u * grid_size))
                grid_max_x = min(grid_size - 1, int(max_u * grid_size))
                grid_min_y = max(0, int(min_v * grid_size))
                grid_max_y = min(grid_size - 1, int(max_v * grid_size))
                
                for gy in range(grid_min_y, grid_max_y + 1):
                    for gx in range(grid_min_x, grid_max_x + 1):
                        uv_grid[gy][gx].append(poly_idx)
        
        logger.info(f"Built spatial grid with {len(poly_data)} polygons")
        
        # Pre-compute UV coverage map to skip empty space
        logger.info("Building UV coverage map...")
        uv_coverage = np.zeros((uv_height, uv_width), dtype=bool)
        
        for poly_info in poly_data:
            poly_uvs = poly_info['uvs']
            if len(poly_uvs) >= 3:
                # Rasterize polygon into coverage map
                for i in range(1, len(poly_uvs) - 1):
                    uv0, uv1, uv2 = poly_uvs[0], poly_uvs[i], poly_uvs[i+1]
                    
                    # Get bounding box of triangle in pixel space
                    min_u = min(uv0.x, uv1.x, uv2.x)
                    max_u = max(uv0.x, uv1.x, uv2.x)
                    min_v = min(uv0.y, uv1.y, uv2.y)
                    max_v = max(uv0.y, uv1.y, uv2.y)
                    
                    min_x = max(0, int(min_u * uv_width))
                    max_x = min(uv_width - 1, int(max_u * uv_width))
                    min_y = max(0, int((1.0 - max_v) * uv_height))
                    max_y = min(uv_height - 1, int((1.0 - min_v) * uv_height))
                    
                    # Mark all pixels in bounding box as covered
                    uv_coverage[min_y:max_y+1, min_x:max_x+1] = True
        
        covered_pixels = np.count_nonzero(uv_coverage)
        total_uv_pixels = uv_width * uv_height
        logger.info(f"UV coverage: {covered_pixels}/{total_uv_pixels} pixels ({100*covered_pixels/total_uv_pixels:.1f}%) inside UV islands")
        
        # Sample UV space with hard limits to prevent freezing
        sample_density = context.scene.zenv_mask_sample_density
        sample_step = int(1.0 / sample_density) if sample_density < 1.0 else 1
        
        # Calculate total samples and enforce maximum
        estimated_samples = (uv_height // sample_step) * (uv_width // sample_step)
        MAX_SAMPLES = 500000  # Hard limit to prevent freezing (10x increase)
        
        if estimated_samples > MAX_SAMPLES:
            # Adjust sample step to stay under limit
            sample_step = int(np.sqrt((uv_height * uv_width) / MAX_SAMPLES))
            sample_step = max(1, sample_step)
            estimated_samples = (uv_height // sample_step) * (uv_width // sample_step)
            logger.warning(f"Reducing samples from {estimated_samples} to {MAX_SAMPLES} to prevent freezing")
        
        logger.info(f"Sampling UV space: {uv_width}x{uv_height} texture, step={sample_step}, ~{estimated_samples} samples")
        
        # Use random sampling to test different areas each time
        import random
        random.seed()  # Different seed each time
        
        # Collect all valid UV pixels
        valid_pixels = []
        for uv_y in range(0, uv_height, sample_step):
            for uv_x in range(0, uv_width, sample_step):
                if uv_coverage[uv_y, uv_x]:
                    valid_pixels.append((uv_x, uv_y))
        
        # Randomly sample from valid pixels
        num_samples = min(len(valid_pixels), estimated_samples)
        sampled_pixels = random.sample(valid_pixels, num_samples)
        
        logger.info(f"Random sampling {num_samples} pixels from {len(valid_pixels)} valid UV pixels")
        
        total_pixels = 0
        visible_pixels = 0
        occluded_pixels = 0
        backface_pixels = 0
        no_world_pos = 0
        
        import time
        start_time = time.time()
        
        # Iterate through sampled pixels
        last_log_time = start_time
        for sample_idx, (uv_x, uv_y) in enumerate(sampled_pixels):
            # Log progress every 2 seconds
            current_time = time.time()
            if current_time - last_log_time > 2.0:
                progress = (sample_idx / num_samples) * 100
                elapsed = current_time - start_time
                samples_per_sec = total_pixels / elapsed if elapsed > 0 else 0
                eta = (num_samples - total_pixels) / samples_per_sec if samples_per_sec > 0 else 0
                logger.info(f"Progress: {progress:.1f}% | {total_pixels}/{num_samples} samples | {samples_per_sec:.0f} samples/sec | ETA: {eta:.1f}s")
                last_log_time = current_time
            
            total_pixels += 1
            
            # Convert pixel position to UV coordinate (0-1 range)
            uv_u = uv_x / (uv_width - 1) if uv_width > 1 else 0.5
            uv_v = 1.0 - (uv_y / (uv_height - 1)) if uv_height > 1 else 0.5
            uv_coord = Vector((uv_u, uv_v))
            
            # Find which polygon triangle contains this UV coordinate
            # Use spatial grid for fast lookup
            grid_x = min(grid_size - 1, int(uv_u * grid_size))
            grid_y = min(grid_size - 1, int(uv_v * grid_size))
            
            world_pos = None
            world_normal = None
            
            # Only check polygons in this grid cell
            candidate_polys = uv_grid[grid_y][grid_x]
            
            # Debug first few samples
            if total_pixels <= 3:
                logger.info(f"Sample {total_pixels}: UV({uv_x},{uv_y}) = ({uv_u:.3f},{uv_v:.3f}), grid cell has {len(candidate_polys)} polys")
            
            for poly_idx in candidate_polys:
                poly_info = poly_data[poly_idx]
                poly_uvs = poly_info['uvs']
                poly_verts = poly_info['verts']
                
                if len(poly_uvs) >= 3:
                    # Check each triangle in the polygon
                    for i in range(1, len(poly_uvs) - 1):
                        uv0, uv1, uv2 = poly_uvs[0], poly_uvs[i], poly_uvs[i+1]
                        
                        # Check if UV point is inside this triangle
                        bary = self.barycentric_coords(uv_coord, uv0, uv1, uv2)
                        
                        if bary and all(b >= -0.001 for b in bary):
                            # UV point is inside this triangle
                            # Interpolate world position using barycentric coords
                            v0, v1, v2 = poly_verts[0], poly_verts[i], poly_verts[i+1]
                            world_pos = bary[0] * v0 + bary[1] * v1 + bary[2] * v2
                            world_normal = poly_info['normal']
                            break
                
                if world_pos:
                    break
            
            # Initialize mask value
            mask_value = 0.0
            
            # If we found a world position for this UV coordinate
            if world_pos and world_normal:
                # Debug first few world positions
                if total_pixels <= 3:
                    logger.info(f"  Found world_pos: {world_pos}, normal: {world_normal}")
                
                # Check if surface faces camera
                to_camera = (cam_location - world_pos).normalized()
                facing_dot = world_normal.dot(to_camera)
                
                if facing_dot <= 0:
                    # Backface
                    backface_pixels += 1
                    mask_value = 0.0
                    if total_pixels <= 3:
                        logger.info(f"  Backface (dot={facing_dot:.3f})")
                else:
                    # Cast ray from camera to this world position
                    ray_direction = (world_pos - cam_location).normalized()
                    ray_distance = (world_pos - cam_location).length
                    
                    # Ray cast to check for occlusion - increased tolerance to 10cm
                    hit_location, hit_normal, hit_index, hit_distance = bvh.ray_cast(cam_location, ray_direction, ray_distance * 1.1)
                    
                    if hit_location is None:
                        # No hit
                        mask_value = 0.0
                        occluded_pixels += 1
                        if total_pixels <= 3:
                            logger.info(f"  Ray cast: NO HIT")
                    else:
                        # Check if the hit is close to our target position
                        distance_to_target = (hit_location - world_pos).length
                        
                        if distance_to_target < 0.1:  # Increased to 10cm tolerance
                            # Ray hit our surface - visible!
                            mask_value = 1.0
                            visible_pixels += 1
                            if total_pixels <= 3:
                                logger.info(f"  VISIBLE! dist={distance_to_target:.4f}m")
                            
                            # Debug visualization
                            if context.scene.zenv_debug_mode and visible_pixels % 100 == 0:
                                debug_hits.append(world_pos.copy())
                        else:
                            # Ray hit something else first - occluded
                            mask_value = 0.0
                            occluded_pixels += 1
                            if total_pixels <= 3:
                                logger.info(f"  Occluded, dist={distance_to_target:.4f}m")
            else:
                # No world position found
                no_world_pos += 1
                if total_pixels <= 3:
                    logger.info(f"  No world position found for this UV coordinate")
            
            # Write to UV texture
            for dy in range(sample_step):
                for dx in range(sample_step):
                    write_x = uv_x + dx
                    write_y = uv_y + dy
                    if 0 <= write_x < uv_width and 0 <= write_y < uv_height:
                        uv_array[write_y, write_x] = mask_value
        
        end_time = time.time()
        total_time = end_time - start_time
        
        logger.info(f"Ray casting complete in {total_time:.2f} seconds:")
        logger.info(f"  Total UV pixels sampled: {total_pixels}")
        logger.info(f"  Visible: {visible_pixels} ({100*visible_pixels/max(1,total_pixels):.1f}%)")
        logger.info(f"  Occluded: {occluded_pixels} ({100*occluded_pixels/max(1,total_pixels):.1f}%)")
        logger.info(f"  Backface: {backface_pixels} ({100*backface_pixels/max(1,total_pixels):.1f}%)")
        logger.info(f"  Performance: {total_pixels/total_time:.0f} samples/sec")
        logger.info(f"UV array shape: {uv_array.shape}, min: {uv_array.min():.3f}, max: {uv_array.max():.3f}")
        
        # Create debug visualization spheres
        if context.scene.zenv_debug_mode and debug_hits:
            logger.info(f"Creating {len(debug_hits)} debug spheres at visible ray hits...")
            for i, hit_pos in enumerate(debug_hits):
                bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01, location=hit_pos)
                sphere = context.active_object
                sphere.name = f"DEBUG_RayHit_{i}"
                # Make it bright green
                mat = bpy.data.materials.new(name=f"DEBUG_MAT_{i}")
                mat.diffuse_color = (0, 1, 0, 1)
                sphere.data.materials.append(mat)
        
        # Write to Blender image
        # Blender stores images bottom-up, so flip the array
        uv_array_flipped = np.flipud(uv_array)
        uv_flat = uv_array_flipped.flatten()
        
        # Create RGBA pixel array (Blender expects RGBA even for grayscale)
        pixels_out = np.zeros(uv_width * uv_height * 4, dtype=np.float32)
        pixels_out[0::4] = uv_flat  # R
        pixels_out[1::4] = uv_flat  # G
        pixels_out[2::4] = uv_flat  # B
        pixels_out[3::4] = 1.0      # A (fully opaque)
        
        # Write pixels to image
        uv_mask_image.pixels[:] = pixels_out
        uv_mask_image.update()
        
        # Save to file
        uv_mask_image.save_render(uv_mask_image.filepath_raw)
        
        logger.info(f"Mask saved to {uv_mask_image.filepath_raw}")
        
        logger.info(f"Camera-to-UV transfer complete")

    def bake_visibility_mask(self, context, mask_mesh):
        """
        Apply post-processing to the transferred UV mask.
        The camera-to-UV transfer is already complete at this point.
        """
        # The mask has already been transferred to UV space
        # Just need to get the image path and apply post-processing
        
        # Find the mask image from the execute method
        # It was passed to transfer_camera_to_uv_space
        # We need to get it from the saved state
        
        # Get the image that was created in create_mask_image
        mask_images = [img for img in bpy.data.images if img.name.startswith("mask_")]
        if not mask_images:
            logger.error("Could not find mask image")
            return None
        
        # Get the most recent one
        mask_image = sorted(mask_images, key=lambda x: x.name)[-1]
        mask_path = mask_image.filepath_raw
        
        # Apply gradient falloff if specified
        if context.scene.zenv_mask_falloff > 0 or context.scene.zenv_mask_margin > 0:
            self.apply_mask_falloff(
                mask_path, 
                context.scene.zenv_mask_margin,
                context.scene.zenv_mask_falloff
            )
        
        return mask_path
    
    def apply_mask_falloff(self, image_path, margin_pixels, falloff_pixels):
        """
        Apply gradient falloff from mask edges using distance transform.
        Creates smooth transition from white to black.
        """
        try:
            import numpy as np
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
        }

    def restore_state(self, context, state):
        """Restore previous scene state"""
        context.scene.render.engine = state['render_engine']

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_TextureProj_Panel(bpy.types.Panel):
    """Panel for texture projection tools"""
    bl_label = "Texture Projection"
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
        box.prop(context.scene, "zenv_texture_path")
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
        box.prop(context.scene, "zenv_use_mask_as_alpha")

        # Visibility Mask
        box.operator("zenv.textureproj_bake_mask", icon='TEXTURE')
        box.prop(context.scene, "zenv_mask_sample_count")
        box.prop(context.scene, "zenv_mask_dilation")
        box.prop(context.scene, "zenv_debug_mode")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_TextureProj_CreateCamera,
    ZENV_OT_TextureProj_GetCameraResolution,
    ZENV_OT_TextureProj_BakeTexture,
    ZENV_OT_TextureProj_BakeVisibilityMask,
    ZENV_PT_TextureProj_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_TextureProj_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_TextureProj_Properties.unregister()

if __name__ == "__main__":
    register()
