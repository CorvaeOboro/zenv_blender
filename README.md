# ZENV BLENDER
blender addons focused on singular features of 3d modelling , materials , and textures

[DOWNLOAD]( https://github.com/CorvaeOboro/zenv_blender/archive/refs/heads/main.zip ) 

each addon is a self contained python file , to be installed and enabled individually , to demonstrate a specific modular feature .
# INSTALL 
- download and extract folder to local filepath
- in Blender > Edit > Preferences > Addon > Install
- select the .py files in the extracted "addon" folder , then enable them with checkbox on  
- addons appear as side panel in upper right of View next to the gizmo there is a "<" arrow expand to see side panel tabs "ZENV"

# ADDONS

## TEXTURE
- [texture_proj_cam](addon/z_blender_TEX_texture_proj_cam.py) - texture projection from camera - creates square orthographic camera from current view , and the camera projects image onto mesh baking to texture . workflow similar to "quick edits" in texture paint mode , now with permanent cameras
- [texture_variant_view](addon/z_blender_TEX_texture_variant_view.py) - specify a folder of textures , then with a mesh selected can quickly cycle through them applied to the mesh , ranking them into subfolders . useful for visualizing and choosing the best from many synthesized texture variants

## MESH
- [separate_by_material](addon/z_blender_MESH_separate_by_material.py) - for each material detach mesh into parts 
- [separate_by_UV](addon/z_blender_MESH_separate_by_UV.py) - for each uv island detach mesh into parts
- [split_by_uv_quadrant](addon/z_blender_MESH_split_by_uv_quadrant.py) - split mesh along UV seams and transform
- [separate_by_axis](addon/z_blender_MESH_separate_by_axis.py) - separate mesh parts by axis
- [rename_objects_by_material](addon/z_blender_MESH_rename_objects_by_material.py) - rename objects by material name
- [noise_displace](addon/z_blender_MESH_noise_displace.py) - 3D noise-based surface displacement with presets
- [cut_world_bricker](addon/z_blender_MESH_cut_world_bricker.py) - Cut mesh into brick like segments
- [to_UV_space](addon/z_blender_MESH_to_UV_space.py) - transform mesh to match UV layout in 3D space
- [wood_grain](addon/z_blender_MESH_wood_grain.py) - generate wood grain patterns on mesh

## GENERATIVE
- [tiles_from_textures](addon/z_blender_GEN_tiles_from_textures.py) - generate random tiles from texture set for tiling and seam blending review
- [ultima_landtiles](addon/z_blender_GEN_ultima_landtiles.py) - generate landtiles from ultima online map mul exported csv data of xyz and id 
- [vfx_slash](addon/z_blender_GEN_vfx_slash.py) - generate parabola based slash mesh effects

## MATERIAL
- [remove_unused_materials](addon/z_blender_MAT_remove_unused_materials.py) - remove unused materials 
- [consolidate_duplicate_mats](addon/z_blender_MAT_consolidate_duplicate_mats.py) - reduce to one material per texture
- [rename_material_by_texture](addon/z_blender_MAT_rename_material_by_texture.py) - rename material by texture name
- [rename_material_suffix](addon/z_blender_MAT_rename_material_suffix.py) - add or remove prefix or suffix on materials
- [remove_all_opacity](addon/z_blender_MAT_remove_all_opacity.py) - remove all opacity textures in materials
- [create_from_textures](addon/z_blender_MAT_create_from_textures.py) - create materials from texture folder
- [unlit_convert](addon/z_blender_MAT_unlit_convert.py) - convert all materials to emission for unlit render
- [remap_textures](addon/z_blender_MAT_remap_textures.py) - remap texture paths in materials

## EXPORT
- [export_objects_blend](addon/z_blender_EXPORT_export_objects_blend.py) - batch export selected objects to separate blend files

## VIEW 
- [view_flat_color_texture](addon/z_blender_VIEW_view_flat_color_texture.py) - quickview flat color texture , unlit viewmode
- [view_scale_clipping](addon/z_blender_VIEW_view_scale_clipping.py) - uses bounds of objects in scene to set near and far clipping

## UV 
- [uv_mirror_zero_pivot](addon/z_blender_UV_uv_mirror_zero_pivot.py) - U or V mirroring with pivot always at zero instead of the default of selected center

## RENDER
- [color](addon/z_blender_RENDER_color.py) - render color and depth passes
- [depth](addon/z_blender_RENDER_depth.py) - render depth passes

## CLEAN
- [scene_optimizer](addon/z_blender_CLEAN_scene_optimizer.py) - optimize scene by removing unused data and cleaning up scene structure

# EXAMPLE WORKFLOWS
- DIFFUSION CAMERA PROJECTION TEXTURING = [texture_proj_cam](addon/z_blender_TEX_texture_proj_cam.py) creates a square camera from view > [render_color_and_depth](addon/z_blender_RENDER_color_and_depth.py) renders color and depth images > img2img diffusion ( stable diffuson ) > [texture_proj_cam](addon/z_blender_TEX_texture_proj_cam.py) bakes texture projection from camera
- ZONE MESH SEPARATION = import mesh > consolidate materials > separate mesh by material > rename meshes by material name > rename materials with _MI suffix > export all to blends

# LICENSE
- free to all , [creative commons CC0](https://creativecommons.org/publicdomain/zero/1.0/) , free to re-distribute , attribution not required
