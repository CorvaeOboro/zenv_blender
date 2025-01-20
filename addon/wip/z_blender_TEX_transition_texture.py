
bl_info = {
    "name": "Transition Texture Baker",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > ZENV",
    "description": " Bake textures of connected meshes to create a tranition texture of equivalent texel density."
}   

import bpy
import bmesh

class BakeTransitionTexture(bpy.types.Operator):
    """Bake a transition texture for blending between two textures"""
    bl_idname = "object.bake_transition_texture"
    bl_label = "Bake Transition Texture"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if len(selected_objects) != 2:
            self.report({'ERROR'}, "Select exactly two meshes")
            return {'CANCELLED'}


        # Create vertex groups in the original meshes
        self.create_vertex_groups(selected_objects)

        # Duplicate meshes
        primary_mesh, secondary_mesh = self.duplicate_meshes(context)

        # Perform UV sewing and relaxation
        joined_mesh = self.perform_uv_operations(context, primary_mesh, secondary_mesh)

        # Bake the texture
        self.bake_texture(context, joined_mesh)  # Use the joined mesh reference

        # Cleanup
        self.cleanup_meshes(joined_mesh)  # Adjust cleanup to handle the joined mesh


        return {'FINISHED'}

    def create_vertex_groups(self, objects):
        for obj in objects:
            if "PrimaryGroup" not in obj.vertex_groups:
                obj.vertex_groups.new(name="PrimaryGroup")
            if "SecondaryGroup" not in obj.vertex_groups:
                obj.vertex_groups.new(name="SecondaryGroup")


    def duplicate_meshes(self, context):
        bpy.ops.object.duplicate()
        return context.selected_objects

    def perform_uv_operations(self, context, joined_mesh):
        # Join meshes for UV sewing
        bpy.context.view_layer.objects.active = primary_mesh
        primary_mesh.select_set(True)
        secondary_mesh.select_set(True)
        bpy.ops.object.join()  # Join meshes

        # Switch to edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        # Get the mesh data
        mesh = bmesh.from_edit_mesh(primary_mesh.data)
        mesh.faces.ensure_lookup_table()

        # Deselect all in edit mode
        for face in mesh.faces:
            face.select_set(False)

        # Get the secondary vertex group
        sec_group = primary_mesh.vertex_groups.get("SecondaryGroup")
        if sec_group is not None:
            sec_group_index = sec_group.index

            # Ensure the deform layer exists
            if mesh.verts.layers.deform.active is not None:
                deform_layer = mesh.verts.layers.deform.active

                # Select faces based on vertex group membership
                for face in mesh.faces:
                    for vert in face.verts:
                        vert_groups = vert[deform_layer]
                        if sec_group_index in vert_groups and vert_groups[sec_group_index] > 0:
                            face.select_set(True)
                            break

        # Update the mesh
        bmesh.update_edit_mesh(primary_mesh.data)

        # Switch back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        # After performing operations, update the reference to the joined mesh
        return joined_mesh  # Return the updated joined mesh



    def bake_texture(self, context, mesh):
        # Setup texture baking and perform the baking operation
        # Ensure mesh is selected and active
        bpy.context.view_layer.objects.active = mesh
        mesh.select_set(True)

        # Create a new image to bake to
        image_name = "Bake_Image"
        image = bpy.data.images.new(image_name, width=1024, height=1024)

        # Set up nodes for baking
        mat = self.setup_material_for_baking(mesh, image)

        # Set up bake settings
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.bake_type = 'COMBINED'
        bpy.context.scene.render.bake.use_pass_direct = False
        bpy.context.scene.render.bake.use_pass_indirect = False

        # Perform the bake
        bpy.ops.object.bake(type='COMBINED')

        # Save the baked image
        image.filepath_raw = "//" + image_name + "_blend.png"
        image.file_format = 'PNG'
        image.save()

    def setup_material_for_baking(self, mesh, image):
        if not mesh.data.materials:
            mat = bpy.data.materials.new(name="Bake_Mat")
            mesh.data.materials.append(mat)
        else:
            mat = mesh.data.materials[0]

        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        for node in nodes:
            nodes.remove(node)

        # Create a new texture node and set the image
        tex_node = nodes.new(type='ShaderNodeTexImage')
        tex_node.image = image
        tex_node.select = True
        nodes.active = tex_node

        return mat

    def cleanup_meshes(self, primary_mesh, secondary_mesh):
        bpy.data.objects.remove(secondary_mesh)
        bpy.data.objects.remove(primary_mesh)

class ZENV_PT_Panel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "ZENV"
    bl_idname = "ZENV_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        self.layout.operator("object.bake_transition_texture")

def register():
    bpy.utils.register_class(BakeTransitionTexture)
    bpy.utils.register_class(ZENV_PT_Panel)

def unregister():
    bpy.utils.unregister_class(BakeTransitionTexture)
    bpy.utils.unregister_class(ZENV_PT_Panel)

if __name__ == "__main__":
    register()
