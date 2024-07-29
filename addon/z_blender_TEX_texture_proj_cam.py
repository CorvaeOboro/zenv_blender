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
        layout.prop(context.scene, "zenv_texture_path")
        layout.prop(context.scene, "zenv_ortho_scale")
        layout.operator("zenv.create_debug_plane")


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
        camera_object.data.ortho_scale = bpy.context.scene.zenv_ortho_scale

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
        return self.bake_texture_workflow(context)

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

        baked_texture_path = self.perform_baking(context, camera_proj_mesh, bake_setup_mesh)
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
        self.cleanup(context, state['original_engine'], state['original_materials'])

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
        self.subdivide_mesh(camera_proj_mesh)
        return camera_proj_mesh
    
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
        bake_image = self.create_bake_image()
        self.setup_baking_material(target_mesh, bake_image)
        context.scene.render.engine = 'CYCLES'
        bpy.ops.object.bake(type='DIFFUSE', save_mode='EXTERNAL', filepath=bake_image.filepath, use_selected_to_active=True)
        if bake_image.has_data:
            bake_image.save_render(bake_image.filepath)
            logger.info("Baking completed successfully.")
            return bake_image.filepath
        else:
            logger.error("Failed to bake image data.")
            return None

    def create_bake_image(self):
        """Create a new image for baking."""
        return bpy.data.images.new(name="BakeImage" + datetime.now().strftime("%Y%m%d%H%M%S"), width=1024, height=1024, alpha=True)

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
        
    def cleanup(self, context, meshes, original_engine, original_materials):
        # Clean up temporary objects and restore original render engine and materials
        logger.info("Cleaning up temporary changes.")
        self.remove_temporary_meshes(context)
        context.scene.render.engine = original_engine
        for obj, mats in original_materials.items():
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)
        logger.info("Cleanup completed.")

    def remove_temporary_meshes(self, context):
        """Remove temporary meshes created during the baking process."""
        for obj in context.selected_objects:
            if "temp_" in obj.name:
                bpy.data.meshes.remove(obj.data, do_unlink=True)


class ZENV_OT_CreateDebugPlane(bpy.types.Operator):
    """Operator to create and bake a debug plane for texture projection visualization."""
    bl_idname = "zenv.create_debug_plane"
    bl_label = "Create Debug Plane"
    bl_description = "Creates a debug plane to visualize the texture projection process"

    def execute(self, context):
        camera = context.scene.camera
        if not camera:
            logger.error("No active camera found.")
            self.report({'ERROR'}, "No active camera found.")
            return {'CANCELLED'}

        intermediate_plane = self.create_plane("IntermediateDebugPlane", camera, -2)
        self.setup_baking_material(intermediate_plane, context.scene.zenv_texture_path)

        receiver_plane = self.create_plane("ReceiverPlane", camera, -2.1)
        self.setup_receiver_material(receiver_plane)

        if not self.bake_texture(intermediate_plane, receiver_plane):
            logger.error("Failed to bake texture.")
            self.report({'ERROR'}, "Failed to bake texture.")
            return {'CANCELLED'}

        result_plane = self.create_plane("ResultDebugPlane", camera, -3)
        self.setup_result_material(result_plane, receiver_plane)

        logger.info("Debug projection plane created and texture baked successfully.")
        self.report({'INFO'}, "Debug projection plane created and texture baked successfully.")
        return {'FINISHED'}

    def create_plane(self, name, camera, offset):
        # Create a plane at a specified offset from the camera
        bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=False, location=camera.location + camera.matrix_world.normalized().to_quaternion() @ Vector((0, 0, offset)))
        plane = bpy.context.active_object
        plane.name = name
        plane.rotation_euler = camera.rotation_euler
        plane.rotation_euler.x += math.pi
        return plane

    def setup_baking_material(self, plane, texture_path):
        # Set up a material for the plane with the specified texture for baking
        mat = bpy.data.materials.get("BakingMaterial") or bpy.data.materials.new(name="BakingMaterial")
        image = bpy.data.images.load(texture_path, check_existing=True)
        setup_material_nodes(mat, image)
        plane.data.materials.append(mat)

    def setup_receiver_material(self, plane):
        # Set up a material for the plane that will receive the baked texture
        mat = bpy.data.materials.new(name="ReceiverMaterial")
        image = bpy.data.images.new(name="ReceiverTexture", width=1024, height=1024, alpha=False)
        setup_material_nodes(mat, image)
        plane.data.materials.append(mat)

    def setup_result_material(self, plane, source_plane):
        # Set up a material for the plane that will display the result of the baking process
        mat = bpy.data.materials.new(name="ResultMaterial")
        # Retrieve the texture image from the source plane's material
        tex_image = next((node for node in source_plane.data.materials[0].node_tree.nodes if node.type == 'TEX_IMAGE'), None)
        if tex_image and tex_image.image:
            setup_material_nodes(mat, tex_image.image)
            plane.data.materials.append(mat)
        else:
            logger.error("Failed to find the texture image on the source plane.")

    def bake_texture(self, source_plane, target_plane):
        # Perform the baking process from the source plane to the target plane
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.bake_type = 'DIFFUSE'
        bpy.context.scene.render.bake.use_pass_direct = False
        bpy.context.scene.render.bake.use_pass_indirect = False
        source_plane.select_set(True)
        target_plane.select_set(True)
        bpy.context.view_layer.objects.active = target_plane
        bpy.ops.object.bake(type='DIFFUSE', save_mode='EXTERNAL', use_selected_to_active=True)
        return True
    
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

#//======================================================================================================
# BLENDER ADDON REGISTER
def register():
    # Register the addon's classes and properties
    bpy.utils.register_class(ZENV_PT_CamProjPanel)
    bpy.utils.register_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.register_class(ZENV_OT_BakeTexture)
    bpy.utils.register_class(ZENV_OT_CreateDebugPlane)  # Register the new operator
    bpy.types.Scene.zenv_texture_path = bpy.props.StringProperty(
        name="Texture File Path",
        subtype='FILE_PATH'
    )
    bpy.types.Scene.zenv_ortho_scale = bpy.props.FloatProperty(
        name="Orthographic Scale",
        default=2.0,
        min=0.01,
        max=100.0
    )

def unregister():
    # Unregister the addon's classes and properties
    bpy.utils.unregister_class(ZENV_PT_CamProjPanel)
    bpy.utils.unregister_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.unregister_class(ZENV_OT_BakeTexture)
    bpy.utils.unregister_class(ZENV_OT_CreateDebugPlane)  # Unregister the new operator
    del bpy.types.Scene.zenv_texture_path
    del bpy.types.Scene.zenv_ortho_scale


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()
