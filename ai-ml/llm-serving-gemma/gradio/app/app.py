# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import requests
import gradio as gr
import os

if "MODEL_ID" in os.environ:
    model_id = os.environ["MODEL_ID"]
else:
    model_id = "gradio"

disable_system_message = False
if "DISABLE_SYSTEM_MESSAGE" in os.environ:
    disable_system_message = os.environ["DISABLE_SYSTEM_MESSAGE"]


def inference_interface(message, history, model_temperature, top_p, max_tokens):

    json_message = {}

    # Need to determine the engine to determine input/output formats
    if "LLM_ENGINE" in os.environ:
        llm_engine = os.environ["LLM_ENGINE"]
    else:
        llm_engine = "openai-chat"

    match llm_engine:
        case "max":
            json_message.update({"temperature": model_temperature})
            json_message.update({"top_p": top_p})
            json_message.update({"max_tokens": max_tokens})
            final_message = process_message(message, history)

            json_message.update({"prompt": final_message})
            json_data = post_request(json_message)

            temp_output = json_data["response"]
            output = temp_output
        case "vllm":
            json_message.update({"temperature": model_temperature})
            json_message.update({"top_p": top_p})
            json_message.update({"max_tokens": max_tokens})
            final_message = process_message(message, history)

            json_message.update({"prompt": final_message})
            json_data = post_request(json_message)

            temp_output = json_data["predictions"][0]
            output = temp_output.split("Output:\n", 1)[1]
        case "tgi":
            json_message.update({"parameters": {}})
            json_message["parameters"].update({"temperature": model_temperature})
            json_message["parameters"].update({"top_p": top_p})
            json_message["parameters"].update({"max_new_tokens": max_tokens})
            final_message = process_message(message, history)

            json_message.update({"inputs": final_message})
            json_data = post_request(json_message)

            temp_output = json_data["generated_text"]
            output = temp_output
        case _:
            print("* History: " + str(history))
            json_message.update({"model": model_id})
            json_message.update({"messages": []})
            # originally this was defaulted, so user would have to manually set this value to disable the prompt
            if not disable_system_message:
                system_message = {
                    "role": "system",
                    "content": "You are a helpful assistant.",
                }
                json_message["messages"].append(system_message)

            json_message["temperature"] = model_temperature

            if len(history) > 0:
                # we have history
                print(
                    "** Before adding additional messages: "
                    + str(json_message["messages"])
                )
                for item in history:
                    user_message = {"role": "user", "content": item[0]}
                    assistant_message = {"role": "assistant", "content": item[1]}
                    json_message["messages"].append(user_message)
                    json_message["messages"].append(assistant_message)

            new_user_message = {"role": "user", "content": message}
            json_message["messages"].append(new_user_message)

            json_data = post_request(json_message)
            output = json_data["choices"][0]["message"]["content"]

    return output


def process_message(message, history):
    user_prompt_format = ""
    system_prompt_format = ""

    # if env prompts are set, use those
    if "USER_PROMPT" in os.environ:
        user_prompt_format = os.environ["USER_PROMPT"]

    if "SYSTEM_PROMPT" in os.environ:
        system_prompt_format = os.environ["SYSTEM_PROMPT"]

    print("* History: " + str(history))

    user_message = ""
    system_message = ""
    history_message = ""

    if len(history) > 0:
        # we have history
        for item in history:
            user_message = user_prompt_format.replace("prompt", item[0])
            system_message = system_prompt_format.replace("prompt", item[1])
            history_message = history_message + user_message + system_message

    new_user_message = user_prompt_format.replace("prompt", message)

    # append the history with the new message and close with the turn
    aggregated_message = history_message + new_user_message
    return aggregated_message


def post_request(json_message):
    print("*** Request" + str(json_message), flush=True)
    response = requests.post(
        os.environ["HOST"] + os.environ["CONTEXT_PATH"], json=json_message
    )
    json_data = response.json()
    print("*** Output: " + str(json_data), flush=True)
    return json_data


with gr.Blocks(fill_height=True) as app:
    html_text = "You are chatting with: " + model_id
    gr.HTML(value=html_text)

    model_temperature = gr.Slider(
        minimum=0.1, maximum=1.0, value=0.9, label="Temperature", render=False
    )
    top_p = gr.Slider(minimum=0.1, maximum=1.0, value=0.95, label="Top_p", render=False)
    max_tokens = gr.Slider(
        minimum=1, maximum=4096, value=256, label="Max Tokens", render=False
    )

    gr.ChatInterface(
        inference_interface, additional_inputs=[model_temperature, top_p, max_tokens]
    )

app.launch(server_name="0.0.0.0")
