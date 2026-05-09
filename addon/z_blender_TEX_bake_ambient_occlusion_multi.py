bl_info = {
    "name": 'TEX Bake Ambient Occlusion',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260309',
    "description": 'Texture Bake ambient occlusion of all selected mesh objects as one',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Texture',
    "group_prefix": 'TEX',
    "description_short": 'bake AO to texture , selected temp merge',
    "description_medium": 'Texture Bake ambient occlusion of all selected mesh objects as one',
    "description_long": """
TEX MULTI-OBJECT AMBIENT OCCLUSION BAKER
- Select multiple mesh objects that share a UV layout / texture space
- Addon duplicates them, joins into a temp object, bakes AO to a new image, saves to //textures/
- Restores scene settings and keeps original objects intact
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
_zenv_ao_bake_console_handler = None


class ZENV_AO_Bake_Properties:
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_ao_bake_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="AO bake texture resolution",
            default=1024,
            min=64,
            max=8192,
        )
        bpy.types.Scene.zenv_ao_bake_samples = bpy.props.IntProperty(
            name="Samples",
            description="Cycles samples for AO baking",
            default=64,
            min=1,
            max=4096,
        )
        bpy.types.Scene.zenv_ao_bake_margin = bpy.props.IntProperty(
            name="Margin",
            description="Bake padding in pixels (0 = no padding)",
            default=4,
            min=0,
            max=256,
        )
        bpy.types.Scene.zenv_ao_bake_use_gpu = bpy.props.BoolProperty(
            name="Use GPU",
            description="Use GPU for Cycles baking when available",
            default=True,
        )

        bpy.types.Scene.zenv_ao_bake_method = bpy.props.EnumProperty(
            name="Bake Method",
            description="AO (Cycles AO bake) or EMIT (shader AO baked via EMIT)",
            items=(
                ('EMIT', "EMIT", "Shader Ambient Occlusion node baked via EMIT"),
                ('AO', "AO", "Cycles AO bake"),
            ),
            default='EMIT',
        )

        bpy.types.Scene.zenv_ao_bake_ao_distance = bpy.props.FloatProperty(
            name="AO Distance",
            description="Ambient Occlusion distance (used for EMIT method)",
            default=0.25,
            min=0.0,
            max=100.0,
        )

        bpy.types.Scene.zenv_ao_bake_double_sided = bpy.props.BoolProperty(
            name="Double-Sided (EMIT)",
            description="Compute AO using both normal and inverted normal to reduce directional bias",
            default=False,
        )

        bpy.types.Scene.zenv_ao_bake_strength = bpy.props.FloatProperty(
            name="AO Strength",
            description="Strength of occlusion darkening (1 = neutral)",
            default=1.0,
            min=0.0,
            max=10.0,
        )

        bpy.types.Scene.zenv_ao_bake_contrast = bpy.props.FloatProperty(
            name="AO Contrast",
            description="Contrast curve for AO (1 = neutral, >1 = stronger crevice separation)",
            default=1.0,
            min=0.01,
            max=10.0,
        )

        bpy.types.Scene.zenv_ao_bake_uv_map = bpy.props.StringProperty(
            name="UV Map",
            description="UV map name to bake with (blank = active UV)",
            default="",
        )

        bpy.types.Scene.zenv_ao_bake_recalc_normals = bpy.props.BoolProperty(
            name="Recalc Normals (Temp)",
            description="Recalculate normals on the temporary joined mesh before baking",
            default=True,
        )

        bpy.types.Scene.zenv_ao_bake_apply_scale = bpy.props.BoolProperty(
            name="Apply Scale (Temp)",
            description="Apply scale on the temporary joined mesh before baking",
            default=False,
        )

        bpy.types.Scene.zenv_ao_bake_hide_originals = bpy.props.BoolProperty(
            name="Hide Originals (Temp)",
            description="Temporarily hide the original selected meshes during bake to avoid double-geometry occlusion",
            default=True,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_ao_bake_resolution
        del bpy.types.Scene.zenv_ao_bake_samples
        del bpy.types.Scene.zenv_ao_bake_margin
        del bpy.types.Scene.zenv_ao_bake_use_gpu
        del bpy.types.Scene.zenv_ao_bake_method
        del bpy.types.Scene.zenv_ao_bake_ao_distance
        del bpy.types.Scene.zenv_ao_bake_double_sided
        del bpy.types.Scene.zenv_ao_bake_strength
        del bpy.types.Scene.zenv_ao_bake_contrast
        del bpy.types.Scene.zenv_ao_bake_uv_map
        del bpy.types.Scene.zenv_ao_bake_recalc_normals
        del bpy.types.Scene.zenv_ao_bake_apply_scale
        del bpy.types.Scene.zenv_ao_bake_hide_originals


class ZENV_AO_Bake_Utils:
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
    def create_ao_image(context):
        prefix = ZENV_AO_Bake_Utils.get_blend_filename_prefix()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"{prefix}_ao_{timestamp}"

        res = context.scene.zenv_ao_bake_resolution
        image = bpy.data.images.new(
            name=image_name,
            width=res,
            height=res,
            alpha=False,
            float_buffer=True,
        )

        texture_dir = ZENV_AO_Bake_Utils.ensure_texture_directory()
        image_path = os.path.join(texture_dir, f"{image_name}.png")
        image.filepath_raw = image_path
        image.file_format = 'PNG'
        return image

    @staticmethod
    def create_temp_bake_material(
        image,
        method: str,
        ao_distance: float,
        double_sided: bool,
        ao_strength: float,
        ao_contrast: float,
    ):
        mat = bpy.data.materials.new(name="__ZENV_TEMP_AO_BAKE_MAT__")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        tex = nodes.new('ShaderNodeTexImage')
        tex.image = image
        tex.select = True
        nodes.active = tex

        out = nodes.new('ShaderNodeOutputMaterial')
        out.location = (600, 0)

        if method == 'EMIT':
            geom = nodes.new('ShaderNodeNewGeometry')
            normal_inv = nodes.new('ShaderNodeVectorMath')
            normal_inv.operation = 'MULTIPLY'
            normal_inv.inputs[1].default_value = (-1.0, -1.0, -1.0)

            ao_a = nodes.new('ShaderNodeAmbientOcclusion')
            ao_a.inputs['Distance'].default_value = ao_distance

            ao_b = nodes.new('ShaderNodeAmbientOcclusion')
            ao_b.inputs['Distance'].default_value = ao_distance

            ao_darken = nodes.new('ShaderNodeMixRGB')
            ao_darken.blend_type = 'LIGHTEN'
            ao_darken.use_clamp = True
            ao_darken.inputs['Fac'].default_value = 1.0

            invert1 = nodes.new('ShaderNodeInvert')
            occl_mul = nodes.new('ShaderNodeMath')
            occl_mul.operation = 'MULTIPLY'
            occl_mul.use_clamp = True
            occl_mul.inputs[1].default_value = ao_strength

            invert2 = nodes.new('ShaderNodeInvert')
            contrast_pow = nodes.new('ShaderNodeMath')
            contrast_pow.operation = 'POWER'
            contrast_pow.use_clamp = True
            contrast_pow.inputs[1].default_value = ao_contrast

            combine = nodes.new('ShaderNodeCombineRGB')

            emission = nodes.new('ShaderNodeEmission')
            emission.inputs['Strength'].default_value = 1.0

            tex.location = (-600, 200)
            geom.location = (-900, 0)
            normal_inv.location = (-700, 0)
            ao_a.location = (-500, 120)
            ao_b.location = (-500, -120)
            ao_darken.location = (-250, 0)
            invert1.location = (-50, 0)
            occl_mul.location = (100, 0)
            invert2.location = (250, 0)
            contrast_pow.location = (400, 0)
            combine.location = (520, 0)
            emission.location = (300, 0)

            links.new(geom.outputs['Normal'], ao_a.inputs['Normal'])
            links.new(geom.outputs['Normal'], normal_inv.inputs[0])
            links.new(normal_inv.outputs[0], ao_b.inputs['Normal'])

            if double_sided:
                links.new(ao_a.outputs['Color'], ao_darken.inputs['Color1'])
                links.new(ao_b.outputs['Color'], ao_darken.inputs['Color2'])
            else:
                links.new(ao_a.outputs['Color'], ao_darken.inputs['Color1'])
                links.new(ao_a.outputs['Color'], ao_darken.inputs['Color2'])

            links.new(ao_darken.outputs['Color'], invert1.inputs['Color'])
            links.new(invert1.outputs['Color'], occl_mul.inputs[0])
            links.new(occl_mul.outputs[0], invert2.inputs['Color'])

            links.new(invert2.outputs['Color'], contrast_pow.inputs[0])

            links.new(contrast_pow.outputs[0], combine.inputs['R'])
            links.new(contrast_pow.outputs[0], combine.inputs['G'])
            links.new(contrast_pow.outputs[0], combine.inputs['B'])

            links.new(combine.outputs['Image'], emission.inputs['Color'])
            links.new(emission.outputs['Emission'], out.inputs['Surface'])
        else:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            tex.location = (-300, 200)
            bsdf.location = (300, 0)
            links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

        return mat

    @staticmethod
    def ensure_uv_layer_on_object(obj, uv_map_name: str):
        if obj.type != 'MESH':
            return

        if not obj.data.uv_layers:
            return

        if not uv_map_name:
            layer = obj.data.uv_layers.active
            if layer:
                layer.active_render = True
            return

        uv_layers = obj.data.uv_layers
        target = uv_layers.get(uv_map_name)
        if target is None:
            src = uv_layers.active
            target = uv_layers.new(name=uv_map_name)
            if src:
                for i in range(len(obj.data.loops)):
                    target.data[i].uv = src.data[i].uv

        uv_layers.active = target
        target.active_render = True

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


class ZENV_OT_TEX_BakeAmbientOcclusionMultiObject(bpy.types.Operator):
    bl_idname = "zenv.tex_bake_ao_multi_object"
    bl_label = "Bake AO (Multi-Object)"
    bl_description = "Temporarily merges selected meshes and bakes Ambient Occlusion to a new texture"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        scene = context.scene

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

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

        settings = ZENV_AO_Bake_Utils.store_scene_settings(scene)

        method = scene.zenv_ao_bake_method
        ao_distance = scene.zenv_ao_bake_ao_distance
        double_sided = scene.zenv_ao_bake_double_sided
        ao_strength = scene.zenv_ao_bake_strength
        ao_contrast = scene.zenv_ao_bake_contrast
        uv_map_name = scene.zenv_ao_bake_uv_map.strip()

        original_visibility = {}

        temp_joined_obj = None
        temp_material = None
        bake_image = None

        try:
            bake_image = ZENV_AO_Bake_Utils.create_ao_image(context)
            temp_material = ZENV_AO_Bake_Utils.create_temp_bake_material(
                bake_image,
                method,
                ao_distance,
                double_sided,
                ao_strength,
                ao_contrast,
            )

            scene.render.engine = 'CYCLES'
            if hasattr(scene, 'cycles'):
                scene.cycles.device = 'GPU' if scene.zenv_ao_bake_use_gpu else 'CPU'
                scene.cycles.samples = scene.zenv_ao_bake_samples
                scene.cycles.use_denoising = False

            scene.view_settings.view_transform = 'Standard'

            scene.render.bake.margin = scene.zenv_ao_bake_margin
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
            temp_duplicates = [obj for obj in context.selected_objects if obj.type == 'MESH']

            if scene.zenv_ao_bake_hide_originals:
                for obj in mesh_selected:
                    original_visibility[obj.name] = {
                        'hide_viewport': getattr(obj, 'hide_viewport', False),
                        'hide_render': getattr(obj, 'hide_render', False),
                        'hide_get': obj.hide_get() if hasattr(obj, 'hide_get') else False,
                    }

                    if hasattr(obj, 'hide_set'):
                        obj.hide_set(True)
                    if hasattr(obj, 'hide_viewport'):
                        obj.hide_viewport = True
                    if hasattr(obj, 'hide_render'):
                        obj.hide_render = True

            for obj in temp_duplicates:
                ZENV_AO_Bake_Utils.ensure_uv_layer_on_object(obj, uv_map_name)

            bpy.ops.object.join()
            temp_joined_obj = context.view_layer.objects.active
            temp_joined_obj.name = "__ZENV_TEMP_AO_JOINED__"

            ZENV_AO_Bake_Utils.ensure_uv_layer_on_object(temp_joined_obj, uv_map_name)

            temp_joined_obj.data.materials.clear()
            temp_joined_obj.data.materials.append(temp_material)

            bpy.ops.object.select_all(action='DESELECT')
            temp_joined_obj.select_set(True)
            context.view_layer.objects.active = temp_joined_obj

            if scene.zenv_ao_bake_apply_scale:
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            if scene.zenv_ao_bake_recalc_normals:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.normals_make_consistent(inside=False)
                bpy.ops.object.mode_set(mode='OBJECT')

            margin = scene.zenv_ao_bake_margin
            bpy.ops.object.bake(
                type='EMIT' if method == 'EMIT' else 'AO',
                margin=margin,
                use_clear=True,
            )

            if bake_image.has_data:
                bake_image.save_render(bake_image.filepath_raw)

            self.report({'INFO'}, f"AO baked: {bake_image.filepath_raw}")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("AO bake failed")
            self.report({'ERROR'}, f"AO bake failed: {str(e)}")
            return {'CANCELLED'}

        finally:
            try:
                if temp_joined_obj:
                    bpy.data.objects.remove(temp_joined_obj, do_unlink=True)
            except Exception:
                pass

            try:
                for obj_name, state in original_visibility.items():
                    obj = bpy.data.objects.get(obj_name)
                    if not obj:
                        continue

                    if hasattr(obj, 'hide_set'):
                        obj.hide_set(state.get('hide_get', False))
                    if hasattr(obj, 'hide_viewport'):
                        obj.hide_viewport = state.get('hide_viewport', False)
                    if hasattr(obj, 'hide_render'):
                        obj.hide_render = state.get('hide_render', False)
            except Exception:
                pass

            try:
                if temp_material:
                    bpy.data.materials.remove(temp_material, do_unlink=True)
            except Exception:
                pass

            try:
                ZENV_AO_Bake_Utils.restore_scene_settings(scene, settings)
            except Exception:
                pass

            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active


class ZENV_PT_TEX_BakeAmbientOcclusionMultiObject(bpy.types.Panel):
    bl_label = "TEX Bake AO Multi"
    bl_idname = "ZENV_PT_tex_bake_ao_multi"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("zenv.tex_bake_ao_multi_object", icon='RENDER_STILL')

        box = layout.box()
        box.label(text="Settings:")
        box.prop(scene, "zenv_ao_bake_resolution")
        box.prop(scene, "zenv_ao_bake_samples")
        box.prop(scene, "zenv_ao_bake_margin")
        box.prop(scene, "zenv_ao_bake_use_gpu")

        box = layout.box()
        box.label(text="AO:")
        box.prop(scene, "zenv_ao_bake_method")
        if scene.zenv_ao_bake_method == 'EMIT':
            box.prop(scene, "zenv_ao_bake_ao_distance")
            box.prop(scene, "zenv_ao_bake_double_sided")
            box.prop(scene, "zenv_ao_bake_strength")
            box.prop(scene, "zenv_ao_bake_contrast")
        box.prop(scene, "zenv_ao_bake_uv_map")
        box.prop(scene, "zenv_ao_bake_recalc_normals")
        box.prop(scene, "zenv_ao_bake_apply_scale")
        box.prop(scene, "zenv_ao_bake_hide_originals")

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
    ZENV_OT_TEX_BakeAmbientOcclusionMultiObject,
    ZENV_PT_TEX_BakeAmbientOcclusionMultiObject,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_ao_bake_console_handler
    if _zenv_ao_bake_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_ao_bake_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_ao_bake_console_handler
    if _zenv_ao_bake_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_ao_bake_console_handler)
    except ValueError:
        pass
    _zenv_ao_bake_console_handler = None


def register():
    _install_logger()
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_AO_Bake_Properties.register()


def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_AO_Bake_Properties.unregister()
    _uninstall_logger()


if __name__ == "__main__":
    register()
