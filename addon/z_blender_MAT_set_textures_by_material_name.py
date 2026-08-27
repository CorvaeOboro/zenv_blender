#region META
bl_info = {
    "name": 'MAT Set Textures by Material Name',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Set textures to materials based on material names',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 90,
    "tags": ['material', 'texture', 'assign', 'nodes', 'principled', 'pbr'],
    "description_short": 'assign textures based on material names',
    "description_medium": 'Scans all materials, strips a configurable suffix (e.g. _MI) from each material name, looks in a user-specified texture directory for matching texture files (by base name + PBR suffix keywords), and recreates the material node tree with Principled BSDF, Image Texture, Normal Map, Displacement, and AO MixRGB nodes as appropriate. Also provides an operator to assign materials to mesh objects by matching mesh names to material names.',
    "description_long": """
MAT Set Textures by Material Name
- A Blender addon for fixing texture paths in materials.
Recreates material nodes with correct texture paths based on material names.
""",
    "image_overview": 'zenv_blender_MAT_set_textures_by_material_name.png',
    "addon_image": 'zenv_blender_MAT_set_textures_by_material_name.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
import re
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty
#endregion


#region PROPS
# Property group for texture directory and material suffix, registered
# on the Scene.

class ZENV_PG_SetTextureByMaterialName_Properties(PropertyGroup):
    """Properties for setting textures by material name."""
    
    texture_dir: StringProperty(
        name="Texture Folder",
        description="Directory containing texture files",
        default="",
        subtype='DIR_PATH'
    )
    
    material_suffix: StringProperty(
        name="Suffix of Material",
        description="Suffix to remove from material names _MI",
        default="_MI"
    )
#endregion


#region OP
# Operators for setting textures by material name and assigning
# materials to meshes by name.

class ZENV_OT_SetTextureByMaterialName(Operator):
    """Set textures to materials based on material names."""
    bl_idname = "zenv.set_textures_by_material_name"
    bl_label = "Set Textures by Material Name"
    bl_options = {'REGISTER', 'UNDO'}

    # Texture type keyword mappings (class-level constant so it is
    # built once, not per material).
    TEXTURE_TYPES = {
        'color': ['color', 'albedo', 'diffuse', 'basecolor'],
        'normal': ['normal', 'nrm', 'norm'],
        'roughness': ['rough', 'roughness', 'rgh'],
        'metallic': ['metal', 'metallic', 'metalness'],
        'height': ['height', 'displacement', 'disp'],
        'ao': ['ao', 'ambient', 'occlusion'],
    }

    # Texture types that must be interpreted as Non-Color data so
    # Blender does not apply sRGB -> linear to their pixels.
    NON_COLOR_TYPES = {'normal', 'roughness', 'metallic', 'height', 'ao'}

    # Processing order: color must be linked before AO so the AO
    # MixRGB node can re-route the existing Base Color link.
    PROCESSING_ORDER = ['color', 'normal', 'roughness', 'metallic',
                        'height', 'ao']

    @classmethod
    def find_matching_textures(cls, material_name, texture_files):
        """Find and classify textures matching a material name.

        Args:
            material_name: Base name of the material (without suffix).
            texture_files: Pre-filtered list of candidate texture
                filenames in the texture directory.

        Returns:
            dict mapping texture type (e.g. ``'color'``) to filename.
            Empty dict if no matches.
        """
        matching_textures = {}
        untyped_files = []

        for tex_file in texture_files:
            tex_base = os.path.splitext(tex_file)[0].lower()

            # Check for exact match or prefixed match
            if tex_base != material_name.lower() and not tex_base.startswith(material_name.lower() + '_'):
                continue

            # Determine texture type
            tex_type = None
            for type_name, keywords in cls.TEXTURE_TYPES.items():
                if any(keyword in tex_base for keyword in keywords):
                    tex_type = type_name
                    break

            if tex_type:
                matching_textures[tex_type] = tex_file
            else:
                # Collect untyped files; the first one will be
                # assigned as color after the loop (independent of
                # file ordering).
                untyped_files.append(tex_file)

        # Assign the first untyped file as color if no color
        # texture was found. This is independent of file ordering.
        if 'color' not in matching_textures and untyped_files:
            matching_textures['color'] = untyped_files[0]

        return matching_textures

    def execute(self, context):
        """Execute the texture set operation."""
        try:
            props = context.scene.zenv_set_textures_props
            texture_dir = os.path.normpath(props.texture_dir)
            suffix = props.material_suffix

            if not texture_dir or not os.path.exists(texture_dir):
                self.report({'ERROR'}, f"Texture directory does not exist: {texture_dir}")
                return {'CANCELLED'}

            processed_count = 0
            skipped_count = 0

            # List the texture directory ONCE pass the result through to process_material.
            SUPPORTED_EXTS = ('.png', '.jpg', '.jpeg', '.tga', '.bmp', '.exr')
            try:
                texture_files = [
                    f for f in os.listdir(texture_dir)
                    if os.path.isfile(os.path.join(texture_dir, f))
                    and f.lower().endswith(SUPPORTED_EXTS)
                ]
            except (PermissionError, FileNotFoundError) as e:
                self.report({'ERROR'}, f"Cannot access texture directory: {str(e)}")
                return {'CANCELLED'}

            for material in bpy.data.materials:
                if not material.use_nodes:
                    continue

                material_name = material.name.strip()
                if not material_name:
                    self.report({'WARNING'}, "Skipping material with empty name")
                    skipped_count += 1
                    continue

                # Strip the configured suffix only when it is at the END
                # of the material name. Using str.replace here would strip
                # the substring anywhere, corrupting names like `_MI_panel`.
                if suffix and material_name.endswith(suffix):
                    material_name = material_name[:-len(suffix)]

                # Process the material
                if self.process_material(material, material_name, texture_dir, texture_files):
                    processed_count += 1
                else:
                    skipped_count += 1

            if processed_count > 0:
                msg = f"Processed {processed_count} materials"
                if skipped_count > 0:
                    msg += f", skipped {skipped_count}"
                self.report({'INFO'}, msg)
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, f"No materials were processed, {skipped_count} skipped")
                return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            return {'CANCELLED'}

    def process_material(self, material, material_name, texture_dir, texture_files):
        """Process a single material and set up its textures.

        Args:
            material: The material to process
            material_name: Base name of the material (without suffix)
            texture_dir: Directory containing texture files
            texture_files: Pre-filtered list of candidate texture filenames
                in ``texture_dir`` (cached by the caller to avoid per-material
                I/O).

        Returns:
            bool: True if material was processed successfully
        """
        # Find matching textures using the extracted classmethod
        matching_textures = self.find_matching_textures(material_name, texture_files)

        if not matching_textures:
            return False

        # Clear and recreate nodes
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        # Create main nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        output.location = (300, 0)
        principled.location = (0, 0)

        # Link main nodes
        links.new(principled.outputs[0], output.inputs[0])

        # Process textures in a deterministic order so that color is
        # linked before AO (AO MixRGB re-routes the Base Color link).
        ordered_items = [
            (t, matching_textures[t])
            for t in self.PROCESSING_ORDER
            if t in matching_textures
        ]

        for i, (tex_type, tex_file) in enumerate(ordered_items):
            try:
                # Create texture node
                tex = nodes.new('ShaderNodeTexImage')
                img_path = os.path.join(texture_dir, tex_file)
                img = bpy.data.images.load(img_path, check_existing=True)
                tex.image = img
                tex.location = (-300, i * -300)

                if tex_type in self.NON_COLOR_TYPES:
                    try:
                        img.colorspace_settings.name = 'Non-Color'
                    except Exception:
                        pass

                # Connect based on texture type
                if tex_type == 'color':
                    links.new(tex.outputs['Color'], principled.inputs['Base Color'])
                elif tex_type == 'normal':
                    normal_map = nodes.new('ShaderNodeNormalMap')
                    normal_map.location = (-150, i * -300)
                    links.new(tex.outputs['Color'], normal_map.inputs['Color'])
                    links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                elif tex_type == 'roughness':
                    links.new(tex.outputs['Color'], principled.inputs['Roughness'])
                elif tex_type == 'metallic':
                    links.new(tex.outputs['Color'], principled.inputs['Metallic'])
                elif tex_type == 'height':
                    # Add displacement setup
                    disp = nodes.new('ShaderNodeDisplacement')
                    disp.location = (0, -300)
                    links.new(tex.outputs['Color'], disp.inputs['Height'])
                    links.new(disp.outputs['Displacement'], output.inputs['Displacement'])
                elif tex_type == 'ao':
                    # Create mix RGB node for AO
                    mix = nodes.new('ShaderNodeMixRGB')
                    mix.blend_type = 'MULTIPLY'
                    mix.inputs[0].default_value = 1.0
                    mix.location = (-150, i * -300)
                    # Connect if base color exists
                    if 'Base Color' in principled.inputs and principled.inputs['Base Color'].links:
                        base_color = principled.inputs['Base Color'].links[0].from_socket
                        links.new(base_color, mix.inputs[1])
                        links.new(tex.outputs['Color'], mix.inputs[2])
                        links.new(mix.outputs['Color'], principled.inputs['Base Color'])

            except Exception as e:
                self.report({'WARNING'}, f"Failed to process texture {tex_file}: {str(e)}")
                continue

        return True


class ZENV_OT_AssignMaterialsByMeshName(Operator):
    """Assign materials to meshes based on matching names."""
    bl_idname = "zenv.assign_materials_by_mesh_name"
    bl_label = "Assign Materials by Mesh Name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the material assignment operation."""
        try:
            # Get all mesh objects in the scene
            mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
            
            if not mesh_objects:
                self.report({'WARNING'}, "No mesh objects found in scene")
                return {'CANCELLED'}
            
            # Get all materials
            materials = {mat.name: mat for mat in bpy.data.materials}
            
            if not materials:
                self.report({'WARNING'}, "No materials found in scene")
                return {'CANCELLED'}
            
            assigned_count = 0
            skipped_count = 0
            
            for obj in mesh_objects:
                # Remove suffix like .001, .002, etc. from mesh name , these are duplicates generated by name collisions 
                base_name = re.sub(r'\.\d{3,}$', '', obj.name)
                
                # Try to find a matching material
                matched_material = None
                
                # First try exact match with base name
                if base_name in materials:
                    matched_material = materials[base_name]
                else:
                    # Try case-insensitive match
                    for mat_name, mat in materials.items():
                        if mat_name.lower() == base_name.lower():
                            matched_material = mat
                            break
                
                if matched_material:
                    # Clear existing materials and assign the matched one
                    obj.data.materials.clear()
                    obj.data.materials.append(matched_material)
                    assigned_count += 1
                else:
                    skipped_count += 1
            
            if assigned_count > 0:
                msg = f"Assigned materials to {assigned_count} mesh(es)"
                if skipped_count > 0:
                    msg += f", skipped {skipped_count} mesh(es) without matching materials"
                self.report({'INFO'}, msg)
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, f"No materials were assigned, {skipped_count} mesh(es) had no matching materials")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_SetTextureByMaterialName(Panel):
    """Panel for fixing texture paths."""
    bl_label = "MAT Set Textures by Material Name"
    bl_idname = "ZENV_PT_set_textures_by_material_name"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout."""
        layout = self.layout
        props = context.scene.zenv_set_textures_props
        
        box = layout.box()

        box.prop(props, "texture_dir")
        box.prop(props, "material_suffix")

        box.operator(ZENV_OT_SetTextureByMaterialName.bl_idname)
        
        box.separator()
        box.operator(ZENV_OT_AssignMaterialsByMeshName.bl_idname)
#endregion


#region REG
classes = (
    ZENV_PG_SetTextureByMaterialName_Properties,
    ZENV_OT_SetTextureByMaterialName,
    ZENV_OT_AssignMaterialsByMeshName,
    ZENV_PT_SetTextureByMaterialName,
)

def register():
    """Register the addon classes and properties."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_set_textures_props = PointerProperty(
        type=ZENV_PG_SetTextureByMaterialName_Properties
    )

def unregister():
    """Unregister the addon classes and properties."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    del bpy.types.Scene.zenv_set_textures_props

if __name__ == "__main__":
    register()
#endregion
