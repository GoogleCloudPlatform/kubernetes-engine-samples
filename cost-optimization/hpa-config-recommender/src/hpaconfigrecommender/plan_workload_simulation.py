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

""" HPA Simulation Plan """
import logging
from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np
from .utils.config import Config
from .utils.models import (
    WorkloadDetails,
    WorkloadPlan,
)
from .utils.log import (
    log_exec_time
)

# Configure logger
logger = logging.getLogger(__name__)
# Configure pandas to copy on writing in a view
pd.options.mode.copy_on_write = True

def _get_proposed_memory_recommendation(
        config: Config,
        workload_df:pd.DataFrame,
        proposed_min_replicas: int,
        ) ->  float:
    """
    Calculate the recommended memory request per replica.

    This function computes the memory request per replica by dividing the
    total memory usage by the proposed minimum replicas and applying an
    extra buffer for memory recommendation.

    Args:
        config (Config): Configuration settings for mem recommendations.
        workload_df (pd.DataFrame): DataFrame containing workload metrics,
            including memory usage.
        proposed_min_replicas (int): Proposed minimum number of replicas.

    Returns:
        float: Recommended memory request per replica in MiB.
    """

    total_memory_capacity= (
        workload_df["sum_containers_mem_usage_mi"].max()
    )
    proposed_min_replicas = max(
        proposed_min_replicas, config.MIN_REC_REPLICAS
    )

    proposed_mem_recommendation = (
        (total_memory_capacity/proposed_min_replicas)
    )

    return np.ceil(
        min(
            proposed_mem_recommendation,
            workload_df["avg_container_mem_usage_mi"].mean()
        )*
        max(config.EXTRA_HPA_BUFFER_FOR_MEMORY_RECOMMENDATION,1))

def _get_unique_combinations(
    workload_plans: List[WorkloadPlan]
) -> List[WorkloadPlan]:
    """
    Filters a list of WorkloadPlan objects to return unique entries
    based on recommended CPU request, memory request, and replica counts.
    The list is sorted by method, then recommended_cpu_request,
    recommended_mem_request_and_limits_mi, and max_replicas.

    Args:
        workload_plans (List[WorkloadPlan]):
            List of recommendations from DMR (Dynamic Memory Request).

    Returns:
        List[WorkloadPlan]: Combined list of recommendations,
            where DMR recommendations that duplicate the DCR combinations
            (same CPU request and min replicas) are excluded.
    """
    seen = set()
    unique_plans = []

    for plan in workload_plans:
        key = (
            plan.recommended_cpu_request,
            plan.recommended_mem_request_and_limits_mi,
            plan.recommended_min_replicas,
            plan.recommended_max_replicas
        )

        if key not in seen:
            seen.add(key)
            unique_plans.append(plan)

    return sorted(
        unique_plans,
        key=lambda x: (
            x.method,
            x.recommended_cpu_request,
            x.recommended_mem_request_and_limits_mi,
            x.recommended_max_replicas
        )
    )


def _is_workload_balanced(workload_df: pd.DataFrame) -> bool:
    """
    Determines if the workload is balanced based on the ratio of CPU
    usage standard deviation to average usage.

    Args:
        workload_df (pd.DataFrame): DataFrame containing the
        workload metrics with "stddev_containers_cpu_usage"
        and "avg_container_cpu_usage".

    Returns:
        A boolean indicating if the workload
        is balanced (True), unbalanced (False), or None for invalid
        data.
    """
    if workload_df.empty:
        logger.warning("Workload DataFrame is empty,")
        return None

    try:
        avg_cpu_usage = workload_df["avg_container_cpu_usage"].mean()
        stddev_cpu_usage = workload_df["stddev_containers_cpu_usage"].mean()

        if avg_cpu_usage == 0:
            logger.info("Division by zero in workload balancing calculation.")
            return None

        ratio = (2 * stddev_cpu_usage) / avg_cpu_usage
        is_balanced = ratio < 0.25
        logger.info(
            "Workload is balanced: %s (ratio = %.3f)", is_balanced, ratio
        )
        return is_balanced

    except KeyError as e:
        logger.error("KeyError: Missing required column %s", {e})
        return True

def _is_cpu_under_provisioned(config: Config,
        workload_df: pd.DataFrame) -> bool:
    """
    Determines if the CPU is under-provisioned by comparing the
    maximum CPU request with the 90th percentile of CPU usage.

    Args:
        df (pd.DataFrame): DataFrame containing the columns.
        config (Config): Run configurations.

    Returns:
        bool: True if CPU is under-provisioned, otherwise False.
        Returns None if input data is invalid.
    """

    underprovisioned_cpu_usage_threshold = (
        config.UNDERPROVISIONED_CPU_USAGE_THRESHOLD
        )
    logger.info("Upder provsioned cpu thereshold: %.2f",
        underprovisioned_cpu_usage_threshold)

    # Compute and compare max CPU request and 90th percentile CPU usage
    max_cpu_request = (
        workload_df.get("avg_container_cpu_request", pd.Series(0)).max()
    )
    cpu_usage_percentile = (
        workload_df["avg_container_cpu_usage"].quantile(
        underprovisioned_cpu_usage_threshold
        )
    )

    return max_cpu_request < cpu_usage_percentile


def _calculate_recommended_max_cpu_capacity(
        config: Config,workload_df: pd.DataFrame) -> int:
    """
    Calculate the recommended maximum HPA capacity based on container
    CPU usage and requests.

    Args:
        df (pd.DataFrame): DataFrame containing 'sum_containers_cpu_request'
                           and 'sum_containers_cpu_usage' columns.
        config (Config): Run configurations.

    Returns:
        float: Recommended HPA max capacity for the workload.
    """

    if _is_cpu_under_provisioned(config,workload_df):
        sum_original_cpu_capacity = (
            workload_df["sum_containers_cpu_usage"].max() *
            config.EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY
        )
        logger.info("The CPU is under-provisioned.")
    else:
        sum_original_cpu_capacity = (
            workload_df["sum_containers_cpu_request"].max()
        )
        logger.info("The CPU is not under-provisioned.")

    logger.info("Max CPU capacity %.3f", sum_original_cpu_capacity)
    return (sum_original_cpu_capacity *
               config.EXTRA_HPA_BUFFER_FOR_MAX_REPLICAS)

def _vpa_recommendation(
        config: Config,
        workload_df: pd.DataFrame) -> WorkloadPlan:
    """
    Static workload recommendation

    Args:
        config (Config): _description_
        workload_df (pd.DataFrame): _description_

    Returns:
        WorkloadPlan
    """
    num_of_replicas = max(
        workload_df["num_replicas_at_usage_window"].min(),
          config.MIN_REC_REPLICAS
          )
    vpa_plan = WorkloadPlan(
        method= "VPA",
        recommended_cpu_request = round(
           (
               workload_df["sum_containers_cpu_usage"].quantile(0.98)/num_of_replicas
            ) * config.EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY

        ,3),
        recommended_cpu_limit_or_unbounded = np.ceil(
            (
                workload_df['sum_containers_cpu_usage'].max()/ num_of_replicas
            ) * config.EXTRA_HPA_BUFFER_FOR_CPU_USAGE_CAPACITY
        ),
        recommended_mem_request_and_limits_mi = np.ceil(
            (
            workload_df["sum_containers_mem_usage_mi"].max()/num_of_replicas
            ) * config.EXTRA_VPA_BUFFER_FOR_MEMORY_RECOMMENDATION
        ),
        recommended_min_replicas = num_of_replicas,
        recommended_max_replicas = num_of_replicas,
        recommended_hpa_target_cpu = 1.0,
        workload_e2e_startup_latency_rows=1
    )
    return vpa_plan

def _dynamic_cpu_request(
    config: Config,
    max_cpu_capacity: float,
    workload_df: pd.DataFrame
) -> List[WorkloadPlan]:
    """

    Generate dynamic CPU request values based on percentiles.

    This function calculates possible configurations for CPU request values
    using percentile-based metrics from workload data. It ensures that only
    unique CPU requests are considered, avoiding duplicates.

    Args:
        config (Config): Configuration settings for HPA recommendations.
        max_cpu_capacity (float): Maximum CPU capacity observed in the workload.
        workload_df (pd.DataFrame): DataFrame containing workload CPU and memory
         metrics.

    Returns:
        List[WorkloadPlan]: List of recommended HPA configurations based on
        CPU usage.

    """
     # Calculate minimum replicas and memory request
    min_replicas = max(
        get_min_replicas(workload_df, config),
        config.MIN_REC_REPLICAS
    )
    proposed_mem_request_mi = _get_proposed_memory_recommendation(
        config, workload_df, min_replicas
    )

    # Generate percentiles using numpy
    percentiles = np.arange(
        config.MIN_DCR_PERCENTILE_VALUE,
        config.MAX_DCR_PERCENTILE_VALUE + 1
    )

    # Calculate CPU requests for all percentiles at once
    quantiles = np.percentile(
        workload_df["avg_container_cpu_usage"], percentiles
    )

    # Round and enforce minimum CPU core value constraint
    cpu_request_percentiles = [
        (p, max(round(q, config.MCPU_ROUNDING),
                config.MIN_CPU_CORE_PROPOSED_VALUE))
        for p, q in zip(percentiles, quantiles)
    ]

    proposed_cpu_requests = []
    seen_combinations = set()

    # Iterate through CPU requests
    for p, cpu_request in cpu_request_percentiles:
        max_replicas = int(np.ceil(max_cpu_capacity / cpu_request))
        combination = (cpu_request, min_replicas, max_replicas)

        if combination not in seen_combinations:
            seen_combinations.add(combination)
            proposed_cpu_requests.append(
                WorkloadPlan(
                    recommended_cpu_request=cpu_request,
                    recommended_mem_request_and_limits_mi=(
                        proposed_mem_request_mi),
                    recommended_min_replicas=min_replicas,
                    recommended_max_replicas=max_replicas,
                    method=f"DCR-{p}",
                )
            )

    logger.info(
        "Generated %d Dynamic CPU Request (DCR) options.",
        len(proposed_cpu_requests),
    )
    return proposed_cpu_requests

def _dynamic_min_replicas(
    config: Config,
    max_cpu_capacity: float,
    workload_df: pd.DataFrame
) -> List[WorkloadPlan]:
    """
    Generate dynamic minimum replicas (DMR) options based on workload metrics.

    This function calculates possible configurations for the minimum number of
    replicas in an HPA setup by evaluating CPU and memory requirements.

    Args:
        config (Config): Configuration settings for HPA recommendations.
        max_cpu_capacity (float): Maximum CPU capacity observed in the workload.
        workload_df (pd.DataFrame): DataFrame containing workload CPU and memory
         metrics.

    Returns:
        List[WorkloadPlan]: List of recommended HPA configurations.
    """
    min_replicas_options = []
    seen_combinations = set()

    # Determine if workload is balanced and compute the proposed CPU request

    scaling_method = "mean" 
    proposed_cpu_request = round(
        workload_df["avg_container_cpu_usage"].mean(),
        config.MCPU_ROUNDING
    )

    if proposed_cpu_request == 0:
        logger.warning(
            "Proposed CPU request is 0. No replicas can be recommended.")
        return []

    # Initialize loop variables
    min_replicas = config.MIN_REC_REPLICAS
    max_replicas = int(np.ceil(max_cpu_capacity / proposed_cpu_request))

    # Iterate using a while loop to handle dynamic recalculations
    while min_replicas < max_replicas:

        # Calculate CPU request per replica
        cpu_request = max(
            round(proposed_cpu_request, 3),
            config.MIN_CPU_CORE_PROPOSED_VALUE
        )
        if (min_replicas * cpu_request) > (
            workload_df["sum_containers_cpu_usage"].max()):
            break

        # Recalculate max replicas based on updated CPU request
        max_replicas = int(np.ceil(max_cpu_capacity / cpu_request))
        # Calculate memory request per replica
        proposed_mem_request_mi = _get_proposed_memory_recommendation(
            config, workload_df, max_replicas
            )

        # Avoid duplicate combinations
        combination = (cpu_request, min_replicas, max_replicas)
        if combination not in seen_combinations:
            seen_combinations.add(combination)
            min_replicas_options.append(
                WorkloadPlan(
                    recommended_cpu_request=cpu_request,
                    recommended_mem_request_and_limits_mi=np.ceil(
                        proposed_mem_request_mi),
                    recommended_min_replicas=min_replicas,
                    recommended_max_replicas=max_replicas,
                    method=f"DMR_{scaling_method}-loop_{min_replicas}",
                )
            )

        # Increment min_replicas
        min_replicas += 1

    logger.info(
        "Generated %d Dynamic Minimum Replicas (DMR-%s) "
        "options based on CPU and memory metrics.",
        len(min_replicas_options),
        scaling_method
    )
    return min_replicas_options


def _calculate_max_usage_slope_up_ratio(
    workload_df: pd.DataFrame,
    workload_e2e_startup_latency_rows: int
) -> pd.DataFrame:
    """
    Updates the input DataFrame in place by calculating the
    'max_usage_slope_up_ratio' column while preserving the intermediate
    columns for CPU and memory usage during startup latency.

    Args:
        workload_df (pd.DataFrame): DataFrame containing workload metrics
            with CPU and memory usage data.
        workload_e2e_startup_latency_rows (int): Number of rows representing
            the startup latency window.

    Returns:
        pd.DataFrame: The input DataFrame updated with the following columns:
            - 'max_cpu_usage_in_workload_e2e_startup_latency'
            - 'max_mem_usage_mi_in_workload_e2e_startup_latency'
            - 'max_usage_slope_up_ratio'
    """
    if workload_e2e_startup_latency_rows <= 0:
        raise ValueError(
            "workload_e2e_startup_latency_rows must be greater than 0."
        )

    # Create a rolling window indexer
    forward_looking = pd.api.indexers.FixedForwardWindowIndexer(
        window_size=workload_e2e_startup_latency_rows
    )

    # Compute rolling max for CPU and memory usage, and keep the columns
    workload_df["max_cpu_usage_in_workload_e2e_startup_latency"] = (
        workload_df["avg_container_cpu_usage"]
        .rolling(window=forward_looking)
        .max()
    )

    workload_df["max_mem_usage_mi_in_workload_e2_startup_latency"] = (
        workload_df["max_containers_mem_usage_mi"]
        .rolling(window=forward_looking)
        .max()
    )

    # Compute CPU and memory ratios safely (avoiding division by zero)
    cpu_ratio = (
        workload_df["max_cpu_usage_in_workload_e2e_startup_latency"]
        / workload_df["avg_container_cpu_usage"].replace(0, np.nan)
    )
    mem_ratio = (
        workload_df["max_mem_usage_mi_in_workload_e2_startup_latency"]
        / workload_df["max_containers_mem_usage_mi"].replace(0, np.nan)
    )

    # Compute the max usage slope-up ratio as the element-wise maximum
    workload_df["max_usage_slope_up_ratio"] = np.maximum(
        cpu_ratio.fillna(0), mem_ratio.fillna(0)
    )

    return workload_df


def _get_recommended_configs(
    config: Config,
    plan: WorkloadPlan,
    workload_df: pd.DataFrame
    ) -> Tuple[Optional[WorkloadPlan], Optional[str]]:
    """
    Calculates the recommended HPA configurations based on the workload
    analysis and usage slopes.

    Args:
        workload_df (pd.DataFrame): The DataFrame containing the workload
            data.
        plan (WorkloadPlan): The HPA plan with initial
            recommendations.
        config (Config): Run configurations.

    Returns:
        Tuple[WorkloadPlan,str]: The updated HPA plan
        with recommended target CPU and limits, and a reason if the plan
        is skipped or invalid.
    """
    reason = {}
    # Filter only the points above what is recommended as baseline requests
    plan_request_baseline = plan.recommended_cpu_request
    filtered_df = workload_df[
        workload_df["avg_container_cpu_usage"] >= plan_request_baseline
    ]
    if filtered_df.empty:
        reason = (
            f"Skip HPA Plan {plan.method}. "
            f"No usage above CPU baseline requests:{plan_request_baseline:.2f}."
        )
        logger.info(reason)
        return None, reason

    # Check if slopes are too big
    max_usage_slope_up_ratio = round(
        filtered_df["max_usage_slope_up_ratio"].max(), 2
    )
    if max_usage_slope_up_ratio > config.HPA_SCALE_LIMIT:
        reason = (
            f"Skip HPA Plan {plan.method}. Slope ratio "
            f"{max_usage_slope_up_ratio} exceeds HPA scale limit "
            f"{config.HPA_SCALE_LIMIT}."
        )
        logger.info(reason)
        return None, reason

    plan.max_usage_slope_up_ratio = max_usage_slope_up_ratio
    plan.recommended_hpa_target_cpu = round(
        (
            (1 - config.HPA_TARGET_BUFFER) /
            filtered_df["max_usage_slope_up_ratio"]
        ).min(), 2
    )
    min_hpa_target_cpu = config.MIN_HPA_TARGET_CPU
    max_hpa_target_cpu = config.MAX_HPA_TARGET_CPU
    if plan.recommended_hpa_target_cpu < min_hpa_target_cpu or \
            plan.recommended_hpa_target_cpu > max_hpa_target_cpu:
        reason = (
            f"Skip HPA Plan {plan.method}. Recommended Target CPU "
            f"{plan.recommended_hpa_target_cpu} not between "
            f"{min_hpa_target_cpu} and {max_hpa_target_cpu}."
        )
        logger.info(reason)
        return None, reason

    plan.recommended_cpu_limit_or_unbounded = np.ceil(
        plan.recommended_cpu_request + (
            filtered_df[
                "max_cpu_usage_in_workload_e2e_startup_latency"
            ].max() / plan.recommended_max_replicas
        )
    )
    return plan, None

def convert_data_types(workload_df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts data types of specific columns in a workload DataFrame for
    memory efficiency and optimized performance.

    - Converts 'window_begin' to datetime64 format.
    - Converts 'num_replicas_at_usage_window' to Int16 (nullable).
    - Converts CPU-related columns to float16 for reduced memory usage.
    - Converts memory-related columns to Int64 (nullable) for larger
      integer capacity.

    Parameters:
        workload_df (pd.DataFrame): The DataFrame containing workload data
                                    with specific columns for conversion.

    Returns:
        pd.DataFrame: DataFrame with columns converted to optimized data types.

    Raises:
        KeyError: If any required column is missing from the input DataFrame.
    """
    # Convert to datetime[s] and remove timezone awareness
    workload_df["window_begin"] = pd.to_datetime(
        workload_df["window_begin"], errors="coerce"
    ).dt.tz_localize(None).astype("datetime64[s]")

    # Convert `num_replicas_at_usage_window` to Int16, allowing for NaN
    workload_df["num_replicas_at_usage_window"] = (
        pd.to_numeric(
            workload_df["num_replicas_at_usage_window"], errors="coerce")
        .astype("Int16")
    )

    # Convert metrics to appropriate numeric types
    float16_columns = [
        "avg_container_cpu_usage",
        "stddev_containers_cpu_usage",
        "sum_containers_cpu_request",
        "sum_containers_cpu_usage"
    ]

    float32_columns = [
        "sum_containers_mem_request_mi",
        "sum_containers_mem_usage_mi"
    ]

    for col in float16_columns:
        workload_df[col] = (
            pd.to_numeric(workload_df[col], errors="coerce").astype("float16")
            )

    for col in float32_columns:
        workload_df[col] = (
            pd.to_numeric(workload_df[col], errors="coerce").astype("float32")
            )
    return workload_df

def get_min_replicas(workload_df: pd.DataFrame, config: Config)-> int:
    """
    Due to node autoscaling, workloads can be evicted and, during a small
    portion of the time, they can get to a smaller than desired number of
    replicas if they don´t have PDB blocking this behaviour.

    Because of such a situation, we return the number of replicas at 10th
    percentile. The 0.1 was arbritary and may be revisited in the future.
    """
    df = workload_df[workload_df["num_replicas_at_usage_window"] > 0]
    if df.empty:
        return config.MIN_REC_REPLICAS
    min_replicas_at_10p = df["num_replicas_at_usage_window"].quantile(0.1)
    return int(min_replicas_at_10p)

@log_exec_time(logger)
def get_simulation_plans(
    workload_details: WorkloadDetails,
    workload_df: pd.DataFrame
) -> Tuple[List[WorkloadPlan], Dict[str,str]]:
    """
    Returns a list of all recommendations from the DMR and DCR Algorithms.

    Args:
        workload_df (pd.DataFrame): DataFrame with workload metrics.
        workload_details: Workload details.

    Returns:
        List[WorkloadPlan]: List of resource recommendations.
        during the programs's run.
    """
    logger.info("Starting HPA simulation plan %s.", workload_details)
    reasons = {}
    if workload_df.empty:
        logger.warning(
            "The workload dataframe is empty, exiting simulation plan."
        )
        reasons["general"] = "Workload dataframe is empty."
        return [], reasons

    workload_df = convert_data_types(workload_df)

    max_cpu_capacity = _calculate_recommended_max_cpu_capacity(
        workload_details.config, workload_df)

    if max_cpu_capacity == 0:
        logger.warning("CPU Max Capacity is 0, exiting simulation plan.")
        reasons["general"] = "CPU Max Capacity is 0."
        return [], reasons

    dcr = _dynamic_cpu_request(
        workload_details.config,
        max_cpu_capacity,
        workload_df
    )

    dmr = _dynamic_min_replicas(
            workload_details.config,
            max_cpu_capacity,
            workload_df
    )

    combinations = dcr + dmr
    proposed_hpa_resources = _get_unique_combinations(combinations)

    if not proposed_hpa_resources:
        logger.info(
            "No valid recommendations generated: for %s", workload_details
        )
        reasons["general"] = "No valid recommendations generated."
        return [], reasons

    workload_e2e_startup_latency_rows = (
        workload_details.workload_e2e_startup_latency_rows
        )

    workload_df = _calculate_max_usage_slope_up_ratio(
        workload_df, workload_e2e_startup_latency_rows
        )

    plans = []
    for plan in proposed_hpa_resources:
        plan.workload_e2e_startup_latency_rows = (
            workload_e2e_startup_latency_rows
        )
        config_vals, reason = _get_recommended_configs(
                workload_details.config,
                plan,
                workload_df
            )
        if config_vals is None:
            reasons[plan.method] = reason
            continue
        plans.append(plan)
    plans.append(_vpa_recommendation(workload_details.config, workload_df))
    logger.info(
        "HPA simulation plan completed successfully with %d plans for %s.",
        len(plans),
        workload_details
    )
    return plans, reasons