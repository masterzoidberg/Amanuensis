import openai
import anthropic
import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple

class APIManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.openai_client = None
        self.anthropic_client = None

    def initialize_clients(self):
        """Initialize API clients with keys from config manager"""
        try:
            # Initialize OpenAI client
            openai_key = self.config_manager.get_api_key('openai')
            if openai_key:
                self.openai_client = openai.OpenAI(api_key=openai_key)

            # Initialize Anthropic client
            anthropic_key = self.config_manager.get_api_key('anthropic')
            if anthropic_key:
                self.anthropic_client = anthropic.Anthropic(api_key=anthropic_key)

            return True, "API clients initialized successfully"

        except Exception as e:
            return False, f"Failed to initialize API clients: {str(e)}"

    def transcribe_audio_files(self, therapist_file: str, client_file: str) -> Tuple[bool, Dict]:
        """
        Transcribe both audio files using Whisper API with speaker separation
        """
        if not self.openai_client:
            return False, {"error": "OpenAI client not initialized"}

        try:
            transcripts = {}

            # Transcribe therapist audio (Channel 1)
            with open(therapist_file, "rb") as audio_file:
                therapist_transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            # Tag all segments as THERAPIST
            therapist_segments = []
            if hasattr(therapist_transcript, 'segments'):
                for segment in therapist_transcript.segments:
                    therapist_segments.append({
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': segment['text'],
                        'speaker': 'THERAPIST'
                    })

            transcripts['therapist'] = {
                'text': therapist_transcript.text,
                'segments': therapist_segments
            }

            # Transcribe client audio (Channel 2)
            with open(client_file, "rb") as audio_file:
                client_transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            # Tag segments as CLIENT (or apply speaker diarization)
            client_segments = []
            if hasattr(client_transcript, 'segments'):
                for segment in client_transcript.segments:
                    # Simple speaker assignment - in production, use speaker diarization
                    client_segments.append({
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': segment['text'],
                        'speaker': 'CLIENT'  # Could be CLIENT_1, CLIENT_2, etc.
                    })

            transcripts['client'] = {
                'text': client_transcript.text,
                'segments': client_segments
            }

            return True, transcripts

        except Exception as e:
            return False, {"error": f"Transcription failed: {str(e)}"}
        finally:
            # Clean up API key from memory
            try:
                if hasattr(self.openai_client, 'api_key'):
                    self.openai_client.api_key = None
            except:
                pass

    def merge_and_sort_transcripts(self, transcripts: Dict) -> List[Dict]:
        """Merge transcripts from both channels and sort by timestamp"""
        all_segments = []

        # Add therapist segments
        for segment in transcripts.get('therapist', {}).get('segments', []):
            all_segments.append(segment)

        # Add client segments
        for segment in transcripts.get('client', {}).get('segments', []):
            all_segments.append(segment)

        # Sort by start time
        all_segments.sort(key=lambda x: x['start'])

        return all_segments

    def format_transcript_for_analysis(self, segments: List[Dict]) -> str:
        """Format transcript segments for Claude analysis"""
        formatted_lines = []

        for segment in segments:
            speaker_tag = f"[{segment['speaker']}]"
            text = segment['text'].strip()
            if text:
                formatted_lines.append(f"{speaker_tag}: {text}")

        return "\n".join(formatted_lines)

    def analyze_therapy_session(self, transcript: str, session_context: Dict = None) -> Tuple[bool, Dict]:
        """
        Analyze therapy session transcript using Claude API
        """
        if not self.anthropic_client:
            return False, {"error": "Anthropic client not initialized"}

        try:
            # Build analysis prompt
            prompt = self._build_therapy_analysis_prompt(transcript, session_context)

            # Call Claude API
            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse Claude's response
            analysis_text = message.content[0].text
            analysis = self._parse_analysis_response(analysis_text)

            return True, analysis

        except Exception as e:
            return False, {"error": f"Analysis failed: {str(e)}"}
        finally:
            # Clean up API key from memory
            try:
                if hasattr(self.anthropic_client, 'api_key'):
                    self.anthropic_client.api_key = None
            except:
                pass

    def _build_therapy_analysis_prompt(self, transcript: str, context: Dict = None) -> str:
        """Build the analysis prompt for Claude"""
        base_prompt = """
Analyze this therapy session excerpt with speaker labels. Provide insights in the following format:

**KEY THEMES PER SPEAKER:**
- THERAPIST: [therapeutic approaches, interventions used]
- CLIENT/CLIENT_1/CLIENT_2: [emotional themes, concerns expressed]

**RELATIONSHIP DYNAMICS:**
[Patterns between speakers, communication styles, therapeutic rapport]

**FOLLOW-UP QUESTIONS:**
[3-5 specific questions the therapist might explore in future sessions]

**THERAPEUTIC OPPORTUNITIES:**
[Areas for intervention, techniques to consider, progress observations]

**SESSION NOTES:**
[Brief summary of session progress and key moments]

Keep recommendations brief and actionable for the therapist.

THERAPY SESSION TRANSCRIPT:
"""

        context_info = ""
        if context:
            client_count = context.get('client_count', 1)
            session_type = context.get('session_type', 'individual')
            context_info = f"\nSESSION CONTEXT: {session_type} therapy with {client_count} client(s)\n"

        return base_prompt + context_info + "\n" + transcript

    def _parse_analysis_response(self, response_text: str) -> Dict:
        """Parse Claude's analysis response into structured data"""
        try:
            # Simple parsing - look for sections marked with **
            sections = {
                'themes': '',
                'dynamics': '',
                'follow_up_questions': '',
                'opportunities': '',
                'session_notes': '',
                'raw_response': response_text
            }

            lines = response_text.split('\n')
            current_section = None

            for line in lines:
                line = line.strip()
                if line.startswith('**KEY THEMES'):
                    current_section = 'themes'
                elif line.startswith('**RELATIONSHIP DYNAMICS'):
                    current_section = 'dynamics'
                elif line.startswith('**FOLLOW-UP QUESTIONS'):
                    current_section = 'follow_up_questions'
                elif line.startswith('**THERAPEUTIC OPPORTUNITIES'):
                    current_section = 'opportunities'
                elif line.startswith('**SESSION NOTES'):
                    current_section = 'session_notes'
                elif current_section and line and not line.startswith('**'):
                    sections[current_section] += line + '\n'

            return sections

        except Exception as e:
            return {
                'error': f"Failed to parse analysis: {str(e)}",
                'raw_response': response_text
            }

    def get_speaker_specific_insights(self, transcript: str, speaker_name: str) -> Tuple[bool, str]:
        """Get insights specific to a particular speaker"""
        if not self.anthropic_client:
            return False, "Anthropic client not initialized"

        try:
            prompt = f"""
Analyze the following therapy session transcript and provide specific insights about {speaker_name}:

1. **Emotional State**: What emotions is {speaker_name} expressing?
2. **Communication Patterns**: How does {speaker_name} communicate?
3. **Key Concerns**: What are {speaker_name}'s main issues or topics?
4. **Therapeutic Engagement**: How is {speaker_name} responding to therapy?
5. **Recommendations**: Specific approaches that might help {speaker_name}

Keep the analysis focused and actionable.

TRANSCRIPT:
{transcript}
"""

            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            return True, message.content[0].text

        except Exception as e:
            return False, f"Speaker analysis failed: {str(e)}"

    def validate_api_connections(self) -> Dict:
        """Test API connections and return status"""
        results = {
            'openai': {'connected': False, 'error': None},
            'anthropic': {'connected': False, 'error': None}
        }

        # Test OpenAI
        try:
            if self.openai_client:
                # Simple test call
                models = self.openai_client.models.list()
                results['openai']['connected'] = True
        except Exception as e:
            results['openai']['error'] = str(e)

        # Test Anthropic
        try:
            if self.anthropic_client:
                # Simple test message
                test_message = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hello"}]
                )
                results['anthropic']['connected'] = True
        except Exception as e:
            results['anthropic']['error'] = str(e)

        return results

    def cleanup(self):
        """Clean up API clients and clear sensitive data from memory"""
        try:
            if self.openai_client:
                if hasattr(self.openai_client, 'api_key'):
                    self.openai_client.api_key = None
                self.openai_client = None

            if self.anthropic_client:
                if hasattr(self.anthropic_client, 'api_key'):
                    self.anthropic_client.api_key = None
                self.anthropic_client = None

        except Exception as e:
            print(f"Cleanup warning: {e}")

    def estimate_api_costs(self, audio_duration_minutes: float, transcript_length: int) -> Dict:
        """Estimate API costs for the session"""
        # Approximate costs (as of 2024 - adjust as needed)
        whisper_cost_per_minute = 0.006  # $0.006 per minute
        claude_cost_per_1k_tokens = 0.015  # Approximate for Claude 3.5 Sonnet

        # Estimate transcript tokens (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = transcript_length / 4

        costs = {
            'whisper_transcription': audio_duration_minutes * whisper_cost_per_minute * 2,  # Two channels
            'claude_analysis': (estimated_tokens / 1000) * claude_cost_per_1k_tokens,
            'total_estimated': 0
        }

        costs['total_estimated'] = costs['whisper_transcription'] + costs['claude_analysis']

        return costs