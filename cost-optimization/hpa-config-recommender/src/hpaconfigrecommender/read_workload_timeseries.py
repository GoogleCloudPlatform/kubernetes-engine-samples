# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''Reading GKE metric data from Cloud monitoring'''
from datetime import datetime
from aiohttp import ClientResponseError
import logging
import pandas as pd
import numpy as np
import asyncio
import pytz
from google.auth.transport.requests import Request
from google.auth import default
import httpx

from hpaconfigrecommender.utils.models import (
    MetricRequestParameter,
    WorkloadDetails,
)
from hpaconfigrecommender.utils.config import (
    Config,
    USER_AGENT
)
from hpaconfigrecommender.utils.log import (
    log_exec_time
)

# Configure logging
logger = logging.getLogger(__name__)

def _build_workload_filter_query(
    config: Config,
    metric_param: MetricRequestParameter,
    workload_details: WorkloadDetails
) -> str:
    '''
    Build the Cloud Monitoring filter query.
    '''
    logger.debug(
        'Building filter query for metric: %s ',
        metric_param.metric
    )

    filter_conditions = [
        f'metric.type = "{metric_param.metric}"',
        'resource.type = "k8s_container"',
    ]

    def _add_filter_condition(label: str, value: str) -> None:

        if value.strip() and value.strip() != '':
            filter_conditions.append(f'{label} = "{value}"')

    if 'memory/used_bytes' in metric_param.metric.lower():
        filter_conditions.append('metric.label.memory_type = "non-evictable"')

    _add_filter_condition(
        'resource.labels.project_id', workload_details.project_id
    )
    _add_filter_condition('resource.labels.location', workload_details.location)
    _add_filter_condition(
        'resource.labels.cluster_name', workload_details.cluster_name
    )
    _add_filter_condition(
        'resource.labels.namespace_name', workload_details.namespace
    )
    _add_filter_condition(
        'metadata.system_labels.top_level_controller_name',
        workload_details.controller_name,
    )
    _add_filter_condition(
        'metadata.system_labels.top_level_controller_type',
        workload_details.controller_type,
    )
    _add_filter_condition(
        'resource.labels.container_name', workload_details.container_name
    )
    if config.get_value('EXCLUDED_NAMESPACES'):
        excluded_filter = ' AND '.join(
            f'NOT resource.labels.namespace_name = "{namespace}"'
            for namespace in config.get_value('EXCLUDED_NAMESPACES')
        )

        filter_conditions.append(excluded_filter)
    logger.debug('Filter query built: %s', ' AND '.join(filter_conditions))
    return ' AND '.join(filter_conditions)

async def _fetch_timeseries_data(
    config: Config,
    metric_param: MetricRequestParameter,
    workload_details: WorkloadDetails,
    start_datetime: datetime,
    end_datetime: datetime,
    alignment_period: int
) -> pd.DataFrame:
    '''
    Fetch time-series data for the specified workload_details and
    metric parameter.
    '''
    logger.info('Fetching time-series metric: %s', metric_param.metric)

    # Base URL for the Monitoring API
    base_url = f'https://monitoring.googleapis.com/v3/projects/{workload_details.project_id}/timeSeries'

    # Convert start and end datetime to UTC and ISO 8601 format
    utc_start_datetime = start_datetime.replace(second=0, microsecond=0).astimezone(pytz.UTC).isoformat()
    utc_end_datetime = end_datetime.replace(second=0, microsecond=0).astimezone(pytz.UTC).isoformat()

    filter_string = _build_workload_filter_query(config, metric_param, workload_details)

    # Query parameters
    params = {
        'aggregation.alignmentPeriod': f'{alignment_period}s',
        'aggregation.crossSeriesReducer': metric_param.cross_series_reducer,
        'aggregation.perSeriesAligner': metric_param.per_series_aligner,
        'aggregation.groupByFields': [
            'resource.labels.container_name',
            'resource.labels.pod_name',
        ],
        'filter': filter_string,
        'interval.startTime': utc_start_datetime,
        'interval.endTime': utc_end_datetime,
        'view': 'FULL',
    }

    # Obtain the access token using the default credentials
    credentials, _ = default()
    credentials.refresh(Request())
    access_token = credentials.token
    if not access_token:
        logger.error('Access token is empty or None!')
        return pd.DataFrame()

    # Authorization header
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': USER_AGENT
    }
    logger.debug('Sending request with headers: %s', headers)

    all_time_series = []

    # Make the requests using httpx and handle pagination
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(base_url, headers=headers, params=params)

            # Log request and response details
            logger.debug('Request URL: %s', response.request.url)
            logger.debug('Request Headers: %s', response.request.headers)
            logger.debug('Response Status: %s', response.status_code)

            if response.status_code == 200:
                logger.debug('Request successful: %s', response.url)
                data = response.json()
                all_time_series.extend(data.get('timeSeries', []))

                # Check for a nextPageToken
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break  # Exit loop if no more pages
                params['pageToken'] = next_page_token  # Update params for next request
            else:
                logger.error('Request failed: %s, Status: %s', response.url, response.status_code)
                raise httpx.HTTPStatusError(
                    f'API call failed with status {response.status_code}',
                    request=response.request,
                    response=response,
                )

    # Normalize the JSON to extract 'container_name' and 'points'
    if not all_time_series:
        logger.warning('No time-series data fetched for the specified parameters.')
        return pd.DataFrame()

    df = pd.json_normalize(
        all_time_series,
        record_path='points',
        meta=[
            ['resource', 'labels', 'container_name'],
            ['resource', 'labels', 'pod_name'],
        ],
        errors='ignore',
    )

    # Drop the 'interval.endTime' column
    df.drop(columns=['interval.endTime'], errors='ignore', inplace=True)

    # Convert to the original timezone
    target_timezone = start_datetime.tzinfo
    df['interval.startTime'] = pd.to_datetime(df['interval.startTime']).dt.tz_convert(target_timezone)

    # Rename 'interval.startTime' to 'window_begin'
    df.rename(columns={'interval.startTime': 'window_begin'}, inplace=True)

    # Adjust data types
    if 'value.int64Value' in df.columns:
        df['value.int64Value'] = df['value.int64Value'].astype('int32')
    if 'value.doubleValue' in df.columns:
        df['value.doubleValue'] = df['value.doubleValue'].astype('float32')
    df['resource.labels.container_name'] = df['resource.labels.container_name'].astype('category')
    df['resource.labels.pod_name'] = df['resource.labels.pod_name'].astype('category')

    return df


def _aggregate_data(merged_df: pd.DataFrame)-> pd.DataFrame:
    '''
    Aggregate and process container resource data.
    '''
    # Set Resource Request sums
    merged_df['sum_containers_cpu_request'] = (
        merged_df['avg_container_cpu_request']
        * merged_df['num_replicas_at_usage_window']
    )
    merged_df['sum_containers_mem_request_mi'] = (
        merged_df['avg_container_mem_request_mi']
        * merged_df['num_replicas_at_usage_window']
    )

    # Set Resource Usage sums
    merged_df['sum_containers_cpu_usage'] = (
        merged_df['avg_container_cpu_usage']
        * merged_df['num_replicas_at_usage_window']
    )
    merged_df['sum_containers_mem_usage_mi'] = (
        merged_df['max_containers_mem_usage_mi']
        * merged_df['num_replicas_at_usage_window']
    )

    # Convert aggregated values from bytes to MiB
    merged_df[
        [
            'avg_container_mem_request_mi',
            'avg_container_mem_usage_mi',
            'max_containers_mem_usage_mi',
            'sum_containers_mem_request_mi',
            'sum_containers_mem_usage_mi',
        ]
    ] /= (
        1024**2
    )

    # Ensure 'window_begin' is a datetime type and resample data
    if not pd.api.types.is_datetime64_any_dtype(merged_df['window_begin']):
        try:
            merged_df['window_begin'] = pd.to_datetime(
                merged_df['window_begin']
            )
        except ValueError as ve:
            logging.error(
                'ValueError converting window_begin to datetime: %s', ve
            )
            return pd.DataFrame()
        except TypeError as te:
            logging.error(
                'TypeError converting window_begin to datetime: %s', te
            )
            return pd.DataFrame()
    necessary_columns = [
        'window_begin',
        'num_replicas_at_usage_window',
        'avg_container_cpu_usage',
        'avg_container_mem_usage_mi',
        'max_containers_mem_usage_mi',
        'stddev_containers_cpu_usage',
        'sum_containers_cpu_request',
        'sum_containers_cpu_usage',
        'sum_containers_mem_request_mi',
        'sum_containers_mem_usage_mi'
    ]
    merged_df = merged_df[necessary_columns]
    return merged_df

def _get_latest_request_value(request_df, resource_type):
    '''
    Returns the latest request value from the DataFrame or 0.0 if the
    DataFrame is empty. Logs an appropriate message based on the resource type.
    '''
    if request_df.empty:
        logger.info(
            'No %s request data found; setting latest request to 0.0.',
            resource_type
        )
        return 0.0
    return request_df['value.doubleValue'].iloc[0]

@log_exec_time(logger)
def get_workload_agg_timeseries(
    config: Config,
    workload_details: WorkloadDetails,
    start_datetime: datetime,
    end_datetime: datetime
) -> pd.DataFrame:
    '''
    Retrieve and process GKE workload data, building a grouped DataFrame
    with CPU and memory usage and requests metrics.

    This function wraps the asynchronous logic into a synchronous interface.

    Args:
        config (Config): Run configurations.
        workload_details (WorkloadDetails): Details of the GKE workload
            query, including project, cluster, location, and controller details.
        start_datetime (datetime): The start time of the data query.
        end_datetime (datetime): The end time of the data query.

    Returns:
        pd.DataFrame: A DataFrame containing aggregated time-series data,
            including CPU and memory usage and request metrics. The DataFrame
            is resampled to 30-second intervals.
    '''

    async def _async_get_workload_agg_timeseries():
        '''
        Internal asynchronous function to fetch and process data.
        '''
        logger.info(
            'Getting aggregated time-series data for workload: %s',
            workload_details
        )
        # Validate workload details
        required_fields = [
            'project_id', 'location', 'cluster_name',
            'namespace', 'controller_name'
        ]
        missing_fields = [
            field for field in required_fields
            if not getattr(workload_details, field, '').strip()
        ]

        if missing_fields:
            logger.warning(
                'Missing workload details: %s. Cannot fetch time-series data.',
                ', '.join(missing_fields)
            )
            return pd.DataFrame()

        # Validate that start_datetime and end_datetime are datetime objects
        if not isinstance(start_datetime, datetime):
            logging.warning(
                'Invalid type for start_datetime: Expected datetime, got %s',
                type(start_datetime).__name__)
            return pd.DataFrame()

        if not isinstance(end_datetime, datetime):
            logging.warning('Invalid type for end_datetime: Expected datetime,'
                          'got %s', type(end_datetime).__name__)
            return pd.DataFrame()

        # Define required metrics
        required_metrics = [
            MetricRequestParameter(
                metric='kubernetes.io/container/memory/used_bytes',
                per_series_aligner='ALIGN_MAX',
                cross_series_reducer='REDUCE_MAX',
            ),
            MetricRequestParameter(
                metric='kubernetes.io/container/cpu/core_usage_time',
                per_series_aligner='ALIGN_RATE',
                cross_series_reducer='REDUCE_MEAN',
            )
        ]
        # Define optional request metrics (if missing, default to 0)
        optional_request_metrics = [
            MetricRequestParameter(
                metric='kubernetes.io/container/cpu/request_cores',
                per_series_aligner='ALIGN_MEAN',
                cross_series_reducer='REDUCE_MEAN',
                latest_value=True,
            ),
            MetricRequestParameter(
                metric='kubernetes.io/container/memory/request_bytes',
                per_series_aligner='ALIGN_MEAN',
                cross_series_reducer='REDUCE_MEAN',
                latest_value=True,
            )
        ]

        # Fetch time-series data for all required metrics
        metric_response_df = await asyncio.gather(
            *[
                _fetch_timeseries_data(
                    config,
                    metric_request,
                    workload_details,
                    start_datetime,
                    end_datetime,
                    config.DISTANCE_BETWEEN_POINTS_SECONDS
                )
                for metric_request in required_metrics
            ]
        )

        # Check if any required metric is missing
        missing_metrics = [
            required_metrics[i].metric for i, df in enumerate(
                metric_response_df) if df.empty
        ]
        # Define optional request metrics (if missing, default to 0)

        if missing_metrics:
            logger.warning(
                'Required metrics missing for workload: %s. '
                'The following metrics were not found: %s. '
                'This likely means the workload does not exist or is not '
                'reporting data.',
                workload_details,
                ', '.join(missing_metrics)
            )
            return pd.DataFrame()

        # Fetch optional request metrics
        optional_response_df = await asyncio.gather(
            *[
                _fetch_timeseries_data(
                    config,
                    metric_request,
                    workload_details,
                    start_datetime,
                    end_datetime,
                    config.DISTANCE_BETWEEN_POINTS_SECONDS
                )
                for metric_request in optional_request_metrics
            ]
        )

        # Assign request metrics (set default 0 if missing)
        cpu_request_df = optional_response_df[0]
        mem_request_df = optional_response_df[1]

        latest_cpu_request = (
            _get_latest_request_value(
                cpu_request_df, 'CPU') if not cpu_request_df.empty else 0.0
        )
        latest_mem_request = (
            _get_latest_request_value(
                mem_request_df, 'Memory') if not mem_request_df.empty else 0.0
        )

        logger.info(
            'CPU Request cores: %s, Memory Request bytes: %s',
            latest_cpu_request, latest_mem_request
        )

        # Process and aggregate data
        mem_usage_grouped = metric_response_df[0].groupby(
            ['window_begin', 'resource.labels.container_name'], observed=True
        ).agg(
            max_containers_mem_usage_mi=('value.int64Value','max'),
            avg_container_mem_usage_mi = ('value.int64Value','mean')
        ).reset_index()

        cpu_usage_grouped = metric_response_df[1].groupby(
            ['window_begin', 'resource.labels.container_name'], observed=True
        ).agg(
            avg_container_cpu_usage=('value.doubleValue', 'mean'),
            stddev_containers_cpu_usage=('value.doubleValue', 'std'),
            num_replicas_at_usage_window=('value.doubleValue', 'count')
        ).reset_index()
        # Ensure NaNs are replaced with 0 for std deviation
        cpu_usage_grouped['stddev_containers_cpu_usage'] = (
            cpu_usage_grouped['stddev_containers_cpu_usage'].replace(np.nan, 0)
        )

        merged_df = cpu_usage_grouped.merge(
            mem_usage_grouped,
            on=['window_begin', 'resource.labels.container_name'], how='inner'
        )

        # Assign request values to merged DataFrame
        merged_df['avg_container_cpu_request'] = latest_cpu_request
        merged_df['avg_container_mem_request_mi'] = latest_mem_request

        return _aggregate_data(merged_df)
    
    # Use asyncio.run to execute the internal async function
    return asyncio.run(_async_get_workload_agg_timeseries())
