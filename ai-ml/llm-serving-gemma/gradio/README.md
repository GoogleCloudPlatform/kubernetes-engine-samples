# Gradio implementation for testing LLM serving engines

This example [Gradio](https://www.gradio.app) implementation demonstrates chat functionality with LLM models.
[Google Kubernetes Engine](https://cloud.google.com/kubernetes-engine).

## Requirements
The implementation expects a few environment variables to be set to function properly.

Below are some examples values:
    
```
    - name: CONTEXT_PATH
      value: "/generate"
    - name: HOST
      value: "http://llm-service:8000"
    - name: LLM_ENGINE
      value: "vllm" # tgi | openai-chat
    - name: MODEL_ID
      value: "gemma"
    - name: USER_PROMPT
      value: "<start_of_turn>user\nprompt<end_of_turn>\n"
    - name: SYSTEM_PROMPT
      value: "<start_of_turn>model\nprompt<end_of_turn>\n"
```