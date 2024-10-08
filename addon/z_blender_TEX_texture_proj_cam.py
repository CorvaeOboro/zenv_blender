bl_info = {
    "name": "TEX texture projection from camera ",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " creates camera from current view , sets up texture projection plane from it onto object , bakes texture of objects texture projection ",
}
#//==================================================================================================
import bpy
import os
import shutil  # For file operations
import numpy as np
from datetime import datetime
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix
from mathutils import Vector
import math
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all levels of log messages

# UI
class ZENV_PT_CamProjPanel(bpy.types.Panel):
    """Creates Panel in the VIEW_3D SidePanel  window"""
    bl_label = "Cam Proj"
    bl_idname = "ZENV_PT_CamProj"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.create_camera_proj")
        layout.operator("zenv.bake_cam_proj_texture")
        layout.prop(context.scene, "zenv_ortho_scale")
        layout.prop(context.scene, "zenv_texture_resolution")
        layout.prop(context.scene, "zenv_texture_path")
        layout.prop(context.scene, "zenv_debug_mode", text="Debug")


#//==================================================================================================
# CREATE ORTHOGRAPHIC CAMERA FROM CURRENT VIEW 
class ZENV_OT_NewCameraOrthoProj(bpy.types.Operator):
    """Operator to set the camera to the current view."""
    bl_idname = "zenv.create_camera_proj"
    bl_label = "Create Camera View"
    bl_description = "Creates an orthographic camera matching the current 3D view"

    def execute(self, context):
        if not self.create_orthographic_camera(context):
            return {'CANCELLED'}
        return {'FINISHED'}

    def create_orthographic_camera(self, context):
        """Create an orthographic camera and match it to the current view."""
        # Generate a unique name for the new camera and create it
        camera_name = self.generate_unique_camera_name("CAM_ORTHO_PROJ_")
        bpy.ops.object.camera_add()
        camera_object = bpy.context.object
        camera_object.name = camera_name
        context.scene.camera = camera_object

        if not self.match_camera_to_current_view(camera_object):
            self.report({'ERROR'}, "Failed to match camera to current view.")
            return False
        if not self.set_orthographic_camera_properties(camera_object):
            self.report({'ERROR'}, "Failed to set orthographic camera properties.")
            return False
        # Set the scene's output resolution to the texture resolution
        context.scene.render.resolution_x = context.scene.zenv_texture_resolution
        context.scene.render.resolution_y = context.scene.zenv_texture_resolution
        return True

    def match_camera_to_current_view(self, camera_object):
        """Match the camera object's transformation with the current 3D view."""
        # Match the camera object's transformation with the current 3D view
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                camera_object.matrix_world = region_3d.view_matrix.inverted()
                break
        else:
            logger.error("Failed to find a VIEW_3D area to match camera view.")
            return False
        return True

    def set_orthographic_camera_properties(self, camera_object):
        """Set camera to orthographic mode and adjust its scale and clipping."""
        # Set camera to orthographic mode and adjust its scale and clipping
        camera_object.data.type = 'ORTHO'
        camera_object.data.ortho_scale = bpy.context.scene.zenv_ortho_scale  # Use the new property

        # Adjust camera clip start and end based on the current view settings
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space_data = area.spaces.active
                camera_object.data.clip_start = space_data.clip_start
                camera_object.data.clip_end = space_data.clip_end
                break
        else:
            logger.error("Failed to find a VIEW_3D area to set camera properties.")
            return False
        return True

    def generate_unique_camera_name(self, base_name):
        # Generate a unique camera name by appending a number to the base name
        cameras = {cam.name for cam in bpy.data.objects if cam.type == 'CAMERA'}
        i = 1
        while f"{base_name}{i}" in cameras:
            i += 1
        return f"{base_name}{i}"

#==========================================================================================================
#  BAKE TEXTURE FROM CAMERA PROJECTED UV
class ZENV_OT_BakeTexture(bpy.types.Operator):
    """Bake textures of selected object from a duplicate with camera projected UVs."""
    bl_idname = "zenv.bake_cam_proj_texture"
    bl_label = "Bake Projected Texture"
    bl_description = "Bakes the texture of the selected object using a camera projection"

    def setup_baking_material(self, mesh, image):
        """Set up a material for the mesh with the specified image for baking."""
        mat = bpy.data.materials.get("BakingMaterial") or bpy.data.materials.new(name="BakingMaterial")
        setup_material_nodes(mat, image)
        mesh.data.materials.clear()
        mesh.data.materials.append(mat)
        logger.info("Baking material setup completed.")

    def execute(self, context):
        if not self.initial_checks(context):
            return {'CANCELLED'}

        state = self.save_current_state(context)
        camera_proj_mesh, bake_setup_mesh = self.prepare_meshes(context, context.active_object)
        if not camera_proj_mesh or not bake_setup_mesh:
            self.restore_state(context, state)
            return {'CANCELLED'}

        if not self.setup_projection_material(context, camera_proj_mesh):
            self.restore_state(context, state)
            return {'CANCELLED'}

        baked_texture_path = self.perform_baking(context, camera_proj_mesh, bake_setup_mesh, state['original_obj'])
        if not baked_texture_path:
            self.restore_state(context, state)
            return {'CANCELLED'}

        self.apply_baked_texture(context, bake_setup_mesh, baked_texture_path)
        self.restore_state(context, state)
        self.report({'INFO'}, "Bake successful. Temporary meshes kept for debugging.")
        return {'FINISHED'}

    def bake_texture_workflow(self, context):
        """Main workflow for baking texture from camera projection."""
        if not self.initial_checks(context):
            return {'CANCELLED'}

        state = self.save_current_state(context)
        camera_proj_mesh, bake_setup_mesh = self.prepare_meshes(context, context.active_object)
        if not camera_proj_mesh or not bake_setup_mesh:
            self.restore_state(context, state)
            return {'CANCELLED'}

        if not self.setup_projection_material(context, camera_proj_mesh):
            self.restore_state(context, state)
            return {'CANCELLED'}

        baked_texture_path = self.perform_baking(context, camera_proj_mesh, bake_setup_mesh, state['original_obj'])
        if not baked_texture_path:
            self.restore_state(context, state)
            return {'CANCELLED'}

        self.apply_baked_texture(context, bake_setup_mesh, baked_texture_path)
        self.restore_state(context, state)
        return {'FINISHED'}

    def save_current_state(self, context):
        """Save the current render engine and materials of selected objects."""
        return {
            'original_obj': context.active_object,
            'original_engine': context.scene.render.engine,
            'original_materials': {obj: obj.data.materials[:] for obj in context.selected_objects}
        }

    def restore_state(self, context, state):
        """Restore the original render engine and materials of selected objects."""
        self.cleanup(context, state['original_obj'], state['original_engine'], state['original_materials'])

    def initial_checks(self, context):
        # Check for the presence of a selected object, an active camera, and that the object is a mesh
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected.")
            return False
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera found.")
            return False
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "The active object must be a mesh.")
            return False
        return True

    def prepare_meshes(self, context, original_obj):
        # Prepares the meshes required for the baking process
        # Create duplicates of the original object for camera projection and baking setup
        camera_proj_mesh = self.create_camera_projection_mesh(context, original_obj)
        bake_setup_mesh = self.create_bake_setup_mesh(context, original_obj)
        return camera_proj_mesh, bake_setup_mesh

    #==========================================================================================================
    # CAMERA PROJECTION UV MESH DUPLICATE
    def create_camera_projection_mesh(self, context, original_obj):
        # Duplicate the original object and prepare it for camera projection
        """Create a temporary mesh for camera projection."""
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        camera_proj_mesh = context.active_object
        camera_proj_mesh.name = "temp_camera_proj_mesh"
        self.add_uv_project_modifier(camera_proj_mesh, context.scene.camera)
        return camera_proj_mesh

    def add_uv_project_modifier(self, mesh, camera):
        """Add a UV Project modifier to the mesh pointing to the given camera."""
        uv_project_modifier = mesh.modifiers.new(name="UVProject", type='UV_PROJECT')
        uv_project_modifier.projector_count = 1
        uv_project_modifier.projectors[0].object = camera
        mesh.data.uv_layers.active.name = "UVProject"
        # Set the UV Project modifier's scale to 1.0 for both X and Y
        uv_project_modifier.scale_x = 1.0
        uv_project_modifier.scale_y = 1.0
        logger.info("UV Project modifier added to mesh.")
    
    def setup_projection_material(self, context, obj):
        # Set up a material with the provided image texture for camera projection
        logger.info("Setting up projection material.")
        image_path = bpy.path.abspath(context.scene.zenv_texture_path)
        if not os.path.isfile(image_path):
            self.report({'ERROR'}, "Image file not found at: " + image_path)
            logger.error("Image file not found at: %s", image_path)
            return False

        image = bpy.data.images.load(image_path, check_existing=True)
        if not image:
            logger.error("Failed to load image at: %s", image_path)
            return False

        mat = bpy.data.materials.get("CameraProjMaterial") or bpy.data.materials.new(name="CameraProjMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        output = nodes.new('ShaderNodeOutputMaterial')
        nodes.new('ShaderNodeTexCoord')
        nodes.new('ShaderNodeMapping')
        nodes.new('ShaderNodeMixRGB')
        links = mat.node_tree.links
        links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
        links.new(output.inputs['Surface'], bsdf.outputs['BSDF'])
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        logger.info("Projection material setup completed.")
        return True

    #==========================================================================================================
    # BAKE MESH DUPLICATE
    def create_bake_setup_mesh(self, context, original_obj):
        # Duplicate the original object and prepare it for baking
        """Create a temporary mesh for bake setup."""
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        bake_setup_mesh = context.active_object
        bake_setup_mesh.name = "temp_bake_setup_mesh"
        self.subdivide_mesh(bake_setup_mesh)
        return bake_setup_mesh

    def setup_baking_material(self, mesh, image):
        """Set up a material for the mesh with the specified image for baking."""
        mat = bpy.data.materials.get("BakingMaterial") or bpy.data.materials.new(name="BakingMaterial")
        setup_material_nodes(mat, image)
        mesh.data.materials.clear()
        mesh.data.materials.append(mat)
        logger.info("Baking material setup completed.")

    def perform_baking(self, context, source_mesh, target_mesh, original_obj):
        # Perform the baking process using Cycles render engine
        logger.info("Performing texture baking.")
        bake_image = self.create_bake_image(context)
        self.setup_baking_material(target_mesh, bake_image)
        self.set_render_settings_for_baking(context)
        # Ensure the source and target meshes are selected and the target is active
        bpy.ops.object.select_all(action='DESELECT')
        source_mesh.select_set(True)
        target_mesh.select_set(True)
        context.view_layer.objects.active = target_mesh
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, save_mode='EXTERNAL', filepath=bake_image.filepath, use_selected_to_active=True, cage_extrusion=0.01, max_ray_distance=0.01)
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath)
            logger.info("Baking completed successfully.")
            return bake_image.filepath
        else:
            logger.error("Failed to bake image data.")
            return None

    def set_render_settings_for_baking(self, context):
        """Set render settings to bake only the Diffuse color."""
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.bake_type = 'DIFFUSE'
        context.scene.render.bake.use_pass_direct = False
        context.scene.render.bake.use_pass_indirect = False
        context.scene.render.bake.use_pass_color = True
        logger.info("Render settings configured for baking Diffuse color only.")
        
    def create_bake_image(self, context):
        """Create a new image for baking."""
        image_name = "BakeImage" + datetime.now().strftime("%Y%m%d%H%M%S")
        bake_resolution = context.scene.zenv_texture_resolution
        image = bpy.data.images.new(name=image_name, width=bake_resolution, height=bake_resolution, alpha=True)
        # Define a valid file path for the image within a "textures" subfolder
        textures_folder = bpy.path.abspath("//textures/")
        if not os.path.exists(textures_folder):
            os.makedirs(textures_folder)
        image.filepath_raw = os.path.join(textures_folder, image_name + ".png")
        image.file_format = 'PNG'
        logger.debug("Bake image will be saved to: %s", image.filepath_raw)
        return image

    def apply_baked_texture(self, context, mesh, texture_path):
        # Apply the baked texture to the mesh using a new material
        logger.info("Applying baked texture to mesh.")
        mat = bpy.data.materials.get("FinalMaterial") or bpy.data.materials.new(name="FinalMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = bpy.data.images.load(texture_path, check_existing=True)
        output = nodes.new('ShaderNodeOutputMaterial')
        links = mat.node_tree.links
        links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
        links.new(output.inputs['Surface'], bsdf.outputs['BSDF'])
        mesh.data.materials.clear()
        mesh.data.materials.append(mat)
        logger.info("Texture applied successfully.")

    def subdivide_mesh(self, mesh):
        # Subdivide the mesh to increase its resolution for better baking results
        """Subdivide the mesh without smoothing."""
        subdiv_modifier = mesh.modifiers.new(name="Subdiv", type='SUBSURF')
        subdiv_modifier.levels = 2  # Set subdivision level, adjust as needed
        subdiv_modifier.subdivision_type = 'SIMPLE'
        
    def cleanup(self, context, original_obj, original_engine, original_materials):
        """Restore the original render engine and materials of selected objects."""
        # Only restore the original render engine and materials, do not remove temporary meshes
        logger.info("Restoring original render engine and materials.")
        context.scene.render.engine = original_engine
        for obj, mats in original_materials.items():
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)
        if not context.scene.zenv_debug_mode:
            bpy.data.objects.remove(bpy.data.objects["temp_camera_proj_mesh"], do_unlink=True)
            bpy.data.objects.remove(bpy.data.objects["temp_bake_setup_mesh"], do_unlink=True)
        logger.info("Original state restored.")
    
#//======================================================================================================
# GLOBAL FUNCTIONS 
def setup_material_nodes(material, image=None):
    """Utility function to set up material nodes."""
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    tex_image = nodes.new('ShaderNodeTexImage')
    if image:
        tex_image.image = image
    output = nodes.new('ShaderNodeOutputMaterial')
    links = material.node_tree.links
    links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
    links.new(output.inputs['Surface'], bsdf.outputs['BSDF'])
    return nodes

def update_ortho_scale(self, context):
    camera = context.scene.camera
    if camera and camera.data.type == 'ORTHO':
        camera.data.ortho_scale = self.zenv_ortho_scale

    
class ZENV_OT_BakeVisibilityMask(bpy.types.Operator):
    """Bake visibility mask of selected object from camera view."""
    bl_idname = "zenv.bake_visibility_mask"
    bl_label = "Bake Visibility Mask"
    bl_description = "Bakes a black and white visibility mask from the camera's perspective"

    def execute(self, context):
        if not self.initial_checks(context):
            return {'CANCELLED'}

        state = self.save_current_state(context)
        visibility_mask_mesh = self.create_visibility_mask_mesh(context, state['original_obj'])
        if not visibility_mask_mesh:
            self.restore_state(context, state)
            return {'CANCELLED'}

        visibility_mask_path = self.perform_visibility_baking(context, visibility_mask_mesh, state['original_obj'])
        if not visibility_mask_path:
            self.restore_state(context, state)
            return {'CANCELLED'}

        self.apply_visibility_mask(context, visibility_mask_mesh, visibility_mask_path)
        self.restore_state(context, state)
        self.report({'INFO'}, "Visibility mask bake successful.")
        return {'FINISHED'}

    def create_visibility_mask_mesh(self, context, original_obj):
        # Duplicate the original object and prepare it for visibility mask baking
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        visibility_mask_mesh = context.active_object
        visibility_mask_mesh.name = "temp_visibility_mask_mesh"
        return visibility_mask_mesh

    def perform_visibility_baking(self, context, mask_mesh, original_obj):
        # Perform the baking process for the visibility mask
        logger.info("Performing visibility mask baking.")
        bake_image = self.create_bake_image(context)
        self.setup_visibility_material(mask_mesh, bake_image)
        self.set_render_settings_for_baking(context)
        # Ensure the mask mesh is selected and active
        bpy.ops.object.select_all(action='DESELECT')
        mask_mesh.select_set(True)
        context.view_layer.objects.active = mask_mesh
        bpy.ops.object.bake(type='EMIT', save_mode='EXTERNAL', filepath=bake_image.filepath)
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath)
            logger.info("Visibility mask baking completed successfully.")
            return bake_image.filepath
        else:
            logger.error("Failed to bake visibility mask.")
            return None

    def setup_visibility_material(self, mesh, image):
        """Set up a material for the mesh with the specified image for baking visibility."""
        mat = bpy.data.materials.get("VisibilityMaskMaterial") or bpy.data.materials.new(name="VisibilityMaskMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        geometry = nodes.new('ShaderNodeNewGeometry')
        emission = nodes.new('ShaderNodeEmission')
        output = nodes.new('ShaderNodeOutputMaterial')
        links = mat.node_tree.links
        links.new(emission.inputs['Color'], geometry.outputs['Backfacing'])
        links.new(output.inputs['Surface'], emission.outputs['Emission'])
        mesh.data.materials.clear()
        mesh.data.materials.append(mat)
        logger.info("Visibility mask material setup completed.")

    def apply_visibility_mask(self, context, mesh, mask_path):
        # Apply the visibility mask to the mesh using a new material
        logger.info("Applying visibility mask to mesh.")
        mat = bpy.data.materials.get("FinalVisibilityMaskMaterial") or bpy.data.materials.new(name="FinalVisibilityMaskMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = bpy.data.images.load(mask_path, check_existing=True)
        output = nodes.new('ShaderNodeOutputMaterial')
        links = mat.node_tree.links
        links.new(output.inputs['Surface'], tex_image.outputs['Color'])
        mesh.data.materials.clear()
        mesh.data.materials.append(mat)
        logger.info("Visibility mask applied successfully.")

    def initial_checks(self, context):
        # Check for the presence of a selected object and that the object is a mesh
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected.")
            return False
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "The active object must be a mesh.")
            return False
        return True

    def save_current_state(self, context):
        """Save the current render engine and materials of selected objects."""
        return {
            'original_obj': context.active_object,
            'original_engine': context.scene.render.engine,
            'original_materials': {obj: obj.data.materials[:] for obj in context.selected_objects}
        }

    def restore_state(self, context, state):
        """Restore the original render engine and materials of selected objects."""
        self.cleanup(context, state['original_obj'], state['original_engine'], state['original_materials'])

    def cleanup(self, context, original_obj, original_engine, original_materials):
        """Restore the original render engine and materials of selected objects."""
        # Only restore the original render engine and materials, do not remove temporary meshes
        logger.info("Restoring original render engine and materials.")
        context.scene.render.engine = original_engine
        for obj, mats in original_materials.items():
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)
        if not context.scene.zenv_debug_mode:
            bpy.data.objects.remove(bpy.data.objects["temp_visibility_mask_mesh"], do_unlink=True)
        logger.info("Original state restored.")


#//======================================================================================================
# BLENDER ADDON REGISTER
def register():
    # Register the addon's classes and properties
    bpy.utils.register_class(ZENV_PT_CamProjPanel)
    bpy.utils.register_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.register_class(ZENV_OT_BakeTexture)
    bpy.utils.register_class(ZENV_OT_BakeVisibilityMask)

    bpy.types.Scene.zenv_ortho_scale = bpy.props.FloatProperty(
        name="Orthographic Scale",
        description="Orthographic scale for the camera projection",
        default=6.0,
        min=0.01,
        max=1000.0,
        update=update_ortho_scale
    )
    bpy.types.Scene.zenv_texture_resolution = bpy.props.IntProperty(
        name="Texture Resolution",
        description="Resolution for the texture to be baked",
        default=1024,
        min=1,
        max=16384
    )
    bpy.types.Scene.zenv_texture_path = bpy.props.StringProperty(
        name="Texture File Path",
        subtype='FILE_PATH'
    )
    bpy.types.Scene.zenv_debug_mode = bpy.props.BoolProperty(
        name="Debug Mode",
        description="Keep temporary meshes after baking for debugging",
        default=False
    )

def unregister():
    # Unregister the addon's classes and properties
    bpy.utils.unregister_class(ZENV_PT_CamProjPanel)
    bpy.utils.unregister_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.unregister_class(ZENV_OT_BakeTexture)
    bpy.utils.unregister_class(ZENV_OT_BakeVisibilityMask)

    del bpy.types.Scene.zenv_ortho_scale
    del bpy.types.Scene.zenv_texture_resolution
    del bpy.types.Scene.zenv_texture_path
    del bpy.types.Scene.zenv_debug_mode


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()
