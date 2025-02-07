/*
Copyright 2024 Google LLC.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Prometheus Dummy Exporter is a testing utility that exposes a prometheus format metric of constant value.
// The metric is exposed at a port that can be configured with flag 'port'
// Metric name and value can be specified with flags 'metric-name' and 'metric-value'.
func main() {
	metricName := flag.String("metric-name", "foo", "custom metric name")
	metricValue := flag.Int64("metric-value", 0, "custom metric value")
	port := flag.Int64("port", 8080, "port to expose metrics on")
	flag.Parse()

	// [START gke_custom_metrics_prometheus_exporter]
	// [START container_custom_metrics_prometheus_exporter]
	metric := prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: *metricName,
			Help: "Custom metric",
		},
	)
	prometheus.MustRegister(metric)
	metric.Set(float64(*metricValue))

	http.Handle("/metrics", promhttp.Handler())
	log.Printf("Starting to listen on :%d", *port)
	err := http.ListenAndServe(fmt.Sprintf(":%d", *port), nil)
	// [END container_custom_metrics_prometheus_exporter]
	// [END gke_custom_metrics_prometheus_exporter]
	log.Fatal("Failed to start serving metrics: %v", err)
}
