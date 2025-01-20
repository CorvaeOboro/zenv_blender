bl_info = {
    "name": "RENDER Scale per Pixel",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (3, 80, 0),
    "location": "View3D > ZENV",
    "description": "Renders Scale per Pixel  ",
}

import bpy
import os
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# UI
class ZENV_PT_RenderScalePerPixel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Scale per Pixel Shader"
    bl_idname = "ZENV_PT_RenderScalePerPixel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "debug_mode", text="Debug")
        layout.operator("zenv.render_scale_per_pixel")

# Property to control debug mode
def init_properties():
    bpy.types.Scene.debug_mode = bpy.props.BoolProperty(
        name="Debug Mode",
        description="Enable debug mode to prevent scene state changes",
        default=False
    )

def clear_properties():
    del bpy.types.Scene.debug_mode

class ZENV_OT_RenderScalePerPixel(bpy.types.Operator):
    # Operator for rendering scale per pixel
    bl_idname = "zenv.render_scale_per_pixel"
    bl_label = "Render Scale Per Pixel"

    def execute(self, context):
        logging.info("Starting scale per pixel rendering...")
        selected_objects = context.selected_objects
        debug_mode = context.scene.debug_mode

        if not context.scene.camera or not selected_objects:
            self.report({'ERROR'}, "No active camera or selected objects found.")
            return {'CANCELLED'}

        # Store original state if not in debug mode
        original_state = self.store_scene_state(context) if not debug_mode else None

        # Setup for rendering
        self.setup_rendering(context, selected_objects)

        # Render and save image
        self.render_and_save_image(context, selected_objects)

        # Restore original state if not in debug mode
        if not debug_mode:
            self.restore_scene_state(context, original_state)

        return {'FINISHED'}

    def store_scene_state(self, context):
        # Store current render settings and materials
        state = {
            'render_engine': context.scene.render.engine,
            'materials': {obj: obj.active_material for obj in context.selected_objects if obj.type == 'MESH'}
        }
        return state

    def restore_scene_state(self, context, state):
        context.scene.render.engine = state['render_engine']
        for obj, mat in state['materials'].items():
            obj.active_material = mat

    def setup_rendering(self, context, selected_objects):
        logging.info("Setting up rendering for scale per pixel...")
        context.scene.render.engine = 'BLENDER_EEVEE'
        context.scene.render.image_settings.file_format = 'PNG'

        # Assign custom shader material to each object
        for obj in selected_objects:
            if obj.type == 'MESH':
                obj.active_material = self.create_scale_shader()

    def create_scale_shader():
        # Create a shader for World Scale Per Pixel 
        material_name = "ScalePerPixelShader"
        material = bpy.data.materials.get(material_name) or bpy.data.materials.new(name=material_name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        # Create nodes
        geometry_node = nodes.new(type='ShaderNodeNewGeometry')
        camera_data_node = nodes.new(type='ShaderNodeCameraData')
        distance_node = nodes.new(type='ShaderNodeVectorMath')
        distance_node.operation = 'DISTANCE'
        multiply_node = nodes.new(type='ShaderNodeMath')
        multiply_node.operation = 'MULTIPLY'
        log_node = nodes.new(type='ShaderNodeMath')
        log_node.operation = 'LOGARITHM'
        clamp_node = nodes.new(type='ShaderNodeMath')
        clamp_node.operation = 'CLAMP'
        map_range_node = nodes.new(type='ShaderNodeMapRange')
        emission_node = nodes.new(type='ShaderNodeEmission')
        output_node = nodes.new(type='ShaderNodeOutputMaterial')

        # Configure nodes
        log_node.inputs[1].default_value = 10  # Base 10 for logarithm
        clamp_node.inputs[1].default_value = -3  # log10(0.001) for 1mm
        clamp_node.inputs[2].default_value = 0   # log10(1) for 1m
        # remap from -3to0 to 0to1
        map_range_node.inputs[1].default_value = -3  # From Min
        map_range_node.inputs[2].default_value = 0   # From Max
        map_range_node.inputs[3].default_value = 0   # To Min
        map_range_node.inputs[4].default_value = 1   # To Max

        # Connect nodes
        links.new(geometry_node.outputs['Position'], distance_node.inputs[0])
        links.new(camera_data_node.outputs['View Vector'], distance_node.inputs[1])
        links.new(distance_node.outputs['Value'], multiply_node.inputs[0])
        # Connect a predefined texel size to multiply_node.inputs[1] if necessary
        links.new(multiply_node.outputs[0], log_node.inputs[0])
        links.new(log_node.outputs[0], clamp_node.inputs[0])
        links.new(clamp_node.outputs[0], map_range_node.inputs[0])
        links.new(map_range_node.outputs[0], emission_node.inputs[0])
        links.new(emission_node.outputs[0], output_node.inputs[0])

        return material

    def render_and_save_image(self, context, selected_objects):
        logging.info("Rendering and saving image...")
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        texture_folder = os.path.join(os.path.dirname(bpy.data.filepath), "textures")
        os.makedirs(texture_folder, exist_ok=True)

        for obj in selected_objects:
            image_name = f"{obj.name}_scale_per_pixel_{datetime_str}.png"
            render_filepath = os.path.join(texture_folder, image_name)
            context.scene.render.filepath = render_filepath
            bpy.ops.render.render(write_still=True)

            if os.path.exists(render_filepath):
                logging.info(f"Image rendered for {obj.name} to: {render_filepath}")
            else:
                self.report({'ERROR'}, f"Failed to render image for {obj.name}.")
                logging.error("Rendered image file not found for " + obj.name)

# Registration
def register():
    init_properties()
    bpy.utils.register_class(ZENV_PT_RenderScalePerPixel)
    bpy.utils.register_class(ZENV_OT_RenderScalePerPixel)
    
def unregister():
    clear_properties()
    bpy.utils.unregister_class(ZENV_PT_RenderScalePerPixel)
    bpy.utils.unregister_class(ZENV_OT_RenderScalePerPixel)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register()
