#region META
bl_info = {
    "name": 'MAT Consolidate Materials by Texture',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Consolidates materials based on base color texture',
    "status": 'working',
    "approved": True,
    "group": 'Material',
    "group_prefix": 'MAT',
    "group_order": 40,
    "addon_order": 20,
    "tags": ['material', 'consolidate', 'duplicate', 'texture', 'cleanup', 'optimize'],
    "description_short": 'reduce to one material per texture',
    "description_medium": 'Detects materials on the active mesh object that share the same base-color image texture, reassigns polygons from duplicate material slots to a single base slot, and purges the now-unused duplicate materials from bpy.data.materials (only if they have zero users and no fake user). Safe for multi-object scenes - only the active object is modified.',
    "description_long": """
MATERIAL CONSOLIDATE BY TEXTURE
 consolidates materials based on base color texture
useful for cleaning up duplicate materials
""",
    "image_overview": 'zenv_blender_MAT_consolidate_duplicate_mats.png',
    "addon_image": 'zenv_blender_MAT_consolidate_duplicate_mats.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
#endregion


#region OP
# Operator that consolidates duplicate materials by base-color texture.

class ZENV_OT_ConsolidateMaterials(bpy.types.Operator):
    """Consolidate materials by their base color texture"""
    bl_idname = "zenv.consolidatematerials_consolidate"
    bl_label = "Consolidate Materials by Texture"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def consolidate_materials_by_texture(cls, context):
        """Consolidate materials on the active object based on base color texture.

        Only the active object's material slots are modified. Materials that
        are no longer used anywhere in the file (including by other objects)
        may be purged from ``bpy.data.materials`` at the end, but materials
        still referenced elsewhere are left intact.

        Returns a tuple ``(slots_reassigned, materials_purged)``.
        """
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or obj.data is None:
            return 0, 0

        mats = obj.data.materials
        if len(mats) < 2:
            return 0, 0

        # Build: texture_image_name -> list of slot indices whose material
        # uses that image as Principled Base Color.
        texture_to_slots = {}
        for slot_index, mat in enumerate(mats):
            if mat is None or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if node.type != 'BSDF_PRINCIPLED':
                    continue
                base_color = node.inputs.get('Base Color')
                if base_color is None or not base_color.links:
                    continue
                tex_node = base_color.links[0].from_node
                if tex_node.type == 'TEX_IMAGE' and tex_node.image is not None:
                    texture_to_slots.setdefault(tex_node.image.name, []).append(slot_index)
                break

        slots_reassigned = 0
        purge_candidates = set()

        for texture_name, slot_indices in texture_to_slots.items():
            if len(slot_indices) < 2:
                continue

            # Pick the base slot: prefer a slot whose material name exactly
            # matches the texture name, otherwise the first slot.
            base_slot = slot_indices[0]
            for si in slot_indices:
                if mats[si] is not None and mats[si].name == texture_name:
                    base_slot = si
                    break
            base_mat = mats[base_slot]
            if base_mat is None:
                continue

            duplicate_slots = {si for si in slot_indices if si != base_slot}
            if not duplicate_slots:
                continue

            # Track materials that will no longer be referenced by this obj
            # so we can consider them for a global purge afterwards.
            for si in duplicate_slots:
                dup_mat = mats[si]
                if dup_mat is not None and dup_mat != base_mat:
                    purge_candidates.add(dup_mat)

            # Reassign polygon material indices from duplicate slots to base.
            for poly in obj.data.polygons:
                if poly.material_index in duplicate_slots:
                    poly.material_index = base_slot
                    slots_reassigned += 1

            # Point the duplicate slots at the base material so this object
            # no longer references the duplicates at all. This is what drops
            # the user count for the duplicate materials.
            for si in duplicate_slots:
                if mats[si] != base_mat:
                    mats[si] = base_mat

        # Only purge materials from the blend file when nothing else in the
        # scene references them. This prevents silently wiping material
        # assignments on other objects.
        purged = 0
        for mat in list(purge_candidates):
            if mat.users == 0 and not mat.use_fake_user:
                try:
                    bpy.data.materials.remove(mat)
                    purged += 1
                except (RuntimeError, ReferenceError):
                    pass

        return slots_reassigned, purged

    def execute(self, context):
        try:
            slots_reassigned, purged = self.consolidate_materials_by_texture(context)
            if slots_reassigned == 0 and purged == 0:
                self.report({'INFO'}, "No duplicate base-color textures found to consolidate")
            else:
                self.report(
                    {'INFO'},
                    f"Consolidated: reassigned {slots_reassigned} polygons, purged {purged} unused materials",
                )
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error consolidating materials: {str(e)}")
            return {'CANCELLED'}
#endregion


#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_ConsolidateMaterials_Panel(bpy.types.Panel):
    """Panel for material consolidation tools"""
    bl_label = "MAT Consolidate Materials"
    bl_idname = "ZENV_PT_consolidate_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        layout.operator("zenv.consolidatematerials_consolidate", icon='NODE_MATERIAL')
#endregion


#region REG
classes = (
    ZENV_OT_ConsolidateMaterials,
    ZENV_PT_ConsolidateMaterials_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
#endregion
