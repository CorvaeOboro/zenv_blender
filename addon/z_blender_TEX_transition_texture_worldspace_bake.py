bl_info = {
    "name": "TEX Bake Transition Worldspace",
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260711',
    "location": "View3D > Sidebar > ZENV",
    "description": "Bake a seamless transitional texture in world space",
}

import math
import os
import traceback
from array import array
from datetime import datetime

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector
from mathutils.bvhtree import BVHTree


__all__ = ('bl_info', 'register', 'unregister')


_LOG_PREFIX = '[ZENV Worldspace Transition]'


def _log(message):
    print(f"{_LOG_PREFIX} {message}")


def _mesh_poll(self, obj):
    return obj is not None and obj.type == 'MESH'


class ZENV_PG_WorldspaceTransition(PropertyGroup):
    source: PointerProperty(name="Source", type=bpy.types.Object, poll=_mesh_poll)
    target: PointerProperty(name="Target", type=bpy.types.Object, poll=_mesh_poll)
    width: IntProperty(name="Width", default=1024, min=16, max=8192)
    height: IntProperty(name="Height", default=1024, min=16, max=8192)
    max_distance: FloatProperty(name="Transition Distance", default=0.1, min=0.000001, soft_max=10.0, subtype='DISTANCE')
    falloff_power: FloatProperty(name="Falloff Power", default=1.0, min=0.05, max=16.0)
    mirror_sampling: BoolProperty(name="Mirror / Unfold Sampling", default=True)
    mirror_scale: FloatProperty(name="Mirror Scale", default=1.0, min=0.0, max=8.0)
    filtering: EnumProperty(
        name="Source Filtering",
        items=(('BILINEAR', "Bilinear", "Bilinear source texture sampling"), ('NEAREST', "Nearest", "Nearest source texel sampling")),
        default='BILINEAR',
    )
    margin: IntProperty(name="UV Margin", default=8, min=0, max=64, subtype='PIXEL')
    bidirectional: BoolProperty(name="Bake Both Directions", default=True)
    auto_filename: BoolProperty(name="Automatic Texture Name", default=True)
    output_name: StringProperty(name="Image Name", default="Worldspace_Transition")
    output_file: StringProperty(name="File Name", default="worldspace_transition.png")
    output_directory: StringProperty(name="Output Directory", default="//textures/", subtype='DIR_PATH')


class _MeshSurface:
    def __init__(self, obj, depsgraph, uv_name):
        self.object = obj
        self.evaluated = obj.evaluated_get(depsgraph)
        self.mesh = bpy.data.meshes.new_from_object(
            self.evaluated,
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        self.matrix_world = self.evaluated.matrix_world.copy()
        self.mesh.calc_loop_triangles()
        uv_layer = self.mesh.uv_layers.get(uv_name) if uv_name else self.mesh.uv_layers.active
        if uv_layer is None:
            self.free()
            raise ValueError(f"{obj.name} has no usable UV map")
        self.uv_name = uv_layer.name
        uv_data = uv_layer.data
        self.world_vertices = [self.matrix_world @ vertex.co for vertex in self.mesh.vertices]
        self.triangles = []
        polygons = []
        for loop_triangle in self.mesh.loop_triangles:
            vertex_indices = tuple(loop_triangle.vertices)
            loops = tuple(loop_triangle.loops)
            self.triangles.append({
                'vertices': vertex_indices,
                'world': tuple(self.world_vertices[index] for index in vertex_indices),
                'uv': tuple(uv_data[index].uv.copy() for index in loops),
                'polygon': loop_triangle.polygon_index,
                'material': self.mesh.polygons[loop_triangle.polygon_index].material_index,
            })
            polygons.append(vertex_indices)
        if not polygons:
            self.free()
            raise ValueError(f"{obj.name} has no triangles")
        self.bvh = BVHTree.FromPolygons(self.world_vertices, polygons, all_triangles=True)

    def nearest(self, point):
        return self.bvh.find_nearest(point)

    def free(self):
        if getattr(self, 'mesh', None) is not None:
            bpy.data.meshes.remove(self.mesh)
            self.mesh = None


class _ImageSampler:
    def __init__(self, image, extension='REPEAT', filtering='BILINEAR'):
        self.image = image
        self.width = image.size[0]
        self.height = image.size[1]
        self.channels = image.channels
        self.extension = extension
        self.filtering = filtering
        self.pixels = array('f', [0.0]) * len(image.pixels)
        image.pixels.foreach_get(self.pixels)

    def axis(self, value):
        if self.extension == 'REPEAT':
            return value - math.floor(value), True
        if self.extension == 'CLIP':
            return value, 0.0 <= value <= 1.0
        return max(0.0, min(1.0, value)), True

    def texel(self, x, y):
        if self.extension == 'REPEAT':
            x %= self.width
            y %= self.height
        else:
            x = max(0, min(self.width - 1, x))
            y = max(0, min(self.height - 1, y))
        index = (y * self.width + x) * self.channels
        r = self.pixels[index]
        g = self.pixels[index + 1] if self.channels > 1 else r
        b = self.pixels[index + 2] if self.channels > 2 else r
        a = self.pixels[index + 3] if self.channels > 3 else 1.0
        return r, g, b, a

    def sample(self, uv):
        u, valid_u = self.axis(uv.x)
        v, valid_v = self.axis(uv.y)
        if not valid_u or not valid_v:
            return 0.0, 0.0, 0.0, 0.0
        if self.filtering == 'NEAREST':
            return self.texel(math.floor(u * self.width), math.floor(v * self.height))
        x = u * self.width - 0.5
        y = v * self.height - 0.5
        x0 = math.floor(x)
        y0 = math.floor(y)
        tx = x - x0
        ty = y - y0
        c00 = self.texel(x0, y0)
        c10 = self.texel(x0 + 1, y0)
        c01 = self.texel(x0, y0 + 1)
        c11 = self.texel(x0 + 1, y0 + 1)
        return tuple(
            (c00[i] * (1.0 - tx) + c10[i] * tx) * (1.0 - ty)
            + (c01[i] * (1.0 - tx) + c11[i] * tx) * ty
            for i in range(4)
        )


class _TransitionUtils:
    """Private utility methods for the world-space transition bake."""

    @staticmethod
    def barycentric_2d(point, a, b, c):
        denominator = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
        if abs(denominator) < 1.0e-20:
            return None
        w0 = ((b.y - c.y) * (point.x - c.x) + (c.x - b.x) * (point.y - c.y)) / denominator
        w1 = ((c.y - a.y) * (point.x - c.x) + (a.x - c.x) * (point.y - c.y)) / denominator
        return w0, w1, 1.0 - w0 - w1

    @staticmethod
    def barycentric_3d(point, a, b, c):
        v0 = b - a
        v1 = c - a
        v2 = point - a
        d00 = v0.dot(v0)
        d01 = v0.dot(v1)
        d11 = v1.dot(v1)
        d20 = v2.dot(v0)
        d21 = v2.dot(v1)
        denominator = d00 * d11 - d01 * d01
        if abs(denominator) < 1.0e-20:
            return 1.0, 0.0, 0.0
        w1 = (d11 * d20 - d01 * d21) / denominator
        w2 = (d00 * d21 - d01 * d20) / denominator
        return 1.0 - w1 - w2, w1, w2

    @staticmethod
    def interpolated_uv(point, triangle):
        weights = _TransitionUtils.barycentric_3d(point, *triangle['world'])
        return triangle['uv'][0] * weights[0] + triangle['uv'][1] * weights[1] + triangle['uv'][2] * weights[2]

    @staticmethod
    def _is_source_image_node(node):
        return (
            node.type == 'TEX_IMAGE'
            and node.image is not None
            and node.name != "ZENV Worldspace Transition"
            and node.label != "Worldspace Transition RGBA"
        )

    @staticmethod
    def _upstream_image_nodes(socket, visited):
        images = []
        for link in socket.links:
            node = link.from_node
            pointer = node.as_pointer()
            if pointer in visited:
                continue
            visited.add(pointer)
            if _TransitionUtils._is_source_image_node(node):
                images.append(node)
                continue
            inputs = list(node.inputs)
            if node.type == 'BSDF_PRINCIPLED':
                base_color = node.inputs.get('Base Color')
                if base_color is not None:
                    inputs = [base_color] + [item for item in inputs if item != base_color]
            for input_socket in inputs:
                if input_socket.is_linked:
                    images.extend(_TransitionUtils._upstream_image_nodes(input_socket, visited))
        return images

    @staticmethod
    def material_image_nodes(material):
        if material is None or not material.use_nodes:
            return []
        nodes = material.node_tree.nodes
        outputs = [node for node in nodes if node.type == 'OUTPUT_MATERIAL' and node.is_active_output]
        linked = []
        for output in outputs:
            surface = output.inputs.get('Surface')
            if surface is not None and surface.is_linked:
                linked.extend(_TransitionUtils._upstream_image_nodes(surface, set()))
        if linked:
            unique = []
            seen = set()
            for node in linked:
                pointer = node.as_pointer()
                if pointer not in seen:
                    seen.add(pointer)
                    unique.append(node)
            return unique
        return [node for node in nodes if _TransitionUtils._is_source_image_node(node)]

    @staticmethod
    def find_image_node(obj, material_index):
        material = None
        if 0 <= material_index < len(obj.material_slots):
            material = obj.material_slots[material_index].material
        candidates = _TransitionUtils.material_image_nodes(material)
        if candidates:
            node = candidates[0]
            return node.image, node.extension
        return None, 'REPEAT'

    @staticmethod
    def smooth_falloff(distance, maximum, power):
        value = max(0.0, min(1.0, 1.0 - distance / maximum))
        value = value * value * (3.0 - 2.0 * value)
        return value ** power

    @staticmethod
    def dilate_pixels(pixels, width, height, iterations):
        occupied = bytearray(width * height)
        for index in range(width * height):
            occupied[index] = 1 if pixels[index * 4 + 3] > 0.0 else 0
        for _ in range(iterations):
            source = pixels[:]
            source_occupied = occupied[:]
            changed = False
            for y in range(height):
                for x in range(width):
                    index = y * width + x
                    if source_occupied[index]:
                        continue
                    neighbours = []
                    if x > 0:
                        neighbours.append(index - 1)
                    if x + 1 < width:
                        neighbours.append(index + 1)
                    if y > 0:
                        neighbours.append(index - width)
                    if y + 1 < height:
                        neighbours.append(index + width)
                    donor = next((item for item in neighbours if source_occupied[item]), None)
                    if donor is None:
                        continue
                    pixels[index * 4:index * 4 + 4] = source[donor * 4:donor * 4 + 4]
                    occupied[index] = 1
                    changed = True
            if not changed:
                break

    @staticmethod
    def underlying_image(obj):
        material_counts = {}
        for polygon in obj.data.polygons:
            material_counts[polygon.material_index] = material_counts.get(polygon.material_index, 0) + 1
        material_indices = sorted(material_counts, key=material_counts.get, reverse=True)
        for material_index in material_indices:
            if material_index < 0 or material_index >= len(obj.material_slots):
                continue
            material = obj.material_slots[material_index].material
            candidates = _TransitionUtils.material_image_nodes(material)
            if candidates:
                _log(
                    f"Resolved '{obj.name}' texture '{candidates[0].image.name}' from assigned material "
                    f"'{material.name}' ({material_counts[material_index]} faces)"
                )
                return candidates[0].image
        return None

    @staticmethod
    def texture_stem(image, fallback):
        if image is None:
            raw_name = fallback
        elif image.filepath:
            raw_name = os.path.basename(bpy.path.abspath(image.filepath))
        else:
            raw_name = image.name
        stem = os.path.splitext(raw_name)[0]
        clean = ''.join(character if character.isalnum() or character in {'-', '_'} else '_' for character in stem)
        clean = clean.strip('_')
        return clean or "texture"

    @staticmethod
    def automatic_output_name(settings, source_obj, target_obj):
        source_image = _TransitionUtils.underlying_image(source_obj)
        target_image = _TransitionUtils.underlying_image(target_obj)
        source_name = _TransitionUtils.texture_stem(source_image, source_obj.name)
        target_name = _TransitionUtils.texture_stem(target_image, target_obj.name)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{target_name}_transition_{source_name}_{timestamp}"

    @staticmethod
    def create_output_image(settings, pixels, source_obj, target_obj):
        if settings.auto_filename:
            base_name = _TransitionUtils.automatic_output_name(settings, source_obj, target_obj)
            image_name = base_name
            suffix = 2
            while bpy.data.images.get(image_name) is not None:
                image_name = f"{base_name}_{suffix}"
                suffix += 1
            filename = image_name + '.png'
        else:
            image_name = settings.output_name.strip() or "Worldspace_Transition"
            filename = settings.output_file.strip() or "worldspace_transition.png"
            if not filename.lower().endswith('.png'):
                filename += '.png'
        expected_values = settings.width * settings.height * 4
        if len(pixels) != expected_values:
            raise ValueError(f"Internal RGBA buffer mismatch: expected {expected_values}, got {len(pixels)}")
        image = bpy.data.images.get(image_name)
        if image is not None:
            _log(
                f"Existing output image '{image.name}': {image.size[0]}x{image.size[1]}, "
                f"channels={image.channels}, pixel values={len(image.pixels)}"
            )
            if image.size[0] != settings.width or image.size[1] != settings.height:
                _log(f"Resizing output image to {settings.width}x{settings.height}")
                image.scale(settings.width, settings.height)
            if image.channels != 4 or len(image.pixels) != expected_values:
                _log("Existing output buffer remained incompatible; recreating the image datablock")
                bpy.data.images.remove(image)
                image = None
        if image is None:
            _log(f"Creating RGBA output image '{image_name}' at {settings.width}x{settings.height}")
            image = bpy.data.images.new(image_name, width=settings.width, height=settings.height, alpha=True)
        actual_values = len(image.pixels)
        _log(
            f"Output buffer ready: {image.size[0]}x{image.size[1]}, channels={image.channels}, "
            f"expected values={expected_values}, actual values={actual_values}"
        )
        if image.channels != 4 or actual_values != expected_values:
            raise ValueError(
                f"Output image buffer is incompatible: expected {expected_values} RGBA values, "
                f"got {actual_values} values across {image.channels} channels"
            )
        image.colorspace_settings.name = 'sRGB'
        image.alpha_mode = 'STRAIGHT'
        image.pixels.foreach_set(pixels)
        image.update()
        directory = bpy.path.abspath(settings.output_directory)
        if not directory:
            raise ValueError("Choose a valid output directory")
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
        image.filepath_raw = filepath
        image.file_format = 'PNG'
        _log(f"Saving PNG to '{filepath}'")
        image.save()
        return image, filepath


class ZENV_OT_TransitionSetSource(Operator):
    bl_idname = "zenv.transition_set_source"
    bl_label = "Set Active as Source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}
        context.scene.zenv_worldspace_transition.source = obj
        return {'FINISHED'}


class ZENV_OT_TransitionSetTarget(Operator):
    bl_idname = "zenv.transition_set_target"
    bl_label = "Set Active as Target"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}
        context.scene.zenv_worldspace_transition.target = obj
        return {'FINISHED'}


class ZENV_OT_BakeWorldspaceTransition(Operator):
    bl_idname = "zenv.bake_worldspace_transition"
    bl_label = "Bake Worldspace Transition"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "zenv_worldspace_transition", None)
        return settings and settings.source and settings.target

    def execute(self, context):
        settings = context.scene.zenv_worldspace_transition
        source_obj = settings.source
        target_obj = settings.target
        if source_obj == target_obj:
            self.report({'ERROR'}, "Source and target must be different objects")
            return {'CANCELLED'}
        source_surface = None
        target_surface = None
        stage = "initialization"
        context.window_manager.progress_begin(0, 1)
        try:
            _log(
                f"Bake started: source='{source_obj.name}', target='{target_obj.name}', "
                f"output={settings.width}x{settings.height}, max distance={settings.max_distance:g}"
            )
            _log("Source images will be resolved per face-assigned material")
            stage = "evaluated mesh creation"
            depsgraph = context.evaluated_depsgraph_get()
            source_surface = _MeshSurface(source_obj, depsgraph, "")
            target_surface = _MeshSurface(target_obj, depsgraph, "")
            _log(
                f"Meshes ready: source triangles={len(source_surface.triangles)}, "
                f"target triangles={len(target_surface.triangles)}, "
                f"source UV='{source_surface.uv_name}', target UV='{target_surface.uv_name}'"
            )
            stage = "RGBA buffer allocation"
            width = settings.width
            height = settings.height
            pixels = array('f', [0.0]) * (width * height * 4)
            _log(f"Allocated {len(pixels)} float values for {width}x{height} RGBA output")
            strengths = array('f', [-1.0]) * (width * height)
            owners = array('i', [-1]) * (width * height)
            samplers = {}
            sampled_pixels = 0
            overlap_conflicts = 0
            skipped_distance = 0
            total_candidates = 0
            triangles = target_surface.triangles
            context.window_manager.progress_end()
            context.window_manager.progress_begin(0, max(1, len(triangles)))
            stage = "target texel projection"
            for triangle_index, target_triangle in enumerate(triangles):
                context.window_manager.progress_update(triangle_index)
                uv0, uv1, uv2 = target_triangle['uv']
                raw_width = (max(uv0.x, uv1.x, uv2.x) - min(uv0.x, uv1.x, uv2.x)) * width
                raw_height = (max(uv0.y, uv1.y, uv2.y) - min(uv0.y, uv1.y, uv2.y)) * height
                if raw_width > width * 64 or raw_height > height * 64:
                    raise ValueError("A target UV triangle spans more than 64 tiles; normalize that UV island")
                min_x = math.floor(min(uv0.x, uv1.x, uv2.x) * width)
                max_x = math.ceil(max(uv0.x, uv1.x, uv2.x) * width)
                min_y = math.floor(min(uv0.y, uv1.y, uv2.y) * height)
                max_y = math.ceil(max(uv0.y, uv1.y, uv2.y) * height)
                world0, world1, world2 = target_triangle['world']
                for raw_y in range(min_y, max_y):
                    uv_y = (raw_y + 0.5) / height
                    for raw_x in range(min_x, max_x):
                        uv_point = Vector(((raw_x + 0.5) / width, uv_y))
                        weights = _TransitionUtils.barycentric_2d(uv_point, uv0, uv1, uv2)
                        if weights is None or min(weights) < -1.0e-7 or max(weights) > 1.0000001:
                            continue
                        total_candidates += 1
                        target_point = world0 * weights[0] + world1 * weights[1] + world2 * weights[2]
                        source_hit, source_normal, source_triangle_index, distance = source_surface.nearest(target_point)
                        if source_hit is None or distance > settings.max_distance:
                            skipped_distance += 1
                            continue
                        sample_hit = source_hit
                        sample_triangle_index = source_triangle_index
                        if settings.mirror_sampling and settings.mirror_scale > 0.0:
                            reflected = source_hit - (target_point - source_hit) * settings.mirror_scale
                            mirror_hit, mirror_normal, mirror_triangle_index, mirror_distance = source_surface.nearest(reflected)
                            if mirror_hit is not None:
                                sample_hit = mirror_hit
                                sample_triangle_index = mirror_triangle_index
                        source_triangle = source_surface.triangles[sample_triangle_index]
                        image, extension = _TransitionUtils.find_image_node(
                            source_obj,
                            source_triangle['material'],
                        )
                        if image is None:
                            raise ValueError("No source image texture was found for a sampled source material")
                        key = (image.as_pointer(), extension, settings.filtering)
                        sampler = samplers.get(key)
                        if sampler is None:
                            material_index = source_triangle['material']
                            material_name = "None"
                            if 0 <= material_index < len(source_obj.material_slots):
                                material = source_obj.material_slots[material_index].material
                                material_name = material.name if material else "None"
                            _log(
                                f"Loading source image '{image.name}' from assigned material slot "
                                f"{material_index} ('{material_name}'): {image.size[0]}x{image.size[1]}, "
                                f"channels={image.channels}, extension={extension}, filtering={settings.filtering}"
                            )
                            sampler = _ImageSampler(image, extension, settings.filtering)
                            samplers[key] = sampler
                        source_uv = _TransitionUtils.interpolated_uv(sample_hit, source_triangle)
                        color = sampler.sample(source_uv)
                        falloff = _TransitionUtils.smooth_falloff(distance, settings.max_distance, settings.falloff_power)
                        alpha = color[3] * falloff
                        x = raw_x % width
                        y = raw_y % height
                        pixel = y * width + x
                        if owners[pixel] != -1 and owners[pixel] != triangle_index:
                            overlap_conflicts += 1
                        if alpha <= strengths[pixel]:
                            continue
                        base = pixel * 4
                        pixels[base] = color[0]
                        pixels[base + 1] = color[1]
                        pixels[base + 2] = color[2]
                        pixels[base + 3] = alpha
                        if strengths[pixel] < 0.0:
                            sampled_pixels += 1
                        strengths[pixel] = alpha
                        owners[pixel] = triangle_index
            if sampled_pixels == 0:
                raise ValueError("No target texels were within the transition distance")
            _log(
                f"Projection complete: candidates={total_candidates:,}, sampled={sampled_pixels:,}, "
                f"outside distance={skipped_distance:,}, UV collisions={overlap_conflicts:,}"
            )
            if settings.margin:
                stage = "UV margin dilation"
                _log(f"Dilating output by {settings.margin} pixels")
                _TransitionUtils.dilate_pixels(pixels, width, height, settings.margin)
            stage = "output image creation"
            image, filepath = _TransitionUtils.create_output_image(settings, pixels, source_obj, target_obj)
            message = f"Saved {image.name} to {filepath}"
            _log(message)
            if settings.bidirectional:
                _log("Starting reverse bake pass")
                original_source = settings.source
                original_target = settings.target
                original_output_name = settings.output_name
                original_output_file = settings.output_file
                try:
                    settings.source = target_obj
                    settings.target = source_obj
                    settings.bidirectional = False
                    if not settings.auto_filename:
                        settings.output_name = original_output_name + "_reverse"
                        file_stem, file_extension = os.path.splitext(original_output_file)
                        settings.output_file = file_stem + "_reverse" + (file_extension or '.png')
                    reverse_status = bpy.ops.zenv.bake_worldspace_transition('EXEC_DEFAULT')
                finally:
                    settings.source = original_source
                    settings.target = original_target
                    settings.bidirectional = True
                    settings.output_name = original_output_name
                    settings.output_file = original_output_file
                if 'FINISHED' not in reverse_status:
                    self.report({'WARNING'}, "Forward complete; reverse pass failed")
                    return {'FINISHED'}
                self.report({'INFO'}, "Saved forward and reverse transition textures")
                return {'FINISHED'}
            if overlap_conflicts:
                self.report({'WARNING'}, message + "; wrapped/overlapping target UVs caused collisions")
            else:
                self.report({'INFO'}, message)
            return {'FINISHED'}
        except Exception as error:
            _log(f"ERROR during {stage}: {error}")
            traceback.print_exc()
            self.report({'ERROR'}, f"{stage}: {error}")
            return {'CANCELLED'}
        finally:
            context.window_manager.progress_end()
            if source_surface is not None:
                source_surface.free()
            if target_surface is not None:
                target_surface.free()


class ZENV_PT_WorldspaceTransition(Panel):
    bl_label = "TEX Worldspace Transition"
    bl_idname = "ZENV_PT_worldspace_transition"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.zenv_worldspace_transition
        box = layout.box()
        box.label(text="Meshes", icon='MESH_DATA')
        row = box.row(align=True)
        row.prop(settings, "source")
        row.operator("zenv.transition_set_source", text="", icon='EYEDROPPER')
        row = box.row(align=True)
        row.prop(settings, "target")
        row.operator("zenv.transition_set_target", text="", icon='EYEDROPPER')
        box = layout.box()
        box.label(text="Worldspace Projection", icon='MOD_SHRINKWRAP')
        box.prop(settings, "max_distance")
        box.prop(settings, "falloff_power")
        box.prop(settings, "mirror_sampling")
        if settings.mirror_sampling:
            box.prop(settings, "mirror_scale")
        box = layout.box()
        box.label(text="Output", icon='RENDER_RESULT')
        row = box.row(align=True)
        row.prop(settings, "width")
        row.prop(settings, "height")
        box.prop(settings, "margin")
        box.prop(settings, "bidirectional")
        box.prop(settings, "auto_filename")
        if settings.auto_filename:
            box.label(text="target_transition_source_YYYYMMDDhhmmss.png", icon='INFO')
        else:
            box.prop(settings, "output_name")
            box.prop(settings, "output_file")
        box.prop(settings, "output_directory")
        layout.operator("zenv.bake_worldspace_transition", icon='RENDER_STILL')


classes = (
    ZENV_PG_WorldspaceTransition,
    ZENV_OT_TransitionSetSource,
    ZENV_OT_TransitionSetTarget,
    ZENV_OT_BakeWorldspaceTransition,
    ZENV_PT_WorldspaceTransition,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_worldspace_transition = PointerProperty(type=ZENV_PG_WorldspaceTransition)


def unregister():
    if hasattr(bpy.types.Scene, "zenv_worldspace_transition"):
        del bpy.types.Scene.zenv_worldspace_transition
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
