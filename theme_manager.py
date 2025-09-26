#!/usr/bin/env python3
"""
Theme Manager for Amanuensis
Centralized theme management with persistence and professional styling
"""

import customtkinter as ctk
import json
import os
from pathlib import Path
from logger_config import get_logger
from typing import Optional, Callable, Dict, Any

class ThemeManager:
    """Centralized theme management for Amanuensis application"""

    def __init__(self):
        self.logger = get_logger('theme_manager')
        self.config_file = Path("theme_config.json")
        self.theme_callbacks = []  # Callbacks to update UI when theme changes

        # Professional color themes
        self.professional_themes = {
            "light": {
                "appearance_mode": "light",
                "color_theme": "blue",
                "professional_colors": {
                    "primary": "#2B5CE6",  # Professional blue
                    "secondary": "#F8F9FA",  # Clean light gray
                    "accent": "#28A745",  # Success green
                    "warning": "#FFC107",  # Warning amber
                    "danger": "#DC3545",  # Error red
                    "text_primary": "#212529",  # Dark text
                    "text_secondary": "#6C757D",  # Muted text
                    "background": "#FFFFFF",  # White background
                    "surface": "#F8F9FA"  # Light surface
                }
            },
            "dark": {
                "appearance_mode": "dark",
                "color_theme": "blue",
                "professional_colors": {
                    "primary": "#4A90E2",  # Professional blue (lighter for dark)
                    "secondary": "#2C2C2E",  # Dark gray
                    "accent": "#34C759",  # Success green (lighter)
                    "warning": "#FF9F0A",  # Warning amber (brighter)
                    "danger": "#FF3B30",  # Error red (brighter)
                    "text_primary": "#FFFFFF",  # White text
                    "text_secondary": "#8E8E93",  # Muted text
                    "background": "#1C1C1E",  # Dark background
                    "surface": "#2C2C2E"  # Dark surface
                }
            },
            "system": {
                "appearance_mode": "system",
                "color_theme": "blue",
                "professional_colors": None  # Will use system defaults
            }
        }

        # Load saved theme or use professional default
        self.current_theme = self.load_theme()
        self.apply_theme(self.current_theme)

    def load_theme(self) -> str:
        """Load theme from config file or return default"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    theme = config.get('theme', 'dark')
                    if theme in self.professional_themes:
                        self.logger.info(f"Loaded theme from config: {theme}")
                        return theme
        except Exception as e:
            self.logger.warning(f"Failed to load theme config: {e}")

        # Default to dark theme for professional therapy use
        return "dark"

    def save_theme(self, theme: str) -> bool:
        """Save theme to config file"""
        try:
            config = {'theme': theme}
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.logger.info(f"Saved theme to config: {theme}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save theme config: {e}")
            return False

    def apply_theme(self, theme: str) -> bool:
        """Apply theme globally to all windows"""
        if theme not in self.professional_themes:
            self.logger.error(f"Unknown theme: {theme}")
            return False

        try:
            theme_config = self.professional_themes[theme]

            # Set CustomTkinter appearance mode
            ctk.set_appearance_mode(theme_config["appearance_mode"])
            ctk.set_default_color_theme(theme_config["color_theme"])

            self.current_theme = theme
            self.save_theme(theme)

            # Notify all registered callbacks about theme change
            self.notify_theme_change(theme, theme_config)

            self.logger.info(f"Applied theme globally: {theme}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply theme {theme}: {e}")
            return False

    def set_theme(self, theme: str) -> bool:
        """Set theme and apply it globally"""
        return self.apply_theme(theme)

    def get_current_theme(self) -> str:
        """Get current theme name"""
        return self.current_theme

    def get_theme_colors(self, theme: Optional[str] = None) -> Dict[str, str]:
        """Get professional colors for a theme"""
        theme = theme or self.current_theme
        if theme in self.professional_themes:
            colors = self.professional_themes[theme].get("professional_colors")
            return colors if colors else {}
        return {}

    def register_theme_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register callback to be notified when theme changes"""
        self.theme_callbacks.append(callback)

    def unregister_theme_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Unregister theme change callback"""
        if callback in self.theme_callbacks:
            self.theme_callbacks.remove(callback)

    def notify_theme_change(self, theme: str, theme_config: Dict[str, Any]):
        """Notify all registered callbacks about theme change"""
        for callback in self.theme_callbacks:
            try:
                callback(theme, theme_config)
            except Exception as e:
                self.logger.warning(f"Theme callback failed: {e}")

    def get_professional_button_style(self, button_type: str = "primary") -> Dict[str, str]:
        """Get professional button styling for current theme"""
        colors = self.get_theme_colors()

        if not colors:
            return {}

        styles = {
            "primary": {
                "fg_color": colors.get("primary", "#2B5CE6"),
                "hover_color": self._lighten_color(colors.get("primary", "#2B5CE6"), 0.1),
                "text_color": "#FFFFFF",
                "border_width": 0
            },
            "secondary": {
                "fg_color": colors.get("secondary", "#F8F9FA"),
                "hover_color": self._lighten_color(colors.get("secondary", "#F8F9FA"), 0.1),
                "text_color": colors.get("text_primary", "#212529"),
                "border_width": 1,
                "border_color": colors.get("primary", "#2B5CE6")
            },
            "success": {
                "fg_color": colors.get("accent", "#28A745"),
                "hover_color": self._lighten_color(colors.get("accent", "#28A745"), 0.1),
                "text_color": "#FFFFFF",
                "border_width": 0
            },
            "warning": {
                "fg_color": colors.get("warning", "#FFC107"),
                "hover_color": self._lighten_color(colors.get("warning", "#FFC107"), 0.1),
                "text_color": colors.get("text_primary", "#212529"),
                "border_width": 0
            },
            "danger": {
                "fg_color": colors.get("danger", "#DC3545"),
                "hover_color": self._lighten_color(colors.get("danger", "#DC3545"), 0.1),
                "text_color": "#FFFFFF",
                "border_width": 0
            }
        }

        return styles.get(button_type, styles["primary"])

    def _lighten_color(self, color: str, factor: float = 0.1) -> str:
        """Lighten a hex color by a factor (simple approximation)"""
        try:
            # Remove # if present
            color = color.lstrip('#')

            # Convert to RGB
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)

            # Lighten by moving toward white
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))

            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return color  # Return original if conversion fails

    def is_light_theme(self) -> bool:
        """Check if current theme is light mode"""
        return self.current_theme == "light"

    def is_dark_theme(self) -> bool:
        """Check if current theme is dark mode"""
        return self.current_theme == "dark"

# Global theme manager instance
_theme_manager = None

def get_theme_manager() -> ThemeManager:
    """Get global theme manager instance (singleton)"""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager

def apply_professional_styling(widget, widget_type: str = "default"):
    """Apply professional styling to a widget based on current theme"""
    theme_manager = get_theme_manager()
    colors = theme_manager.get_theme_colors()

    if not colors:
        return

    # Professional styling based on widget type
    if hasattr(widget, 'configure'):
        try:
            if widget_type == "frame":
                widget.configure(
                    fg_color=colors.get("surface", "transparent"),
                    border_width=1,
                    border_color=colors.get("secondary", "gray")
                )
            elif widget_type == "label":
                widget.configure(
                    text_color=colors.get("text_primary", "black")
                )
            elif widget_type == "entry":
                widget.configure(
                    fg_color=colors.get("background", "white"),
                    text_color=colors.get("text_primary", "black"),
                    border_color=colors.get("secondary", "gray")
                )
        except Exception as e:
            # Ignore styling errors - widget might not support all properties
            pass

if __name__ == "__main__":
    # Test theme manager
    import tkinter as tk

    tm = get_theme_manager()
    print(f"Current theme: {tm.get_current_theme()}")
    print(f"Theme colors: {tm.get_theme_colors()}")

    # Test theme switching
    for theme in ["light", "dark", "system"]:
        print(f"Switching to {theme}: {tm.set_theme(theme)}")
        print(f"Professional colors: {tm.get_theme_colors()}")
        print(f"Button style: {tm.get_professional_button_style()}")
        print()