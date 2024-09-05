bl_info = {
    "name": "RENDER color and depth ",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (3, 80, 0),
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
        layout.operator("zenv.render_complete_datetime")
        layout.operator("zenv.render_color_datetime")
        layout.operator("zenv.render_depth_datetime")

#//==================================================================================================

class ZENV_OT_RenderComplete(bpy.types.Operator):
    bl_idname = "zenv.render_complete_datetime"
    bl_label = "Render Complete Shading Lighting"

    def execute(self, context):
        logging.info("Starting complete shading lighting rendering...")
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

class ZENV_OT_RenderColor(bpy.types.Operator):
    bl_idname = "zenv.render_color_datetime"
    bl_label = "Render Flat Color"

    def execute(self, context):
        logging.info("Starting flat color rendering...")

        
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera found.")
            return {'CANCELLED'}

        # Store original state
        original_state = self.store_scene_state(context)
        # Store original settings
        original_settings = {
            'engine': context.scene.render.engine,
            'display_device': context.scene.display_settings.display_device,
            'view_transform': context.scene.view_settings.view_transform,
            'color_space': context.scene.sequencer_colorspace_settings.name
        }

        # Set up for accurate color rendering
        self.setup_render_settings(context) # Standard , not AgX 

        # Setup for flat color rendering using temporary emission materials
        self.setup_flat_color_rendering(context)

        # Render and save image
        self.render_and_save_image(context)

        # Restore original state
        self.restore_scene_state(context, original_state)


        return {'FINISHED'}
        return {'FINISHED'}

    def store_scene_state(self, context):
        state = {
            'engine': context.scene.render.engine,
            'materials': {obj: obj.active_material for obj in bpy.data.objects if obj.type == 'MESH'},
            'settings': {
                'display_device': context.scene.display_settings.display_device,
                'view_transform': context.scene.view_settings.view_transform,
                'color_space': context.scene.sequencer_colorspace_settings.name
            }
        }
        return state

    def restore_scene_state(self, context, state):
        logging.info("Restoring original scene state...")
        context.scene.render.engine = state['engine']
        for obj, mat in state['materials'].items():
            if obj.type == 'MESH':
                obj.active_material = mat
        context.scene.display_settings.display_device = state['settings']['display_device']
        context.scene.view_settings.view_transform = state['settings']['view_transform']
        context.scene.sequencer_colorspace_settings.name = state['settings']['color_space']

        # Restore original settings
        self.restore_original_settings(context, original_settings)

        return {'FINISHED'}
        
    def setup_flat_color_rendering(self, context):
        logging.info("Configuring materials for flat color rendering...")
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for slot in obj.material_slots:
                    original_mat = slot.material
                    if original_mat and original_mat.use_nodes:
                        # Create a temporary emission material
                        temp_mat = bpy.data.materials.new(name="TempEmissionMaterial")
                        temp_mat.use_nodes = True
                        node_tree = temp_mat.node_tree
                        nodes = node_tree.nodes
                        nodes.clear()  # Clear default nodes

                        emission_node = nodes.new(type='ShaderNodeEmission')
                        output_node = nodes.new(type='ShaderNodeOutputMaterial')
                        node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])

                        # Find the Principled BSDF and its connected texture node
                        principled_node = next((node for node in original_mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
                        if principled_node:
                            base_color_input = principled_node.inputs['Base Color']
                            for link in base_color_input.links:
                                if link.from_node.type == 'TEX_IMAGE':
                                    # Copy the texture node to the new material
                                    texture_node = nodes.new(type='ShaderNodeTexImage')
                                    texture_node.image = link.from_node.image
                                    node_tree.links.new(texture_node.outputs['Color'], emission_node.inputs['Color'])
                                    break
                        else:
                            # If no Principled BSDF is found or no texture is connected, use a default color
                            emission_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)  # White color

                        slot.material = temp_mat

        return True

    def setup_render_settings(self, context):
        logging.info("Configuring render settings for accurate color rendering...")
        scene = context.scene

        # Set color management to standard sRGB for consistency
        scene.display_settings.display_device = 'sRGB'
        scene.view_settings.view_transform = 'Standard'
        scene.sequencer_colorspace_settings.name = 'sRGB'

        # Ensure the render engine is set up without post-processing effects
        scene.render.engine = 'BLENDER_EEVEE'
        scene.eevee.use_gtao = False  # Global illumination off
        scene.eevee.use_bloom = False  # Bloom effect off
        scene.eevee.use_ssr = False  # Screen space reflections off
        scene.render.image_settings.file_format = 'PNG'  # Output as PNG

        # Adjust additional settings to ensure flat color rendering with no shading effects
        scene.world.color = (1, 1, 1)  # World background color to white

    def restore_original_settings(self, context, original_settings):
        logging.info("Restoring original render settings...")
        scene = context.scene
        scene.display_settings.display_device = original_settings['display_device']
        scene.view_settings.view_transform = original_settings['view_transform']
        scene.sequencer_colorspace_settings.name = original_settings['color_space']
        scene.render.engine = original_settings['engine']

    def render_and_save_image(self, context):
        logging.info("Rendering and saving image...")
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        texture_folder = os.path.join(os.path.dirname(bpy.data.filepath), "textures")
        os.makedirs(texture_folder, exist_ok=True)
        image_name = f"flat_color_{datetime_str}.png"
        render_filepath = os.path.join(texture_folder, image_name)
        context.scene.render.filepath = render_filepath
        bpy.ops.render.render(write_still=True)

    def restore_scene(self, context, original_engine, original_materials):
        logging.info("Restoring original materials and render engine settings...")
        context.scene.render.engine = original_engine
        for obj, mat in original_materials.items():
            if obj.type == 'MESH':
                obj.active_material = mat

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
        original_state = self.store_scene_state(context, camera)

        # Setup for rendering
        self.setup_rendering(context, camera, obj)

        # Render and save image
        rendered_image_path = self.render_image(context, obj)

        # Restore original settings
        self.restore_scene_state(context, camera, original_state)

        if not rendered_image_path:
            return {'CANCELLED'}

        logging.info("Rendered image successfully.")
        return {'FINISHED'}

    def store_scene_state(self, context, camera):
        state = {
            'clip_start': camera.data.clip_start,
            'clip_end': camera.data.clip_end,
            'engine': context.scene.render.engine,
            'settings': context.scene.render.image_settings.file_format,
            'compositor_nodes': self.store_compositor_nodes(context) if context.scene.use_nodes else None
        }
        return state

    def restore_scene_state(self, context, camera, state):
        logging.info("Restoring original scene state...")
        camera.data.clip_start = state['clip_start']
        camera.data.clip_end = state['clip_end']
        context.scene.render.engine = state['engine']
        context.scene.render.image_settings.file_format = state['settings']
        if state['compositor_nodes']:
            self.restore_compositor_nodes(context)

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
        cam_matrix_inv = camera.matrix_world.inverted()
        local_coords = [cam_matrix_inv @ obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
        
        # Calculate distances in camera space (z-depth)
        z_depths = [-co.z for co in local_coords]  # Negative because camera looks down negative Z-axis
        min_depth = min(z_depths)
        max_depth = max(z_depths)

        # Set up Map Range node to normalize depth
        map_range.inputs['From Min'].default_value = min_depth
        map_range.inputs['From Max'].default_value = max_depth
        map_range.inputs['To Min'].default_value = 0
        map_range.inputs['To Max'].default_value = 1

        # Adjust the curve of the depth map (optional)
        map_range.use_clamp = True

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
    bpy.utils.register_class(ZENV_OT_RenderComplete)
    bpy.utils.register_class(ZENV_OT_RenderColor)
    bpy.utils.register_class(ZENV_OT_RenderDepth)
    
def unregister():
    bpy.utils.unregister_class(ZENV_PT_RenderQuick)
    bpy.utils.unregister_class(ZENV_OT_RenderComplete)
    bpy.utils.unregister_class(ZENV_OT_RenderColor)
    bpy.utils.unregister_class(ZENV_OT_RenderDepth)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()
