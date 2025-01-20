# RENDER Unlit Color
# render unlit basecolor images from camera 

bl_info = {
    "name": "RENDER Unlit Color",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Renders unlit texture images with datetime suffix",
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
    
    def execute(self, context):
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera found.")
            return {'CANCELLED'}
            
        try:
            # Store original render settings
            original_engine = context.scene.render.engine
            original_materials = self.store_original_materials()
            
            # Setup rendering
            self.setup_rendering(context)
            
            # Create temporary materials
            self.setup_flat_color_rendering(context)
            
            # Render and save
            success = self.render_color_image(context)
            
            # Restore original settings and materials
            context.scene.render.engine = original_engine
            self.restore_materials(original_materials)
            
            if success:
                self.report({'INFO'}, "Unlit color image rendered successfully")
                return {'FINISHED'}
            return {'CANCELLED'}
            
        except Exception as e:
            logger.error(f"Unlit color rendering failed: {str(e)}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def store_original_materials(self):
        """Store original material assignments"""
        original_materials = {}
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                original_materials[obj.name] = [slot.material for slot in obj.material_slots]
        return original_materials

    def restore_materials(self, original_materials):
        """Restore original material assignments"""
        for obj_name, materials in original_materials.items():
            obj = bpy.data.objects.get(obj_name)
            if obj and obj.type == 'MESH':
                for i, material in enumerate(materials):
                    if i < len(obj.material_slots):
                        obj.material_slots[i].material = material

    def setup_rendering(self, context):
        """Setup render settings for unlit color"""
        context.scene.render.engine = 'BLENDER_EEVEE'
        context.scene.render.image_settings.file_format = 'PNG'
        context.scene.render.image_settings.color_mode = 'RGB'
        
        # Disable unnecessary effects
        context.scene.eevee.use_gtao = False
        context.scene.eevee.use_bloom = False
        context.scene.eevee.use_ssr = False

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
        context.scene.render.filepath = render_filepath
        
        # Render
        bpy.ops.render.render(write_still=True)
        
        if not os.path.exists(render_filepath):
            raise Exception("Failed to save rendered color image")
            
        return True

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RenderColorOnly(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport for unlit color rendering"""
    bl_label = "Render Unlit Color"
    bl_idname = "ZENV_PT_RenderColor"
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
    ZENV_PT_RenderColorOnly,
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
