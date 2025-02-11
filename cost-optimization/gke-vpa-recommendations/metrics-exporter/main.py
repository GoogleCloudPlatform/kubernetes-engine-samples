# Copyright 2023 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import time
import config
import asyncio
import logging
import utils
import warnings
from google.protobuf import descriptor_pb2
import bigquery_schema_pb2
from google.cloud import monitoring_v3
from google.cloud import bigquery_storage_v1
from google.cloud.bigquery_storage_v1 import types
from google.cloud.bigquery_storage_v1 import writer
from google.api_core.exceptions import GoogleAPICallError

warnings.filterwarnings(
    "ignore",
    "Your application has authenticated using end user credentials")


async def get_gke_metrics(metric_name, query, namespace, start_time, client):
    """
    Retrieves Google Kubernetes Engine (GKE) metrics.

    Parameters:
    metric_name (str): The name of the metric to retrieve.
    query: Query configuration for the metric.

    Returns:
    list: List of metrics.
    """
    interval = utils.get_interval(start_time, query.window)
    aggregation = utils.get_aggregation(query)
    project_name = utils.get_request_name()
    rows = []
    try:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'metric.type = "{query.metric}" AND resource.label.namespace_name = {namespace}',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation})

        logging.info(f"Building Row of metric results")

        for result in results:
            row = bigquery_schema_pb2.Record()
            label = result.resource.labels
            metadata = result.metadata.system_labels.fields
            metric_label = result.metric.labels

            if "hpa" in metric_name:
                controller_name = metric_label['targetref_name']
                controller_type = metric_label['targetref_kind']
                container_name = metric_label['container_name']
            elif "vpa" in metric_name:
                controller_name = label['controller_name']
                controller_type = label['controller_kind']
                container_name = metric_label['container_name']
            else:
                controller_name = metadata['top_level_controller_name'].string_value
                controller_type = metadata['top_level_controller_type'].string_value
                container_name = label['container_name']
            
            row.run_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))
            row.metric_name = metric_name
            row.project_id = label['project_id']
            row.location = label['location']
            row.cluster_name = label['cluster_name']
            row.namespace_name = label['namespace_name']
            row.controller_name = controller_name
            row.controller_type = controller_type
            row.container_name = container_name
            points = []
            for point in result.points:
                new_point = row.points_array.add()
                new_point.metric_timestamp = point.interval.start_time.strftime('%Y-%m-%d %H:%M:%S.%f')
                new_point.metric_value = point.value.double_value or float(point.value.int64_value)
            rows.append(row.SerializeToString())
    except GoogleAPICallError as error:
        logging.info(f'Google API call error: {error}')
    except Exception as error:
        logging.info(f'Unexpected error: {error}')
    return rows


async def write_to_bigquery(write_client, rows):       
    parent = write_client.table_path(config.PROJECT_ID, config.BIGQUERY_DATASET, config.BIGQUERY_TABLE)
    write_stream = types.WriteStream()
    write_stream.type_ = types.WriteStream.Type.PENDING
    write_stream = write_client.create_write_stream(
        parent=parent, write_stream=write_stream
    )
    stream_name = write_stream.name

    # Create a template with fields needed for the first request.
    request_template = types.AppendRowsRequest()

    # The initial request must contain the stream name.
    request_template.write_stream = stream_name

    # So that BigQuery knows how to parse the serialized_rows, generate a
    # protocol buffer representation of your message descriptor.
    proto_schema = types.ProtoSchema()
    proto_descriptor = descriptor_pb2.DescriptorProto()
    bigquery_schema_pb2.Record.DESCRIPTOR.CopyToProto(proto_descriptor)
    proto_schema.proto_descriptor = proto_descriptor
    proto_data = types.AppendRowsRequest.ProtoData()
    proto_data.writer_schema = proto_schema
    request_template.proto_rows = proto_data
    
    # Some stream types support an unbounded number of requests. Construct an
    # AppendRowsStream to send an arbitrary number of requests to a stream.
    append_rows_stream = writer.AppendRowsStream(write_client, request_template)

    # Create a batch of row data by appending proto2 serialized bytes to the
    # serialized_rows repeated field.
    proto_rows = types.ProtoRows()
    for row in rows:
        proto_rows.serialized_rows.append(row)
    request = types.AppendRowsRequest()
    request.offset = 0
    proto_data = types.AppendRowsRequest.ProtoData()
    proto_data.rows = proto_rows
    request.proto_rows = proto_data

    append_rows_stream.send(request)

    # Shutdown background threads and close the streaming connection.
    append_rows_stream.close()

    # A PENDING type stream must be "finalized" before being committed. No new
    # records can be written to the stream after this method has been called.
    write_client.finalize_write_stream(name=write_stream.name)

    # Commit the stream you created earlier.
    batch_commit_write_streams_request = types.BatchCommitWriteStreamsRequest()
    batch_commit_write_streams_request.parent = parent
    batch_commit_write_streams_request.write_streams = [write_stream.name]
    write_client.batch_commit_write_streams(batch_commit_write_streams_request)

    logging.info(f"Writes to stream: '{write_stream.name}' have been committed.")

async def run_pipeline(namespace, client, bqclient, start_time):
    for metric, query in config.MQL_QUERY.items():
        logging.info(f'Retrieving {metric} for namespace {namespace}...')
        rows_to_insert = await get_gke_metrics(metric, query, namespace, start_time, client)
        if rows_to_insert:
            await write_to_bigquery(bqclient, rows_to_insert)
        else:
            logging.info(f'{metric} unavailable. Skip')

    logging.info("Run Completed")

def get_namespaces(client, start_time):
    namespaces = set()
    query = config.NS_QUERY

    interval = utils.get_interval(start_time, query.window)
    aggregation = utils.get_aggregation(query)
    project_name = utils.get_request_name()

    try:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": f'metric.type = "{query.metric}" AND {config.namespace_filter}',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.HEADERS,
                "aggregation": aggregation})

        logging.info("Building Row of Namespace results")
        for result in results:
            label = result.resource.labels
            namespaces.add(label['namespace_name'])
        return list(namespaces)

    except GoogleAPICallError as error:
        logging.error(f'Google API call error: {error}')
    except Exception as error:
        logging.error(f'Unexpected error: {error}')
    return list(namespaces)


if __name__ == "__main__":
    utils.setup_logging()
    start_time = time.time()

    try:
        client = monitoring_v3.MetricServiceClient()
        bqclient = bigquery_storage_v1.BigQueryWriteClient()

    except Exception as error:
        logging.error(f'Google client connection error: {error}')   
    monitor_namespaces = get_namespaces(client, start_time)
    namespace_count = len(monitor_namespaces)

    logging.debug(f"Discovered {namespace_count} namespaces to query")
    if (namespace_count > 0):
        for namespace in monitor_namespaces:
            asyncio.run(
                run_pipeline(
                    namespace,
                    client=client,
                    bqclient=bqclient,
                    start_time=start_time))
    else:
        logging.error("Monitored Namespace list is zero size, end Job")
