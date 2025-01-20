import bpy

# Function to remove default objects
def clear_scene():
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='MESH')
    bpy.ops.object.delete()
    for light in bpy.data.lights:
        bpy.data.lights.remove(light)
    for camera in bpy.data.cameras:
        bpy.data.cameras.remove(camera)

# Import OBJ function
def import_obj(obj_path):
    bpy.ops.wm.obj_import(filepath=obj_path)

# Unwrap model function
def unwrap_model():
    obj = bpy.context.selected_objects[-1]
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
    bpy.ops.object.mode_set(mode='OBJECT')

# Setup material and shaders using vertex color
def setup_material():
    obj = bpy.context.view_layer.objects.active
    if len(obj.data.materials) == 0:
        mat = bpy.data.materials.new(name="ColorAttributeMaterial")
        obj.data.materials.append(mat)
    else:
        mat = obj.data.materials[0]
    
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    # Create Principled BSDF shader node
    shader = nodes.new(type='ShaderNodeBsdfPrincipled')
    
    # Create Vertex Color node
    vertex_color = nodes.new(type='ShaderNodeVertexColor')
    
    # Create Material Output node
    material_output = nodes.new(type='ShaderNodeOutputMaterial')

    # Connect Vertex Color node to Principled BSDF shader node
    mat.node_tree.links.new(vertex_color.outputs['Color'], shader.inputs['Base Color'])
    mat.node_tree.links.new(shader.outputs['BSDF'], material_output.inputs['Surface'])



# Setup bake function
def bake_texture(image_name, image_path):
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'CPU'
    image = bpy.data.images.new(image_name, width=1024, height=1024)
    image.filepath_raw = image_path
    image.file_format = 'PNG'
    obj = bpy.context.view_layer.objects.active
    mat = obj.active_material
    node_tree = mat.node_tree
    node = node_tree.nodes.new('ShaderNodeTexImage')
    node.select = True
    node_tree.nodes.active = node
    node.image = image
    
    # Save the Blender file before baking
    blend_file_path = image_path.rsplit('.', 1)[0] + ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend_file_path)

    # Proceed with the baking operation
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=False)
    image.save_render(filepath=image_path)


# Export to FBX function
def export_fbx(fbx_path):
    bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=True)

# Main function to run the operations
def main(obj_path, image_name, image_path, fbx_path):
    clear_scene()
    import_obj(obj_path)
    # Make sure the imported object is selected
    bpy.context.view_layer.objects.active = bpy.context.selected_objects[-1]
    unwrap_model()
    setup_material()
    bake_texture(image_name, image_path)
    export_fbx(fbx_path)

# Example usage with absolute paths
obj_path = r'E:\ComfyUI_windows_portable\ComfyUI\output\meshsave_00033.obj'
image_name = 'meshsave_00034'
image_path = r'E:\ComfyUI_windows_portable\ComfyUI\output\meshsave_00033.png'
fbx_path = r'E:\ComfyUI_windows_portable\ComfyUI\output\meshsave_00033.fbx'
main(obj_path, image_name, image_path, fbx_path)