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


# ORCA custom metrics tracking (optimized: static cgroup discovery, decoupled background sampling, sliding window rates)
class SlidingRateTracker:
    """Calculates rps_fractional and eps using a fixed-size 10-second sliding bucket ring buffer."""
    def __init__(self, window_seconds=10):
        self.window_seconds = int(window_seconds)
        self.buckets = [[0, 0, 0] for _ in range(self.window_seconds)]
        self.lock = threading.Lock()

    def record_and_get_rates(self, is_error=False):
        now = time.time()
        current_sec = int(now)
        idx = current_sec % self.window_seconds
        with self.lock:
            bucket = self.buckets[idx]
            if bucket[0] == current_sec:
                bucket[1] += 1
                if is_error:
                    bucket[2] += 1
            else:
                bucket[0] = current_sec
                bucket[1] = 1
                bucket[2] = 1 if is_error else 0

            min_sec = current_sec - self.window_seconds
            total_reqs = 0
            total_errs = 0
            for sec, reqs, errs in self.buckets:
                if min_sec < sec <= current_sec:
                    total_reqs += reqs
                    total_errs += errs

        return round(total_reqs / self.window_seconds, 4), round(total_errs / self.window_seconds, 4)


class OrcaMetricsTracker:
    """Manages container metrics polling decoupled from the HTTP request path."""
    def __init__(self):
        self.rate_tracker = SlidingRateTracker(10)
        self.cpu_utilization = 0.0
        self.mem_utilization = 0.0
        self.lock = threading.Lock()
        self._thread = None
        self._started = False

        self._cgroup_mode = None
        self._cpu_usage_path = None
        self._cpu_quota_cpus = float(os.cpu_count() or 1)
        self._mem_usage_path = None
        self._mem_limit_bytes = None

        self._last_cpu_usage = None
        self._last_cpu_timestamp = 0.0
        self._last_proc_cpu = None

        self._discover_cgroups()
        self._sample()

    def _discover_cgroups(self):
        cdir = None
        try:
            with open('/proc/self/cgroup', 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) == 3:
                        p = os.path.join('/sys/fs/cgroup', parts[2].lstrip('/'))
                        if os.path.exists(p):
                            cdir = p
                            break
        except Exception:
            pass
        if not cdir or not os.path.exists(cdir):
            cdir = '/sys/fs/cgroup'

        # Check cgroup v2
        v2_cpu_stat = os.path.join(cdir, 'cpu.stat')
        if os.path.exists(v2_cpu_stat):
            self._cgroup_mode = 'v2'
            self._cpu_usage_path = v2_cpu_stat
            cpu_max = os.path.join(cdir, 'cpu.max')
            if os.path.exists(cpu_max):
                try:
                    with open(cpu_max, 'r') as f:
                        parts = f.read().strip().split()
                        if len(parts) == 2 and parts[0] != 'max':
                            q, p = float(parts[0]), float(parts[1])
                            if q > 0 and p > 0:
                                self._cpu_quota_cpus = q / p
                except Exception:
                    pass

            v2_mem_curr = os.path.join(cdir, 'memory.current')
            if os.path.exists(v2_mem_curr):
                self._mem_usage_path = v2_mem_curr
                v2_mem_max = os.path.join(cdir, 'memory.max')
                if os.path.exists(v2_mem_max):
                    try:
                        with open(v2_mem_max, 'r') as f:
                            m_str = f.read().strip()
                            if m_str != 'max':
                                m_val = float(m_str)
                                if m_val > 0:
                                    self._mem_limit_bytes = m_val
                    except Exception:
                        pass
            return

        # Check cgroup v1
        v1_cpuacct = os.path.join(cdir, 'cpuacct.usage')
        if not os.path.exists(v1_cpuacct):
            v1_cpuacct = '/sys/fs/cgroup/cpuacct/cpuacct.usage'
        if os.path.exists(v1_cpuacct):
            self._cgroup_mode = 'v1'
            self._cpu_usage_path = v1_cpuacct
            v1_quota = os.path.join(cdir, 'cpu.cfs_quota_us')
            v1_period = os.path.join(cdir, 'cpu.cfs_period_us')
            if os.path.exists(v1_quota) and os.path.exists(v1_period):
                try:
                    with open(v1_quota, 'r') as fq, open(v1_period, 'r') as fp:
                        q = float(fq.read().strip())
                        p = float(fp.read().strip())
                        if q > 0 and p > 0:
                            self._cpu_quota_cpus = q / p
                except Exception:
                    pass

            v1_mem_usage = os.path.join(cdir, 'memory.usage_in_bytes')
            if not os.path.exists(v1_mem_usage):
                v1_mem_usage = '/sys/fs/cgroup/memory/memory.usage_in_bytes'
            if os.path.exists(v1_mem_usage):
                self._mem_usage_path = v1_mem_usage
                v1_mem_limit = os.path.join(cdir, 'memory.limit_in_bytes')
                if not os.path.exists(v1_mem_limit):
                    v1_mem_limit = '/sys/fs/cgroup/memory/memory.limit_in_bytes'
                if os.path.exists(v1_mem_limit):
                    try:
                        with open(v1_mem_limit, 'r') as f:
                            lim = float(f.read().strip())
                            if 0 < lim < (1 << 60):
                                self._mem_limit_bytes = lim
                    except Exception:
                        pass
            return

        # Fallback to host procfs
        self._cgroup_mode = 'proc'

    def _read_cpu_usage(self):
        if self._cgroup_mode == 'v2' and self._cpu_usage_path:
            try:
                with open(self._cpu_usage_path, 'r') as f:
                    for line in f:
                        if line.startswith('usage_usec'):
                            return float(line.split()[1]) / 1e6
            except Exception:
                pass
        elif self._cgroup_mode == 'v1' and self._cpu_usage_path:
            try:
                with open(self._cpu_usage_path, 'r') as f:
                    return float(f.read().strip()) / 1e9
            except Exception:
                pass
        return None

    def _read_mem_utilization(self):
        if self._mem_usage_path and self._mem_limit_bytes:
            try:
                with open(self._mem_usage_path, 'r') as f:
                    usage = float(f.read().strip())
                    return max(0.0, min(1.0, usage / self._mem_limit_bytes))
            except Exception:
                pass

        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = float(parts[1].split()[0])
                total = meminfo.get('MemTotal', 1.0)
                avail = meminfo.get('MemAvailable', meminfo.get('MemFree', 0.0))
                return max(0.0, min(1.0, (total - avail) / total))
        except Exception:
            return 0.0

    def _sample(self):
        now = time.time()
        usage_sec = self._read_cpu_usage()
        if usage_sec is not None:
            if self._last_cpu_usage is not None:
                elapsed = now - self._last_cpu_timestamp
                if elapsed > 0:
                    delta_usage = usage_sec - self._last_cpu_usage
                    if delta_usage >= 0 and self._cpu_quota_cpus > 0:
                        self.cpu_utilization = round(max(0.0, delta_usage / (elapsed * self._cpu_quota_cpus)), 4)
            self._last_cpu_usage = usage_sec
            self._last_cpu_timestamp = now
        else:
            try:
                with open('/proc/stat', 'r') as f:
                    fields = [float(x) for x in f.readline().strip().split()[1:]]
                    idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
                    total = sum(fields)
                if self._last_proc_cpu is not None:
                    prev_total, prev_idle = self._last_proc_cpu
                    delta_total = total - prev_total
                    delta_idle = idle - prev_idle
                    if delta_total > 0:
                        self.cpu_utilization = round(max(0.0, (delta_total - delta_idle) / delta_total), 4)
                self._last_proc_cpu = (total, idle)
            except Exception:
                try:
                    load1 = os.getloadavg()[0]
                    self.cpu_utilization = round(max(0.0, min(1.0, load1 / self._cpu_quota_cpus)), 4)
                except Exception:
                    self.cpu_utilization = 0.0

        self.mem_utilization = round(self._read_mem_utilization(), 4)

    def start_background_sampler(self):
        with self.lock:
            if self._started:
                return
            self._started = True

            def _loop():
                while True:
                    time.sleep(1.0)
                    try:
                        self._sample()
                    except Exception:
                        pass

            self._thread = threading.Thread(target=_loop, daemon=True)
            self._thread.start()


_orca_tracker = OrcaMetricsTracker()


def get_cpu_utilization():
    return _orca_tracker.cpu_utilization


def get_memory_utilization():
    return _orca_tracker.mem_utilization


def _record_request_and_get_rates(is_error=False):
    return _orca_tracker.rate_tracker.record_and_get_rates(is_error=is_error)


# Automatically start background sampler if enabled at process launch
if os.getenv('ENABLE_ORCA_HEADERS') == 'True':
    _orca_tracker.start_background_sampler()


@app.after_request
def add_orca_headers(response):
    if os.getenv('ENABLE_ORCA_HEADERS') == 'True':
        _orca_tracker.start_background_sampler()
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
