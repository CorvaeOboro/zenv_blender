bl_info = {
    "name": 'RENDER Depth Map',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Renders depth map images with datetime suffix',
    "status": 'working',
    "approved": True,
    "sort_priority": '2',
    "group": 'Render',
    "group_prefix": 'RENDER',
    "description_short": 'renders depth with auto min max from selected object with datetime suffix',
    "description_long": """
RENDER Depth Map
 with automatic per object camera clipping adjustments.
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from datetime import datetime
from mathutils import Vector
import logging

# ------------------------------------------------------------------------
#    Logging
# ------------------------------------------------------------------------

# Setup logging to output to both console and Blender's info area
class ZENV_RenderDepthOnly_BlenderLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        print(msg)  # Print to console
        if record.levelno >= logging.INFO:
            self.blender_report(msg)
    
    def blender_report(self, msg):
        if hasattr(bpy.context, 'window_manager'):
            self.report_to_window({'INFO'}, msg)
    
    def report_to_window(self, type, msg):
        if hasattr(bpy.context, 'window_manager'):
            bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=msg), 
                                                title="Depth Render Info", 
                                                icon='INFO')

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Add console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Add Blender handler
blender_handler = ZENV_RenderDepthOnly_BlenderLogHandler()
blender_handler.setFormatter(formatter)
logger.addHandler(blender_handler)

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_RenderDepthOnly(bpy.types.Operator):
    """Operator for rendering depth maps"""
    bl_idname = "zenv.render_depth_datetime"
    bl_label = "Render Depth Map"
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo support
    
    def store_render_settings(self, context):
        """Store all render settings that will be modified"""
        scene = context.scene
        render = scene.render
        view_layer = context.view_layer
        
        return {
            'engine': render.engine,
            'use_nodes': scene.use_nodes,
            'use_pass_z': view_layer.use_pass_z,
            'file_format': render.image_settings.file_format,
            'color_mode': render.image_settings.color_mode,
            'filepath': render.filepath,
            'node_tree': self.store_node_tree(scene) if scene.use_nodes else None
        }
        
    def store_node_tree(self, scene):
        """Store the current node tree setup"""
        if not scene.node_tree:
            return None
            
        # Store node tree using Blender's built-in copy function
        return scene.node_tree.copy()
        
    def restore_render_settings(self, context, original_settings):
        """Restore all render settings to their original state"""
        scene = context.scene
        render = scene.render
        view_layer = context.view_layer
        
        # Restore basic settings
        render.engine = original_settings['engine']
        scene.use_nodes = original_settings['use_nodes']
        view_layer.use_pass_z = original_settings['use_pass_z']
        render.image_settings.file_format = original_settings['file_format']
        render.image_settings.color_mode = original_settings['color_mode']
        render.filepath = original_settings['filepath']
        
        # Restore node tree if it existed
        if original_settings['node_tree']:
            if scene.node_tree:
                bpy.data.node_groups.remove(scene.node_tree, do_unlink=True)
            scene.node_tree = original_settings['node_tree']
        
    def execute(self, context):
        logger.info("Starting depth map rendering process...")
        
        camera = context.scene.camera
        obj = context.active_object if context.active_object and context.active_object.type == 'MESH' else None

        if not camera:
            logger.error("No active camera found in scene")
            self.report({'ERROR'}, "No active camera found in scene")
            return {'CANCELLED'}
            
        if not obj:
            logger.error("No active mesh object selected")
            self.report({'ERROR'}, "Please select a mesh object to render depth map")
            return {'CANCELLED'}

        try:
            logger.info(f"Processing depth map for object: {obj.name}")
            
            # Store original settings
            original_settings = self.store_render_settings(context)
            
            logger.info("Setting up render settings...")
            self.setup_rendering(context, camera, obj)
            
            logger.info("Rendering depth map...")
            success, filepath = self.render_depth_map(context, obj)
            
            # Restore original settings
            logger.info("Restoring original render settings...")
            self.restore_render_settings(context, original_settings)
            
            if success:
                logger.info(f"Depth map rendered successfully to: {filepath}")
                self.report({'INFO'}, f"Depth map saved to: {filepath}")
                return {'FINISHED'}
                
            logger.error("Failed to render depth map")
            return {'CANCELLED'}
            
        except Exception as e:
            logger.error(f"Depth map rendering failed: {str(e)}")
            self.report({'ERROR'}, str(e))
            # Ensure settings are restored even if an error occurs
            if 'original_settings' in locals():
                self.restore_render_settings(context, original_settings)
            return {'CANCELLED'}

    def setup_rendering(self, context, camera, obj):
        """Setup render settings for depth map"""
        logger.info("Configuring render settings...")
        
        # Set render engine to Cycles (required for proper depth)
        context.scene.render.engine = 'CYCLES'
        context.scene.render.image_settings.file_format = 'PNG'
        context.scene.render.image_settings.color_mode = 'RGB'
        context.scene.use_nodes = True
        
        # Enable Z-pass for the active view layer
        context.view_layer.use_pass_z = True
        
        logger.info("Setting up compositor nodes...")
        # Setup compositor nodes
        node_tree = context.scene.node_tree
        node_tree.nodes.clear()
        
        # Create render layer node
        render_layer_node = node_tree.nodes.new('CompositorNodeRLayers')
        
        # Create map range node for depth
        map_range_node = node_tree.nodes.new('CompositorNodeMapRange')
        
        # Calculate depth range based on object vertices in camera space
        logger.info("Calculating depth range from object vertices...")
        cam_matrix_inv = camera.matrix_world.inverted()
        local_coords = [cam_matrix_inv @ obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
        z_depths = [-co.z for co in local_coords]  # Negative because camera looks down negative Z-axis
        min_depth = min(z_depths)
        max_depth = max(z_depths)
        
        logger.info(f"Depth range: {min_depth:.2f} to {max_depth:.2f}")
        
        # Set up Map Range node to normalize depth
        map_range_node.inputs['From Min'].default_value = min_depth
        map_range_node.inputs['From Max'].default_value = max_depth
        map_range_node.inputs['To Min'].default_value = 0
        map_range_node.inputs['To Max'].default_value = 1
        map_range_node.use_clamp = True
        
        # Create invert node
        invert_node = node_tree.nodes.new('CompositorNodeInvert')
        
        # Create composite output node
        composite_node = node_tree.nodes.new('CompositorNodeComposite')
        
        # Link nodes
        node_tree.links.new(render_layer_node.outputs['Depth'], map_range_node.inputs[0])
        node_tree.links.new(map_range_node.outputs[0], invert_node.inputs[1])
        node_tree.links.new(invert_node.outputs[0], composite_node.inputs['Image'])
        
        # Position nodes for better organization
        render_layer_node.location = (-300, 0)
        map_range_node.location = (0, 0)
        invert_node.location = (300, 0)
        composite_node.location = (600, 0)
        
        logger.info("Compositor nodes setup complete")

    def render_depth_map(self, context, obj):
        """Render and save the depth map"""
        # Get current blend file path and name
        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            logger.warning("Blender file not saved, using default name: 00_texture")
            self.report({'WARNING'}, "Blender file not saved yet, using default name: 00_texture")
            blend_filepath = "00_texture"
            
        # Extract blend file name without extension
        blend_filename = os.path.splitext(os.path.basename(blend_filepath))[0]
        
        # Create datetime suffix
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Setup output path using blend file name for both folder and file
        output_folder = os.path.join(os.path.dirname(blend_filepath), blend_filename)
        os.makedirs(output_folder, exist_ok=True)
        logger.info(f"Created output folder: {output_folder}")
        
        # Set render path with blend filename included
        render_filepath = os.path.join(output_folder, f"{blend_filename}_depth_{datetime_str}.png")
        context.scene.render.filepath = render_filepath
        
        logger.info(f"Rendering to: {render_filepath}")
        
        # Render
        bpy.ops.render.render(write_still=True)
        
        if not os.path.exists(render_filepath):
            logger.error(f"Failed to save rendered depth map to: {render_filepath}")
            raise Exception("Failed to save rendered depth map")
            
        logger.info(f"Successfully saved depth map: {render_filepath}")
        return True, render_filepath

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RenderDepthOnly(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for depth map rendering"""
    bl_label = "RENDER Depth Map"
    bl_idname = "ZENV_PT_RenderDepthOnly_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.render_depth_datetime")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PT_RenderDepthOnly,
    ZENV_OT_RenderDepthOnly,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
