import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from backend.app.services.memory.recall import recall

logger = logging.getLogger("MemoryInjector")

@dataclass
class SystemPromptUpdateFrame(Frame):
    """Custom frame to update the system prompt in the RouterLLMService."""
    system_prompt: str

class MemoryContextInjector(FrameProcessor):
    """
    Intercepts the user's turn (TranscriptionFrame), runs semantic & graph recall
    in the background, and injects the context block as a SystemPromptUpdateFrame
    before passing the TranscriptionFrame downstream.
    """
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.UPSTREAM and isinstance(frame, TranscriptionFrame):
            query = frame.text
            
            # Fetch relevant context
            try:
                memories = await recall(query, k=6)
                
                # We could also fetch priorities, goals, open loops from the db here
                # For Phase 1 / Phase 3 baseline, we stick to the memories
                
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                # Build the memory context string
                context_lines = [f"## WHAT I KNOW ABOUT KARTHIK RIGHT NOW (auto-generated, {date_str})"]
                
                if memories:
                    context_lines.append("Relevant memories for this turn:")
                    for m in memories:
                        text = m.get('text', '')
                        if text:
                            context_lines.append(f"- {text}")
                else:
                    context_lines.append("No specific memories surfaced for this context.")
                    
                context_block = "\n".join(context_lines)
                
                # Fetch the full system prompt (persona + time/mood + memory + rules)
                from backend.app.services.llm_service import get_system_prompt
                full_system_prompt = get_system_prompt(health_status="full", memory_context=context_block)
                
                # Push the update frame first
                await self.push_frame(SystemPromptUpdateFrame(system_prompt=full_system_prompt), direction)
                
                logger.info("[MemoryInjector] Successfully injected full system prompt.")
                
            except Exception as e:
                logger.error(f"[MemoryInjector] Failed to inject memory context: {e}")
                
            # Then push the original transcription downstream
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)
