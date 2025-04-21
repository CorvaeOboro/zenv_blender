# TEXTURE TRANSITION by EDGE EXTRUSION
# two meshes that are touching , one is extended onto other 
# baking onto the other as part of creating a seamless texture transition

bl_info = {
    "name": "TEX Transition Texture Extrude",
    "category": "ZENV",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Crete a tranisiton between two meshes by extruding the edge and baking",
}

import bpy
import bmesh
import logging
import os
from datetime import datetime
from bpy.props import BoolProperty, FloatProperty, StringProperty, IntProperty
import mathutils
import math

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

class ZENV_TransitionTextureExtend_Logger:
    """Logger class for transition texture operations"""
    
    @staticmethod
    def log_info(message, phase="INFO"):
        """Log a message with a phase prefix"""
        print(f"[{phase}] {message}")
    
    @staticmethod
    def log_error(message, phase="ERROR"):
        """Log an error message with a phase prefix"""
        print(f"[{phase}] {message}")
# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_TransitionTextureExtend_Properties:
    """Property management for texture transition addon"""
    
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_transition_debug = BoolProperty(
            name="Debug Mode",
            description="Keep temporary objects for debugging",
            default=False
        )
        
        bpy.types.Scene.zenv_transition_offset = FloatProperty(
            name="Bake Offset",
            description="Offset distance for baking cage",
            default=0.001,
            min=0.0001,
            max=0.1
        )
        
        bpy.types.Scene.zenv_transition_resolution = IntProperty(
            name="Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        
        bpy.types.Scene.zenv_transition_samples = IntProperty(
            name="Samples",
            description="Number of samples for baking",
            default=32,
            min=1,
            max=4096
        )
        
        bpy.types.Scene.zenv_transition_margin = IntProperty(
            name="Margin",
            description="Margin size in pixels for bake result",
            default=16,
            min=0,
            max=64
        )
        
        bpy.types.Scene.zenv_transition_use_denoising = BoolProperty(
            name="Use Denoising",
            description="Enable denoising for bake result",
            default=True
        )
        
        bpy.types.Scene.zenv_transition_save_path = StringProperty(
            name="Save Path",
            description="Directory path to save baked textures",
            subtype='DIR_PATH',
            default="//textures"
        )
        
        # Step toggles
        bpy.types.Scene.zenv_step_separate = BoolProperty(
            name="1. Separate Meshes",
            description="Separate meshes at shared edge",
            default=True
        )
        
        bpy.types.Scene.zenv_step_extend = BoolProperty(
            name="2. Extend Edge",
            description="Extend source mesh over target",
            default=True
        )
        
        bpy.types.Scene.zenv_step_uvs = BoolProperty(
            name="3. Extend UVs",
            description="Extend UVs of source mesh",
            default=True
        )
        
        bpy.types.Scene.zenv_step_cage = BoolProperty(
            name="4. Create Cage",
            description="Create baking cage",
            default=True
        )
        
        bpy.types.Scene.zenv_step_bake = BoolProperty(
            name="5. Bake Texture",
            description="Bake texture from source to target",
            default=True
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_transition_debug
        del bpy.types.Scene.zenv_transition_offset
        del bpy.types.Scene.zenv_transition_resolution
        del bpy.types.Scene.zenv_transition_samples
        del bpy.types.Scene.zenv_transition_margin
        del bpy.types.Scene.zenv_transition_use_denoising
        del bpy.types.Scene.zenv_transition_save_path
        del bpy.types.Scene.zenv_step_separate
        del bpy.types.Scene.zenv_step_extend
        del bpy.types.Scene.zenv_step_uvs
        del bpy.types.Scene.zenv_step_cage
        del bpy.types.Scene.zenv_step_bake

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_TransitionTextureExtend_Utils:
    """Utility functions for texture transition"""
    
    @staticmethod
    def get_shared_edges(source_obj, target_obj):
        """Find edges that are touching between two meshes"""
        ZENV_TransitionTextureExtend_Logger.log_info(
            f"Starting edge analysis between {source_obj.name} and {target_obj.name}", 
            "EDGE DETECTION"
        )
        
        bm1 = bmesh.new()
        bm1.from_mesh(source_obj.data)
        bm1.verts.ensure_lookup_table()
        bm1.edges.ensure_lookup_table()
        
        bm2 = bmesh.new()
        bm2.from_mesh(target_obj.data)
        bm2.verts.ensure_lookup_table()
        bm2.edges.ensure_lookup_table()
        
        ZENV_TransitionTextureExtend_Logger.log_info(
            f"Source mesh: {len(bm1.edges)} edges, {len(bm1.verts)} vertices", "MESH INFO"
        )
        ZENV_TransitionTextureExtend_Logger.log_info(
            f"Target mesh: {len(bm2.edges)} edges, {len(bm2.verts)} vertices", "MESH INFO"
        )
        
        shared_edges = []
        threshold = 0.001  # Distance threshold for vertex proximity
        
        # For each edge in source mesh
        for e1_idx, e1 in enumerate(bm1.edges):
            v1_start = e1.verts[0].co.copy()
            v1_end = e1.verts[1].co.copy()
            e1_dir = (v1_end - v1_start).normalized()
            e1_length = (v1_end - v1_start).length
            
            # Find matching vertices in target mesh
            start_matches = []
            end_matches = []
            
            for v2_idx, v2 in enumerate(bm2.verts):
                dist_to_start = (v2.co - v1_start).length
                if dist_to_start < threshold:
                    start_matches.append((v2_idx, v2.co.copy(), dist_to_start))
                
                dist_to_end = (v2.co - v1_end).length
                if dist_to_end < threshold:
                    end_matches.append((v2_idx, v2.co.copy(), dist_to_end))
            
            # Only proceed if both vertices have matches
            if start_matches and end_matches:
                min_distance = float('inf')
                closest_edge = None
                
                for e2_idx, e2 in enumerate(bm2.edges):
                    v2_start = e2.verts[0].co.copy()
                    v2_end = e2.verts[1].co.copy()
                    e2_dir = (v2_end - v2_start).normalized()
                    e2_length = (v2_end - v2_start).length
                    
                    # Check if this edge connects any matching vertices
                    s_idx = e2.verts[0].index
                    e_idx_ = e2.verts[1].index
                    
                    for sm in start_matches:
                        for em in end_matches:
                            if ((s_idx == sm[0] and e_idx_ == em[0]) or
                                (s_idx == em[0] and e_idx_ == sm[0])):
                                
                                dot_product = abs(e1_dir.dot(e2_dir))
                                length_diff = abs(e1_length - e2_length)
                                
                                # If nearly parallel and same length
                                if dot_product > 0.99 and length_diff < threshold:
                                    dist = (sm[2] + em[2]) / 2.0
                                    if dist < min_distance:
                                        min_distance = dist
                                        closest_edge = (e2_idx, e2, {
                                            'source_start': v1_start,
                                            'source_end': v1_end,
                                            'target_start': v2_start,
                                            'target_end': v2_end,
                                            'distance': dist,
                                            'edge_length': e1_length,
                                            'edge_dir': e1_dir
                                        })
                
                if closest_edge:
                    shared_edges.append((
                        e1.index,
                        closest_edge[0],
                        closest_edge[2]
                    ))
        
        bm1.free()
        bm2.free()
        
        ZENV_TransitionTextureExtend_Logger.log_info(
            f"Found {len(shared_edges)} shared edges", "EDGE DETECTION COMPLETE"
        )
        return shared_edges

    @staticmethod
    def extend_mesh_at_edge(obj, edge_data, direction, distance):
        """Extend mesh from specified edges using BMesh extrude operator"""
        logger = ZENV_TransitionTextureExtend_Logger
        logger.log_info(f"Starting mesh extension for {obj.name}", "MESH EXTENSION")
        
        # Create copy of object with clear name
        new_name = f"{obj.name}_extended"
        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj.name = new_name
        new_obj.data.name = f"{new_name}_mesh"
        bpy.context.collection.objects.link(new_obj)
        
        edge_indices = [edge_info[0] for edge_info in edge_data]
        logger.log_info(f"Processing {len(edge_indices)} edges for extension", "MESH EXTENSION")
        
        bm = bmesh.new()
        bm.from_mesh(new_obj.data)
        
        # Ensure lookup tables are updated
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Get UV layer
        uv_layer = bm.loops.layers.uv.verify()
        
        for edge_idx, edge_info in enumerate(edge_data):
            logger.log_info(f"Processing edge {edge_idx + 1}/{len(edge_data)}", "MESH EXTENSION")
            
            # Ensure lookup tables after any potential topology changes
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            try:
                edge = bm.edges[edge_indices[edge_idx]]
                edge_dir = edge_info[2]['edge_dir']
                edge_length = edge_info[2]['edge_length']
                
                # Normal perpendicular to edge in XY plane
                edge_normal = mathutils.Vector((-edge_dir.y, edge_dir.x, 0)).normalized()
                
                # Original midpoint
                orig_mid = (edge.verts[0].co + edge.verts[1].co) / 2
                
                # Decide extension direction
                extend_dir = edge_normal if direction > 0 else -edge_normal
                extend_dist = edge_length
                
                # Collect original UVs
                orig_uvs = {}
                uv_edge_verts = []
                for face in edge.link_faces:
                    for loop in face.loops:
                        orig_uvs[loop.vert.index] = loop[uv_layer].uv.copy()
                        if loop.vert in edge.verts:
                            uv_edge_verts.append((loop.vert.index, loop[uv_layer].uv.copy()))
                
                # Compute UV density
                uv_density = 1.0
                if len(uv_edge_verts) >= 2:
                    uv_edge_dir = (uv_edge_verts[1][1] - uv_edge_verts[0][1]).normalized()
                    uv_edge_length = (uv_edge_verts[1][1] - uv_edge_verts[0][1]).length
                    if edge_length != 0:
                        uv_density = uv_edge_length / edge_length
                    uv_normal = mathutils.Vector((-uv_edge_dir.y, uv_edge_dir.x))
                
                # Deselect all edges
                for e in bm.edges:
                    e.select = False
                edge.select = True
                
                # Store original geometry
                orig_verts = set(edge.verts)
                orig_faces = set(edge.link_faces)
                orig_edge_index = edge.index
                
                # Extrude
                ret = bmesh.ops.extrude_edge_only(bm, edges=[edge])
                
                # Ensure lookup tables after extrusion
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                
                # Collect new geometry
                new_verts = set()
                new_faces = set()
                new_edges = set()
                for elem in ret['geom']:
                    if isinstance(elem, bmesh.types.BMVert):
                        if elem not in orig_verts:
                            new_verts.add(elem)
                    elif isinstance(elem, bmesh.types.BMFace):
                        if elem not in orig_faces:
                            new_faces.add(elem)
                    elif isinstance(elem, bmesh.types.BMEdge):
                        if elem.index != orig_edge_index:
                            new_edges.add(elem)
                
                # Translate new vertices
                bmesh.ops.translate(
                    bm,
                    vec=extend_dir * extend_dist,
                    verts=list(new_verts)
                )
                
                # Update UVs for new geometry
                new_edge = None
                for e in new_edges:
                    if all(v in new_verts for v in e.verts):
                        new_edge = e
                        break
                
                if new_edge and len(uv_edge_verts) >= 2:
                    new_mid = (new_edge.verts[0].co + new_edge.verts[1].co) / 2
                    actual_offset = (new_mid - orig_mid).length
                    
                    uv_offset_length = actual_offset * uv_density
                    uv_offset_dir = uv_normal if direction > 0 else -uv_normal
                    uv_offset = uv_offset_dir * uv_offset_length
                    
                    # Update UVs
                    for face in new_faces:
                        for loop in face.loops:
                            if loop.vert in orig_verts:
                                if loop.vert.index in orig_uvs:
                                    loop[uv_layer].uv = orig_uvs[loop.vert.index].copy()
                            else:
                                for orig_vert in orig_verts:
                                    if (loop.vert.co - extend_dir * extend_dist - orig_vert.co).length < 0.0001:
                                        orig_uv = orig_uvs[orig_vert.index]
                                        loop[uv_layer].uv = orig_uv + uv_offset
                                        break
                
            except Exception as e:
                logger.log_error(f"Error processing edge {edge_idx + 1}: {str(e)}")
                continue
        
        # Final geometry update
        bm.normal_update()
        bm.to_mesh(new_obj.data)
        new_obj.data.update()
        bm.free()
        
        logger.log_info("Mesh extension complete", "MESH EXTENSION")
        return new_obj

    @staticmethod
    def extend_uvs(obj, edge_data, direction, distance):
        """
        Extend UVs from specified edges.
        Fixed bug where `edge_data` was overwritten with an empty list.
        """
        ZENV_TransitionTextureExtend_Logger.log_info(f"Starting UV extension on {obj.name}", "UV EXTENSION")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            bm.free()
            ZENV_TransitionTextureExtend_Logger.log_info("No active UV layer found, skipping UV extension", "UV EXTENSION")
            return obj
        
        # Build a reference of positions & UVs for each relevant edge
        processed_edge_data = []
        for e_info in edge_data:
            e_idx = e_info[0]
            edge = bm.edges[e_idx]
            
            # Grab edge vertices
            verts = edge.verts[:]
            
            # Store UV data
            uvs = {}
            for vert in verts:
                for loop in vert.link_loops:
                    if loop.face in edge.link_faces:  # or you can store all
                        uvs[loop.vert.index] = loop[uv_layer].uv.copy()
            
            processed_edge_data.append({
                'verts': [v.co.copy() for v in verts],
                'uvs': uvs
            })
        
        bm.free()
        
        # Switch to EDIT mode
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        
        # Find and select those edges
        for edge_info in processed_edge_data:
            for edge in bm.edges:
                v1_pos = edge.verts[0].co
                v2_pos = edge.verts[1].co
                ref_v1, ref_v2 = edge_info['verts']
                
                # Check both possible orders
                match1 = ((v1_pos - ref_v1).length < 0.0001 and
                          (v2_pos - ref_v2).length < 0.0001)
                match2 = ((v1_pos - ref_v2).length < 0.0001 and
                          (v2_pos - ref_v1).length < 0.0001)
                
                if match1 or match2:
                    edge.select = True
                    break
        
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()
        
        # Back to EDIT mode for UV transform
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Example approach: move selected UVs by (direction.to_2d() * distance)
        # in the UV editor
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.transform.translate(
            value=(direction.x * distance, direction.y * distance, 0),
            orient_type='GLOBAL'
        )
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        ZENV_TransitionTextureExtend_Logger.log_info("UV extension complete", "UV EXTENSION")
        return obj
    
    @staticmethod
    def create_bake_cage(obj, offset):
        """Create offset cage for baking"""
        cage = obj.copy()
        cage.data = obj.data.copy()
        bpy.context.scene.collection.objects.link(cage)
        
        mod = cage.modifiers.new(name="Cage", type='SOLIDIFY')
        mod.thickness = offset
        mod.offset = 1.0
        
        return cage
    
    @staticmethod
    def prepare_mesh_for_baking(obj):
        """Prepare mesh for baking by setting correct shading and normals"""
        orig_shade_smooth = [p.use_smooth for p in obj.data.polygons]
        
        # Set flat shading
        for p in obj.data.polygons:
            p.use_smooth = False
            
        obj.data.use_auto_smooth = False
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.shade_flat()
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        
        return orig_shade_smooth

    @staticmethod
    def restore_mesh_shading(obj, orig_shade_smooth):
        """Restore original shading settings"""
        for p, smooth in zip(obj.data.polygons, orig_shade_smooth):
            p.use_smooth = smooth

    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking to avoid black bakes"""
        logger = ZENV_TransitionTextureExtend_Logger
        logger.log_info("Setting up render settings for baking...")
        
        # Store original settings
        original_engine = context.scene.render.engine
        logger.log_info(f"Original render engine: {original_engine}")
        
        # Set to Cycles
        context.scene.render.engine = 'CYCLES'
        logger.log_info("Set render engine to CYCLES")
        
        if hasattr(context.scene, 'cycles'):
            # Configure Cycles settings
            context.scene.cycles.device = 'GPU'
            context.scene.cycles.samples = context.scene.zenv_transition_samples
            logger.log_info(f"Cycles samples set to: {context.scene.cycles.samples}")
            
            # Set bake type and passes
            context.scene.cycles.bake_type = 'DIFFUSE'
            context.scene.render.bake.use_pass_direct = False
            context.scene.render.bake.use_pass_indirect = False
            context.scene.render.bake.use_pass_color = True
            logger.log_info("Configured for diffuse color-only baking (no lighting)")
            
            # Quality settings
            context.scene.cycles.use_denoising = False  # Disable denoising for baking
            context.scene.cycles.use_high_quality_normals = True
            logger.log_info("Set high quality normals, disabled denoising for baking")
        
        # Bake settings
        context.scene.render.bake.margin = context.scene.zenv_transition_margin
        context.scene.render.bake.use_clear = True
        context.scene.render.bake.use_selected_to_active = True
        context.scene.render.bake.max_ray_distance = 0.1  # Small ray distance for planes
        logger.log_info(f"Bake settings: margin={context.scene.render.bake.margin}, ray_distance=0.1")
        
        return original_engine

    @staticmethod
    def setup_bake_materials(source_obj, target_obj, context):
        """Setup temporary material for baking while preserving original materials"""
        logger = ZENV_TransitionTextureExtend_Logger
        logger.log_info("Setting up bake materials...")
        
        # Ensure texture directory exists
        texture_dir = bpy.path.abspath(context.scene.zenv_transition_save_path)
        if not os.path.exists(texture_dir):
            try:
                os.makedirs(texture_dir)
                logger.log_info(f"Created texture directory: {texture_dir}")
            except Exception as e:
                logger.log_error(f"Failed to create texture directory: {str(e)}")
                texture_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
                os.makedirs(texture_dir, exist_ok=True)
                logger.log_info(f"Using fallback directory: {texture_dir}")
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bake_transition_{timestamp}.png"
        texture_path = os.path.join(texture_dir, filename)
        logger.log_info(f"Texture will be saved to: {texture_path}")
        
        # Store original materials
        source_original_mats = [mat for mat in source_obj.data.materials]
        target_original_mats = [mat for mat in target_obj.data.materials]
        logger.log_info(f"Stored original materials - Source: {len(source_original_mats)}, Target: {len(target_original_mats)}")
        
        # Create temporary bake material
        temp_bake_mat = bpy.data.materials.new(name="__TEMP_BAKE_MATERIAL__")
        temp_bake_mat.use_nodes = True
        nodes = temp_bake_mat.node_tree.nodes
        nodes.clear()
        
        # Create image node for baking
        tex_image = nodes.new('ShaderNodeTexImage')
        bake_image = bpy.data.images.new(
            filename,
            width=context.scene.zenv_transition_resolution,
            height=context.scene.zenv_transition_resolution,
            alpha=True,
            float_buffer=True
        )
        bake_image.filepath_raw = texture_path
        bake_image.file_format = 'PNG'
        
        tex_image.image = bake_image
        tex_image.select = True
        nodes.active = tex_image
        
        # Temporarily assign bake material to target
        if not target_obj.data.materials:
            target_obj.data.materials.append(temp_bake_mat)
        else:
            target_obj.data.materials[0] = temp_bake_mat
        
        logger.log_info("Temporary bake material setup complete")
        
        # Return data needed for cleanup
        return {
            'bake_image': bake_image,
            'temp_material': temp_bake_mat,
            'source_materials': source_original_mats,
            'target_materials': target_original_mats
        }

    @staticmethod
    def cleanup_material_slots(obj):
        """Remove unused material slots from the object"""
        logger = ZENV_TransitionTextureExtend_Logger
        
        # Must be in object mode
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Store active object
        active_obj = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = obj
        
        try:
            # Get initial slot count
            initial_slots = len(obj.material_slots)
            logger.log_info(f"Cleaning up material slots on {obj.name} (initial slots: {initial_slots})")
            
            # Remove empty slots first
            empty_slots = [i for i, slot in enumerate(obj.material_slots) if not slot.material]
            if empty_slots:
                logger.log_info(f"Found {len(empty_slots)} empty material slots")
                for i in reversed(empty_slots):  # Remove from highest index to lowest
                    obj.active_material_index = i
                    bpy.ops.object.material_slot_remove()
            
            # Now remove unused slots
            used_indices = set()
            if obj.type == 'MESH':
                for polygon in obj.data.polygons:
                    used_indices.add(polygon.material_index)
            
            # Remove slots that aren't used by any polygons
            unused_slots = [i for i in range(len(obj.material_slots)) if i not in used_indices]
            if unused_slots:
                logger.log_info(f"Found {len(unused_slots)} unused material slots")
                for i in reversed(unused_slots):  # Remove from highest index to lowest
                    obj.active_material_index = i
                    bpy.ops.object.material_slot_remove()
            
            final_slots = len(obj.material_slots)
            if final_slots < initial_slots:
                logger.log_info(f"Removed {initial_slots - final_slots} material slots from {obj.name}")
            else:
                logger.log_info(f"No unused material slots found on {obj.name}")
            
        finally:
            # Restore active object
            bpy.context.view_layer.objects.active = active_obj

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_TransitionTextureExtend_Bake(bpy.types.Operator):
    """Bake texture transition between selected meshes"""
    bl_idname = "zenv.transition_bake_extend"
    bl_label = "Bake Transition"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        sel = context.selected_objects
        return (
            len(sel) == 2 and
            all(obj.type == 'MESH' for obj in sel) and
            context.active_object in sel
        )
    
    def execute(self, context):
        try:
            # Get objects based on selection order
            # Active object (last selected) will be the target
            # Other selected object will be the source to extend
            target_obj = context.active_object
            source_obj = [obj for obj in context.selected_objects if obj != target_obj][0]
            
            logger = ZENV_TransitionTextureExtend_Logger
            logger.log_info(f"Using selection order for baking:")
            logger.log_info(f"Source object (will be extended): {source_obj.name}")
            logger.log_info(f"Target object (active, bake target): {target_obj.name}")
            
            debug_mode = context.scene.zenv_transition_debug
            temp_objects = []
            
            # Store original settings
            original_engine = context.scene.render.engine
            original_device = (
                context.scene.cycles.device if hasattr(context.scene, 'cycles') else None
            )
            
            try:
                # 0) Clean up unused material slots
                logger.log_info("Step 0: Cleaning up unused material slots...")
                ZENV_TransitionTextureExtend_Utils.cleanup_material_slots(source_obj)
                ZENV_TransitionTextureExtend_Utils.cleanup_material_slots(target_obj)
                
                # 1) Setup global render/bake settings
                original_engine = ZENV_TransitionTextureExtend_Utils.setup_render_settings(context)
                
                # 2) Step 1: find shared edges
                if context.scene.zenv_step_separate:
                    ZENV_TransitionTextureExtend_Logger.log_info("Step 1: Finding shared edges...")
                    shared_edges = ZENV_TransitionTextureExtend_Utils.get_shared_edges(source_obj, target_obj)
                    if not shared_edges:
                        self.report({'ERROR'}, "No shared edges found")
                        return {'CANCELLED'}
                    ZENV_TransitionTextureExtend_Logger.log_info(f"Found {len(shared_edges)} shared edges")
                else:
                    shared_edges = []
                
                # 3) Step 2: Extend only the source mesh
                if context.scene.zenv_step_extend and shared_edges:
                    ZENV_TransitionTextureExtend_Logger.log_info("Step 2: Extending source mesh...")
                    # For direction, we do (target - source).normalized()
                    direction_vec = (target_obj.location - source_obj.location).normalized()
                    
                    source_extended = ZENV_TransitionTextureExtend_Utils.extend_mesh_at_edge(
                        source_obj,
                        shared_edges,
                        direction_vec,
                        1.0
                    )
                    
                    if debug_mode:
                        temp_objects.append(source_extended)
                else:
                    source_extended = source_obj
                
                # 4) Step 3: Extend UVs on the newly extended source
                if context.scene.zenv_step_uvs and shared_edges:
                    ZENV_TransitionTextureExtend_Logger.log_info("Step 3: Extending UVs...")
                    # Use the same direction, but maybe a smaller distance for UV
                    source_uvs = ZENV_TransitionTextureExtend_Utils.extend_uvs(
                        source_extended,
                        shared_edges,
                        (target_obj.location - source_obj.location).normalized(),
                        0.2
                    )
                    if debug_mode:
                        temp_objects.append(source_uvs)
                else:
                    source_uvs = source_extended
                
                # 5) Step 4: Create cage (optional)
                cage_obj = None
                if context.scene.zenv_step_cage and shared_edges:
                    ZENV_TransitionTextureExtend_Logger.log_info("Step 4: Creating bake cage...")
                    cage_obj = ZENV_TransitionTextureExtend_Utils.create_bake_cage(
                        source_uvs,
                        context.scene.zenv_transition_offset
                    )
                    if debug_mode:
                        temp_objects.append(cage_obj)
                
                # 6) Step 5: Bake
                if context.scene.zenv_step_bake:
                    ZENV_TransitionTextureExtend_Logger.log_info("Step 5: Setting up bake materials...")
                    
                    # Use the extended mesh if available, otherwise use original source
                    bake_source = source_uvs if 'source_uvs' in locals() else source_obj
                    logger.log_info(f"Using {'extended' if bake_source != source_obj else 'original'} source mesh for baking")
                    
                    bake_data = ZENV_TransitionTextureExtend_Utils.setup_bake_materials(
                        bake_source,  # Use extended mesh
                        target_obj,
                        context
                    )
                    
                    logger.log_info("Starting bake process...")
                    logger.log_info("Verifying object selection and active states:")
                    logger.log_info(f"Source object (for baking): {bake_source.name}")
                    logger.log_info(f"Target object: {target_obj.name}")
                    
                    # Correct selection order: extended source selected, target active
                    bpy.ops.object.select_all(action='DESELECT')
                    bake_source.select_set(True)  # Select extended mesh
                    target_obj.select_set(True)
                    bpy.context.view_layer.objects.active = target_obj
                    
                    logger.log_info("Selection state set for baking")
                    logger.log_info(f"Active object: {bpy.context.view_layer.objects.active.name}")
                    logger.log_info(f"Selected objects: {[obj.name for obj in bpy.context.selected_objects]}")
                    
                    # Perform bake
                    try:
                        bpy.ops.object.bake(
                            type='DIFFUSE',
                            pass_filter={'COLOR'},
                            use_selected_to_active=True,
                            margin=context.scene.zenv_transition_margin,
                            use_clear=True
                        )
                        
                        logger.log_info("Bake operation completed")
                        
                        if bake_data['bake_image'].has_data:
                            try:
                                bake_data['bake_image'].save()
                                logger.log_info(f"Baked texture saved to: {bake_data['bake_image'].filepath_raw}")
                                try:
                                    bake_data['bake_image'].pack()
                                    logger.log_info("Image packed successfully")
                                except Exception as e:
                                    logger.log_info(f"Warning: Could not pack image: {str(e)}")
                            except Exception as e:
                                logger.log_error(f"Failed to save baked image: {str(e)}")
                                raise
                        else:
                            logger.log_error("Bake failed - no image data generated")
                            raise Exception("No image data after baking")
                        
                    except Exception as e:
                        logger.log_error(f"Bake operation failed: {str(e)}")
                        raise
                    
                    finally:
                        # Restore original materials
                        logger.log_info("Restoring original materials...")
                        target_obj.data.materials.clear()
                        for mat in bake_data['target_materials']:
                            target_obj.data.materials.append(mat)
                        
                        # Remove temporary material
                        bpy.data.materials.remove(bake_data['temp_material'])
                        logger.log_info("Cleanup completed")
                
                # Cleanup duplicates if not in debug mode
                if not debug_mode:
                    for obj_del in temp_objects:
                        if obj_del and obj_del != source_obj:
                            bpy.data.objects.remove(obj_del, do_unlink=True)
                    if cage_obj and cage_obj != source_obj:
                        bpy.data.objects.remove(cage_obj, do_unlink=True)
                
                logger.log_info("Texture transition complete!")
                return {'FINISHED'}
            
            finally:
                # Restore original render settings
                context.scene.render.engine = original_engine
                if hasattr(context.scene, 'cycles') and original_device:
                    context.scene.cycles.device = original_device
        
        except Exception as e:
            logger.log_error(f"Error during texture transition: {str(e)}")
            self.report({'ERROR'}, f"Transition failed: {str(e)}")
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_TextureTransition_Panel(bpy.types.Panel):
    """Panel for texture transition generation and settings"""
    bl_label = "TEX Texture Transition"
    bl_idname = "ZENV_PT_texture_transition"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "zenv_transition_debug")
        
        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(scene, "zenv_transition_offset")
        box.prop(scene, "zenv_transition_resolution")
        box.prop(scene, "zenv_transition_samples")
        box.prop(scene, "zenv_transition_margin")
        box.prop(scene, "zenv_transition_use_denoising")
        box.prop(scene, "zenv_transition_save_path")
        
        box = layout.box()
        box.label(text="Process Steps:")
        box.prop(scene, "zenv_step_separate")
        box.prop(scene, "zenv_step_extend")
        box.prop(scene, "zenv_step_uvs")
        box.prop(scene, "zenv_step_cage")
        box.prop(scene, "zenv_step_bake")
        
        layout.operator("zenv.transition_bake_extend")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_TransitionTextureExtend_Bake,
    ZENV_PT_TextureTransition_Panel,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    ZENV_TransitionTextureExtend_Properties.register()

def unregister():
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)
    ZENV_TransitionTextureExtend_Properties.unregister()

if __name__ == "__main__":
    register()
