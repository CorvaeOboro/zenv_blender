#region blinfo
bl_info = {
    "name": 'TEX Vertex Color Baker',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Bake vertex colors to texture maps and vice versa',
    "status": 'wip',
    "approved": False,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 70,
    "addon_order": 70,
    "location": 'View3D > ZENV',
    "tags": ['texture', 'vertex', 'color', 'bake', 'uv'],
    "description_short": 'Bake vertex colors to texture maps and vice versa.',
    "description_medium": 'Provides two operators: bake active vertex-color layer to an image '
                          'texture via Cycles, and sample a texture per UV loop to write '
                          'vertex colors back. Includes auto-unwrap, render settings '
                          'preservation, and temporary material handling.',
    "description_long": 'Vertex color baking utility with two-way conversion. The bake '
                        'operator creates a temporary material, configures Cycles bake '
                        'settings, bakes the active vertex color layer to a PNG/JPEG/Targa '
                        'image, and restores all render settings afterwards. The set-from-'
                        'texture operator samples an image per UV loop with correct Y-flip '
                        'and bounds clamping, writing RGBA into the active vertex color layer.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}
#endregion

#region imports
import bpy
import os
import random
import logging
from datetime import datetime
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator, Panel
#endregion

#region logging
# Module logger setup - stream handler install / uninstall
logger = logging.getLogger(__name__)
_log_handler = None


def _install_logger():
    """Install a stream handler on the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setLevel(logging.DEBUG)
    _log_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.DEBUG)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region utils
# Utility functions - output dirs, texture naming, material nodes, render settings, UV sampling
class ZENV_VertexBake_Utils:
    """Utility functions for vertex color baking"""

    # Map Blender image file_format enum values to conventional file extensions.
    FILE_EXTENSIONS = {
        'PNG': 'png',
        'JPEG': 'jpg',
        'TARGA': 'tga',
    }

    @staticmethod
    def ensure_output_directory(context):
        """Ensure output directory exists"""
        output_path = bpy.path.abspath(context.scene.zenv_output_path)
        os.makedirs(output_path, exist_ok=True)
        return output_path

    @staticmethod
    def generate_texture_name(obj_name):
        """Generate unique texture filename.

        Uses a timestamp plus a short random suffix so that two bakes issued
        within the same second do not collide on disk.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = format(random.randint(0, 0xFFFF), '04x')
        return f"{obj_name}_vcol_{timestamp}_{suffix}"

    @staticmethod
    def setup_material_nodes(material, image=None, vertex_color_name=None):
        """Set up material nodes for baking"""
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        # Create nodes
        vertex_color = nodes.new('ShaderNodeVertexColor')
        if vertex_color_name:
            vertex_color.layer_name = vertex_color_name

        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')

        # Position nodes
        vertex_color.location = (-300, 0)
        principled.location = (0, 0)
        output.location = (300, 0)

        # Create links
        links.new(vertex_color.outputs['Color'], principled.inputs['Base Color'])
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

        # Add image texture node if provided
        if image:
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.image = image
            tex_image.location = (0, -300)
            # Only the active node is used as the bake target.
            nodes.active = tex_image

    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking.

        Returns a dict of the previous values so the caller can restore them
        after baking via restore_render_settings.
        """
        scene = context.scene
        render = scene.render
        cycles = scene.cycles
        bake = render.bake
        previous = {
            'engine': render.engine,
            'device': cycles.device,
            'use_selected_to_active': bake.use_selected_to_active,
            'use_clear': bake.use_clear,
            'margin': bake.margin,
        }
        render.engine = 'CYCLES'
        cycles.device = 'CPU'
        bake.use_selected_to_active = False
        bake.use_clear = True
        bake.margin = 4
        return previous

    @staticmethod
    def restore_render_settings(context, previous):
        """Restore render settings captured by setup_render_settings."""
        if not previous:
            return
        scene = context.scene
        render = scene.render
        cycles = scene.cycles
        bake = render.bake
        render.engine = previous['engine']
        cycles.device = previous['device']
        bake.use_selected_to_active = previous['use_selected_to_active']
        bake.use_clear = previous['use_clear']
        bake.margin = previous['margin']

    @staticmethod
    def sample_image_into_vertex_colors(obj, image):
        """Sample ``image`` per UV loop and write the result into the active
        vertex-color layer of ``obj``.

        Corrects the prior implementation which:
          * ignored the V coordinate,
          * used a wrong flat-index formula,
          * did not flip the Y axis (Blender UV origin is bottom-left while
            ``image.pixels`` is laid out top-left first),
          * did not clamp coordinates, so UVs at exactly 1.0 sampled past the
            last pixel and produced empty slices.
        """
        mesh = obj.data
        if not mesh.uv_layers or mesh.uv_layers.active is None:
            raise RuntimeError("Object has no UV map to sample with.")

        if not mesh.vertex_colors:
            vcol = mesh.vertex_colors.new()
        else:
            vcol = mesh.vertex_colors.active

        # Capture the UV layer reference AFTER any vertex-color layer creation.
        # Creating a new vertex color layer reallocates the loop-domain data
        # arrays in Blender's RNA, which invalidates captured UV
        # data references (they return NaN until re-fetched).
        uv_layer = mesh.uv_layers.active.data

        width, height = image.size
        if width <= 0 or height <= 0:
            raise RuntimeError("Source image has zero pixels.")

        # Read the flat RGBA buffer once; per-loop slicing of the bpy_prop_array
        # is far slower than indexing into a Python list.
        pixels = list(image.pixels)

        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                uv = uv_layer[loop_idx].uv
                # Clamp to valid pixel range and flip V so the image is not
                # sampled upside-down.
                x = min(max(int(uv.x * width), 0), width - 1)
                y = min(max(int((1.0 - uv.y) * height), 0), height - 1)
                i = (y * width + x) * 4
                vcol.data[loop_idx].color = pixels[i:i + 4]
        return vcol

    @staticmethod
    def ensure_uv_map(context, obj):
        """Ensure object has a UV map"""
        if not obj.data.uv_layers:
            if not context.scene.zenv_auto_unwrap:
                return False

            # Create new UV layer
            obj.data.uv_layers.new(name="UVMap")

            # Enter edit mode and unwrap
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.unwrap(
                method='ANGLE_BASED',
                margin=context.scene.zenv_unwrap_margin
            )
            bpy.ops.object.mode_set(mode='OBJECT')

        return True
#endregion

#region ops
# Operators - bake vertex colors to texture and set vertex colors from texture

#region ops-bake
# Bake active vertex color layer to an image texture via Cycles
class ZENV_OT_VertexBake_BakeTexture(Operator):
    """Bake vertex colors to texture"""
    bl_idname = "zenv.vertexbake_bake"
    bl_label = "Bake Vertex Colors"
    bl_description = "Bake vertex colors to texture map"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return False
        # The enum may be unset (None) or point at the placeholder 'None' item
        # returned when no layers exist. Validate against the active layer
        # directly so the operator is only enabled when there is something to
        # bake.
        if not obj.data.vertex_colors or obj.data.vertex_colors.active is None:
            return False
        selected = context.scene.zenv_use_vertex_color
        return selected not in (None, '', 'None')

    def execute(self, context):
        try:
            # Get active object
            obj = context.active_object

            # Ensure UV map exists
            if not ZENV_VertexBake_Utils.ensure_uv_map(context, obj):
                self.report({'ERROR'}, "Object needs UV coordinates. Enable Auto Unwrap or create UVs manually.")
                return {'CANCELLED'}

            # Setup output paths
            output_dir = ZENV_VertexBake_Utils.ensure_output_directory(context)
            texture_name = ZENV_VertexBake_Utils.generate_texture_name(obj.name)
            output_format = context.scene.zenv_output_format
            ext = ZENV_VertexBake_Utils.FILE_EXTENSIONS.get(output_format, output_format.lower())
            image_path = os.path.join(output_dir, f"{texture_name}.{ext}")

            # Create image for baking
            image = bpy.data.images.new(
                texture_name,
                context.scene.zenv_bake_resolution,
                context.scene.zenv_bake_resolution
            )
            image.filepath_raw = image_path
            image.file_format = context.scene.zenv_output_format

            # Use a dedicated temporary material so the user's existing
            # materials and node trees are never modified. We append it as a
            # new slot, make it active for baking, then restore the original
            # active slot and remove the temp material afterwards.
            temp_mat = bpy.data.materials.new(name=f"{obj.name}_vcol_bake_temp")
            original_active_slot = obj.active_material_index
            obj.data.materials.append(temp_mat)
            obj.active_material_index = len(obj.data.materials) - 1

            # Setup nodes with selected vertex color layer
            ZENV_VertexBake_Utils.setup_material_nodes(
                temp_mat,
                image,
                context.scene.zenv_use_vertex_color
            )
            render_settings_backup = ZENV_VertexBake_Utils.setup_render_settings(context)

            try:
                # Save a copy of the blend file alongside the texture if requested.
                # copy=True writes the file without switching the active document,
                # so the user stays in their original scene.
                if context.scene.zenv_save_blend:
                    blend_path = os.path.join(output_dir, f"{texture_name}.blend")
                    bpy.ops.wm.save_as_mainfile(filepath=blend_path, copy=True)

                # Perform baking
                bpy.ops.object.bake(
                    type='DIFFUSE',
                    pass_filter={'COLOR'},
                    use_selected_to_active=False
                )

                # Save image
                image.save_render(filepath=image_path)

                # Drop the in-memory image datablock so repeated bakes do not
                # accumulate orphan images. The file on disk is unaffected.
                if image.users == 1:
                    bpy.data.images.remove(image)

                self.report({'INFO'}, f"Baked texture saved to: {image_path}")
                return {'FINISHED'}
            finally:
                # Always restore the user's original active material slot
                # and remove the temporary bake material, even on failure.
                if temp_mat.name in bpy.data.materials:
                    bpy.data.materials.remove(temp_mat)
                if 0 <= original_active_slot < len(obj.data.materials):
                    obj.active_material_index = original_active_slot
                ZENV_VertexBake_Utils.restore_render_settings(context, render_settings_backup)

        except Exception as e:
            logger.error(f"Error during baking: {str(e)}")
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}
#endregion

#region ops-setfrom
# Sample a texture per UV loop and write RGBA into the active vertex color layer
class ZENV_OT_VertexBake_SetFromTexture(Operator):
    """Set vertex colors from texture"""
    bl_idname = "zenv.vertexbake_set_from_texture"
    bl_label = "Set From Texture"
    bl_description = "Set vertex colors from texture map"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and
                context.scene.zenv_texture_path and
                os.path.exists(bpy.path.abspath(context.scene.zenv_texture_path)))

    def execute(self, context):
        try:
            obj = context.active_object

            # Ensure UV map exists
            if not ZENV_VertexBake_Utils.ensure_uv_map(context, obj):
                self.report({'ERROR'}, "Object needs UV coordinates. Enable Auto Unwrap or create UVs manually.")
                return {'CANCELLED'}

            # Load texture
            texture_path = bpy.path.abspath(context.scene.zenv_texture_path)
            image = bpy.data.images.load(texture_path)

            try:
                ZENV_VertexBake_Utils.sample_image_into_vertex_colors(obj, image)
            except RuntimeError as sample_err:
                if image.users == 1:
                    bpy.data.images.remove(image)
                self.report({'ERROR'}, str(sample_err))
                return {'CANCELLED'}

            # Cleanup: only remove the image if nothing else references it,
            # since bpy.data.images.load may have returned an existing datablock
            # already used by another material/texture.
            if image.users == 1:
                bpy.data.images.remove(image)

            self.report({'INFO'}, "Vertex colors set from texture")
            return {'FINISHED'}

        except Exception as e:
            logger.error(f"Error setting vertex colors: {str(e)}")
            self.report({'ERROR'}, f"Failed to set vertex colors: {str(e)}")
            return {'CANCELLED'}
#endregion

#endregion

#region props
# Property management - scene properties for bake settings, UV, vertex color selection
class ZENV_VertexBake_Properties:
    """Property management for vertex color baking addon"""

    @classmethod
    def register(cls):
        """Register all properties (idempotent - skips already-registered props)"""
        if not hasattr(bpy.types.Scene, 'zenv_bake_resolution'):
            bpy.types.Scene.zenv_bake_resolution = IntProperty(
                name="Resolution",
                description="Texture resolution for baking",
                default=1024,
                min=64,
                max=8192
            )
        if not hasattr(bpy.types.Scene, 'zenv_output_format'):
            bpy.types.Scene.zenv_output_format = EnumProperty(
                name="Format",
                description="Output image format",
                items=[
                    ('PNG', "PNG", "Save as PNG"),
                    ('JPEG', "JPEG", "Save as JPEG"),
                    ('TARGA', "TARGA", "Save as Targa")
                ],
                default='PNG'
            )
        if not hasattr(bpy.types.Scene, 'zenv_save_blend'):
            bpy.types.Scene.zenv_save_blend = BoolProperty(
                name="Save Blend",
                description="Save .blend file with baked texture",
                default=False
            )
        if not hasattr(bpy.types.Scene, 'zenv_output_path'):
            bpy.types.Scene.zenv_output_path = StringProperty(
                name="Output Path",
                description="Path for saving baked textures",
                default="//textures/",
                subtype='DIR_PATH'
            )
        if not hasattr(bpy.types.Scene, 'zenv_unwrap_margin'):
            bpy.types.Scene.zenv_unwrap_margin = FloatProperty(
                name="UV Margin",
                description="Margin between UV islands",
                default=0.001,
                min=0.0,
                max=1.0
            )
        if not hasattr(bpy.types.Scene, 'zenv_auto_unwrap'):
            bpy.types.Scene.zenv_auto_unwrap = BoolProperty(
                name="Auto Unwrap",
                description="Automatically unwrap if no UVs exist",
                default=True
            )
        if not hasattr(bpy.types.Scene, 'zenv_use_vertex_color'):
            bpy.types.Scene.zenv_use_vertex_color = EnumProperty(
                name="Vertex Color Layer",
                description="Which vertex color layer to bake",
                items=lambda self, context: ZENV_VertexBake_Properties.get_vertex_color_items(context),
            )
        if not hasattr(bpy.types.Scene, 'zenv_texture_path'):
            bpy.types.Scene.zenv_texture_path = StringProperty(
                name="Texture Path",
                description="Path to texture for setting vertex colors",
                default="",
                subtype='FILE_PATH'
            )

    @staticmethod
    def get_vertex_color_items(context):
        """Get list of vertex color layers from active object"""
        items = []
        if context.active_object and context.active_object.type == 'MESH':
            mesh = context.active_object.data
            items = [(layer.name, layer.name, f"Use {layer.name} vertex colors")
                    for layer in mesh.vertex_colors]
        return items or [('None', "No Vertex Colors", "No vertex color layers found")]

    @classmethod
    def unregister(cls):
        """Unregister all properties"""
        for prop_name in (
            'zenv_bake_resolution', 'zenv_output_format', 'zenv_save_blend',
            'zenv_output_path', 'zenv_unwrap_margin', 'zenv_auto_unwrap',
            'zenv_use_vertex_color', 'zenv_texture_path',
        ):
            if hasattr(bpy.types.Scene, prop_name):
                delattr(bpy.types.Scene, prop_name)
#endregion

#region panel
# View3D panel UI for vertex color baking controls
class ZENV_PT_VertexBake(Panel):
    """Panel for vertex color baking tools"""
    bl_label = "TEX Vertex Color Baker"
    bl_idname = "ZENV_PT_vertexbake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # UV settings
        box = layout.box()
        box.label(text="UV Settings:")
        box.prop(scene, "zenv_auto_unwrap")
        if scene.zenv_auto_unwrap:
            box.prop(scene, "zenv_unwrap_margin")

        # Vertex Color settings
        box = layout.box()
        box.label(text="Vertex Color Settings:")
        box.prop(scene, "zenv_use_vertex_color")

        # Bake settings
        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(scene, "zenv_bake_resolution")
        box.prop(scene, "zenv_output_format")
        box.prop(scene, "zenv_output_path")
        box.prop(scene, "zenv_save_blend")

        # Bake button
        layout.operator("zenv.vertexbake_bake")

        # Texture to Vertex Color
        box = layout.box()
        box.label(text="Texture to Vertex Color:")
        box.prop(scene, "zenv_texture_path")
        box.operator("zenv.vertexbake_set_from_texture")
#endregion

#region register
# Class registration and module load / unload
classes = (
    ZENV_OT_VertexBake_BakeTexture,
    ZENV_OT_VertexBake_SetFromTexture,
    ZENV_PT_VertexBake,
)

def register():
    _install_logger()
    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except ValueError:
            pass
    ZENV_VertexBake_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass
    ZENV_VertexBake_Properties.unregister()
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
