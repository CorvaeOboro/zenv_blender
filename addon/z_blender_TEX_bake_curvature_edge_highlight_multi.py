bl_info = {
    "name": 'TEX Bake Curvature Edge Highlight',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260309',
    "description": 'Bake curvature edge highlight overlay for multiple selected mesh objects by temporarily merging them',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Texture',
    "group_prefix": 'TEX',
    "description_short": 'bake Curvature to texture , selected temp merge',
    "description_medium": 'curvature overlay bake for 0.5-gray base / white edges / dark crevices',
    "description_long": """
TEX MULTI-OBJECT CURVATURE EDGE HIGHLIGHT BAKER
- Select multiple mesh objects that share a UV layout / texture space
- Addon duplicates them, joins into a temp object, bakes a curvature overlay to a new image, saves to //textures/
- Overlay format is tuned for compositing:
  - 0.5 gray base
  - white convex edge highlight with falloff
  - dark gray concave/crevice shading
- Restores scene settings and keeps original objects intact
Implementation uses a Cycles shader and bakes EMIT for a lighting-independent result:
- convex response: Geometry Pointiness
- concave response: Ambient Occlusion (inverted)
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from datetime import datetime
import logging
from math import radians
from math import ceil
from array import array
import bmesh

logger = logging.getLogger(__name__)
_zenv_curvature_bake_console_handler = None


class ZENV_CurvatureBake_Properties:
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_curv_bake_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Curvature bake texture resolution",
            default=1024,
            min=64,
            max=8192,
        )
        bpy.types.Scene.zenv_curv_bake_samples = bpy.props.IntProperty(
            name="Samples",
            description="Cycles samples for curvature baking",
            default=64,
            min=1,
            max=4096,
        )
        bpy.types.Scene.zenv_curv_bake_margin = bpy.props.IntProperty(
            name="Margin",
            description="Bake padding in pixels (0 = no padding)",
            default=4,
            min=0,
            max=256,
        )
        bpy.types.Scene.zenv_curv_bake_use_gpu = bpy.props.BoolProperty(
            name="Use GPU",
            description="Use GPU for Cycles baking when available",
            default=True,
        )

        bpy.types.Scene.zenv_curv_edge_strength = bpy.props.FloatProperty(
            name="Edge Strength",
            description="Strength of convex/edge highlights",
            default=1.0,
            min=0.0,
            max=5.0,
        )
        bpy.types.Scene.zenv_curv_crevice_strength = bpy.props.FloatProperty(
            name="Crevice Strength",
            description="Strength of concave/crevice darkening",
            default=1.0,
            min=0.0,
            max=5.0,
        )

        bpy.types.Scene.zenv_curv_edge_low = bpy.props.FloatProperty(
            name="Edge Low",
            description="Lower threshold for edge highlight ramp",
            default=0.35,
            min=0.0,
            max=1.0,
        )
        bpy.types.Scene.zenv_curv_edge_high = bpy.props.FloatProperty(
            name="Edge High",
            description="Upper threshold for edge highlight ramp",
            default=0.65,
            min=0.0,
            max=1.0,
        )

        bpy.types.Scene.zenv_curv_crevice_low = bpy.props.FloatProperty(
            name="Crevice Low",
            description="Lower threshold for crevice ramp (after AO invert)",
            default=0.25,
            min=0.0,
            max=1.0,
        )
        bpy.types.Scene.zenv_curv_crevice_high = bpy.props.FloatProperty(
            name="Crevice High",
            description="Upper threshold for crevice ramp (after AO invert)",
            default=0.8,
            min=0.0,
            max=1.0,
        )

        bpy.types.Scene.zenv_curv_ao_distance = bpy.props.FloatProperty(
            name="AO Distance",
            description="Distance for Ambient Occlusion node (controls crevice size)",
            default=0.25,
            min=0.0,
            max=100.0,
        )

        bpy.types.Scene.zenv_curv_wireframe_enable = bpy.props.BoolProperty(
            name="Wireframe Edges",
            description="Overlay 1px wireframe edges (baked into UV space)",
            default=True,
        )
        bpy.types.Scene.zenv_curv_wireframe_px = bpy.props.FloatProperty(
            name="Wire Px",
            description="Wireframe thickness in pixels",
            default=1.0,
            min=0.1,
            max=10.0,
        )
        bpy.types.Scene.zenv_curv_wireframe_strength = bpy.props.FloatProperty(
            name="Wire Strength",
            description="Strength of wireframe edge overlay",
            default=1.0,
            min=0.0,
            max=5.0,
        )

        bpy.types.Scene.zenv_curv_wireframe_sharp_only = bpy.props.BoolProperty(
            name="Sharp Edges Only",
            description="Only draw edges with a face angle above the threshold (plus boundaries)",
            default=True,
        )

        bpy.types.Scene.zenv_curv_wireframe_sharp_angle = bpy.props.FloatProperty(
            name="Sharp Angle",
            description="Edge angle threshold in degrees for Sharp Edges Only",
            default=30.0,
            min=0.0,
            max=180.0,
            subtype='ANGLE',
        )

        bpy.types.Scene.zenv_curv_wireframe_falloff_px = bpy.props.IntProperty(
            name="Wire Falloff Px",
            description="UV-space blur/falloff radius for wire overlay (0 = no falloff)",
            default=2,
            min=0,
            max=64,
        )

        bpy.types.Scene.zenv_curv_temp_subdiv_levels = bpy.props.IntProperty(
            name="Temp Subdiv",
            description="Subdivision levels applied only to the temporary joined mesh (adds density for curvature)",
            default=1,
            min=0,
            max=4,
        )
        bpy.types.Scene.zenv_curv_temp_bevel_width = bpy.props.FloatProperty(
            name="Temp Bevel",
            description="World-space bevel width applied only to the temporary joined mesh",
            default=0.005,
            min=0.0,
            max=10.0,
            subtype='DISTANCE',
        )
        bpy.types.Scene.zenv_curv_temp_bevel_segments = bpy.props.IntProperty(
            name="Bevel Segments",
            description="Bevel segments on the temporary joined mesh",
            default=2,
            min=1,
            max=16,
        )
        bpy.types.Scene.zenv_curv_temp_bevel_angle = bpy.props.FloatProperty(
            name="Bevel Angle",
            description="Bevel angle limit in degrees (only for the temporary joined mesh)",
            default=30.0,
            min=0.0,
            max=180.0,
            subtype='ANGLE',
        )
        bpy.types.Scene.zenv_curv_temp_apply_scale = bpy.props.BoolProperty(
            name="Apply Scale (Temp)",
            description="Apply scale on the temporary joined mesh before baking",
            default=True,
        )
        bpy.types.Scene.zenv_curv_temp_recalc_normals = bpy.props.BoolProperty(
            name="Recalc Normals (Temp)",
            description="Recalculate normals on the temporary joined mesh before baking",
            default=True,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_curv_bake_resolution
        del bpy.types.Scene.zenv_curv_bake_samples
        del bpy.types.Scene.zenv_curv_bake_margin
        del bpy.types.Scene.zenv_curv_bake_use_gpu
        del bpy.types.Scene.zenv_curv_edge_strength
        del bpy.types.Scene.zenv_curv_crevice_strength
        del bpy.types.Scene.zenv_curv_edge_low
        del bpy.types.Scene.zenv_curv_edge_high
        del bpy.types.Scene.zenv_curv_crevice_low
        del bpy.types.Scene.zenv_curv_crevice_high
        del bpy.types.Scene.zenv_curv_ao_distance
        del bpy.types.Scene.zenv_curv_wireframe_enable
        del bpy.types.Scene.zenv_curv_wireframe_px
        del bpy.types.Scene.zenv_curv_wireframe_strength
        del bpy.types.Scene.zenv_curv_wireframe_sharp_only
        del bpy.types.Scene.zenv_curv_wireframe_sharp_angle
        del bpy.types.Scene.zenv_curv_wireframe_falloff_px
        del bpy.types.Scene.zenv_curv_temp_subdiv_levels
        del bpy.types.Scene.zenv_curv_temp_bevel_width
        del bpy.types.Scene.zenv_curv_temp_bevel_segments
        del bpy.types.Scene.zenv_curv_temp_bevel_angle
        del bpy.types.Scene.zenv_curv_temp_apply_scale
        del bpy.types.Scene.zenv_curv_temp_recalc_normals


class ZENV_CurvatureBake_Utils:
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
    def _clamp_int(v: int, lo: int, hi: int) -> int:
        return lo if v < lo else hi if v > hi else v

    @staticmethod
    def _draw_uv_line_into_mask(mask, width: int, height: int, uv0, uv1, radius_px: float):
        x0 = uv0.x * (width - 1)
        y0 = uv0.y * (height - 1)
        x1 = uv1.x * (width - 1)
        y1 = uv1.y * (height - 1)

        dx = x1 - x0
        dy = y1 - y0
        steps = int(max(abs(dx), abs(dy)) * 2.0) + 1

        r = max(0.5, float(radius_px))
        r_int = int(ceil(r))

        for s in range(steps + 1):
            t = s / steps if steps > 0 else 0.0
            x = x0 + dx * t
            y = y0 + dy * t
            cx = int(round(x))
            cy = int(round(y))

            xmin = ZENV_CurvatureBake_Utils._clamp_int(cx - r_int, 0, width - 1)
            xmax = ZENV_CurvatureBake_Utils._clamp_int(cx + r_int, 0, width - 1)
            ymin = ZENV_CurvatureBake_Utils._clamp_int(cy - r_int, 0, height - 1)
            ymax = ZENV_CurvatureBake_Utils._clamp_int(cy + r_int, 0, height - 1)

            for yy in range(ymin, ymax + 1):
                for xx in range(xmin, xmax + 1):
                    ddx = xx - x
                    ddy = yy - y
                    if (ddx * ddx + ddy * ddy) <= (r * r):
                        idx = yy * width + xx
                        if mask[idx] != 255:
                            mask[idx] = 255

    @staticmethod
    def build_uv_edge_mask(obj, width: int, height: int, wire_px: float, sharp_only: bool, sharp_angle_deg: float):
        if obj.type != 'MESH':
            return None

        mesh = obj.data
        if not mesh.uv_layers or mesh.uv_layers.active is None:
            return None

        mask = bytearray(width * height)
        radius_px = max(0.1, float(wire_px)) * 0.5

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None:
                return None

            angle_threshold = radians(float(sharp_angle_deg))

            for e in bm.edges:
                include = True
                if sharp_only:
                    if len(e.link_faces) < 2:
                        include = True
                    else:
                        try:
                            include = e.calc_face_angle() >= angle_threshold
                        except Exception:
                            include = True

                if not include:
                    continue

                for f in e.link_faces:
                    for loop in f.loops:
                        if loop.edge != e:
                            continue
                        uv0 = loop[uv_layer].uv
                        uv1 = loop.link_loop_next[uv_layer].uv
                        ZENV_CurvatureBake_Utils._draw_uv_line_into_mask(mask, width, height, uv0, uv1, radius_px)
                        break

        finally:
            bm.free()

        return mask

    @staticmethod
    def blur_mask_bytearray(mask, width: int, height: int, radius_px: int):
        if radius_px <= 0:
            return None

        r = int(radius_px)
        w = width
        h = height

        win_w = [0] * w
        for x in range(w):
            left = x - r
            if left < 0:
                left = 0
            right = x + r
            if right > (w - 1):
                right = (w - 1)
            win_w[x] = (right - left + 1)

        win_h = [0] * h
        for y in range(h):
            top = y - r
            if top < 0:
                top = 0
            bot = y + r
            if bot > (h - 1):
                bot = (h - 1)
            win_h[y] = (bot - top + 1)

        tmp = array('I', [0]) * (w * h)

        for y in range(h):
            row_off = y * w
            prefix = array('I', [0]) * (w + 1)
            run = 0
            for x in range(w):
                run += mask[row_off + x]
                prefix[x + 1] = run

            for x in range(w):
                left = x - r
                if left < 0:
                    left = 0
                right = x + r
                if right > (w - 1):
                    right = (w - 1)
                tmp[row_off + x] = prefix[right + 1] - prefix[left]

        blurred = bytearray(w * h)
        for x in range(w):
            prefix = array('I', [0]) * (h + 1)
            run = 0
            for y in range(h):
                run += tmp[y * w + x]
                prefix[y + 1] = run

            for y in range(h):
                top = y - r
                if top < 0:
                    top = 0
                bot = y + r
                if bot > (h - 1):
                    bot = (h - 1)
                s = prefix[bot + 1] - prefix[top]
                denom = win_w[x] * win_h[y]
                val = int(round(s / denom))
                if val < 0:
                    val = 0
                elif val > 255:
                    val = 255
                blurred[y * w + x] = val

        return blurred

    @staticmethod
    def composite_wire_mask_into_image(image, mask, wire_strength: float):
        if not image or mask is None:
            return

        width, height = image.size
        if len(mask) != (width * height):
            return

        pixels = [0.0] * (width * height * 4)
        image.pixels.foreach_get(pixels)

        strength = max(0.0, float(wire_strength))
        for i in range(width * height):
            m = mask[i]
            if m <= 0:
                continue
            fac = (float(m) / 255.0) * strength
            if fac <= 0.0:
                continue
            base = i * 4
            pixels[base + 0] = min(1.0, pixels[base + 0] + fac)
            pixels[base + 1] = min(1.0, pixels[base + 1] + fac)
            pixels[base + 2] = min(1.0, pixels[base + 2] + fac)
            pixels[base + 3] = 1.0

        image.pixels.foreach_set(pixels)
        image.update()

    @staticmethod
    def create_curvature_image(context):
        prefix = ZENV_CurvatureBake_Utils.get_blend_filename_prefix()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"{prefix}_curvature_{timestamp}"

        res = context.scene.zenv_curv_bake_resolution
        image = bpy.data.images.new(
            name=image_name,
            width=res,
            height=res,
            alpha=False,
            float_buffer=True,
        )

        texture_dir = ZENV_CurvatureBake_Utils.ensure_texture_directory()
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
    def create_temp_curvature_bake_material(context, image):
        scene = context.scene

        mat = bpy.data.materials.new(name="__ZENV_TEMP_CURVATURE_BAKE_MAT__")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # Bake target image node (must be active for bake)
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = image
        tex_image.select = True
        nodes.active = tex_image

        geom = nodes.new('ShaderNodeNewGeometry')
        ramp_edge = nodes.new('ShaderNodeValToRGB')
        rgb_to_bw = nodes.new('ShaderNodeRGBToBW')
        math_edge_strength = nodes.new('ShaderNodeMath')
        combine = nodes.new('ShaderNodeCombineRGB')

        emission = nodes.new('ShaderNodeEmission')
        output = nodes.new('ShaderNodeOutputMaterial')

        # Defaults

        # Edge ramp tuning
        if len(ramp_edge.color_ramp.elements) >= 2:
            ramp_edge.color_ramp.elements[0].position = min(scene.zenv_curv_edge_low, scene.zenv_curv_edge_high)
            ramp_edge.color_ramp.elements[1].position = max(scene.zenv_curv_edge_low, scene.zenv_curv_edge_high)
            ramp_edge.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
            ramp_edge.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

        # Strength scales
        math_edge_strength.operation = 'MULTIPLY'
        math_edge_strength.use_clamp = True
        math_edge_strength.inputs[1].default_value = scene.zenv_curv_edge_strength

        emission.inputs['Strength'].default_value = 1.0

        # Layout
        tex_image.location = (-800, 300)

        geom.location = (-800, 0)
        ramp_edge.location = (-600, 0)
        rgb_to_bw.location = (-400, 0)
        math_edge_strength.location = (-200, 0)
        combine.location = (0, 0)

        emission.location = (300, 0)
        output.location = (500, 0)

        # Links
        links.new(geom.outputs['Pointiness'], ramp_edge.inputs['Fac'])
        links.new(ramp_edge.outputs['Color'], rgb_to_bw.inputs['Color'])
        links.new(rgb_to_bw.outputs['Val'], math_edge_strength.inputs[0])

        links.new(math_edge_strength.outputs[0], combine.inputs['R'])
        links.new(math_edge_strength.outputs[0], combine.inputs['G'])
        links.new(math_edge_strength.outputs[0], combine.inputs['B'])

        links.new(combine.outputs['Image'], emission.inputs['Color'])
        links.new(emission.outputs['Emission'], output.inputs['Surface'])

        return mat


class ZENV_OT_TEX_BakeCurvatureEdgeHighlightMultiObject(bpy.types.Operator):
    bl_idname = "zenv.tex_bake_curvature_edge_multi_object"
    bl_label = "Bake Curvature Overlay (Multi-Object)"
    bl_description = "Temporarily merges selected meshes and bakes a curvature overlay (0.5 base, white edges, dark crevices)"
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

        settings = ZENV_CurvatureBake_Utils.store_scene_settings(scene)

        temp_joined_obj = None
        temp_material = None
        bake_image = None
        wire_mask = None

        try:
            bake_image = ZENV_CurvatureBake_Utils.create_curvature_image(context)
            temp_material = ZENV_CurvatureBake_Utils.create_temp_curvature_bake_material(context, bake_image)

            scene.render.engine = 'CYCLES'
            if hasattr(scene, 'cycles'):
                scene.cycles.device = 'GPU' if scene.zenv_curv_bake_use_gpu else 'CPU'
                scene.cycles.samples = scene.zenv_curv_bake_samples
                scene.cycles.use_denoising = False

            scene.view_settings.view_transform = 'Standard'

            scene.render.bake.margin = scene.zenv_curv_bake_margin
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
            temp_joined_obj.name = "__ZENV_TEMP_CURVATURE_JOINED__"

            bpy.ops.object.select_all(action='DESELECT')
            temp_joined_obj.select_set(True)
            context.view_layer.objects.active = temp_joined_obj

            if scene.zenv_curv_wireframe_enable:
                res = scene.zenv_curv_bake_resolution
                wire_mask = ZENV_CurvatureBake_Utils.build_uv_edge_mask(
                    temp_joined_obj,
                    res,
                    res,
                    scene.zenv_curv_wireframe_px,
                    scene.zenv_curv_wireframe_sharp_only,
                    scene.zenv_curv_wireframe_sharp_angle,
                )
                if wire_mask is not None and scene.zenv_curv_wireframe_falloff_px > 0:
                    wire_mask = ZENV_CurvatureBake_Utils.blur_mask_bytearray(
                        wire_mask,
                        res,
                        res,
                        scene.zenv_curv_wireframe_falloff_px,
                    )

            if scene.zenv_curv_temp_apply_scale:
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            if scene.zenv_curv_temp_bevel_width > 0.0:
                mod_bevel = temp_joined_obj.modifiers.new(name="__ZENV_TEMP_BEVEL__", type='BEVEL')
                if hasattr(mod_bevel, 'offset_type'):
                    mod_bevel.offset_type = 'WIDTH'
                elif hasattr(mod_bevel, 'width_type'):
                    mod_bevel.width_type = 'WIDTH'
                mod_bevel.width = scene.zenv_curv_temp_bevel_width
                mod_bevel.segments = scene.zenv_curv_temp_bevel_segments
                mod_bevel.limit_method = 'ANGLE'
                mod_bevel.angle_limit = radians(scene.zenv_curv_temp_bevel_angle)
                if hasattr(mod_bevel, 'miter_outer'):
                    mod_bevel.miter_outer = 'MITER_ARC'

            if scene.zenv_curv_temp_subdiv_levels > 0:
                mod_subdiv = temp_joined_obj.modifiers.new(name="__ZENV_TEMP_SUBDIV__", type='SUBSURF')
                mod_subdiv.subdivision_type = 'SIMPLE'
                mod_subdiv.levels = scene.zenv_curv_temp_subdiv_levels
                mod_subdiv.render_levels = scene.zenv_curv_temp_subdiv_levels

            if scene.zenv_curv_temp_recalc_normals:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.normals_make_consistent(inside=False)
                bpy.ops.object.mode_set(mode='OBJECT')

            temp_joined_obj.data.materials.clear()
            temp_joined_obj.data.materials.append(temp_material)

            margin = scene.zenv_curv_bake_margin
            bpy.ops.object.bake(
                type='EMIT',
                margin=margin,
                use_clear=True,
            )

            if scene.zenv_curv_wireframe_enable and wire_mask is not None:
                ZENV_CurvatureBake_Utils.composite_wire_mask_into_image(
                    bake_image,
                    wire_mask,
                    scene.zenv_curv_wireframe_strength,
                )

            if bake_image.has_data:
                bake_image.save_render(bake_image.filepath_raw)

            self.report({'INFO'}, f"Curvature baked: {bake_image.filepath_raw}")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Curvature bake failed")
            self.report({'ERROR'}, f"Curvature bake failed: {str(e)}")
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
                ZENV_CurvatureBake_Utils.restore_scene_settings(scene, settings)
            except Exception:
                pass

            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active


class ZENV_PT_TEX_BakeCurvatureEdgeHighlightMultiObject(bpy.types.Panel):
    bl_label = "TEX Bake Curvature Multi"
    bl_idname = "ZENV_PT_tex_bake_curvature_multi"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("zenv.tex_bake_curvature_edge_multi_object", icon='RENDER_STILL')

        box = layout.box()
        box.label(text="Bake:")
        box.prop(scene, "zenv_curv_bake_resolution")
        box.prop(scene, "zenv_curv_bake_samples")
        box.prop(scene, "zenv_curv_bake_margin")
        box.prop(scene, "zenv_curv_bake_use_gpu")

        box = layout.box()
        box.label(text="Overlay Tuning:")
        box.prop(scene, "zenv_curv_edge_strength")
        row = box.row(align=True)
        row.prop(scene, "zenv_curv_edge_low")
        row.prop(scene, "zenv_curv_edge_high")

        box = layout.box()
        box.label(text="Low Poly Boost:")
        box.prop(scene, "zenv_curv_temp_bevel_width")
        row = box.row(align=True)
        row.prop(scene, "zenv_curv_temp_bevel_segments")
        row.prop(scene, "zenv_curv_temp_bevel_angle")
        box.prop(scene, "zenv_curv_temp_subdiv_levels")
        box.prop(scene, "zenv_curv_temp_apply_scale")
        box.prop(scene, "zenv_curv_temp_recalc_normals")

        box = layout.box()
        box.label(text="Edge Lines:")
        box.prop(scene, "zenv_curv_wireframe_enable")
        if scene.zenv_curv_wireframe_enable:
            row = box.row(align=True)
            row.prop(scene, "zenv_curv_wireframe_px")
            row.prop(scene, "zenv_curv_wireframe_strength")
            box.prop(scene, "zenv_curv_wireframe_sharp_only")
            if scene.zenv_curv_wireframe_sharp_only:
                box.prop(scene, "zenv_curv_wireframe_sharp_angle")
            box.prop(scene, "zenv_curv_wireframe_falloff_px")

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
    ZENV_OT_TEX_BakeCurvatureEdgeHighlightMultiObject,
    ZENV_PT_TEX_BakeCurvatureEdgeHighlightMultiObject,
)


def _install_logger():
    """Attach a single StreamHandler to ``logger`` (idempotent)."""
    global _zenv_curvature_bake_console_handler
    if _zenv_curvature_bake_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_curvature_bake_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by :func:`_install_logger`."""
    global _zenv_curvature_bake_console_handler
    if _zenv_curvature_bake_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_curvature_bake_console_handler)
    except ValueError:
        pass
    _zenv_curvature_bake_console_handler = None


def register():
    _install_logger()
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_CurvatureBake_Properties.register()


def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_CurvatureBake_Properties.unregister()
    _uninstall_logger()


if __name__ == "__main__":
    register()
