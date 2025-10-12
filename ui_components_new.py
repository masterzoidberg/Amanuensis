#!/usr/bin/env python3
"""
Amanuensis V2 - New UI Components (Componentized Architecture)
Phase 1: Insights Panel
"""

import customtkinter as ctk
import tkinter as tk
from datetime import datetime
import time
from collections import deque
from typing import Dict, Any, Optional, Callable, Tuple


def map_risk_to_style(level: str, theme) -> Tuple[str, str, str]:
    """
    Map risk level to badge colors (centralized for consistency).

    Args:
        level: Risk level ('Low', 'Medium', 'High')
        theme: Theme resolver with .get() method

    Returns:
        tuple: (bg_color, fg_color, display_text)
    """
    # Helper for safe theme access
    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        elif isinstance(theme, dict):
            return theme.get(key, fallback)
        else:
            return fallback

    level_upper = level.upper() if isinstance(level, str) else 'LOW'

    if 'HIGH' in level_upper:
        bg = get_theme_color('badge_high', '#dc2626')
        fg = '#ffffff'
        text = 'High Risk'
    elif 'MEDIUM' in level_upper or 'MED' in level_upper:
        bg = get_theme_color('badge_med', '#f59e0b')
        fg = '#ffffff'
        text = 'Medium Risk'
    else:  # Low or default
        bg = get_theme_color('badge_low', '#10b981')
        fg = '#ffffff'
        text = 'Low Risk'

    return bg, fg, text


def set_recording_state_action(state, is_recording: bool, theme, verbose: bool = False):
    """
    Update the SessionControls recording button state without direct widget access.

    Args:
        state: SimpleNamespace with _start_stop_btn and _recording_state refs
        is_recording: True if recording started, False if stopped
        theme: Theme resolver with .get() method
        verbose: Enable diagnostic logging
    """
    # Helper for safe theme access
    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        elif isinstance(theme, dict):
            return theme.get(key, fallback)
        else:
            return fallback

    if hasattr(state, '_start_stop_btn') and hasattr(state, '_recording_state'):
        btn = state._start_stop_btn
        rec_state = state._recording_state

        # Update internal recording state
        rec_state['is_recording'] = is_recording

        # Update button appearance
        if is_recording:
            btn.configure(
                text='⏹ Stop Recording',
                fg_color=get_theme_color('danger', '#c94a4a')
            )
        else:
            btn.configure(
                text='⏺ Start Recording',
                fg_color=get_theme_color('success', '#43a047')
            )

        if verbose:
            print(f"REC ui_state updated: recording={is_recording}")


def create_insights_panel_new(root, state, actions, theme) -> ctk.CTkFrame:
    """
    Create the Insights Panel component for session timeline and insight cards.

    Args:
        root: Parent widget (should be positioned at grid row=1, col=2)
        state: SimpleNamespace or dict with insights, cost, avg_phrase, timeline_window_min/max
        actions: Object with on_send_insight, add_insight_card, on_timeline_change methods
        theme: Theme resolver dict-like with .get() method (safe fallbacks)

    Returns:
        CTkFrame configured as the insights panel
    """
    # Helper: safe theme color getter with fallback
    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        elif isinstance(theme, dict):
            return theme.get(key, fallback)
        else:
            return fallback

    # Tag color mapping with theme fallbacks
    tag_colors = {
        'High Risk': get_theme_color('badge_high', '#dc2626'),
        'Medium Risk': get_theme_color('badge_med', '#f59e0b'),
        'Low Risk': get_theme_color('badge_low', '#10b981'),
        'Follow-up': get_theme_color('accent', '#6d28d9'),
    }

    # Main panel frame
    panel_frame = ctk.CTkFrame(
        root,
        fg_color=get_theme_color('bg_secondary', '#2d2d2d'),
        corner_radius=8,
        border_width=2,
        border_color=get_theme_color('border_defined', '#606060')
    )

    # Configure grid: scrollable area expands
    panel_frame.grid_rowconfigure(0, weight=0)  # Title + Toast container
    panel_frame.grid_rowconfigure(1, weight=0)  # Timeline slider
    panel_frame.grid_rowconfigure(2, weight=0)  # "Insights" header
    panel_frame.grid_rowconfigure(3, weight=1)  # Scrollable cards area (EXPANDS)
    panel_frame.grid_rowconfigure(4, weight=0)  # Input row
    panel_frame.grid_rowconfigure(5, weight=0)  # Summary footer
    panel_frame.grid_columnconfigure(0, weight=1)
    
    # ===================================================================
    # ROW 0: Session Timeline Title + Toast Container
    # ===================================================================
    title_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
    title_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
    title_frame.grid_columnconfigure(0, weight=1)

    title_label = ctk.CTkLabel(
        title_frame,
        text="Session Timeline",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=get_theme_color('text_primary', '#ffffff'),
        anchor="w"
    )
    title_label.grid(row=0, column=0, sticky="w")

    # Toast label (initially hidden)
    toast_label = ctk.CTkLabel(
        title_frame,
        text="",
        font=ctk.CTkFont(size=10),
        text_color=get_theme_color('text_primary', '#ffffff'),
        fg_color=get_theme_color('toast_bg', '#10b981'),
        corner_radius=4,
        padx=8,
        pady=4
    )
    toast_label.grid(row=0, column=1, sticky="e")
    toast_label.grid_remove()  # Hide initially

    def show_toast(message: str):
        """Show transient toast notification"""
        if not panel_frame.winfo_exists():
            return
        toast_label.configure(text=message)
        toast_label.grid()
        # Auto-hide after 1.5s
        panel_frame.after(1500, lambda: toast_label.grid_remove() if panel_frame.winfo_exists() else None)
    
    # ===================================================================
    # ROW 1: Timeline Slider (0-10 minutes)
    # ===================================================================
    slider_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
    slider_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
    slider_frame.grid_columnconfigure(0, weight=1)
    
    timeline_value_var = tk.IntVar(value=getattr(state, 'timeline_window_min', 0))
    timeline_label = ctk.CTkLabel(
        slider_frame,
        text=f"{timeline_value_var.get()} min",
        font=ctk.CTkFont(size=12),
        text_color=get_theme_color('text_secondary', '#e0e0e0'),
        width=50
    )
    
    def on_timeline_slider_change(value):
        """Update timeline label and notify action"""
        nonlocal current_timeline_window
        int_val = int(value)
        current_timeline_window = int_val
        timeline_value_var.set(int_val)
        timeline_label.configure(text=f"{int_val} min")

        # Notify action (used for setting analysis window)
        if hasattr(actions, 'on_timeline_change'):
            actions.on_timeline_change(int_val)
    
    timeline_slider = ctk.CTkSlider(
        slider_frame,
        from_=getattr(state, 'timeline_window_min', 0),
        to=getattr(state, 'timeline_window_max', 10),
        number_of_steps=10,
        command=on_timeline_slider_change,
        button_color=get_theme_color('primary', '#1e40af'),
        button_hover_color=get_theme_color('accent', '#6d28d9'),
        progress_color=get_theme_color('primary', '#1e40af')
    )
    timeline_slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    timeline_label.grid(row=0, column=1, sticky="e")
    
    # ===================================================================
    # ROW 2: Preset Action Buttons (Dynamic from config)
    # ===================================================================
    preset_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
    preset_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))

    # Get presets from state (configured in settings)
    insights_presets = getattr(state, 'insights_presets', [])
    enabled_presets = [p for p in insights_presets if p.get('enabled', True)]

    # Configure grid columns dynamically based on number of presets
    num_presets = len(enabled_presets)
    if num_presets > 0:
        for i in range(num_presets):
            preset_frame.grid_columnconfigure(i, weight=1)

        # Render each enabled preset as a button
        for idx, preset in enumerate(enabled_presets):
            preset_id = preset.get('id', f'preset_{idx}')
            preset_label = preset.get('label', f'Preset {idx+1}')

            # Create button with handler
            def make_preset_handler(pid):
                return lambda: actions.on_preset_click(pid) if hasattr(actions, 'on_preset_click') else None

            preset_btn = ctk.CTkButton(
                preset_frame,
                text=preset_label,
                command=make_preset_handler(preset_id),
                font=ctk.CTkFont(size=10),
                height=28,
                fg_color=get_theme_color('primary', '#1e40af'),
                hover_color=get_theme_color('accent', '#6d28d9')
            )

            # Add padding between buttons except for the last one
            padx_config = (0, 5) if idx < num_presets - 1 else (0, 0)
            preset_btn.grid(row=0, column=idx, sticky="ew", padx=padx_config)

    else:
        # Fallback if no presets configured
        ctk.CTkLabel(
            preset_frame,
            text="No presets configured. Configure in Settings → Insights Presets",
            font=ctk.CTkFont(size=10),
            text_color=get_theme_color('text_muted', '#888888')
        ).grid(row=0, column=0, sticky="w")

    # ===================================================================
    # ROW 3: Chat Area (EXPANDS) - replaces card stack
    # ===================================================================
    chat_scrollable = ctk.CTkScrollableFrame(
        panel_frame,
        fg_color=get_theme_color('bg_primary', '#1a1a1a'),
        scrollbar_fg_color=get_theme_color('bg_accent', '#404040'),
        scrollbar_button_color=get_theme_color('primary', '#1e40af'),
        scrollbar_button_hover_color=get_theme_color('accent', '#6d28d9'),
        corner_radius=6
    )
    chat_scrollable.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
    chat_scrollable.grid_columnconfigure(0, weight=1)
    
    # Chat message tracking
    message_widgets = []  # List of message widget references
    current_timeline_window = 0  # Minutes (0 = show all)

    # ===================================================================
    # HELPER: Render chat message bubble
    # ===================================================================
    def render_message_bubble(parent, message: Dict[str, Any], row_idx: int):
        """Render a chat-style message bubble (user or assistant)."""
        role = message.get('role', 'assistant')
        content = message.get('content', '')
        timestamp = message.get('timestamp', datetime.now().strftime("%H:%M:%S"))
        metadata = message.get('metadata', {})

        # User messages: darker background, left-aligned
        # Assistant messages: slightly lighter, left-aligned
        if role == 'user':
            bubble_fg = get_theme_color('bg_accent', '#2b2b2b')
            label_prefix = "You: "
        else:
            bubble_fg = '#1e1e1e'  # Slightly lighter than bg_primary
            label_prefix = "Assistant: "

        # Create bubble frame
        bubble_frame = ctk.CTkFrame(
            parent,
            fg_color=bubble_fg,
            corner_radius=8,
            border_width=1,
            border_color=get_theme_color('border_subtle', '#404040')
        )
        bubble_frame.grid(row=row_idx, column=0, sticky="ew", padx=5, pady=5)
        bubble_frame.grid_columnconfigure(0, weight=1)

        # Header: role + timestamp
        header_frame = ctk.CTkFrame(bubble_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 5))
        header_frame.grid_columnconfigure(0, weight=1)

        role_label = ctk.CTkLabel(
            header_frame,
            text=label_prefix,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=get_theme_color('text_primary', '#ffffff'),
            anchor="w"
        )
        role_label.grid(row=0, column=0, sticky="w")

        timestamp_label = ctk.CTkLabel(
            header_frame,
            text=timestamp,
            font=ctk.CTkFont(size=10),
            text_color=get_theme_color('text_muted', '#b0b0b0'),
            anchor="e"
        )
        timestamp_label.grid(row=0, column=1, sticky="e")

        # Content (full text, wraps without truncation)
        content_label = ctk.CTkLabel(
            bubble_frame,
            text=content,
            font=ctk.CTkFont(size=12),
            text_color=get_theme_color('text_secondary', '#e0e0e0'),
            anchor="w",
            justify="left",
            wraplength=700  # Wide wrap for readability
        )
        content_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        # Optional: Show metadata (template, time window, cost)
        if metadata:
            meta_frame = ctk.CTkFrame(bubble_frame, fg_color="transparent")
            meta_frame.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

            meta_parts = []
            if 'template' in metadata:
                meta_parts.append(f"Template: {metadata['template']}")
            if 'time_window' in metadata:
                meta_parts.append(f"Window: {metadata['time_window']}")
            if 'cost' in metadata:
                meta_parts.append(f"Cost: ${metadata['cost']:.4f}")

            if meta_parts:
                meta_label = ctk.CTkLabel(
                    meta_frame,
                    text=" • ".join(meta_parts),
                    font=ctk.CTkFont(size=9),
                    text_color=get_theme_color('text_muted', '#888888'),
                    anchor="w"
                )
                meta_label.pack(side="left")

        return bubble_frame

    # ===================================================================
    # HELPER: Add chat message to history and UI
    # ===================================================================
    def add_chat_message(role: str, content: str, metadata: Dict = None):
        """
        Add a chat message to history and render in UI.

        Args:
            role: 'user' or 'assistant'
            content: Full message text (no truncation)
            metadata: Optional dict with template, time_window, cost
        """
        if not panel_frame.winfo_exists():
            return

        verbose = getattr(state, 'VERBOSE_INSIGHTS', False)

        # Create message object
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'metadata': metadata or {}
        }

        # Add to chat history
        if hasattr(state, 'chat_history'):
            state.chat_history.append(message)

        if verbose:
            print(f"CHAT add_message role={role} len={len(content)}")

        # Render message
        row_idx = len(message_widgets)
        widget = render_message_bubble(chat_scrollable, message, row_idx)
        message_widgets.append(widget)

        # Auto-scroll to bottom
        try:
            if chat_scrollable.winfo_exists():
                chat_scrollable._parent_canvas.yview_moveto(1.0)
        except:
            pass

        # Show toast for assistant messages
        if role == 'assistant':
            show_toast(f"Response received ({len(content)} chars)")

    # Attach add_chat_message to actions for external access
    if hasattr(actions, '__dict__'):
        actions.add_chat_message = lambda role, content, metadata=None: panel_frame.after(0, lambda: add_chat_message(role, content, metadata))
        # Keep backward compatibility with add_insight_card
        def legacy_add_card(card_data):
            """Convert old card format to chat message"""
            title = card_data.get('title', 'Insight')
            body = card_data.get('body', '')
            tags = card_data.get('tags', [])
            full_content = f"{title}\n\n{body}" if title != 'Live Therapist Insight' else body
            metadata = {'tags': ', '.join(tags)} if tags else {}
            add_chat_message('assistant', full_content, metadata)
        actions.add_insight_card = lambda card: panel_frame.after(0, lambda: legacy_add_card(card))
    
    # ===================================================================
    # ROW 4: Input Row (Chat-style)
    # ===================================================================
    input_frame = ctk.CTkFrame(
        panel_frame,
        fg_color=get_theme_color('bg_accent', '#404040'),
        corner_radius=6
    )
    input_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
    input_frame.grid_columnconfigure(0, weight=1)

    insight_entry = ctk.CTkEntry(
        input_frame,
        placeholder_text="Ask about the session...",
        font=ctk.CTkFont(size=12),
        height=36,
        fg_color=get_theme_color('bg_primary', '#1a1a1a'),
        border_color=get_theme_color('border_subtle', '#404040'),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    insight_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

    def send_message():
        """Send user message and trigger analysis"""
        text = insight_entry.get().strip()
        if not text:
            return

        # Clear input
        insight_entry.delete(0, 'end')

        # Add user message to chat
        add_chat_message('user', text)

        # Trigger backend handler
        if hasattr(actions, 'on_send_insight'):
            actions.on_send_insight(text, template=None)

    send_button = ctk.CTkButton(
        input_frame,
        text="Send",
        font=ctk.CTkFont(size=12, weight="bold"),
        width=80,
        height=36,
        command=send_message,
        fg_color=get_theme_color('primary', '#1e40af'),
        hover_color=get_theme_color('accent', '#6d28d9')
    )
    send_button.grid(row=0, column=1, sticky="e", padx=10, pady=10)

    # Bind Enter key to send
    insight_entry.bind("<Return>", lambda e: send_message())
    
    # ===================================================================
    # ROW 5: Summary Footer (Analyzed, Cost, Avg Phrase)
    # ===================================================================
    summary_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
    summary_frame.grid(row=5, column=0, sticky="e", padx=15, pady=(5, 10))
    
    def update_summary():
        """Update summary labels from state (Phase 5b: actual LLM cost)"""
        # Use new LLM cost tracking (llm_cost_total) with 4 decimals
        cost_total = getattr(state, 'llm_cost_total', 0.0)
        cost_str = f"${cost_total:.4f}"
        avg_phrase = getattr(state, 'avg_phrase', '—')
        return f"Analyzed: ✅  Cost: {cost_str}  Avg. phrase: {avg_phrase}"
    
    summary_label = ctk.CTkLabel(
        summary_frame,
        text=update_summary(),
        font=ctk.CTkFont(size=10),
        text_color=get_theme_color('text_muted', '#b0b0b0'),
        anchor="e"
    )
    summary_label.pack(side="right")
    
    # Attach summary update method for external refresh
    if hasattr(actions, '__dict__'):
        actions.update_summary = lambda: panel_frame.after(0, lambda: summary_label.configure(text=update_summary()))

    # Note: Bottom padding handled by pady in card grid placement (5px per card)

    return panel_frame


def create_top_nav_bar(root, state, actions, theme) -> ctk.CTkFrame:
    """
    Create the TopNavBar component for app title, session display, and controls.
    
    Args:
        root: Parent widget (should be positioned at grid row=0, colspan=3)
        state: SimpleNamespace or dict with session_file, risk_level, dark_mode, app_version, VERBOSE_UI
        actions: Object with on_theme_toggle, on_open_settings, on_risk_click (optional), on_session_click (optional)
        theme: Theme resolver dict-like with .get() method (safe fallbacks)
    
    Returns:
        CTkFrame configured as the top navigation bar
    """
    # Helper: safe theme color getter with fallback
    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        elif isinstance(theme, dict):
            return theme.get(key, fallback)
        else:
            return fallback
    
    # Extract state values with defaults
    session_file = getattr(state, 'session_file', 'No active session')
    risk_level = getattr(state, 'risk_level', 'Low')
    dark_mode = getattr(state, 'dark_mode', True)
    app_version = getattr(state, 'app_version', 'Amanuensis V2')
    verbose = getattr(state, 'VERBOSE_UI', False)
    
    # Diagnostic log
    if verbose:
        print(f"TOPNAV init: dark={dark_mode} session={session_file} risk={risk_level}")
    
    # Main nav bar frame (height ~48-56px)
    nav_frame = ctk.CTkFrame(
        root,
        height=56,
        fg_color=get_theme_color('bg_primary', '#0B0F14'),
        corner_radius=0,
        border_width=0,
        border_color=get_theme_color('border_defined', '#1E2A36')
    )
    nav_frame.grid_propagate(False)  # Fixed height
    
    # Configure internal 3-column grid: left / center (expands) / right
    nav_frame.grid_columnconfigure(0, weight=0)  # Left section
    nav_frame.grid_columnconfigure(1, weight=1)  # Center section (expands)
    nav_frame.grid_columnconfigure(2, weight=0)  # Right section
    nav_frame.grid_rowconfigure(0, weight=1)
    
    # ===================================================================
    # LEFT: App Title
    # ===================================================================
    title_label = ctk.CTkLabel(
        nav_frame,
        text=app_version,
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color=get_theme_color('text_primary', '#E8E8E8'),
        anchor="w"
    )
    title_label.grid(row=0, column=0, sticky="w", padx=20, pady=12)
    
    # ===================================================================
    # CENTER: Session File Display (bound to StringVar)
    # ===================================================================
    # Create StringVar for dynamic updates
    session_var = tk.StringVar(value=f"Session: {session_file}")
    
    session_label = ctk.CTkLabel(
        nav_frame,
        textvariable=session_var,
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_muted', '#9CA3AF'),
        anchor="center"
    )
    session_label.grid(row=0, column=1, sticky="ew", padx=20, pady=12)
    
    # Store StringVar for external updates
    if hasattr(state, '__dict__'):
        state.session_var = session_var
    
    # Optional: Make clickable
    if hasattr(actions, 'on_session_click'):
        session_label.configure(cursor="hand2")
        session_label.bind("<Button-1>", lambda e: actions.on_session_click())
    
    # ===================================================================
    # RIGHT: Control Cluster (Theme Toggle + Risk Badge + Settings)
    # ===================================================================
    right_cluster = ctk.CTkFrame(nav_frame, fg_color="transparent")
    right_cluster.grid(row=0, column=2, sticky="e", padx=20, pady=12)
    
    # 1) Theme Toggle Button
    theme_text = "☀️ Light" if dark_mode else "🌙 Dark"
    theme_button = ctk.CTkButton(
        right_cluster,
        text=theme_text,
        font=ctk.CTkFont(size=12, weight="bold"),
        width=90,
        height=32,
        corner_radius=6,
        fg_color=get_theme_color('accent', '#6d28d9'),
        hover_color=get_theme_color('primary', '#1e40af'),
        text_color=get_theme_color('text_primary', '#E8E8E8'),
        command=lambda: handle_theme_toggle()
    )
    theme_button.pack(side="left", padx=(0, 10))
    
    def handle_theme_toggle():
        """Handle theme toggle with diagnostics"""
        if hasattr(actions, 'on_theme_toggle'):
            # Update state
            if hasattr(state, '__dict__'):
                state.dark_mode = not getattr(state, 'dark_mode', True)
            
            if verbose:
                print(f"TOPNAV theme toggled → dark={getattr(state, 'dark_mode', True)}")
            
            # Call action (will reapply theme)
            actions.on_theme_toggle()
            
            # Update button text
            new_text = "☀️ Light" if getattr(state, 'dark_mode', True) else "🌙 Dark"
            theme_button.configure(text=new_text)
    
    # 2) Risk Badge Label (Phase 5b: centralized mapper)
    risk_bg, risk_fg, risk_text = map_risk_to_style(risk_level, theme)

    risk_badge = ctk.CTkLabel(
        right_cluster,
        text=risk_text,
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=risk_fg,
        fg_color=risk_bg,
        corner_radius=6,
        padx=12,
        pady=6
    )
    risk_badge.pack(side="left", padx=(0, 10))
    
    # Optional: Make risk badge clickable to cycle levels
    if hasattr(actions, 'on_risk_click'):
        risk_badge.configure(cursor="hand2")
        
        def cycle_risk():
            """Cycle through risk levels (Phase 5b: uses centralized mapper)"""
            levels = ['Low', 'Medium', 'High']
            current = getattr(state, 'risk_level', 'Low')
            next_idx = (levels.index(current) + 1) % len(levels)
            next_level = levels[next_idx]

            if hasattr(state, '__dict__'):
                state.risk_level = next_level

            # Use centralized mapper for consistency
            new_bg, new_fg, new_text = map_risk_to_style(next_level, theme)
            risk_badge.configure(text=new_text, fg_color=new_bg, text_color=new_fg)

            # Diagnostic
            if verbose:
                print(f"RISK mapped: level={next_level} bg={new_bg} fg={new_fg}")

            actions.on_risk_click(next_level)

        risk_badge.bind("<Button-1>", lambda e: cycle_risk())

    # Store badge reference for external updates
    if hasattr(state, '__dict__'):
        state.risk_badge = risk_badge
    
    # 3) Settings Button
    settings_button = ctk.CTkButton(
        right_cluster,
        text="⚙️",
        font=ctk.CTkFont(size=16),
        width=36,
        height=32,
        corner_radius=6,
        fg_color=get_theme_color('bg_secondary', '#2d2d2d'),
        hover_color=get_theme_color('accent', '#6d28d9'),
        text_color=get_theme_color('text_primary', '#E8E8E8'),
        command=lambda: handle_settings_click()
    )
    settings_button.pack(side="left")
    
    def handle_settings_click():
        """Handle settings button click with thread safety"""
        if verbose:
            print("TOPNAV settings opened")
        
        if hasattr(actions, 'on_open_settings'):
            # Ensure on main thread
            nav_frame.after(0, actions.on_open_settings)
    
    # Attach update methods for external control
    def update_session(new_session_file):
        """Update session display"""
        if nav_frame.winfo_exists():
            session_var.set(f"Session: {new_session_file}")
    
    def update_risk(new_level):
        """Update risk badge"""
        if nav_frame.winfo_exists() and new_level in risk_colors:
            risk_badge.configure(
                text=f"{new_level} Risk",
                fg_color=risk_colors[new_level]
            )
    
    def update_theme_button(is_dark):
        """Update theme button text"""
        if nav_frame.winfo_exists():
            text = "☀️ Light" if is_dark else "🌙 Dark"
            theme_button.configure(text=text)
    
    # Store update methods in actions for external access
    if hasattr(actions, '__dict__'):
        actions.update_session = update_session
        actions.update_risk = update_risk
        actions.update_theme_button = update_theme_button
    
    return nav_frame


def create_transcript_panel_new(root, state, actions, theme) -> ctk.CTkFrame:
    """Create the Transcript Panel component with speaker controls and copy UX."""

    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        if isinstance(theme, dict):
            return theme.get(key, fallback)
        return fallback

    def adjust_color_brightness(hex_color, factor=1.08):
        try:
            color = hex_color.lstrip('#')
            if len(color) != 6:
                return hex_color
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            r = max(0, min(255, int(r * factor)))
            g = max(0, min(255, int(g * factor)))
            b = max(0, min(255, int(b * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    # Initialize state defaults
    if not hasattr(state, 'speaker_roles') or not state.speaker_roles:
        state.speaker_roles = {1: "Therapist", 2: "Client"}
    if not hasattr(state, 'turns'):
        state.turns = deque(maxlen=1000)
    if not hasattr(state, 'font_size'):
        state.font_size = 18
    if not hasattr(state, 'timestamps_enabled'):
        state.timestamps_enabled = True
    if not hasattr(state, 'clock') or not callable(state.clock):
        state.clock = time.time
    verbose = getattr(state, 'VERBOSE_UI', False)

    if verbose:
        print(f"TRANSCRIPT init: font={state.font_size} roles={state.speaker_roles}")

    frame_fg = get_theme_color('bg_secondary', '#18212c')
    text_bg = get_theme_color('bg_primary', '#0B0F14')
    text_fg = get_theme_color('text_primary', '#E8E8E8')
    text_muted = get_theme_color('text_muted', '#9CA3AF')
    stripe_bg = adjust_color_brightness(text_bg, 1.06)

    panel_frame = ctk.CTkFrame(
        root,
        fg_color=frame_fg,
        corner_radius=8,
        border_width=1,
        border_color=get_theme_color('border_subtle', '#1E2A36')
    )

    panel_frame.grid_rowconfigure(0, weight=0)
    panel_frame.grid_rowconfigure(1, weight=0)
    panel_frame.grid_rowconfigure(2, weight=1)
    panel_frame.grid_columnconfigure(0, weight=1)

    # Header
    header_frame = ctk.CTkFrame(panel_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 6))
    header_frame.grid_columnconfigure(0, weight=1)
    header_frame.grid_columnconfigure(1, weight=0)

    title_label = ctk.CTkLabel(
        header_frame,
        text="Live Transcript",
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color=text_fg,
        anchor="w"
    )
    title_label.grid(row=0, column=0, sticky="w")

    controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
    controls_frame.grid(row=0, column=1, sticky="e")

    role_options = ["Therapist", "Client", "Other"]
    speaker_roles = state.speaker_roles
    speaker1_var = tk.StringVar(value=speaker_roles.get(1, "Therapist"))
    speaker2_var = tk.StringVar(value=speaker_roles.get(2, "Client"))

    def handle_role_change(speaker_id, value):
        speaker_roles[speaker_id] = value
        if hasattr(actions, 'on_speaker_role_change') and actions.on_speaker_role_change:
            actions.on_speaker_role_change(speaker_id, value)

    speaker1_menu = ctk.CTkOptionMenu(
        controls_frame,
        values=role_options,
        variable=speaker1_var,
        command=lambda v: handle_role_change(1, v),
        fg_color=get_theme_color('button_secondary', '#1f2933'),
        button_color=get_theme_color('button_secondary', '#1f2933'),
        button_hover_color=get_theme_color('button_secondary_hover', '#2b3644'),
        text_color=text_fg,
        width=150
    )
    speaker1_menu.grid(row=0, column=0, padx=(0, 10))

    speaker2_menu = ctk.CTkOptionMenu(
        controls_frame,
        values=role_options,
        variable=speaker2_var,
        command=lambda v: handle_role_change(2, v),
        fg_color=get_theme_color('button_secondary', '#1f2933'),
        button_color=get_theme_color('button_secondary', '#1f2933'),
        button_hover_color=get_theme_color('button_secondary_hover', '#2b3644'),
        text_color=text_fg,
        width=150
    )
    speaker2_menu.grid(row=0, column=1, padx=(0, 12))

    def font_decrease():
        if hasattr(actions, 'on_font_decrease') and actions.on_font_decrease:
            actions.on_font_decrease()

    def font_increase():
        if hasattr(actions, 'on_font_increase') and actions.on_font_increase:
            actions.on_font_increase()

    btn_font = ctk.CTkFont(size=14, weight="bold")
    font_down_btn = ctk.CTkButton(
        controls_frame,
        text="A−",
        width=40,
        height=32,
        font=btn_font,
        fg_color=get_theme_color('button_secondary', '#1f2933'),
        hover_color=get_theme_color('button_secondary_hover', '#2b3644'),
        text_color=text_fg,
        command=font_decrease
    )
    font_down_btn.grid(row=0, column=2, padx=(0, 6))

    font_up_btn = ctk.CTkButton(
        controls_frame,
        text="A+",
        width=40,
        height=32,
        font=btn_font,
        fg_color=get_theme_color('button_secondary', '#1f2933'),
        hover_color=get_theme_color('button_secondary_hover', '#2b3644'),
        text_color=text_fg,
        command=font_increase
    )
    font_up_btn.grid(row=0, column=3)

    # Text area
    text_container = ctk.CTkFrame(panel_frame, fg_color="transparent")
    text_container.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

    text_widget = ctk.CTkTextbox(
        text_container,
        wrap="word",
        font=ctk.CTkFont(size=state.font_size),
        fg_color=text_bg,
        text_color=text_fg,
        border_color=get_theme_color('border_subtle', '#1E2A36'),
        border_width=1
    )
    text_widget.pack(fill="both", expand=True)

    # CTkTextbox wraps a tkinter Text widget - get reference to it for tag operations
    tk_text = text_widget._textbox if hasattr(text_widget, '_textbox') else text_widget

    # Configure text tags (spacing, colors, etc.)
    try:
        tk_text.tag_configure("base", spacing3=6)
        tk_text.tag_configure("spk1", background=stripe_bg)
        tk_text.tag_configure("spk2", background=text_bg)
        tk_text.tag_configure("timestamp", foreground=text_muted)
        tk_text.tag_configure("phi", foreground=get_theme_color('warning', '#FFA500'), underline=True)
    except Exception as e:
        print(f"Warning: Could not configure text tags: {e}")

    # Prevent direct typing but allow navigation/selection
    def block_unless_control(event):
        if event.state & 0x4:  # Control key held
            return
        return "break"

    text_widget.bind("<Key>", block_unless_control)

    # Context menu
    context_menu = tk.Menu(text_widget, tearoff=0)

    def copy_selection():
        if tk_text.tag_ranges("sel"):
            selected = tk_text.get("sel.first", "sel.last")
            if hasattr(actions, 'on_copy_selection') and actions.on_copy_selection:
                actions.on_copy_selection(selected)

    def copy_all():
        content = tk_text.get("1.0", "end-1c")
        if hasattr(actions, 'on_copy_all') and actions.on_copy_all:
            actions.on_copy_all(content)

    def current_time():
        try:
            return state.clock() if callable(state.clock) else time.time()
        except Exception:
            return time.time()

    def copy_last_five():
        # Reasoning: Delegate to main.py which sources from authoritative transcript_panel_state.turns
        # instead of using local state.turns which may be incomplete
        if hasattr(actions, 'on_copy_last_5') and callable(actions.on_copy_last_5):
            actions.on_copy_last_5()
        else:
            if verbose:
                print("[TRANSCRIPT] Warning: on_copy_last_5 action not available")
    context_menu.add_command(label="Copy Selection", command=copy_selection)
    context_menu.add_command(label="Copy Last 5 Minutes", command=copy_last_five)
    context_menu.add_command(label="Copy All", command=copy_all)

    def show_context_menu(event):
        """
        Show context menu at pointer or near widget (Windows 11 safe).

        Reasoning:
            - Mouse events (Button-3) have x_root/y_root
            - Keyboard events (Shift-F10, Menu) may not - use widget position
            - Always release grab in finally block
        """
        if not text_widget.winfo_exists():
            return

        try:
            # Enable/disable "Copy Selection" based on selection state
            has_selection = bool(tk_text.tag_ranges("sel"))
            if not has_selection:
                context_menu.entryconfig(0, state="disabled")
            else:
                context_menu.entryconfig(0, state="normal")

            # Get menu position: use event coords if available, else widget position
            if hasattr(event, 'x_root') and hasattr(event, 'y_root') and event.x_root and event.y_root:
                # Mouse event - use pointer position
                x = event.x_root
                y = event.y_root
            else:
                # Keyboard event - position near widget center
                x = text_widget.winfo_rootx() + 50
                y = text_widget.winfo_rooty() + 50

            context_menu.tk_popup(x, y)
        finally:
            # Always release grab (Windows 11 requirement)
            try:
                context_menu.grab_release()
            except:
                pass

    # Windows 11 context menu bindings
    # Reasoning: Support multiple ways to open context menu on Windows
    text_widget.bind("<Button-3>", show_context_menu)  # Right-click
    text_widget.bind("<Shift-F10>", show_context_menu)  # Shift+F10 (Windows standard)
    text_widget.bind("<App>", show_context_menu)  # Menu/Application key

    # Windows 11 keyboard shortcut for "Copy Last 5 Minutes"
    # Reasoning: Quick access without menu for frequent operation
    def handle_copy_last_5(event):
        copy_last_five()
        return "break"

    text_widget.bind("<Control-Shift-C>", handle_copy_last_5)

    if verbose:
        print("[TRANSCRIPT] Windows 11 context menu bindings installed")

    def handle_ctrl_c(event):
        if tk_text.tag_ranges("sel"):
            selected = tk_text.get("sel.first", "sel.last")
            if hasattr(actions, 'on_copy_selection') and actions.on_copy_selection:
                actions.on_copy_selection(selected)
            return "break"
        return "break"

    text_widget.bind("<Control-c>", handle_ctrl_c)

    def ensure_font(size):
        bounded = max(14, min(24, int(size)))
        state.font_size = bounded
        text_widget.configure(font=ctk.CTkFont(size=bounded))

    def append_turn_internal(turn_data):
        if not text_widget.winfo_exists():
            return

        # Extract data from the turn dictionary
        speaker_label = turn_data.get('speaker', 'UNKNOWN')
        text = turn_data.get('text', '').strip()
        abs_start = turn_data.get('start')
        abs_end = turn_data.get('end')
        is_phi = turn_data.get('is_phi', False)
        turn_id = turn_data.get('id')

        if not turn_id or not text:
            return

        ts_enabled = getattr(state, 'timestamps_enabled', True)
        if abs_start is None: abs_start = current_time()
        if abs_end is None: abs_end = abs_start

        timestamp = datetime.fromtimestamp(abs_start).strftime('%H:%M:%S')

        # Determine speaker styling from label (more robust than ID)
        # This is a simple heuristic; a more robust mapping would be better.
        tag = "spk1" if "therapist" in speaker_label.lower() or "speaker 1" in speaker_label.lower() else "spk2"

        # Check if separate_speakers is enabled to show speaker labels
        separate_speakers_enabled = getattr(state, 'separate_speakers', False)

        if separate_speakers_enabled:
            line_header = f"[{timestamp}] {speaker_label}: "
        else:
            line_header = f"[{timestamp}] "

        line_content = text
        line = line_header + line_content

        auto_scroll = text_widget.yview()[1] >= 0.95
        if tk_text.index("end-1c") != "1.0":
            line = "\n" + line

        # Insert text and apply tags
        tk_text.insert("end", line)
        line_start = tk_text.index(f"end-{len(line)}c linestart")
        line_end = tk_text.index("end-1c")

        tk_text.tag_add("base", line_start, line_end)
        tk_text.tag_add(tag, line_start, line_end)
        tk_text.tag_add(turn_id, line_start, line_end) # Unique tag for updates

        if ts_enabled:
            ts_end_pos = f"{line_start}+{len(line_header)-2}c"
            tk_text.tag_add("timestamp", line_start, ts_end_pos)

        if is_phi:
            content_start_pos = f"{line_start}+{len(line_header)}c"
            tk_text.tag_add("phi", content_start_pos, line_end)

        if auto_scroll:
            text_widget.see("end")

        # Store the full turn data in the state deque
        state.turns.append(turn_data)

        if verbose:
            print(f"TRANSCRIPT append: id={turn_id} phi={is_phi} len={len(text)}")

    def append_turn(turn_data):
        # The public-facing action, ensures the call is thread-safe
        panel_frame.after(0, lambda: append_turn_internal(turn_data))

    def update_turn_internal(turn_id: str, new_text: str):
        if not text_widget.winfo_exists() or not turn_id:
            return

        tag_ranges = tk_text.tag_ranges(turn_id)
        if not tag_ranges:
            if verbose:
                print(f"TRANSCRIPT update failed: turn_id '{turn_id}' not found.")
            return

        line_start, line_end = tag_ranges
        original_line = tk_text.get(line_start, line_end)

        try:
            # Find where the header ([HH:MM:SS] Speaker:) ends
            header_end_index = original_line.index(':') + 1
            header_end_index = original_line.index(':', header_end_index) + 2
            content_start_pos = tk_text.index(f"{line_start}+{header_end_index}c")

            # Replace the old content with the new approved text
            tk_text.delete(content_start_pos, line_end)
            tk_text.insert(content_start_pos, new_text)

            # Remove the PHI tag from the updated range
            new_content_end_pos = tk_text.index(f"{content_start_pos}+{len(new_text)}c")
            tk_text.tag_remove("phi", content_start_pos, new_content_end_pos)

            # Update the turn in the state deque for consistency
            for turn in state.turns:
                if turn.get('id') == turn_id:
                    turn['text'] = new_text
                    turn['is_phi'] = False
                    break
            
            if verbose:
                print(f"TRANSCRIPT update: id={turn_id} approved.")

        except (ValueError, tk.TclError) as e:
            if verbose:
                print(f"TRANSCRIPT update error for id={turn_id}: {e}")

    def update_turn(turn_id: str, new_text: str):
        panel_frame.after(0, lambda: update_turn_internal(turn_id, new_text))

    def update_font(size):
        panel_frame.after(0, lambda: ensure_font(size))

    def refresh_roles(s1, s2):
        panel_frame.after(0, lambda: _refresh_roles(s1, s2))

    def _refresh_roles(s1, s2):
        speaker1_var.set(s1)
        speaker2_var.set(s2)

    # Attach actions to the provided namespace
    if hasattr(actions, '__dict__'):
        actions.append_turn = append_turn
        actions.update_turn = update_turn
        actions.update_font = update_font
        actions.refresh_roles = refresh_roles
        actions.text_widget = text_widget

    state.text_widget = text_widget

    # Apply initial font
    ensure_font(state.font_size)

    return panel_frame


def create_session_controls(root, state, actions, theme) -> ctk.CTkFrame:
    """
    Create the Session Controls component for device selection, buffer, and privacy settings.
    
    Args:
        root: Parent widget (should be positioned at grid row=1, col=0)
        state: SimpleNamespace with devices, buffer_seconds, separate_speakers, privacy, dark_mode, VERBOSE_UI
        actions: Object with on_select_mic, on_select_loopback, on_buffer_change, on_separate_speakers,
                 on_start_stop, on_theme_toggle, on_phi_toggle, on_auto_approve_toggle
        theme: Theme resolver dict-like with .get() method (safe fallbacks)
    
    Returns:
        CTkFrame configured as the session controls panel
    """
    # Helper: safe theme color getter with fallback
    def get_theme_color(key, fallback):
        if hasattr(theme, 'get'):
            return theme.get(key, fallback)
        elif isinstance(theme, dict):
            return theme.get(key, fallback)
        else:
            return fallback
    
    verbose = getattr(state, 'VERBOSE_UI', False)
    
    # Main panel frame
    panel_frame = ctk.CTkFrame(
        root,
        fg_color=get_theme_color('bg_secondary', '#2d2d2d'),
        corner_radius=8,
        border_width=2,
        border_color=get_theme_color('border_defined', '#606060')
    )
    
    # Configure grid to allow scrolling if needed
    panel_frame.grid_rowconfigure(0, weight=1)
    panel_frame.grid_columnconfigure(0, weight=1)
    
    # Scrollable frame for all controls
    scrollable = ctk.CTkScrollableFrame(
        panel_frame,
        fg_color='transparent',
        scrollbar_button_color=get_theme_color('accent', '#1f6aa5'),
        scrollbar_button_hover_color=get_theme_color('accent_hover', '#2a8fd6')
    )
    scrollable.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)

    # Configure grid: single column, full width expansion
    scrollable.grid_columnconfigure(0, weight=1)

    # Define row constants to prevent overlap collisions
    ROW_TITLE = 0
    ROW_MIC_LABEL = 1
    ROW_MIC_DROPDOWN = 2
    ROW_LOOP_LABEL = 3
    ROW_LOOP_DROPDOWN = 4
    ROW_BUFFER_LABEL = 5
    ROW_BUFFER_SLIDER = 6
    ROW_SEPARATE_CHECK = 7
    ROW_START_STOP_BTN = 8
    ROW_THEME_TOGGLE = 9
    ROW_NOTES_BUTTON = 10
    ROW_PRIVACY_TITLE = 11
    ROW_PHI_CHECK = 12
    ROW_AUTO_APPROVE_CHECK = 13

    # Title
    title = ctk.CTkLabel(
        scrollable,
        text='Session Controls',
        font=ctk.CTkFont(size=18, weight='bold'),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    title.grid(row=ROW_TITLE, column=0, sticky='w', pady=(0, 15))

    # --- Device Selection ---

    # Microphone dropdown
    mic_label = ctk.CTkLabel(
        scrollable,
        text='Microphone',
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    mic_label.grid(row=ROW_MIC_LABEL, column=0, sticky='w', pady=(5, 2))
    
    mic_devices = state.devices.get('mics', []) if hasattr(state, 'devices') else []
    mic_sel = state.devices.get('mic_sel', None) if hasattr(state, 'devices') else None

    # Diagnostic logging
    if verbose:
        print(f"CTRL mic_devices={mic_devices} (count={len(mic_devices)})")
        print(f"CTRL mic_sel={mic_sel}")

    mic_var = ctk.StringVar(value=mic_sel or (mic_devices[0] if mic_devices else 'None'))
    
    def on_mic_change(choice):
        if hasattr(state, 'devices'):
            state.devices['mic_sel'] = choice
        if hasattr(actions, 'on_select_mic'):
            panel_frame.after(0, lambda: actions.on_select_mic(choice))
        if verbose:
            print(f"CTRL mic={choice}")
    
    mic_dropdown = ctk.CTkOptionMenu(
        scrollable,
        variable=mic_var,
        values=mic_devices if mic_devices else ['None'],
        command=on_mic_change,
        fg_color=get_theme_color('bg_primary', '#1a1a1a'),
        button_color=get_theme_color('accent', '#1f6aa5'),
        button_hover_color=get_theme_color('accent_hover', '#2a8fd6')
    )
    mic_dropdown.grid(row=ROW_MIC_DROPDOWN, column=0, sticky='ew', pady=(0, 10))

    # System Audio (Loopback) dropdown
    loop_label = ctk.CTkLabel(
        scrollable,
        text='System Audio',
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    loop_label.grid(row=ROW_LOOP_LABEL, column=0, sticky='w', pady=(5, 2))
    
    loop_devices = state.devices.get('loops', []) if hasattr(state, 'devices') else []
    loop_sel = state.devices.get('loop_sel', None) if hasattr(state, 'devices') else None

    # Diagnostic logging
    if verbose:
        print(f"CTRL loop_devices={loop_devices} (count={len(loop_devices)})")
        print(f"CTRL loop_sel={loop_sel}")

    loop_var = ctk.StringVar(value=loop_sel or (loop_devices[0] if loop_devices else 'None'))
    
    def on_loop_change(choice):
        if hasattr(state, 'devices'):
            state.devices['loop_sel'] = choice
        if hasattr(actions, 'on_select_loopback'):
            panel_frame.after(0, lambda: actions.on_select_loopback(choice))
        if verbose:
            print(f"CTRL loop={choice}")
    
    loop_dropdown = ctk.CTkOptionMenu(
        scrollable,
        variable=loop_var,
        values=loop_devices if loop_devices else ['None'],
        command=on_loop_change,
        fg_color=get_theme_color('bg_primary', '#1a1a1a'),
        button_color=get_theme_color('accent', '#1f6aa5'),
        button_hover_color=get_theme_color('accent_hover', '#2a8fd6')
    )
    loop_dropdown.grid(row=ROW_LOOP_DROPDOWN, column=0, sticky='ew', pady=(0, 10))

    # --- Buffer Duration Slider ---

    buffer_label = ctk.CTkLabel(
        scrollable,
        text=f'Buffer Duration: {getattr(state, "buffer_seconds", 30)}s',
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    buffer_label.grid(row=ROW_BUFFER_LABEL, column=0, sticky='w', pady=(5, 2))
    
    def on_buffer_slide(value):
        int_value = int(value)
        state.buffer_seconds = int_value
        buffer_label.configure(text=f'Buffer Duration: {int_value}s')
        if hasattr(actions, 'on_buffer_change'):
            panel_frame.after(0, lambda: actions.on_buffer_change(int_value))
        if verbose:
            print(f"CTRL buffer={int_value}")
    
    buffer_slider = ctk.CTkSlider(
        scrollable,
        from_=10,
        to=120,
        number_of_steps=110,
        command=on_buffer_slide,
        button_color=get_theme_color('accent', '#1f6aa5'),
        button_hover_color=get_theme_color('accent_hover', '#2a8fd6'),
        progress_color=get_theme_color('accent', '#1f6aa5')
    )
    buffer_slider.set(getattr(state, 'buffer_seconds', 30))
    buffer_slider.grid(row=ROW_BUFFER_SLIDER, column=0, sticky='ew', pady=(0, 10))

    # --- Separate Speakers Checkbox ---

    separate_var = ctk.BooleanVar(value=getattr(state, 'separate_speakers', False))

    def on_separate_toggle():
        enabled = separate_var.get()
        state.separate_speakers = enabled
        if hasattr(actions, 'on_separate_speakers'):
            panel_frame.after(0, lambda: actions.on_separate_speakers(enabled))
        if verbose:
            print(f"CTRL separate={enabled}")

    separate_check = ctk.CTkCheckBox(
        scrollable,
        text='Separate Speakers',
        variable=separate_var,
        command=on_separate_toggle,
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff'),
        fg_color=get_theme_color('accent', '#1f6aa5'),
        hover_color=get_theme_color('accent_hover', '#2a8fd6')
    )
    separate_check.grid(row=ROW_SEPARATE_CHECK, column=0, sticky='w', pady=(5, 15))
    
    # --- Start/Stop Button ---
    
    # Track recording state in a mutable container to avoid closure issues
    recording_state = {'is_recording': False}
    
    def on_start_stop_click():
        recording_state['is_recording'] = not recording_state['is_recording']
        if recording_state['is_recording']:
            start_stop_btn.configure(
                text='⏹ Stop Recording',
                fg_color=get_theme_color('danger', '#c94a4a')
            )
        else:
            start_stop_btn.configure(
                text='⏺ Start Recording',
                fg_color=get_theme_color('success', '#43a047')
            )
        
        if hasattr(actions, 'on_start_stop'):
            panel_frame.after(0, actions.on_start_stop)
        if verbose:
            print(f"CTRL start_stop toggled: recording={recording_state['is_recording']}")
    
    start_stop_btn = ctk.CTkButton(
        scrollable,
        text='⏺ Start Recording',
        command=on_start_stop_click,
        font=ctk.CTkFont(size=16, weight='bold'),
        fg_color=get_theme_color('success', '#43a047'),
        hover_color=get_theme_color('success_hover', '#357a38'),
        height=40
    )
    start_stop_btn.grid(row=ROW_START_STOP_BTN, column=0, sticky='ew', pady=(0, 15))

    # Store reference for external state sync
    state._start_stop_btn = start_stop_btn
    state._recording_state = recording_state

    # --- Theme Toggle ---

    def on_theme_click():
        current_dark = getattr(state, 'dark_mode', True)
        state.dark_mode = not current_dark
        if hasattr(actions, 'on_theme_toggle'):
            panel_frame.after(0, actions.on_theme_toggle)
        if verbose:
            print(f"CTRL theme toggled: dark={state.dark_mode}")

    theme_btn = ctk.CTkButton(
        scrollable,
        text='🌙 Dark Mode' if getattr(state, 'dark_mode', True) else '☀️ Light Mode',
        command=on_theme_click,
        font=ctk.CTkFont(size=14),
        fg_color=get_theme_color('bg_primary', '#1a1a1a'),
        hover_color=get_theme_color('border_subtle', '#3a3a3a')
    )
    theme_btn.grid(row=ROW_THEME_TOGGLE, column=0, sticky='ew', pady=(0, 15))
    
    # Store reference for external updates
    state._theme_btn = theme_btn

    # --- Generate Progress Notes Button ---

    def on_generate_notes_click():
        if hasattr(actions, 'on_generate_notes'):
            panel_frame.after(0, actions.on_generate_notes)
        if verbose:
            print(f"CTRL generate_notes clicked")

    generate_notes_btn = ctk.CTkButton(
        scrollable,
        text='📋 Generate Progress Notes',
        command=on_generate_notes_click,
        font=ctk.CTkFont(size=14, weight='bold'),
        fg_color=get_theme_color('accent', '#1f6aa5'),
        hover_color=get_theme_color('accent_hover', '#2a8fd6'),
        height=35
    )
    generate_notes_btn.grid(row=ROW_NOTES_BUTTON, column=0, sticky='ew', pady=(0, 20))

    # Store reference for external state sync (e.g., disable when no transcript)
    state._generate_notes_btn = generate_notes_btn

    # --- Privacy Settings ---

    privacy_title = ctk.CTkLabel(
        scrollable,
        text='Privacy Settings',
        font=ctk.CTkFont(size=16, weight='bold'),
        text_color=get_theme_color('text_primary', '#ffffff')
    )
    privacy_title.grid(row=ROW_PRIVACY_TITLE, column=0, sticky='w', pady=(5, 10))
    
    # PHI Detection checkbox
    phi_var = ctk.BooleanVar(
        value=state.privacy.get('phi_detection', False) if hasattr(state, 'privacy') else False
    )
    
    def on_phi_toggle():
        enabled = phi_var.get()
        if hasattr(state, 'privacy'):
            state.privacy['phi_detection'] = enabled
        if hasattr(actions, 'on_phi_toggle'):
            panel_frame.after(0, lambda: actions.on_phi_toggle(enabled))
        if verbose:
            print(f"CTRL phi={enabled}")
    
    phi_check = ctk.CTkCheckBox(
        scrollable,
        text='PHI Detection',
        variable=phi_var,
        command=on_phi_toggle,
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff'),
        fg_color=get_theme_color('warning', '#FFA500'),
        hover_color=get_theme_color('warning_hover', '#FF8C00')
    )
    phi_check.grid(row=ROW_PHI_CHECK, column=0, sticky='w', pady=(0, 8))

    # Auto-approve checkbox
    auto_approve_var = ctk.BooleanVar(
        value=state.privacy.get('auto_approve', False) if hasattr(state, 'privacy') else False
    )

    def on_auto_approve_toggle():
        enabled = auto_approve_var.get()
        if hasattr(state, 'privacy'):
            state.privacy['auto_approve'] = enabled
        if hasattr(actions, 'on_auto_approve_toggle'):
            panel_frame.after(0, lambda: actions.on_auto_approve_toggle(enabled))
        if verbose:
            print(f"CTRL auto_approve={enabled}")

    auto_approve_check = ctk.CTkCheckBox(
        scrollable,
        text='Auto-approve Transcripts',
        variable=auto_approve_var,
        command=on_auto_approve_toggle,
        font=ctk.CTkFont(size=14),
        text_color=get_theme_color('text_primary', '#ffffff'),
        fg_color=get_theme_color('accent', '#1f6aa5'),
        hover_color=get_theme_color('accent_hover', '#2a8fd6')
    )
    auto_approve_check.grid(row=ROW_AUTO_APPROVE_CHECK, column=0, sticky='w', pady=(0, 10))
    
    return panel_frame
