# TEXTURE TRANSITION by UV WELDING
# two meshes that are touching , merge them and weld their UVs
# creating a seamless texture transition by UV stitching

bl_info = {
    "name": "TEX Transition Texture UV Weld",
    "author": "CorvaeOboro",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > ZENV",
    "description": "Create a transition between two meshes by UV welding",
}

import bpy
import bmesh
import mathutils
from mathutils import Vector
import math
import os
import tempfile

# ------------------------------------------------------------------------
#    Setup Logging
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Logger:
    """Logger class for UV welding operations"""
    
    @staticmethod
    def log_info(message, category="INFO"):
        print(f"[{category}] {message}")
    
    @staticmethod
    def log_error(message):
        print(f"[ERROR] {message}")

# ------------------------------------------------------------------------
#    Properties
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Properties:
    """Property management for UV welding addon"""
    
    @classmethod
    def register(cls):
        bpy.types.Scene.zenv_weld_debug = bpy.props.BoolProperty(
            name="Debug Mode",
            description="Enable debug logging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_steps = bpy.props.BoolProperty(
            name="Step Mode",
            description="Execute steps separately for debugging",
            default=False
        )
        
        bpy.types.Scene.zenv_weld_cleanup = bpy.props.BoolProperty(
            name="Cleanup",
            description="Remove temporary objects after welding",
            default=True
        )

        # Baking properties
        bpy.types.Scene.zenv_weld_resolution = bpy.props.IntProperty(
            name="Resolution",
            description="Resolution of the baked texture",
            default=1024,
            min=64,
            max=8192
        )
        
        bpy.types.Scene.zenv_weld_samples = bpy.props.IntProperty(
            name="Samples",
            description="Number of samples for baking",
            default=32,
            min=1,
            max=4096
        )
        
        bpy.types.Scene.zenv_weld_margin = bpy.props.IntProperty(
            name="Margin",
            description="Margin size in pixels for bake result",
            default=16,
            min=0,
            max=64
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.zenv_weld_debug
        del bpy.types.Scene.zenv_weld_steps
        del bpy.types.Scene.zenv_weld_cleanup
        del bpy.types.Scene.zenv_weld_resolution
        del bpy.types.Scene.zenv_weld_samples
        del bpy.types.Scene.zenv_weld_margin

# ------------------------------------------------------------------------
#    Utilities
# ------------------------------------------------------------------------

class ZENV_TransitionTextureWeld_Utils:
    """Utility functions for UV welding"""
    
    @staticmethod
    def get_shared_edges(source_obj, target_obj):
        """Find edges that are touching between two meshes"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info(f"Starting edge analysis between {source_obj.name} and {target_obj.name}", "EDGE DETECTION")
        
        # Create BMesh objects
        bm1 = bmesh.new()
        bm1.from_mesh(source_obj.data)
        bm1.verts.ensure_lookup_table()
        bm1.edges.ensure_lookup_table()
        bm1.faces.ensure_lookup_table()
        
        bm2 = bmesh.new()
        bm2.from_mesh(target_obj.data)
        bm2.verts.ensure_lookup_table()
        bm2.edges.ensure_lookup_table()
        bm2.faces.ensure_lookup_table()
        
        logger.log_info(f"Source mesh: {len(bm1.edges)} edges, {len(bm1.verts)} vertices", "MESH INFO")
        logger.log_info(f"Target mesh: {len(bm2.edges)} edges, {len(bm2.verts)} vertices", "MESH INFO")
        
        # Transform vertices to world space
        source_matrix = source_obj.matrix_world
        target_matrix = target_obj.matrix_world
        
        verts1_world = [source_matrix @ v.co for v in bm1.verts]
        verts2_world = [target_matrix @ v.co for v in bm2.verts]
        
        # Find matching vertex pairs
        threshold = 0.0001
        vert_pairs = []
        for i, v1 in enumerate(verts1_world):
            for j, v2 in enumerate(verts2_world):
                if (v1 - v2).length < threshold:
                    vert_pairs.append((i, j))
        
        # Find edges that share both vertices
        shared_edges = []
        for e1 in bm1.edges:
            v1_indices = {v.index for v in e1.verts}
            e1_verts_world = [verts1_world[v.index] for v in e1.verts]
            
            for e2 in bm2.edges:
                v2_indices = {v.index for v in e2.verts}
                e2_verts_world = [verts2_world[v.index] for v in e2.verts]
                
                # Check if both vertices of both edges match
                matching_pairs = 0
                for i, v1 in enumerate(e1_verts_world):
                    for j, v2 in enumerate(e2_verts_world):
                        if (v1 - v2).length < threshold:
                            matching_pairs += 1
                
                if matching_pairs == 2:
                    # Store edge data
                    e1_dir = (e1_verts_world[1] - e1_verts_world[0]).normalized()
                    e1_length = (e1_verts_world[1] - e1_verts_world[0]).length
                    
                    shared_edges.append((
                        e1.index,
                        e2.index,
                        {
                            'edge_dir': e1_dir,
                            'edge_length': e1_length,
                            'source_verts': [v.index for v in e1.verts],
                            'target_verts': [v.index for v in e2.verts]
                        }
                    ))
        
        bm1.free()
        bm2.free()
        
        logger.log_info(f"Found {len(shared_edges)} shared edges", "EDGE DETECTION COMPLETE")
        return shared_edges

    @staticmethod
    def create_merged_mesh(source_obj, target_obj, shared_edges):
        """Create a new mesh by merging source and target meshes"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Creating merged mesh...")

        def create_temp_object(obj, suffix):
            """Create a temporary copy of an object"""
            temp_mesh = obj.data.copy()
            temp_obj = obj.copy()
            temp_obj.data = temp_mesh
            temp_obj.name = f"_TEMP_{obj.name}_{suffix}"
            bpy.context.scene.collection.objects.link(temp_obj)
            return temp_obj

        # Create temporary objects for reference
        temp_source = create_temp_object(source_obj, "source")
        temp_target = create_temp_object(target_obj, "target")

        # Create the merged object
        merged_mesh = bpy.data.meshes.new(name=f"{source_obj.name}_extended.001_merged")
        merged_obj = bpy.data.objects.new(merged_mesh.name, merged_mesh)
        bpy.context.scene.collection.objects.link(merged_obj)

        # Create BMesh for merged object
        bm = bmesh.new()
        
        # Add source mesh
        bm_source = bmesh.new()
        bm_source.from_mesh(source_obj.data)
        bm_source.verts.ensure_lookup_table()
        bm_source.edges.ensure_lookup_table()
        bm_source.faces.ensure_lookup_table()
        
        source_verts = {}
        source_faces = {}
        
        # Copy source mesh with world transform
        for v in bm_source.verts:
            new_vert = bm.verts.new(source_obj.matrix_world @ v.co)
            source_verts[v.index] = new_vert
        
        bm.verts.ensure_lookup_table()
        
        for f in bm_source.faces:
            new_face = bm.faces.new([source_verts[v.index] for v in f.verts])
            source_faces[f.index] = new_face
        
        bm.faces.ensure_lookup_table()
        
        # Add target mesh
        bm_target = bmesh.new()
        bm_target.from_mesh(target_obj.data)
        bm_target.verts.ensure_lookup_table()
        bm_target.edges.ensure_lookup_table()
        bm_target.faces.ensure_lookup_table()
        
        target_verts = {}
        target_faces = {}
        
        # Copy target mesh with world transform
        for v in bm_target.verts:
            new_vert = bm.verts.new(target_obj.matrix_world @ v.co)
            target_verts[v.index] = new_vert
        
        bm.verts.ensure_lookup_table()
        
        for f in bm_target.faces:
            try:
                new_face = bm.faces.new([target_verts[v.index] for v in f.verts])
                target_faces[f.index] = new_face
            except ValueError:
                logger.log_info(f"Skipping duplicate face in target mesh")
        
        bm.faces.ensure_lookup_table()

        # Collect seam vertices and create mapping
        seam_vert_pairs = []
        seam_verts = set()
        for edge_data in shared_edges:
            source_edge_verts = edge_data[2]['source_verts']
            target_edge_verts = edge_data[2]['target_verts']
            for sv, tv in zip(source_edge_verts, target_edge_verts):
                seam_vert_pairs.append((source_verts[sv], target_verts[tv]))
                seam_verts.add(source_verts[sv].index)

        # Create vertex groups
        source_group = merged_obj.vertex_groups.new(name="source_verts")
        target_group = merged_obj.vertex_groups.new(name="target_verts")
        seam_group = merged_obj.vertex_groups.new(name="seam_verts")

        # Store face indices before welding
        source_face_indices = {idx for idx, face in source_faces.items() if face.is_valid}
        target_face_indices = {idx for idx, face in target_faces.items() if face.is_valid}

        # Perform welding
        weld_map = {}
        for source_vert, target_vert in seam_vert_pairs:
            weld_map[target_vert] = source_vert

        bmesh.ops.weld_verts(bm, targetmap=weld_map)

        # Update mesh after welding
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Create UV layers
        uv_layer = bm.loops.layers.uv.new()
        
        # Copy UVs from source mesh
        source_uv = bm_source.loops.layers.uv.verify()
        for face_idx, new_face in source_faces.items():
            if new_face.is_valid:
                old_face = bm_source.faces[face_idx]
                for new_loop, old_loop in zip(new_face.loops, old_face.loops):
                    new_loop[uv_layer].uv = old_loop[source_uv].uv.copy()

        # Copy UVs from target mesh
        target_uv = bm_target.loops.layers.uv.verify()
        for face_idx, new_face in target_faces.items():
            if new_face.is_valid:
                old_face = bm_target.faces[face_idx]
                for new_loop, old_loop in zip(new_face.loops, old_face.loops):
                    new_loop[uv_layer].uv = old_loop[target_uv].uv.copy()

        # Update mesh
        bm.normal_update()
        bm.to_mesh(merged_mesh)

        # Create custom properties to store face mappings
        merged_obj["source_faces"] = list(source_face_indices)
        merged_obj["target_faces"] = list(target_face_indices)
        merged_obj["seam_vertices"] = list(seam_verts)

        # Store temporary objects for later reference
        merged_obj["temp_source"] = temp_source.name
        merged_obj["temp_target"] = temp_target.name

        # Build vertex groups carefully
        source_indices = []
        target_indices = []
        seam_indices = list(seam_verts)

        # Step 1: Add all source vertices to source group
        for orig_idx, new_vert in source_verts.items():
            if new_vert.is_valid:
                source_indices.append(new_vert.index)

        # Step 2: Add all target vertices to target group
        for orig_idx, new_vert in target_verts.items():
            if new_vert.is_valid and new_vert.index not in seam_verts:
                target_indices.append(new_vert.index)

        # Step 3: Add vertices from faces connected to target vertices
        target_connected = set(target_indices)
        for v_idx in target_indices:
            v = bm.verts[v_idx]
            for edge in v.link_edges:
                other_vert = edge.other_vert(v)
                if other_vert.index not in seam_verts:
                    target_connected.add(other_vert.index)

        # Step 4: Remove target vertices from source group
        source_indices = [idx for idx in source_indices if idx not in target_connected]

        # Add vertices to groups
        if source_indices:
            source_group.add(source_indices, 1.0, 'ADD')
        if target_indices:
            target_group.add(list(target_connected), 1.0, 'ADD')
        if seam_indices:
            seam_group.add(seam_indices, 1.0, 'ADD')

        # Log vertex group sizes
        logger.log_info(f"Source group size: {len(source_indices)}")
        logger.log_info(f"Target group size: {len(target_connected)}")
        logger.log_info(f"Seam group size: {len(seam_indices)}")

        # Cleanup
        bm.free()
        bm_source.free()
        bm_target.free()

        return merged_obj

    @staticmethod
    def weld_uvs(obj, shared_edges):
        """Weld UVs at shared edges using Blender's UV stitch operation"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Starting UV welding...")
        
        # Store current mode and active area
        original_mode = bpy.context.object.mode
        original_area = bpy.context.area.type
        
        # Enter edit mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Get BMesh
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Get UV layer
        uv_layer = bm.loops.layers.uv.verify()
        
        # Get vertex groups
        source_group = obj.vertex_groups.get("source_verts")
        target_group = obj.vertex_groups.get("target_verts")
        seam_group = obj.vertex_groups.get("seam_verts")
        
        if not all([source_group, target_group, seam_group]):
            logger.log_error("Required vertex groups not found")
            return obj
        
        # Get seam vertices and face sets
        seam_verts = set(obj["seam_vertices"])
        source_faces = set(obj["source_faces"])
        target_faces = set(obj["target_faces"])
        
        # Process each shared edge
        for edge_idx, edge_data in enumerate(shared_edges):
            logger.log_info(f"Processing edge {edge_idx + 1}/{len(shared_edges)}")
            
            # Deselect all
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.mesh.select_mode(type='EDGE')
            
            # Get edge vertices
            source_edge_verts = edge_data[2]['source_verts']
            target_edge_verts = edge_data[2]['target_verts']
            
            # Find edges connecting these vertices
            source_edge = None
            target_edge = None
            
            for edge in bm.edges:
                edge_vert_indices = {v.index for v in edge.verts}
                if edge_vert_indices == set(source_edge_verts):
                    source_edge = edge
                elif edge_vert_indices == set(target_edge_verts):
                    target_edge = edge
            
            if not source_edge or not target_edge:
                logger.log_info(f"Could not find edges for pair {edge_idx + 1}")
                continue
            
            # Get faces connected to these edges
            source_edge_faces = [f for f in source_edge.link_faces if f.index in source_faces]
            target_edge_faces = [f for f in target_edge.link_faces if f.index in target_faces]
            
            if not source_edge_faces or not target_edge_faces:
                logger.log_info(f"Missing faces for edge {edge_idx + 1}")
                continue
            
            # Get UV coordinates for source edge
            source_edge_uvs = []
            for face in source_edge_faces:
                for loop in face.loops:
                    if loop.vert.index in source_edge_verts:
                        source_edge_uvs.append((loop.vert.index, loop[uv_layer].uv.copy()))
            
            # Sort UV coordinates by vertex index to maintain order
            source_edge_uvs.sort(key=lambda x: x[0])
            
            if len(source_edge_uvs) < 2:
                logger.log_info(f"Not enough UV coordinates for source edge {edge_idx + 1}")
                continue
            
            # Calculate source edge properties
            source_uv_start = source_edge_uvs[0][1]
            source_uv_end = source_edge_uvs[1][1]
            source_uv_vec = source_uv_end - source_uv_start
            source_uv_length = source_uv_vec.length
            
            if source_uv_length == 0:
                logger.log_info(f"Zero-length source UV edge {edge_idx + 1}")
                continue
            
            source_uv_dir = source_uv_vec.normalized()
            
            # Process target faces
            for face in target_edge_faces:
                # Get UV coordinates for target edge
                target_edge_uvs = []
                target_loops = {}  # Map vertex index to loop
                
                for loop in face.loops:
                    if loop.vert.index in target_edge_verts:
                        target_edge_uvs.append((loop.vert.index, loop[uv_layer].uv.copy()))
                        target_loops[loop.vert.index] = loop
                
                # Sort UV coordinates by vertex index to match source order
                target_edge_uvs.sort(key=lambda x: x[0])
                
                if len(target_edge_uvs) < 2:
                    continue
                
                # Calculate target edge properties
                target_uv_start = target_edge_uvs[0][1]
                target_uv_end = target_edge_uvs[1][1]
                target_uv_vec = target_uv_end - target_uv_start
                target_uv_length = target_uv_vec.length
                
                if target_uv_length == 0:
                    continue
                
                target_uv_dir = target_uv_vec.normalized()
                
                # Calculate transformation
                scale = source_uv_length / target_uv_length
                angle = math.atan2(source_uv_dir.y, source_uv_dir.x) - \
                       math.atan2(target_uv_dir.y, target_uv_dir.x)
                
                # Transform all UVs in the face
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    # Get relative position from start of edge
                    rel_pos = uv - target_uv_start
                    
                    # Apply transformation
                    x = rel_pos.x * math.cos(angle) - rel_pos.y * math.sin(angle)
                    y = rel_pos.x * math.sin(angle) + rel_pos.y * math.cos(angle)
                    transformed_pos = mathutils.Vector((x * scale, y * scale))
                    
                    # Set new UV position
                    loop[uv_layer].uv = source_uv_start + transformed_pos
            
            # Update mesh
            bmesh.update_edit_mesh(obj.data)
        
        # Restore original mode and area type
        bpy.ops.object.mode_set(mode=original_mode)
        if original_area != 'IMAGE_EDITOR':
            bpy.context.area.type = original_area
        
        logger.log_info("UV welding complete")
        return obj

    @staticmethod
    def cleanup_temp_objects(obj):
        """Remove temporary objects created during the process"""
        if "temp_source" in obj:
            temp_source = bpy.data.objects.get(obj["temp_source"])
            if temp_source:
                bpy.data.objects.remove(temp_source, do_unlink=True)
        if "temp_target" in obj:
            temp_target = bpy.data.objects.get(obj["temp_target"])
            if temp_target:
                bpy.data.objects.remove(temp_target, do_unlink=True)

    @staticmethod
    def setup_render_settings(context):
        """Configure render settings for baking"""
        logger = ZENV_TransitionTextureWeld_Logger
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
            context.scene.cycles.samples = context.scene.zenv_weld_samples
            logger.log_info(f"Cycles samples set to: {context.scene.cycles.samples}")
            
            # Set bake type and passes
            context.scene.cycles.bake_type = 'DIFFUSE'
            context.scene.render.bake.use_pass_direct = False
            context.scene.render.bake.use_pass_indirect = False
            context.scene.render.bake.use_pass_color = True
            logger.log_info("Configured for diffuse color-only baking (no lighting)")
            
            # Quality settings
            context.scene.cycles.use_denoising = False
            context.scene.cycles.use_high_quality_normals = True
            logger.log_info("Set high quality normals, disabled denoising for baking")
        
        # Bake settings
        context.scene.render.bake.margin = context.scene.zenv_weld_margin
        context.scene.render.bake.use_clear = True
        context.scene.render.bake.use_selected_to_active = True
        context.scene.render.bake.max_ray_distance = 0.1
        logger.log_info(f"Bake settings: margin={context.scene.render.bake.margin}, ray_distance=0.1")
        
        return original_engine

    @staticmethod
    def setup_bake_materials(merged_obj, source_obj, context):
        """Setup temporary material for baking"""
        logger = ZENV_TransitionTextureWeld_Logger
        logger.log_info("Setting up bake materials...")
        
        # Create bake image with proper name and filepath
        image_name = f"{merged_obj.name}_bake"
        bake_image = bpy.data.images.new(
            image_name,
            width=context.scene.zenv_weld_resolution,
            height=context.scene.zenv_weld_resolution,
            alpha=True,
            float_buffer=True
        )
        
        # Set filepath for the image
        blend_filepath = bpy.data.filepath
        if blend_filepath:
            # If blend file is saved, save next to it
            image_dir = os.path.dirname(blend_filepath)
            image_filepath = os.path.join(image_dir, image_name + ".png")
        else:
            # If blend file is not saved, use temp directory
            image_filepath = os.path.join(tempfile.gettempdir(), image_name + ".png")
        
        bake_image.filepath_raw = image_filepath
        logger.log_info(f"Bake image will be saved to: {image_filepath}")
        
        # Create temporary bake material
        temp_bake_mat = bpy.data.materials.new(name="__TEMP_BAKE_MATERIAL__")
        temp_bake_mat.use_nodes = True
        nodes = temp_bake_mat.node_tree.nodes
        nodes.clear()
        
        # Create image node for baking
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = bake_image
        tex_image.select = True
        nodes.active = tex_image
        
        # Store original materials
        merged_original_mats = [mat for mat in merged_obj.data.materials]
        
        # Assign bake material to merged object
        merged_obj.data.materials.clear()
        merged_obj.data.materials.append(temp_bake_mat)
        
        return {
            'bake_image': bake_image,
            'temp_material': temp_bake_mat,
            'merged_materials': merged_original_mats,
            'image_filepath': image_filepath
        }

    @staticmethod
    def restore_materials(obj, materials):
        """Restore original materials to object"""
        obj.data.materials.clear()
        for mat in materials:
            obj.data.materials.append(mat)

# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class ZENV_OT_TransitionTextureWeld_Bake(bpy.types.Operator):
    """Weld UVs between selected meshes and bake textures"""
    bl_idname = "zenv.transition_weld"
    bl_label = "Weld UVs and Bake"
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
            target_obj = context.active_object
            source_obj = [obj for obj in context.selected_objects if obj != target_obj][0]
            
            logger = ZENV_TransitionTextureWeld_Logger
            logger.log_info(f"Using selection order for UV welding:")
            logger.log_info(f"Source object (UV reference): {source_obj.name}")
            logger.log_info(f"Target object (UV to transform): {target_obj.name}")
            
            # Store original render settings
            original_engine = ZENV_TransitionTextureWeld_Utils.setup_render_settings(context)
            
            # Find shared edges
            shared_edges = ZENV_TransitionTextureWeld_Utils.get_shared_edges(source_obj, target_obj)
            if not shared_edges:
                self.report({'ERROR'}, "No shared edges found")
                return {'CANCELLED'}
            
            # Create merged mesh
            merged_obj = ZENV_TransitionTextureWeld_Utils.create_merged_mesh(
                source_obj, target_obj, shared_edges
            )
            
            # Weld UVs
            ZENV_TransitionTextureWeld_Utils.weld_uvs(merged_obj, shared_edges)
            
            # Setup materials for baking
            bake_data = ZENV_TransitionTextureWeld_Utils.setup_bake_materials(
                merged_obj, source_obj, context
            )
            
            # Select objects for baking
            bpy.ops.object.select_all(action='DESELECT')
            source_obj.select_set(True)
            merged_obj.select_set(True)
            bpy.context.view_layer.objects.active = merged_obj
            
            # Bake
            logger.log_info("Starting bake...")
            bpy.ops.object.bake(
                type='DIFFUSE',
                pass_filter={'COLOR'},
                use_selected_to_active=True,
                margin=context.scene.zenv_weld_margin
            )
            
            # Save baked image
            logger.log_info(f"Saving baked image to: {bake_data['image_filepath']}")
            bake_data['bake_image'].file_format = 'PNG'
            bake_data['bake_image'].save()
            
            # Restore materials
            ZENV_TransitionTextureWeld_Utils.restore_materials(
                merged_obj, bake_data['merged_materials']
            )
            
            # Cleanup
            if context.scene.zenv_weld_cleanup:
                ZENV_TransitionTextureWeld_Utils.cleanup_temp_objects(merged_obj)
                bpy.data.objects.remove(source_obj, do_unlink=True)
                bpy.data.objects.remove(target_obj, do_unlink=True)
                bpy.data.materials.remove(bake_data['temp_material'])
            
            # Restore render settings
            context.scene.render.engine = original_engine
            
            self.report({'INFO'}, f"Baked image saved to: {bake_data['image_filepath']}")
            return {'FINISHED'}
            
        except Exception as e:
            logger.log_error(f"Error during UV welding: {str(e)}")
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

# ------------------------------------------------------------------------
#    Panel
# ------------------------------------------------------------------------

class ZENV_PT_TransitionTextureWeld_Panel(bpy.types.Panel):
    """Panel for UV welding tools"""
    bl_label = "Texture Transition UV Weld"
    bl_idname = "ZENV_PT_transition_weld"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Options:")
        box.prop(scene, "zenv_weld_debug")
        box.prop(scene, "zenv_weld_steps")
        box.prop(scene, "zenv_weld_cleanup")
        
        box = layout.box()
        box.label(text="Bake Settings:")
        box.prop(scene, "zenv_weld_resolution")
        box.prop(scene, "zenv_weld_samples")
        box.prop(scene, "zenv_weld_margin")
        
        layout.operator("zenv.transition_weld")

# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    ZENV_OT_TransitionTextureWeld_Bake,
    ZENV_PT_TransitionTextureWeld_Panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    ZENV_TransitionTextureWeld_Properties.register()

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    ZENV_TransitionTextureWeld_Properties.unregister()

if __name__ == "__main__":
    register()
