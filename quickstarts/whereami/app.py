# Copyright 2021 Google LLC
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

from flask import Flask, request, Response, jsonify
import logging
from logging.config import dictConfig
import sys
import os
from flask_cors import CORS
import whereami_payload
# gRPC stuff
from concurrent import futures
import multiprocessing
import grpc
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc
# whereami protobufs
import whereami_pb2
import whereami_pb2_grpc
# Prometheus export setup
from prometheus_flask_exporter import PrometheusMetrics
from py_grpc_prometheus.prometheus_server_interceptor import PromServerInterceptor
from prometheus_client import start_http_server
# OpenTelemetry setup
os.environ["OTEL_PYTHON_FLASK_EXCLUDED_URLS"] = "healthz,metrics"  # set exclusions
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.propagators.cloud_trace_propagator import (
    CloudTraceFormatPropagator,
)
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# set up logging
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://sys.stdout',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

# get host IP
host_ip = os.getenv("HOST", "0.0.0.0") # in absence of env var, default to 0.0.0.0 (IPv4)

# check to see if tracing enabled and sampling probability
trace_sampling_ratio = 0  # default to not sampling if absence of environment var
if os.getenv("TRACE_SAMPLING_RATIO"):

    try:
        trace_sampling_ratio = float(os.getenv("TRACE_SAMPLING_RATIO"))
    except:
        logging.warning("Invalid trace ratio provided.")  # invalid value? just keep at 0%

# if tracing is desired, set up trace provider / exporter
if trace_sampling_ratio > 0:
    logging.info("Attempting to enable tracing.")

    sampler = TraceIdRatioBased(trace_sampling_ratio)

    # OTEL setup
    set_global_textmap(CloudTraceFormatPropagator())

    tracer_provider = TracerProvider(sampler=sampler)
    cloud_trace_exporter = CloudTraceSpanExporter()
    tracer_provider.add_span_processor(
        # BatchSpanProcessor buffers spans and sends them in batches in a
        # background thread. The default parameters are sensible, but can be
        # tweaked to optimize your performance
        BatchSpanProcessor(cloud_trace_exporter)
    )
    trace.set_tracer_provider(tracer_provider)

    tracer = trace.get_tracer(__name__)
    logging.info("Tracing enabled.")

else:
    logging.info("Tracing disabled.")

# flask setup
app = Flask(__name__)
handler = logging.StreamHandler(sys.stdout)
app.logger.addHandler(handler)
#app.logger.propagate = True
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()  # enable tracing for Requests
app.config['JSON_AS_ASCII'] = False  # otherwise our emojis get hosed
CORS(app)  # enable CORS
metrics = PrometheusMetrics(app)  # enable Prom metrics

# gRPC setup
grpc_serving_port = int(os.environ.get('PORT', 9090)) # configurable via `PORT` but default to 9090
grpc_metrics_port = 8000  # prometheus /metrics

# define Whereami object
whereami_payload = whereami_payload.WhereamiPayload()


# create gRPC class
class WhereamigRPC(whereami_pb2_grpc.WhereamiServicer):

    def GetPayload(self, request, context):
        payload = whereami_payload.build_payload(None)
        return whereami_pb2.WhereamiReply(**payload)

# Custom gRPC server interceptor for request logging
class RequestLoggingInterceptor(grpc.ServerInterceptor):
    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)

        # This interceptor only supports unary-unary RPCs
        if not handler or not handler.unary_unary:
            return handler

        def logging_wrapper(request, context):
            if handler_call_details.method != f'/{health.SERVICE_NAME}/Check':
                self._logger.info(
                    f"gRPC request received: Method='{handler_call_details.method}', Peer='{context.peer()}'")
            return handler.unary_unary(request, context)

        return grpc.unary_unary_rpc_method_handler(
            logging_wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer)


# if selected will serve gRPC endpoint on port 9090
# see https://github.com/grpc/grpc/blob/master/examples/python/xds/server.py
# for reference on code below
def grpc_serve():
    # the +5 you see below re: max_workers is a hack to avoid thread starvation
    # working on a proper workaround
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()+5),
        interceptors=(PromServerInterceptor(), RequestLoggingInterceptor(),))  # interceptor for metrics and logging

    # Add the application servicer to the server.
    whereami_pb2_grpc.add_WhereamiServicer_to_server(WhereamigRPC(), server)

    # Create a health check servicer. We use the non-blocking implementation
    # to avoid thread starvation.
    health_servicer = health.HealthServicer(
        experimental_non_blocking=True,
        experimental_thread_pool=futures.ThreadPoolExecutor(max_workers=1))
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Create a tuple of all of the services we want to export via reflection.
    services = tuple(
        service.full_name
        for service in whereami_pb2.DESCRIPTOR.services_by_name.values()) + (
            reflection.SERVICE_NAME, health.SERVICE_NAME)

    # Start an end point to expose metrics at host:$grpc_metrics_port/metrics
    start_http_server(port=grpc_metrics_port)  # starts a flask server for metrics

    # Add the reflection service to the server.
    reflection.enable_server_reflection(services, server)
    server.add_insecure_port(host_ip + ':' + str(grpc_serving_port))
    server.start()

    # Mark all services as healthy.
    overall_server_health = ""
    for service in services + (overall_server_health,):
        health_servicer.set(service, health_pb2.HealthCheckResponse.SERVING)

    # Park the main application thread.
    server.wait_for_termination()


# HTTP heathcheck
@app.route('/healthz')  # healthcheck endpoint
@metrics.do_not_track()  # exclude from prom metrics
def i_am_healthy():
    return ('OK')


# default HTTP service
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def home(path):

    payload = whereami_payload.build_payload(request.headers)

    # split the path to see if user wants to read a specific field
    requested_value = path.split('/')[-1]
    if requested_value in payload.keys():

        return payload[requested_value]

    return jsonify(payload)

if __name__ == '__main__':

    # decision point - HTTP or gRPC?
    if os.getenv('GRPC_ENABLED') == "True":
        logging.info('gRPC server listening on port %s'%(grpc_serving_port))
        grpc_serve()

    else:
        app.run(
            host=host_ip.strip('[]'), # stripping out the brackets if present
            port=int(os.environ.get('PORT', 8080)),
            #debug=True,
            threaded=True)
