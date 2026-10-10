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
import json
import time
import threading
import collections
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


# ORCA custom metrics tracking
_last_cgroup_cpu = None
_last_cgroup_timestamp = 0.0
_last_cpu_times = None
_last_cpu_utilization = 0.0
_orca_lock = threading.Lock()
_request_timestamps = collections.deque()
_error_timestamps = collections.deque()
_RATE_WINDOW_SECONDS = 10.0
_MIN_SAMPLE_INTERVAL = 1.0  # minimum seconds between CPU measurements


def _get_cgroup_dir():
    """Finds the cgroup directory for the current process."""
    try:
        with open('/proc/self/cgroup', 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3:
                    cgroup_path = parts[2].lstrip('/')
                    p = os.path.join('/sys/fs/cgroup', cgroup_path)
                    if os.path.exists(p):
                        return p
    except Exception:
        pass
    return '/sys/fs/cgroup'


def _read_cgroup_cpu():
    """Reads container CPU usage in seconds and quota in cores from cgroups."""
    cdir = _get_cgroup_dir()
    # cgroup v2
    cpu_stat = os.path.join(cdir, 'cpu.stat')
    if os.path.exists(cpu_stat):
        usage_usec = None
        with open(cpu_stat, 'r') as f:
            for line in f:
                if line.startswith('usage_usec'):
                    usage_usec = float(line.split()[1])
                    break
        quota_cpus = None
        cpu_max = os.path.join(cdir, 'cpu.max')
        if os.path.exists(cpu_max):
            with open(cpu_max, 'r') as f:
                parts = f.read().strip().split()
                if len(parts) == 2 and parts[0] != 'max':
                    quota_cpus = float(parts[0]) / float(parts[1])
        if quota_cpus is None:
            quota_cpus = float(os.cpu_count() or 1)
        if usage_usec is not None:
            return usage_usec / 1e6, quota_cpus

    # cgroup v1
    v1_usage = os.path.join(cdir, 'cpuacct.usage')
    if not os.path.exists(v1_usage):
        v1_usage = '/sys/fs/cgroup/cpuacct/cpuacct.usage'
    if os.path.exists(v1_usage):
        with open(v1_usage, 'r') as f:
            usage_sec = float(f.read().strip()) / 1e9
        quota_cpus = None
        v1_quota = os.path.join(cdir, 'cpu.cfs_quota_us')
        v1_period = os.path.join(cdir, 'cpu.cfs_period_us')
        if os.path.exists(v1_quota) and os.path.exists(v1_period):
            with open(v1_quota, 'r') as fq, open(v1_period, 'r') as fp:
                q = float(fq.read().strip())
                p = float(fp.read().strip())
                if q > 0 and p > 0:
                    quota_cpus = q / p
        if quota_cpus is None:
            quota_cpus = float(os.cpu_count() or 1)
        return usage_sec, quota_cpus

    return None, None


def _read_cpu_times():
    """Reads /proc/stat to get total and idle CPU times."""
    try:
        with open('/proc/stat', 'r') as f:
            fields = [float(x) for x in f.readline().strip().split()[1:]]
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
            total = sum(fields)
            return total, idle
    except Exception:
        return None, None


def get_cpu_utilization():
    """Captures CPU utilization using cgroup stats scaled by container CPU limit."""
    global _last_cgroup_cpu, _last_cgroup_timestamp, _last_cpu_times, _last_cpu_utilization
    now = time.time()
    with _orca_lock:
        usage_sec, quota_cpus = _read_cgroup_cpu()
        if usage_sec is not None and quota_cpus is not None:
            if _last_cgroup_cpu is not None:
                prev_usage, _ = _last_cgroup_cpu
                elapsed_time = now - _last_cgroup_timestamp
                # Only recompute if minimum interval elapsed to avoid microsecond quantization
                if elapsed_time >= _MIN_SAMPLE_INTERVAL:
                    delta_usage = usage_sec - prev_usage
                    if delta_usage >= 0 and elapsed_time > 0 and quota_cpus > 0:
                        _last_cpu_utilization = max(0.0, delta_usage / (elapsed_time * quota_cpus))
                    _last_cgroup_cpu = (usage_sec, quota_cpus)
                    _last_cgroup_timestamp = now
            else:
                _last_cgroup_cpu = (usage_sec, quota_cpus)
                _last_cgroup_timestamp = now
            return round(_last_cpu_utilization, 4)
        else:
            # Fallback to /proc/stat or load average
            total, idle = _read_cpu_times()
            if total is not None and idle is not None:
                if _last_cpu_times is not None:
                    prev_total, prev_idle = _last_cpu_times
                    delta_total = total - prev_total
                    delta_idle = idle - prev_idle
                    if delta_total > 0:
                        _last_cpu_utilization = max(0.0, (delta_total - delta_idle) / delta_total)
                _last_cpu_times = (total, idle)
                return round(_last_cpu_utilization, 4)
            else:
                try:
                    load1 = os.getloadavg()[0]
                    cpu_count = os.cpu_count() or 1
                    return round(max(0.0, min(1.0, load1 / cpu_count)), 4)
                except Exception:
                    return 0.0


def get_memory_utilization():
    """Captures memory utilization as a float between 0.0 and 1.0."""
    cdir = _get_cgroup_dir()
    # Check cgroup v2
    try:
        mem_curr = os.path.join(cdir, 'memory.current')
        mem_max = os.path.join(cdir, 'memory.max')
        if os.path.exists(mem_curr) and os.path.exists(mem_max):
            with open(mem_curr, 'r') as f:
                usage = float(f.read().strip())
            with open(mem_max, 'r') as f:
                max_str = f.read().strip()
                if max_str != 'max':
                    limit = float(max_str)
                    if limit > 0:
                        return round(max(0.0, min(1.0, usage / limit)), 4)
    except Exception:
        pass

    # Check cgroup v1
    try:
        mem_usage = os.path.join(cdir, 'memory.usage_in_bytes')
        mem_limit = os.path.join(cdir, 'memory.limit_in_bytes')
        if not os.path.exists(mem_usage):
            mem_usage = '/sys/fs/cgroup/memory/memory.usage_in_bytes'
            mem_limit = '/sys/fs/cgroup/memory/memory.limit_in_bytes'
        if os.path.exists(mem_usage) and os.path.exists(mem_limit):
            with open(mem_usage, 'r') as f:
                usage = float(f.read().strip())
            with open(mem_limit, 'r') as f:
                limit = float(f.read().strip())
                if 0 < limit < (1 << 60):
                    return round(max(0.0, min(1.0, usage / limit)), 4)
    except Exception:
        pass

    # Fallback to /proc/meminfo
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = float(parts[1].split()[0])
            total = meminfo.get('MemTotal', 1.0)
            avail = meminfo.get('MemAvailable', meminfo.get('MemFree', 0.0))
            return round(max(0.0, min(1.0, (total - avail) / total)), 4)
    except Exception:
        return 0.0


def _record_request_and_get_rates(is_error=False):
    """Calculates rps_fractional and eps over a sliding time window."""
    now = time.time()
    with _orca_lock:
        _request_timestamps.append(now)
        if is_error:
            _error_timestamps.append(now)

        cutoff = now - _RATE_WINDOW_SECONDS
        while _request_timestamps and _request_timestamps[0] < cutoff:
            _request_timestamps.popleft()
        while _error_timestamps and _error_timestamps[0] < cutoff:
            _error_timestamps.popleft()

        rps = round(len(_request_timestamps) / _RATE_WINDOW_SECONDS, 4)
        eps = round(len(_error_timestamps) / _RATE_WINDOW_SECONDS, 4)
        return rps, eps


# Initialize CPU baseline measurement
_init_cgroup = _read_cgroup_cpu()
if _init_cgroup[0] is not None:
    _last_cgroup_cpu = _init_cgroup
    _last_cgroup_timestamp = time.time()
else:
    _last_cpu_times = _read_cpu_times()


@app.after_request
def add_orca_headers(response):
    if os.getenv('ENABLE_ORCA_HEADERS') == 'True':
        is_error = response.status_code >= 500
        rps, eps = _record_request_and_get_rates(is_error=is_error)
        cpu_util = get_cpu_utilization()
        mem_util = get_memory_utilization()
        orca_metrics = {
            'cpu_utilization': cpu_util,
            'mem_utilization': mem_util,
            'application_utilization': cpu_util,
            'rps_fractional': rps,
            'eps': eps,
        }
        response.headers['endpoint-load-metrics-json'] = f"JSON {json.dumps(orca_metrics)}"
    return response


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
