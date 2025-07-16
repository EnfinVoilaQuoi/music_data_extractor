# diagnostic_imports.py
"""Script de diagnostic pour identifier les problèmes d'imports"""

import sys
from pathlib import Path

def test_individual_imports():
    """Test chaque import individuellement"""
    print("🔍 Test des imports individuels...")
    
    imports_to_test = [
        ("models.entities", "Artist, Track, Album"),
        ("models.enums", "SessionStatus, ExtractionStatus"),
        ("core.database", "Database"),
        ("core.session_manager", "SessionManager"),
        ("utils.text_utils", "clean_artist_name"),
        ("config.settings", "settings"),
    ]
    
    for module, items in imports_to_test:
        try:
            exec(f"from {module} import {items}")
            print(f"✅ {module}: {items}")
        except Exception as e:
            print(f"❌ {module}: {e}")
    
    print("\n🧪 Test des steps...")
    
    # Test des steps un par un
    steps_to_test = [
        "steps.step1_discover",
        "steps.step2_extract", 
        "steps.step3_process",
        "steps.step4_export"
    ]
    
    for step in steps_to_test:
        try:
            module = __import__(step, fromlist=[''])
            print(f"✅ {step} importé")
        except Exception as e:
            print(f"❌ {step}: {e}")

if __name__ == "__main__":
    test_individual_imports()
