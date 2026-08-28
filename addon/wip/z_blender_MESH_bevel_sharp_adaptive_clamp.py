#region blinfo
bl_info = {
    "name": 'MESH Bevel Sharp Adaptive Clamp',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Add adaptive bevels to sharp edges with dynamic overlap prevention',
    "status": 'wip',
    "approved": False,
    "group": 'Mesh',
    "group_prefix": 'MESH',
    "group_order": 50,
    "addon_order": 60,
    "location": 'View3D > ZENV',
    "tags": ['mesh', 'bevel', 'sharp', 'adaptive', 'clamp'],
    "description_short": 'Add adaptive bevels to sharp edges with overlap prevention.',
    "description_medium": 'Detects sharp edges by angle threshold and applies bevels with '
                          'Blender\'s clamp_overlap to prevent overlapping geometry.',
    "description_long": 'MESH Bevel Sharp Adaptive Clamp creates clean, non-overlapping '
                        'bevels by detecting edge intersections and adaptively adjusting '
                        'bevel widths. Uses angle-based sharp edge detection and Blender\'s '
                        'built-in clamp_overlap for efficient, correct results.',
    "image_overview": '',
    "addon_image": '',
    "warning": '',
    "doc_url": '',
}
#endregion

#region imports
import bpy
import bmesh
import math
import logging
from mathutils import Vector
from bpy.props import FloatProperty, BoolProperty, IntProperty, EnumProperty, PointerProperty
from bpy.types import PropertyGroup, Operator, Panel
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
    _log_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)


def _uninstall_logger():
    """Remove the stream handler from the module logger (idempotent)."""
    global _log_handler
    if _log_handler is not None:
        logger.removeHandler(_log_handler)
        _log_handler = None
#endregion

#region ops
# Operator - detect sharp edges by angle and bevel them with clamp_overlap

#region ops-edgehelpers
# Edge helpers - angle between faces and edge midpoint
class ZENV_OT_BevelSharpAdaptiveClamp(Operator):
    """Add adaptive bevels to sharp edges with dynamic overlap prevention"""
    bl_idname = "zenv.bevel_sharp_adaptive_clamp"
    bl_label = "Bevel Sharp Adaptive Clamp"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    def get_edge_angle(self, edge):
        """Get angle between faces connected to edge.

        Returns 180 deg for non-manifold edges (0 or 3+ linked faces)
        so they are always treated as sharp.
        """
        if len(edge.link_faces) != 2:
            return 180.0

        vec1 = edge.link_faces[0].normal
        vec2 = edge.link_faces[1].normal
        angle = vec1.angle(vec2)
        return math.degrees(angle)

    def get_edge_midpoint(self, edge):
        """Get the midpoint of an edge"""
        return (edge.verts[0].co + edge.verts[1].co) / 2
#endregion

    #region ops-execute
    # Execute - build BMesh, find sharp edges, bevel with clamp, restore mode
    def execute(self, context):
        props = context.scene.zenv_bevel_sharp_adaptive_clamp_props
        active_obj = context.active_object

        if not active_obj or active_obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Store current mode for restoration in finally
        original_mode = active_obj.mode
        bm = None

        try:
            bpy.ops.object.mode_set(mode='OBJECT')

            # Create BMesh
            bm = bmesh.new()
            bm.from_mesh(active_obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            # Find sharp edges by angle threshold
            sharp_edges = []
            for edge in bm.edges:
                angle = self.get_edge_angle(edge)
                if angle > props.sharp_angle:
                    sharp_edges.append(edge)

            if not sharp_edges:
                self.report({'INFO'}, "No sharp edges found")
                return {'CANCELLED'}

            logger.info(f"Found {len(sharp_edges)} sharp edges (threshold {props.sharp_angle} deg)")

            # Single batch bevel with built-in overlap clamping.
            # This replaces the per-edge overlap detection and sequential
            # beveling with Blender's clamp_overlap.
            bmesh.ops.bevel(
                bm,
                geom=sharp_edges,
                offset=props.max_bevel_width,
                offset_type='WIDTH',
                segments=props.segments,
                profile=0.5,
                affect='EDGES',
                clamp_overlap=True,
            )

            # Final cleanup
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

            # Update mesh
            bm.to_mesh(active_obj.data)
            active_obj.data.update()
            bm.free()
            bm = None  # mark as freed so finally doesn't double-free

            self.report({'INFO'}, f"Applied adaptive bevel to {len(sharp_edges)} edges")
            logger.info(f"Applied adaptive bevel to {len(sharp_edges)} edges")
            return {'FINISHED'}

        except Exception as e:
            logger.error(f"Bevel operation failed: {e}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        finally:
            # Free BMesh if still allocated
            if bm is not None:
                try:
                    bm.free()
                except Exception:
                    pass
            # Restore original mode
            try:
                bpy.ops.object.mode_set(mode=original_mode)
            except Exception:
                pass
    #endregion
#endregion

#region props
# Property group - sharp angle threshold, bevel width range, segment count
class ZENV_PG_BevelSharpAdaptiveClamp(PropertyGroup):
    """Property group for adaptive bevel settings with angle-based clamping"""
    sharp_angle: FloatProperty(
        name="Sharp Angle",
        description="Angle threshold for sharp edges (degrees)",
        default=60.0,
        min=0.0,
        max=180.0
    )
    max_bevel_width: FloatProperty(
        name="Max Bevel Width",
        description="Maximum bevel width",
        default=1.0,
        min=0.0001,
        max=10.0
    )
    min_bevel_width: FloatProperty(
        name="Min Bevel Width",
        description="Minimum allowed bevel width",
        default=0.001,
        min=0.0001,
        max=0.1
    )
    segments: IntProperty(
        name="Segments",
        description="Number of bevel segments",
        default=1,
        min=1,
        max=10
    )
#endregion

#region panel
# View3D panel UI - bevel settings and apply button
class ZENV_PT_BevelSharpAdaptiveClamp(Panel):
    """Panel for controlling adaptive bevel settings with angle-based clamping for sharp edges"""
    bl_label = "MESH Bevel Sharp Adaptive"
    bl_idname = "ZENV_PT_bevel_sharp_adaptive_clamp"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_bevel_sharp_adaptive_clamp_props

        col = layout.column(align=True)
        col.prop(props, "sharp_angle")
        col.prop(props, "max_bevel_width")
        col.prop(props, "min_bevel_width")
        col.prop(props, "segments")

        layout.operator("zenv.bevel_sharp_adaptive_clamp")
#endregion

#region register
# Class registration and module load / unload
classes = (
    ZENV_PG_BevelSharpAdaptiveClamp,
    ZENV_OT_BevelSharpAdaptiveClamp,
    ZENV_PT_BevelSharpAdaptiveClamp
)

def register():
    _install_logger()
    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except ValueError:
            pass  # Already registered
    if not hasattr(bpy.types.Scene, "zenv_bevel_sharp_adaptive_clamp_props"):
        bpy.types.Scene.zenv_bevel_sharp_adaptive_clamp_props = PointerProperty(type=ZENV_PG_BevelSharpAdaptiveClamp)

def unregister():
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass  # Already unregistered
    if hasattr(bpy.types.Scene, "zenv_bevel_sharp_adaptive_clamp_props"):
        delattr(bpy.types.Scene, "zenv_bevel_sharp_adaptive_clamp_props")
    _uninstall_logger()

if __name__ == "__main__":
    register()
#endregion
