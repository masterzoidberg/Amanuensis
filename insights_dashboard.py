#!/usr/bin/env python3
"""
Expandable Insights Dashboard Window (800x600)
Comprehensive analysis and transcript management interface
"""

import customtkinter as ctk
import threading
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import tkinter.filedialog as filedialog
from api_manager import APIManager

class InsightsDashboard:
    """Expandable insights dashboard for comprehensive session analysis"""

    def __init__(self, config_manager, api_manager=None, on_close: Optional[callable] = None):
        self.config_manager = config_manager
        self.api_manager = api_manager or APIManager(config_manager)
        self.on_close = on_close

        # Dashboard state
        self.current_transcript = ""
        self.analysis_results = {}
        self.session_data = {}
        self.is_analyzing = False

        self.setup_ui()

    def setup_ui(self):
        """Setup the insights dashboard interface"""
        self.window = ctk.CTkToplevel()
        self.window.title("Amanuensis - Insights Dashboard")
        self.window.geometry("900x700")
        self.window.minsize(600, 400)

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Main container with scrollable frame
        main_container = ctk.CTkFrame(self.window)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header_frame = ctk.CTkFrame(main_container)
        header_frame.pack(fill="x", pady=(0, 15))

        # Title and session info
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=15)

        title_label = ctk.CTkLabel(
            title_frame,
            text="📊 Therapeutic Insights Dashboard",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left")

        # Session info
        self.session_info_label = ctk.CTkLabel(
            title_frame,
            text="Session: Not started",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.session_info_label.pack(side="right")

        # Create notebook for tabs
        self.notebook = ctk.CTkTabview(main_container)
        self.notebook.pack(fill="both", expand=True)

        # Create tabs
        self.create_transcript_tab()
        self.create_analysis_tab()
        self.create_export_tab()
        self.create_settings_tab()

        # Status bar
        status_frame = ctk.CTkFrame(main_container)
        status_frame.pack(fill="x", pady=(10, 0))

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="[*] Dashboard ready",
            font=ctk.CTkFont(size=11),
            text_color="#2CC985"
        )
        self.status_label.pack(side="left", padx=15, pady=8)

        # Close button
        close_button = ctk.CTkButton(
            status_frame,
            text="Close Dashboard",
            command=self.close_dashboard,
            width=120,
            height=25,
            font=ctk.CTkFont(size=11),
            fg_color=("gray60", "gray40")
        )
        close_button.pack(side="right", padx=15, pady=5)

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.close_dashboard)

    def create_transcript_tab(self):
        """Create the transcript viewing tab"""
        tab = self.notebook.add("Transcript")

        # Controls frame
        controls_frame = ctk.CTkFrame(tab)
        controls_frame.pack(fill="x", padx=10, pady=10)

        # Transcript controls
        controls_title = ctk.CTkLabel(
            controls_frame,
            text="Live Transcript",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        controls_title.pack(side="left", padx=15, pady=10)

        # Auto-scroll toggle
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        auto_scroll_cb = ctk.CTkCheckBox(
            controls_frame,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
            font=ctk.CTkFont(size=11)
        )
        auto_scroll_cb.pack(side="right", padx=15, pady=10)

        # Speaker filter
        speaker_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        speaker_frame.pack(side="right", padx=(0, 20))

        ctk.CTkLabel(speaker_frame, text="Filter:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.speaker_filter = ctk.CTkComboBox(
            speaker_frame,
            values=["All", "Therapist", "Client"],
            width=100,
            height=25,
            font=ctk.CTkFont(size=10),
            command=self.filter_transcript
        )
        self.speaker_filter.pack(side="left", padx=(5, 0))

        # Transcript display
        transcript_frame = ctk.CTkFrame(tab)
        transcript_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.transcript_text = ctk.CTkTextbox(
            transcript_frame,
            font=ctk.CTkFont(size=12),
            wrap="word"
        )
        self.transcript_text.pack(fill="both", expand=True, padx=15, pady=15)

        # Add some sample content
        sample_text = """[00:00:15] Therapist: Good morning, how are you feeling today?

[00:00:18] Client: I'm okay, I guess. Had a rough week though.

[00:00:22] Therapist: I'm sorry to hear that. Would you like to tell me about what made it difficult?

[00:00:27] Client: Work has been really stressful. My manager keeps piling on more tasks and I feel overwhelmed.

[00:00:33] Therapist: That sounds very challenging. When you say overwhelmed, what does that feel like for you physically and emotionally?

[00:00:40] Client: My chest gets tight, I can't sleep well, and I find myself snapping at my family more often.

[00:00:46] Therapist: Those are significant stress responses. Let's explore some strategies that might help you manage these feelings..."""

        self.transcript_text.insert("0.0", sample_text)

    def create_analysis_tab(self):
        """Create the analysis results tab"""
        tab = self.notebook.add("Analysis")

        # Analysis controls
        controls_frame = ctk.CTkFrame(tab)
        controls_frame.pack(fill="x", padx=10, pady=10)

        controls_title = ctk.CTkLabel(
            controls_frame,
            text="AI-Powered Analysis",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        controls_title.pack(side="left", padx=15, pady=10)

        # Analysis progress
        self.analysis_progress = ctk.CTkProgressBar(controls_frame, width=200)
        self.analysis_progress.pack(side="right", padx=15, pady=10)
        self.analysis_progress.set(0)

        # Analysis type selector
        analysis_type_frame = ctk.CTkFrame(tab)
        analysis_type_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            analysis_type_frame,
            text="Analysis Type:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=15, pady=10)

        self.analysis_type_var = ctk.StringVar(value="Comprehensive")
        analysis_types = ["Comprehensive", "Themes", "Progress", "Risk Assessment", "Dynamics", "Custom"]

        for analysis_type in analysis_types:
            radio = ctk.CTkRadioButton(
                analysis_type_frame,
                text=analysis_type,
                variable=self.analysis_type_var,
                value=analysis_type,
                font=ctk.CTkFont(size=11)
            )
            radio.pack(side="left", padx=10, pady=10)

        # Custom prompt frame (initially hidden)
        self.custom_frame = ctk.CTkFrame(tab)
        self.custom_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            self.custom_frame,
            text="Custom Prompt:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.custom_prompt = ctk.CTkTextbox(
            self.custom_frame,
            height=60,
            font=ctk.CTkFont(size=11)
        )
        # Insert placeholder text manually since placeholder_text isn't supported
        self.custom_prompt.insert("0.0", "Enter your custom analysis prompt...")
        self.custom_prompt.pack(fill="x", padx=15, pady=(0, 15))

        # Initially hide custom frame
        self.custom_frame.pack_forget()

        # Analyze button
        analyze_frame = ctk.CTkFrame(tab)
        analyze_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.analyze_button = ctk.CTkButton(
            analyze_frame,
            text="🧠 Analyze Current Session",
            command=self.start_analysis,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#2CC985", "#2FA572")
        )
        self.analyze_button.pack(pady=15)

        # Results display
        results_frame = ctk.CTkFrame(tab)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        results_title = ctk.CTkLabel(
            results_frame,
            text="Analysis Results",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        results_title.pack(pady=(15, 10))

        self.results_text = ctk.CTkTextbox(
            results_frame,
            font=ctk.CTkFont(size=11),
            wrap="word"
        )
        self.results_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Add sample analysis
        sample_analysis = """THERAPEUTIC ANALYSIS RESULTS
Generated: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """

🎯 KEY THEMES IDENTIFIED:
• Work-related stress and overwhelm
• Physical manifestations of anxiety (chest tightness, sleep issues)
• Impact on family relationships
• Difficulty with boundary setting at work

💡 THERAPEUTIC INSIGHTS:
• Client shows good self-awareness of stress responses
• Physical symptoms indicate need for anxiety management techniques
• Family relationships being affected suggests stress spillover
• Manager relationship may need professional boundary discussions

📈 PROGRESS INDICATORS:
• Client is articulating emotions clearly
• Recognition of physical symptoms shows increased mindfulness
• Willingness to explore impact on family relationships

⚠️ AREAS OF CONCERN:
• Sleep disruption can compound stress and emotional regulation
• Family conflict may create additional stress cycles
• Work boundaries appear unclear or ineffective

🔄 RECOMMENDED INTERVENTIONS:
• Stress reduction techniques (breathing exercises, progressive muscle relaxation)
• Communication strategies for workplace boundaries
• Family session to address relationship impact
• Sleep hygiene education and practices

📊 SESSION METRICS:
• Client engagement: High
• Emotional awareness: Good
• Therapeutic alliance: Strong
• Risk factors: Low-Medium (work stress)"""

        self.results_text.insert("0.0", sample_analysis)

    def create_export_tab(self):
        """Create the export and session management tab"""
        tab = self.notebook.add("Export")

        # Export options
        export_frame = ctk.CTkFrame(tab)
        export_frame.pack(fill="x", padx=10, pady=10)

        export_title = ctk.CTkLabel(
            export_frame,
            text="Session Export & Management",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        export_title.pack(pady=(15, 20))

        # Export buttons grid
        buttons_frame = ctk.CTkFrame(export_frame)
        buttons_frame.pack(pady=(0, 15))

        export_buttons = [
            ("📄 Export Transcript", self.export_transcript, "#3498DB"),
            ("🧠 Export Analysis", self.export_analysis, "#9B59B6"),
            ("📊 Export Full Report", self.export_full_report, "#2CC985"),
            ("💾 Save Session", self.save_session, "#F39C12")
        ]

        for i, (text, command, color) in enumerate(export_buttons):
            row = i // 2
            col = i % 2

            button = ctk.CTkButton(
                buttons_frame,
                text=text,
                command=command,
                width=200,
                height=40,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=color
            )
            button.grid(row=row, column=col, padx=15, pady=10)

        # Session history
        history_frame = ctk.CTkFrame(tab)
        history_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        history_title = ctk.CTkLabel(
            history_frame,
            text="Session History",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        history_title.pack(pady=(15, 10))

        # History list
        self.history_listbox = ctk.CTkScrollableFrame(history_frame, height=200)
        self.history_listbox.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Add sample history items
        self.add_history_items()

    def create_settings_tab(self):
        """Create the settings and configuration tab"""
        tab = self.notebook.add("Settings")

        # Settings sections
        settings_frame = ctk.CTkScrollableFrame(tab)
        settings_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Analysis settings
        analysis_settings = ctk.CTkFrame(settings_frame)
        analysis_settings.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            analysis_settings,
            text="Analysis Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Auto-analysis toggle
        self.auto_analysis_var = ctk.BooleanVar()
        auto_analysis_cb = ctk.CTkCheckBox(
            analysis_settings,
            text="Auto-analyze every 3 minutes during session",
            variable=self.auto_analysis_var,
            font=ctk.CTkFont(size=11)
        )
        auto_analysis_cb.pack(anchor="w", padx=15, pady=5)

        # Analysis depth
        depth_frame = ctk.CTkFrame(analysis_settings, fg_color="transparent")
        depth_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(depth_frame, text="Analysis Depth:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.analysis_depth = ctk.CTkSlider(depth_frame, from_=1, to=5, number_of_steps=4)
        self.analysis_depth.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.analysis_depth.set(3)

        # Privacy settings
        privacy_settings = ctk.CTkFrame(settings_frame)
        privacy_settings.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            privacy_settings,
            text="Privacy Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Local processing
        self.local_processing_var = ctk.BooleanVar(value=True)
        local_cb = ctk.CTkCheckBox(
            privacy_settings,
            text="Use local Whisper transcription (recommended)",
            variable=self.local_processing_var,
            font=ctk.CTkFont(size=11)
        )
        local_cb.pack(anchor="w", padx=15, pady=5)

        # Data retention
        retention_frame = ctk.CTkFrame(privacy_settings, fg_color="transparent")
        retention_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(retention_frame, text="Data Retention (days):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.retention_entry = ctk.CTkEntry(retention_frame, width=100, height=25)
        self.retention_entry.pack(side="left", padx=(10, 0))
        self.retention_entry.insert(0, "30")

        # Export settings
        export_settings = ctk.CTkFrame(settings_frame)
        export_settings.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            export_settings,
            text="Export Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Default export format
        format_frame = ctk.CTkFrame(export_settings, fg_color="transparent")
        format_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(format_frame, text="Default Format:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.export_format = ctk.CTkComboBox(
            format_frame,
            values=["PDF", "DOCX", "TXT", "JSON"],
            width=100,
            height=25
        )
        self.export_format.pack(side="left", padx=(10, 0))

        # Include timestamps
        self.include_timestamps_var = ctk.BooleanVar(value=True)
        timestamps_cb = ctk.CTkCheckBox(
            export_settings,
            text="Include timestamps in exports",
            variable=self.include_timestamps_var,
            font=ctk.CTkFont(size=11)
        )
        timestamps_cb.pack(anchor="w", padx=15, pady=(15, 20))

    def add_history_items(self):
        """Add sample session history items"""
        sessions = [
            {"date": "2024-01-15 14:30", "client": "Session #47", "duration": "50 min", "status": "Complete"},
            {"date": "2024-01-12 10:00", "client": "Session #46", "duration": "45 min", "status": "Complete"},
            {"date": "2024-01-08 15:15", "client": "Session #45", "duration": "50 min", "status": "Complete"},
            {"date": "2024-01-05 11:30", "client": "Session #44", "duration": "50 min", "status": "Complete"},
        ]

        for session in sessions:
            session_frame = ctk.CTkFrame(self.history_listbox)
            session_frame.pack(fill="x", pady=5)

            # Session info
            info_text = f"{session['date']} - {session['client']} ({session['duration']})"
            ctk.CTkLabel(session_frame, text=info_text, font=ctk.CTkFont(size=11)).pack(side="left", padx=15, pady=10)

            # Load button
            load_btn = ctk.CTkButton(
                session_frame,
                text="Load",
                command=lambda s=session: self.load_session(s),
                width=60,
                height=25,
                font=ctk.CTkFont(size=10)
            )
            load_btn.pack(side="right", padx=15, pady=5)

    def filter_transcript(self, selected_filter):
        """Filter transcript by speaker"""
        # In a real implementation, this would filter the transcript display
        self.status_label.configure(text=f"[*] Filter applied: {selected_filter}")

    def start_analysis(self):
        """Start AI analysis of the current session"""
        if self.is_analyzing:
            return

        analysis_type = self.analysis_type_var.get()

        # Show custom prompt frame if custom analysis selected
        if analysis_type == "Custom":
            self.custom_frame.pack(fill="x", padx=10, pady=(0, 10), before=self.notebook)
        else:
            self.custom_frame.pack_forget()

        # Get the prompt based on analysis type
        prompt = self.get_analysis_prompt(analysis_type)

        if not prompt:
            self.status_label.configure(text="[!] Please enter a custom prompt", text_color="#E74C3C")
            return

        # Start analysis thread
        self.is_analyzing = True
        self.analyze_button.configure(text="Analyzing...", state="disabled")
        self.status_label.configure(text="[*] AI analysis in progress...", text_color="#F39C12")

        thread = threading.Thread(target=self.run_analysis, args=(prompt, analysis_type))
        thread.daemon = True
        thread.start()

    def get_analysis_prompt(self, analysis_type: str) -> str:
        """Get the appropriate prompt for the analysis type"""
        prompts = {
            "Comprehensive": "Provide a comprehensive therapeutic analysis of this session transcript, including key themes, insights, progress indicators, areas of concern, and recommended interventions.",
            "Themes": "Identify key emotional themes and behavioral patterns from this therapy session transcript.",
            "Progress": "Assess therapeutic progress, breakthroughs, and client growth from this session transcript.",
            "Risk Assessment": "Identify safety concerns, crisis indicators, or urgent issues requiring immediate attention in this session transcript.",
            "Dynamics": "Analyze relationship dynamics and communication patterns in this therapy session transcript.",
            "Custom": self.custom_prompt.get("0.0", "end").strip()
        }
        return prompts.get(analysis_type, "")

    def run_analysis(self, prompt: str, analysis_type: str):
        """Run the AI analysis in a background thread"""
        try:
            # Simulate progress updates
            for i in range(0, 101, 10):
                self.window.after(0, lambda p=i/100: self.analysis_progress.set(p))
                threading.Event().wait(0.2)

            # Get the current transcript
            transcript = self.get_current_transcript()

            # Call Claude API for analysis
            full_prompt = f"{prompt}\n\nSession Transcript:\n{transcript}"
            response = self.api_manager.get_claude_analysis(full_prompt)

            # Update UI with results
            self.window.after(0, lambda: self.analysis_complete(response, analysis_type))

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            self.window.after(0, lambda: self.analysis_failed(error_msg))

    def analysis_complete(self, result: str, analysis_type: str):
        """Handle completed analysis"""
        self.is_analyzing = False
        self.analyze_button.configure(text="🧠 Analyze Current Session", state="normal")
        self.analysis_progress.set(1.0)
        self.status_label.configure(text="[*] Analysis completed successfully", text_color="#2CC985")

        # Update results display
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"{analysis_type.upper()} ANALYSIS RESULTS\nGenerated: {timestamp}\n\n"

        self.results_text.configure(state="normal")
        self.results_text.delete("0.0", "end")
        self.results_text.insert("0.0", header + result)
        self.results_text.configure(state="disabled")

        # Store result
        self.analysis_results[analysis_type] = {
            'timestamp': timestamp,
            'result': result
        }

        # Switch to analysis tab
        self.notebook.set("Analysis")

    def analysis_failed(self, error: str):
        """Handle failed analysis"""
        self.is_analyzing = False
        self.analyze_button.configure(text="🧠 Analyze Current Session", state="normal")
        self.analysis_progress.set(0)
        self.status_label.configure(text=f"[!] {error}", text_color="#E74C3C")

    def get_current_transcript(self) -> str:
        """Get the current transcript text"""
        return self.transcript_text.get("0.0", "end")

    def update_transcript(self, new_text: str):
        """Update the transcript display with new text"""
        self.transcript_text.configure(state="normal")
        self.transcript_text.delete("0.0", "end")
        self.transcript_text.insert("0.0", new_text)
        self.transcript_text.configure(state="disabled")

        if self.auto_scroll_var.get():
            self.transcript_text.see("end")

    def update_session_info(self, session_info: str):
        """Update session information display"""
        self.session_info_label.configure(text=session_info)

    def export_transcript(self):
        """Export the current transcript"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.get_current_transcript())
                self.status_label.configure(text=f"[*] Transcript exported to {filename}", text_color="#2CC985")
            except Exception as e:
                self.status_label.configure(text=f"[!] Export failed: {e}", text_color="#E74C3C")

    def export_analysis(self):
        """Export the current analysis results"""
        if not self.analysis_results:
            self.status_label.configure(text="[!] No analysis results to export", text_color="#E74C3C")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    if filename.endswith('.json'):
                        json.dump(self.analysis_results, f, indent=2)
                    else:
                        for analysis_type, data in self.analysis_results.items():
                            f.write(f"{analysis_type.upper()} ANALYSIS\n")
                            f.write(f"Generated: {data['timestamp']}\n\n")
                            f.write(data['result'])
                            f.write("\n\n" + "="*50 + "\n\n")

                self.status_label.configure(text=f"[*] Analysis exported to {filename}", text_color="#2CC985")
            except Exception as e:
                self.status_label.configure(text=f"[!] Export failed: {e}", text_color="#E74C3C")

    def export_full_report(self):
        """Export a complete session report"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    # Header
                    f.write("AMANUENSIS THERAPY SESSION REPORT\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                    # Session info
                    f.write("SESSION INFORMATION\n")
                    f.write("-" * 20 + "\n")
                    f.write(f"Session: {self.session_info_label.cget('text')}\n\n")

                    # Transcript
                    f.write("TRANSCRIPT\n")
                    f.write("-" * 20 + "\n")
                    f.write(self.get_current_transcript())
                    f.write("\n\n")

                    # Analysis results
                    if self.analysis_results:
                        f.write("ANALYSIS RESULTS\n")
                        f.write("-" * 20 + "\n\n")
                        for analysis_type, data in self.analysis_results.items():
                            f.write(f"{analysis_type.upper()}\n")
                            f.write(f"Generated: {data['timestamp']}\n\n")
                            f.write(data['result'])
                            f.write("\n\n")

                self.status_label.configure(text=f"[*] Full report exported to {filename}", text_color="#2CC985")
            except Exception as e:
                self.status_label.configure(text=f"[!] Export failed: {e}", text_color="#E74C3C")

    def save_session(self):
        """Save the current session data"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}.json"

        session_data = {
            'timestamp': timestamp,
            'transcript': self.get_current_transcript(),
            'analysis_results': self.analysis_results,
            'session_info': self.session_info_label.cget('text')
        }

        try:
            sessions_dir = "sessions"
            os.makedirs(sessions_dir, exist_ok=True)
            filepath = os.path.join(sessions_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)

            self.status_label.configure(text=f"[*] Session saved as {filename}", text_color="#2CC985")
        except Exception as e:
            self.status_label.configure(text=f"[!] Save failed: {e}", text_color="#E74C3C")

    def load_session(self, session_data):
        """Load a previous session"""
        self.status_label.configure(text=f"[*] Loading session: {session_data['client']}", text_color="#F39C12")
        # In a real implementation, this would load the actual session data

    def close_dashboard(self):
        """Close the dashboard"""
        if self.on_close:
            self.on_close()
        self.window.destroy()

    def show(self):
        """Show the dashboard window"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus()

def test_insights_dashboard():
    """Test the insights dashboard"""
    from config_manager import SecureConfigManager

    config = SecureConfigManager()
    dashboard = InsightsDashboard(config)

    # Show the window
    dashboard.show()
    dashboard.window.mainloop()

if __name__ == "__main__":
    test_insights_dashboard()