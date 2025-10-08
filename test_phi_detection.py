#!/usr/bin/env python3
"""
Test script for PHI detection functionality
Tests Presidio integration with sample therapy transcript data
"""

import sys
import time
from datetime import datetime

# Test if PHI detection dependencies are available
try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine
    import spacy
    PHI_AVAILABLE = True
    print("✓ PHI detection dependencies available")
except ImportError as e:
    PHI_AVAILABLE = False
    print(f"✗ PHI detection dependencies missing: {e}")
    print("Run: pip install presidio-analyzer presidio-anonymizer spacy")
    print("Then: python -m spacy download en_core_web_sm")

def setup_phi_analyzer():
    """Set up Presidio analyzer with therapy-specific recognizers using proper Pattern objects"""
    if not PHI_AVAILABLE:
        return None, None

    try:
        # Import Pattern class - this was the missing piece!
        from presidio_analyzer import Pattern

        # Initialize Presidio Analyzer
        analyzer = AnalyzerEngine()

        # Add family relationship recognizer with proper Pattern objects
        family_patterns = [
            Pattern(
                name="family_relation_with_name",
                regex=r"\b(?:my|his|her|their)\s+(?:wife|husband|mother|father|mom|dad|sister|brother|son|daughter|child|children|parent|parents|family|spouse|partner)\s+([A-Z][a-z]+)\b",
                score=0.85
            ),
            Pattern(
                name="name_family_relation",
                regex=r"\b([A-Z][a-z]+)\s+(?:is|was)\s+(?:my|his|her|their)\s+(?:wife|husband|mother|father|mom|dad|sister|brother|son|daughter|child|parent|spouse|partner)\b",
                score=0.85
            )
        ]

        family_recognizer = PatternRecognizer(
            supported_entity="FAMILY_RELATION",
            patterns=family_patterns,
            name="family_relation_recognizer"
        )
        analyzer.registry.add_recognizer(family_recognizer)

        # Add workplace recognizer with proper Pattern objects
        workplace_patterns = [
            Pattern(
                name="boss_at_company",
                regex=r"\b(?:my|his|her|their)\s+(?:boss|manager|supervisor|colleague|coworker|employee)\s+(?:at\s+)?([A-Z][a-zA-Z\s&]{2,20})\b",
                score=0.8
            ),
            Pattern(
                name="work_for_company",
                regex=r"\b(?:works?|working)\s+(?:at|for)\s+([A-Z][a-zA-Z\s&]{2,20})\b",
                score=0.8
            ),
            Pattern(
                name="company_mention",
                regex=r"\b(?:company|organization|business|firm|office)\s+(?:called|named)?\s*([A-Z][a-zA-Z\s&]{2,20})\b",
                score=0.7
            )
        ]

        workplace_recognizer = PatternRecognizer(
            supported_entity="WORKPLACE",
            patterns=workplace_patterns,
            name="workplace_recognizer"
        )
        analyzer.registry.add_recognizer(workplace_recognizer)

        # Add healthcare provider recognizer with proper Pattern objects
        healthcare_patterns = [
            Pattern(
                name="doctor_title_name",
                regex=r"\b(?:Dr|Doctor|Therapist|Counselor|Psychiatrist|Psychologist)[\.\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
                score=0.9
            ),
            Pattern(
                name="my_doctor_name",
                regex=r"\b(?:my|his|her|their)\s+(?:doctor|therapist|counselor|psychiatrist|psychologist)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
                score=0.9
            )
        ]

        healthcare_recognizer = PatternRecognizer(
            supported_entity="HEALTHCARE_PROVIDER",
            patterns=healthcare_patterns,
            name="healthcare_provider_recognizer"
        )
        analyzer.registry.add_recognizer(healthcare_recognizer)

        # Add education recognizer
        education_patterns = [
            Pattern(
                name="school_name",
                regex=r"\b(?:school|university|college)\s+(?:called|named)?\s*([A-Z][a-zA-Z\s&]{2,30})\b",
                score=0.7
            ),
            Pattern(
                name="attend_school",
                regex=r"\b(?:goes?|going|attend(?:s|ing)?)\s+(?:to\s+)?([A-Z][a-zA-Z\s&]+(?:School|University|College))\b",
                score=0.8
            )
        ]

        education_recognizer = PatternRecognizer(
            supported_entity="EDUCATION",
            patterns=education_patterns,
            name="education_recognizer"
        )
        analyzer.registry.add_recognizer(education_recognizer)

        # Initialize Anonymizer
        anonymizer = AnonymizerEngine()

        print("✓ PHI analyzer set up successfully with custom therapy recognizers")
        return analyzer, anonymizer

    except Exception as e:
        print(f"✗ Failed to set up PHI analyzer: {e}")
        print(f"Error details: {type(e).__name__}: {str(e)}")
        return None, None

def test_phi_detection(analyzer, sample_texts):
    """Test PHI detection on sample therapy transcript texts"""
    if not analyzer:
        print("✗ No PHI analyzer available for testing")
        return

    print("\n" + "="*60)
    print("PHI DETECTION TEST RESULTS")
    print("="*60)

    for i, text in enumerate(sample_texts, 1):
        print(f"\nTest {i}: {text[:50]}...")
        print("-" * 40)

        try:
            # Analyze for PHI with high recall settings
            results = analyzer.analyze(
                text=text,
                language='en',
                score_threshold=0.1  # Low threshold for high recall
            )

            if results:
                print(f"✓ Found {len(results)} PHI entities:")
                for result in results:
                    entity_text = text[result.start:result.end]
                    print(f"  - {result.entity_type}: '{entity_text}' (Score: {result.score:.2f})")
            else:
                print("✓ No PHI detected")

        except Exception as e:
            print(f"✗ PHI analysis error: {e}")

def test_anonymization(analyzer, anonymizer, text):
    """Test PHI anonymization on a sample text"""
    if not analyzer or not anonymizer:
        return

    print("\n" + "="*60)
    print("PHI ANONYMIZATION TEST")
    print("="*60)

    try:
        # Analyze for PHI
        results = analyzer.analyze(text=text, language='en', score_threshold=0.1)

        if results:
            print(f"Original text: {text}")

            # Anonymize the text
            anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)

            print(f"Anonymized text: {anonymized_result.text}")
            print(f"Anonymized {len(results)} entities")
        else:
            print("No PHI to anonymize")

    except Exception as e:
        print(f"✗ Anonymization error: {e}")

def run_comprehensive_test():
    """Run comprehensive PHI detection test suite"""
    print("Amanuensis V2 - PHI Detection Test Suite")
    print("="*50)

    # Sample therapy transcript texts with various PHI types
    sample_texts = [
        # Family relationships
        "My wife Sarah has been very supportive during this difficult time.",
        "I had a fight with my brother Mike yesterday and I feel terrible about it.",
        "My daughter Emma is having trouble at school and I don't know how to help her.",

        # Workplace information
        "My boss at Microsoft is putting a lot of pressure on me to work overtime.",
        "I work for Amazon and the stress is really getting to me.",
        "My coworker John at the company has been very difficult to work with.",

        # Healthcare providers
        "Dr. Johnson referred me to you for anxiety management.",
        "My previous therapist Dr. Smith suggested I try meditation.",
        "I've been seeing Psychiatrist Williams for medication management.",

        # Contact information
        "You can reach me at john.doe@email.com or call me at 555-123-4567.",
        "My address is 123 Main Street, New York, NY 10001.",

        # Mixed PHI
        "After talking to my wife Jennifer about Dr. Peterson's advice, I decided to quit my job at Google and focus on my mental health.",

        # Clean text (no PHI)
        "I've been feeling anxious lately and having trouble sleeping at night.",
        "The therapy sessions have been really helpful for managing my stress."
    ]

    # Set up PHI detection
    analyzer, anonymizer = setup_phi_analyzer()

    if not analyzer:
        print("Cannot run tests - PHI detection not available")
        return False

    # Test PHI detection
    test_phi_detection(analyzer, sample_texts)

    # Test anonymization
    test_text = "My wife Sarah and I visited Dr. Johnson at his office in Microsoft building."
    test_anonymization(analyzer, anonymizer, test_text)

    print("\n" + "="*60)
    print("PHI DETECTION TEST COMPLETED")
    print("="*60)

    return True

def simulate_transcript_workflow():
    """Simulate the actual transcript workflow with PHI detection"""
    if not PHI_AVAILABLE:
        print("Cannot simulate workflow - PHI detection not available")
        return

    print("\n" + "="*60)
    print("TRANSCRIPT WORKFLOW SIMULATION")
    print("="*60)

    # Sample formatted transcript segments (as they would appear from the transcription)
    transcript_segments = [
        "[14:23:15] [THERAPIST]: How are you feeling today?",
        "[14:23:22] [CLIENT]: I'm struggling with my relationship with my wife Jennifer.",
        "[14:23:35] [THERAPIST]: Can you tell me more about what's happening?",
        "[14:23:45] [CLIENT]: We had a big fight about my job at Microsoft and she thinks I work too much.",
        "[14:24:02] [THERAPIST]: Work-life balance can be challenging. Have you discussed this with Dr. Peterson before?",
        "[14:24:15] [CLIENT]: Yes, but I haven't made much progress. My email is john.smith@company.com if you need to contact me."
    ]

    analyzer, _ = setup_phi_analyzer()
    if not analyzer:
        return

    print("Processing transcript segments...")

    for i, segment in enumerate(transcript_segments, 1):
        print(f"\nSegment {i}: {segment}")

        # Extract plain text (simulate the extract_plain_text function)
        import re
        pattern = r'^\[\d{2}:\d{2}:\d{2}\]\s*\[\w+\]:\s*(.+)$'
        match = re.match(pattern, segment.strip())
        if match:
            plain_text = match.group(1).strip()
        else:
            plain_text = segment.strip()

        # Analyze for PHI
        try:
            results = analyzer.analyze(text=plain_text, language='en', score_threshold=0.1)

            if results:
                print(f"  → PHI DETECTED: {len(results)} entities - REQUIRES MANUAL REVIEW")
                for result in results:
                    entity_text = plain_text[result.start:result.end]
                    print(f"    - {result.entity_type}: '{entity_text}'")
            else:
                print(f"  → Clean segment - direct to transcript")

        except Exception as e:
            print(f"  → PHI analysis error: {e} - fallback to transcript")

def test_fixed_recognizers():
    """Test the fixed recognizers to ensure they work correctly"""
    print("\n" + "="*60)
    print("TESTING FIXED CUSTOM RECOGNIZERS")
    print("="*60)

    if not PHI_AVAILABLE:
        return False

    try:
        # Test the fixed recognizer setup
        analyzer, anonymizer = setup_phi_analyzer()
        if not analyzer:
            print("✗ Failed to set up analyzer")
            return False

        # Test specific patterns that were failing
        test_cases = [
            {
                "text": "My wife Sarah has been very supportive during this difficult time.",
                "expected": ["Sarah"],
                "type": "FAMILY_RELATION"
            },
            {
                "text": "I work for Microsoft and the stress is getting to me.",
                "expected": ["Microsoft"],
                "type": "WORKPLACE"
            },
            {
                "text": "Dr. Johnson referred me to you for anxiety management.",
                "expected": ["Johnson"],
                "type": "HEALTHCARE_PROVIDER"
            },
            {
                "text": "Mike is my brother who always supports me.",
                "expected": ["Mike"],
                "type": "FAMILY_RELATION"
            },
            {
                "text": "My boss at Google keeps pushing deadlines.",
                "expected": ["Google"],
                "type": "WORKPLACE"
            }
        ]

        passed_tests = 0
        total_tests = len(test_cases)

        for i, test_case in enumerate(test_cases, 1):
            print(f"\nTest {i}: {test_case['text']}")

            try:
                results = analyzer.analyze(
                    text=test_case['text'],
                    language='en',
                    score_threshold=0.1
                )

                if results:
                    found_entities = []
                    for result in results:
                        entity_text = test_case['text'][result.start:result.end]
                        found_entities.append(entity_text)
                        print(f"  ✓ Found {result.entity_type}: '{entity_text}' (Score: {result.score:.2f})")

                    # Check if expected entities were found
                    expected_found = any(expected in found_entities for expected in test_case['expected'])
                    if expected_found:
                        print(f"  ✓ Expected entities detected!")
                        passed_tests += 1
                    else:
                        print(f"  ⚠ Expected entities {test_case['expected']} not found in {found_entities}")
                else:
                    print(f"  ✗ No PHI detected (expected {test_case['expected']})")

            except Exception as e:
                print(f"  ✗ Analysis failed: {e}")

        print(f"\nFixed Recognizer Tests: {passed_tests}/{total_tests} passed")
        return passed_tests == total_tests

    except Exception as e:
        print(f"✗ Fixed recognizer test error: {e}")
        return False

if __name__ == "__main__":
    try:
        # Run comprehensive test
        success = run_comprehensive_test()

        if success:
            # Test the fixed recognizers
            print("\n" + "="*60)
            print("TESTING FIXED CUSTOM RECOGNIZERS")
            print("="*60)

            fixed_success = test_fixed_recognizers()

            # Run workflow simulation
            simulate_transcript_workflow()

            if fixed_success:
                print(f"\n✅ ALL PHI detection tests completed successfully!")
                print("🎉 Fixed custom recognizers are working correctly!")
                print("Your PHI detection system is ready for use!")
            else:
                print(f"\n⚠️  Basic tests passed but some custom recognizer issues remain")
                print("Check the detailed output above for specific failures")
        else:
            print(f"\n✗ PHI detection test failed")
            print("Please install dependencies and try again")

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest error: {e}")
        sys.exit(1)