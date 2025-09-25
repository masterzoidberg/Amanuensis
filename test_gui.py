#!/usr/bin/env python3
"""
Test just the GUI components of Amanuensis
"""

import customtkinter as ctk
from tkinter import messagebox

def main():
    """Create and test a simplified GUI"""
    print("Starting GUI test...")

    # Set appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create main window
    root = ctk.CTk()
    root.title("Amanuensis GUI Test")
    root.geometry("800x600")

    # Header
    header = ctk.CTkFrame(root)
    header.pack(fill="x", padx=20, pady=20)

    title = ctk.CTkLabel(
        header,
        text="Amanuensis - GUI Test",
        font=ctk.CTkFont(size=24, weight="bold")
    )
    title.pack(pady=20)

    # Main content
    content = ctk.CTkFrame(root)
    content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # Left panel
    left = ctk.CTkFrame(content)
    left.pack(side="left", fill="both", expand=False, padx=(20, 10), pady=20)
    left.configure(width=300)

    ctk.CTkLabel(left, text="Session Setup", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)

    # Client count
    client_frame = ctk.CTkFrame(left)
    client_frame.pack(fill="x", padx=20, pady=10)

    ctk.CTkLabel(client_frame, text="Clients:").pack(side="left", padx=20, pady=15)
    client_combo = ctk.CTkComboBox(client_frame, values=["1", "2", "3"])
    client_combo.pack(side="right", padx=20, pady=15)

    # Buttons
    button_frame = ctk.CTkFrame(left)
    button_frame.pack(fill="x", padx=20, pady=20)

    def test_button():
        messagebox.showinfo("Test", "Button clicked successfully!")

    record_btn = ctk.CTkButton(
        button_frame,
        text="Test Recording",
        command=test_button,
        width=200,
        height=50,
        font=ctk.CTkFont(size=16, weight="bold"),
        fg_color=("#2CC985", "#2FA572")
    )
    record_btn.pack(pady=10)

    analyze_btn = ctk.CTkButton(
        button_frame,
        text="Test Analysis",
        command=test_button,
        width=200,
        height=40,
        font=ctk.CTkFont(size=14),
        fg_color=("#FF6B35", "#E8590C")
    )
    analyze_btn.pack(pady=10)

    # Right panel
    right = ctk.CTkFrame(content)
    right.pack(side="right", fill="both", expand=True, padx=(10, 20), pady=20)

    ctk.CTkLabel(right, text="AI Insights", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)

    insights = ctk.CTkTextbox(right, font=ctk.CTkFont(size=13))
    insights.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    insights.insert("0.0", "This is a test of the AI insights panel.\\n\\nAll GUI components are working correctly!")
    insights.configure(state="disabled")

    # Status bar
    status_frame = ctk.CTkFrame(root)
    status_frame.pack(fill="x", padx=20, pady=(0, 20))

    status_label = ctk.CTkLabel(
        status_frame,
        text="[*] GUI Test - All Components Working",
        font=ctk.CTkFont(size=14),
        text_color="#2CC985"
    )
    status_label.pack(pady=10)

    print("GUI components created successfully!")
    print("Close the window to exit...")

    # Run the GUI
    root.mainloop()
    print("GUI test completed successfully!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"GUI test failed: {e}")
        import traceback
        traceback.print_exc()