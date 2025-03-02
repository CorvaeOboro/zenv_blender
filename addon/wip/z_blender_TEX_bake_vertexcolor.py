# VERTEX COLOR BAKING
# Bake vertex colors to texture maps and vice versa

bl_info = {
    "name": "TEX Vertex Color Baker",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Bake vertex colors to texture maps and vice versa",
}

import bpy
import os
import bmesh
import logging
from datetime import datetime
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_VertexBake_Properties:
    """Property management for vertex color baking addon"""
    
    @classmethod
    def register(cls):
        """Register all properties"""
        bpy.types.Scene.zenv_bake_resolution = IntProperty(
            name="Resolution",
            description="Texture resolution for baking",
            default=1024,
            min=64,
            max=8192
        )
        
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
        
        bpy.types.Scene.zenv_save_blend = BoolProperty(
            name="Save Blend",
            description="Save .blend file with baked texture",
            default=False
        )
        
        bpy.types.Scene.zenv_output_path = StringProperty(
            name="Output Path",
            description="Path for saving baked textures",
            default="//textures/",
            subtype='DIR_PATH'
        )
        
        bpy.types.Scene.zenv_unwrap_margin = FloatProperty(
            name="UV Margin",
            description="Margin between UV islands",
            default=0.001,
            min=0.0,
            max=1.0
        )
        
        bpy.types.Scene.zenv_auto_unwrap = BoolProperty(
            name="Auto Unwrap",
            description="Automatically unwrap if no UVs exist",
            default=True
        )
        
        bpy.types.Scene.zenv_use_vertex_color = EnumProperty(
            name="Vertex Color Layer",
            description="Which vertex color layer to bake",
            items=lambda self, context: cls.get_vertex_color_items(context),
            default=None
        )
        
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
        del bpy.types.Scene.zenv_bake_resolution
        del bpy.types.Scene.zenv_output_format
        del bpy.types.Scene.zenv_save_blend
        del bpy.types.Scene.zenv_output_path
        del bpy.types.Scene.zenv_unwrap_margin
        del bpy.types.Scene.zenv_auto_unwrap
        del bpy.types.Scene.zenv_use_vertex_color
        del bpy.types.Scene.zenv_texture_path

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_VertexBake_Utils:
    """Utility functions for vertex color baking"""
    
    @staticmethod
    def ensure_output_directory(context):
        """Ensure output directory exists"""
        output_path = bpy.path.abspath(context.scene.zenv_output_path)
        os.makedirs(output_path, exist_ok=True)
        return output_path
    
    @staticmethod
    def generate_texture_name(obj_name):
        """Generate unique texture filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{obj_name}_vcol_{timestamp}"
    
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
            tex_image.select = True
            nodes.active = tex_image
    
    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking"""
        context.scene.render.engine = 'CYCLES'
        context.scene.cycles.device = 'CPU'
        context.scene.render.bake.use_selected_to_active = False
        context.scene.render.bake.use_clear = True
        context.scene.render.bake.margin = 4
    
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

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_VertexBake_BakeTexture(bpy.types.Operator):
    """Bake vertex colors to texture"""
    bl_idname = "zenv.vertexbake_bake"
    bl_label = "Bake Vertex Colors"
    bl_description = "Bake vertex colors to texture map"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and 
                obj.data.vertex_colors.active and
                context.scene.zenv_use_vertex_color != 'None')
    
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
            image_path = os.path.join(output_dir, f"{texture_name}.{context.scene.zenv_output_format.lower()}")
            
            # Create image for baking
            image = bpy.data.images.new(
                texture_name,
                context.scene.zenv_bake_resolution,
                context.scene.zenv_bake_resolution
            )
            image.filepath_raw = image_path
            image.file_format = context.scene.zenv_output_format
            
            # Setup material
            if not obj.data.materials:
                mat = bpy.data.materials.new(name=f"{obj.name}_vcol_material")
                obj.data.materials.append(mat)
            else:
                mat = obj.data.materials[0]
            
            # Setup nodes with selected vertex color layer
            ZENV_VertexBake_Utils.setup_material_nodes(
                mat, 
                image, 
                context.scene.zenv_use_vertex_color
            )
            ZENV_VertexBake_Utils.setup_render_settings(context)
            
            # Save blend file if requested
            if context.scene.zenv_save_blend:
                blend_path = os.path.join(output_dir, f"{texture_name}.blend")
                bpy.ops.wm.save_as_mainfile(filepath=blend_path)
            
            # Perform baking
            bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_selected_to_active=False
            )
            
            # Save image
            image.save_render(filepath=image_path)
            
            self.report({'INFO'}, f"Baked texture saved to: {image_path}")
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Error during baking: {str(e)}")
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}

class ZENV_OT_VertexBake_SetFromTexture(bpy.types.Operator):
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
            
            # Create new vertex color layer if needed
            if not obj.data.vertex_colors:
                vcol = obj.data.vertex_colors.new()
            else:
                vcol = obj.data.vertex_colors.active
            
            # Create temporary material for texture lookup
            temp_mat = bpy.data.materials.new(name="__temp_vcol_material")
            temp_mat.use_nodes = True
            nodes = temp_mat.node_tree.nodes
            nodes.clear()
            
            # Setup nodes for texture lookup
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.image = image
            
            # Get mesh data
            mesh = obj.data
            
            # Get active UV layer
            uv_layer = mesh.uv_layers.active.data
            
            # For each polygon
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    # Get UV coordinates
                    uv = uv_layer[loop_idx].uv
                    # Sample color from texture
                    color = tex_image.image.pixels[
                        int(uv.x * image.size[0]) * 4:
                        int(uv.x * image.size[0]) * 4 + 4
                    ]
                    # Set vertex color
                    vcol.data[loop_idx].color = color
            
            # Cleanup
            bpy.data.materials.remove(temp_mat)
            bpy.data.images.remove(image)
            
            self.report({'INFO'}, "Vertex colors set from texture")
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Error setting vertex colors: {str(e)}")
            self.report({'ERROR'}, f"Failed to set vertex colors: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_VertexBake_Panel(bpy.types.Panel):
    """Panel for vertex color baking tools"""
    bl_label = "TEX Vertex Color Baker"
    bl_idname = "ZENV_PT_vertexbake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
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

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_VertexBake_BakeTexture,
    ZENV_OT_VertexBake_SetFromTexture,
    ZENV_PT_VertexBake_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_VertexBake_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_VertexBake_Properties.unregister()

if __name__ == "__main__":
    register()