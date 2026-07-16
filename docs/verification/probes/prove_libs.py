import sys
import asyncio

def prove_pipecat():
    try:
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        vad = SileroVADAnalyzer()
        print("[OK] Pipecat SileroVADAnalyzer instantiated.")
    except Exception as e:
        print(f"[FAIL] Pipecat: {e}")
        sys.exit(1)

def prove_graphiti():
    try:
        from graphiti_core import Graphiti
        from graphiti_core.llm_client.openai_client import OpenAIClient
        import os
        
        # We just need to instantiate the client. 
        # Using a mock/placeholder API key just for instantiation proof.
        os.environ['OPENAI_API_KEY'] = 'mock-key-for-instantiation'
        
        client = OpenAIClient()
        graphiti = Graphiti("neo4j://localhost:7687", "neo4j", "password", llm_client=client)
        print("[OK] Graphiti instantiated.")
    except Exception as e:
        print(f"[FAIL] Graphiti: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("--- Proving Core Libs ---")
    prove_pipecat()
    prove_graphiti()
    print("--- Success ---")
