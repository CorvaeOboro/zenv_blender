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

# UI
class ZENV_PT_CamProjPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
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

#//==================================================================================================

class ZENV_OT_NewCameraOrthoProj(bpy.types.Operator):
    """Operator to set the camera to the current view."""
    bl_idname = "zenv.create_camera_proj"
    bl_label = "Set Camera View"

    def execute(self, context):
        try:
            self.create_orthographic_camera(context)
            return {'FINISHED'}
        except Exception as e:
            logger.error("Failed to create orthographic camera: %s", e)
            self.report({'ERROR'}, "Failed to create orthographic camera.")
            return {'CANCELLED'}

    def create_orthographic_camera(self, context):
        camera_name = self.generate_unique_camera_name("CAM_ORTHO_PROJ_")
        bpy.ops.object.camera_add()
        camera_object = bpy.context.object
        camera_object.name = camera_name
        context.scene.camera = camera_object

        self.match_camera_to_current_view(camera_object)
        self.set_orthographic_camera_properties(camera_object)

    def match_camera_to_current_view(self, camera_object):
        # Match the camera object's transformation with the current view
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                camera_object.matrix_world = region_3d.view_matrix.inverted()
                break

    def set_orthographic_camera_properties(self, camera_object):
        # Set camera to orthographic and adjust orthographic scale
        camera_object.data.type = 'ORTHO'
        camera_object.data.ortho_scale = 2.0

        # Adjust camera clip start and end based on the current view settings
        camera_object.data.clip_start = bpy.context.space_data.clip_start
        camera_object.data.clip_end = bpy.context.space_data.clip_end

    def generate_unique_camera_name(self, base_name):
        # Generate a unique camera name
        cameras = [cam.name for cam in bpy.data.objects if cam.type == 'CAMERA']
        if base_name not in cameras:
            return base_name

        i = 1
        while f"{base_name}_{i}" in cameras:
            i += 1
        return f"{base_name}_{i}"

class ZENV_OT_BakeTexture(bpy.types.Operator):
    bl_idname = "zenv.bake_cam_proj_texture"
    bl_label = "Bake Texture"

    def execute(self, context):
        # Initial checks
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected.")
            return {'CANCELLED'}
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera found.")
            return {'CANCELLED'}
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "The active object must be a mesh.")
            return {'CANCELLED'}

        # Save original settings
        original_obj = context.active_object
        original_engine = context.scene.render.engine
        original_materials = {obj: obj.data.materials[:] for obj in context.selected_objects}

        # Create texture folder
        blend_file_path = bpy.data.filepath
        texture_folder = os.path.join(os.path.dirname(blend_file_path), "textures")
        os.makedirs(texture_folder, exist_ok=True)

        # Create temporary meshes and perform baking
        camera_proj_mesh = self.create_camera_projection_mesh(context, original_obj)
        bake_setup_mesh = self.create_bake_setup_mesh(context, original_obj)

        try:
            # Setup baking material on camera projection mesh
            self.setup_projection_material(context, camera_proj_mesh)

            # Perform baking
            baked_texture_name = self.get_baked_texture_name(original_obj)
            filepath = os.path.join(texture_folder, baked_texture_name + ".png")
            self.bake_texture(context, camera_proj_mesh, bake_setup_mesh, original_obj, filepath)
        finally:
            # Cleanup
            self.cleanup(context, [camera_proj_mesh, bake_setup_mesh], original_engine, original_materials)
            self.report({'INFO'}, "cleanup.")

        return {'FINISHED'}

    def create_camera_projection_mesh(self, context, original_obj):
        """Create a temporary mesh for camera projection."""
        # Duplicate the original object
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        camera_proj_mesh = context.active_object
        camera_proj_mesh.name = "temp_camera_proj_mesh"
        camera_proj_mesh.select_set(False)
        self.subdivide_mesh(camera_proj_mesh)  # Subdivide the mesh
        return camera_proj_mesh

    def create_bake_setup_mesh(self, context, original_obj):
        """Create a temporary mesh for bake setup."""
        # Duplicate the original object
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        bpy.ops.object.duplicate(linked=False, mode='TRANSLATION')
        bake_setup_mesh = context.active_object
        bake_setup_mesh.name = "temp_bake_setup_mesh"
        bake_setup_mesh.select_set(False)
        self.subdivide_mesh(bake_setup_mesh)  # Subdivide the mesh
        return bake_setup_mesh
    
    def setup_projection_material(self, context, obj):
        """Setup material for camera projection."""
        image_path = bpy.path.abspath(context.scene.zenv_texture_path)
        if not os.path.isfile(image_path):
            self.report({'ERROR'}, "Image file not found at: " + image_path)
            return

        # Load and assign image to material
        image = bpy.data.images.load(image_path, check_existing=True)
        bake_mat = bpy.data.materials.new(name="CameraProjMaterial")
        bake_mat.use_nodes = True
        nodes = bake_mat.node_tree.nodes
        nodes.clear()

        # Set up nodes for camera projection
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        tex_coord = nodes.new('ShaderNodeTexCoord')
        tex_coord.object = context.scene.camera
        mapping = nodes.new('ShaderNodeMapping')
        mapping.inputs['Scale'].default_value = (0.5, 0.5, 0.5)  # Set scale to 0.5
        add_vector = nodes.new('ShaderNodeVectorMath')
        add_vector.operation = 'ADD'
        add_vector.inputs[1].default_value = (0.5, 0.5, 0.5)  # Add (0.5, 0.5, 0.5)
        emission = nodes.new('ShaderNodeEmission')
        output = nodes.new('ShaderNodeOutputMaterial')

        # Connect nodes
        bake_mat.node_tree.links.new(mapping.inputs['Vector'], tex_coord.outputs['Object'])
        bake_mat.node_tree.links.new(add_vector.inputs[0], mapping.outputs['Vector'])
        bake_mat.node_tree.links.new(tex_image.inputs['Vector'], add_vector.outputs['Vector'])
        bake_mat.node_tree.links.new(emission.inputs['Color'], tex_image.outputs['Color'])
        bake_mat.node_tree.links.new(output.inputs['Surface'], emission.outputs['Emission'])

        obj.data.materials.clear()
        obj.data.materials.append(bake_mat)

    def bake_texture(self, context, camera_proj_mesh, bake_setup_mesh, original_obj, filepath):
        # Switch to Cycles render engine
        context.scene.render.engine = 'CYCLES'

        bake_image = bpy.data.images.new(name="BakeImage", width=1024, height=1024, alpha=False)
        bake_image.file_format = 'JPEG'

        # Assign bake image to bake setup mesh
        bake_mat = bpy.data.materials.new(name="BakeSetupMaterial")
        bake_mat.use_nodes = True
        nodes = bake_mat.node_tree.nodes
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = bake_image
        nodes.new('ShaderNodeOutputMaterial')
        bake_setup_mesh.data.materials.clear()
        bake_setup_mesh.data.materials.append(bake_mat)

        # Select the necessary objects for baking
        bpy.ops.object.select_all(action='DESELECT')
        bake_setup_mesh.select_set(True)
        camera_proj_mesh.select_set(True)
        context.view_layer.objects.active = bake_setup_mesh

        context.scene.cycles.bake_margin = 4  # Increase margin to avoid artifacts
        context.scene.cycles.samples = 512  # Increase samples for better quality
        # Perform baking with the use of a cage
        context.scene.render.bake.use_cage = True
        context.scene.render.bake.cage_extrusion = 0.001

        # Perform baking
        bpy.ops.object.bake(type='EMIT', save_mode='EXTERNAL', filepath=filepath, use_selected_to_active=True, cage_extrusion=0.001)

        # Save the image if it has data
        if bake_image.has_data:
            bake_image.filepath_raw = filepath
            bake_image.save()
        else:
            self.report({'ERROR'}, "Failed to bake image data.")

        # Cleanup
        bake_mat.node_tree.nodes.remove(tex_image)

    def get_baked_texture_name(self, obj):
        """Generate a unique name for the baked texture."""
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{obj.name}_baked_{datetime_str}.png"

    def cleanup(self, context, temp_meshes, original_engine, original_materials):
        """Cleanup function to remove temporary objects and restore original settings."""
        for temp_mesh in temp_meshes:
            if temp_mesh:
                bpy.data.objects.remove(temp_mesh, do_unlink=True)
        context.scene.render.engine = original_engine
        for obj, mats in original_materials.items():
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)

    def subdivide_mesh(self, mesh):
        """Subdivide the mesh without smoothing."""
        subdiv_modifier = mesh.modifiers.new(name="Subdiv", type='SUBSURF')
        subdiv_modifier.levels = 2  # Set subdivision level, adjust as needed
        subdiv_modifier.subdivision_type = 'SIMPLE'

#//======================================================================================================
def register():
    bpy.utils.register_class(ZENV_PT_CamProjPanel)
    bpy.utils.register_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.register_class(ZENV_OT_BakeTexture)
    bpy.types.Scene.zenv_texture_path = bpy.props.StringProperty(
        name="Texture File Path",
        subtype='FILE_PATH'
    )

def unregister():
    bpy.utils.unregister_class(ZENV_PT_CamProjPanel)
    bpy.utils.unregister_class(ZENV_OT_NewCameraOrthoProj)
    bpy.utils.unregister_class(ZENV_OT_BakeTexture)
    del bpy.types.Scene.zenv_texture_path

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()