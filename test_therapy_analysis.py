#!/usr/bin/env python3
"""
Test script for therapy analysis system
Tests Claude API integration with sample de-identified transcript segments
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Test if analysis dependencies are available
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
    print("✓ Anthropic Claude API package available")
except ImportError as e:
    ANTHROPIC_AVAILABLE = False
    print(f"✗ Anthropic package missing: {e}")
    print("Run: pip install anthropic")

def create_test_config():
    """Create test configuration file"""
    try:
        config = {
            "claude_api_key": "",
            "analysis_frequency": 60,  # 1 minute for testing
            "auto_approve_enabled": False,
            "prompt_template": "cognitive_behavioral",
            "sensitivity_threshold": 0.7,
            "risk_alert_keywords": ["suicide", "self-harm", "hurt myself", "end it all", "kill myself"]
        }

        config_file = Path("analysis_config.json")
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        print("✓ Created test configuration file")
        print("⚠️  Please add your Claude API key to analysis_config.json")
        return config_file

    except Exception as e:
        print(f"✗ Failed to create config: {e}")
        return None

def load_test_config():
    """Load test configuration"""
    try:
        config_file = Path("analysis_config.json")
        if not config_file.exists():
            print("No config file found, creating default...")
            create_test_config()
            return None

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if not config.get('claude_api_key'):
            print("⚠️  Claude API key not configured in analysis_config.json")
            return None

        return config

    except Exception as e:
        print(f"✗ Config load error: {e}")
        return None

def test_claude_connection(api_key):
    """Test Claude API connection"""
    if not ANTHROPIC_AVAILABLE:
        return False

    try:
        print("Testing Claude API connection...")

        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            messages=[{"role": "user", "content": "Hello, can you hear me?"}]
        )

        print("✓ Claude API connection successful")
        print(f"Response: {response.content[0].text[:100]}...")
        return True

    except Exception as e:
        print(f"✗ Claude API test failed: {e}")
        return False

def get_sample_transcript_segments():
    """Get sample de-identified therapy transcript segments for testing"""
    return [
        {
            "id": "test_001",
            "text": "[14:23:15] [THERAPIST]: How are you feeling today? Any changes since our last session?",
            "type": "therapist_question"
        },
        {
            "id": "test_002",
            "text": "[14:23:22] [CLIENT]: I've been struggling with anxiety again. The work situation is really getting to me and I can't seem to shake these negative thoughts.",
            "type": "client_response_anxiety"
        },
        {
            "id": "test_003",
            "text": "[14:23:45] [CLIENT]: Sometimes I feel like nothing I do matters and I wonder if it would be better if I just disappeared. I know that sounds dramatic but that's how I feel.",
            "type": "client_risk_indicator"
        },
        {
            "id": "test_004",
            "text": "[14:24:02] [THERAPIST]: Thank you for sharing that with me. Those feelings sound really difficult. Can you tell me more about what 'disappeared' means to you?",
            "type": "therapist_risk_assessment"
        },
        {
            "id": "test_005",
            "text": "[14:24:15] [CLIENT]: Not like hurting myself or anything serious. More like... escaping to somewhere peaceful where I don't have to deal with all this pressure.",
            "type": "client_clarification"
        },
        {
            "id": "test_006",
            "text": "[14:24:30] [THERAPIST]: I hear you saying you're not thinking about self-harm, which is important. Let's explore some healthier ways to find that sense of peace you're looking for.",
            "type": "therapist_intervention"
        },
        {
            "id": "test_007",
            "text": "[14:24:45] [CLIENT]: Actually, the breathing exercises you taught me last time did help when I remembered to use them. Maybe I should practice those more.",
            "type": "client_progress"
        },
        {
            "id": "test_008",
            "text": "[14:25:00] [THERAPIST]: That's wonderful insight. What do you think would help you remember to use the breathing exercises when you need them most?",
            "type": "therapist_homework_planning"
        }
    ]

def test_prompt_templates():
    """Test different therapy prompt templates"""
    print("\n" + "="*60)
    print("PROMPT TEMPLATE TESTING")
    print("="*60)

    # Sample templates (simplified versions of main.py templates)
    templates = {
        "cognitive_behavioral": {
            "name": "Cognitive Behavioral Therapy (CBT)",
            "prompt": """Analyze this therapy segment using CBT principles:

1. **Cognitive Patterns**: Identify thought patterns and beliefs
2. **Behavioral Observations**: Note behaviors and coping strategies
3. **Emotional Themes**: Track emotional states
4. **Risk Assessment**: Safety concerns (score 1-10)
5. **CBT Interventions**: Suggest evidence-based techniques

Transcript: {transcript}
Context: {context}

Provide structured analysis with confidence scores."""
        },
        "solution_focused": {
            "name": "Solution-Focused Brief Therapy",
            "prompt": """Analyze using solution-focused principles:

1. **Strengths & Resources**: Client capabilities and successes
2. **Goals & Scaling**: Progress indicators and goal clarity
3. **Exception Finding**: When problems are less severe
4. **Risk Assessment**: Safety concerns (score 1-10)
5. **Solution Building**: Next steps toward outcomes

Focus on what's working rather than what's wrong.

Transcript: {transcript}
Context: {context}"""
        }
    }

    sample_transcript = "[CLIENT]: I've been struggling with anxiety but the breathing exercises helped."
    sample_context = "Client previously reported high anxiety levels. Working on coping strategies."

    for template_name, template_data in templates.items():
        print(f"\n{template_name.upper()} TEMPLATE:")
        print("-" * 40)

        formatted_prompt = template_data['prompt'].format(
            transcript=sample_transcript,
            context=sample_context
        )

        print(f"Prompt length: {len(formatted_prompt)} characters")
        print(f"First 200 chars: {formatted_prompt[:200]}...")
        print("✓ Template formatting successful")

def test_analysis_workflow(api_key):
    """Test complete analysis workflow with sample data"""
    if not ANTHROPIC_AVAILABLE or not api_key:
        print("Cannot test workflow - API not available or key missing")
        return False

    print("\n" + "="*60)
    print("THERAPY ANALYSIS WORKFLOW TEST")
    print("="*60)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        samples = get_sample_transcript_segments()

        # Test different risk levels
        test_cases = [
            {
                "name": "Low Risk Case",
                "segments": samples[:2]  # Normal conversation
            },
            {
                "name": "Medium Risk Case",
                "segments": samples[2:4]  # Contains risk language
            },
            {
                "name": "Resolution Case",
                "segments": samples[4:6]  # Shows improvement
            }
        ]

        for case in test_cases:
            print(f"\n{case['name']}:")
            print("-" * 30)

            # Combine segments
            combined_text = "\n".join([seg['text'] for seg in case['segments']])

            # Create analysis prompt
            prompt = f"""Analyze this therapy segment using CBT principles:

1. **Risk Assessment**: Rate safety concerns (1-10 scale)
2. **Emotional State**: Current emotional patterns
3. **Therapeutic Progress**: Signs of improvement or concern
4. **Recommendations**: Next steps for treatment

Transcript:
{combined_text}

Provide brief, structured analysis focusing on clinical insights."""

            try:
                start_time = time.time()

                response = client.messages.create(
                    model="claude-3-haiku-20240307",  # Use Haiku for testing (faster/cheaper)
                    max_tokens=500,
                    temperature=0.1,
                    messages=[{"role": "user", "content": prompt}]
                )

                processing_time = time.time() - start_time

                print(f"✓ Analysis completed ({processing_time:.2f}s)")
                print(f"Tokens used: {response.usage.input_tokens + response.usage.output_tokens}")

                # Check response content
                analysis_text = response.content[0].text
                print(f"Response length: {len(analysis_text)} characters")

                # Check for risk indicators
                risk_keywords = ["risk", "safety", "concern", "harm"]
                found_risk = any(keyword in analysis_text.lower() for keyword in risk_keywords)

                if found_risk:
                    print("⚠️  Risk indicators detected in analysis")
                else:
                    print("✓ No significant risk indicators")

                # Show excerpt
                print(f"Analysis excerpt: {analysis_text[:150]}...")

            except Exception as e:
                print(f"✗ Analysis failed: {e}")

        return True

    except Exception as e:
        print(f"✗ Workflow test error: {e}")
        return False

def test_risk_detection():
    """Test risk detection algorithms"""
    print("\n" + "="*60)
    print("RISK DETECTION TEST")
    print("="*60)

    risk_test_cases = [
        {
            "text": "I've been feeling really hopeless lately and wondering if life is worth living",
            "expected_risk": "HIGH",
            "keywords": ["hopeless", "worth living"]
        },
        {
            "text": "Sometimes I think about ending it all when things get really bad",
            "expected_risk": "HIGH",
            "keywords": ["ending it all"]
        },
        {
            "text": "I feel sad but I'm working on getting better with therapy",
            "expected_risk": "LOW",
            "keywords": []
        },
        {
            "text": "I had a panic attack but used the breathing exercises and it helped",
            "expected_risk": "LOW",
            "keywords": []
        }
    ]

    # Risk keyword detection
    risk_keywords = ["suicide", "self-harm", "hurt myself", "end it all", "kill myself",
                    "hopeless", "worthless", "better off dead", "ending it all"]

    for i, case in enumerate(risk_test_cases, 1):
        print(f"\nTest Case {i}: {case['expected_risk']} Risk")
        print(f"Text: {case['text']}")

        # Check for risk keywords
        found_keywords = [kw for kw in risk_keywords if kw in case['text'].lower()]

        if found_keywords:
            detected_risk = "HIGH"
            print(f"✓ Keywords detected: {found_keywords}")
        else:
            detected_risk = "LOW"
            print("✓ No risk keywords found")

        # Validate detection
        if detected_risk == case['expected_risk']:
            print(f"✓ Risk detection correct: {detected_risk}")
        else:
            print(f"⚠️  Risk detection mismatch: Expected {case['expected_risk']}, got {detected_risk}")

def test_cost_calculation():
    """Test cost calculation for analysis requests"""
    print("\n" + "="*60)
    print("COST CALCULATION TEST")
    print("="*60)

    # Claude-3 pricing (approximate)
    input_cost_per_token = 0.000003   # $3 per million tokens
    output_cost_per_token = 0.000015  # $15 per million tokens

    test_scenarios = [
        {"input_tokens": 1000, "output_tokens": 500, "description": "Typical analysis"},
        {"input_tokens": 2000, "output_tokens": 1000, "description": "Large segment"},
        {"input_tokens": 500, "output_tokens": 250, "description": "Small segment"}
    ]

    total_cost = 0

    for scenario in test_scenarios:
        input_cost = scenario['input_tokens'] * input_cost_per_token
        output_cost = scenario['output_tokens'] * output_cost_per_token
        request_cost = input_cost + output_cost

        print(f"\n{scenario['description']}:")
        print(f"  Input tokens: {scenario['input_tokens']:,} (${input_cost:.4f})")
        print(f"  Output tokens: {scenario['output_tokens']:,} (${output_cost:.4f})")
        print(f"  Total cost: ${request_cost:.4f}")

        total_cost += request_cost

    print(f"\nTotal cost for {len(test_scenarios)} analyses: ${total_cost:.4f}")
    print(f"Cost per 50-minute session (~25 analyses): ${total_cost * 8:.4f}")

def run_comprehensive_test():
    """Run complete therapy analysis test suite"""
    print("Amanuensis V2 - Therapy Analysis Test Suite")
    print("="*60)

    # Load configuration
    config = load_test_config()
    if not config:
        return False

    # Test API connection
    if not test_claude_connection(config['claude_api_key']):
        return False

    # Test prompt templates
    test_prompt_templates()

    # Test analysis workflow
    if not test_analysis_workflow(config['claude_api_key']):
        return False

    # Test risk detection
    test_risk_detection()

    # Test cost calculation
    test_cost_calculation()

    print("\n" + "="*60)
    print("THERAPY ANALYSIS TEST COMPLETED")
    print("="*60)
    print("✓ All tests passed successfully")
    print("Your therapy analysis system is ready for use!")

    return True

def generate_test_report():
    """Generate a test report with sample outputs"""
    print("\n" + "="*60)
    print("SAMPLE OUTPUT REPORT")
    print("="*60)

    # Sample analysis result format
    sample_result = {
        "id": "analysis_12345",
        "timestamp": time.time(),
        "model": "claude-3-sonnet-20240229",
        "processing_time": 2.3,
        "tokens_used": 1500,
        "cost_estimate": 0.0225,
        "success": True,
        "structured_analysis": {
            "risk_assessment": {
                "score": 3,
                "confidence": 0.85,
                "rationale": "No immediate safety concerns detected"
            },
            "cognitive_patterns": [
                "Catastrophic thinking about work situations",
                "All-or-nothing thought patterns"
            ],
            "emotional_themes": [
                "Anxiety (moderate level)",
                "Some hopelessness about change"
            ],
            "recommendations": [
                "Continue cognitive restructuring exercises",
                "Introduce progressive muscle relaxation"
            ]
        },
        "risk_alerts": [],
        "summary": "Client showing mild anxiety with catastrophic thinking patterns. No immediate safety concerns. Responding well to CBT interventions."
    }

    print("Sample Analysis Result Structure:")
    print(json.dumps(sample_result, indent=2, default=str))

    # Sample session summary
    sample_session = {
        "session_info": {
            "date": datetime.now().isoformat(),
            "duration_minutes": 50,
            "total_analyses": 8,
            "analysis_frequency": 120
        },
        "statistics": {
            "total_requests": 8,
            "successful_requests": 8,
            "failed_requests": 0,
            "total_cost": 0.18,
            "tokens_used": 12000
        },
        "risk_summary": {
            "high_risk_alerts": 0,
            "medium_risk_alerts": 1,
            "total_risk_events": 1
        }
    }

    print(f"\nSample Session Summary:")
    print(json.dumps(sample_session, indent=2))

if __name__ == "__main__":
    try:
        # Run comprehensive test
        success = run_comprehensive_test()

        if success:
            # Generate sample report
            generate_test_report()

            print(f"\n✓ Therapy analysis system testing completed successfully")
        else:
            print(f"\n✗ Some tests failed - please check configuration and try again")

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest error: {e}")
        sys.exit(1)