#region META
bl_info = {
    "name": 'GEN Planet Procedural',
    "blender": (4, 0, 0),
    "category": 'ZENV',
    "version": '20260825',
    "description": 'Generate procedural planets with layered terrain',
    "status": 'working',
    "approved": True,
    "group": 'Generative',
    "group_prefix": 'GEN',
    "group_order": 30,
    "addon_order": 30,
    "tags": ['generative', 'planet', 'procedural', 'terrain', 'noise', 'icosphere'],
    "description_short": 'Generate procedural planets with layered terrain.',
    "description_medium": 'Builds a high-resolution icosphere base, radial displacement through combined fBm + ridged-multifractal noise for continents and mountains. Optionally adds an ocean shell, impact craters, and a volumetric atmosphere shell.',
    "description_long": """\
GEN Planet Procedural - Generate procedural planets with layered terrain.
Builds a high-resolution icosphere base, radial displacement through
combined fBm + ridged-multifractal noise for continents and mountains.
Optionally adds an ocean shell, impact craters, and a volumetric atmosphere shell.""",
    "addon_image": 'zenv_blender_GEN_planet.png',
    "location": 'View3D > ZENV > GEN Planet Procedural',
    "warning": '',
    "doc_url": '',
}
#endregion

#region IMPORT
import bpy
import bmesh
import logging
import math
import random
from mathutils import Vector, noise
from bpy.props import (
    FloatProperty,
    IntProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import Panel, Operator, PropertyGroup
#endregion

#region LOG
# Module logger setup with idempotent install/uninstall helpers.

logger = logging.getLogger(__name__)
_zenv_planet_procedural_console_handler = None


def _install_logger():
    """Attach a single StreamHandler to logger (idempotent)."""
    global _zenv_planet_procedural_console_handler
    if _zenv_planet_procedural_console_handler is not None:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _zenv_planet_procedural_console_handler = handler


def _uninstall_logger():
    """Remove the handler added by _install_logger."""
    global _zenv_planet_procedural_console_handler
    if _zenv_planet_procedural_console_handler is None:
        return
    try:
        logger.removeHandler(_zenv_planet_procedural_console_handler)
    except ValueError:
        pass
    _zenv_planet_procedural_console_handler = None
#endregion

#region PROPS
# Property group for procedural planet generation settings, registered on Scene.

class ZENV_PG_PlanetProcedural_Properties(PropertyGroup):
    """Properties for procedural planet generation"""

    # Base shape
    planet_radius: FloatProperty(
        name="Planet Radius",
        description="Base radius of the planet",
        default=1.0,
        min=0.1,
        max=100.0,
    )
    resolution: IntProperty(
        name="Resolution",
        description="Approximate target vertex density along the equator (drives icosphere subdivisions)",
        default=256,
        min=32,
        max=1024,
    )
    extra_subdivisions: IntProperty(
        name="Extra Subdivisions",
        description="Additional uniform subdivisions applied before displacement for finer detail",
        default=1,
        min=0,
        max=3,
    )
    random_seed: IntProperty(
        name="Random Seed",
        description="Seed used to offset noise sampling",
        default=0,
        min=0,
        max=10000,
    )

    # Terrain layered displacement
    terrain_strength: FloatProperty(
        name="Terrain Strength",
        description="Overall radial displacement amplitude as a fraction of planet radius",
        default=0.05,
        min=0.0,
        max=1.0,
    )
    sea_level_bias: FloatProperty(
        name="Sea Level Bias",
        description="Shifts the continental signal up/down before sea level. 0 = ~50/50 land/ocean",
        default=0.0,
        min=-0.5,
        max=0.5,
    )
    continent_scale: FloatProperty(
        name="Continent Scale",
        description="Frequency of large continental masses (smaller = larger continents)",
        default=1.1,
        min=0.1,
        max=10.0,
    )
    mountain_scale: FloatProperty(
        name="Mountain Scale",
        description="Frequency of ridged mountain ranges (plate-tectonic style)",
        default=2.5,
        min=0.5,
        max=20.0,
    )
    detail_scale: FloatProperty(
        name="Detail Scale",
        description="Frequency of fine surface detail",
        default=16.0,
        min=1.0,
        max=64.0,
    )
    terrain_octaves: IntProperty(
        name="Terrain Octaves",
        description="Number of fBm octaves for continental shape",
        default=6,
        min=1,
        max=10,
    )
    mountain_octaves: IntProperty(
        name="Mountain Octaves",
        description="Number of ridged-multifractal octaves for mountains",
        default=5,
        min=1,
        max=10,
    )
    detail_octaves: IntProperty(
        name="Detail Octaves",
        description="Number of octaves for high-frequency surface detail",
        default=4,
        min=1,
        max=8,
    )
    terrain_lacunarity: FloatProperty(
        name="Lacunarity",
        description="Frequency multiplier between octaves",
        default=2.0,
        min=1.5,
        max=3.5,
    )
    terrain_gain: FloatProperty(
        name="Gain",
        description="Amplitude multiplier between octaves (controls roughness)",
        default=0.5,
        min=0.2,
        max=0.9,
    )
    mountain_weight: FloatProperty(
        name="Mountain Weight",
        description="Contribution of ridged mountain layer to total displacement",
        default=0.85,
        min=0.0,
        max=2.0,
    )
    coast_ridge_weight: FloatProperty(
        name="Coastal Ridge Weight",
        description="Strength of ridge lines along continent boundaries (plate-tectonic mountain ranges)",
        default=0.6,
        min=0.0,
        max=2.0,
    )
    detail_weight: FloatProperty(
        name="Detail Weight",
        description="Contribution of fine detail layer to total displacement",
        default=0.15,
        min=0.0,
        max=1.0,
    )

    # Ocean
    generate_ocean: BoolProperty(
        name="Generate Ocean",
        description="Generate an ocean shell sphere",
        default=True,
    )
    ocean_level: FloatProperty(
        name="Ocean Level",
        description="Ocean shell height above base planet radius (fraction of radius). 0 = ~50/50 land/ocean",
        default=0.0,
        min=-0.2,
        max=0.5,
    )
    ocean_opacity: FloatProperty(
        name="Ocean Opacity",
        description="Alpha opacity of the ocean surface",
        default=0.75,
        min=0.0,
        max=1.0,
    )
    ocean_color: FloatVectorProperty(
        name="Ocean Color",
        description="Surface color of the ocean shell",
        subtype='COLOR',
        default=(0.05, 0.20, 0.45),
        min=0.0,
        max=1.0,
    )

    # Atmosphere
    atmosphere_height: FloatProperty(
        name="Atmosphere Height",
        description="Height of the atmosphere shell (fraction of radius)",
        default=0.10,
        min=0.0,
        max=1.0,
    )
    atmosphere_density: FloatProperty(
        name="Atmosphere Density",
        description="Volumetric density of the atmosphere",
        default=0.5,
        min=0.0,
        max=2.0,
    )

    # Colors
    surface_color: FloatVectorProperty(
        name="Surface Color",
        description="Base color of the planet surface",
        subtype='COLOR',
        default=(0.45, 0.40, 0.32),
        min=0.0,
        max=1.0,
    )
    atmosphere_color: FloatVectorProperty(
        name="Atmosphere Color",
        description="Color of the atmosphere",
        subtype='COLOR',
        default=(0.5, 0.7, 1.0),
        min=0.0,
        max=1.0,
    )

    # Features
    generate_craters: BoolProperty(
        name="Generate Craters",
        description="Generate impact craters. Off by default for tectonic-looking worlds",
        default=False,
    )
    crater_count: IntProperty(
        name="Crater Count",
        description="Number of impact craters",
        default=8,
        min=0,
        max=200,
    )
    generate_clouds: BoolProperty(
        name="Generate Clouds",
        description="Reserved for future cloud layer generation",
        default=False,
    )
#endregion

#region NOISE
# Noise primitives: fBm, ridged multifractal, and turbulence wrappers
# used by the terrain displacement stage.

class ZENV_PlanetProcedural_Utils:
    """Shared procedural-planet helpers used by the operator."""

    @staticmethod
    def fbm(point, octaves, lacunarity, gain):
        """Classic fractional Brownian motion (signed, normalized to ~[-1, 1])."""
        total = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        for _ in range(octaves):
            total += amplitude * noise.noise(point * frequency)
            max_value += amplitude
            amplitude *= gain
            frequency *= lacunarity
        if max_value <= 0.0:
            return 0.0
        return total / max_value

    @staticmethod
    def ridged_multifractal(point, octaves, lacunarity, gain):
        """Ridged multifractal noise producing sharp, mountain-like ridges in [0, ~1]."""
        total = 0.0
        amplitude = 1.0
        frequency = 1.0
        weight = 1.0
        max_value = 0.0
        for _ in range(octaves):
            sample = 1.0 - abs(noise.noise(point * frequency))
            sample = sample * sample
            sample *= weight
            weight = max(0.0, min(1.0, sample * 2.0))
            total += amplitude * sample
            max_value += amplitude
            amplitude *= gain
            frequency *= lacunarity
        if max_value <= 0.0:
            return 0.0
        return total / max_value

    @staticmethod
    def turbulence(point, octaves):
        """Turbulence wrapper using Blender's built-in (positional-arg safe)."""
        # noise.turbulence_vector requires (position, octaves, hard) as positional args.
        return noise.turbulence_vector(point, octaves, True).x
#endregion

#region MESH
# Base sphere creation: resolution mapping, seed suffix formatting, and
# icosphere generation with optional extra subdivisions.

    @staticmethod
    def resolution_to_subdivisions(resolution):
        """Map the user-facing 'resolution' value to icosphere subdivision count.

        Icosphere vertex counts approximately double per subdivision; we clamp
        to the safe 1..7 range supported by ``bmesh.ops.create_icosphere``.
        """
        clamped_resolution = max(16, int(resolution))
        # log2(resolution / 8) gives 1..7 across the supported range.
        subdivisions = int(round(math.log2(clamped_resolution / 8.0)))
        return max(1, min(7, subdivisions))

    @staticmethod
    def make_seed_suffix(generation_seed):
        """Format a generation seed into a stable, sortable name suffix."""
        return f"seed{int(generation_seed):06d}"

    @staticmethod
    def create_base_sphere(props, generation_seed):
        """Create base icosphere mesh, optionally with extra uniform subdivisions."""
        suffix = ZENV_PlanetProcedural_Utils.make_seed_suffix(generation_seed)
        subdivisions = ZENV_PlanetProcedural_Utils.resolution_to_subdivisions(props.resolution)
        bm = bmesh.new()
        try:
            bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=props.planet_radius)

            for _ in range(props.extra_subdivisions):
                bmesh.ops.subdivide_edges(
                    bm,
                    edges=bm.edges[:],
                    cuts=1,
                    use_grid_fill=True,
                )
                # Re-project each vertex to the sphere so the new geometry stays smooth.
                for vert in bm.verts:
                    vert.co = vert.co.normalized() * props.planet_radius

            mesh = bpy.data.meshes.new(f"Planet_{suffix}")
            bm.to_mesh(mesh)
        finally:
            bm.free()

        obj = bpy.data.objects.new(f"Planet_{suffix}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        logger.info(
            "Created base planet sphere %s: subdivisions=%d, extra=%d, verts=%d",
            suffix,
            subdivisions,
            props.extra_subdivisions,
            len(mesh.vertices),
        )
        return obj
#endregion

#region TERRAIN
# Layered radial displacement: continents (fBm), coastal ridges, mountains
# (ridged multifractal), and fine detail — all applied per-vertex.

    @staticmethod
    def apply_terrain_displacement(obj, props, generation_seed):
        """Apply layered radial displacement combining fBm + ridged + tectonic ridges.

        Layers:
            * Continent shape   - signed fBm. Centered around 0 so sea level at
              base radius gives ~50/50 land/ocean coverage.
            * Coastal ridges    - ``1 - abs(continent_lowfreq)`` produces sharp
              linear ridges that follow plate-boundary-like seams. This is what
              gives planetary-scale mountain RANGES rather than impact-style
              point craters.
            * Mountain mass     - ridged multifractal masked by positive
              continent height; provides per-range bulk and roughness.
            * Detail            - high-frequency fBm for surface micro-detail.
        """
        seed_offset = Vector((
            float(generation_seed) * 1.7,
            float(generation_seed) * 2.3,
            float(generation_seed) * 3.1,
        ))

        fbm = ZENV_PlanetProcedural_Utils.fbm
        ridged = ZENV_PlanetProcedural_Utils.ridged_multifractal

        mesh = obj.data
        radius = props.planet_radius
        amplitude = radius * props.terrain_strength

        for vert in mesh.vertices:
            direction = vert.co.normalized()

            # Continental shape: signed fBm centered around 0
            continent_point = direction * props.continent_scale + seed_offset
            continent = fbm(
                continent_point,
                props.terrain_octaves,
                props.terrain_lacunarity,
                props.terrain_gain,
            ) + props.sea_level_bias

            # Coastal / tectonic ridge: linear ridges along zero-crossings of
            # the continent field (i.e. continental boundaries).
            coast_ridge = 1.0 - min(1.0, abs(continent) * 6.0)
            coast_ridge = coast_ridge * coast_ridge

            # Mountain mass: ridged multifractal, only active above sea level.
            mountain_point = direction * props.mountain_scale + seed_offset * 0.5
            mountains = ridged(
                mountain_point,
                props.mountain_octaves,
                props.terrain_lacunarity,
                props.terrain_gain,
            )
            mountain_mask = max(0.0, continent)
            mountains *= mountain_mask

            # Fine detail: high-frequency fBm
            detail_point = direction * props.detail_scale + seed_offset * 0.25
            detail = fbm(
                detail_point,
                props.detail_octaves,
                props.terrain_lacunarity,
                props.terrain_gain,
            )

            displacement = (
                continent
                + mountains * props.mountain_weight
                + coast_ridge * props.coast_ridge_weight * mountain_mask
                + detail * props.detail_weight
            )

            vert.co = direction * (radius + displacement * amplitude)

        mesh.update()
        logger.info("Applied layered terrain displacement to %d vertices", len(mesh.vertices))
#endregion

#region SHELL
# Post-terrain features: topographic surface material, ocean shell, impact
# craters, and volumetric atmosphere shell.

    @staticmethod
    def create_surface_material(obj, props, generation_seed):
        """Create a topographic Principled BSDF material driven by elevation.

        Color is sampled from a ColorRamp keyed to ``length(position)`` mapped
        through the radial displacement range, producing distinct deep-ocean,
        shallow, beach, lowland, forest, mountain, and snow-cap bands.
        """
        suffix = ZENV_PlanetProcedural_Utils.make_seed_suffix(generation_seed)
        # Defensive clear so any previous slots on a re-used mesh data-block
        # cannot leak into the new generation's material assignment.
        obj.data.materials.clear()
        material = bpy.data.materials.new(name=f"Planet_Material_{suffix}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output_node = nodes.new('ShaderNodeOutputMaterial')
        principled_node = nodes.new('ShaderNodeBsdfPrincipled')
        bump_node = nodes.new('ShaderNodeBump')
        detail_noise_node = nodes.new('ShaderNodeTexNoise')
        geometry_node = nodes.new('ShaderNodeNewGeometry')
        vector_length_node = nodes.new('ShaderNodeVectorMath')
        map_range_node = nodes.new('ShaderNodeMapRange')
        color_ramp_node = nodes.new('ShaderNodeValToRGB')

        # Geometry -> length of position (object-space radial distance).
        vector_length_node.operation = 'LENGTH'
        links.new(geometry_node.outputs['Position'], vector_length_node.inputs[0])

        # Map radial distance to 0..1 across the displaced range.
        max_displacement = props.planet_radius * props.terrain_strength
        map_range_node.inputs['From Min'].default_value = props.planet_radius - max_displacement
        map_range_node.inputs['From Max'].default_value = props.planet_radius + max_displacement
        map_range_node.inputs['To Min'].default_value = 0.0
        map_range_node.inputs['To Max'].default_value = 1.0
        map_range_node.clamp = True
        links.new(vector_length_node.outputs['Value'], map_range_node.inputs['Value'])

        # Topographic ColorRamp: deep ocean -> shallow -> beach -> grass -> forest -> rock -> snow.
        ramp = color_ramp_node.color_ramp
        ramp.interpolation = 'LINEAR'
        # Default ramp ships with two stops; remove all except the first.
        while len(ramp.elements) > 1:
            ramp.elements.remove(ramp.elements[-1])
        topographic_stops = (
            (0.00, (0.02, 0.06, 0.20, 1.0)),  # deep ocean floor
            (0.40, (0.05, 0.20, 0.45, 1.0)),  # shallow shelf
            (0.49, (0.20, 0.45, 0.65, 1.0)),  # coastal water
            (0.51, (0.85, 0.78, 0.55, 1.0)),  # beach / sand
            (0.56, (0.35, 0.55, 0.20, 1.0)),  # lowland grass
            (0.68, (0.20, 0.35, 0.12, 1.0)),  # forest / highland
            (0.80, (0.45, 0.38, 0.30, 1.0)),  # rocky mountain
            (0.92, (0.70, 0.70, 0.72, 1.0)),  # bare peak
            (1.00, (1.00, 1.00, 1.00, 1.0)),  # snow cap
        )
        ramp.elements[0].position = topographic_stops[0][0]
        ramp.elements[0].color = topographic_stops[0][1]
        for stop_position, stop_color in topographic_stops[1:]:
            new_element = ramp.elements.new(stop_position)
            new_element.color = stop_color
        links.new(map_range_node.outputs['Result'], color_ramp_node.inputs['Fac'])
        links.new(color_ramp_node.outputs['Color'], principled_node.inputs['Base Color'])

        principled_node.inputs['Roughness'].default_value = 0.85

        # Specular input was renamed in Blender 4.0 ('Specular IOR Level').
        if 'Specular IOR Level' in principled_node.inputs:
            principled_node.inputs['Specular IOR Level'].default_value = 0.15
        elif 'Specular' in principled_node.inputs:
            principled_node.inputs['Specular'].default_value = 0.15

        # Procedural bump for micro-surface roughness on top of the topo color.
        detail_noise_node.inputs['Scale'].default_value = 50.0
        detail_noise_node.inputs['Detail'].default_value = 16.0
        detail_noise_node.inputs['Roughness'].default_value = 0.7
        bump_node.inputs['Strength'].default_value = 0.3
        links.new(detail_noise_node.outputs['Color'], bump_node.inputs['Height'])
        links.new(bump_node.outputs['Normal'], principled_node.inputs['Normal'])

        links.new(principled_node.outputs['BSDF'], output_node.inputs[0])

        obj.data.materials.append(material)

    @staticmethod
    def add_craters(obj, props):
        """Stamp simple cosine-bowl impact craters into the surface."""
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)

            for _ in range(props.crater_count):
                theta = random.uniform(0.0, 2.0 * math.pi)
                phi = math.acos(random.uniform(-1.0, 1.0))  # uniform on sphere
                crater_radius = random.uniform(0.05, 0.20)
                crater_depth = random.uniform(0.02, 0.06) * props.planet_radius

                center_direction = Vector((
                    math.sin(phi) * math.cos(theta),
                    math.sin(phi) * math.sin(theta),
                    math.cos(phi),
                ))

                for vert in bm.verts:
                    angular_distance = (vert.co.normalized() - center_direction).length
                    if angular_distance < crater_radius:
                        falloff = math.cos(angular_distance / crater_radius * math.pi * 0.5)
                        vert.co -= vert.co.normalized() * crater_depth * falloff

            bm.to_mesh(obj.data)
        finally:
            bm.free()

    @staticmethod
    def create_ocean_sphere(planet_obj, props, generation_seed):
        """Create an ocean shell sphere with translucent (~75%) opacity."""
        suffix = ZENV_PlanetProcedural_Utils.make_seed_suffix(generation_seed)
        radius = props.planet_radius * (1.0 + props.ocean_level)

        bm = bmesh.new()
        try:
            bmesh.ops.create_icosphere(bm, subdivisions=5, radius=radius)
            mesh = bpy.data.meshes.new(f"Ocean_{suffix}")
            bm.to_mesh(mesh)
        finally:
            bm.free()

        ocean_obj = bpy.data.objects.new(f"Ocean_{suffix}", mesh)
        bpy.context.scene.collection.objects.link(ocean_obj)

        # Defensive: a freshly created mesh has no slots, but clear here
        # so a stray pre-existing material data-block can never get attached.
        ocean_obj.data.materials.clear()

        material = bpy.data.materials.new(name=f"Ocean_Material_{suffix}")
        material.use_nodes = True
        material.blend_method = 'BLEND'
        # Backwards-compatible: shadow_method removed in Blender 4.2+.
        if hasattr(material, 'shadow_method'):
            material.shadow_method = 'HASHED'

        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output_node = nodes.new('ShaderNodeOutputMaterial')
        principled_node = nodes.new('ShaderNodeBsdfPrincipled')

        principled_node.inputs['Base Color'].default_value = (*props.ocean_color, 1.0)
        principled_node.inputs['Roughness'].default_value = 0.05
        principled_node.inputs['Alpha'].default_value = props.ocean_opacity

        # Transmission/IOR for water-like refraction; input names changed in 4.0.
        if 'Transmission Weight' in principled_node.inputs:
            principled_node.inputs['Transmission Weight'].default_value = 0.6
        elif 'Transmission' in principled_node.inputs:
            principled_node.inputs['Transmission'].default_value = 0.6
        if 'IOR' in principled_node.inputs:
            principled_node.inputs['IOR'].default_value = 1.33

        links.new(principled_node.outputs['BSDF'], output_node.inputs[0])

        ocean_obj.data.materials.append(material)
        return ocean_obj

    @staticmethod
    def create_atmosphere(planet_obj, props, generation_seed):
        """Create a volumetric atmosphere shell as a copy of the planet mesh."""
        suffix = ZENV_PlanetProcedural_Utils.make_seed_suffix(generation_seed)
        atmosphere_obj = planet_obj.copy()
        atmosphere_obj.data = planet_obj.data.copy()
        atmosphere_obj.name = f"Atmosphere_{suffix}"
        atmosphere_obj.data.name = f"Atmosphere_{suffix}"
        bpy.context.scene.collection.objects.link(atmosphere_obj)
        atmosphere_obj.scale = Vector((1.0 + props.atmosphere_height,) * 3)

        # The mesh copy inherited the planet's surface material slot. Strip it
        # so the atmosphere never accidentally renders the surface shader.
        atmosphere_obj.data.materials.clear()

        material = bpy.data.materials.new(name=f"Atmosphere_Material_{suffix}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output_node = nodes.new('ShaderNodeOutputMaterial')
        volume_node = nodes.new('ShaderNodeVolumePrincipled')

        volume_node.inputs['Density'].default_value = props.atmosphere_density
        volume_node.inputs['Color'].default_value = (*props.atmosphere_color, 1.0)

        links.new(volume_node.outputs[0], output_node.inputs[1])

        atmosphere_obj.data.materials.append(material)
        return atmosphere_obj
#endregion

#region OP
# Operator that generates a procedural planet by orchestrating the workflow:
# base sphere -> terrain displacement -> surface material -> craters -> ocean -> atmosphere.

class ZENV_OT_PlanetProcedural_Generate(Operator):
    """Generate a procedural planet"""
    bl_idname = "zenv.planet_procedural_generate"
    bl_label = "Generate Planet"
    bl_description = "Generate a new procedural planet"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        try:
            props = context.scene.zenv_planet_procedural_props

            # Resolve a generation seed. When the user leaves
            # random_seed=0 we draw a fresh random integer so every
            # generation gets a unique suffix and a unique world.
            if props.random_seed > 0:
                generation_seed = int(props.random_seed)
            else:
                generation_seed = random.randint(1, 999999)
            random.seed(generation_seed)

            planet_obj = ZENV_PlanetProcedural_Utils.create_base_sphere(
                props, generation_seed
            )
            ZENV_PlanetProcedural_Utils.apply_terrain_displacement(
                planet_obj, props, generation_seed
            )
            ZENV_PlanetProcedural_Utils.create_surface_material(
                planet_obj, props, generation_seed
            )

            # Smooth shading for the high-resolution surface.
            for polygon in planet_obj.data.polygons:
                polygon.use_smooth = True

            if props.generate_craters and props.crater_count > 0:
                ZENV_PlanetProcedural_Utils.add_craters(planet_obj, props)

            if props.generate_ocean:
                ocean_obj = ZENV_PlanetProcedural_Utils.create_ocean_sphere(
                    planet_obj, props, generation_seed
                )
                ocean_obj.parent = planet_obj

            if props.atmosphere_height > 0.0:
                atmosphere_obj = ZENV_PlanetProcedural_Utils.create_atmosphere(
                    planet_obj, props, generation_seed
                )
                atmosphere_obj.parent = planet_obj

            bpy.ops.object.select_all(action='DESELECT')
            planet_obj.select_set(True)
            context.view_layer.objects.active = planet_obj

            self.report({'INFO'}, f"Planet generated successfully (seed={generation_seed})")
            logger.info("Planet generated successfully (seed=%d)", generation_seed)
            return {'FINISHED'}

        except Exception as exception_caught:
            logger.error("Error generating planet: %s", exception_caught)
            self.report({'ERROR'}, f"Planet generation failed: {exception_caught}")
            return {'CANCELLED'}
#endregion

#region PANEL
# Sidebar panel in the ZENV category of the 3D Viewport.

class ZENV_PT_PlanetProcedural(Panel):
    """Panel for procedural planet generator"""
    bl_label = "GEN Planet Procedural"
    bl_idname = "ZENV_PT_PlanetProcedural"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ZENV'

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, 'zenv_planet_procedural_props')

    def draw(self, context):
        layout = self.layout
        props = context.scene.zenv_planet_procedural_props

        base_box = layout.box()
        base_box.label(text="Base", icon='WORLD')
        base_box.prop(props, "planet_radius")
        base_box.prop(props, "resolution")
        base_box.prop(props, "extra_subdivisions")
        base_box.prop(props, "random_seed")

        terrain_box = layout.box()
        terrain_box.label(text="Terrain", icon='RNDCURVE')
        terrain_box.prop(props, "terrain_strength")
        terrain_box.prop(props, "sea_level_bias")
        terrain_box.prop(props, "continent_scale")
        terrain_box.prop(props, "mountain_scale")
        terrain_box.prop(props, "detail_scale")
        terrain_box.prop(props, "terrain_octaves")
        terrain_box.prop(props, "mountain_octaves")
        terrain_box.prop(props, "detail_octaves")
        terrain_box.prop(props, "terrain_lacunarity")
        terrain_box.prop(props, "terrain_gain")
        terrain_box.prop(props, "mountain_weight")
        terrain_box.prop(props, "coast_ridge_weight")
        terrain_box.prop(props, "detail_weight")

        ocean_box = layout.box()
        ocean_box.label(text="Ocean", icon='MOD_FLUIDSIM')
        ocean_box.prop(props, "generate_ocean")
        if props.generate_ocean:
            ocean_box.prop(props, "ocean_level")
            ocean_box.prop(props, "ocean_opacity")
            ocean_box.prop(props, "ocean_color")

        atmosphere_box = layout.box()
        atmosphere_box.label(text="Atmosphere", icon='OUTLINER_OB_VOLUME')
        atmosphere_box.prop(props, "atmosphere_height")
        atmosphere_box.prop(props, "atmosphere_density")

        color_box = layout.box()
        color_box.label(text="Colors", icon='COLOR')
        color_box.prop(props, "atmosphere_color")

        feature_box = layout.box()
        feature_box.label(text="Features", icon='MOD_PARTICLES')
        feature_box.prop(props, "generate_craters")
        if props.generate_craters:
            feature_box.prop(props, "crater_count")
        feature_box.prop(props, "generate_clouds")

        layout.operator(ZENV_OT_PlanetProcedural_Generate.bl_idname, icon='WORLD_DATA')
#endregion

#region REG
classes = (
    ZENV_PG_PlanetProcedural_Properties,
    ZENV_OT_PlanetProcedural_Generate,
    ZENV_PT_PlanetProcedural,
)


def register():
    _install_logger()
    for current_class_to_register in classes:
        try:
            bpy.utils.register_class(current_class_to_register)
        except ValueError:
            pass
    if not hasattr(bpy.types.Scene, "zenv_planet_procedural_props"):
        bpy.types.Scene.zenv_planet_procedural_props = PointerProperty(
            type=ZENV_PG_PlanetProcedural_Properties
        )


def unregister():
    for current_class_to_unregister in reversed(classes):
        try:
            bpy.utils.unregister_class(current_class_to_unregister)
        except RuntimeError:
            pass
    if hasattr(bpy.types.Scene, "zenv_planet_procedural_props"):
        del bpy.types.Scene.zenv_planet_procedural_props
    _uninstall_logger()


if __name__ == "__main__":
    register()
#endregion
