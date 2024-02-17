
bl_info = {
    "name": "TEX Quick Texture Viewer",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": "Quickly view texture variants on a Blender model"
}

import bpy
import os
from bpy.props import StringProperty, PointerProperty, IntProperty
from bpy.types import PropertyGroup, Panel, Operator
import shutil


class QuickTextureViewerProperties(PropertyGroup):
    folder_path: StringProperty(
        name="Folder Path",
        description="Folder containing texture images",
        subtype='DIR_PATH'
    )
    texture_files: StringProperty(
        name="Texture Files",
        description="List of texture files",
        default=""
    )
    material_index: IntProperty(
        name="Material Index",
        description="Index of the current texture",
        default=0
    )

def load_textures(self, context):
    folder_path = context.scene.quick_texture_viewer.folder_path
    qtvp = context.scene.quick_texture_viewer
    qtvp.texture_files = ""
    qtvp.material_index = 0

    if folder_path:
        image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        qtvp.texture_files = '|'.join(image_files)

    # Store original texture
    obj = context.active_object
    if obj.material_slots and obj.material_slots[0].material and obj.material_slots[0].material.use_nodes:
        bsdf = obj.material_slots[0].material.node_tree.nodes.get('Principled BSDF')
        if bsdf and bsdf.inputs['Base Color'].links:
            img_tex_node = bsdf.inputs['Base Color'].links[0].from_node
            if img_tex_node and img_tex_node.type == 'TEX_IMAGE' and img_tex_node.image:
                original_texture_path = bpy.path.abspath(img_tex_node.image.filepath)
                qtvp.texture_files = original_texture_path + '|' + qtvp.texture_files

    return {'FINISHED'}

def assign_texture(context):
    scene = context.scene
    qtvp = scene.quick_texture_viewer
    obj = context.active_object

    if qtvp.texture_files and obj.material_slots and obj.material_slots[0].material:
        textures = qtvp.texture_files.split('|')
        current_texture = textures[qtvp.material_index]

        mat = obj.material_slots[0].material
        if mat.use_nodes:
            bsdf = mat.node_tree.nodes.get('Principled BSDF')
            if bsdf:
                if 'Image Texture' not in mat.node_tree.nodes:
                    img_tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                else:
                    img_tex_node = mat.node_tree.nodes['Image Texture']
                img_tex_node.image = bpy.data.images.load(current_texture)
                mat.node_tree.links.new(bsdf.inputs['Base Color'], img_tex_node.outputs['Color'])

                # Force redraw of viewport
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)



def cycle_texture(context, direction):
    scene = context.scene
    qtvp = scene.quick_texture_viewer

    if qtvp.texture_files:
        textures = qtvp.texture_files.split('|')
        num_textures = len(textures)
        if direction == 'NEXT':
            qtvp.material_index = (qtvp.material_index + 1) % num_textures
        elif direction == 'PREVIOUS':
            qtvp.material_index = (qtvp.material_index - 1) % num_textures
        assign_texture(context)

class QuickTextureLoadOperator(Operator):
    bl_idname = "quick_texture.load_textures"
    bl_label = "Load Textures"
    bl_description = "Load textures from the specified folder"

    def execute(self, context):
        load_textures(self, context)
        return {'FINISHED'}

class QuickTextureCopyPathOperator(Operator):
    bl_idname = "quick_texture.copy_path"
    bl_label = "Copy Texture Path"
    bl_description = "Copy the file path of the current texture to the clipboard"

    def execute(self, context):
        qtvp = context.scene.quick_texture_viewer
        textures = qtvp.texture_files.split('|')
        current_texture = textures[qtvp.material_index]
        context.window_manager.clipboard = current_texture
        self.report({'INFO'}, "Texture path copied to clipboard")
        return {'FINISHED'}

class QuickTextureCyclePreviousOperator(Operator):
    bl_idname = "quick_texture.cycle_previous"
    bl_label = "Previous Texture"
    bl_description = "Cycle to the previous texture"

    def execute(self, context):
        cycle_texture(context, 'PREVIOUS')
        return {'FINISHED'}

class QuickTextureCycleNextOperator(Operator):
    bl_idname = "quick_texture.cycle_next"
    bl_label = "Next Texture"
    bl_description = "Cycle to the next texture"

    def execute(self, context):
        cycle_texture(context, 'NEXT')
        return {'FINISHED'}

# New operator to copy the current texture to a subfolder
class QuickTextureCopyToSubfolderOperator(bpy.types.Operator):
    bl_idname = "quick_texture.copy_to_subfolder"
    bl_label = "Copy to Subfolder"

    def execute(self, context):
        scene = context.scene
        qtvp = scene.quick_texture_viewer

        if qtvp.texture_files and qtvp.material_index >= 0:
            textures = qtvp.texture_files.split('|')
            current_texture_path = textures[qtvp.material_index]

            target_folder = bpy.path.abspath(qtvp.folder_path)
            subfolder_path = os.path.join(target_folder, "01")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)
            shutil.copyfile(current_texture_path, new_texture_path)

            self.report({'INFO'}, f"Texture copied to {new_texture_path}")
        else:
            self.report({'WARNING'}, "No texture selected or path invalid.")

        return {'FINISHED'}

# New operator to move the current texture to a subfolder
class QuickTextureMoveToSubfolderOperator(bpy.types.Operator):
    bl_idname = "quick_texture.move_to_subfolder"
    bl_label = "Move to Subfolder"

    def execute(self, context):
        scene = context.scene
        qtvp = scene.quick_texture_viewer

        if qtvp.texture_files and qtvp.material_index >= 0:
            textures = qtvp.texture_files.split('|')
            current_texture_path = textures[qtvp.material_index]

            target_folder = bpy.path.abspath(qtvp.folder_path)
            subfolder_path = os.path.join(target_folder, "02")
            os.makedirs(subfolder_path, exist_ok=True)

            texture_name = os.path.basename(current_texture_path)
            new_texture_path = os.path.join(subfolder_path, texture_name)

            # Move the file
            shutil.move(current_texture_path, new_texture_path)

            # Update the texture list
            textures[qtvp.material_index] = new_texture_path
            qtvp.texture_files = '|'.join(textures)

            self.report({'INFO'}, f"Texture moved to {new_texture_path}")
        else:
            self.report({'WARNING'}, "No texture selected or path invalid.")

        return {'FINISHED'}


class QuickTextureViewerPanel(bpy.types.Panel):
    bl_label = "Quick Texture Viewer"
    bl_idname = "MATERIAL_PT_QuickTextureViewer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quick Texture Viewer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        qtvp = scene.quick_texture_viewer

        layout.prop(qtvp, "folder_path")
        layout.operator("quick_texture.load_textures", icon='FILE_REFRESH', text="Load Textures")
        layout.operator("quick_texture.copy_to_subfolder", icon='DUPLICATE', text="Copy to Subfolder 01")
        layout.operator("quick_texture.move_to_subfolder", icon='FORWARD', text="Move to Subfolder 02")


        if qtvp.texture_files:
            textures = qtvp.texture_files.split('|')
            current_texture = textures[qtvp.material_index]
            layout.label(text=f"Current Texture: {current_texture}")
            row = layout.row(align=True)
            row.operator("quick_texture.cycle_previous", icon='TRIA_LEFT', text="Previous")
            row.operator("quick_texture.cycle_next", icon='TRIA_RIGHT', text="Next")
            layout.operator("quick_texture.copy_path", icon='COPYDOWN', text="Copy Path")

def register():
    bpy.utils.register_class(QuickTextureViewerProperties)
    bpy.types.Scene.quick_texture_viewer = PointerProperty(type=QuickTextureViewerProperties)
    bpy.utils.register_class(QuickTextureViewerPanel)
    bpy.utils.register_class(QuickTextureLoadOperator)
    bpy.utils.register_class(QuickTextureCyclePreviousOperator)
    bpy.utils.register_class(QuickTextureCycleNextOperator)
    bpy.utils.register_class(QuickTextureCopyPathOperator)
    bpy.utils.register_class(QuickTextureCopyToSubfolderOperator)
    bpy.utils.register_class(QuickTextureMoveToSubfolderOperator)

def unregister():
    bpy.utils.unregister_class(QuickTextureViewerProperties)
    del bpy.types.Scene.quick_texture_viewer
    bpy.utils.unregister_class(QuickTextureViewerPanel)
    bpy.utils.unregister_class(QuickTextureLoadOperator)
    bpy.utils.unregister_class(QuickTextureCyclePreviousOperator)
    bpy.utils.unregister_class(QuickTextureCycleNextOperator)
    bpy.utils.unregister_class(QuickTextureCopyPathOperator)
    bpy.utils.unregister_class(QuickTextureCopyToSubfolderOperator)
    bpy.utils.unregister_class(QuickTextureMoveToSubfolderOperator)

if __name__ == "__main__":
    register()
