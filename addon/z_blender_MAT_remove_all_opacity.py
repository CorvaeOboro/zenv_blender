# MATERIAL REMOVE OPACITY ALL
# for each material in the scene remove all opacity nodes

bl_info = {
    "name": "MAT Remove Opacity",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Remove opacity textures and settings from materials"
}   

import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy.types import Panel, Operator, PropertyGroup

class MaterialOpacityUtils:
    """Utility functions for opacity management"""
    
    @staticmethod
    def remove_opacity_links(material):
        """Remove opacity links from a material"""
        if not material or not material.use_nodes:
            return False
            
        modified = False
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                # Handle alpha input
                alpha_socket = node.inputs.get('Alpha')
                if alpha_socket and alpha_socket.is_linked:
                    # Remove all links to alpha
                    for link in alpha_socket.links:
                        material.node_tree.links.remove(link)
                    modified = True
                    
                # Reset alpha value
                if alpha_socket:
                    alpha_socket.default_value = 1.0
                    modified = True
                    
                # Handle transmission input
                transmission_socket = node.inputs.get('Transmission')
                if transmission_socket and transmission_socket.is_linked:
                    # Remove all links to transmission
                    for link in transmission_socket.links:
                        material.node_tree.links.remove(link)
                    modified = True
                    
                # Reset transmission value
                if transmission_socket:
                    transmission_socket.default_value = 0.0
                    modified = True
                    
        return modified
    
    @staticmethod
    def cleanup_unused_nodes(material):
        """Remove unused texture and mix nodes"""
        if not material or not material.use_nodes:
            return False
            
        modified = False
        nodes_to_remove = []
        
        # Find unused nodes
        for node in material.node_tree.nodes:
            if node.type in {'TEX_IMAGE', 'MIX_RGB', 'MATH'}:
                # Check if node outputs are used
                outputs_used = False
                for output in node.outputs:
                    if output.links:
                        outputs_used = True
                        break
                        
                if not outputs_used:
                    nodes_to_remove.append(node)
        
        # Remove unused nodes
        for node in nodes_to_remove:
            material.node_tree.nodes.remove(node)
            modified = True
            
        return modified
    
    @staticmethod
    def process_material(material, props):
        """Process a single material"""
        if not material:
            return False
            
        modified = False
        
        # Remove opacity links
        if MaterialOpacityUtils.remove_opacity_links(material):
            modified = True
            
        # Clean up unused nodes
        if props.remove_unused and MaterialOpacityUtils.cleanup_unused_nodes(material):
            modified = True
            
        # Update blend mode
        if props.force_opaque and material.blend_method != 'OPAQUE':
            material.blend_method = 'OPAQUE'
            modified = True
            
        return modified

class ZENV_PG_OpacityRemovalProps(PropertyGroup):
    """Properties for opacity removal"""
    remove_unused: BoolProperty(
        name="Remove Unused Nodes",
        description="Remove unused texture and mix nodes after removing opacity",
        default=True
    )
    
    force_opaque: BoolProperty(
        name="Force Opaque Blend Mode",
        description="Set material blend mode to Opaque",
        default=True
    )
    
    scope: EnumProperty(
        name="Scope",
        description="Which materials to process",
        items=[
            ('SELECTED', "Selected Objects", "Process materials on selected objects only"),
            ('ALL', "All Materials", "Process all materials in the scene")
        ],
        default='SELECTED'
    )

class ZENV_OT_RemoveOpacity(Operator):
    """Remove opacity from materials"""
    bl_idname = "zenv.remove_opacity"
    bl_label = "Remove Opacity"
    bl_description = "Remove opacity textures and settings from materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if context.scene.zenv_opacity_props.scope == 'SELECTED':
            return context.selected_objects
        return True
    
    def execute(self, context):
        props = context.scene.zenv_opacity_props
        modified_count = 0
        
        # Get materials to process
        materials = set()
        if props.scope == 'SELECTED':
            for obj in context.selected_objects:
                if hasattr(obj.data, 'materials'):
                    for slot in obj.material_slots:
                        if slot.material:
                            materials.add(slot.material)
        else:
            materials.update(bpy.data.materials)
        
        # Process materials
        for mat in materials:
            if MaterialOpacityUtils.process_material(mat, props):
                modified_count += 1
        
        # Report results
        if modified_count > 0:
            self.report({'INFO'}, f"Modified {modified_count} materials")
        else:
            self.report({'INFO'}, "No materials needed modification")
            
        return {'FINISHED'}

class ZENV_PT_OpacityRemovalPanel(Panel):
    """Panel for opacity removal settings"""
    bl_label = "Remove Opacity"
    bl_idname = "ZENV_PT_opacity_removal"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_opacity_props
        
        # Settings
        box = layout.box()
        box.label(text="Settings")
        col = box.column(align=True)
        col.prop(props, "scope")
        col.prop(props, "remove_unused")
        col.prop(props, "force_opaque")
        
        # Operator
        box = layout.box()
        box.operator("zenv.remove_opacity")

def register():
    bpy.utils.register_class(ZENV_PG_OpacityRemovalProps)
    bpy.utils.register_class(ZENV_OT_RemoveOpacity)
    bpy.utils.register_class(ZENV_PT_OpacityRemovalPanel)
    bpy.types.Scene.zenv_opacity_props = bpy.props.PointerProperty(type=ZENV_PG_OpacityRemovalProps)

def unregister():
    bpy.utils.unregister_class(ZENV_PG_OpacityRemovalProps)
    bpy.utils.unregister_class(ZENV_OT_RemoveOpacity)
    bpy.utils.unregister_class(ZENV_PT_OpacityRemovalPanel)
    del bpy.types.Scene.zenv_opacity_props

if __name__ == "__main__":
    register()
