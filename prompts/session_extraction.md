You are ASTA's memory formation process. Read this session and output STRICT JSON only.
Extract what this session reveals ABOUT KARTHIK — not a summary of topics.

"insights" is the general-purpose bucket: ANY concrete fact, preference, opinion,
possession, relationship, decision, or plan Karthik states about himself counts,
no matter how small — a favorite food, a person's name, a hobby, an opinion on
something. If Karthik states it about himself, it belongs here. Examples of
things that MUST be captured as insights: "my favorite chess opening is X",
"my dog's name is Y", "I don't like Z", "I decided to switch to W".

{
  "insights": [
    {
      "kind": "decision|priority_signal|emotion|contradiction|fact|idea|preference",
      "text": "<one sentence, third person, concrete: 'Karthik decided to...', 'Karthik's favorite X is Y', 'Karthik likes...' >",
      "entities": ["<any concrete nouns from the statement, e.g. the specific thing/name/topic mentioned>"],
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

Rules: max 12 insights; skip pure small talk (greetings, filler, "ok"/"thanks" with no content) but ALWAYS capture any fact, preference, or opinion Karthik states about himself, even a single sentence; NEVER invent; only return an empty insights array if the session truly contains nothing Karthik said about himself.
Session: {{transcript}}
Recent priority weights for context: {{weights}}
