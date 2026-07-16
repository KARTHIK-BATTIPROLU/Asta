import logging
import random
from typing import Optional
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import Frame, TranscriptionFrame, TextFrame, TTSSpeakFrame

logger = logging.getLogger("Reflex")

SLOW_THRESHOLD = 0.7

def estimate_cost(text: str) -> float:
    """Heuristic cost estimator for ASTA."""
    text = text.lower()
    cost = 0.0
    slow_verbs = ["remember", "find", "research", "build", "search", "analyze", "summarize"]
    
    if len(text.split()) > 10:
        cost += 0.3
        
    for verb in slow_verbs:
        if verb in text:
            cost += 0.5
            break
            
    if "yesterday" in text or "last week" in text:
        cost += 0.3
        
    return cost

class FillerPool:
    def __init__(self):
        # In production this loads from a pre-synthesized nightly cache of 50 phrases
        self.families = {
            "digging": ["Let me dig that up for you.", "Searching my memory banks.", "Hold on, looking through the archives."],
            "researching": ["I'll look into that right away.", "Scanning the web for you.", "Give me a second to research that."],
            "thinking": ["Hmm, let me think.", "Interesting. Just a moment.", "Processing that now."],
            "default": ["Got it. One second.", "On it.", "Sure thing, boss."]
        }
        self.last_used_family = None

    def pick(self, topic: str) -> str:
        topic_lower = topic.lower()
        if "remember" in topic_lower or "find" in topic_lower:
            family = "digging"
        elif "research" in topic_lower or "search" in topic_lower:
            family = "researching"
        else:
            family = "thinking"
            
        # Avoid same family twice if possible
        if family == self.last_used_family:
            family = "default"
            
        self.last_used_family = family
        return random.choice(self.families[family])

filler_pool = FillerPool()

class ReflexProcessor(FrameProcessor):
    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            cost = estimate_cost(frame.text)
            if cost >= SLOW_THRESHOLD:
                filler = filler_pool.pick(topic=frame.text)
                logger.info(f"Reflex fired: estimated cost {cost} >= {SLOW_THRESHOLD}. Filler: '{filler}'")
                await self.push_frame(TTSSpeakFrame(filler), direction)
                
        await self.push_frame(frame, direction)
