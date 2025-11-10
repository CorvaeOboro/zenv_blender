"""
ZENV Blender Addon Website Generator
-------------------------------------
Generates the main website HTML page from addon bl_info metadata.

Website is generated from bl_info data in each Addon .py files
 grouping by group_prefix , sorted by sort_priority within each group

Output: docs/index.html 

VERSION: 20251108
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, field
from collections import defaultdict

# Import the validator to reuse addon parsing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from DEV_blender_addon_metadata_validator import AddonMetadataValidator, AddonMetadata

@dataclass
class AddonGroup:
    """Group of addons by category."""
    prefix: str
    name: str
    addons: List[AddonMetadata] = field(default_factory=list)
    
    @property
    def sort_key(self) -> str:
        """Get sort key for group ordering."""
        # Use first addon's sort_priority or default
        if self.addons:
            return str(self.addons[0].bl_info.get('sort_priority', '999'))
        return '999'

class WebsiteGenerator:
    """Generates website HTML from addon metadata."""
    
    def __init__(self, addon_dir: str, output_dir: str):
        self.addon_dir = os.path.abspath(addon_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.validator = AddonMetadataValidator(addon_dir)
        self.groups: Dict[str, AddonGroup] = {}
        
    def load_addons(self):
        """Load and validate all addons."""
        print("Loading addons...")
        self.validator.scan_directory()
        
        # Filter to main folder addons with working/stable status
        # If no approved field exists, include by default
        approved_addons = [
            addon for addon in self.validator.addons
            if addon.folder_category == 'main'
            and addon.bl_info.get('status', 'working') in ['working', 'stable', 'wip']
            and addon.bl_info.get('approved', True) != False  # Include if missing or True
        ]
        
        print(f"Found {len(approved_addons)} addons for website")
        
        # Group by group_prefix
        for addon in approved_addons:
            # Try to get from bl_info, fallback to extracting from filename
            prefix = addon.bl_info.get('group_prefix')
            group_name = addon.bl_info.get('group')
            
            if not prefix:
                # Extract from filename: z_blender_PREFIX_name.py
                filename = os.path.basename(addon.file_path)
                parts = filename.replace('z_blender_', '').split('_')
                if len(parts) > 0:
                    prefix = parts[0].upper()
                    group_name = prefix.title()
                else:
                    prefix = 'OTHER'
                    group_name = 'Other'
            
            if not group_name:
                group_name = prefix.title()
            
            if prefix not in self.groups:
                self.groups[prefix] = AddonGroup(prefix=prefix, name=group_name)
            
            self.groups[prefix].addons.append(addon)
        
        # Sort addons within each group by sort_priority
        for group in self.groups.values():
            group.addons.sort(key=lambda a: int(a.bl_info.get('sort_priority', '999')))
        
        print(f"Organized into {len(self.groups)} groups")
    
    def generate_html(self) -> str:
        """Generate complete HTML page."""
        html_parts = []
        
        # HTML header
        html_parts.append(self._generate_header())
        
        # Hero section
        html_parts.append(self._generate_hero())
        
        # Group sections
        sorted_groups = sorted(self.groups.values(), key=lambda g: g.sort_key)
        for group in sorted_groups:
            html_parts.append(self._generate_group_section(group))
        
        # Footer
        html_parts.append(self._generate_footer())
        
        return '\n'.join(html_parts)
    
    def _generate_header(self) -> str:
        """Generate HTML header with styles."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZENV Blender Addons</title>
    <meta name="description" content="Blender addons focused on singular features of 3d modelling, materials, and textures.">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #e0e0e0;
            background: #1a1a1a;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        /* Header */
        .header {
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 2px solid #3a3a3a;
        }
        
        .header h1 {
            font-size: 2rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1rem;
            color: #b0b0b0;
            margin-bottom: 15px;
        }
        
        .header a {
            color: #4a7ba7;
            text-decoration: none;
            font-weight: 500;
        }
        
        .header a:hover {
            text-decoration: underline;
        }
        
        /* Group Section */
        .group-section {
            margin-bottom: 40px;
        }
        
        .group-title {
            font-size: 1.5rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 15px;
            text-transform: uppercase;
        }
        
        /* Addon List - Compact Horizontal */
        .addon-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .addon-item {
            display: flex;
            align-items: center;
            background: #2d2d2d;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            padding: 8px 12px;
            transition: background 0.2s ease, border-color 0.2s ease;
            min-height: 60px;
        }
        
        .addon-item:hover {
            background: #3a3a3a;
            border-color: #4a7ba7;
        }
        
        .addon-image {
            width: 280px;
            height: 50px;
            object-fit: cover;
            background: #1a1a1a;
            border-radius: 3px;
            margin-right: 15px;
            flex-shrink: 0;
        }
        
        .addon-image-placeholder {
            width: 280px;
            height: 50px;
            background: #1a1a1a;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #555;
            font-size: 1.2rem;
            margin-right: 15px;
            flex-shrink: 0;
        }
        
        .addon-info {
            display: flex;
            align-items: center;
            gap: 15px;
            flex: 1;
            min-width: 0;
        }
        
        .addon-name {
            font-size: 0.95rem;
            font-weight: 500;
            color: #ffffff;
            min-width: 200px;
            flex-shrink: 0;
        }
        
        .addon-description {
            color: #b0b0b0;
            font-size: 0.9rem;
            line-height: 1.4;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .addon-meta {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-left: auto;
            flex-shrink: 0;
        }
        
        .addon-tag {
            display: inline-block;
            background: #3a3a3a;
            color: #888;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
        }
        
        .addon-tag.status-stable {
            background: #3a5a3a;
            color: #8ac88a;
        }
        
        .addon-tag.status-working {
            background: #3a4a5a;
            color: #8ab7d7;
        }
        
        /* Responsive */
        @media (max-width: 1024px) {
            .addon-image,
            .addon-image-placeholder {
                width: 200px;
            }
            
            .addon-name {
                min-width: 150px;
            }
        }
        
        @media (max-width: 768px) {
            .addon-item {
                flex-direction: column;
                align-items: flex-start;
                padding: 12px;
            }
            
            .addon-image,
            .addon-image-placeholder {
                width: 100%;
                height: 80px;
                margin-right: 0;
                margin-bottom: 10px;
            }
            
            .addon-info {
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }
            
            .addon-name {
                min-width: 0;
            }
            
            .addon-description {
                white-space: normal;
            }
            
            .addon-meta {
                margin-left: 0;
            }
        }
    </style>
</head>
<body>
"""
    
    def _generate_hero(self) -> str:
        """Generate simple header section."""
        return """
    <div class="container">
        <div class="header">
            <h1>ZENV BLENDER</h1>
            <p>Blender addons focused on singular features of 3d modelling, materials, and textures</p>
            <p><a href="https://github.com/CorvaeOboro/zenv_blender/archive/refs/heads/main.zip">[DOWNLOAD]</a></p>
            <p>Each addon is a self contained python file, to be installed and enabled individually, to demonstrate a specific modular feature.</p>
        </div>
"""
    
    def _generate_group_section(self, group: AddonGroup) -> str:
        """Generate a group section with its addons."""
        addon_items = []
        
        for addon in group.addons:
            addon_items.append(self._generate_addon_item(addon))
        
        items_html = '\n'.join(addon_items)
        
        return f"""        <section class="group-section">
            <h2 class="group-title">{group.name}</h2>
            <div class="addon-list">
{items_html}
            </div>
        </section>
"""
    
    def _generate_addon_item(self, addon: AddonMetadata) -> str:
        """Generate a compact addon list item."""
        name = addon.bl_info.get('name', 'Unnamed Addon')
        description = addon.bl_info.get('description_short', addon.bl_info.get('description', 'No description available'))
        status = addon.bl_info.get('status', 'working')
        version = addon.bl_info.get('version', 'N/A')
        image_path = addon.bl_info.get('image_overview', '')
        
        # Handle image
        if image_path and os.path.exists(os.path.join(self.addon_dir, '..', image_path)):
            # Convert to relative path for web
            image_html = f'<img src="{image_path}" alt="{name}" class="addon-image">'
        else:
            # Placeholder
            image_html = '<div class="addon-image-placeholder"></div>'
        
        # Status tag
        status_class = f"status-{status}" if status in ['stable', 'working'] else ""
        
        return f"""                <div class="addon-item">
                    {image_html}
                    <div class="addon-info">
                        <div class="addon-name">{name}</div>
                        <div class="addon-description">{description}</div>
                        <div class="addon-meta">
                            <span class="addon-tag {status_class}">{status}</span>
                        </div>
                    </div>
                </div>"""
    
    def _generate_footer(self) -> str:
        """Generate simple footer."""
        return """    </div>
</body>
</html>
"""
    
    def generate(self):
        """Main generation process."""
        print("=" * 80)
        print("ZENV BLENDER ADDON WEBSITE GENERATOR")
        print("=" * 80)
        
        # Load addons
        self.load_addons()
        
        # Generate HTML
        print("\nGenerating HTML...")
        html = self.generate_html()
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Write to file
        output_file = os.path.join(self.output_dir, 'index.html')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n[OK] Website generated: {output_file}")
        print(f"[OK] Total addons: {sum(len(g.addons) for g in self.groups.values())}")
        print(f"[OK] Total groups: {len(self.groups)}")
        
        # Summary by group
        print("\nGroup Summary:")
        print("-" * 80)
        for group in sorted(self.groups.values(), key=lambda g: g.sort_key):
            print(f"  {group.prefix:10} {group.name:20} {len(group.addons):3} addons")
        
        print("\n" + "=" * 80)
        print("GENERATION COMPLETE")
        print("=" * 80)
        print(f"\nOpen in browser: file:///{output_file}")

def main():
    """Main entry point."""
    # Paths
    script_dir = Path(__file__).parent
    addon_dir = script_dir.parent / 'addon'
    output_dir = script_dir.parent / 'docs'
    
    # Generate
    generator = WebsiteGenerator(str(addon_dir), str(output_dir))
    generator.generate()

if __name__ == '__main__':
    main()
