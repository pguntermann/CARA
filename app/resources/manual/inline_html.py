"""
Script to create an inline version of the manual with embedded images, graphics, and CSS.

This script:
1. Reads index.html
2. Inlines the CSS from manual.css
3. Finds all image references in the screenshots folder (including PNG, JPG, SVG, etc.)
4. Converts them to base64 data URIs
5. Replaces the image src attributes with data URIs
6. Saves the result as manual-inline.html

Supports all image formats including SVG graphics (logo, layout visualizations, etc.).
"""

import base64
import os
import re
from pathlib import Path

def get_script_dir():
    """Get the directory where this script is located."""
    return Path(__file__).parent.absolute()

def image_to_base64(image_path):
    """Convert an image file (including SVG) to base64 data URI.
    
    Supports PNG, JPG, GIF, SVG, and WebP formats.
    SVG files are handled correctly with the image/svg+xml MIME type.
    """
    if not os.path.exists(image_path):
        print(f"Warning: Image not found: {image_path}")
        return None
    
    # Read image as binary (works for all formats including SVG)
    with open(image_path, 'rb') as f:
        image_data = f.read()
        encoded = base64.b64encode(image_data).decode('utf-8')
    
    # Determine MIME type from file extension
    ext = os.path.splitext(image_path)[1].lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',  # SVG graphics (logo, layout visualizations, etc.)
        '.webp': 'image/webp'
    }
    mime_type = mime_types.get(ext, 'image/png')
    
    return f"data:{mime_type};base64,{encoded}"

def inline_css(html_content, css_path):
    """Inline CSS from external file into HTML."""
    if not css_path.exists():
        print(f"Warning: CSS file not found: {css_path}")
        return html_content
    
    print(f"Reading CSS from {css_path.name}...")
    with open(css_path, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    # Replace <link rel="stylesheet" href="manual.css"> with inline <style>
    pattern = r'<link\s+rel=["\']stylesheet["\']\s+href=["\']manual\.css["\']\s*>'
    replacement = f'<style>\n{css_content}\n    </style>'
    
    if re.search(pattern, html_content):
        html_content = re.sub(pattern, replacement, html_content)
        print("  - CSS inlined successfully")
        return html_content
    else:
        print("  - No CSS link tag found, skipping CSS inlining")
        return html_content

def bake_screenshots():
    """Main function to bake screenshots and CSS into the HTML."""
    script_dir = get_script_dir()
    html_path = script_dir / 'index.html'
    css_path = script_dir / 'manual.css'
    output_path = script_dir / 'manual-inline.html'
    screenshots_dir = script_dir / 'screenshots'
    
    # Check if files exist
    if not html_path.exists():
        print(f"Error: {html_path} not found!")
        return False
    
    if not screenshots_dir.exists():
        print(f"Warning: {screenshots_dir} not found. No screenshots to bake.")
        # Still create the output file as a copy
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Created {output_path} without screenshots.")
        return True
    
    # Read the HTML file
    print(f"Reading {html_path}...")
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Inline CSS first
    html_content = inline_css(html_content, css_path)
    
    # Find all image references in the screenshots folder
    # Pattern matches: src="screenshots/filename.ext" or src='screenshots/filename.ext'
    # This includes all image formats: PNG, JPG, SVG, etc.
    pattern = r'src=["\']screenshots/([^"\']+)["\']'
    matches = re.findall(pattern, html_content)
    
    if not matches:
        print("No image references found in HTML.")
        # Still create the output file as a copy
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Created {output_path} without changes.")
        return True
    
    # Get unique image filenames (some images may appear multiple times)
    unique_matches = list(set(matches))
    
    print(f"Found {len(matches)} image reference(s) ({len(unique_matches)} unique):")
    for match in unique_matches:
        count = matches.count(match)
        if count > 1:
            print(f"  - {match} ({count} occurrences)")
        else:
            print(f"  - {match}")
    
    # Convert each unique image (including SVG graphics) to base64 and replace in HTML
    replacements = 0
    for image_filename in unique_matches:
        image_path = screenshots_dir / image_filename
        
        if not image_path.exists():
            print(f"Warning: Image not found: {image_path}")
            continue
        
        print(f"Converting {image_filename} to base64...")
        base64_data = image_to_base64(image_path)
        
        if base64_data:
            # Replace the image src with base64 data URI
            # Match both single and double quotes
            # Use re.sub with count=0 to replace ALL occurrences (not just the first one)
            old_pattern1 = rf'src="screenshots/{re.escape(image_filename)}"'
            old_pattern2 = rf"src='screenshots/{re.escape(image_filename)}'"
            
            # Count how many replacements we'll make
            count1 = len(re.findall(old_pattern1, html_content))
            count2 = len(re.findall(old_pattern2, html_content))
            
            if count1 > 0:
                html_content = re.sub(old_pattern1, f'src="{base64_data}"', html_content, count=0)
                replacements += count1
            elif count2 > 0:
                html_content = re.sub(old_pattern2, f"src='{base64_data}'", html_content, count=0)
                replacements += count2
            else:
                print(f"Warning: Could not find pattern for {image_filename}")
    
    # Write the output file
    print(f"\nWriting {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\nSuccessfully created {output_path}")
    print(f"  - CSS inlined")
    print(f"  - Converted {replacements} image(s) to base64 (including SVG graphics)")
    
    # Calculate file sizes
    original_size = os.path.getsize(html_path)
    new_size = os.path.getsize(output_path)
    size_diff = new_size - original_size
    
    print(f"  - Original size: {original_size:,} bytes")
    print(f"  - New size: {new_size:,} bytes")
    print(f"  - Size increase: {size_diff:,} bytes ({size_diff / 1024:.1f} KB)")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("CARA Manual - Inline HTML Script (CSS + Images + SVG)")
    print("=" * 60)
    print()
    
    success = bake_screenshots()
    
    if success:
        print("\nDone! You can now share manual-inline.html")
    else:
        print("\nFailed to create inline version")
        exit(1)

