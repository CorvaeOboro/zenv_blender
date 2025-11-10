bl_info = {
    "name": 'MAT Remap Textures',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20250213',
    "description": 'Remap texture paths in materials',
    "status": 'working',
    "approved": True,
    "sort_priority": '1',
    "group": 'Material',
    "group_prefix": 'MAT',
    "description_short": 'remap texture paths in materials',
    "description_long": """
MAT Remap Textures - A Blender addon for texture path remapping.
remap texture paths in materials, switch between texture sets.
""",
    "location": 'View3D > ZENV',
}

import bpy
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, EnumProperty, PointerProperty

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_PG_RemapTextures_Properties(PropertyGroup):
    """Properties for texture remapping."""
    old_path: StringProperty(
        name="Old Path",
        description="Path to replace in texture references",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )
    new_path: StringProperty(
        name="New Path",
        description="New path to use for texture references",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )
    image_ext: EnumProperty(
        name="Image Extension",
        description="Image file extension to use",
        items=[
            ('.png', "PNG", "Use PNG format"),
            ('.bmp', "BMP", "Use BMP format"),
            ('.jpg', "JPG", "Use JPG format"),
            ('.tga', "TGA", "Use TGA format"),
            ('.tif', "TIF", "Use TIF format"),
        ],
        default='.png'
    )

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_RemapTextures(Operator):
    """Remap texture paths in materials."""
    bl_idname = "zenv.remap_textures"
    bl_label = "Remap Textures"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the texture remapping operation."""
        try:
            props = context.scene.zenv_remap_props
            old_path = props.old_path
            new_path = props.new_path
            ext = props.image_ext
            
            # Validate paths
            if not old_path or not new_path:
                self.report({'ERROR'}, "Both old and new paths must be specified")
                return {'CANCELLED'}

            # Convert to absolute paths
            old_path = os.path.abspath(old_path)
            new_path = os.path.abspath(new_path)
            
            # Clean up paths
            old_path = old_path.replace('\\', '/')
            new_path = new_path.replace('\\', '/')
            if old_path.endswith('/'):
                old_path = old_path[:-1]
            if new_path.endswith('/'):
                new_path = new_path[:-1]

            # Track changes
            remapped_count = 0
            
            # Process all materials
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                    
                # Process all nodes
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        img = node.image
                        if img.filepath:
                            old_filepath = os.path.abspath(
                                bpy.path.abspath(img.filepath)
                            ).replace('\\', '/')
                            
                            # Check if old path is in filepath
                            if old_path in old_filepath:
                                # Get the relative path after old_path
                                rel_path = old_filepath[old_filepath.find(old_path) + len(old_path):].lstrip('/')
                                
                                # Change extension if needed
                                base_path = os.path.splitext(rel_path)[0]
                                new_filepath = f"{new_path}/{base_path}{ext}"
                                
                                # Ensure the directory exists
                                os.makedirs(os.path.dirname(new_filepath), exist_ok=True)
                                
                                # Update filepath and reload image
                                if os.path.exists(new_filepath):
                                    img.filepath = new_filepath
                                    img.filepath_raw = new_filepath
                                    img.reload()
                                    remapped_count += 1
                                else:
                                    self.report(
                                        {'WARNING'}, 
                                        f"File not found: {new_filepath}"
                                    )

            if remapped_count > 0:
                # Force update of all image users
                for img in bpy.data.images:
                    img.update_tag()
                
                # Redraw all areas to show changes
                for area in context.screen.areas:
                    area.tag_redraw()
                
                self.report(
                    {'INFO'}, 
                    f"Remapped {remapped_count} texture paths"
                )
                return {'FINISHED'}
            else:
                self.report(
                    {'WARNING'}, 
                    "No textures were remapped. Check paths and files."
                )
                return {'CANCELLED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error remapping textures: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_RemapTexturesPanel(Panel):
    """Panel for texture remapping tools."""
    bl_label = "MAT Remap Textures"
    bl_idname = "ZENV_PT_remap_textures"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_remap_props

        # Path inputs
        box = layout.box()

        box.prop(props, "old_path")
        box.prop(props, "new_path")
        box.prop(props, "image_ext")

        box.operator(ZENV_OT_RemapTextures.bl_idname)

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_PG_RemapTextures_Properties,
    ZENV_OT_RemapTextures,
    ZENV_PT_RemapTexturesPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_remap_props = PointerProperty(
        type=ZENV_PG_RemapTextures_Properties
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_remap_props

if __name__ == "__main__":
    register()
