import sys
import os

# Ensure hermes_agent is in the Python path
sys.path.insert(0, os.path.abspath('hermes_agent'))

from hermes_agent.run_agent import AIAgent
from hermes_agent.hermes_cli.config import load_config_readonly

def test_gate6():
    print("Initializing AIAgent for Gate 6...")
    
    # Read provider and model from config.yaml, not hardcoded strings
    cfg = load_config_readonly()
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, dict):
        model_str = model_cfg.get("default", "")
        provider_str = model_cfg.get("provider", "")
    else:
        model_str = model_cfg
        provider_str = ""
        
    print(f"Loaded config -> model: {model_str}, provider: {provider_str}")
        
    keys = [
        os.environ.get("GROQ_API_KEY", ""),
        "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"
    ]
    
    prompt = "Create a python skill to calculate the 100th fibonacci number, save it as a skill and use it."
    
    for key in keys:
        if not key:
            continue
            
        print(f"Attempting chat loop with API key starting with: {key[:8]}...")
        os.environ["GROQ_API_KEY"] = key
        
        # Enable ONLY essential toolsets to keep token count extremely low for Groq Free Tier
        agent = AIAgent(
            session_id='test_g6', 
            model=model_str, 
            provider=provider_str,
            max_tokens=256,
            enabled_toolsets=["core", "skills", "terminal"]
        )
        response = agent.chat(prompt)
        
        if "Request payload too large" not in response and "Cannot compress further" not in response:
            print("\n\n--- Assistant Response ---")
            print(response)
            break
        else:
            print(f"Key {key[:8]} hit a rate/TPM limit, falling back...")

if __name__ == "__main__":
    test_gate6()
