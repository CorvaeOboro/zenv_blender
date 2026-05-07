bl_info = {
    "name": 'RENDER Unlit Color',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260418',
    "description": 'Renders unlit texture images with datetime suffix',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Render',
    "group_prefix": 'RENDER',
    "description_short": 'quick renders color unlit image with datetime suffix',
    "description_long": """
RENDER Unlit Color
 render unlit basecolor images from camera
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_RenderColorOnly(bpy.types.Operator):
    """Operator for rendering unlit color images"""
    bl_idname = "zenv.render_color_datetime"
    bl_label = "Render Unlit Color"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Subset of EEVEE attributes that we may disable to get a flat unlit
    # render. Each one is guarded because Blender 4.2+ removed
    # ``use_bloom`` / ``use_ssr`` entirely.
    _EEVEE_FLAGS = ('use_gtao', 'use_bloom', 'use_ssr')

    @staticmethod
    def _resolve_eevee_engine():
        """Return the EEVEE engine id available in this Blender build.

        Blender 4.2 renamed ``BLENDER_EEVEE`` to ``BLENDER_EEVEE_NEXT``.
        Fall back to whatever id is present in the enum.
        """
        try:
            enum_items = bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
            ids = {item.identifier for item in enum_items}
        except Exception:
            ids = set()
        for candidate in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
            if candidate in ids:
                return candidate
        # Last resort: keep whatever the scene already has.
        return None

    def execute(self, context):
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera found.")
            return {'CANCELLED'}

        original_state = self.store_original_render_state(context)
        original_materials = self.store_original_materials()

        try:
            # Setup rendering
            self.setup_rendering(context)

            # Create temporary materials
            self.setup_flat_color_rendering(context)

            # Render and save
            render_filepath = self.render_color_image(context)

            if render_filepath:
                self.report({'INFO'}, f"Rendered: {render_filepath}")
                return {'FINISHED'}
            return {'CANCELLED'}

        except Exception as e:
            logger.error(f"Unlit color rendering failed: {str(e)}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        finally:
            # Always restore the scene, even if rendering failed.
            self.restore_original_render_state(context, original_state)
            self.restore_materials(original_materials)

    def store_original_render_state(self, context):
        """Capture every render setting we are going to modify."""
        scene = context.scene
        render = scene.render
        state = {
            'engine': render.engine,
            'file_format': render.image_settings.file_format,
            'color_mode': render.image_settings.color_mode,
            'filepath': render.filepath,
            'view_transform': scene.view_settings.view_transform,
        }
        eevee = getattr(scene, 'eevee', None)
        if eevee is not None:
            for flag in self._EEVEE_FLAGS:
                if hasattr(eevee, flag):
                    state[f'eevee.{flag}'] = getattr(eevee, flag)
        return state

    def restore_original_render_state(self, context, state):
        """Restore whatever was captured by ``store_original_render_state``."""
        scene = context.scene
        render = scene.render
        render.engine = state['engine']
        render.image_settings.file_format = state['file_format']
        render.image_settings.color_mode = state['color_mode']
        render.filepath = state['filepath']
        scene.view_settings.view_transform = state['view_transform']
        eevee = getattr(scene, 'eevee', None)
        if eevee is not None:
            for flag in self._EEVEE_FLAGS:
                key = f'eevee.{flag}'
                if key in state and hasattr(eevee, flag):
                    setattr(eevee, flag, state[key])

    def store_original_materials(self):
        """Snapshot per-slot material assignments for every mesh object.

        Keys are the objects themselves (not their names) so an object
        rename between store and restore no longer silently drops the
        mapping. Stale references are filtered during restore.
        """
        original_materials = {}
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                original_materials[obj] = [slot.material for slot in obj.material_slots]
        return original_materials

    def restore_materials(self, original_materials):
        """Restore original material assignments captured by ``store_original_materials``."""
        for obj, materials in original_materials.items():
            try:
                if obj is None or obj.type != 'MESH':
                    continue
            except ReferenceError:
                # Object was deleted between store and restore.
                continue
            for i, material in enumerate(materials):
                if i < len(obj.material_slots):
                    obj.material_slots[i].material = material

    def setup_rendering(self, context):
        """Setup render settings for unlit color"""
        engine_id = self._resolve_eevee_engine()
        if engine_id is not None:
            context.scene.render.engine = engine_id
        context.scene.render.image_settings.file_format = 'PNG'
        context.scene.render.image_settings.color_mode = 'RGB'

        # Set color management to Standard for exact texture colors (no color transform)
        context.scene.view_settings.view_transform = 'Standard'

        # Disable unnecessary effects, tolerating Blender versions that
        # have removed some of these attributes (notably 4.2+).
        eevee = getattr(context.scene, 'eevee', None)
        if eevee is not None:
            for flag in self._EEVEE_FLAGS:
                if hasattr(eevee, flag):
                    setattr(eevee, flag, False)

    def setup_flat_color_rendering(self, context):
        """Create and assign temporary materials for unlit color rendering"""
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for slot in obj.material_slots:
                    original_mat = slot.material
                    if original_mat and original_mat.use_nodes:
                        # Create temporary material
                        temp_mat = bpy.data.materials.new(name=f"Temp_{original_mat.name}")
                        temp_mat.use_nodes = True
                        nodes = temp_mat.node_tree.nodes
                        nodes.clear()

                        # Create emission shader for unlit rendering
                        emission = nodes.new('ShaderNodeEmission')
                        output = nodes.new('ShaderNodeOutputMaterial')
                        
                        # Find and use image texture from original material
                        image_texture = None
                        for node in original_mat.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                image_texture = nodes.new('ShaderNodeTexImage')
                                image_texture.image = node.image
                                # Copy texture node settings
                                image_texture.extension = node.extension
                                image_texture.interpolation = node.interpolation
                                image_texture.projection = node.projection
                                break
                        
                        # Link nodes
                        if image_texture:
                            temp_mat.node_tree.links.new(image_texture.outputs['Color'], emission.inputs['Color'])
                        emission.inputs['Strength'].default_value = 1.0
                        temp_mat.node_tree.links.new(emission.outputs[0], output.inputs[0])
                        
                        # Position nodes
                        if image_texture:
                            image_texture.location = (-300, 0)
                        emission.location = (0, 0)
                        output.location = (300, 0)
                        
                        # Assign temporary material
                        slot.material = temp_mat

    def render_color_image(self, context):
        """Render and save the color image"""
        # Get current blend file path and name
        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            self.report({'ERROR'}, "Blender file not saved yet, no name to use, defaulting to 00_texture")
            blend_filepath = "00_texture"
            
        # Extract blend file name without extension
        blend_filename = os.path.splitext(os.path.basename(blend_filepath))[0]
        
        # Create datetime suffix
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Setup output path using blend file name for both folder and file
        output_folder = os.path.join(os.path.dirname(blend_filepath), blend_filename)
        os.makedirs(output_folder, exist_ok=True)
        
        # Set render path with blend filename included
        render_filepath = os.path.join(output_folder, f"{blend_filename}_color_{datetime_str}.png")
        # Convert to absolute path for display
        render_filepath = os.path.abspath(render_filepath)
        context.scene.render.filepath = render_filepath
        
        # Render
        bpy.ops.render.render(write_still=True)
        
        if not os.path.exists(render_filepath):
            raise Exception("Failed to save rendered color image")
            
        return render_filepath

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RenderColor_Panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for unlit color rendering"""
    bl_label = "RENDER Unlit Color"
    bl_idname = "ZENV_PT_render_color"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.render_color_datetime")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PT_RenderColor_Panel,
    ZENV_OT_RenderColorOnly,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
