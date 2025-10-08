#!/usr/bin/env python3
"""
Fix all dangerous self.colors[] bracket access to use safe .get() method.
"""
import re

# Read main.py
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define color fallbacks based on color_schemes structure
color_fallbacks = {
    # Backgrounds
    'bg_primary': '#1a1a1a',
    'bg_secondary': '#2d2d2d',
    'bg_accent': '#404040',
    'bg_elevated': '#4a4a4a',
    'bg_hover': '#525252',
    'bg_selected': '#5a5a5a',

    # Text colors
    'text_primary': '#ffffff',
    'text_secondary': '#e0e0e0',
    'text_muted': '#b0b0b0',
    'text_disabled': '#808080',
    'text_inverse': '#1a1a1a',
    'medical_text': '#ffffff',

    # Borders
    'border_subtle': '#404040',
    'border_defined': '#606060',
    'border_strong': '#808080',

    # Status colors
    'success': '#047857',
    'warning': '#b45309',
    'danger': '#dc2626',
    'info': '#1d4ed8',
    'primary': '#1e40af',
    'accent': '#6d28d9',

    # Status backgrounds
    'success_bg': '#064e3b',
    'warning_bg': '#92400e',
    'danger_bg': '#991b1b',
    'info_bg': '#1e3a8a',
    'primary_bg': '#1e40af',

    # Button states
    'button_primary': '#1e40af',
    'button_primary_hover': '#1d4ed8',
    'button_primary_text': '#ffffff',
    'button_secondary': '#374151',
    'button_secondary_hover': '#4b5563',
    'button_secondary_text': '#f9fafb',
    'button_success': '#047857',
    'button_success_hover': '#065f46',
    'button_warning': '#b45309',
    'button_warning_hover': '#92400e',
    'button_danger': '#dc2626',
    'button_danger_hover': '#b91c1c',
    'button_disabled': '#374151',
    'button_disabled_text': '#6b7280',

    # Input fields
    'input_bg': '#374151',
    'input_border': '#6b7280',
    'input_focus': '#2563eb',
    'input_text': '#f9fafb',
    'input_placeholder': '#9ca3af',
    'input_background': '#374151',  # Alias for input_bg

    # Clinical/medical
    'insight_bg': '#1e293b',
    'insight_border': '#475569',
    'risk_high': '#dc2626',
    'risk_medium': '#b45309',
    'risk_low': '#047857',
    'clinical_accent': '#1e40af',
    'therapy_primary': '#047857',
    'therapy_secondary': '#0f766e',

    # Effects
    'panel_shadow': '#00000080',
    'overlay_bg': '#000000cc',
    'divider': '#404040',

    # Badges
    'badge_low': '#047857',
    'badge_med': '#b45309',
    'badge_high': '#dc2626',

    # Non-existent keys that should map to real keys
    'accent_hover': '#1d4ed8',  # Map to primary hover
}

# Track replacements
replacements_made = 0
lines_modified = []

# Find all bracket-style accesses: self.colors['key']
pattern = r"self\.colors\[(['\"])([^'\"]+)\1\]"

def replace_bracket_access(match):
    global replacements_made, lines_modified
    quote = match.group(1)
    key = match.group(2)
    fallback = color_fallbacks.get(key, '#ffffff')

    replacements_made += 1

    # Return safe .get() version
    return f"self.colors.get('{key}', '{fallback}')"

# Replace all occurrences
new_content = re.sub(pattern, replace_bracket_access, content)

# Write updated content
with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"[OK] Fixed {replacements_made} bracket-style color accesses")
print(f"[OK] All self.colors['key'] -> self.colors.get('key', fallback)")
