"""
Mesh to UV Space
Transform mesh between 3D and UV space with vertex separation and merging
"""

bl_info = {
    "name": "Mesh to UV Space",
    "author": "CorvaeOboro",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ZENV",
    "description": "Transform mesh between 3D and UV space with vertex separation and merging",
    "warning": "",
    "doc_url": "",
    "category": "ZENV",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.types import Panel, Operator, PropertyGroup

class ZENV_PG_MeshToUVSpace(PropertyGroup):
    do_phase_0: bpy.props.BoolProperty(
        name="Phase 0: Prepare Mesh",
        default=True,
        description="Triangulate mesh and separate vertices for UV transformation"
    )
    do_phase_2: bpy.props.BoolProperty(
        name="Phase 2: To UV Space",
        default=True,
        description="Transform mesh to UV space coordinates"
    )
    do_phase_3: bpy.props.BoolProperty(
        name="Phase 3: To 3D Space",
        default=False,
        description="Transform mesh back to original 3D space coordinates"
    )
    do_phase_4: bpy.props.BoolProperty(
        name="Phase 4: Merge Vertices",
        default=False,
        description="Merge vertices and UVs at very small distances to reconstruct the mesh"
    )

class ZENV_OT_MeshToUVSpace(Operator):
    """Transform mesh between 3D and UV space with vertex separation and merging.
    
    This operator performs a series of transformations:
    1. Prepares mesh by triangulating and separating vertices
    2. Transforms mesh to UV space coordinates
    3. Optionally transforms back to 3D space
    4. Optionally merges vertices to reconstruct the mesh
    """
    bl_idname = "zenv.mesh_to_uv_space"
    bl_label = "Apply UV Transform"
    bl_options = {'REGISTER', 'UNDO'}
    
    def log_msg(self, message):
        """Print a message to console and Blender's info area"""
        print(message)
        self.report({'INFO'}, message)

    def log_bmesh_stats(self, bm, label=""):
        """Print BMesh statistics (#verts, #edges, #faces)"""
        n_v = len(bm.verts)
        n_e = len(bm.edges)
        n_f = len(bm.faces)
        self.log_msg(f"BMesh stats {label}: {n_v} verts, {n_e} edges, {n_f} faces.")

    def auto_mark_uv_seams_from_islands(self, bm, uv_layer):
        """
        Detect edges that should be seams by comparing UV coordinates
        of adjacent faces along shared edges.
        """
        def get_edge_uvs(edge, face, uv_layer):
            """Get UV coordinates for an edge in the context of a face"""
            uvs = []
            loop_start = None
            # Find the loop that starts at one of the edge verts
            for loop in face.loops:
                if loop.vert in edge.verts:
                    loop_start = loop
                    break
            
            if loop_start is None:
                return None
                
            # Get both UV coordinates for the edge
            current = loop_start
            uvs.append(current[uv_layer].uv.copy())
            
            # Find the next loop that uses the edge
            for loop in face.loops:
                if loop.vert in edge.verts and loop != loop_start:
                    uvs.append(loop[uv_layer].uv.copy())
                    break
                    
            return uvs if len(uvs) == 2 else None

        def uvs_match(uvs1, uvs2, threshold=0.0001):
            """Compare two sets of UV coordinates"""
            if not uvs1 or not uvs2:
                return False
                
            # Check both possible orderings of UV pairs
            return (all((uvs1[i] - uvs2[i]).length < threshold for i in range(2)) or
                    all((uvs1[i] - uvs2[1-i]).length < threshold for i in range(2)))

        mark_count = 0
        edges_processed = set()

        for edge in bm.edges:
            if edge in edges_processed:
                continue
                
            if len(edge.link_faces) != 2:
                # Boundary edges should be seams
                if not edge.seam:
                    edge.seam = True
                    mark_count += 1
                edges_processed.add(edge)
                continue
                
            # Get UV coordinates for the edge in both faces
            uvs1 = get_edge_uvs(edge, edge.link_faces[0], uv_layer)
            uvs2 = get_edge_uvs(edge, edge.link_faces[1], uv_layer)
            
            # If UV coordinates don't match, mark as seam
            if not uvs_match(uvs1, uvs2):
                if not edge.seam:
                    edge.seam = True
                    mark_count += 1
                    
            edges_processed.add(edge)

        self.log_msg(f"Marked {mark_count} new edges as seams.")

    def split_vertices_along_seams(self, bm, uv_layer):
        """
        Split vertices that are connected by seam edges to create separate vertices
        for each UV island.
        """
        split_count = 0
        edges_to_split = [e for e in bm.edges if e.seam]
        
        # First, split all seam edges
        for edge in edges_to_split:
            # Get UV coordinates for both ends of the edge in each face
            faces = edge.link_faces
            if len(faces) != 2:
                continue
                
            # Get loops for this edge in both faces
            loops1 = [l for l in faces[0].loops if l.edge == edge]
            loops2 = [l for l in faces[1].loops if l.edge == edge]
            
            if not loops1 or not loops2:
                continue
                
            # Get UV coordinates
            uvs1 = [l[uv_layer].uv for l in loops1]
            uvs2 = [l[uv_layer].uv for l in loops2]
            
            # Check if UVs are different
            if any((uvs1[i] - uvs2[i]).length > 0.0001 for i in range(len(uvs1))):
                # Split the edge
                result = bmesh.ops.split_edges(bm, edges=[edge], verts=[edge.verts[0], edge.verts[1]])
                split_count += 1
        
        # Update mesh indices
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        
        self.log_msg(f"Split {split_count} edges along seams")
        return split_count

    def phase_0_prepare_and_store(self, obj):
        """
        Prepare mesh by completely separating into individual triangles:
        1) Triangulate the mesh
        2) Create new mesh with completely separate triangles
        3) Store UV and original position data for each vertex
        """
        self.log_msg("=== PHASE 0: Prepare Mesh + Store Original Positions ===")

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get initial BMesh
        bm_orig = bmesh.new()
        bm_orig.from_mesh(obj.data)
        
        # Ensure UV layers exist
        if not bm_orig.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm_orig.free()
            return {'CANCELLED'}
        
        uv_layer_orig = bm_orig.loops.layers.uv.verify()
        
        # Triangulate
        bmesh.ops.triangulate(bm_orig, faces=bm_orig.faces[:])
        
        # Create new BMesh for rebuilt mesh
        bm_new = bmesh.new()
        pos_layer = bm_new.verts.layers.float_vector.new("original_position")
        uv_layer_new = bm_new.loops.layers.uv.new("UVMap")
        
        triangle_count = 0
        
        # Process each triangle, creating completely new vertices for each
        for face in bm_orig.faces:
            # Create three new vertices for this triangle
            new_verts = []
            uvs = []
            
            for loop in face.loops:
                # Create new vertex with original position
                new_vert = bm_new.verts.new(loop.vert.co)
                new_vert[pos_layer] = loop.vert.co.copy()
                new_verts.append(new_vert)
                # Store UV coordinates
                uvs.append(loop[uv_layer_orig].uv.copy())
            
            try:
                # Create new face
                new_face = bm_new.faces.new(new_verts)
                # Assign UV coordinates
                for loop, uv in zip(new_face.loops, uvs):
                    loop[uv_layer_new].uv = uv
                triangle_count += 1
            except ValueError as e:
                self.log_msg(f"Warning: Could not create face: {str(e)}")
        
        # Clean up original BMesh
        bm_orig.free()
        
        # Update indices
        bm_new.verts.index_update()
        bm_new.edges.index_update()
        bm_new.faces.index_update()
        
        # Update the mesh
        bm_new.to_mesh(obj.data)
        bm_new.free()
        
        self.log_msg(f"Rebuilt mesh with {triangle_count} separate triangles")
        return {'FINISHED'}

    def phase_2_transform_to_uv(self, obj):
        """Transform mesh vertices to match UV coordinates"""
        self.log_msg("=== PHASE 2: Transform to UV Space ===")

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        if not bm.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm.free()
            return {'CANCELLED'}

        uv_layer = bm.loops.layers.uv.verify()
        
        # Transform each vertex based on its UV coordinates in its first face
        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                loop.vert.co.x = uv.x
                loop.vert.co.y = uv.y
                loop.vert.co.z = 0.0

        bm.to_mesh(obj.data)
        bm.free()
        return {'FINISHED'}

    def phase_3_transform_back(self, obj):
        """Restore mesh to original positions"""
        self.log_msg("=== PHASE 3: Transform Back to Original Positions ===")

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        pos_layer = bm.verts.layers.float_vector.get("original_position")
        if not pos_layer:
            self.log_msg("No stored positions found. Aborting.")
            bm.free()
            return {'CANCELLED'}

        for v in bm.verts:
            v.co = v[pos_layer]

        bm.to_mesh(obj.data)
        bm.free()
        return {'FINISHED'}

    def phase_4_merge_by_distance(self, obj):
        """Merge vertices and UVs at very small distances to reconstruct the mesh"""
        self.log_msg("=== PHASE 4: Merging Vertices and UVs ===")

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        if not bm.loops.layers.uv:
            self.log_msg("No UV layers found. Aborting.")
            bm.free()
            return {'CANCELLED'}

        uv_layer = bm.loops.layers.uv.verify()
        
        # Use very small merge distances
        MERGE_DISTANCE = 0.00001  # For vertex positions
        UV_GRID_SIZE = 0.000001   # For UV coordinate binning
        
        # First, create a map of vertices by their UV coordinates
        uv_vert_map = {}
        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                vert = loop.vert
                key = (round(uv.x / UV_GRID_SIZE), round(uv.y / UV_GRID_SIZE))
                
                if key not in uv_vert_map:
                    uv_vert_map[key] = []
                uv_vert_map[key].append((vert, uv.copy()))

        # Merge vertices that share the same UV coordinates (within merge distance)
        weld_count = 0
        for verts_and_uvs in uv_vert_map.values():
            if len(verts_and_uvs) > 1:
                # Keep the first vertex as target
                target_vert = verts_and_uvs[0][0]
                target_uv = verts_and_uvs[0][1]
                
                # Collect vertices to merge
                verts_to_merge = []
                for other_vert, other_uv in verts_and_uvs[1:]:
                    if (target_vert.co - other_vert.co).length <= MERGE_DISTANCE:
                        verts_to_merge.append(other_vert)
                
                if verts_to_merge:
                    # Use BMesh weld operator to merge vertices
                    bmesh.ops.weld_verts(bm, targetmap={v: target_vert for v in verts_to_merge})
                    weld_count += len(verts_to_merge)
                    
                    # Update UV coordinates for the merged vertices' faces
                    for face in target_vert.link_faces:
                        for loop in face.loops:
                            if loop.vert == target_vert:
                                loop[uv_layer].uv = target_uv

        # Update mesh indices
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        
        # Remove doubles to clean up the mesh
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=MERGE_DISTANCE)
        
        # Update the mesh
        bm.to_mesh(obj.data)
        bm.free()
        
        self.log_msg(f"Merged {weld_count} vertices")
        return {'FINISHED'}

    def execute(self, context):
        props = context.scene.zenv_mesh_to_uv_props
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.log_msg("No active mesh object selected")
            return {'CANCELLED'}

        if props.do_phase_0:
            result = self.phase_0_prepare_and_store(obj)
            if result != {'FINISHED'}:
                return result

        if props.do_phase_2:
            result = self.phase_2_transform_to_uv(obj)
            if result != {'FINISHED'}:
                return result

        if props.do_phase_3:
            result = self.phase_3_transform_back(obj)
            if result != {'FINISHED'}:
                return result

        if props.do_phase_4:
            result = self.phase_4_merge_by_distance(obj)
            if result != {'FINISHED'}:
                return result

        return {'FINISHED'}


class ZENV_PT_MeshToUVSpace(Panel):
    """Panel for controlling mesh to UV space transformations.
    
    Provides controls for:
    - Mesh preparation and vertex separation
    - UV space transformation
    - 3D space transformation
    - Vertex merging and mesh reconstruction
    """
    bl_label = "MESH to UV Space"
    bl_idname = "ZENV_PT_MeshToUVSpace"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_mesh_to_uv_props
        
        col = layout.column(align=True)
        col.prop(props, "do_phase_0")
        col.prop(props, "do_phase_2")
        col.prop(props, "do_phase_3")
        col.prop(props, "do_phase_4")
        
        layout.operator("zenv.mesh_to_uv_space")

# Registration
classes = (
    ZENV_PG_MeshToUVSpace,
    ZENV_OT_MeshToUVSpace,
    ZENV_PT_MeshToUVSpace,
)

def register():
    for current_class_to_register in classes:
        bpy.utils.register_class(current_class_to_register)
    bpy.types.Scene.zenv_mesh_to_uv_props = bpy.props.PointerProperty(type=ZENV_PG_MeshToUVSpace)

def unregister():
    del bpy.types.Scene.zenv_mesh_to_uv_props
    for current_class_to_unregister in reversed(classes):
        bpy.utils.unregister_class(current_class_to_unregister)

if __name__ == "__main__":
    register()
