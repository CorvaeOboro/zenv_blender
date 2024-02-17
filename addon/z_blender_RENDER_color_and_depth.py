bl_info = {
    "name": "RENDER color and depth ",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " renders quick simple color and depth images with datetime suffix",
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
class ZENV_PT_RenderQuick(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "RENDER_depth"
    bl_idname = "ZENV_PT_RenderDepthColor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.render_color_datetime")
        layout.operator("zenv.render_depth_datetime")

#//==================================================================================================

class ZENV_OT_RenderColor(bpy.types.Operator):
    bl_idname = "zenv.render_color_datetime"
    bl_label = "Render Flat Color"

    def execute(self, context):
        logging.info("Starting flat color rendering...")
        selected_objects = context.selected_objects

        if not context.scene.camera or not selected_objects:
            self.report({'ERROR'}, "No active camera or selected objects found.")
            return {'CANCELLED'}

        # Store original state
        original_materials = {o: o.active_material for o in bpy.data.objects if o.type == 'MESH'}
        original_engine = context.scene.render.engine
        original_settings = context.scene.render.image_settings.file_format
        original_clip_start = context.scene.camera.data.clip_start
        original_clip_end = context.scene.camera.data.clip_end

        # Setup for rendering
        self.setup_rendering(context, selected_objects)

        # Render and save image
        self.render_and_save_image(context, selected_objects)

        # Restore original state
        self.restore_scene(context, original_materials, original_engine, original_settings, original_clip_start, original_clip_end)

        return {'FINISHED'}

    def setup_rendering(self, context, selected_objects):
        logging.info("Setting up rendering for flat color...")
        context.scene.render.engine = 'BLENDER_EEVEE'
        context.scene.eevee.use_gtao = False
        context.scene.eevee.use_bloom = False
        context.scene.eevee.use_ssr = False
        context.scene.render.image_settings.file_format = 'PNG'

        # Create and assign temporary materials
        for obj in selected_objects:
            if obj.type == 'MESH' and obj.active_material:
                temp_material = bpy.data.materials.new(name="TempFlatColorMaterial")
                temp_material.use_nodes = True
                node_tree = temp_material.node_tree

                # Use existing Material Output node
                output_node = self.get_material_output_node(node_tree)

                bsdf = node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                node_tree.links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])

                # Check and link diffuse texture if available
                self.link_diffuse_texture(obj.active_material, temp_material, bsdf)

                obj.active_material = temp_material

        return True
        
    def get_material_output_node(self, node_tree):
        for node in node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                return node
        # If not found, create a new Material Output node
        return node_tree.nodes.new('ShaderNodeOutputMaterial')

    def link_diffuse_texture(self, original_material, temp_material, bsdf):
        if original_material.use_nodes:
            for node in original_material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    texture_node = temp_material.node_tree.nodes.new('ShaderNodeTexImage')
                    texture_node.image = node.image
                    temp_material.node_tree.links.new(texture_node.outputs['Color'], bsdf.inputs['Base Color'])
                    break  # Assuming first image texture is the diffuse texture


    def adjust_camera_clipping(self, camera, obj):
        # Transform the bounding box coordinates to world space
        world_verts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Calculate distances from the camera to each vertex of the bounding box
        camera_co = camera.matrix_world.translation
        distances = [np.linalg.norm(corner - camera_co) for corner in world_verts]

        # Set the clipping start and end based on these distances
        min_distance = min(distances)
        max_distance = max(distances)
        camera.data.clip_start = max(min_distance * 0.9, 0.1)  # Avoid too small clipping start
        camera.data.clip_end = max_distance * 1.1  # Slightly beyond the furthest point

    def restore_scene(self, context, original_materials, original_engine, original_settings, original_clip_start, original_clip_end):
        logging.info("Restoring original scene settings...")
        # Restore materials
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.active_material = original_materials.get(o)

        # Restore render settings
        context.scene.render.engine = original_engine
        context.scene.render.image_settings.file_format = original_settings
        context.scene.camera.data.clip_start = original_clip_start
        context.scene.camera.data.clip_end = original_clip_end

    def render_and_save_image(self, context, selected_objects):
        logging.info("Rendering and saving image...")
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        texture_folder = os.path.join(os.path.dirname(bpy.data.filepath), "textures")
        os.makedirs(texture_folder, exist_ok=True)

        for obj in selected_objects:
            texture_name = "texture"
            image_name = f"{obj.name}_{texture_name}_color_{datetime_str}.png"
            render_filepath = os.path.join(texture_folder, image_name)

            context.scene.render.filepath = render_filepath
            context.scene.render.image_settings.file_format = 'PNG'

            bpy.ops.render.render(write_still=True)

            if os.path.exists(render_filepath):
                logging.info(f"Image rendered for {obj.name} to: {render_filepath}")
            else:
                self.report({'ERROR'}, f"Failed to render image for {obj.name}.")
                logging.error("Rendered image file not found for " + obj.name)


class ZENV_OT_RenderDepth(bpy.types.Operator):
    bl_idname = "zenv.render_depth_datetime"
    bl_label = "Render Depth Map"

    def execute(self, context):
        logging.info("Starting depth map rendering...")
        camera = context.scene.camera
        obj = context.selected_objects[0] if context.selected_objects else None

        if not camera or not obj:
            self.report({'ERROR'}, "No active camera or selected object found.")
            return {'CANCELLED'}

        # Store original settings
        original_clip_start = camera.data.clip_start
        original_clip_end = camera.data.clip_end
        original_engine = context.scene.render.engine
        original_settings = context.scene.render.image_settings.file_format
        original_compositor_nodes = self.store_compositor_nodes(context) if context.scene.use_nodes else None

        # Setup for rendering
        self.setup_rendering(context, camera, obj)

        # Render and save image
        rendered_image_path = self.render_image(context, obj)

        # Restore original settings
        self.restore_scene(context, camera, original_engine, original_settings, original_clip_start, original_clip_end, original_compositor_nodes)

        if not rendered_image_path:
            return {'CANCELLED'}

        logging.info("Rendered image successfully.")
        return {'FINISHED'}

    def store_compositor_nodes(self, context):
        nodes = context.scene.node_tree.nodes
        return {n.name: n.type for n in nodes}

    def restore_scene(self, context, camera, original_engine, original_settings, original_clip_start, original_clip_end, original_compositor_nodes):
        logging.info("Restoring original scene settings...")
        camera.data.clip_start = original_clip_start
        camera.data.clip_end = original_clip_end
        context.scene.render.engine = original_engine
        context.scene.render.image_settings.file_format = original_settings

        # Restore compositor nodes
        if original_compositor_nodes:
            self.restore_compositor_nodes(context)
            print("restore")

    def setup_rendering(self, context, camera, obj):
        logging.info("Setting up rendering...")
        context.scene.render.engine = 'CYCLES'
        context.scene.render.image_settings.file_format = 'PNG'  # Use PNG to preserve depth data

        # Enable Z-pass for the active view layer
        context.view_layer.use_pass_z = True  # Corrected reference to the active view layer

        #self.set_depth_range(camera, obj)
        self.setup_compositor_nodes(context,camera, obj)
        return True

    def setup_compositor_nodes(self, context,camera, obj):
        logging.info("Setting up compositor nodes for depth rendering...")
        context.scene.use_nodes = True
        tree = context.scene.node_tree
        tree.nodes.clear()
    

        render_layers = tree.nodes.new('CompositorNodeRLayers')
        map_range = tree.nodes.new('CompositorNodeMapRange')
        invert = tree.nodes.new('CompositorNodeInvert')
        comp = tree.nodes.new('CompositorNodeComposite')

        # Transform object vertices to camera space
        mat = camera.matrix_world.normalized().inverted()
        local_coords = [mat @ obj.matrix_world @ v.co for v in obj.data.vertices]
        distances = [np.linalg.norm(co - camera.location) for co in local_coords]
        min_distance = min(distances)
        max_distance = max(distances)

        # General multiplier for depth range adjustment
        depth_min_multiplier = 0.35  # Adjust this as needed
        depth_multiplier = 0.5  # Adjust this as needed
        # Set up Map Range node to normalize depth
        camera = context.scene.camera
        map_range.inputs['From Min'].default_value = min_distance * depth_min_multiplier
        map_range.inputs['From Max'].default_value = max_distance * depth_multiplier
        map_range.inputs['To Min'].default_value = 0
        map_range.inputs['To Max'].default_value = 1

        # Link nodes
        tree.links.new(render_layers.outputs['Depth'], map_range.inputs[0])
        tree.links.new(map_range.outputs[0], invert.inputs[1])
        tree.links.new(invert.outputs[0], comp.inputs[0])

    def restore_compositor_nodes(self, context):
        logging.info("Restoring to default compositor nodes...")
        tree = context.scene.node_tree
        tree.nodes.clear()

        # Create Render Layers node
        render_layers_node = tree.nodes.new('CompositorNodeRLayers')

        # Create Composite node
        composite_node = tree.nodes.new('CompositorNodeComposite')

        # Link Render Layers to Composite
        tree.links.new(render_layers_node.outputs[0], composite_node.inputs[0])


    def render_image(self, context, obj):
        logging.info("Rendering image...")
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        texture_name = "texture"  # Customize as needed
        image_name = f"{obj.name}_{texture_name}_depth_{datetime_str}.png"
        texture_folder = os.path.join(os.path.dirname(bpy.data.filepath), "textures")
        os.makedirs(texture_folder, exist_ok=True)
        render_filepath = os.path.join(texture_folder, image_name)

        context.scene.render.filepath = render_filepath
        bpy.ops.render.render(write_still=True)

        if os.path.exists(render_filepath):
            logging.info("Image rendered to: " + render_filepath)
            return render_filepath
        else:
            logging.error("Rendered image file not found.")
            return None

#//======================================================================================================
def register():
    bpy.utils.register_class(ZENV_PT_RenderQuick)
    bpy.utils.register_class(ZENV_OT_RenderColor)
    bpy.utils.register_class(ZENV_OT_RenderDepth)
    
def unregister():
    bpy.utils.unregister_class(ZENV_PT_RenderQuick)
    bpy.utils.unregister_class(ZENV_OT_RenderColor)
    bpy.utils.unregister_class(ZENV_OT_RenderDepth)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()