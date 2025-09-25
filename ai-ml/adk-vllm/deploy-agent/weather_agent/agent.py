# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Full example code for the basic weather agent
# --- Full example code demonstrating LlmAgent with Tools ---
import os

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from litellm.rerank_api.main import httpx
from pydantic import BaseModel, Field

# --- 1. Define Schemas ---

# Input schema used by both agents
class CityInput(BaseModel):
    city: str = Field(description="The city to get information about.")

# --- 2. Define the Tool (Only for the first agent) ---
def get_weather(city: str) -> str:
    """Retrieves the weather condition of a given city."""
    print(f"\n-- Tool Call: get_weather(city='{city}') --")
    city_weather = {
        "paris": "The weather in Paris is sunny with a temperature of 25 degrees Celsius (77 degrees Fahrenheit).",
        "ottawa": "In Ottawa, it's currently cloudy with a temperature of 18 degrees Celsius (64 degrees Fahrenheit) and a chance of rain.",
        "tokyo": "Tokyo sees humid conditions with a high of 28 degrees Celsius (82 degrees Fahrenheit) and possible rainfall."
    }
    result = city_weather.get(city.strip().lower(), f"Sorry, I don't have weather information in {city}.")
    print(f"-- Tool Result: '{result}' --")
    return result

# --- 3. Configure Agent ---
# Connect to the deployed model by using LiteLlm
api_base_url = os.getenv("LLM_BASE_URL", "http://vllm-llama3-service:8000/v1")
model_name_at_endpoint = os.getenv("MODEL_NAME", "hosted_vllm/meta-llama/Llama-3.1-8B-Instruct")
model = LiteLlm(
    model=model_name_at_endpoint,
    api_base=api_base_url,
)

# Uses a tool and output_key
weather_agent = LlmAgent(
    model=model,
    name="weather_agent_tool",
    description="Retrieves weather in a city using a specific tool.",
    instruction="""You are a helpful agent that provides weather report in a city using a tool.
The user will provide a city name in a JSON format like {"city": "city_name"}.
1. Extract the city name.
2. Use the `get_weather` tool to find the weather. Don't use other tools!
3. Answer on user request based on the weather
""",
    tools=[get_weather],
    input_schema=CityInput,
    output_key="city_weather_tool_result", # Store final text response
)

root_agent = weather_agent
