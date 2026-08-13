with open(r'C:\Python311\Lib\site-packages\graphiti_core\llm_client\groq_client.py', 'r') as f:
    content = f.read()

content = content.replace(
    "result = response.choices[0].message.content or ''\n            return json.loads(result)",
    "result = response.choices[0].message.content or ''\n            print(f'\\n[GroqClient] Prompt tokens: {response.usage.prompt_tokens}, Completion tokens: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}')\n            return json.loads(result)"
)

with open(r'C:\Python311\Lib\site-packages\graphiti_core\llm_client\groq_client.py', 'w') as f:
    f.write(content)
