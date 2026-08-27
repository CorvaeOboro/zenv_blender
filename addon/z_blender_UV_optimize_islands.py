#region META
bl_info = {
    "name": 'UV Optimize Islands',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260823',
    "description": 'Move UV islands closer to origin in whole-tile increments',
    "status": 'working',
    "approved": True,
    "group": 'UV',
    "group_prefix": 'UV',
    "group_order": 80,
    "addon_order": 20,
    "tags": ['uv', 'islands', 'optimize', 'texture'],
    "description_short": 'Snap UV islands toward origin',
    "description_medium": 'Optimize UV island positions by moving them closer to UV space origin (0,0) while maintaining texture mapping by moving in whole-number tile increments',
    "description_long": """\
UV Optimize Islands
 Move each UV island closer to the (0,0) origin by whole-number UV tile
 offsets so the texture sampling result is preserved.
 this is useful for texture baking UVs , and for game engine UV precision 
""",
    "location": 'View3D > ZENV',
    "image_overview": 'zenv_blender_UV_optimize_islands.png',
    "addon_image": 'zenv_blender_UV_optimize_islands.png',
}

#region IMPORT
import bpy
import bmesh
import math
import logging
from mathutils import Vector
from bpy.types import Operator, Panel
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)
_logger_handler = None

#endregion
#region UTILS
class ZENV_UVIslandOptimizer_Utils:
    """Static utilities for UV island detection and bounds math."""

    UV_EPSILON = 1e-4

    @staticmethod
    def get_uv_islands(bm: bmesh.types.BMesh, uv_layer) -> List[Set[bmesh.types.BMFace]]:
        """Group faces into UV islands by walking edges whose loops share UVs.

        Two faces sharing a topological edge are considered to be in the same
        island only if their UV loops along that edge coincide (within
        ``UV_EPSILON``); otherwise the edge is a UV seam.
        """
        bm.faces.ensure_lookup_table()
        remaining: Set[bmesh.types.BMFace] = set(bm.faces)
        islands: List[Set[bmesh.types.BMFace]] = []
        eps = ZENV_UVIslandOptimizer_Utils.UV_EPSILON

        while remaining:
            seed = remaining.pop()
            island: Set[bmesh.types.BMFace] = {seed}
            frontier: Set[bmesh.types.BMFace] = {seed}

            while frontier:
                face = frontier.pop()
                for edge in face.edges:
                    for link_face in edge.link_faces:
                        if link_face not in remaining:
                            continue
                        # Check if the two faces' UV loops along this edge coincide
                        shared_uvs = False
                        for loop in edge.link_loops:
                            if loop.face is not face:
                                continue
                            luv = loop[uv_layer].uv
                            for other_loop in edge.link_loops:
                                if other_loop.face is link_face:
                                    if (luv - other_loop[uv_layer].uv).length < eps:
                                        shared_uvs = True
                                        break
                            if shared_uvs:
                                break
                        if shared_uvs:
                            island.add(link_face)
                            frontier.add(link_face)
                            remaining.remove(link_face)

            islands.append(island)
            logger.debug("Found UV island with %d faces", len(island))

        return islands

    @staticmethod
    def get_island_bounds(island: Set[bmesh.types.BMFace], uv_layer) -> Tuple[float, float, float, float]:
        """Return ``(min_u, min_v, max_u, max_v)`` for the given island."""
        min_u = float('inf')
        min_v = float('inf')
        max_u = float('-inf')
        max_v = float('-inf')
        for face in island:
            for loop in face.loops:
                u, v = loop[uv_layer].uv
                if u < min_u: min_u = u
                if v < min_v: min_v = v
                if u > max_u: max_u = u
                if v > max_v: max_v = v
        return min_u, min_v, max_u, max_v

    @classmethod
    def get_island_center(cls, island: Set[bmesh.types.BMFace], uv_layer) -> Vector:
        """Return the center of an island's UV bounding box as a :class:`Vector`."""
        min_u, min_v, max_u, max_v = cls.get_island_bounds(island, uv_layer)
        return Vector(((min_u + max_u) * 0.5, (min_v + max_v) * 0.5))

#endregion
#region OP
class ZENV_OT_UVIslandOptimizer(Operator):
    """Move each UV island toward the (0,0) origin in whole-tile increments.

    The integer-offset move preserves texture sampling because the texture
    repeats per UV tile, so visual appearance does not change.
    """
    bl_idname = "zenv.uv_island_optimizer_optimize"
    bl_label = "Shift UV to 0-1 Range"
    bl_description = "Snap each UV island to the 0-1 UV range by whole-tile offsets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Please select a mesh object")
                return {'CANCELLED'}

            me = obj.data
            in_edit_mode = (obj.mode == 'EDIT')

            # Acquire bmesh: reuse the live edit-mode bmesh, or build one from the data.
            if in_edit_mode:
                bm = bmesh.from_edit_mesh(me)
            else:
                bm = bmesh.new()
                bm.from_mesh(me)

            try:
                if not bm.loops.layers.uv:
                    self.report({'ERROR'}, "Mesh has no UV layer")
                    return {'CANCELLED'}
                uv_layer = bm.loops.layers.uv.verify()

                islands = ZENV_UVIslandOptimizer_Utils.get_uv_islands(bm, uv_layer)
                logger.info("Optimizing %d UV islands location on '%s'", len(islands), obj.name)

                moved = 0
                for island in islands:
                    center = ZENV_UVIslandOptimizer_Utils.get_island_center(island, uv_layer)
                    offset = -Vector((math.floor(center.x), math.floor(center.y)))
                    if offset.length_squared == 0.0:
                        continue
                    for face in island:
                        for loop in face.loops:
                            loop[uv_layer].uv += offset
                    moved += 1

                if in_edit_mode:
                    bmesh.update_edit_mesh(me)
                else:
                    bm.to_mesh(me)
            finally:
                # Only free bmeshes we created ourselves; never free edit-mode bmesh.
                if not in_edit_mode:
                    bm.free()

            logger.info("UV optimize complete: %d/%d islands moved", moved, len(islands))
            self.report({'INFO'}, f"Shifted {moved}/{len(islands)} UV islands")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("UV optimize failed: %s", e)
            self.report({'ERROR'}, f"UV optimize failed: {e}")
            return {'CANCELLED'}

#endregion
#region PANEL
class ZENV_PT_UVIslandOptimizer(Panel):
    """Panel for UV island optimization."""
    bl_label = "UV Optimize Islands"
    bl_idname = "ZENV_PT_uv_island_optimizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.operator(ZENV_OT_UVIslandOptimizer.bl_idname, icon='UV_ISLANDSEL')

#endregion
#region REG
classes = (
    ZENV_OT_UVIslandOptimizer,
    ZENV_PT_UVIslandOptimizer,
)

def register():
    """Register all addon classes and configure the module logger handler."""
    global _logger_handler
    if _logger_handler is None:
        _logger_handler = logging.StreamHandler()
        _logger_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(_logger_handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    logger.info("UV Optimize Islands registered successfully")

def unregister():
    """Unregister all addon classes and remove the module logger handler."""
    global _logger_handler
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    logger.info("UV Optimize Islands unregistered")
    if _logger_handler is not None:
        try:
            logger.removeHandler(_logger_handler)
        except ValueError:
            pass
        _logger_handler = None

if __name__ == "__main__":
    register()
#endregion
