#region META
bl_info = {
    "name": 'MAT Create From Textures',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Create materials from texture files',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 60,
    "tags": ['material', 'texture', 'pbr', 'create', 'import', 'shader'],
    "description_short": 'create materials from texture folder',
    "description_medium": 'Scans a directory for texture files, groups them by base name (stripping PBR suffixes like _color, _normal, _roughness, etc.), and creates a Principled BSDF material per group with the appropriate texture maps linked (Base Color, Normal, Roughness, Metallic, Height/Displacement, Alpha). Supports a non-PBR fallback that creates a simple diffuse material from the first texture.',
    "description_long": """
MAT Create From Textures - A Blender addon for creating materials from textures.
Create PBR materials from texture files using common naming conventions.
""",
    "image_overview": 'zenv_blender_MAT_create_from_textures.png',
    "addon_image": 'zenv_blender_MAT_create_from_textures.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty
#endregion


#region PROPS
# Property group for material creation from textures, registered on the Scene.

class ZENV_PG_CreateFromTextures_Properties(PropertyGroup):
    """Properties for material creation from textures."""
    
    texture_dir: StringProperty(
        name="Texture Directory",
        description="Directory containing texture files",
        default="",
        subtype='DIR_PATH'
    )
    
    use_pbr: BoolProperty(
        name="Use PBR",
        description="Create PBR materials with normal, roughness, etc.",
        default=True
    )
#endregion


#region OP
# Operator that creates materials from texture files in a directory.

class ZENV_OT_CreateFromTextures(Operator):
    """Create materials from texture files in directory."""
    bl_idname = "zenv.create_from_textures"
    bl_label = "Create Materials"
    bl_options = {'REGISTER', 'UNDO'}

    # PBR suffixes used for grouping and classification.
    PBR_SUFFIXES = (
        '_color', '_albedo', '_diffuse', '_basecolor',
        '_normal', '_nrm', '_norm',
        '_roughness', '_rough', '_rgh',
        '_metallic', '_metal', '_metalness',
        '_height', '_displacement', '_disp',
        '_ao', '_ambient', '_occlusion',
        '_opacity', '_alpha',
    )

    # Map-type classification keywords.
    COLOR_KEYS = ('_color', '_albedo', '_diffuse', '_basecolor')
    NORMAL_KEYS = ('_normal', '_nrm', '_norm')
    ROUGH_KEYS = ('_roughness', '_rough', '_rgh')
    METAL_KEYS = ('_metallic', '_metal', '_metalness')
    HEIGHT_KEYS = ('_height', '_displacement', '_disp')
    ALPHA_KEYS = ('_opacity', '_alpha')
    AO_KEYS = ('_ao', '_ambient', '_occlusion')

    @classmethod
    def strip_pbr_suffix(cls, base_name):
        """Strip a single trailing PBR suffix from ``base_name``.

        Matching is case-insensitive at the END of the base name only.
        Returns the stripped base name (or the original if no suffix
        matched).
        """
        lower = base_name.lower()
        for suffix in cls.PBR_SUFFIXES:
            if lower.endswith(suffix):
                return base_name[:-len(suffix)]
        return base_name

    @classmethod
    def group_textures_by_base(cls, files):
        """Group texture filenames by their PBR-stripped base name.

        Args:
            files: iterable of filenames (strings, no directory prefix).
        Returns:
            dict mapping base_name -> list of original filenames.
        """
        groups = {}
        for file in files:
            base_name = os.path.splitext(file)[0]
            base_name = cls.strip_pbr_suffix(base_name)
            groups.setdefault(base_name, []).append(file)
        return groups

    @classmethod
    def classify_texture(cls, filename):
        """Classify a texture filename into a PBR map type.

        Returns one of: 'color', 'normal', 'rough', 'metal', 'height',
        'alpha', 'ao', or None if no known map type is detected.
        """
        file_lower = filename.lower()
        if any(x in file_lower for x in cls.COLOR_KEYS):
            return 'color'
        if any(x in file_lower for x in cls.NORMAL_KEYS):
            return 'normal'
        if any(x in file_lower for x in cls.ROUGH_KEYS):
            return 'rough'
        if any(x in file_lower for x in cls.METAL_KEYS):
            return 'metal'
        if any(x in file_lower for x in cls.HEIGHT_KEYS):
            return 'height'
        if any(x in file_lower for x in cls.ALPHA_KEYS):
            return 'alpha'
        if any(x in file_lower for x in cls.AO_KEYS):
            return 'ao'
        return None

    @classmethod
    def load_image_safe(cls, img_path):
        """Load an image with check_existing and per-file error handling.

        Returns the image datablock, or None if loading failed.
        """
        try:
            return bpy.data.images.load(img_path, check_existing=True)
        except Exception:
            return None

    @classmethod
    def create_pbr_material(cls, base_name, texture_dir, texture_files):
        """Create a PBR material with the appropriate texture links.

        Returns the created material, or None if creation failed.
        """
        mat = bpy.data.materials.new(name=base_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output.location = (300, 0)
        principled.location = (0, 0)
        links.new(principled.outputs[0], output.inputs[0])

        for tex_index, file in enumerate(texture_files):
            img_path = os.path.join(texture_dir, file)
            img = cls.load_image_safe(img_path)
            if img is None:
                continue

            tex = nodes.new('ShaderNodeTexImage')
            tex.image = img
            tex_y = tex_index * -300
            tex.location = (-300, tex_y)

            map_type = cls.classify_texture(file)

            # Non-color maps must not get sRGB -> linear conversion.
            if map_type != 'color':
                try:
                    img.colorspace_settings.name = 'Non-Color'
                except Exception:
                    pass

            if map_type == 'color':
                links.new(tex.outputs['Color'], principled.inputs['Base Color'])
            elif map_type == 'normal':
                normal_map = nodes.new('ShaderNodeNormalMap')
                normal_map.location = (-150, tex_y)
                links.new(tex.outputs['Color'], normal_map.inputs['Color'])
                links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
            elif map_type == 'rough':
                links.new(tex.outputs['Color'], principled.inputs['Roughness'])
            elif map_type == 'metal':
                links.new(tex.outputs['Color'], principled.inputs['Metallic'])
            elif map_type == 'height':
                displacement = nodes.new('ShaderNodeDisplacement')
                displacement.location = (0, tex_y)
                links.new(tex.outputs['Color'], displacement.inputs['Height'])
                links.new(displacement.outputs['Displacement'], output.inputs['Displacement'])
            elif map_type == 'alpha':
                links.new(tex.outputs['Color'], principled.inputs['Alpha'])
            elif map_type == 'ao':
                # AO has no dedicated Principled BSDF input in Blender 4.x.
                # Mix AO into Base Color via a MixRGB node set to Multiply
                # so the ambient occlusion darkens crevices.
                mix = nodes.new('ShaderNodeMixRGB')
                mix.blend_type = 'MULTIPLY'
                mix.inputs['Fac'].default_value = 0.5
                mix.location = (-150, tex_y)
                # Re-link Base Color through the mix node
                base_color_link = None
                for link in links:
                    if link.to_socket == principled.inputs['Base Color']:
                        base_color_link = link
                        break
                if base_color_link is not None:
                    from_socket = base_color_link.from_socket
                    links.remove(base_color_link)
                    links.new(from_socket, mix.inputs['Color1'])
                links.new(tex.outputs['Color'], mix.inputs['Color2'])
                links.new(mix.outputs['Color'], principled.inputs['Base Color'])
            else:
                # Unknown map type: leave the texture node loaded but
                # unconnected so the user can wire it manually.
                pass

        return mat

    @classmethod
    def create_simple_material(cls, base_name, texture_dir, texture_files):
        """Create a simple diffuse material from the first texture.

        Returns the created material, or None if creation failed.
        """
        mat = bpy.data.materials.new(name=base_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        output = nodes.new('ShaderNodeOutputMaterial')
        diffuse = nodes.new('ShaderNodeBsdfDiffuse')
        output.location = (300, 0)
        diffuse.location = (0, 0)
        links.new(diffuse.outputs[0], output.inputs[0])

        if texture_files:
            img_path = os.path.join(texture_dir, texture_files[0])
            img = cls.load_image_safe(img_path)
            if img is not None:
                tex = nodes.new('ShaderNodeTexImage')
                tex.image = img
                tex.location = (-300, 0)
                links.new(tex.outputs['Color'], diffuse.inputs['Color'])

        return mat

    def execute(self, context):
        """Execute the material creation."""
        props = context.scene.zenv_create_textures_props
        texture_dir = props.texture_dir

        if not texture_dir or not os.path.exists(texture_dir):
            self.report({'ERROR'}, "Invalid texture directory")
            return {'CANCELLED'}

        # Track created materials for cleanup on failure.
        created_materials = []

        try:
            files = [f for f in os.listdir(texture_dir)
                     if os.path.isfile(os.path.join(texture_dir, f))]

            texture_groups = self.group_textures_by_base(files)

            wm = context.window_manager
            wm.progress_begin(0, len(texture_groups))

            created_count = 0
            for i, (base_name, texture_files) in enumerate(texture_groups.items()):
                if props.use_pbr:
                    mat = self.create_pbr_material(base_name, texture_dir, texture_files)
                else:
                    mat = self.create_simple_material(base_name, texture_dir, texture_files)
                if mat is not None:
                    created_materials.append(mat)
                    created_count += 1
                wm.progress_update(i + 1)

            wm.progress_end()

            self.report({'INFO'}, f"Created {created_count} materials")
            return {'FINISHED'}

        except Exception as e:
            # Clean up partially-created materials on failure.
            for mat in created_materials:
                if mat.name in bpy.data.materials:
                    bpy.data.materials.remove(mat, do_unlink=True)
            self.report({'ERROR'}, f"Error creating materials: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_CreateFromTexturesPanel(Panel):
    """Panel for creating materials from textures."""
    bl_label = "MAT Create From Textures"
    bl_idname = "ZENV_PT_create_from_textures"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_create_textures_props

        box = layout.box()
        box.prop(props, "texture_dir")
        box.prop(props, "use_pbr")
        box.operator(ZENV_OT_CreateFromTextures.bl_idname)
#endregion


#region REG
classes = (
    ZENV_PG_CreateFromTextures_Properties,
    ZENV_OT_CreateFromTextures,
    ZENV_PT_CreateFromTexturesPanel,
)

def register():
    """Register the addon classes."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_create_textures_props = PointerProperty(
        type=ZENV_PG_CreateFromTextures_Properties
    )

def unregister():
    """Unregister the addon classes."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_create_textures_props

if __name__ == "__main__":
    register()
#endregion
