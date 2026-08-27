#region META
bl_info = {
    "name": 'GEN random Tiles by Textures',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Create a grid of planes with random textures',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 10,
    "tags": ['generate', 'tiles', 'texture', 'grid', 'random', 'material'],
    "description_short": 'generate random tiles from texture set for tiling and seam blending review',
    "description_medium": 'Generative tool that creates a grid of planes, each assigned a random texture from a user-selected folder. Supports configurable grid size, tile size, spacing, random 90-degree rotation, and a reproducible random seed. Useful for reviewing texture seams and visualizing tiling patterns.',
    "description_long": """
Generate Random Tiles from Textures
Creates a grid of planes with randomly assigned textures from a selected folder.
Useful for:
- Reviewing texture seams in a texture set
- Visualizing texture variations
- Testing material setups with different textures
Supports random 90-degree rotation, configurable tile size and grid spacing,
and a reproducible random seed.
""",
    "image_overview": 'zenv_blender_GEN_tiles_from_textures.png',
    "addon_image": 'zenv_blender_GEN_tiles_from_textures.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import math
import random
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import IntProperty, BoolProperty, FloatProperty, StringProperty, PointerProperty
#endregion


#region PROPS
# Property group for tile generation settings, registered on the Scene.

class ZENV_PG_TileProperties(PropertyGroup):
    """Property group for tile generation settings."""
    texture_dir: StringProperty(
        name="Texture Directory",
        description="Directory containing texture files to randomly assign to tiles",
        default="",
        subtype='DIR_PATH'
    )
    grid_size: IntProperty(
        name="Grid Size",
        description="Number of rows and columns in the grid",
        default=10,
        min=1,
        max=100
    )
    tile_size: FloatProperty(
        name="Tile Size",
        description="Size of each plane tile in Blender units",
        default=1.0,
        min=0.01,
    )
    grid_spacing: FloatProperty(
        name="Grid Spacing",
        description="Distance between tile centers in the grid",
        default=1.0,
        min=0.01,
    )
    random_rotation: BoolProperty(
        name="Random Rotation",
        description="Randomly rotate each tile in 90-degree increments",
        default=False
    )
    seed: IntProperty(
        name="Random Seed",
        description="Seed for reproducible random tile arrangement (0 = random each time)",
        default=0,
        min=0,
    )
#endregion


#region OP
# Operator that browses for textures and creates a grid of tiled planes.

class ZENV_OT_CreateRandomTiles(Operator):
    """Create a grid of planes with random textures from a folder."""
    bl_idname = "zenv.create_random_tiles"
    bl_label = "Create Random Tiles"
    bl_options = {'REGISTER', 'UNDO'}

    # Supported texture file extensions (lowercase, with dot).
    TEXTURE_EXTENSIONS = (
        '.png', '.jpg', '.jpeg', '.tif', '.tiff',
        '.bmp', '.tga', '.exr', '.hdr', '.webp',
    )

    @classmethod
    def create_material_from_texture(cls, texture_path):
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
        
        # Load and assign the image (check_existing avoids duplicate datablocks)
        texture_node.image = bpy.data.images.load(texture_path, check_existing=True)

        # Use Closest (point) sampling so low-resolution textures show their
        # true pixels instead of being blurred by linear interpolation.
        texture_node.interpolation = 'Closest'
        
        # Link nodes
        links = material.node_tree.links
        links.new(texture_node.outputs['Color'], 
                 principled_bsdf.inputs['Base Color'])
        links.new(principled_bsdf.outputs['BSDF'], 
                 output_node.inputs['Surface'])
        
        # Position nodes for readable layout
        output_node.location = (300, 0)
        principled_bsdf.location = (0, 0)
        texture_node.location = (-300, 0)
        
        return material

    def create_plane(self, context, location, material, tile_size):
        """Create a plane with the given material at the specified location."""
        bpy.ops.mesh.primitive_plane_add(
            size=tile_size,
            enter_editmode=False,
            align='WORLD',
            location=location
        )
        plane = context.active_object

        # Random rotation if enabled - use 90 degree increments
        if context.scene.zenv_tile_props.random_rotation:
            # Choose from 0, 90, 180, or 270 degrees (in radians)
            rotation = random.choice([
                0.0,
                math.radians(90),
                math.radians(180),
                math.radians(270),
            ])
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
        spacing = props.grid_spacing
        tile_size = props.tile_size

        # Seed the random generator for reproducible results.
        if props.seed > 0:
            random.seed(props.seed)

        # Calculate grid dimensions
        total_width = grid_size * spacing
        start_x = -total_width / 2 + spacing / 2
        start_y = -total_width / 2 + spacing / 2

        wm = context.window_manager
        total_tiles = grid_size * grid_size
        wm.progress_begin(0, total_tiles)

        # Create grid
        tile_index = 0
        for row in range(grid_size):
            for col in range(grid_size):
                wm.progress_update(tile_index)
                tile_index += 1

                # Calculate position
                x = start_x + col * spacing
                y = start_y + row * spacing
                location = (x, y, 0)

                # Create plane with random material
                material = random.choice(materials)
                self.create_plane(context, location, material, tile_size)

        wm.progress_end()

    def execute(self, context):
        """Execute the operator."""
        props = context.scene.zenv_tile_props
        texture_dir = props.texture_dir

        if not texture_dir or not os.path.isdir(texture_dir):
            self.report({'ERROR'}, "Invalid texture directory")
            return {'CANCELLED'}

        # Collect image files from the directory, filtering by extension.
        try:
            files = [f for f in os.listdir(texture_dir)
                     if os.path.isfile(os.path.join(texture_dir, f))
                     and os.path.splitext(f)[1].lower() in self.TEXTURE_EXTENSIONS]
        except Exception as e:
            self.report({'ERROR'}, f"Could not read texture directory: {e}")
            return {'CANCELLED'}

        if not files:
            self.report({'ERROR'}, "No texture files found in directory")
            return {'CANCELLED'}

        file_paths = [os.path.join(texture_dir, f) for f in files]

        # Create materials from textures, skipping any files that fail.
        materials = []
        failed_files = 0
        for file_path in file_paths:
            try:
                material = self.create_material_from_texture(file_path)
                materials.append(material)
            except Exception as e:
                failed_files += 1
                self.report({'WARNING'},
                            f"Could not load texture '{os.path.basename(file_path)}': {e}")

        if not materials:
            self.report({'ERROR'}, "No textures could be loaded")
            return {'CANCELLED'}

        # Create grid of planes. If this fails, clean up the materials we
        # created so they don't linger as orphans in bpy.data.materials.
        try:
            self.create_tile_grid(context, materials)
        except Exception as e:
            # Clean up materials created above to avoid datablock pollution.
            for mat in materials:
                if mat.users == 0:
                    bpy.data.materials.remove(mat)
            self.report({'ERROR'}, f"Error creating tile grid: {e}")
            return {'CANCELLED'}

        grid_size = context.scene.zenv_tile_props.grid_size
        parts = [f"Created {grid_size}x{grid_size} tile grid with {len(materials)} textures"]
        if failed_files:
            parts.append(f"skipped {failed_files} unreadable file(s)")
        self.report({'INFO'}, ", ".join(parts))
        return {'FINISHED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

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
        box.label(text="Texture Source:", icon='FILE_FOLDER')
        box.prop(props, "texture_dir")

        box = layout.box()
        box.label(text="Grid Settings:", icon='GRID')
        col = box.column(align=True)
        col.prop(props, "grid_size")
        col.prop(props, "tile_size")
        col.prop(props, "grid_spacing")
        col.prop(props, "random_rotation")
        col.prop(props, "seed")
        
        box = layout.box()
        box.label(text="Create Tiles:", icon='TEXTURE')
        box.operator(ZENV_OT_CreateRandomTiles.bl_idname)
#endregion


#region REG
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
#endregion
