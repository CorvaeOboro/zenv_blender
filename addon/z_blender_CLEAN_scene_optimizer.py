#region META
bl_info = {
    "name": 'CLEAN Scene Optimizer',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260822',
    "description": 'Tools for cleaning and optimizing scene data including unused textures, materials, and mesh data',
    "status": 'working',
    "approved": True,
    "group": 'Clean',
    "group_prefix": 'CLEAN',
    "group_order": 100,
    "addon_order": 10,
    "tags": ['clean', 'optimize', 'texture', 'material', 'mesh', 'vertex group', 'duplicate'],
    "description_short": 'optimize removing unused material , textures , and mesh data',
    "description_medium": 'Scene cleanup utility that removes unused/missing textures, unused/duplicate materials, optimizes mesh data (doubles, loose verts, normals), and strips empty vertex groups. Respects fake-user pins and library-linked data.',
    "description_long": """
CLEAN Scene Optimizer
- Removing unused textures and materials
- Cleaning up missing texture references
- Consolidating duplicate materials
- Optimizing mesh data
- Removing empty vertex groups
""",
    "image_overview": 'zenv_blender_CLEAN_scene_optimizer.png',
    "addon_image": 'zenv_blender_CLEAN_scene_optimizer.png',
    "location": 'View3D > ZENV',
}
#endregion

#region IMPORT
import bpy
import bmesh
import re
from pathlib import Path
#endregion


#region TEX
# Texture cleanup operators - remove unused and missing image datablocks.
# Workflow stage 1: clean up texture references before touching materials.

#region UNUSED
class ZENV_OT_CleanUnusedTextures(bpy.types.Operator):
    """Remove unused image textures from the blend file.

    Scans all materials for image texture nodes and removes any images that are
    not used in any material. Only removes unpacked images to avoid data loss.
    """
    bl_idname = "zenv.clean_unused_textures"
    bl_label = "Remove Unused Textures"
    bl_description = "Remove image datablocks not referenced by any material, world, light, compositor, node group, or brush"
    bl_options = {'REGISTER', 'UNDO'}

    #region SCAN
    # Node types that hold a direct reference to an image datablock.
    # Includes TEX_ENVIRONMENT (world/environment textures) alongside the
    # usual TEX_IMAGE so sky/environment maps are not deleted as "unused".
    _IMAGE_NODE_TYPES = {'TEX_IMAGE', 'TEX_ENVIRONMENT'}

    @staticmethod
    def _collect_node_trees():
        """Yield every node tree in the file that may reference images.

        Covers material, world, light and compositor trees as well as all
        node groups (which can be nested inside any of the above and used
        as assets on their own). Scene compositor trees are reached via
        ``scene.compositing_node_group`` (Blender 5.0+) or
        ``scene.node_tree`` (Blender 4.x).
        """
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree is not None:
                yield mat.node_tree
        for world in bpy.data.worlds:
            if world.use_nodes and world.node_tree is not None:
                yield world.node_tree
        for light in bpy.data.lights:
            if light.use_nodes and light.node_tree is not None:
                yield light.node_tree
        for ng in bpy.data.node_groups:
            if ng is not None:
                yield ng
        for scene in bpy.data.scenes:
            # Blender 5.0+ removed ``scene.node_tree`` and replaced it with
            # ``scene.compositing_node_group`` (the compositor node tree is
            # now a standalone datablock, also reachable via
            # ``bpy.data.node_groups`` above). Support both APIs so the
            # addon keeps working on Blender 4.x and 5.x.
            nt = getattr(scene, 'compositing_node_group', None)
            if nt is None:
                nt = getattr(scene, 'node_tree', None)
            if nt is not None:
                yield nt

    def find_texture_users(self):
        """Find all image datablocks referenced by any node tree or brush.

        Scans material, world, light, compositor and node-group trees for
        ``TEX_IMAGE`` / ``TEX_ENVIRONMENT`` nodes, plus brush texture slots.

        Returns:
            set: Image datablocks that are currently in use somewhere.
        """
        used_images = set()
        for nt in self._collect_node_trees():
            for node in nt.nodes:
                if node.type in self._IMAGE_NODE_TYPES and node.image is not None:
                    used_images.add(node.image)
        # Brushes can reference textures that in turn reference images.
        for br in bpy.data.brushes:
            for slot in getattr(br, "texture_slots", None) or ():
                if slot is None:
                    continue
                tex = slot.texture
                if tex is not None and tex.image is not None:
                    used_images.add(tex.image)
        return used_images
    #endregion

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
            if img in used_images:
                continue
            # Never drop images the user pinned, packed data,
            # or library-linked data (Blender refuses to remove linked
            # data anyway, but skipping keeps the reported count honest).
            if img.packed_file:
                continue
            if img.use_fake_user:
                continue
            if img.library is not None:
                continue
            bpy.data.images.remove(img)
            removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} unused textures")
        return {'FINISHED'}
#endregion

#region MISSING
class ZENV_OT_CleanMissingTextures(bpy.types.Operator):
    """Remove image datablocks whose source file is missing on disk.

    Scans all image datablocks and removes any that reference files that no
    longer exist on disk. Only removes unpacked, non-library, non-fake-user
    images whose source is FILE to avoid data loss. Nodes that referenced
    the removed image will have their ``image`` slot cleared.
    """
    bl_idname = "zenv.clean_missing_textures"
    bl_label = "Clean Missing Textures"
    bl_description = (
        "Remove image datablocks whose referenced file is missing on disk"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator.

        Removes image datablocks whose source file cannot be resolved on disk.

        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        # Image sources that do not correspond to a file on disk and must
        # never be removed because their filepath is empty / missing.
        SKIP_SOURCES = {'GENERATED', 'VIEWER', 'RENDER_RESULT', 'SEQUENCE', 'MOVIE'}

        removed_count = 0
        for img in bpy.data.images[:]:
            # Skip packed images (data lives inside the .blend).
            if img.packed_file:
                continue
            # Skip images that are not disk-backed by nature.
            if getattr(img, 'source', 'FILE') in SKIP_SOURCES:
                continue
            # Skip images with no filepath assigned at all (generated, etc.).
            if not img.filepath:
                continue
            # Skip library-linked images (Blender won't remove them anyway).
            if img.library is not None:
                continue
            # Respect user-pinned images.
            if img.use_fake_user:
                continue
            # Only remove if the referenced file truly cannot be resolved.
            if not Path(bpy.path.abspath(img.filepath)).exists():
                bpy.data.images.remove(img)
                removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} missing texture references")
        return {'FINISHED'}
#endregion
#endregion


#region MAT
# Material cleanup operators - remove unused materials and merge duplicates.
# Workflow stage 2: after textures are clean, consolidate materials.

#region ORPHAN
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

        # Find all used materials across every object type that exposes
        # material slots (meshes, curves, NURBS, texts, metaballs,
        # volumes, grease pencil, hair, point clouds, ...). Restricting to
        # MESH only would delete materials still assigned to non-mesh
        # geometry.
        for obj in bpy.data.objects:
            slots = getattr(obj, "material_slots", None)
            if not slots:
                continue
            used_materials.update(
                slot.material for slot in slots if slot.material is not None
            )

        # Remove unused materials
        removed_count = 0
        for mat in bpy.data.materials[:]:
            if mat in used_materials:
                continue
            # Respect user-pinned materials, library-linked data, and
            # library overrides - none of these should be deleted without a report.
            if mat.use_fake_user:
                continue
            if mat.library is not None or mat.override_library is not None:
                continue
            bpy.data.materials.remove(mat)
            removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} unused materials")
        return {'FINISHED'}
#endregion

#region DUP
class ZENV_OT_CleanDuplicateMaterials(bpy.types.Operator):
    """Consolidate duplicate materials based on name AND properties.

    Finds materials whose names share the same base name once the trailing
    Blender `.001`/`.002`/... numeric suffix is stripped, and whose shader
    setup is equivalent. Only materials that match are merged.
    """
    bl_idname = "zenv.clean_duplicate_materials"
    bl_label = "Remove Duplicate Materials"
    bl_description = "Merge materials with the same base name AND equivalent node/texture setup"
    bl_options = {'REGISTER', 'UNDO'}

    # Matches only the Blender auto-generated numeric suffix at the end,
    # e.g. `wood.oak.001` -> base `wood.oak`, `mat` -> base `mat`.
    _BLENDER_DUPE_SUFFIX_RE = re.compile(r"\.\d+$")

    #region SIG
    @classmethod
    def _base_name(cls, name):
        """Strip only the trailing `.NNN` Blender dedup suffix, if present."""
        return cls._BLENDER_DUPE_SUFFIX_RE.sub("", name)

    @staticmethod
    def _node_signature(node):
        """Build a name-independent fingerprint of a single node.

        Captures the node type, image reference (for TEX_IMAGE), the
        referenced node group (for group nodes), and the default values of
        all inputs. Node **names** are deliberately excluded because
        Blender auto-renames nodes on paste/duplicate (``Image Texture.001``)
        and would otherwise prevent equivalent materials from matching.
        """
        entry = [node.type]
        if node.type == 'TEX_IMAGE':
            entry.append(node.image.name if node.image is not None else None)
            entry.append(
                getattr(node.image.colorspace_settings, 'name', None)
                if node.image is not None else None
            )
        elif node.type == 'GROUP':
            # Reference the node-group datablock by name so two materials
            # using different group datablocks are NOT considered equivalent.
            nt = getattr(node, 'node_tree', None)
            entry.append(nt.name if nt is not None else None)
        for inp in node.inputs:
            try:
                val = inp.default_value
            except AttributeError:
                continue
            if hasattr(val, '__iter__') and not isinstance(val, str):
                entry.append(tuple(round(float(v), 6) for v in val))
            else:
                try:
                    entry.append(round(float(val), 6))
                except (TypeError, ValueError):
                    entry.append(val)
        return tuple(entry)

    @classmethod
    def _material_signature(cls, mat):
        """Build a comparable fingerprint of a material's shader setup.

        Two materials with the same signature are considered equivalent and
        safe to merge. The signature intentionally focuses on user-visible
        shading state (nodes, links, image datablocks, key input values)
        and ignores volatile state like node positions **and node names**.

        Links are expressed by a stable per-node index derived from the
        sorted node signatures (not by node name), so renaming a node no
        longer invalidates equivalence.
        """
        sig = [
            bool(mat.use_nodes),
            mat.blend_method,
            round(float(mat.diffuse_color[0]), 6),
            round(float(mat.diffuse_color[1]), 6),
            round(float(mat.diffuse_color[2]), 6),
            round(float(mat.diffuse_color[3]), 6),
            round(float(mat.metallic), 6),
            round(float(mat.roughness), 6),
        ]

        if mat.use_nodes and mat.node_tree is not None:
            nt = mat.node_tree
            # Build a name -> stable index map by sorting on the
            # name-independent node signature. Nodes with identical
            # signatures share an index bucket; ties are broken by name
            # purely to make the sort deterministic.
            node_sigs = {n.name: cls._node_signature(n) for n in nt.nodes}
            ordered_names = sorted(
                nt.nodes,
                key=lambda n: (node_sigs[n.name], n.name)
            )
            name_to_index = {n.name: i for i, n in enumerate(ordered_names)}

            sig.append(tuple(node_sigs[n.name] for n in ordered_names))

            link_sig = tuple(sorted(
                (name_to_index[l.from_node.name], l.from_socket.identifier,
                 name_to_index[l.to_node.name], l.to_socket.identifier)
                for l in nt.links
            ))
            sig.append(link_sig)

        return tuple(sig)
    #endregion

    def execute(self, context):
        """Execute the operator.

        Merges duplicate materials and updates all object references.

        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        # Group materials by (base_name, signature) so only truly equivalent
        # duplicates are merged together.
        groups = {}
        for mat in bpy.data.materials:
            # Never touch linked / override materials.
            if mat.library is not None or mat.override_library is not None:
                continue
            base_name = self._base_name(mat.name)
            try:
                sig = self._material_signature(mat)
            except Exception:
                # If we cannot build a signature for any reason, be safe and
                # leave this material alone.
                continue
            groups.setdefault((base_name, sig), []).append(mat)

        # Merge duplicates inside each equivalence group.
        merged_count = 0
        for (_base_name, _sig), mats in groups.items():
            if len(mats) <= 1:
                continue
            # Prefer the material whose name exactly matches the base (no
            # numeric suffix) so the canonical name is retained.
            mats.sort(key=lambda m: (self._BLENDER_DUPE_SUFFIX_RE.search(m.name) is not None, m.name))
            primary_mat = mats[0]
            for dup_mat in mats[1:]:
                # Replace all uses of the duplicate with the primary material
                # across every object type that exposes material slots
                # (meshes, curves, NURBS, texts, metaballs, volumes,
                # grease pencil, hair, point clouds, ...).
                for obj in bpy.data.objects:
                    slots = getattr(obj, "material_slots", None)
                    if not slots:
                        continue
                    for slot in slots:
                        if slot.material == dup_mat:
                            slot.material = primary_mat
                # Also patch any meshes that reference the material directly
                # (e.g. via mesh.materials) in case an object isn't the user.
                for mesh in bpy.data.meshes:
                    for i, m in enumerate(mesh.materials):
                        if m == dup_mat:
                            mesh.materials[i] = primary_mat
                if dup_mat.users == 0 and not dup_mat.use_fake_user:
                    bpy.data.materials.remove(dup_mat)
                    merged_count += 1
                # If the duplicate still has users (e.g. fake_user pin or
                # a reference that could not be repointed), it was not
                # merged away - do not inflate the count.

        self.report({'INFO'}, f"Merged {merged_count} duplicate materials")
        return {'FINISHED'}
#endregion
#endregion


#region MESH
# Mesh data cleanup operator - doubles, loose verts, degenerate edges, normals.
# Workflow stage 3: after materials are clean, optimize mesh geometry.

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
        "Remove doubles, dissolve loose vertices, and (optionally) "
        "recalculate normals outward"
    )
    bl_options = {'REGISTER', 'UNDO'}

    #region PROPS
    # Operator properties so users can tune behavior instead of relying on
    # hardcoded values. Defaults preserve the original behavior.
    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description="Maximum distance between two vertices to be merged",
        default=0.0001,
        min=0.0,
        precision=5,
        unit='LENGTH',
    )
    dissolve_distance: bpy.props.FloatProperty(
        name="Dissolve Distance",
        description="Maximum distance for degenerate-edge dissolution",
        default=0.0001,
        min=0.0,
        precision=5,
        unit='LENGTH',
    )
    recalc_normals: bpy.props.BoolProperty(
        name="Recalculate Normals",
        description=(
            "Recalculate normals to face outward. Disable to preserve "
            "intentionally inward-facing normals (skydomes, inverted hulls, "
            "backface-culled interiors)"
        ),
        default=True,
    )
    #endregion

    def execute(self, context):
        """Execute the operator.

        Cleans up mesh data for mesh objects in the current scene.

        This includes:
        - Removing duplicate vertices
        - Dissolving degenerate edges
        - Removing loose geometry
        - Recalculating normals

        Returns:
            set: {'FINISHED'} if the operation was successful.
        """
        scene = context.scene
        view_layer = context.view_layer

        # Remember state that may change so it can be restored afterwards.
        original_active = view_layer.objects.active
        original_selection = [o for o in context.selected_objects]
        original_mode = 'OBJECT'
        if original_active is not None:
            original_mode = original_active.mode

        # Anything not in OBJECT mode will choke mode_set calls below.
        if original_active is not None and original_active.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass

        # Collect safe candidates: mesh objects in this scene, not library
        # data, not hidden from the view layer, and each unique mesh only
        # once (multi-user meshes must not be cleaned more than once).
        seen_meshes = set()
        candidates = []
        for obj in scene.objects:
            if obj.type != 'MESH':
                continue
            if obj.library is not None or obj.override_library is not None:
                continue
            me = obj.data
            if me is None or me.library is not None:
                continue
            if obj.name not in view_layer.objects:
                continue  # Not editable in this view layer.
            if not obj.visible_get(view_layer=view_layer):
                continue  # Respect user's hidden state.
            if me.name in seen_meshes:
                continue
            seen_meshes.add(me.name)
            candidates.append(obj)

        cleaned_objects = 0
        failures = 0

        for obj in candidates:
            me = obj.data

            # Step 1: clean up with bmesh in OBJECT mode (no operator calls,
            # so the bmesh stays valid throughout).
            try:
                bpy.ops.object.select_all(action='DESELECT')
                view_layer.objects.active = obj
                obj.select_set(True)

                bm = bmesh.new()
                try:
                    bm.from_mesh(me)
                    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=self.merge_distance)
                    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=self.dissolve_distance)
                    loose_verts = [v for v in bm.verts if not v.link_edges]
                    if loose_verts:
                        bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
                    bm.to_mesh(me)
                    me.update()
                finally:
                    bm.free()

                # Step 2: recalc normals via operator. Skipped when the user
                # disabled it (e.g. to preserve intentionally inward-facing
                # normals on skydomes / inverted hulls). Otherwise done in
                # EDIT mode with select-all so the operator has something to
                # act on, then return to OBJECT mode.
                if self.recalc_normals:
                    bpy.ops.object.mode_set(mode='EDIT')
                    try:
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.mesh.normals_make_consistent(inside=False)
                    finally:
                        bpy.ops.object.mode_set(mode='OBJECT')

                cleaned_objects += 1
            except Exception as e:
                failures += 1
                # Make sure the object is not stuck in EDIT mode.
                if obj.mode != 'OBJECT':
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except RuntimeError:
                        pass
                self.report({'WARNING'}, f"Skipped '{obj.name}': {e}")

        # Restore original selection / active / mode as best possible.
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except RuntimeError:
            pass
        for o in original_selection:
            if o and o.name in view_layer.objects:
                try:
                    o.select_set(True)
                except RuntimeError:
                    pass
        if original_active is not None and original_active.name in view_layer.objects:
            view_layer.objects.active = original_active
            if original_mode != 'OBJECT' and original_active.mode != original_mode:
                try:
                    bpy.ops.object.mode_set(mode=original_mode)
                except RuntimeError:
                    pass

        if failures:
            self.report({'INFO'}, f"Cleaned mesh data for {cleaned_objects} objects ({failures} skipped)")
        else:
            self.report({'INFO'}, f"Cleaned mesh data for {cleaned_objects} objects")
        return {'FINISHED'}
#endregion


#region VGRP
# Vertex group cleanup operator - remove empty groups not referenced by
# modifiers/drivers. Workflow stage 4: final pass after geometry is clean.

class ZENV_OT_RemoveEmptyVertexGroups(bpy.types.Operator):
    """Remove empty vertex groups from all meshes.

    Scans all mesh objects and removes any vertex groups that have no vertices
    assigned to them with non-zero weights. Vertex groups referenced **by
    name** from modifiers, drivers, shape keys, or the object's active vertex
    color/weight masks are preserved to avoid breaking those references.
    """
    bl_idname = "zenv.remove_empty_vertex_groups"
    bl_label = "Remove Empty Vertex Groups"
    bl_description = "Remove vertex groups that have no vertices assigned and are not referenced by modifiers/drivers"
    bl_options = {'REGISTER', 'UNDO'}

    # Weight threshold below which a vertex is considered unweighted. Using a
    # small epsilon instead of an exact 0.0 compare avoids floating-point
    # noise being treated as a real assignment.
    _WEIGHT_EPSILON = 1e-6

    # Modifier RNA property names that store a vertex-group *name* and would
    # be invalidated if the referenced group were deleted. This is a conservative
    # superset covering the common deform / mask / weight modifiers.
    _MODIFIER_VG_PROPS = (
        'vertex_group', 'subtarget',
        'mask_tex_uv_layer',  # UV layer, not VG - kept out by name check
    )

    #region REFS
    @classmethod
    def _referenced_group_names(cls, obj):
        """Return the set of vertex-group names referenced by name from any
        modifier, driver, shape key, or the object's paint mask on `obj`.

        Vertex groups are referenced by name (not by index) in many places,
        so deleting a group whose name is still cited elsewhere invalidates
        those references without warning.
        """
        referenced = set()

        # Modifiers: scan every RNA property whose value matches a group name.
        vg_names = {g.name for g in obj.vertex_groups}
        for mod in obj.modifiers:
            for prop in cls._MODIFIER_VG_PROPS:
                val = getattr(mod, prop, None)
                if isinstance(val, str) and val in vg_names:
                    referenced.add(val)
            # Some modifiers expose extra vertex-group inputs as collections
            # of name strings (e.g. Vertex Weight Mix/Proximity).
            for extra in ('vertex_group_a', 'vertex_group_b'):
                val = getattr(mod, extra, None)
                if isinstance(val, str) and val in vg_names:
                    referenced.add(val)

        # Shape keys can target a vertex group by name.
        shape_keys = getattr(obj.data, 'shape_keys', None)
        if shape_keys is not None:
            for kb in shape_keys.key_blocks:
                vg = getattr(kb, 'vertex_group', None)
                if isinstance(vg, str) and vg in vg_names:
                    referenced.add(vg)

        # Drivers on this object's animation data may reference a vertex
        # group name via F-Curve variable targets.
        ad = obj.animation_data
        if ad is not None and ad.drivers:
            for fc in ad.drivers:
                drv = fc.driver
                for var in drv.variables:
                    for tgt in var.targets:
                        # `data_path` like 'pose.bones["..."].vertex_groups["GroupName"].weight'
                        path = getattr(tgt, 'data_path', None) or ''
                        # Cheap substring scan; the name is quoted in the path.
                        for name in vg_names:
                            if name and name in path:
                                referenced.add(name)

        # Active vertex group / weight paint mask.
        active_vg = getattr(obj, 'vertex_group', None)
        if isinstance(active_vg, str) and active_vg in vg_names:
            referenced.add(active_vg)

        return referenced
    #endregion

    def execute(self, context):
        """Removes empty vertex groups from all mesh objects."""
        removed_count = 0
        skipped_referenced = 0
        for obj in context.scene.objects:
            if obj.type != 'MESH':
                continue
            if obj.library is not None or obj.override_library is not None:
                continue
            if not obj.vertex_groups:
                continue

            referenced_names = self._referenced_group_names(obj)

            # Single pass over the mesh data: for each vertex, record which
            # groups it has non-zero weight in.
            used_group_indices = set()
            all_group_count = len(obj.vertex_groups)
            for vert in obj.data.vertices:
                for vg in vert.groups:
                    if abs(vg.weight) > self._WEIGHT_EPSILON:
                        used_group_indices.add(vg.group)
                # Early out once every group has been seen.
                if len(used_group_indices) >= all_group_count:
                    break

            empty_groups = [g for g in obj.vertex_groups
                            if g.index not in used_group_indices]
            for group in empty_groups:
                if group.name in referenced_names:
                    skipped_referenced += 1
                    continue
                obj.vertex_groups.remove(group)
                removed_count += 1

        if skipped_referenced:
            self.report(
                {'INFO'},
                f"Removed {removed_count} empty vertex groups "
                f"({skipped_referenced} kept: referenced by modifiers/drivers)"
            )
        else:
            self.report({'INFO'}, f"Removed {removed_count} empty vertex groups")
        return {'FINISHED'}
#endregion


#region PANEL
# UI panel - displayed at the bottom of the file so the core operator logic
# is near the top and the UI layer is last, matching the workflow ordering.

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
#endregion


#region REG
# Registration - classes tuple, register/unregister, __main__ entry point.
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
#endregion
