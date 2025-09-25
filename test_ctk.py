#!/usr/bin/env python3
"""
CustomTkinter compatibility test for Amanuensis
"""

import customtkinter as ctk

def test_basic_components():
    """Test basic CustomTkinter components"""
    print("Testing CustomTkinter components...")

    # Test basic window
    root = ctk.CTk()
    root.title("CTK Test")
    root.geometry("400x300")

    # Test basic components
    frame = ctk.CTkFrame(root)
    frame.pack(padx=20, pady=20)

    label = ctk.CTkLabel(frame, text="Test Label")
    label.pack(pady=10)

    # Test entry without placeholder_text
    entry = ctk.CTkEntry(frame, width=200)
    entry.pack(pady=10)

    # Test button
    button = ctk.CTkButton(frame, text="Test Button")
    button.pack(pady=10)

    # Test combobox
    combo = ctk.CTkComboBox(frame, values=["Option 1", "Option 2"])
    combo.pack(pady=10)

    # Test textbox
    textbox = ctk.CTkTextbox(frame, width=300, height=100)
    textbox.pack(pady=10)

    print("All components created successfully!")
    print("CustomTkinter version:", ctk.__version__ if hasattr(ctk, '__version__') else "Unknown")

    # Close immediately for automated testing
    root.after(1000, root.destroy)
    root.mainloop()

if __name__ == "__main__":
    try:
        test_basic_components()
        print("SUCCESS: CustomTkinter compatibility test passed!")
    except Exception as e:
        print(f"FAILED: CustomTkinter compatibility test failed: {e}")
        import traceback
        traceback.print_exc()