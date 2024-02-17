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
- rename objects by material name
- separate by material - for each material detach mesh into parts by assignment
## TEX
- texture projection from camera - creates square cameras from view , and cam projected image onto mesh baking to texture 
- texture variant view 
## MAT
- remove unused materials 
- consolidate duplicate materials - reduce to one material per texture
- rename material by texture
- rename material suffix - add or remove "_MI"
- remove all opacity textures in materials
## EXPORT
- batch export selected objects to separate blend files
## VIEW 
- quickview flat color texture - unlit viewmode
- clipping auto set - uses bounds of objects in scene to set near and far clipping


# EXAMPLE WORKFLOW
- import zone mesh > consolidate materials > separate mesh by material > rename meshes by material name > rename materials with _MI suffix > export all to blends
- create square camera from view > render color and depth > img2img diffusion ( stable diffuson ) > bake texture projection from cam 
- mesh cleaning 

# LICENSE
- free to all , [creative commons CC0](https://creativecommons.org/publicdomain/zero/1.0/) , free to re-distribute , attribution not required
