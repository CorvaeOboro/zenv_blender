# ZENV BLENDER
blender addons focused on singular features of 3d modelling , materials , and textures

[DOWNLOAD]( https://github.com/CorvaeOboro/zenv_blender/archive/refs/heads/main.zip ) 

# INSTALL 
- download and extract folder to local filepath
- in Blender > Edit > Preferences > Addon 
- select the .py files in the extracted addon folder , then check them on to install
- addons appear in View on side panel "ZENV"

# ADDONS
## MESH
- [rename_objects_by_material](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MESH_rename_objects_by_material.py) - rename objects by material name
- [separate_by_material](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MESH_separate_by_material.py) -  for each material detach mesh into parts by assignment
## TEX
- [texture_proj_cam](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_TEX_texture_proj_cam.py) -  texture projection from camera - creates square cameras from view , and camera projected image onto mesh baking to texture .
- [texture_variant_view](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_TEX_texture_variant_view.py) - specify a folder of textures , then with a mesh selected can quickly cycle through them applied to the mesh , ranking them into subfolders. useful for visualizing and choosing the best from many synthesized texture variants .
## MAT
- [remove_unused_materials](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_remove_unused_materials) - remove unused materials 
- [consolidate_duplicate_mats](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_consolidate_duplicate_mats) - reduce to one material per texture
- [rename_material_by_texture](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_rename_material_by_texture.py) - rename material by texture name
- [rename_material_suffix](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_rename_material_suffix.py) - add or remove "_MI" suffix on materials
- [remove_all_opacity](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_remove_all_opacity.py) - remove all opacity textures in materials
- [create_from_textures](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_MAT_create_from_textures.py) - create materials from texture folder
## EXPORT
- [export_objects_blend](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_EXPORT_export_objects_blend.py) - batch export selected objects to separate blend files
## VIEW 
- [view_flat_color_texture](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_VIEW_view_flat_color_texture.py) - quickview flat color texture - unlit viewmode
- [view_scale_clipping](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_VIEW_view_scale_clipping.py) - uses bounds of objects in scene to set near and far clipping
## UV 
- [uv_mirror_zero_pivot](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_UV_uv_mirror_zero_pivot.py) - U or V mirroring with pivot always at zero instead of the default of selected center
## RENDER
- [render_color_and_depth](https://github.com/CorvaeOboro/zenv_blender/blob/main/addon/z_blender_RENDER_color_and_depth.py) - with object selected renders a depth image auto fit to object bounds , and a flat shaded color render . useful for use with cam projected texture of diffusion depth controlnet .


# EXAMPLE WORKFLOWS
- ZONE MESH SEPARATION = import mesh > consolidate materials > separate mesh by material > rename meshes by material name > rename materials with _MI suffix > export all to blends
- DIFFUSION CAMERA PROJECTION TEXTURING = create square camera from view > render color and depth > img2img diffusion ( stable diffuson ) > bake texture projection from cam 

# LICENSE
- free to all , [creative commons CC0](https://creativecommons.org/publicdomain/zero/1.0/) , free to re-distribute , attribution not required
