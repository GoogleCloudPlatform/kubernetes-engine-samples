# Copyright 2025 Google LLC
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

''' Simulation Run - Code to Run recommendations plans and simulations'''
from multiprocessing import Pool
import logging
from google.cloud import bigquery
from google.api_core.gapic_v1.client_info import ClientInfo
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np
from hpaconfigrecommender.utils.models import (
    WorkloadPlan,
    WorkloadRecommendation,
    WorkloadDetails,
)
from hpaconfigrecommender.plan_workload_simulation import (
    get_simulation_plans, convert_data_types
)
from .utils.config import (
    Config, USER_AGENT
)
from .utils.log import (
    log_exec_time
)

# Configure logger
logger = logging.getLogger(__name__)


def _calculate_savings(
        analysis_df: pd.DataFrame, config: Config) -> pd.DataFrame:
    '''
    Calculates the CPU and memory savings based on recommendations forecasts.

    Args:
        analysis_df (pd.DataFrame): The DataFrame containing workload
        data to analyze.
        config (Config): Run configurations.

    Returns:
        pd.DataFrame: The DataFrame with calculated savings columns.
    '''
    if analysis_df.empty:
        logger.info('The analysis dataframe is empty')
        return pd.DataFrame()

    # Convert 'window_begin' to datetime if it's not already
    analysis_df['window_begin'] = pd.to_datetime(analysis_df['window_begin'])

    # Ensure the DataFrame is sorted by 'window_begin'
    analysis_df = analysis_df.sort_values('window_begin')

    # Set 'window_begin' as the index
    analysis_df.set_index('window_begin', inplace=True)

    # Calculate CPU and memory savings
    analysis_df['forecast_cpu_saving'] = (
        analysis_df.get('sum_containers_cpu_request', np.inf)
        - analysis_df['forecast_sum_cpu_up_and_running']
    ).round(3)

    analysis_df['forecast_mem_saving_mi'] = np.ceil(
        analysis_df.get('sum_containers_mem_request_mi', np.inf)
        - analysis_df['forecast_sum_mem_up_and_running']
    )
    analysis_df['avg_saving_in_cpus'] = (
        analysis_df['forecast_cpu_saving']
        + (
            (analysis_df['forecast_mem_saving_mi'] / 1024)
            / config.COST_OF_GB_IN_CPUS
        )
    ).round(2)

    # Calculate line clash as a boolean
    analysis_df['forecast_clash'] = (
        analysis_df['sum_containers_cpu_usage']
        > analysis_df['forecast_sum_cpu_up_and_running']
    ) | (
        analysis_df['sum_containers_mem_usage_mi']
        > analysis_df['forecast_sum_mem_up_and_running']
    )
    # Apply rolling mean over a 1-day (24-hour)
    # window using time-based rolling
    analysis_df['avg_saving_in_cpus_1d_mean'] = (
        analysis_df['avg_saving_in_cpus']
        .rolling(window='1D', min_periods=1)
        .mean()
        .round(2)
    )
    # Reset the index if needed
    analysis_df.reset_index(inplace=True)

    return analysis_df

def _simulate_behaviour(
    config: Config,
    rec: WorkloadRecommendation,
    workload_df: pd.DataFrame,
    starting_replica: int
) -> pd.DataFrame:
    """
    Simulates recommendations behavior for a workload.
    """
    if rec.plan.method == 'VPA':
        plan = rec.plan
        # Update the DataFrame in a single operation
        workload_df['forecast_replicas_up_and_running'] = (
            plan.recommended_max_replicas
        )
        workload_df['forecast_sum_cpu_up_and_running'] = (
            plan.recommended_max_replicas * plan.recommended_cpu_request
        )
        workload_df['forecast_sum_mem_up_and_running'] = (
            plan.recommended_max_replicas *
            plan.recommended_mem_request_and_limits_mi
        )
        workload_df['scale_up_behaviour_to_x_times'] = 0
        workload_df['forecast_replicas_desired'] = (
            plan.recommended_max_replicas
            )
        return workload_df

    cpu_clash_counter = 0

    # Extract constants
    min_replicas = rec.plan.recommended_min_replicas
    max_replicas = rec.plan.recommended_max_replicas
    recommended_cpu_request = rec.plan.recommended_cpu_request
    recommended_mem_request = (
        rec.plan.recommended_mem_request_and_limits_mi
    )
    target_cpu = rec.plan.recommended_hpa_target_cpu
    startup_latency = rec.plan.workload_e2e_startup_latency_rows
    scale_down_steps = config.HPA_SCALE_DOWN_DEFAULT_BEHAVIOUR_STEPS

    # Initialize arrays
    n_rows = len(workload_df)
    forecast_replicas = np.empty(n_rows, dtype=int)
    forecast_replicas[:] = min_replicas
    forecast_sum_cpu = np.zeros(n_rows)
    forecast_sum_mem = np.zeros(n_rows)
    scale_up_behaviour = np.zeros(n_rows)
    forecast_replicas_desired = np.zeros(n_rows, dtype=int)

    # Extract necessary columns as numpy arrays
    sum_cpu_usage = workload_df['sum_containers_cpu_usage'].to_numpy()
    sum_mem_usage_mi = workload_df['sum_containers_mem_usage_mi'].to_numpy()
    # Iterate through rows to simulate recommendations behavior
    for i in range(n_rows):
        if i < startup_latency:
            forecast_replicas[i] = starting_replica
        else:
            # Handle scale-up and scale-down conditions
            scale_up_index = i - startup_latency
            scale_down_start_index = max(0, scale_up_index - scale_down_steps)
            scale_down_end_index = scale_down_start_index + scale_down_steps

            # Scale-up condition
            replicas_up = (
                forecast_replicas_desired[scale_up_index]
                if scale_up_index >= 0
                else min_replicas
            )

            # Scale-down condition
            if scale_down_start_index <= 0:
                replicas_down = min_replicas
            else:
            # Scale-down condition
                replicas_down = max(
                    forecast_replicas_desired[
                        scale_down_start_index:scale_down_end_index].max(),
                    min_replicas,
                )

            # Final forecast replicas
            forecast_replicas[i] = np.clip(
                max(replicas_up, replicas_down), min_replicas, max_replicas
            )

        # Forecast CPU and memory usage
        forecast_sum_cpu[i] = (
            forecast_replicas[i] * recommended_cpu_request
        )
        forecast_sum_mem[i] = (
            forecast_replicas[i] * recommended_mem_request
        )

        # Validate forecasted CPU usage against actual usage
        if forecast_sum_cpu[i] < sum_cpu_usage[i]:
            cpu_clash_counter += 1

            if cpu_clash_counter > config.CPU_CLASH_COUNT_THRESHOLD:
                rec.valid = False
                rec.validation_msg = (
                    f'Index: {i} '
                    f'Clash exists '
                    f'recommendations forecast sum cpu: {forecast_sum_cpu[i]:.3f} is < '
                    f'sum cpu usage: {sum_cpu_usage[i]:.3f} '
                    'This exceeds the CPU_CLASH_COUNT_THRESHOLD: '
                    f'{config.CPU_CLASH_COUNT_THRESHOLD}'
                )
                return pd.DataFrame()  # Exit early if forecast is invalid

        # Validate forecasted memory usage against actual usage
        if forecast_sum_mem[i] < sum_mem_usage_mi[i]:
            rec.valid = False
            rec.validation_msg = (
                f'Index: {i} '
                f'Clash exists '
                f'recommendations forecast sum mem: {forecast_sum_cpu[i]:.3f} is < '
                f'sum mem usage: {sum_mem_usage_mi[i]:.3f}'
            )
            return pd.DataFrame()  # Exit early if forecast is invalid
        # Compute current metric value
        current_metric_value = round((
            sum_cpu_usage[i] / forecast_sum_cpu[i]
            if recommended_cpu_request > 0
            else 0
        ),2)
        scale_up_behaviour[i] = current_metric_value

        # Compute desired replicas within min and max replica limits
        if i < startup_latency:
            forecast_replicas_desired[i]=starting_replica
        else:
            forecast_replicas_desired[i] = max(
                min_replicas,
                min(
                    max_replicas,
                    int(
                        np.ceil(
                            forecast_replicas[i] * (
                                current_metric_value / target_cpu
                                )
                        )
                    )
                )
            )


    # Update the DataFrame in a single operation
    workload_df['forecast_replicas_up_and_running'] = forecast_replicas
    workload_df['forecast_sum_cpu_up_and_running'] = forecast_sum_cpu
    workload_df['forecast_sum_mem_up_and_running'] = forecast_sum_mem
    workload_df['scale_up_behaviour_to_x_times'] = scale_up_behaviour
    workload_df['forecast_replicas_desired'] = forecast_replicas_desired

    return workload_df

def _is_plan_valid(
        config: Config, plan: WorkloadPlan
        ) -> Tuple[bool, Optional[str]]:
    '''
    Validate an recommendations workload plan based on defined criteria.

    Args:
        plan (WorkloadPlan): The recommendations workload plan to validate.
        config (Config): Run configurations

    Returns:
        bool: Returns True if the recommendations plan is valid, otherwise False.

    Validation criteria:
    - The `max_usage_slope_up_ratio` should not exceed the defined
      `config.HPA_SCALE_LIMIT`.
    - The `recommended_min_replicas` must be less than the
      `recommended_max_replicas`.
    - The recommendations Target CPU must be greater than the config.MIN_HPA_TARGET_CPU
    '''
    HPA_SCALE_LIMIT = config.HPA_SCALE_LIMIT
    MIN_HPA_TARGET_CPU = config.MIN_HPA_TARGET_CPU

    if plan.max_usage_slope_up_ratio > HPA_SCALE_LIMIT:
        msg = 'max_usage_slope_up_ratio: {} exceeds HPA_SCALE_LIMIT {}'.format(
            plan.max_usage_slope_up_ratio, HPA_SCALE_LIMIT
        )
        return False, msg
    if (
        plan.recommended_min_replicas
        > plan.recommended_max_replicas
    ):
        msg = 'min replicas {} greater than  max replicas {}'.format(
            plan.recommended_min_replicas,
            plan.recommended_max_replicas,
        )
        return False, msg
    if plan.recommended_hpa_target_cpu < MIN_HPA_TARGET_CPU:
        msg =(
            'recommended_hpa_target_cpu {} is less than MIN_HPA_TARGET_CPU {}'
            .format(plan.recommended_hpa_target_cpu, MIN_HPA_TARGET_CPU)
        )
        return False, msg
    return True, None

def _process_plan(
    plan: WorkloadPlan,
    workload_details: WorkloadDetails,
    workload_df: pd.DataFrame,
    config: Config,
    calculate_inital_replicas: callable,
) -> Tuple[Optional[pd.DataFrame],
           WorkloadRecommendation, Optional[str]]:
    '''
    Processes a single recommendations plan: validates, simulates behavior,
    calculates savings.

    Args:
        plan (WorkloadPlan): The recommendations plan to process.
        workload_details (WorkloadDetails): Details of the workload.
        workload_df (pd.DataFrame): DataFrame containing workload data.
        config (Config): Configuration for recommendations processing.
        calculate_starting_replicas (callable): Function to calculate starting
        replicas.

    Returns:
        Tuple[Optional[pd.DataFrame], Optional[WorkloadRecommendation]]:
            - A DataFrame with simulation results, or None if skipped.
            - The WorkloadRecommendation for the plan, or None if invalid.
    '''
    logger.info('Processing plan: %s', plan.method)
    # Create recommendation and validate
    rec = WorkloadRecommendation(
        workload_details=workload_details,
        plan=plan,
    )

    rec.valid, rec.validation_msg = (
        _is_plan_valid(config, plan)
    )

    logger.info(
        'Details: %s\nPlan: %s\nValid: %s (%s)',
        workload_details, plan, rec.valid, rec.validation_msg
    )

    if not rec.valid:
        logger.info('Invalid plan: %s', rec.validation_msg)
        return None, rec, rec.validation_msg

    # Calculate starting replicas
    starting_replicas = calculate_inital_replicas(workload_df, plan)
    logger.info('Starting replicas: %s', starting_replicas)

    # Simulate recommendations behavior

    analysis_df = _simulate_behaviour(
        config, rec, workload_df, starting_replicas
    )

    if analysis_df.empty:
        logger.info('Empty simulation results. Skipping.')
        rec.valid = False
        return None, rec, rec.validation_msg

    # Calculate savings and analyze clashes
    analysis_df = _calculate_savings(analysis_df, config)
    rec.forecast_cpu_saving = (
        analysis_df['forecast_cpu_saving'].mean().round(3)
    )
    rec.forecast_mem_saving_mi = (
        np.ceil(analysis_df['forecast_mem_saving_mi'].mean())
    )
    avg_saving = analysis_df['avg_saving_in_cpus'].mean()
    rec.scale_up_behaviour_to_x_times = (
        analysis_df['scale_up_behaviour_to_x_times'].max()
    )

    logger.info('Avg savings for %s: %s', plan.method, avg_saving)
    analysis_df['method'] = plan.method
    return analysis_df, rec, None

def _calculate_starting_replicas(
        workload_df:pd.DataFrame, plan: WorkloadPlan):
    '''Calcuate the number of replicas needed during initial startup'''

    max_cpu = workload_df.loc[0:plan.workload_e2e_startup_latency_rows, 'sum_containers_cpu_usage'].max()
    starting_replicas =  int(np.ceil(max_cpu / plan.recommended_cpu_request))
    return np.clip(
        starting_replicas,
        plan.recommended_min_replicas,
        plan.recommended_max_replicas)

def _analyze_configuration_plans(
    config: Config,
    plans: List[WorkloadPlan],
    workload_details: WorkloadDetails,
    workload_df: pd.DataFrame,
) -> Tuple[pd.DataFrame,WorkloadRecommendation, Optional[str]]:
    '''
    Optimized recommendations simulation plans analysis for a given workload using
    concurrent.futures.
    '''
    reasons = {}

    workload_df = convert_data_types(workload_df)

    # Prepare the function arguments
    args_list = [
        (
            plan, workload_details, workload_df,
            config, _calculate_starting_replicas
            )
        for plan in plans
    ]

    highest_avg_saving = -np.inf
    best_rec = None
    best_analysis_df = pd.DataFrame()
    all_simulation_df = []

    # Use ProcessPoolExecutor for multiprocessing
    with ProcessPoolExecutor() as executor:
        # Submit all tasks to the executor
        results = executor.map(_process_plan, *zip(*args_list)) 
        for result in results:
            analysis_df, rec, reason = result  # Unpack the result tuple
            if analysis_df is None:
                reasons[rec.plan.method] = reason
                continue

            # Evaluate results
            avg_saving = analysis_df['avg_saving_in_cpus'].mean()
            all_simulation_df.append(analysis_df)
            if avg_saving > highest_avg_saving:
                highest_avg_saving = avg_saving
                best_rec = rec
                best_analysis_df = analysis_df

    logger.info(best_rec)

    return best_analysis_df, best_rec, reasons, all_simulation_df

def write_to_bigquery(analysis_df: pd.DataFrame,
                       rec: WorkloadRecommendation,
                       bq_project_id: str,
                       bq_dataset_id: str,
                       bq_table_id: str):
    """
    Writes the given DataFrame to BigQuery, ensuring only the required columns are sent.

    Args:
        analysis_df (pd.DataFrame): DataFrame containing the time series data.
        rec: Object containing workload details and additional attributes.
    """
    if analysis_df.empty:
        logger.info("No data to write to BigQuery.")
        return

    # Define additional workload details to be added to the DataFrame
    required_columns = {
        "project_id": rec.workload_details.project_id,
        "cluster_name": rec.workload_details.cluster_name,
        "location": rec.workload_details.location,
        "namespace": rec.workload_details.namespace,
        "controller_name": rec.workload_details.controller_name,
        "container_name": rec.workload_details.container_name,
        "analysis_period_start": rec.analysis_period_start,
        "analysis_period_end": rec.analysis_period_end,
        "recommended_cpu_request": rec.plan.recommended_cpu_request,
        "recommended_mem_request_and_limits_mi": rec.plan.recommended_mem_request_and_limits_mi,
        "recommended_cpu_limit_or_unbounded": rec.plan.recommended_cpu_limit_or_unbounded,
        "recommended_min_replicas": rec.plan.recommended_min_replicas,
        "recommended_max_replicas":rec.plan.recommended_max_replicas,
        "recommended_hpa_target_cpu": rec.plan.recommended_hpa_target_cpu,
        "max_usage_slope_up_ratio": rec.plan.max_usage_slope_up_ratio,
        "workload_e2e_startup_latency_rows": rec.plan.workload_e2e_startup_latency_rows,
        "method": rec.plan.method,
        "forecast_mem_saving_mi": rec.forecast_mem_saving_mi,
        "forecast_cpu_saving": rec.forecast_cpu_saving,
    }

    # Add workload details to the DataFrame
    for col, value in required_columns.items():
        analysis_df[col] = value

    # Define only the required columns to be written to BigQuery
    required_bq_columns = [
        "window_begin",
        "num_replicas_at_usage_window",
        "sum_containers_cpu_request",
        "sum_containers_cpu_usage",
        "forecast_sum_cpu_up_and_running",
        "sum_containers_mem_request_mi",
        "sum_containers_mem_usage_mi",
        "forecast_sum_mem_up_and_running",
        "forecast_replicas_up_and_running",
    ] + list(required_columns.keys())  # Append workload details to required col

    # Filter DataFrame to contain only the required columns
    analysis_df = analysis_df[required_bq_columns]


    full_table_id = f"{bq_project_id}.{bq_dataset_id}.{bq_table_id}"

    # Configure BigQuery client with custom user-agent
    client_info = ClientInfo(user_agent=USER_AGENT)
    bq_client = bigquery.Client(project=bq_project_id, client_info=client_info)

    try:
        # Load DataFrame into BigQuery
        job = bq_client.load_table_from_dataframe(
            analysis_df,
            full_table_id,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"),
        )

        job.result()  # Wait for the job to complete
        logger.info(
            f"Successfully wrote {len(analysis_df)} records to BigQuery table "
            f"{full_table_id}")

    except Exception as e:
        logger.error(f"Failed to write to BigQuery: {e}")


@log_exec_time(logger)
def run_simulation_plans(
    plans: List[WorkloadPlan],
    workload_details: WorkloadDetails,
    workload_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, WorkloadRecommendation, Dict[str,str]]:
    '''
    Runs the recommendations simulation for a given workload and recommendations plans.

    Args:
        workload_df (pd.DataFrame): Workload metrics and data.
        workload_details (WorkloadDetails): Workload's characteristics.
        plans (List[WorkloadRecommendation]): List of recommendations plans.

    Returns:
        Tuple[pd.DataFrame, Optional[WorkloadRecommendation]]:
            - A DataFrame with simulation analysis.
            - An WorkloadRecommendation or None if no data is found.
    '''
    reasons = {}
    analysis_df, rec, reason, all_simulations_df = _analyze_configuration_plans(
        workload_details.config,
        plans,
        workload_details,
        workload_df
    )

    if analysis_df.empty:
        logger.info('No valid analysis data found, returning empty DataFrame.')
        reasons['Empty analysis dataframe'] =  reason
        return analysis_df, None, reasons
    rec.workload_details.min_replicas = int(np.ceil(
        analysis_df['num_replicas_at_usage_window'].min()
    ))
    rec.workload_details.max_replicas = int(np.ceil(
        analysis_df['num_replicas_at_usage_window'].max()
    ))
    rec.analysis_period_start=analysis_df['window_begin'].min()
    rec.analysis_period_end=analysis_df['window_begin'].max()
    rec.workload_details.min_replicas=(
        analysis_df['num_replicas_at_usage_window'].min()
        )
    rec.workload_details.max_replicas=(
        analysis_df['num_replicas_at_usage_window'].max()
        )

    return analysis_df, rec, reason, all_simulations_df

@log_exec_time(logger)
def plan_and_run_simulation(
    workload_details: WorkloadDetails,
    workload_df: pd.DataFrame
) -> Tuple[pd.DataFrame, WorkloadRecommendation, Dict[str,str]]:
    '''
    Plans and runs the recommendations simulation for the given workload.

    Args:
        workload_details (WorkloadDetails): Workload's characteristics.
        workload_df (pd.DataFrame): Workload metrics and data.

    Returns:
        Tuple[pd.DataFrame, Optional[WorkloadRecommendation]]:
            - A DataFrame with simulation results.
            - An WorkloadRecommendation or None if no plans exist.
    '''
    reasons = {}
    plans, reason = get_simulation_plans(
        workload_details,
        workload_df
    )
    if not plans:
        logger.info('No plans exists for workload %s', workload_details)
        reasons['No plans exists'] = reason
        return pd.DataFrame(), None, reasons
    analysis_df, savings_summary , reason, all_simulation_dfs = run_simulation_plans(
        plans,
        workload_details,
        workload_df
    )
    return analysis_df, savings_summary, reasons, all_simulation_dfs


