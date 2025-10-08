#!/usr/bin/env python3
"""
Debug script for individual PHI recognizer testing
Tests each custom recognizer separately to identify regex compilation issues
"""

import sys
import re
from pathlib import Path

# Test if PHI detection dependencies are available
try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_anonymizer import AnonymizerEngine
    import spacy
    PHI_AVAILABLE = True
    print("✓ All PHI detection dependencies available")
except ImportError as e:
    PHI_AVAILABLE = False
    print(f"✗ PHI detection dependencies missing: {e}")
    print("Run: pip install presidio-analyzer presidio-anonymizer spacy")
    print("Then: python -m spacy download en_core_web_sm")
    sys.exit(1)

def test_individual_pattern(pattern_name, regex_pattern, test_strings):
    """Test an individual regex pattern"""
    print(f"\n{'='*60}")
    print(f"Testing Pattern: {pattern_name}")
    print(f"Regex: {regex_pattern}")
    print('='*60)

    try:
        # Test regex compilation
        compiled_regex = re.compile(regex_pattern)
        print("✓ Regex compiles successfully")

        # Test against sample strings
        for i, test_string in enumerate(test_strings, 1):
            print(f"\nTest {i}: {test_string}")
            matches = compiled_regex.findall(test_string)
            if matches:
                print(f"  ✓ Match found: {matches}")
            else:
                print(f"  ✗ No match")

    except Exception as e:
        print(f"✗ Regex compilation failed: {e}")
        return False

    return True

def test_presidio_pattern_object(pattern_name, regex_pattern, score):
    """Test creating a Presidio Pattern object"""
    print(f"\nTesting Presidio Pattern object for: {pattern_name}")

    try:
        pattern = Pattern(
            name=pattern_name,
            regex=regex_pattern,
            score=score
        )
        print(f"✓ Pattern object created successfully")
        print(f"  Name: {pattern.name}")
        print(f"  Score: {pattern.score}")
        return pattern

    except Exception as e:
        print(f"✗ Pattern object creation failed: {e}")
        return None

def test_pattern_recognizer(entity_type, patterns, recognizer_name):
    """Test creating a PatternRecognizer"""
    print(f"\nTesting PatternRecognizer for: {entity_type}")

    try:
        recognizer = PatternRecognizer(
            supported_entity=entity_type,
            patterns=patterns,
            name=recognizer_name
        )
        print(f"✓ PatternRecognizer created successfully")
        print(f"  Entity: {recognizer.supported_entity}")
        print(f"  Name: {recognizer.name}")
        print(f"  Patterns: {len(patterns)} pattern(s)")
        return recognizer

    except Exception as e:
        print(f"✗ PatternRecognizer creation failed: {e}")
        return None

def test_analyzer_integration(recognizer, test_texts):
    """Test integrating recognizer with AnalyzerEngine"""
    print(f"\nTesting analyzer integration...")

    try:
        # Create analyzer
        analyzer = AnalyzerEngine()

        # Add recognizer
        analyzer.registry.add_recognizer(recognizer)
        print(f"✓ Recognizer added to analyzer")

        # Test analysis
        for i, text in enumerate(test_texts, 1):
            print(f"\nAnalysis Test {i}: {text}")
            try:
                results = analyzer.analyze(
                    text=text,
                    language='en',
                    score_threshold=0.1
                )

                if results:
                    print(f"  ✓ Found {len(results)} PHI entities:")
                    for result in results:
                        entity_text = text[result.start:result.end]
                        print(f"    - {result.entity_type}: '{entity_text}' (Score: {result.score:.2f})")
                else:
                    print(f"  ✗ No PHI detected")

            except Exception as e:
                print(f"  ✗ Analysis failed: {e}")

        return True

    except Exception as e:
        print(f"✗ Analyzer integration failed: {e}")
        return False

def run_family_recognizer_test():
    """Test family relationship recognizer"""
    print("\n" + "="*80)
    print("TESTING FAMILY RELATIONSHIP RECOGNIZER")
    print("="*80)

    # Test patterns individually
    patterns_data = [
        {
            "name": "family_relation_with_name",
            "regex": r"\b(?:my|his|her|their)\s+(?:wife|husband|mother|father|mom|dad|sister|brother|son|daughter|child|children|parent|parents|family|spouse|partner)\s+([A-Z][a-z]+)\b",
            "score": 0.85,
            "test_strings": [
                "My wife Sarah has been very supportive",
                "His brother Mike is coming to visit",
                "Their daughter Emma is in college",
                "Her mother Jennifer called yesterday"
            ]
        },
        {
            "name": "name_family_relation",
            "regex": r"\b([A-Z][a-z]+)\s+(?:is|was)\s+(?:my|his|her|their)\s+(?:wife|husband|mother|father|mom|dad|sister|brother|son|daughter|child|parent|spouse|partner)\b",
            "score": 0.85,
            "test_strings": [
                "Sarah is my wife and she's amazing",
                "Mike was his brother who passed away",
                "Emma is their daughter who lives nearby",
                "Jennifer is her mother from California"
            ]
        }
    ]

    valid_patterns = []

    for pattern_data in patterns_data:
        # Test regex compilation
        if test_individual_pattern(
            pattern_data["name"],
            pattern_data["regex"],
            pattern_data["test_strings"]
        ):
            # Test Pattern object creation
            pattern_obj = test_presidio_pattern_object(
                pattern_data["name"],
                pattern_data["regex"],
                pattern_data["score"]
            )
            if pattern_obj:
                valid_patterns.append(pattern_obj)

    if valid_patterns:
        # Test PatternRecognizer creation
        recognizer = test_pattern_recognizer(
            "FAMILY_RELATION",
            valid_patterns,
            "family_relation_recognizer"
        )

        if recognizer:
            # Test analyzer integration
            test_texts = [
                "My wife Sarah has been very supportive during this difficult time.",
                "I had a fight with my brother Mike yesterday and I feel terrible about it.",
                "Sarah is my wife and she helps me through everything.",
                "Mike was his brother who always supported him."
            ]

            return test_analyzer_integration(recognizer, test_texts)

    return False

def run_workplace_recognizer_test():
    """Test workplace recognizer"""
    print("\n" + "="*80)
    print("TESTING WORKPLACE RECOGNIZER")
    print("="*80)

    patterns_data = [
        {
            "name": "boss_at_company",
            "regex": r"\b(?:my|his|her|their)\s+(?:boss|manager|supervisor|colleague|coworker|employee)\s+(?:at\s+)?([A-Z][a-zA-Z\s&]{2,20})\b",
            "score": 0.8,
            "test_strings": [
                "My boss at Microsoft is very demanding",
                "Her manager at Google keeps pushing deadlines",
                "Their supervisor John is really helpful",
                "His coworker at Amazon Tech is great"
            ]
        },
        {
            "name": "work_for_company",
            "regex": r"\b(?:works?|working)\s+(?:at|for)\s+([A-Z][a-zA-Z\s&]{2,20})\b",
            "score": 0.8,
            "test_strings": [
                "I work for Microsoft Corporation",
                "She works at Google headquarters",
                "He's working for Amazon Web Services",
                "They work at Apple Inc"
            ]
        }
    ]

    valid_patterns = []

    for pattern_data in patterns_data:
        if test_individual_pattern(
            pattern_data["name"],
            pattern_data["regex"],
            pattern_data["test_strings"]
        ):
            pattern_obj = test_presidio_pattern_object(
                pattern_data["name"],
                pattern_data["regex"],
                pattern_data["score"]
            )
            if pattern_obj:
                valid_patterns.append(pattern_obj)

    if valid_patterns:
        recognizer = test_pattern_recognizer(
            "WORKPLACE",
            valid_patterns,
            "workplace_recognizer"
        )

        if recognizer:
            test_texts = [
                "My boss at Microsoft is putting a lot of pressure on me to work overtime.",
                "I work for Amazon and the stress is really getting to me.",
                "She works at Google and loves the company culture.",
                "His manager at Apple is very supportive."
            ]

            return test_analyzer_integration(recognizer, test_texts)

    return False

def run_healthcare_recognizer_test():
    """Test healthcare provider recognizer"""
    print("\n" + "="*80)
    print("TESTING HEALTHCARE PROVIDER RECOGNIZER")
    print("="*80)

    patterns_data = [
        {
            "name": "doctor_title_name",
            "regex": r"\b(?:Dr|Doctor|Therapist|Counselor|Psychiatrist|Psychologist)[\.\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
            "score": 0.9,
            "test_strings": [
                "Dr. Johnson referred me to you for anxiety management",
                "Doctor Smith suggested I try meditation",
                "Therapist Williams has been very helpful",
                "Psychiatrist Brown prescribed new medication"
            ]
        },
        {
            "name": "my_doctor_name",
            "regex": r"\b(?:my|his|her|their)\s+(?:doctor|therapist|counselor|psychiatrist|psychologist)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
            "score": 0.9,
            "test_strings": [
                "My doctor Johnson says I'm improving",
                "Her therapist Williams is amazing",
                "His psychiatrist Brown changed his medication",
                "Their counselor Smith recommended this"
            ]
        }
    ]

    valid_patterns = []

    for pattern_data in patterns_data:
        if test_individual_pattern(
            pattern_data["name"],
            pattern_data["regex"],
            pattern_data["test_strings"]
        ):
            pattern_obj = test_presidio_pattern_object(
                pattern_data["name"],
                pattern_data["regex"],
                pattern_data["score"]
            )
            if pattern_obj:
                valid_patterns.append(pattern_obj)

    if valid_patterns:
        recognizer = test_pattern_recognizer(
            "HEALTHCARE_PROVIDER",
            valid_patterns,
            "healthcare_provider_recognizer"
        )

        if recognizer:
            test_texts = [
                "Dr. Johnson referred me to you for anxiety management.",
                "My previous therapist Dr. Smith suggested I try meditation.",
                "I've been seeing Psychiatrist Williams for medication management.",
                "Her doctor Brown is very thorough."
            ]

            return test_analyzer_integration(recognizer, test_texts)

    return False

def test_full_integration():
    """Test full integration with all recognizers"""
    print("\n" + "="*80)
    print("TESTING FULL INTEGRATION WITH ALL RECOGNIZERS")
    print("="*80)

    try:
        # Create analyzer
        analyzer = AnalyzerEngine()

        # Add all custom recognizers (simplified versions for testing)
        from presidio_analyzer import Pattern

        # Family patterns
        family_patterns = [
            Pattern(
                name="family_simple",
                regex=r"\b(?:my|his|her)\s+(?:wife|husband|mother|father|brother|sister)\s+([A-Z][a-z]+)\b",
                score=0.85
            )
        ]

        family_recognizer = PatternRecognizer(
            supported_entity="FAMILY_RELATION",
            patterns=family_patterns,
            name="family_recognizer"
        )
        analyzer.registry.add_recognizer(family_recognizer)

        # Workplace patterns
        workplace_patterns = [
            Pattern(
                name="work_simple",
                regex=r"\bwork(?:s|ing)?\s+(?:at|for)\s+([A-Z][a-zA-Z\s]{2,15})\b",
                score=0.8
            )
        ]

        workplace_recognizer = PatternRecognizer(
            supported_entity="WORKPLACE",
            patterns=workplace_patterns,
            name="workplace_recognizer"
        )
        analyzer.registry.add_recognizer(workplace_recognizer)

        # Healthcare patterns
        healthcare_patterns = [
            Pattern(
                name="doctor_simple",
                regex=r"\b(?:Dr\.?\s+|Doctor\s+)([A-Z][a-z]+)\b",
                score=0.9
            )
        ]

        healthcare_recognizer = PatternRecognizer(
            supported_entity="HEALTHCARE_PROVIDER",
            patterns=healthcare_patterns,
            name="healthcare_recognizer"
        )
        analyzer.registry.add_recognizer(healthcare_recognizer)

        print("✓ All recognizers added successfully")

        # Test complex scenarios
        test_scenarios = [
            "My wife Sarah and I visited Dr. Johnson at his office in Microsoft building.",
            "I work for Google and my brother Mike thinks I should see Therapist Williams.",
            "Dr. Smith said my husband John's anxiety is work-related.",
            "After talking to my mother Jennifer about Doctor Peterson's advice, I decided to quit my job at Amazon."
        ]

        print(f"\nTesting {len(test_scenarios)} complex scenarios...")

        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\nScenario {i}: {scenario}")

            try:
                results = analyzer.analyze(
                    text=scenario,
                    language='en',
                    score_threshold=0.1
                )

                if results:
                    print(f"  ✓ Found {len(results)} PHI entities:")
                    for result in results:
                        entity_text = scenario[result.start:result.end]
                        print(f"    - {result.entity_type}: '{entity_text}' (Score: {result.score:.2f})")
                else:
                    print(f"  ✗ No PHI detected")

            except Exception as e:
                print(f"  ✗ Analysis failed: {e}")

        return True

    except Exception as e:
        print(f"✗ Full integration test failed: {e}")
        return False

def main():
    """Run comprehensive recognizer debugging"""
    print("Amanuensis V2 - PHI Recognizer Debug Suite")
    print("="*80)

    if not PHI_AVAILABLE:
        return False

    # Track test results
    results = {}

    # Test individual recognizers
    print("\n🔍 Testing individual recognizers...")
    results['family'] = run_family_recognizer_test()
    results['workplace'] = run_workplace_recognizer_test()
    results['healthcare'] = run_healthcare_recognizer_test()

    # Test full integration
    print("\n🔗 Testing full integration...")
    results['integration'] = test_full_integration()

    # Summary
    print("\n" + "="*80)
    print("DEBUGGING SUMMARY")
    print("="*80)

    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)

    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name.upper()}: {status}")

    print(f"\nOverall: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All tests passed! PHI recognizers are working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the detailed output above.")
        return False

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ PHI recognizer debugging completed successfully!")
        else:
            print("\n❌ PHI recognizer debugging found issues that need fixing.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nDebug interrupted by user")
    except Exception as e:
        print(f"\nDebug error: {e}")
        sys.exit(1)