"""
CLEAN Scene Optimizer 
- Removing unused textures and materials
- Cleaning up missing texture references
- Consolidating duplicate materials
- Optimizing mesh data
- Removing empty vertex groups
"""

bl_info = {
    "name": "CLEAN Scene Optimizer",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": (
        "Tools for cleaning and optimizing scene data including unused textures, "
        "materials, and mesh data"
    )
}

import bpy
import bmesh
from pathlib import Path


class ZENV_PT_SceneOptimizerPanel(bpy.types.Panel):
    """Panel for scene optimization tools.
    - Texture cleanup (unused and missing textures)
    - Material cleanup (unused and duplicate materials)
    - Mesh cleanup (mesh data optimization and vertex groups)
    """
    bl_label = "CLEAN Scene Optimizer"
    bl_idname = "ZENV_PT_SceneOptimizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        """Draw the panel layout with organized sections for different cleanup tools."""
        layout = self.layout
        
        # Texture cleaning section
        box = layout.box()
        box.label(text="Texture Cleanup")
        col = box.column(align=True)
        col.operator("zenv.clean_unused_textures")
        col.operator("zenv.clean_missing_textures")
        
        # Material cleaning section
        box = layout.box()
        box.label(text="Material Cleanup")
        col = box.column(align=True)
        col.operator("zenv.clean_unused_materials")
        col.operator("zenv.clean_duplicate_materials")
        
        # Mesh cleaning section
        box = layout.box()
        box.label(text="Mesh Cleanup")
        col = box.column(align=True)
        col.operator("zenv.clean_mesh_data")
        col.operator("zenv.remove_empty_vertex_groups")


class ZENV_OT_CleanUnusedTextures(bpy.types.Operator):
    """Remove unused image textures from the blend file.
    
    Scans all materials for image texture nodes and removes any images that are
    not used in any material. Only removes unpacked images to avoid data loss.
    """
    bl_idname = "zenv.clean_unused_textures"
    bl_label = "Remove Unused Textures"
    bl_description = "Remove all image textures that are not used in any materials"
    bl_options = {'REGISTER', 'UNDO'}

    def find_texture_users(self):
        """Find all textures being used in materials.
        
        Returns:
            set: Set of image datablocks that are used in material nodes.
        """
        used_images = set()
        for mat in bpy.data.materials:
            if mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        used_images.add(node.image)
        return used_images

    def execute(self, context):
        """Execute the operator.
        
        Removes all unused image textures from the blend file.
        
        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        used_images = self.find_texture_users()
        removed_count = 0

        # Remove unused images
        for img in bpy.data.images[:]:
            if img not in used_images and not img.packed_file:
                bpy.data.images.remove(img)
                removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} unused textures")
        return {'FINISHED'}


class ZENV_OT_CleanMissingTextures(bpy.types.Operator):
    """Remove references to missing texture files.
    
    Scans all image datablocks and removes any that reference files that no
    longer exist on disk. Only removes unpacked images to avoid data loss.
    """
    bl_idname = "zenv.clean_missing_textures"
    bl_label = "Clean Missing Textures"
    bl_description = (
        "Remove references to missing texture files and attempt to find "
        "relocated textures"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator.
        
        Removes references to missing texture files.
        
        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        removed_count = 0
        for img in bpy.data.images[:]:
            if not img.packed_file and not Path(bpy.path.abspath(img.filepath)).exists():
                bpy.data.images.remove(img)
                removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} missing texture references")
        return {'FINISHED'}


class ZENV_OT_CleanUnusedMaterials(bpy.types.Operator):
    """Remove materials that aren't assigned to any objects.
    
    Scans all objects in the scene and removes any materials that are not
    assigned to any object's material slots.
    """
    bl_idname = "zenv.clean_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_description = "Remove all materials that are not assigned to any objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator.
        
        Removes all unused materials from the blend file.
        
        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        used_materials = set()
        
        # Find all used materials
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                used_materials.update(
                    slot.material for slot in obj.material_slots if slot.material
                )

        # Remove unused materials
        removed_count = 0
        for mat in bpy.data.materials[:]:
            if mat not in used_materials:
                bpy.data.materials.remove(mat)
                removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} unused materials")
        return {'FINISHED'}


class ZENV_OT_CleanDuplicateMaterials(bpy.types.Operator):
    """Consolidate duplicate materials based on name.
    
    Finds materials with the same base name (ignoring .001, .002 suffixes) and
    merges them by replacing all uses of duplicates with the primary material.
    """
    bl_idname = "zenv.clean_duplicate_materials"
    bl_label = "Remove Duplicate Materials"
    bl_description = "Merge materials with the same name and similar properties"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator.
        
        Merges duplicate materials and updates all object references.
        
        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        materials_by_name = {}
        
        # Group materials by base name (without .001, .002 etc)
        for mat in bpy.data.materials:
            base_name = mat.name.split('.')[0]
            if base_name not in materials_by_name:
                materials_by_name[base_name] = []
            materials_by_name[base_name].append(mat)

        # Merge duplicates
        merged_count = 0
        for base_name, mats in materials_by_name.items():
            if len(mats) > 1:
                primary_mat = mats[0]
                for dup_mat in mats[1:]:
                    # Replace all uses of duplicate material with primary material
                    for obj in bpy.data.objects:
                        if obj.type == 'MESH':
                            for slot in obj.material_slots:
                                if slot.material == dup_mat:
                                    slot.material = primary_mat
                    bpy.data.materials.remove(dup_mat)
                    merged_count += 1

        self.report({'INFO'}, f"Merged {merged_count} duplicate materials")
        return {'FINISHED'}


class ZENV_OT_CleanMeshData(bpy.types.Operator):
    """Clean up mesh data including doubles, unused vertices, etc.
    
    Performs several mesh cleanup operations:
    - Removes duplicate vertices
    - Dissolves degenerate edges
    - Removes loose vertices
    - Recalculates normals
    """
    bl_idname = "zenv.clean_mesh_data"
    bl_label = "Clean Mesh Data"
    bl_description = (
        "Remove doubles, dissolve loose vertices, and recalculate normals"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator.
        
        Cleans up mesh data for all mesh objects in the scene.
        
        This includes:
        - Removing duplicate vertices
        - Dissolving loose vertices
        - Removing loose geometry
        - Recalculating normals
        
        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        cleaned_objects = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                # Enter edit mode
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                
                # Get the bmesh
                me = obj.data
                bm = bmesh.from_edit_mesh(me)
                
                # Remove doubles
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
                
                # Dissolve loose vertices
                bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0001)
                
                # Remove loose geometry
                loose_verts = [v for v in bm.verts if not v.link_edges]
                bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
                
                # Update mesh
                bmesh.update_edit_mesh(me)
                
                # Recalculate normals
                bpy.ops.mesh.normals_make_consistent(inside=False)
                
                # Exit edit mode
                bpy.ops.object.mode_set(mode='OBJECT')
                
                cleaned_objects += 1

        self.report({'INFO'}, f"Cleaned mesh data for {cleaned_objects} objects")
        return {'FINISHED'}


class ZENV_OT_RemoveEmptyVertexGroups(bpy.types.Operator):
    """Remove empty vertex groups from all meshes.
    
    Scans all mesh objects and removes any vertex groups that have no vertices
    assigned to them with non-zero weights.
    """
    bl_idname = "zenv.remove_empty_vertex_groups"
    bl_label = "Remove Empty Vertex Groups"
    bl_description = "Remove vertex groups that have no vertices assigned"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Removes empty vertex groups from all mesh objects."""
        removed_count = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                # Get list of empty groups
                empty_groups = []
                for group in obj.vertex_groups:
                    is_empty = True
                    for vert in obj.data.vertices:
                        try:
                            group.weight(vert.index)
                            is_empty = False
                            break
                        except RuntimeError:
                            continue
                    if is_empty:
                        empty_groups.append(group)
                
                # Remove empty groups
                for group in empty_groups:
                    obj.vertex_groups.remove(group)
                    removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} empty vertex groups")
        return {'FINISHED'}


# Registration
classes = (
    ZENV_PT_SceneOptimizerPanel,
    ZENV_OT_CleanUnusedTextures,
    ZENV_OT_CleanMissingTextures,
    ZENV_OT_CleanUnusedMaterials,
    ZENV_OT_CleanDuplicateMaterials,
    ZENV_OT_CleanMeshData,
    ZENV_OT_RemoveEmptyVertexGroups,
)

def register():
    """Register the addon classes and operators."""
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    """Unregister the addon classes and operators."""
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
