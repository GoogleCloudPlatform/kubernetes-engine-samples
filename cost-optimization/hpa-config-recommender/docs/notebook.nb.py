# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.6
#   kernelspec:
#     display_name: Python 3
#     name: python3
# ---

# %%
# Copyright 2025 Google LLC
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# %% [markdown] id="F5NeGWWU_ZRa"
# # Workload Recommender Module Deployment Guide
#
#
# Ensure you have Python installed and then execute the following commands to build and install the library locally.
#

# %% id="O9iW9oWt_YLv"
# Install build tool and build the project
# ! python3 -m pip install --upgrade build
# ! python3 -m build

# %% id="pMw4aVXq_8Kf"
# Install the built library
# ! pip install dist/workloadrecommender-*.tar.gz --quiet

# %% id="TKlbZ7xAACnA"
# ## Step 2: Authenticate with Google Cloud
# You need to authenticate with Google Cloud to access GKE metrics.

# Authenticate using Google Cloud SDK
# ! gcloud auth application-default login

# %% id="JfOibFN8AIHj"
# ## Step 3: Import Required Modules and Define Workload Details
# Import the necessary modules and define your Kubernetes workload details.
from hpaconfigrecommender.hpa_simulation_run import(
        run_hpa_simulation_plans
)
from hpaconfigrecommender.hpa_simulation_plan import(
        get_hpa_simulation_plans
)
from hpaconfigrecommender.utils.config import HPAConfig
from hpaconfigrecommender.utils.models import (
    WorkloadDetails
)
hpa_config = HPAConfig()

# %% id="ksDrL7bSD97c"
from datetime import datetime, timedelta

# Parameters (from user inputs)
ANALYSIS_PERIOD_START_DATETIME = "2025-01-01 16:30:00+00:00"  #@param {type:"string"}
ANALYSIS_PERIOD_END_DATETIME = "2025-01-15 16:30:00+00:00"  #@param {type:"string"}
PROJECT_ID = 'gtools-koptimize'  #@param {type:"string"}
LOCATION = 'us-central1'  #@param {type:"string"}
CLUSTER_NAME = 'online-boutique-ca'  #@param {type:"string"}
NAMESPACE = 'default'  #@param {type:"string"}
CONTAINER_NAME = 'perf-server-js'  #@param {type:"string"}
CONTROLLER_NAME = 'perf-server-js'  #@param {type:"string"}
CONTROLLER_TYPE = 'Deployment'  #@param {type:"string"}

# Validate parameters
try:
    start_datetime = datetime.strptime(ANALYSIS_PERIOD_START_DATETIME, "%Y-%m-%d %H:%M:%S%z")
    end_datetime = datetime.strptime(ANALYSIS_PERIOD_END_DATETIME, "%Y-%m-%d %H:%M:%S%z")

    # Ensure all fields are entered and validate dates
    if not all([PROJECT_ID, LOCATION, CLUSTER_NAME, NAMESPACE, CONTAINER_NAME, CONTROLLER_NAME, CONTROLLER_TYPE]):
        raise ValueError("All workload search parameters must be provided.")
    if start_datetime >= end_datetime:
        raise ValueError("The start date must be earlier than the end date.")
    if start_datetime < datetime.now(tz=start_datetime.tzinfo) - timedelta(weeks=6):
        raise ValueError("The start date must be within the last 6 weeks.")
except ValueError as e:
    print(f"Parameter validation error: {e}")
    raise

# %% id="sR9iTprFAet4"
# Define the details for your Kubernetes workload
workload_details = WorkloadDetails(
            project_id="gke-rightsize",
            cluster_name="online-boutique",
            location="us-central1-f",
            namespace="default",
            controller_name="frontend",
            controller_type="Deployment",
            container_name="server"
        )


# %% id="5xVgoZVNAnP_"
# ## Step 4: Fetch Aggregated Timeseries Metrics
# Use the `get_workload_agg_timeseries` function to fetch CPU and memory usage metrics for the workload.

# Define start and end times for analysis
def convert_str_time(date_str):
        date_object = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S%z")
        return(date_object)

start_datetime = convert_str_time(ANALYSIS_PERIOD_START_DATETIME)
end_datetime = convert_str_time(ANALYSIS_PERIOD_END_DATETIME)

workload_df = get_workload_agg_timeseries(
        hpa_config,workload_details,start_datetime, end_datetime
        )

# %% id="z4yyIl2vA8Ck"
# ## Step 5: Enrich the `workload_details` object with the time it takes for the workload to go from pod scheduling to the ready state.

# Add workload startuptime
workload_details.scheduled_to_ready_seconds = 30

# %% id="afyBzLmGBV3D"
# ## Step 6: Generate HPA or VPA Simulation Plans
# Use the `get_simulation_plans` function to generate scaling recommendations based on historical data.

plans, reason = get_hpa_simulation_plans(hpa_config, workload_details, workload_df)

# %% id="t-xujLb2BwBV"
# ## Step 7: Run the Simulation
# Simulate the plans to evaluate performance and resource optimization.

analysis_df, recomendation,  reasons = run_hpa_simulation_plans(hpa_config, plans, workload_details, workload_df)

# ## Step 8: Review Results
# Review the generated analysis and recommendations.

if analysis_df.empty:
    print("No suitable recommendations found. Summary:")
    print(reasons)
else:
    print("Recommendations Summary:")
    print(recommendation)
    analysis_df["recommended_cpu_request"] = recomendation.hpa_plan.recommended_cpu_request
    analysis_df["recommended_mem_request_mi"] = recomendation.hpa_plan.recommended_mem_request_mi

# Plot visualizations for recommendation
    analysis_df.plot(title="CPU Recommendation vs Avg Usage", x="window_begin", y=["recommended_cpu_request","avg_container_cpu_usage"])
    analysis_df.plot(title="Memory Recommendation vs Avg Usage (MiB)", x="window_begin", y=["recommended_mem_request_mi","max_containers_mem_usage_mi"])

    analysis_df.plot(title="CPU Sum Usage vs Recommendation", x="window_begin", y=["hpa_forecast_sum_cpu_up_and_running","sum_container_cpu_usage"])
    analysis_df.plot(title="Memory Sum Usage vs Recommendation (MiB)", x="window_begin", y=["hpa_forecast_sum_mem_up_and_running","sum_containers_mem_usage_mi"])

