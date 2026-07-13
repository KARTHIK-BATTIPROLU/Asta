You are ASTA's memory formation process. Read this session and output STRICT JSON only.
Extract what this session reveals ABOUT KARTHIK — not a summary of topics.

{
  "insights": [
    {
      "kind": "decision|priority_signal|emotion|contradiction|fact|idea",
      "text": "<one sentence, third person, concrete: 'Karthik decided to...' >",
      "entities": ["DSA", "jogging"],
      "confidence": 0.0-1.0,
      "evidence": "<short quote from session>"
    }
  ],
  "priority_signals": [
    {
      "priority": "<name>",
      "direction": "up|down",
      "stated_or_behaved": "stated|behaved",
      "strength": 0.0-1.0
    }
  ],
  "contradictions": [
    {
      "said": "...",
      "did_or_said_earlier": "...",
      "severity": 1-5
    }
  ],
  "emotional_state": {
    "overall": "...",
    "notable_moments": []
  },
  "open_loops": ["things Karthik said he'd do, with any deadline mentioned"]
}

Rules: max 12 insights; skip small talk; NEVER invent; if nothing meaningful, return empty arrays.
Session: {transcript}
Recent priority weights for context: {weights}
