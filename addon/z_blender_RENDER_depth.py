#region META
bl_info = {
    "name": 'RENDER Depth Map',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Renders depth map images with datetime suffix',
    "status": 'working',
    "approved": True,
    "group": 'Render',
    "group_prefix": 'RENDER',
    "group_order": 90,
    "addon_order": 20,
    "tags": ['render', 'depth', 'map', 'z-depth', 'cycles', 'compositor'],
    "description_short": 'renders depth with auto min max from selected object with datetime suffix',
    "description_medium": 'render a depth map for the active mesh object using Cycles and a compositor node tree - auto-normalizes depth range from object vertices in camera space and saves with datetime suffix',
    "description_long": """
RENDER Depth Map
 with automatic per object camera clipping adjustments.
""",
    "image_overview": 'zenv_blender_RENDER_depth.png',
    "addon_image": 'zenv_blender_RENDER_depth.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
from datetime import datetime
from mathutils import Vector

import logging
logger = logging.getLogger(__name__)
_zenv_depth_console_handler = None

# Blender 5.0 unified the compositor: many CompositorNode* types were removed
# in favor of their ShaderNode* counterparts, the Composite output node was
# replaced by Group Output, and scene.node_tree became compositing_node_group.
_IS_BLENDER_5 = bpy.app.version >= (5, 0, 0)
#endregion


#region OP
class ZENV_OT_RenderDepthOnly(bpy.types.Operator):
    """Operator for rendering depth maps"""
    bl_idname = "zenv.render_depth_datetime"
    bl_label = "Render Depth Map"
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo support

    @classmethod
    def poll(cls, context):
        """Only enable when there is an active mesh object and a scene camera."""
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and context.scene.camera is not None)

    @staticmethod
    def _get_compositor_tree(scene):
        """Return the scene's compositor node tree.

        Blender 5.0+ removed ``scene.node_tree`` and replaced it with
        ``scene.compositing_node_group`` (a standalone node-group datablock).
        Support both APIs so the addon keeps working on 4.x and 5.x.
        """
        nt = getattr(scene, 'compositing_node_group', None)
        if nt is None:
            nt = getattr(scene, 'node_tree', None)
        return nt

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
            'node_tree': self.store_node_tree(scene) if scene.use_nodes else None,
            # On Blender 5.x, store the original compositor node group
            # reference so we can restore/reassign it after rendering.
            'original_comp_group': getattr(scene, 'compositing_node_group', None),
        }
        
    def store_node_tree(self, scene):
        """Store the current node tree setup"""
        nt = self._get_compositor_tree(scene)
        if not nt:
            return None

        # Store node tree using Blender's built-in copy function
        return nt.copy()

    @staticmethod
    def _copy_nodes(src_tree, dst_tree):
        """Copy all nodes and links from ``src_tree`` into ``dst_tree``.

        ``Scene.node_tree`` is read-only and cannot be reassigned, so we
        rebuild the original nodes/links in-place from the saved copy.
        """
        dst_tree.nodes.clear()
        dst_tree.links.clear()
        # Map old node names to new node objects so links can be rebuilt.
        name_map = {}
        for src_node in src_tree.nodes:
            new_node = dst_tree.nodes.new(src_node.bl_idname)
            new_node.name = src_node.name
            new_node.label = src_node.label
            new_node.location = src_node.location
            # Copy default input values where applicable.
            for src_input in src_node.inputs:
                if src_input.is_linked:
                    continue
                if hasattr(src_input, 'default_value'):
                    try:
                        new_node.inputs[src_input.name].default_value = src_input.default_value
                    except Exception:
                        pass
            # Copy node-specific attributes (use_clamp/clamp, invert, etc.).
            for attr in ('use_clamp', 'clamp', 'invert', 'blend_type'):
                if hasattr(src_node, attr):
                    try:
                        setattr(new_node, attr, getattr(src_node, attr))
                    except Exception:
                        pass
            name_map[src_node.name] = new_node
        # Rebuild links.
        for src_link in src_tree.links:
            from_node = name_map.get(src_link.from_node.name)
            to_node = name_map.get(src_link.to_node.name)
            if from_node is None or to_node is None:
                continue
            from_sock = None
            for sock in from_node.outputs:
                if sock.name == src_link.from_socket.name:
                    from_sock = sock
                    break
            to_sock = None
            for sock in to_node.inputs:
                if sock.name == src_link.to_socket.name:
                    to_sock = sock
                    break
            if from_sock is not None and to_sock is not None:
                dst_tree.links.new(from_sock, to_sock)

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
            nt = self._get_compositor_tree(scene)
            if nt:
                self._copy_nodes(original_settings['node_tree'], nt)
        else:
            # No original node tree - clear any nodes we added.
            nt = self._get_compositor_tree(scene)
            if nt:
                nt.nodes.clear()

        # Blender 5.x: if we created a compositor node group that didn't
        # exist before, remove it and restore the original reference.
        if hasattr(scene, 'compositing_node_group'):
            original_group = original_settings.get('original_comp_group')
            current_group = scene.compositing_node_group
            if current_group is not original_group:
                if current_group is not None:
                    bpy.data.node_groups.remove(current_group)
                scene.compositing_node_group = original_group
        
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

        original_settings = None
        try:
            logger.info(f"Processing depth map for object: {obj.name}")

            # Store original settings
            original_settings = self.store_render_settings(context)

            logger.info("Setting up render settings...")
            self.setup_rendering(context, camera, obj)

            logger.info("Rendering depth map...")
            success, filepath = self.render_depth_map(context, obj)

            if success:
                logger.info(f"Depth map rendered successfully to: {filepath}")
                self.report({'INFO'}, f"Depth map saved to: {filepath}")
                return {'FINISHED'}

            logger.error("Failed to render depth map")
            return {'CANCELLED'}

        except Exception as e:
            logger.error(f"Depth map rendering failed: {str(e)}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        finally:
            if original_settings is not None:
                logger.info("Restoring original render settings...")
                try:
                    self.restore_render_settings(context, original_settings)
                except Exception:
                    logger.exception("Failed to restore render settings")

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
        node_tree = self._get_compositor_tree(context.scene)
        if node_tree is None:
            # Blender 5.0+ stores the compositor tree as a standalone
            # node-group datablock (``compositing_node_group``) which is
            # not created automatically when ``use_nodes`` is toggled on.
            # Create one and assign it to the scene.
            if hasattr(context.scene, 'compositing_node_group'):
                node_tree = bpy.data.node_groups.new(
                    "CompositorNt", 'CompositorNodeTree')
                context.scene.compositing_node_group = node_tree
            else:
                # Blender 4.x: node_tree should exist after use_nodes=True
                node_tree = context.scene.node_tree
        node_tree.nodes.clear()
        
        # Create render layer node (same type on both versions)
        render_layer_node = node_tree.nodes.new('CompositorNodeRLayers')
        
        # Create map range node for depth.
        # Blender 5.0 unified nodes: CompositorNodeMapRange was removed,
        # use ShaderNodeMapRange instead. The attribute is ``clamp`` (not
        # ``use_clamp``) on the shader version.
        map_range_type = 'ShaderNodeMapRange' if _IS_BLENDER_5 else 'CompositorNodeMapRange'
        map_range_node = node_tree.nodes.new(map_range_type)
        
        # Calculate depth range based on object vertices in camera space
        logger.info("Calculating depth range from object vertices...")
        cam_matrix_inv = camera.matrix_world.inverted()
        local_coords = [cam_matrix_inv @ obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
        z_depths = [-co.z for co in local_coords]  # Negative because camera looks down negative Z-axis
        min_depth = min(z_depths)
        max_depth = max(z_depths)
        
        logger.info(f"Depth range: {min_depth:.2f} to {max_depth:.2f}")
        
        # Set up Map Range node to normalize depth.
        # The original 4.x code used a separate Invert node to flip the
        # normalized depth (so closer = brighter). On 5.0, CompositorNodeInvert
        # was removed and ShaderNodeInvert is not unified (it can't be added
        # to a compositor tree). Instead, we simply swap To Min/To Max to
        # achieve the same inversion in a single node.
        map_range_node.inputs['From Min'].default_value = min_depth
        map_range_node.inputs['From Max'].default_value = max_depth
        map_range_node.inputs['To Min'].default_value = 1
        map_range_node.inputs['To Max'].default_value = 0
        if _IS_BLENDER_5:
            map_range_node.clamp = True
        else:
            map_range_node.use_clamp = True
        
        # Create output node.
        # Blender 5.0: CompositorNodeComposite was removed, replaced by
        # Group Output. An interface socket must be created for the input.
        if _IS_BLENDER_5:
            composite_node = node_tree.nodes.new('NodeGroupOutput')
            node_tree.interface.new_socket(
                name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
        else:
            composite_node = node_tree.nodes.new('CompositorNodeComposite')
        
        # Link nodes
        node_tree.links.new(render_layer_node.outputs['Depth'], map_range_node.inputs[0])
        node_tree.links.new(map_range_node.outputs[0], composite_node.inputs['Image'])
        
        # Position nodes for better organization
        render_layer_node.location = (-300, 0)
        map_range_node.location = (0, 0)
        composite_node.location = (300, 0)
        
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
#endregion


#region PANEL
class ZENV_PT_RenderDepthOnly(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for depth map rendering"""
    bl_label = "RENDER Depth Map"
    bl_idname = "ZENV_PT_RenderDepthOnly"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.render_depth_datetime")
#endregion


#region REG
classes = (
    ZENV_OT_RenderDepthOnly,
    ZENV_PT_RenderDepthOnly,
)


def register():
    """Register the addon classes and logger."""
    global _zenv_depth_console_handler
    if _zenv_depth_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_depth_console_handler = handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)


def unregister():
    """Unregister the addon classes and logger."""
    global _zenv_depth_console_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    if _zenv_depth_console_handler is not None:
        try:
            logger.removeHandler(_zenv_depth_console_handler)
        except ValueError:
            pass
        _zenv_depth_console_handler = None


if __name__ == "__main__":
    register()
#endregion
