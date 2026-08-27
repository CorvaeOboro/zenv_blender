#region META
bl_info = {
    "name": 'TEX Bake UV Island Facing-Center Mask',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Bake a black/white mask where 1 face per connected UV island is chosen based on facing a world center',
    "status": 'working',
    "approved": True,
    "group": 'Texture',
    "group_prefix": 'TEX',
    "group_order": 10,
    "addon_order": 50,
    "tags": ['texture', 'bake', 'mask', 'uv-island', 'facing', 'center', 'multi-object'],
    "description_short": 'per UV island pick 1 face facing a center point; bake mask via EMIT',
    "description_medium": 'Bake directional facing mask per object via dot-product face normal - Inward, Outward, Up, and Down modes with UV island or mesh connectivity grouping',
    "description_long": """
TEX MULTI-OBJECT UV ISLAND FACING-CENTER MASK BAKER
- Select multiple mesh objects that share a UV layout / texture space
- Addon duplicates them, joins into a temp object
- Finds connected UV islands (faces connected across non-seam UV edges)
- For each island, selects 1 face whose normal best points toward a configurable world-space center or direction
- Writes a face-attribute mask and bakes it to a black/white texture via EMIT
- Saves to //textures/ and restores scene settings
""",
    "image_overview": 'zenv_blender_TEX_bake_uv_island_facing_center_mask_multi.png',
    "addon_image": 'zenv_blender_TEX_bake_uv_island_facing_center_mask_multi.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
from datetime import datetime
import logging
import math
from math import radians
from mathutils import Vector

logger = logging.getLogger(__name__)
_zenv_uv_island_facing_center_mask_console_handler = None
#endregion


#region PROPS
class ZENV_UVIslandFacingCenterMask_Properties:
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_islandmask_bake_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Mask bake texture resolution",
            default=1024,
            min=64,
            max=8192,
        )
        bpy.types.Scene.zenv_islandmask_bake_samples = bpy.props.IntProperty(
            name="Samples",
            description="Cycles samples for mask baking",
            default=16,
            min=1,
            max=4096,
        )
        bpy.types.Scene.zenv_islandmask_bake_margin = bpy.props.IntProperty(
            name="Margin",
            description="Bake padding in pixels (0 = no padding)",
            default=0,
            min=0,
            max=256,
        )
        bpy.types.Scene.zenv_islandmask_bake_use_gpu = bpy.props.BoolProperty(
            name="Use GPU",
            description="Use GPU for Cycles baking when available",
            default=True,
        )

        bpy.types.Scene.zenv_islandmask_uv_map = bpy.props.StringProperty(
            name="UV Map",
            description="UV map name to use (blank = active UV)",
            default="",
        )

        bpy.types.Scene.zenv_islandmask_grouping_mode = bpy.props.EnumProperty(
            name="Grouping",
            description="How to group faces into sub-components (one face picked per group)",
            items=(
                ('UV', "UV Continuity", "Groups faces by UV continuity across shared mesh edges"),
                ('MESH_EDGE', "Mesh (Edge Connected)", "Groups faces by mesh connectivity (UV seams ignored)"),
                ('MESH_VERT', "Mesh (Vertex Connected)", "Groups faces by any shared vertex (loose connectivity)"),
            ),
            default='UV',
        )

        bpy.types.Scene.zenv_islandmask_uv_epsilon = bpy.props.FloatProperty(
            name="UV Epsilon",
            description="UV comparison tolerance for UV continuity grouping",
            default=1e-5,
            min=1e-9,
            max=1e-2,
            precision=8,
        )

        bpy.types.Scene.zenv_islandmask_center = bpy.props.FloatVectorProperty(
            name="Center",
            description="World-space center point the faces should face",
            default=(0.0, 0.0, 0.0),
            size=3,
            subtype='TRANSLATION',
        )
        bpy.types.Scene.zenv_islandmask_center_height_offset = bpy.props.FloatProperty(
            name="Height Offset",
            description="Offset added to center Z before evaluating facing",
            default=0.0,
            min=-100000.0,
            max=100000.0,
        )

        bpy.types.Scene.zenv_islandmask_sharp_only = bpy.props.BoolProperty(
            name="Sharp Edges Only",
            description="UV islands are defined by UV continuity; additionally restrict mask selection to faces adjacent to edges above threshold",
            default=False,
        )
        bpy.types.Scene.zenv_islandmask_sharp_angle = bpy.props.FloatProperty(
            name="Sharp Angle",
            description="Edge angle threshold in degrees when Sharp Edges Only is enabled",
            default=30.0,
            min=0.0,
            max=180.0,
            subtype='ANGLE',
        )

        bpy.types.Scene.zenv_islandmask_match_threshold_enable = bpy.props.BoolProperty(
            name="Match Threshold",
            description="Only allow faces within the angle threshold of the target direction; if none match, nothing is selected (black)",
            default=False,
        )
        bpy.types.Scene.zenv_islandmask_match_threshold_angle = bpy.props.FloatProperty(
            name="Max Angle",
            description="Maximum allowed angle (degrees) between face normal and target direction",
            default=45.0,
            min=0.0,
            max=180.0,
            subtype='ANGLE',
        )

    @classmethod
    def unregister(cls):
        for attr in (
            'zenv_islandmask_bake_resolution',
            'zenv_islandmask_bake_samples',
            'zenv_islandmask_bake_margin',
            'zenv_islandmask_bake_use_gpu',
            'zenv_islandmask_uv_map',
            'zenv_islandmask_grouping_mode',
            'zenv_islandmask_uv_epsilon',
            'zenv_islandmask_center',
            'zenv_islandmask_center_height_offset',
            'zenv_islandmask_sharp_only',
            'zenv_islandmask_sharp_angle',
            'zenv_islandmask_match_threshold_enable',
            'zenv_islandmask_match_threshold_angle',
        ):
            if hasattr(bpy.types.Scene, attr):
                delattr(bpy.types.Scene, attr)
#endregion


#region UTILS
class ZENV_UVIslandFacingCenterMask_Utils:
    MASK_ATTR_NAME = "zenv_island_facing_mask"

    @staticmethod
    def replace_object_mesh_with_evaluated_copy(obj: bpy.types.Object, depsgraph):
        if obj.type != 'MESH':
            return
        try:
            eval_obj = obj.evaluated_get(depsgraph)
            new_mesh = bpy.data.meshes.new_from_object(
                eval_obj,
                preserve_all_data_layers=True,
                depsgraph=depsgraph,
            )
        except Exception:
            return

        old_mesh = obj.data
        obj.data = new_mesh
        try:
            if old_mesh and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
        except Exception:
            pass

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
    def create_mask_image(context, mode: str):
        prefix = ZENV_UVIslandFacingCenterMask_Utils.get_blend_filename_prefix()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_str = str(mode).lower()
        image_name = f"{prefix}_island_facing_mask_{mode_str}_{timestamp}"

        res = context.scene.zenv_islandmask_bake_resolution
        image = bpy.data.images.new(
            name=image_name,
            width=res,
            height=res,
            alpha=False,
            float_buffer=True,
        )

        texture_dir = ZENV_UVIslandFacingCenterMask_Utils.ensure_texture_directory()
        image_path = os.path.join(texture_dir, f"{image_name}.png")
        image.filepath_raw = image_path
        image.file_format = 'PNG'
        return image

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

    @staticmethod
    def _uv_pair_matches(pair_a, pair_b, eps: float) -> bool:
        if pair_a is None or pair_b is None:
            return False
        a0, a1 = pair_a
        b0, b1 = pair_b
        if (a0 - b0).length <= eps and (a1 - b1).length <= eps:
            return True
        if (a0 - b1).length <= eps and (a1 - b0).length <= eps:
            return True
        return False

    @staticmethod
    def build_connected_uv_islands(mesh: bpy.types.Mesh, uv_map_name: str, uv_epsilon: float = 1e-5):
        return ZENV_UVIslandFacingCenterMask_Utils.build_connected_uv_islands_with_epsilon(mesh, uv_map_name, uv_epsilon)

    @staticmethod
    def build_connected_uv_islands_with_epsilon(mesh: bpy.types.Mesh, uv_map_name: str, uv_epsilon: float):
        if not mesh.uv_layers:
            return []

        if uv_map_name:
            uv_layer = mesh.uv_layers.get(uv_map_name)
        else:
            uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            return []

        uv_data = uv_layer.data
        loops = mesh.loops
        polys = mesh.polygons

        eps = float(max(1e-9, uv_epsilon))
        neighbors = {p.index: set() for p in polys}

        edge_map = {}
        for poly in polys:
            ls = poly.loop_start
            lt = poly.loop_total
            for i in range(lt):
                li = ls + i
                li_next = ls + ((i + 1) % lt)
                v0 = loops[li].vertex_index
                v1 = loops[li_next].vertex_index
                key = (v0, v1) if v0 < v1 else (v1, v0)

                uv0 = uv_data[li].uv
                uv1 = uv_data[li_next].uv
                pair = (Vector((uv0.x, uv0.y)), Vector((uv1.x, uv1.y)))
                edge_map.setdefault(key, []).append((poly.index, pair))

        for entries in edge_map.values():
            if len(entries) < 2:
                continue
            for i in range(len(entries)):
                f0, p0 = entries[i]
                for j in range(i + 1, len(entries)):
                    f1, p1 = entries[j]
                    if ZENV_UVIslandFacingCenterMask_Utils._uv_pair_matches(p0, p1, eps):
                        neighbors[f0].add(f1)
                        neighbors[f1].add(f0)

        visited = set()
        islands = []
        for poly in polys:
            idx = poly.index
            if idx in visited:
                continue
            stack = [idx]
            visited.add(idx)
            comp = []
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in neighbors.get(cur, ()): 
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
            islands.append(comp)

        return islands

    @staticmethod
    def build_connected_mesh_components(mesh: bpy.types.Mesh, connect_by_vertex: bool):
        polys = mesh.polygons
        neighbors = {p.index: set() for p in polys}

        if connect_by_vertex:
            vert_to_faces = {}
            for poly in polys:
                for v in poly.vertices:
                    vert_to_faces.setdefault(int(v), []).append(poly.index)
            for faces in vert_to_faces.values():
                if len(faces) < 2:
                    continue
                for i in range(len(faces)):
                    f0 = faces[i]
                    for j in range(i + 1, len(faces)):
                        f1 = faces[j]
                        neighbors[f0].add(f1)
                        neighbors[f1].add(f0)
        else:
            edge_to_faces = {}
            for poly in polys:
                vtx = poly.vertices
                for i in range(len(vtx)):
                    a = int(vtx[i])
                    b = int(vtx[(i + 1) % len(vtx)])
                    key = (a, b) if a < b else (b, a)
                    edge_to_faces.setdefault(key, []).append(poly.index)
            for faces in edge_to_faces.values():
                if len(faces) != 2:
                    continue
                f0, f1 = faces
                neighbors[f0].add(f1)
                neighbors[f1].add(f0)

        visited = set()
        comps = []
        for poly in polys:
            idx = poly.index
            if idx in visited:
                continue
            stack = [idx]
            visited.add(idx)
            comp = []
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in neighbors.get(cur, ()):
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
            comps.append(comp)
        return comps

    @staticmethod
    def create_or_get_face_mask_attribute(mesh: bpy.types.Mesh):
        attr = mesh.attributes.get(ZENV_UVIslandFacingCenterMask_Utils.MASK_ATTR_NAME)
        if attr is None:
            attr = mesh.attributes.new(
                name=ZENV_UVIslandFacingCenterMask_Utils.MASK_ATTR_NAME,
                type='FLOAT',
                domain='FACE',
            )
        return attr

    @staticmethod
    def clear_face_mask_attribute(attr):
        for i in range(len(attr.data)):
            attr.data[i].value = 0.0

    @staticmethod
    def choose_face_per_island(
        obj,
        islands,
        center_world: Vector,
        sharp_only: bool,
        sharp_angle_deg: float,
        mode: str,
        match_threshold_enable: bool,
        match_threshold_angle_deg: float,
    ):
        mesh = obj.data
        polys = mesh.polygons
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()

        sharp_faces = None
        if sharp_only:
            angle_th = radians(float(sharp_angle_deg))
            sharp_faces = set()
            edge_to_faces = {}
            for poly in polys:
                vtx = poly.vertices
                for i in range(len(vtx)):
                    a = int(vtx[i])
                    b = int(vtx[(i + 1) % len(vtx)])
                    key = (a, b) if a < b else (b, a)
                    edge_to_faces.setdefault(key, []).append(poly.index)

            for faces in edge_to_faces.values():
                if len(faces) == 1:
                    sharp_faces.add(faces[0])
                    continue
                if len(faces) != 2:
                    continue
                f0, f1 = faces
                try:
                    ang = polys[f0].normal.angle(polys[f1].normal)
                except Exception:
                    continue
                if ang >= angle_th:
                    sharp_faces.add(f0)
                    sharp_faces.add(f1)

        chosen = []
        eps = 1e-12

        mode = str(mode).upper()

        if match_threshold_enable:
            angle_th = radians(float(match_threshold_angle_deg))
            cos_limit = float(max(-1.0, min(1.0, math.cos(angle_th))))
        else:
            cos_limit = -1.0

        up = Vector((0.0, 0.0, 1.0))
        down = Vector((0.0, 0.0, -1.0))

        for island in islands:
            best_face = None
            best_score = -1e30
            best_dist2 = 1e30

            def consider_face(fi):
                nonlocal best_face, best_score, best_dist2
                poly = polys[fi]
                wc = obj.matrix_world @ poly.center
                v = center_world - wc
                n = normal_matrix @ poly.normal
                if n.length_squared <= eps:
                    return
                n.normalize()

                if mode == 'UP':
                    target_dir = up
                    dot = float(n.dot(target_dir))
                    dist2 = 0.0
                elif mode == 'DOWN':
                    target_dir = down
                    dot = float(n.dot(target_dir))
                    dist2 = 0.0
                else:
                    if v.length_squared < eps:
                        return
                    dir_to_center = v.normalized()
                    target_dir = (-dir_to_center) if mode == 'OUTWARD' else dir_to_center
                    dot = float(n.dot(target_dir))
                    dist2 = float(v.length_squared)

                if match_threshold_enable and dot < cos_limit:
                    return

                score = dot

                if best_face is None:
                    best_score = score
                    best_dist2 = dist2
                    best_face = fi
                    return

                if score > best_score + 1e-9:
                    best_score = score
                    best_dist2 = dist2
                    best_face = fi
                    return

                if abs(score - best_score) <= 1e-9 and dist2 < best_dist2:
                    best_score = score
                    best_dist2 = dist2
                    best_face = fi

            if sharp_faces is not None:
                for fi in island:
                    if fi in sharp_faces:
                        consider_face(fi)
            if best_face is None:
                for fi in island:
                    consider_face(fi)

            if best_face is not None:
                chosen.append(best_face)

        return chosen

    @staticmethod
    def create_temp_mask_bake_material(image):
        mat = bpy.data.materials.new(name="__ZENV_TEMP_ISLAND_MASK_BAKE_MAT__")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        tex = nodes.new('ShaderNodeTexImage')
        tex.image = image
        tex.select = True
        nodes.active = tex

        attr = nodes.new('ShaderNodeAttribute')
        attr.attribute_name = ZENV_UVIslandFacingCenterMask_Utils.MASK_ATTR_NAME

        comb = nodes.new('ShaderNodeCombineColor')
        comb.mode = 'RGB'

        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Strength'].default_value = 1.0

        out = nodes.new('ShaderNodeOutputMaterial')

        tex.location = (-900, 300)
        attr.location = (-700, 0)
        comb.location = (-400, 0)
        emission.location = (-100, 0)
        out.location = (200, 0)

        links.new(attr.outputs['Fac'], comb.inputs[0])
        links.new(attr.outputs['Fac'], comb.inputs[1])
        links.new(attr.outputs['Fac'], comb.inputs[2])
        links.new(comb.outputs[0], emission.inputs['Color'])
        links.new(emission.outputs['Emission'], out.inputs['Surface'])

        return mat
#endregion


#region OP
class ZENV_OT_TEX_BakeUVIslandFacingCenterMaskMultiObject(bpy.types.Operator):
    """Bake a facing-center mask picking 1 face per UV island for multiple objects.

    Duplicates selected meshes, finds connected UV islands (or mesh-connected
    components), picks 1 face per island whose normal best points toward a
    configurable world-space center or direction (Inward/Outward/Up/Down),
    writes a face-attribute mask, and bakes it to a B/W texture via EMIT.
    """
    bl_idname = "zenv.tex_bake_uv_island_facing_center_mask_multi_object"
    bl_label = "Bake UV Island Facing Mask (Multi-Object)"
    bl_description = "Pick 1 face per connected UV island (best facing a center) and bake a B/W mask via EMIT"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        description="How to choose the face per group",
        items=(
            ('INWARD', "Inward", "Pick the face whose normal best points toward the center"),
            ('OUTWARD', "Outward", "Pick the face whose normal best points away from the center"),
            ('UP', "Up", "Pick the face whose normal best points up (+Z)"),
            ('DOWN', "Down", "Pick the face whose normal best points down (-Z)"),
        ),
        default='INWARD',
    )

    @classmethod
    def poll(cls, context):
        """Only enable when at least one mesh object is selected."""
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        scene = context.scene

        depsgraph = context.evaluated_depsgraph_get()

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

        settings = ZENV_UVIslandFacingCenterMask_Utils.store_scene_settings(scene)

        temp_duplicates = []
        temp_material = None
        bake_image = None

        try:
            bake_image = ZENV_UVIslandFacingCenterMask_Utils.create_mask_image(context, mode=self.mode)

            scene.render.engine = 'CYCLES'
            if hasattr(scene, 'cycles'):
                scene.cycles.device = 'GPU' if scene.zenv_islandmask_bake_use_gpu else 'CPU'
                scene.cycles.samples = scene.zenv_islandmask_bake_samples
                scene.cycles.use_denoising = False

            scene.view_settings.view_transform = 'Standard'

            scene.render.bake.margin = scene.zenv_islandmask_bake_margin
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

            uv_map_name = scene.zenv_islandmask_uv_map.strip()
            for obj in temp_duplicates:
                ZENV_UVIslandFacingCenterMask_Utils.ensure_uv_layer_on_object(obj, uv_map_name)

            for obj in temp_duplicates:
                ZENV_UVIslandFacingCenterMask_Utils.replace_object_mesh_with_evaluated_copy(obj, depsgraph)
                ZENV_UVIslandFacingCenterMask_Utils.ensure_uv_layer_on_object(obj, uv_map_name)

            center = Vector(scene.zenv_islandmask_center)
            center.z += float(scene.zenv_islandmask_center_height_offset)

            temp_material = ZENV_UVIslandFacingCenterMask_Utils.create_temp_mask_bake_material(bake_image)

            for obj in temp_duplicates:
                grouping_mode = scene.zenv_islandmask_grouping_mode
                if grouping_mode == 'UV':
                    islands = ZENV_UVIslandFacingCenterMask_Utils.build_connected_uv_islands_with_epsilon(
                        obj.data,
                        uv_map_name,
                        scene.zenv_islandmask_uv_epsilon,
                    )
                elif grouping_mode == 'MESH_VERT':
                    islands = ZENV_UVIslandFacingCenterMask_Utils.build_connected_mesh_components(obj.data, True)
                else:
                    islands = ZENV_UVIslandFacingCenterMask_Utils.build_connected_mesh_components(obj.data, False)
                if not islands:
                    self.report({'ERROR'}, f"Could not build UV islands on: {obj.name}")
                    return {'CANCELLED'}

                chosen_faces = ZENV_UVIslandFacingCenterMask_Utils.choose_face_per_island(
                    obj,
                    islands,
                    center_world=center,
                    sharp_only=scene.zenv_islandmask_sharp_only,
                    sharp_angle_deg=scene.zenv_islandmask_sharp_angle,
                    mode=self.mode,
                    match_threshold_enable=scene.zenv_islandmask_match_threshold_enable,
                    match_threshold_angle_deg=scene.zenv_islandmask_match_threshold_angle,
                )

                attr = ZENV_UVIslandFacingCenterMask_Utils.create_or_get_face_mask_attribute(obj.data)
                ZENV_UVIslandFacingCenterMask_Utils.clear_face_mask_attribute(attr)
                for fi in chosen_faces:
                    if 0 <= fi < len(attr.data):
                        attr.data[fi].value = 1.0

                obj.data.materials.clear()
                obj.data.materials.append(temp_material)

            bpy.ops.object.select_all(action='DESELECT')
            for obj in temp_duplicates:
                obj.select_set(True)
            context.view_layer.objects.active = temp_duplicates[0] if temp_duplicates else None

            margin = scene.zenv_islandmask_bake_margin
            for i, obj in enumerate(temp_duplicates):
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.bake(
                    type='EMIT',
                    margin=margin,
                    use_clear=(i == 0),
                )

            if bake_image.has_data:
                bake_image.save_render(bake_image.filepath_raw)

            baked_mode = str(self.mode).lower()
            self.report({'INFO'}, f"Island mask ({baked_mode}) baked: {bake_image.filepath_raw}")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Island facing mask bake failed")
            self.report({'ERROR'}, f"Island facing mask bake failed: {str(e)}")
            return {'CANCELLED'}

        finally:
            try:
                if temp_duplicates:
                    for obj in temp_duplicates:
                        try:
                            bpy.data.objects.remove(obj, do_unlink=True)
                        except Exception:
                            pass
            except Exception:
                pass

            try:
                if temp_material:
                    bpy.data.materials.remove(temp_material, do_unlink=True)
            except Exception:
                pass

            try:
                ZENV_UVIslandFacingCenterMask_Utils.restore_scene_settings(scene, settings)
            except Exception:
                pass

            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active
#endregion


#region PANEL
class ZENV_PT_TEX_BakeUVIslandFacingCenterMaskMultiObject(bpy.types.Panel):
    """Panel for the multi-object UV island facing-center mask baker."""
    bl_label = "TEX Bake UV Island Facing Mask"
    bl_idname = "ZENV_PT_tex_bake_uv_island_facing_mask"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        op_in = row.operator("zenv.tex_bake_uv_island_facing_center_mask_multi_object", text="Bake Inward", icon='RENDER_STILL')
        op_in.mode = 'INWARD'
        op_out = row.operator("zenv.tex_bake_uv_island_facing_center_mask_multi_object", text="Bake Outward", icon='RENDER_STILL')
        op_out.mode = 'OUTWARD'

        row = layout.row(align=True)
        op_up = row.operator("zenv.tex_bake_uv_island_facing_center_mask_multi_object", text="Bake Up", icon='RENDER_STILL')
        op_up.mode = 'UP'
        op_down = row.operator("zenv.tex_bake_uv_island_facing_center_mask_multi_object", text="Bake Down", icon='RENDER_STILL')
        op_down.mode = 'DOWN'

        box = layout.box()
        box.label(text="Bake:")
        box.prop(scene, "zenv_islandmask_bake_resolution")
        box.prop(scene, "zenv_islandmask_bake_samples")
        box.prop(scene, "zenv_islandmask_bake_margin")
        box.prop(scene, "zenv_islandmask_bake_use_gpu")

        box = layout.box()
        box.label(text="UV:")
        box.prop(scene, "zenv_islandmask_uv_map")

        box = layout.box()
        box.label(text="Grouping:")
        box.prop(scene, "zenv_islandmask_grouping_mode")
        if scene.zenv_islandmask_grouping_mode == 'UV':
            box.prop(scene, "zenv_islandmask_uv_epsilon")

        box = layout.box()
        box.label(text="Facing Center:")
        box.prop(scene, "zenv_islandmask_center")
        box.prop(scene, "zenv_islandmask_center_height_offset")

        box = layout.box()
        box.label(text="Optional Restriction:")
        box.prop(scene, "zenv_islandmask_sharp_only")
        if scene.zenv_islandmask_sharp_only:
            box.prop(scene, "zenv_islandmask_sharp_angle")

        box.prop(scene, "zenv_islandmask_match_threshold_enable")
        if scene.zenv_islandmask_match_threshold_enable:
            box.prop(scene, "zenv_islandmask_match_threshold_angle")

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
#endregion


#region REG
classes = (
    ZENV_OT_TEX_BakeUVIslandFacingCenterMaskMultiObject,
    ZENV_PT_TEX_BakeUVIslandFacingCenterMaskMultiObject,
)


def register():
    """Register the addon classes, properties, and logger."""
    global _zenv_uv_island_facing_center_mask_console_handler
    if _zenv_uv_island_facing_center_mask_console_handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _zenv_uv_island_facing_center_mask_console_handler = handler
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_UVIslandFacingCenterMask_Properties.register()


def unregister():
    """Unregister the addon classes, properties, and logger."""
    global _zenv_uv_island_facing_center_mask_console_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_UVIslandFacingCenterMask_Properties.unregister()
    if _zenv_uv_island_facing_center_mask_console_handler is not None:
        try:
            logger.removeHandler(_zenv_uv_island_facing_center_mask_console_handler)
        except ValueError:
            pass
        _zenv_uv_island_facing_center_mask_console_handler = None


if __name__ == "__main__":
    register()
#endregion
