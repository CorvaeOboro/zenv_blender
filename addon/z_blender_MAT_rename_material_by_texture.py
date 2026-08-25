#region META
bl_info = {
    "name": 'MAT Rename Material by Texture',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Rename and merge materials based on their base color texture names',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 30,
    "tags": ['material', 'texture', 'rename', 'merge', 'cleanup', 'name'],
    "description_short": 'rename material by texture name',
    "description_medium": 'Scans selected mesh objects for materials with a Principled BSDF whose Base Color input is connected to an Image Texture node. Extracts the texture name (stripping optional prefix/suffix) to derive a base name. Optionally renames materials to match the texture base name (with an optional suffix added). Optionally merges materials that share the same texture base name by replacing all references with the first material and removing the duplicates.',
    "description_long": """
MAT Rename Material by Texture - A Blender addon for renaming and merging materials.
1. Scans selected mesh objects for materials with base color textures.
2. Extracts the texture base name (stripping configurable prefix/suffix).
3. Renames materials to match the texture base name (with optional suffix).
4. Optionally merges materials that share the same texture base name.
Only selected objects are scanned; merge replaces references on all objects.
""",
    "image_overview": 'zenv_blender_MAT_rename_material_by_texture.png',
    "addon_image": 'zenv_blender_MAT_rename_material_by_texture.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import os
from collections import defaultdict
from bpy.props import BoolProperty, StringProperty, EnumProperty
from bpy.types import Panel, Operator, PropertyGroup
#endregion


#region UTILS
# Utility class with static methods for finding base color textures
# and extracting base names. Not registered with Blender.

class ZENV_MaterialRename_Utils:
    """Utility functions for material renaming"""
    
    @staticmethod
    def find_base_color_texture(material):
        """Find base color texture node in material"""
        if not material or not material.use_nodes:
            return None
            
        # Find Principled BSDF
        principled = next((n for n in material.node_tree.nodes 
                         if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            return None
            
        # Find connected texture
        base_color = principled.inputs['Base Color']
        if not base_color.is_linked:
            return None
            
        texture_node = base_color.links[0].from_node
        if texture_node.type != 'TEX_IMAGE' or not texture_node.image:
            return None
            
        return texture_node

    @staticmethod
    def get_texture_base_name(texture_node, remove_suffix=True, custom_suffix="", remove_prefix=True, custom_prefix=""):
        """Get base name from texture node"""
        if not texture_node or not texture_node.image:
            return None
            
        # Get name without extension
        name = os.path.splitext(texture_node.image.name)[0]
        
        # Remove custom prefix if specified
        if remove_prefix and custom_prefix and name.startswith(custom_prefix):
            name = name[len(custom_prefix):]
            
        # Remove custom suffix if specified
        if remove_suffix and custom_suffix and name.endswith(custom_suffix):
            name = name[:-len(custom_suffix)]
            
        return name
#endregion


#region OP
# Operator that renames and optionally merges materials by texture name.

class ZENV_OT_RenameMaterialsByTexture(Operator):
    """Rename materials based on their base color texture names"""
    bl_idname = "zenv.rename_materials_by_texture"
    bl_label = "Rename by Texture"
    bl_description = "Rename materials based on their base color texture names"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            props = context.scene.zenv_mat_rename_props
            texture_material_map = defaultdict(set)
            renamed = 0
            merged = 0

            # Collect materials with textures
            for obj in context.selected_objects:
                if obj.type != 'MESH':
                    continue

                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.use_nodes:
                        continue

                    # Find texture
                    texture_node = ZENV_MaterialRename_Utils.find_base_color_texture(mat)
                    if not texture_node:
                        continue

                    # Get base name
                    texture_name = ZENV_MaterialRename_Utils.get_texture_base_name(
                        texture_node,
                        props.remove_suffix,
                        props.texture_suffix,
                        props.remove_prefix,
                        props.texture_prefix
                    )
                    if not texture_name:
                        continue

                    # Add to map (set ensures O(1) membership and no duplicates)
                    texture_material_map[texture_name].add(mat)

            # Process materials
            for texture_name, materials in texture_material_map.items():
                if not materials:  # Skip if no materials
                    continue

                # Convert set to sorted list for deterministic ordering
                materials_list = sorted(materials, key=lambda m: m.name)

                # Add suffix if enabled
                final_name = texture_name
                if props.add_material_suffix:
                    final_name += props.material_suffix

                # Merge or rename materials
                if props.merge_materials and len(materials_list) > 1:
                    try:
                        # Keep first material
                        main_mat = materials_list[0]
                        if not main_mat or main_mat.name not in bpy.data.materials:
                            continue

                        # Rename main material
                        main_mat.name = final_name
                        renamed += 1

                        # Process other materials
                        for other_mat in materials_list[1:]:
                            if not other_mat or other_mat.name not in bpy.data.materials:
                                continue

                            # Skip if same material
                            if other_mat == main_mat:
                                continue

                            try:
                                # Replace all uses of other_mat with main_mat
                                for obj in bpy.data.objects:
                                    if obj.type == 'MESH':
                                        for slot in obj.material_slots:
                                            if slot.material == other_mat:
                                                slot.material = main_mat

                                # Only remove if it exists and is not used
                                if (other_mat.name in bpy.data.materials and
                                    not any(obj.material_slots and any(slot.material == other_mat for slot in obj.material_slots)
                                           for obj in bpy.data.objects)):
                                    bpy.data.materials.remove(other_mat)
                                    merged += 1

                            except ReferenceError:
                                continue
                    except Exception as e:
                        self.report({'WARNING'}, f"Error processing material: {str(e)}")
                        continue
                else:
                    # Just rename the material
                    for mat in materials_list:
                        if mat and mat.name in bpy.data.materials:
                            mat.name = final_name
                            renamed += 1

            # Report results
            if merged > 0:
                self.report({'INFO'}, f"Renamed {renamed} materials and merged {merged} duplicates")
            else:
                self.report({'INFO'}, f"Renamed {renamed} materials")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error renaming materials: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PROPS
# Property group for material renaming settings, registered on the Scene.

class ZENV_PG_MaterialRenameProps(PropertyGroup):
    """Properties for material renaming"""
    remove_prefix: BoolProperty(
        name="Prefix Remove",
        description="Remove prefix from texture name when renaming",
        default=True
    )
    texture_prefix: StringProperty(
        name="Texture Prefix",
        description="Prefix to remove from texture names",
        default="d_"
    )
    remove_suffix: BoolProperty(
        name="Suffix Remove",
        description="Remove suffix from texture name when renaming",
        default=True
    )
    texture_suffix: StringProperty(
        name="Texture Suffix",
        description="Suffix to remove from texture names",
        default="_C"
    )
    add_material_suffix: BoolProperty(
        name="+ Suffix",
        description="Add suffix to material names",
        default=True
    )
    material_suffix: StringProperty(
        name="Suffix Add",
        description="Suffix to add to material names",
        default="_MI"
    )
    merge_materials: BoolProperty(
        name="Merge Materials",
        description="Merge materials that use the same texture",
        default=True
    )
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_MaterialRenameByTexture(Panel):
    """Panel for material renaming operations"""
    bl_label = "MAT Rename by Texture"
    bl_idname = "ZENV_PT_material_rename_texture"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_mat_rename_props
        
        # Texture settings
        box = layout.box()
        box.label(text="Alter Texture Name")
        col = box.column(align=True)
        
        # Prefix settings
        row = col.row()
        row.prop(props, "remove_prefix")
        sub = row.row()
        sub.active = props.remove_prefix
        sub.prop(props, "texture_prefix", text="")
        
        # Suffix settings
        row = col.row()
        row.prop(props, "remove_suffix")
        sub = row.row()
        sub.active = props.remove_suffix
        sub.prop(props, "texture_suffix", text="")
        
        # Material settings
        box = layout.box()
        box.label(text="Material Name")
        col = box.column(align=True)
        row = col.row()
        row.prop(props, "add_material_suffix")
        sub = row.row()
        sub.active = props.add_material_suffix
        sub.prop(props, "material_suffix", text="")
        col.prop(props, "merge_materials")
        
        # Operator
        box = layout.box()
        box.operator("zenv.rename_materials_by_texture")
#endregion


#region REG
classes = (
    ZENV_PG_MaterialRenameProps,
    ZENV_OT_RenameMaterialsByTexture,
    ZENV_PT_MaterialRenameByTexture,
)


def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_mat_rename_props = bpy.props.PointerProperty(type=ZENV_PG_MaterialRenameProps)


def unregister():
    del bpy.types.Scene.zenv_mat_rename_props
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)


if __name__ == "__main__":
    register()
#endregion
