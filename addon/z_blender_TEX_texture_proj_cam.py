bl_info = {
    "name": 'TEX Camera Projection',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250119',
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

    @classmethod
    def unregister(cls):
        """Unregister all properties"""
        del bpy.types.Scene.zenv_ortho_scale
        del bpy.types.Scene.zenv_texture_resolution
        del bpy.types.Scene.zenv_texture_path
        del bpy.types.Scene.zenv_debug_mode

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_TextureProj_Utils:
    """Utility functions for texture projection"""
    
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
        """Create and set up orthographic camera"""
        camera_name = self.generate_unique_camera_name("CAM_ORTHO_PROJ_")
        bpy.ops.object.camera_add()
        camera = context.active_object
        camera.name = camera_name
        context.scene.camera = camera

        # Set up camera properties
        if not self.match_camera_to_view(camera, context):
            return False
        if not self.setup_camera_properties(camera, context):
            return False

        # Set render resolution
        context.scene.render.resolution_x = context.scene.zenv_texture_resolution
        context.scene.render.resolution_y = context.scene.zenv_texture_resolution

        return True

    def match_camera_to_view(self, camera, context):
        """Match camera to current 3D view"""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                camera.matrix_world = area.spaces.active.region_3d.view_matrix.inverted()
                return True
        return False

    def setup_camera_properties(self, camera, context):
        """Set up orthographic camera properties"""
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = context.scene.zenv_ortho_scale

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                camera.data.clip_start = space.clip_start
                camera.data.clip_end = space.clip_end
                return True
        return False

    def generate_unique_camera_name(self, base_name):
        """Generate unique camera name"""
        cameras = {cam.name for cam in bpy.data.objects if cam.type == 'CAMERA'}
        i = 1
        while f"{base_name}{i}" in cameras:
            i += 1
        return f"{base_name}{i}"

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
        
        # Add camera projection modifier
        uvmod = source.modifiers.new(name="UVProject", type='UV_PROJECT')
        uvmod.projector_count = 1
        uvmod.projectors[0].object = context.scene.camera
        
        return source

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
        """Create new image for baking"""
        image_name = f"bake_{datetime.now():%Y%m%d_%H%M%S}"
        bake_image = bpy.data.images.new(
            name=image_name,
            width=context.scene.zenv_texture_resolution,
            height=context.scene.zenv_texture_resolution,
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
            cage_extrusion=0.001,  # Tiny extrusion for precise baking
            margin=16
        )
        
        # Save result
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath_raw)
            return bake_image.filepath_raw
            
        return None

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
        
        # Load and set image
        image = bpy.data.images.load(texture_path)
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
        box.operator("zenv.textureproj_create_camera", icon='ADD')
        box.prop(context.scene, "zenv_ortho_scale")

        # Texture settings
        box = layout.box()
        box.label(text="Texture:", icon='TEXTURE')
        box.prop(context.scene, "zenv_texture_path")
        box.prop(context.scene, "zenv_texture_resolution")

        # Baking
        box = layout.box()
        box.label(text="Baking:", icon='RENDER_RESULT')
        box.operator("zenv.textureproj_bake", icon='RENDER_STILL')
        box.prop(context.scene, "zenv_debug_mode")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_TextureProj_CreateCamera,
    ZENV_OT_TextureProj_BakeTexture,
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
