bl_info = {
    "name": 'TEX Bake Worldspace Bounds Gradients',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260309',
    "description": 'Bake worldspace bounds gradient  for multiple selected mesh objects by temporarily merging them',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Texture',
    "group_prefix": 'TEX',
    "description_short": 'multi-object worldspace gradients bake (XYZ RGB or vertical grayscale)',
    "description_long": """
TEX MULTI-OBJECT WORLDSPACE BOUNDS GRADIENT BAKER
- Select multiple mesh objects that share a UV layout / texture space
- Addon duplicates them, joins into a temp object
- Computes combined WORLDSPACE bounds of the joined temp object
- Bakes a bounded gradient to a new image and saves to //textures/
Modes:
- XYZ RGB: R=X, G=Y, B=Z (each normalized to 0-1 within combined bounds)
- Vertical Only: grayscale from world Z (same value in RGB)
Bakes EMIT for a lighting-independent result.
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from datetime import datetime
import logging
from mathutils import Vector

logger = logging.getLogger(__name__)
_zenv_worldspace_gradient_bake_console_handler = None


class ZENV_WorldspaceGradientBake_Properties:
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_wsgrad_bake_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Gradient bake texture resolution",
            default=1024,
            min=64,
            max=8192,
        )
        bpy.types.Scene.zenv_wsgrad_bake_samples = bpy.props.IntProperty(
            name="Samples",
            description="Cycles samples for gradient baking",
            default=32,
            min=1,
            max=4096,
        )
        bpy.types.Scene.zenv_wsgrad_bake_margin = bpy.props.IntProperty(
            name="Margin",
            description="Bake padding in pixels (0 = no padding)",
            default=4,
            min=0,
            max=256,
        )
        bpy.types.Scene.zenv_wsgrad_bake_use_gpu = bpy.props.BoolProperty(
            name="Use GPU",
            description="Use GPU for Cycles baking when available",
            default=True,
        )
        bpy.types.Scene.zenv_wsgrad_vertical_only = bpy.props.BoolProperty(
            name="Vertical Only",
            description="Bake a vertical (world Z) grayscale gradient (most common)",
            default=True,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_wsgrad_bake_resolution
        del bpy.types.Scene.zenv_wsgrad_bake_samples
        del bpy.types.Scene.zenv_wsgrad_bake_margin
        del bpy.types.Scene.zenv_wsgrad_bake_use_gpu
        del bpy.types.Scene.zenv_wsgrad_vertical_only


class ZENV_WorldspaceGradientBake_Utils:
    @staticmethod
    def ensure_texture_directory():
        texture_dir = bpy.path.abspath("//textures")
        if not os.path.exists(texture_dir):
            os.makedirs(texture_dir)
        return texture_dir

    @staticmethod
    def get_blend_filename_prefix():
        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            return "00_texture"
        return os.path.splitext(os.path.basename(blend_filepath))[0]

    @staticmethod
    def create_gradient_image(context, vertical_only: bool):
        prefix = ZENV_WorldspaceGradientBake_Utils.get_blend_filename_prefix()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "vertical" if vertical_only else "xyz"
        image_name = f"{prefix}_wsgrad_{mode}_{timestamp}"

        res = context.scene.zenv_wsgrad_bake_resolution
        image = bpy.data.images.new(
            name=image_name,
            width=res,
            height=res,
            alpha=False,
            float_buffer=True,
        )

        texture_dir = ZENV_WorldspaceGradientBake_Utils.ensure_texture_directory()
        image_path = os.path.join(texture_dir, f"{image_name}.png")
        image.filepath_raw = image_path
        image.file_format = 'PNG'
        return image

    @staticmethod
    def store_scene_settings(scene):
        settings = {
            'render_engine': scene.render.engine,
            'view_transform': scene.view_settings.view_transform,
            'cycles_device': scene.cycles.device if hasattr(scene, 'cycles') else None,
            'cycles_samples': scene.cycles.samples if hasattr(scene, 'cycles') else None,
            'bake_margin': scene.render.bake.margin,
            'bake_use_clear': scene.render.bake.use_clear,
        }

        if hasattr(scene.render.bake, 'target'):
            settings['bake_target'] = scene.render.bake.target
        if hasattr(scene.render.bake, 'use_selected_to_active'):
            settings['bake_use_selected_to_active'] = scene.render.bake.use_selected_to_active

        return settings

    @staticmethod
    def restore_scene_settings(scene, settings):
        scene.render.engine = settings['render_engine']
        scene.view_settings.view_transform = settings['view_transform']

        if hasattr(scene, 'cycles'):
            if settings.get('cycles_device') is not None:
                scene.cycles.device = settings['cycles_device']
            if settings.get('cycles_samples') is not None:
                scene.cycles.samples = settings['cycles_samples']

        scene.render.bake.margin = settings['bake_margin']
        scene.render.bake.use_clear = settings['bake_use_clear']

        if hasattr(scene.render.bake, 'target') and 'bake_target' in settings:
            scene.render.bake.target = settings['bake_target']
        if hasattr(scene.render.bake, 'use_selected_to_active') and 'bake_use_selected_to_active' in settings:
            scene.render.bake.use_selected_to_active = settings['bake_use_selected_to_active']

    @staticmethod
    def get_object_world_bounds(obj):
        world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

        min_x = min(v.x for v in world_corners)
        max_x = max(v.x for v in world_corners)
        min_y = min(v.y for v in world_corners)
        max_y = max(v.y for v in world_corners)
        min_z = min(v.z for v in world_corners)
        max_z = max(v.z for v in world_corners)

        eps = 1e-8
        if abs(max_x - min_x) < eps:
            max_x = min_x + eps
        if abs(max_y - min_y) < eps:
            max_y = min_y + eps
        if abs(max_z - min_z) < eps:
            max_z = min_z + eps

        return (min_x, max_x, min_y, max_y, min_z, max_z)

    @staticmethod
    def create_temp_wsgrad_bake_material(
        image,
        bounds,
        vertical_only: bool,
    ):
        min_x, max_x, min_y, max_y, min_z, max_z = bounds

        mat = bpy.data.materials.new(name="__ZENV_TEMP_WSGRAD_BAKE_MAT__")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        tex_image.select = True
        nodes.active = tex_image

        geom = nodes.new('ShaderNodeNewGeometry')
        sep = nodes.new('ShaderNodeSeparateXYZ')

        emission = nodes.new('ShaderNodeEmission')
        output = nodes.new('ShaderNodeOutputMaterial')

        emission.inputs['Strength'].default_value = 1.0

        tex_image.location = (-900, 300)
        geom.location = (-900, 0)
        sep.location = (-500, 0)

        emission.location = (200, 0)
        output.location = (400, 0)

        links.new(geom.outputs['Position'], sep.inputs['Vector'])

        if vertical_only:
            map_z = nodes.new('ShaderNodeMapRange')
            map_z.clamp = True
            map_z.inputs['From Min'].default_value = min_z
            map_z.inputs['From Max'].default_value = max_z
            map_z.inputs['To Min'].default_value = 0.0
            map_z.inputs['To Max'].default_value = 1.0

            comb = nodes.new('ShaderNodeCombineRGB')

            map_z.location = (-300, -150)
            comb.location = (0, 0)

            links.new(sep.outputs['Z'], map_z.inputs['Value'])
            links.new(map_z.outputs['Result'], comb.inputs['R'])
            links.new(map_z.outputs['Result'], comb.inputs['G'])
            links.new(map_z.outputs['Result'], comb.inputs['B'])

            links.new(comb.outputs['Image'], emission.inputs['Color'])

        else:
            map_x = nodes.new('ShaderNodeMapRange')
            map_y = nodes.new('ShaderNodeMapRange')
            map_z = nodes.new('ShaderNodeMapRange')

            for node in (map_x, map_y, map_z):
                node.clamp = True
                node.inputs['To Min'].default_value = 0.0
                node.inputs['To Max'].default_value = 1.0

            map_x.inputs['From Min'].default_value = min_x
            map_x.inputs['From Max'].default_value = max_x
            map_y.inputs['From Min'].default_value = min_y
            map_y.inputs['From Max'].default_value = max_y
            map_z.inputs['From Min'].default_value = min_z
            map_z.inputs['From Max'].default_value = max_z

            comb = nodes.new('ShaderNodeCombineRGB')

            map_x.location = (-300, 100)
            map_y.location = (-300, 0)
            map_z.location = (-300, -100)
            comb.location = (0, 0)

            links.new(sep.outputs['X'], map_x.inputs['Value'])
            links.new(sep.outputs['Y'], map_y.inputs['Value'])
            links.new(sep.outputs['Z'], map_z.inputs['Value'])

            links.new(map_x.outputs['Result'], comb.inputs['R'])
            links.new(map_y.outputs['Result'], comb.inputs['G'])
            links.new(map_z.outputs['Result'], comb.inputs['B'])

            links.new(comb.outputs['Image'], emission.inputs['Color'])

        links.new(emission.outputs['Emission'], output.inputs['Surface'])

        return mat


class ZENV_OT_TEX_BakeWorldspaceBoundedGradientsMultiObject(bpy.types.Operator):
    bl_idname = "zenv.tex_bake_ws_bounded_gradients_multi_object"
    bl_label = "Bake Worldspace Gradients (Multi-Object)"
    bl_description = "Temporarily merges selected meshes and bakes bounded worldspace gradients"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        scene = context.scene

        original_active = context.view_layer.objects.active
        original_selected = [obj for obj in context.selected_objects]

        mesh_selected = [obj for obj in original_selected if obj.type == 'MESH']
        if not mesh_selected:
            self.report({'ERROR'}, "Select one or more mesh objects")
            return {'CANCELLED'}

        non_mesh = [obj for obj in original_selected if obj.type != 'MESH']
        if non_mesh:
            self.report({'ERROR'}, "Only mesh objects can be baked")
            return {'CANCELLED'}

        missing_uv = [obj for obj in mesh_selected if not obj.data.uv_layers]
        if missing_uv:
            self.report({'ERROR'}, f"Missing UVs on: {', '.join(o.name for o in missing_uv)}")
            return {'CANCELLED'}

        settings = ZENV_WorldspaceGradientBake_Utils.store_scene_settings(scene)

        vertical_only = scene.zenv_wsgrad_vertical_only

        temp_joined_obj = None
        temp_material = None
        bake_image = None

        try:
            bake_image = ZENV_WorldspaceGradientBake_Utils.create_gradient_image(context, vertical_only)

            scene.render.engine = 'CYCLES'
            if hasattr(scene, 'cycles'):
                scene.cycles.device = 'GPU' if scene.zenv_wsgrad_bake_use_gpu else 'CPU'
                scene.cycles.samples = scene.zenv_wsgrad_bake_samples
                scene.cycles.use_denoising = False

            scene.view_settings.view_transform = 'Standard'

            scene.render.bake.margin = scene.zenv_wsgrad_bake_margin
            scene.render.bake.use_clear = True
            if hasattr(scene.render.bake, 'use_selected_to_active'):
                scene.render.bake.use_selected_to_active = False
            if hasattr(scene.render.bake, 'target'):
                scene.render.bake.target = 'IMAGE_TEXTURES'

            bpy.ops.object.select_all(action='DESELECT')
            for obj in mesh_selected:
                obj.select_set(True)
            context.view_layer.objects.active = mesh_selected[0]

            bpy.ops.object.duplicate(linked=False)
            bpy.ops.object.join()
            temp_joined_obj = context.view_layer.objects.active
            temp_joined_obj.name = "__ZENV_TEMP_WSGRAD_JOINED__"

            bpy.ops.object.select_all(action='DESELECT')
            temp_joined_obj.select_set(True)
            context.view_layer.objects.active = temp_joined_obj
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

            bounds = ZENV_WorldspaceGradientBake_Utils.get_object_world_bounds(temp_joined_obj)
            temp_material = ZENV_WorldspaceGradientBake_Utils.create_temp_wsgrad_bake_material(
                image=bake_image,
                bounds=bounds,
                vertical_only=vertical_only,
            )

            temp_joined_obj.data.materials.clear()
            temp_joined_obj.data.materials.append(temp_material)

            bpy.ops.object.select_all(action='DESELECT')
            temp_joined_obj.select_set(True)
            context.view_layer.objects.active = temp_joined_obj

            margin = scene.zenv_wsgrad_bake_margin
            bpy.ops.object.bake(
                type='EMIT',
                margin=margin,
                use_clear=True,
            )

            if bake_image.has_data:
                bake_image.save_render(bake_image.filepath_raw)

            self.report({'INFO'}, f"Worldspace gradient baked: {bake_image.filepath_raw}")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Worldspace gradient bake failed")
            self.report({'ERROR'}, f"Worldspace gradient bake failed: {str(e)}")
            return {'CANCELLED'}

        finally:
            try:
                if temp_joined_obj:
                    bpy.data.objects.remove(temp_joined_obj, do_unlink=True)
            except Exception:
                pass

            try:
                if temp_material:
                    bpy.data.materials.remove(temp_material, do_unlink=True)
            except Exception:
                pass

            try:
                ZENV_WorldspaceGradientBake_Utils.restore_scene_settings(scene, settings)
            except Exception:
                pass

            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active


class ZENV_PT_TEX_BakeWorldspaceBoundedGradientsMultiObject(bpy.types.Panel):
    bl_label = "TEX Bake World Gradients"
    bl_idname = "ZENV_PT_tex_bake_world_gradients_multi"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("zenv.tex_bake_ws_bounded_gradients_multi_object", icon='RENDER_STILL')

        box = layout.box()
        box.label(text="Bake:")
        box.prop(scene, "zenv_wsgrad_bake_resolution")
        box.prop(scene, "zenv_wsgrad_bake_samples")
        box.prop(scene, "zenv_wsgrad_bake_margin")
        box.prop(scene, "zenv_wsgrad_bake_use_gpu")

        box = layout.box()
        box.label(text="Mode:")
        box.prop(scene, "zenv_wsgrad_vertical_only")

        selected = [obj for obj in context.selected_objects]
        mesh_selected = [obj for obj in selected if obj.type == 'MESH']

        if not selected:
            layout.label(text="No Selected Mesh", icon='INFO')
        elif not mesh_selected:
            layout.label(text="Select Mesh Objects", icon='INFO')
        else:
            missing_uv = [obj for obj in mesh_selected if not obj.data.uv_layers]
            if missing_uv:
                layout.label(text="Selected Mesh Missing UVs", icon='INFO')


classes = (
    ZENV_OT_TEX_BakeWorldspaceBoundedGradientsMultiObject,
    ZENV_PT_TEX_BakeWorldspaceBoundedGradientsMultiObject,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_worldspace_gradient_bake_console_handler
    if _zenv_worldspace_gradient_bake_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_worldspace_gradient_bake_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_worldspace_gradient_bake_console_handler
    if _zenv_worldspace_gradient_bake_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_worldspace_gradient_bake_console_handler)
    except ValueError:
        pass
    _zenv_worldspace_gradient_bake_console_handler = None


def register():
    _install_logger()
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_WorldspaceGradientBake_Properties.register()


def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_WorldspaceGradientBake_Properties.unregister()
    _uninstall_logger()


if __name__ == "__main__":
    register()
