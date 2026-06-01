"""
Intent Detection Service for ASTA
Routes user messages to appropriate handlers: casual, tool, memory, or general
"""
import logging
import re
from typing import Dict, Optional, List

logger = logging.getLogger("IntentDetector")


class IntentDetector:
    """
    Detects user intent and determines routing strategy.
    
    Intent Types:
    - casual: greetings, small talk → NO RAG, NO TOOLS, natural response
    - tool: explicit tool requests → NO RAG, FORCE tool call
    - memory: queries about past → USE RAG, NO TOOLS
    - general: everything else → LIGHT RAG, natural response
    """
    
    # Casual conversation patterns
    CASUAL_PATTERNS = [
        r'\b(hey|hi|hello|sup|yo|hiya|howdy)\b',
        r'\b(what\'?s up|wassup|how are you|how\'?s it going)\b',
        r'\b(good morning|good afternoon|good evening|good night)\b',
        r'\b(thanks|thank you|thx|ty)\b',
        r'\b(bye|goodbye|see ya|later|cya)\b',
        r'\b(ok|okay|cool|nice|great|awesome|perfect)\b',
        r'\b(lol|haha|lmao|rofl)\b',
        r'\b(nothing|ntg|nm|not much|nah|nope)\b',
        r'\b(just casual|just chatting|just talking)\b',
        r'\b(fun|boring|tired|busy)\b',
    ]
    
    # Tool intent patterns
    TOOL_PATTERNS = {
        "study_planner": [
            r'\b(study|studying|exam|mark.*done|done (for|with) (today|studying))\b',
            r'\b(plan my (day|study|exams?|routine))\b',
            r'\b(what am i studying|study plan|study routine|study schedule)\b',
        ],
        "weather": [
            r'\b(weather|temperature|forecast|rain|snow|sunny|cloudy|cold|hot|humid)\b',
            r'\b(should i (jog|run|walk|exercise))\b',
            r'\b(what\'?s the weather|how\'?s the weather)\b',
        ],
        "search": [
            r'\b(search|google|find|look up|lookup)\b',
            r'\b(what is|who is|where is|when is|why is|how is)\b',
            r'\b(tell me about|information about|info on)\b',
            r'\b(latest news on|news about)\b',
        ],
        "news": [
            r'\b(news|headlines|breaking news|current events)\b',
            r'\b(what\'?s happening|what\'?s going on)\b',
        ],
        # Calendar tool removed - using Notion for task/schedule management
        "notion": [
            r'\b(notion|note|write down|save (this|to notion))\b',
            r'\b(create (a )?page|add to notion)\b',
            r'\b(read (my )?notion|check notion)\b',
            r'\b(task|tasks|todo|to-do|schedule|meeting|appointment)\b',
            r'\b(add (a )?task|create (a )?task|new task)\b',
            r'\b(what\'?s on my (schedule|calendar|agenda))\b',
            r'\b(my (tasks|schedule|routine|agenda))\b',
        ],
        "image": [
            r'\b(generate (an? )?image|create (an? )?image|make (an? )?image)\b',
            r'\b(draw|picture|photo|illustration)\b',
            r'\b(show me (a |an )?image of)\b',
        ],
    }
    
    # Memory query patterns
    MEMORY_PATTERNS = [
        r'\b(remember|recall|you (said|told|mentioned))\b',
        r'\b(we (discussed|talked about|spoke about))\b',
        r'\b(last time|previously|before|earlier)\b',
        r'\b(what did (i|we)|did (i|we) (say|talk|discuss))\b',
        r'\b(my (projects|skills|work|tasks))\b',
        r'\b(do you know (about|my))\b',
    ]
    
    def __init__(self):
        # Compile patterns for performance
        self.casual_regex = [re.compile(p, re.IGNORECASE) for p in self.CASUAL_PATTERNS]
        self.tool_regex = {
            tool: [re.compile(p, re.IGNORECASE) for p in patterns]
            for tool, patterns in self.TOOL_PATTERNS.items()
        }
        self.memory_regex = [re.compile(p, re.IGNORECASE) for p in self.MEMORY_PATTERNS]
    
    def detect(self, user_message: str) -> Dict:
        """
        Detect intent from user message.
        
        Returns:
            {
                "type": "casual" | "tool" | "memory" | "general",
                "use_rag": bool,
                "force_tool": str | None,
                "confidence": float,
                "reasoning": str
            }
        """
        msg_lower = user_message.lower().strip()
        msg_len = len(user_message.split())
        
        # Empty or very short messages
        if not msg_lower or msg_len == 0:
            return self._build_result("casual", False, None, 1.0, "Empty message")
        
        # 1. Check for casual conversation (high priority for short messages)
        if msg_len <= 5:  # Short messages are likely casual
            for pattern in self.casual_regex:
                if pattern.search(msg_lower):
                    return self._build_result(
                        "casual", False, None, 0.95,
                        f"Casual greeting/response detected: '{user_message[:30]}'"
                    )
        
        # 2. Check for explicit tool requests (highest priority)
        for tool_name, patterns in self.tool_regex.items():
            for pattern in patterns:
                if pattern.search(msg_lower):
                    # Special handling for ambiguous "what is" queries
                    if tool_name == "search" and msg_len <= 3:
                        # "what is" alone is too vague, might be casual
                        continue
                    
                    return self._build_result(
                        "tool", False, tool_name, 0.9,
                        f"Tool intent detected: {tool_name}"
                    )
        
        # 3. Check for memory queries
        for pattern in self.memory_regex:
            if pattern.search(msg_lower):
                return self._build_result(
                    "memory", True, None, 0.85,
                    "Memory query detected"
                )
        
        # 4. Check for questions that might need tools
        question_words = ["what", "who", "where", "when", "why", "how", "which"]
        if any(msg_lower.startswith(word) for word in question_words):
            # Questions about specific topics might need search
            if msg_len > 4:  # Longer questions likely need tools
                return self._build_result(
                    "tool", False, "search", 0.7,
                    "Question detected, might need search"
                )
        
        # 5. Default to general conversation with light RAG
        # Use RAG only if message is substantial (>5 words)
        use_rag = msg_len > 5
        return self._build_result(
            "general", use_rag, None, 0.6,
            f"General conversation (len={msg_len}, rag={use_rag})"
        )
    
    def _build_result(
        self,
        intent_type: str,
        use_rag: bool,
        force_tool: Optional[str],
        confidence: float,
        reasoning: str
    ) -> Dict:
        """Build standardized intent result"""
        return {
            "type": intent_type,
            "use_rag": use_rag,
            "force_tool": force_tool,
            "confidence": confidence,
            "reasoning": reasoning
        }
    
    def should_skip_rag(self, intent: Dict) -> bool:
        """Helper to determine if RAG should be skipped"""
        return not intent.get("use_rag", False)
    
    def get_forced_tool(self, intent: Dict) -> Optional[str]:
        """Helper to get forced tool name"""
        return intent.get("force_tool")


# Global instance
intent_detector = IntentDetector()
