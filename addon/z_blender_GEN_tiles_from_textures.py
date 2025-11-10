bl_info = {
    "name": 'GEN random Tiles by Textures',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250302',
    "description": 'Create a grid of planes with random textures',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Generative',
    "group_prefix": 'GEN',
    "description_short": 'generate random tiles from texture set for tiling and seam blending review',
    "description_long": """
Generate Random Tiles from Textures - A Blender addon for texture visualization.

This addon creates a grid of planes with randomly assigned textures from a
selected folder. It's particularly useful for:
- Reviewing texture seams in a texture set
- Visualizing texture variations
- Testing material setups with different textures

consider rotation toggle and offset , the initial conditions of the texture tiles being laid out may have different system 
in isometric game likely the textures arent being rotated , but perhaps mirrored ? each of such transforms influences the texture's macro pattern for example a rotated set couldnt have a global diagonal direction lighting
""",
    "location": 'View3D > ZENV',
}

import bpy
import random
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import IntProperty, BoolProperty, PointerProperty
from bpy_extras.io_utils import ImportHelper

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_TileProperties(PropertyGroup):
    """Property group for tile generation settings."""
    grid_size: IntProperty(
        name="Grid Size",
        description="Number of rows and columns in the grid",
        default=10,
        min=1,
        max=100
    )
    random_rotation: BoolProperty(
        name="Random Rotation",
        description="Randomly rotate each tile",
        default=False
    )

# ------------------------------------------------------------------------
#    Operator
# ------------------------------------------------------------------------

class ZENV_OT_CreateRandomTiles(Operator, ImportHelper):
    """Create a grid of planes with random textures from a folder."""
    bl_idname = "zenv.create_random_tiles"
    bl_label = "Create Random Tiles"
    bl_options = {'REGISTER', 'UNDO'}

    # File browser properties
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.tga",
        options={'HIDDEN'}
    )
    files: bpy.props.CollectionProperty(
        type=bpy.types.OperatorFileListElement,
    )
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH'
    )

    @staticmethod
    def create_material_from_texture(texture_path):
        """Create a new material with the given texture."""
        # Get the texture name from the path
        texture_name = os.path.splitext(os.path.basename(texture_path))[0]
        
        # Create a new material
        material = bpy.data.materials.new(name=f"Material_{texture_name}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes
        principled_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        texture_node = nodes.new('ShaderNodeTexImage')
        output_node = nodes.new('ShaderNodeOutputMaterial')
        
        # Load and assign the image
        texture_node.image = bpy.data.images.load(texture_path)
        
        # Link nodes
        links = material.node_tree.links
        links.new(texture_node.outputs['Color'], 
                 principled_bsdf.inputs['Base Color'])
        links.new(principled_bsdf.outputs['BSDF'], 
                 output_node.inputs['Surface'])
        
        # Position nodes for better organization
        output_node.location = (300, 0)
        principled_bsdf.location = (0, 0)
        texture_node.location = (-300, 0)
        
        return material

    def create_plane(self, context, location, material):
        """Create a plane with the given material at the specified location."""
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            enter_editmode=False,
            align='WORLD',
            location=location
        )
        plane = bpy.context.active_object
        
        # Random rotation if enabled - use 90 degree increments
        if context.scene.zenv_tile_props.random_rotation:
            # Choose from 0, 90, 180, or 270 degrees (in radians)
            rotation = random.choice([0, 1.5708, 3.1416, 4.7124])
            plane.rotation_euler.z = rotation
        
        # Assign material
        if plane.data.materials:
            plane.data.materials[0] = material
        else:
            plane.data.materials.append(material)
            
        return plane

    def create_tile_grid(self, context, materials):
        """Create a grid of planes with random materials."""
        props = context.scene.zenv_tile_props
        grid_size = props.grid_size
        
        # Calculate grid dimensions
        total_width = grid_size
        start_x = -total_width / 2
        start_y = -total_width / 2
        
        # Create grid
        for row in range(grid_size):
            for col in range(grid_size):
                # Calculate position
                x = start_x + col
                y = start_y + row
                location = (x, y, 0)
                
                # Create plane with random material
                material = random.choice(materials)
                self.create_plane(context, location, material)

    def execute(self, context):
        """Execute the operator."""
        # Get selected files
        files = [os.path.join(self.directory, file.name) 
                for file in self.files]
        if not files:
            self.report({'ERROR'}, "No texture files selected")
            return {'CANCELLED'}
            
        try:
            # Create materials from textures
            materials = []
            for file_path in files:
                material = self.create_material_from_texture(file_path)
                materials.append(material)
            
            # Create grid of planes
            self.create_tile_grid(context, materials)
            
            grid_size = context.scene.zenv_tile_props.grid_size
            self.report(
                {'INFO'}, 
                f"Created {grid_size}x{grid_size} tile grid with "
                f"{len(materials)} textures"
            )
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error creating tiles: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RandomTilesPanel(Panel):
    """Panel for creating random texture tiles."""
    bl_label = "GEN Random Texture Tiles"
    bl_idname = "ZENV_PT_random_tiles"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_tile_props
        
        box = layout.box()
        box.label(text="Grid Settings:", icon='GRID')
        col = box.column(align=True)
        col.prop(props, "grid_size")
        col.prop(props, "random_rotation")
        
        box = layout.box()
        box.label(text="Create Tiles:", icon='TEXTURE')
        box.operator(ZENV_OT_CreateRandomTiles.bl_idname)


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_TileProperties,
    ZENV_OT_CreateRandomTiles,
    ZENV_PT_RandomTilesPanel,
)

def register():
    """Register the addon classes."""
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zenv_tile_props = PointerProperty(type=ZENV_PG_TileProperties)

def unregister():
    """Unregister the addon classes."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.zenv_tile_props

if __name__ == "__main__":
    register()
