from litellm import completion

response = completion(
    model="ollama/llama3.2",
    messages=[
        {
            "role": "user",
            "content": "Réponds uniquement : Ollama fonctionne avec Python."
        }
    ],
    api_base="http://localhost:11434"
)

print(response["choices"][0]["message"]["content"])