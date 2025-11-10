bl_info = {
    "name": 'ULTIMA Map from CSV',
    "blender": (2, 93, 0),
    "category": 'ZENV',
    "version": '20241209',
    "description": 'Generate a map from Ultima land textures for texture painting and debugging with improved performance and UV mapping.',
    "status": 'wip',
    "approved": True,
    "group": 'Ultima',
    "group_prefix": 'ULTIMA',
    "location": 'View3D > Tool',
}

import bpy
import csv
import os

# Define default paths (can be overridden via the file selector)
DEFAULT_TEXTURE_FOLDER_PATH = "D:/ULTIMA/MODS/ultima_online_mods/ENV/ENV_HeartWood"
DEFAULT_CSV_FILEPATH = "D:/ULTIMA/MODS/ultima_online_mods/ENV/ENV_HeartWood/map5.csv"

def create_materials(texture_names, texture_folder_path, messages):
    """
    Create materials for each unique texture name.

    Args:
        texture_names (set): A set of unique texture names.
        texture_folder_path (str): Path to the folder containing textures.
        messages (list): List to append messages for reporting.

    Returns:
        dict: A dictionary mapping texture names to Blender material objects.
    """
    materials = {}
    for texture_name in texture_names:
        texture_path = os.path.join(texture_folder_path, texture_name)
        if not os.path.exists(texture_path):
            messages.append(('WARNING', f"Texture file not found: {texture_name}."))
            continue
        
        # Create a new material
        mat = bpy.data.materials.new(name=texture_name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if not bsdf:
            messages.append(('WARNING', f"Principled BSDF not found in material: {texture_name}."))
            continue
        
        # Create and configure the image texture node
        tex_image = mat.node_tree.nodes.new('ShaderNodeTexImage')
        try:
            tex_image.image = bpy.data.images.load(texture_path)
        except Exception as e:
            messages.append(('WARNING', f"Failed to load texture {texture_name}: {e}"))
            continue
        
        # Link the texture to the BSDF node
        mat.node_tree.links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
        materials[texture_name] = mat
        messages.append(('INFO', f"Material created for texture: {texture_name}"))
    
    return materials

def read_csv_map(filepath):
    """
    Read the CSV and return map_data and messages.
    Handles two formats:
    1) x,y,z,texture_name
    2) x,y,z,Land_ID -> converts to a texture_name

    Args:
        filepath (str): Path to the CSV file.

    Returns:
        tuple: (map_data, messages)
            - map_data: List of dictionaries with keys x, y, z, texture_name.
            - messages: List of (severity, message) tuples.
    """
    map_data = []
    messages = []

    if not os.path.exists(filepath):
        messages.append(('ERROR', f"CSV file not found: {filepath}"))
        return map_data, messages

    try:
        with open(filepath, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            if not csv_reader.fieldnames:
                messages.append(('ERROR', "CSV file contains no headers."))
                return map_data, messages

            # Normalize field names to lowercase for case-insensitive matching
            field_names_lower = [f.lower() for f in csv_reader.fieldnames]

            has_texture_name = 'texture_name' in field_names_lower
            has_land_id = 'land_id' in field_names_lower
            expected_fields = {'x', 'y', 'z'}

            if not expected_fields.issubset(set(field_names_lower)):
                messages.append(('ERROR', "CSV missing required columns: x, y, z."))
                return map_data, messages

            if not has_texture_name and not has_land_id:
                messages.append(('ERROR', "CSV must contain either 'texture_name' or 'Land_ID' column."))
                return map_data, messages

            format_detected = "texture_name" if has_texture_name else "Land_ID"
            messages.append(('INFO', f"CSV format detected: {format_detected} based."))

            texture_names = set()

            for row in csv_reader:
                row_lower = {k.lower(): v for k, v in row.items()}

                # Parse coordinates
                try:
                    x = float(row_lower.get('x', ''))
                    y = float(row_lower.get('y', ''))
                    z = float(row_lower.get('z', ''))
                except ValueError:
                    messages.append(('WARNING', f"Invalid coordinates in row: {row}. Skipping."))
                    continue

                # Determine texture_name
                if has_texture_name:
                    texture_name = row_lower.get('texture_name', "").strip()
                    if not texture_name:
                        messages.append(('WARNING', f"Empty 'texture_name' in row: {row}. Skipping."))
                        continue
                else:
                    # Generate texture_name from Land_ID
                    land_id_str = row_lower.get('land_id', "").strip()
                    if not land_id_str.isdigit():
                        messages.append(('WARNING', f"Invalid 'Land_ID' in row: {row}. Skipping."))
                        continue
                    land_id = int(land_id_str)
                    hex_str = hex(land_id)[2:].upper().zfill(4)
                    texture_name = f"env_{land_id}_heartwood_A_0x{hex_str}.bmp"
                    messages.append(('INFO', f"Generated texture from Land_ID={land_id}: {texture_name}"))

                texture_names.add(texture_name)

                map_data.append({
                    "x": x,
                    "y": y,
                    "z": z,
                    "texture_name": texture_name
                })

            messages.append(('INFO', f"CSV parsing complete. Total valid entries: {len(map_data)}"))
    except Exception as e:
        messages.append(('ERROR', f"Failed to read CSV file: {e}"))

    return map_data, messages

def clear_scene():
    """
    Clears all mesh objects from the current scene.
    """
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def create_planes(map_data, materials, messages):
    """
    Create plane objects based on map_data and assign materials.

    Args:
        map_data (list): List of dictionaries with x, y, z, texture_name.
        materials (dict): Dictionary mapping texture_name to Blender material objects.
        messages (list): List to append messages for reporting.
    """
    current_collection = bpy.context.collection

    for entry in map_data:
        x = entry['x']
        y = entry['y']
        z = entry['z']
        texture_name = entry['texture_name']

        # Create mesh data for a plane
        mesh = bpy.data.meshes.new(name=f"Plane_{x}_{y}_{z}")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            [],
            [(0, 1, 2, 3)]
        )
        mesh.update()

        # Create UV map
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="UVMap")

        # Access the UV layer
        uv_layer = mesh.uv_layers.active.data

        # Assign UV coordinates (default UVs)
        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                vert_idx = mesh.loops[loop_idx].vertex_index
                if vert_idx == 0:
                    uv_layer[loop_idx].uv = (0.0, 0.0)
                elif vert_idx == 1:
                    uv_layer[loop_idx].uv = (1.0, 0.0)
                elif vert_idx == 2:
                    uv_layer[loop_idx].uv = (1.0, 1.0)
                elif vert_idx == 3:
                    uv_layer[loop_idx].uv = (0.0, 1.0)

        # **Apply UV Transformations: Mirroring on X-axis and Rotating 180 Degrees**
        for loop in mesh.loops:
            uv = uv_layer[loop.index].uv
            # Mirror on X-axis: Flip the U coordinate
            uv.x = 1.0 - uv.x
            # Rotate 180 degrees: Flip both U and V coordinates
            uv.y = 1.0 - uv.y
            uv_layer[loop.index].uv = uv

        # **Optional: Further UV Adjustments**
        # Uncomment and modify the following code if additional UV transformations are needed.

        # Example: Additional rotation or scaling
        # for loop in mesh.loops:
        #     uv = uv_layer[loop.index].uv
        #     # Rotate UVs 90 degrees clockwise
        #     rotated_u = uv.y
        #     rotated_v = 1.0 - uv.x
        #     uv_layer[loop.index].uv = (rotated_u, rotated_v)
        
        # Example: Mirror UVs vertically
        # for loop in mesh.loops:
        #     uv = uv_layer[loop.index].uv
        #     uv.y = 1.0 - uv.y
        #     uv_layer[loop.index].uv = uv

        # Create an object with the mesh
        obj = bpy.data.objects.new(name=f"x{int(x)}_y{int(y)}_z{int(z)}", object_data=mesh)
        obj.location = (x, y, z)

        # Assign material if available
        mat = materials.get(texture_name)
        if mat:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)
            messages.append(('INFO', f"Assigned material '{mat.name}' to object '{obj.name}'."))
        else:
            messages.append(('WARNING', f"No material found for texture '{texture_name}'. Object '{obj.name}' remains untextured."))

        # Link the object to the current collection
        current_collection.objects.link(obj)

class ZENV_OT_LoadData(bpy.types.Operator):
    bl_idname = "zenv.load_data"
    bl_label = "Load Data from CSV"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        subtype="FILE_PATH",
        default=DEFAULT_CSV_FILEPATH,
        name="CSV File",
        description="Path to the CSV file containing map data."
    )

    texture_folder_path: bpy.props.StringProperty(
        subtype="DIR_PATH",
        default=DEFAULT_TEXTURE_FOLDER_PATH,
        name="Texture Folder",
        description="Path to the folder containing texture files."
    )

    def execute(self, context):
        # Read CSV data
        map_data, messages = read_csv_map(self.filepath)

        # Report messages from CSV reading
        for severity, msg in messages:
            self.report({severity}, msg)

        if not map_data:
            self.report({'WARNING'}, "No valid data to process from CSV.")
            return {'CANCELLED'}

        # Collect unique texture names
        unique_textures = set(entry['texture_name'] for entry in map_data)

        # Create materials
        materials = create_materials(unique_textures, self.texture_folder_path, messages)

        # Report messages from material creation
        for severity, msg in messages:
            self.report({severity}, msg)

        if not materials:
            self.report({'WARNING'}, "No materials were created. Aborting object creation.")
            return {'CANCELLED'}

        # Clear existing mesh objects
        self.report({'INFO'}, "Clearing existing mesh objects from the scene...")
        clear_scene()

        # Create planes and assign materials
        create_planes(map_data, materials, messages)

        # Report final messages
        for severity, msg in messages:
            self.report({severity}, msg)

        self.report({'INFO'}, "Map data loaded and objects created successfully.")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ZENV_PT_Panel(bpy.types.Panel):
    bl_label = "ZENV Panel"
    bl_idname = "ZENV_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.load_data")

def register():
    bpy.utils.register_class(ZENV_OT_LoadData)
    bpy.utils.register_class(ZENV_PT_Panel)

def unregister():
    bpy.utils.unregister_class(ZENV_OT_LoadData)
    bpy.utils.unregister_class(ZENV_PT_Panel)

if __name__ == "__main__":
    register()
