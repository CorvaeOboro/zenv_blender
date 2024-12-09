bl_info = {
    "name": "Random Tiles by Textures",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),  # Update as needed
    "location": "View3D > Sidebar > Random Tiles by Textures",
    "description": "Create a grid of planes with random textures",
    "category": "Object",
}

import bpy
import random
import os
from bpy.props import StringProperty, CollectionProperty
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper

class OT_CreateRandomTiles(Operator, ImportHelper):
    bl_idname = "object.create_random_tiles"
    bl_label = "Create Random Tiles"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(
        default='*.png;*.jpg;*.jpeg;*.tga;*.bmp',
        options={'HIDDEN'}
    )

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')

    def execute(self, context):
        textures = [os.path.join(self.directory, f.name) for f in self.files]
        if not textures:
            self.report({'ERROR'}, "No textures selected")
            return {'CANCELLED'}
        # Proceed to create materials and grid
        create_random_tiles(context, textures)
        return {'FINISHED'}

def create_material_from_texture(texture_path):
    import bpy
    import os

    mat_name = os.path.splitext(os.path.basename(texture_path))[0] + "_MI"
    if mat_name in bpy.data.materials:
        mat = bpy.data.materials[mat_name]
    else:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        tex_image = mat.node_tree.nodes.new('ShaderNodeTexImage')
        try:
            tex_image.image = bpy.data.images.load(texture_path)
        except:
            print("Cannot load image %s" % texture_path)
            return None
        mat.node_tree.links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
    return mat

def create_plane_at(i, j, materials):
    import bpy
    import random
    bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=False, location=(i, j, 0))
    obj = bpy.context.active_object
    mat = random.choice(materials)
    if mat is None:
        return
    if obj.data.materials:
        # assign to 1st material slot
        obj.data.materials[0] = mat
    else:
        # no slots
        obj.data.materials.append(mat)

def create_random_tiles(context, texture_paths):
    materials = []
    for texture_path in texture_paths:
        mat = create_material_from_texture(texture_path)
        if mat:
            materials.append(mat)
    if not materials:
        print("No materials created")
        return
    # Create grid of planes
    for i in range(20):
        for j in range(20):
            create_plane_at(i, j, materials)

class RandomTilesPanel(Panel):
    bl_label = "ZENV"
    bl_idname = "VIEW3D_PT_random_tiles"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Random Tiles by Textures'  # This creates the tab

    def draw(self, context):
        layout = self.layout
        layout.operator("object.create_random_tiles", text="Create Random Tiles")

def register():
    bpy.utils.register_class(OT_CreateRandomTiles)
    bpy.utils.register_class(RandomTilesPanel)

def unregister():
    bpy.utils.unregister_class(OT_CreateRandomTiles)
    bpy.utils.unregister_class(RandomTilesPanel)

if __name__ == "__main__":
    register()
