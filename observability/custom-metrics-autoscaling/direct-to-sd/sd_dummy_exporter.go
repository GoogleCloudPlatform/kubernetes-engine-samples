/*
Copyright 2018 Google Inc

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
	"strings"
	"time"

	gce "cloud.google.com/go/compute/metadata"
	monitoring "cloud.google.com/go/monitoring/apiv3/v2"
	"cloud.google.com/go/monitoring/apiv3/v2/monitoringpb"
	"golang.org/x/net/context"
	"google.golang.org/genproto/googleapis/api/metric"
	"google.golang.org/genproto/googleapis/api/monitoredres"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// SD Dummy Exporter is a testing utility that exports a metric of constant value to Stackdriver
// in a loop. Metric name and value can be specified with flags 'metric-name' and 'metric-value'.
// SD Dummy Exporter assumes that it runs as a pod in GCE or GKE cluster, and the pod id, pod name
// and namespace are passed to it with 'pod-id', 'pod-name' and 'namespace' flags.
// Pod ID and pod name can be passed to a pod via Downward API.
func main() {
	// Gather pod information
	podId := flag.String("pod-id", "", "pod id")
	namespace := flag.String("namespace", "", "namespace")
	podName := flag.String("pod-name", "", "pod name")
	metricName := flag.String("metric-name", "foo", "custom metric name")
	metricValue := flag.Int64("metric-value", 0, "custom metric value")
	metricLabelsArg := flag.String("metric-labels", "bar=1", "custom metric labels")
	// Whether to use old Stackdriver resource model - use monitored resource "gke_container"
	// For old resource model, podId flag has to be set.
	useOldResourceModel := flag.Bool("use-old-resource-model", true, "use old stackdriver resource model")
	// Whether to use new Stackdriver resource model - use monitored resource "k8s_pod"
	// For new resource model, podName and namespace flags have to be set.
	useNewResourceModel := flag.Bool("use-new-resource-model", false, "use new stackdriver resource model")
	flag.Parse()

	if *podId == "" && *useOldResourceModel {
		log.Fatalf("No pod id specified.")
	}

	if *podName == "" && *useNewResourceModel {
		log.Fatalf("No pod name specified.")
	}

	if *namespace == "" && *useNewResourceModel {
		log.Fatalf("No pod namespace specified.")
	}

	stackdriverService, err := getStackDriverService()
	if err != nil {
		log.Fatalf("Error getting Stackdriver service: %v", err)
	}

	metricLabels := make(map[string]string)
	for _, label := range strings.Split(*metricLabelsArg, ",") {
		labelParts := strings.Split(label, "=")
		metricLabels[labelParts[0]] = labelParts[1]
	}

	oldModelLabels := getResourceLabelsForOldModel(*podId)
	newModelLabels := getResourceLabelsForNewModel(*namespace, *podName)
	for {
		if *useOldResourceModel {
			err := exportMetric(stackdriverService, *metricName, *metricValue, metricLabels, "gke_container", oldModelLabels)
			if err != nil {
				log.Printf("Failed to write time series data for old resource model: %v\n", err)
			} else {
				log.Printf("Finished writing time series for new resource model with value: %v\n", metricValue)
			}
		}
		if *useNewResourceModel {
			err := exportMetric(stackdriverService, *metricName, *metricValue, metricLabels, "k8s_pod", newModelLabels)
			if err != nil {
				log.Printf("Failed to write time series data for new resource model: %v\n", err)
			} else {
				log.Printf("Finished writing time series for new resource model with value: %v\n", metricValue)
			}
		}
		time.Sleep(5000 * time.Millisecond)
	}
}

func getStackDriverService() (*monitoring.MetricClient, error) {
	return monitoring.NewMetricClient(context.Background())
}

// getResourceLabelsForOldModel returns resource labels needed to correctly label metric data
// exported to StackDriver. Labels contain details on the cluster (project id, name)
// and pod for which the metric is exported (zone, id).
func getResourceLabelsForOldModel(podId string) map[string]string {
	projectId, _ := gce.ProjectID()
	zone, _ := gce.Zone()
	clusterName, _ := gce.InstanceAttributeValue("cluster-name")
	clusterName = strings.TrimSpace(clusterName)
	return map[string]string{
		"project_id":   projectId,
		"zone":         zone,
		"cluster_name": clusterName,
		// container name doesn't matter here, because the metric is exported for
		// the pod, not the container
		"container_name": "",
		"pod_id":         podId,
		// namespace_id and instance_id don't matter
		"namespace_id": "default",
		"instance_id":  "",
	}
}

// getResourceLabelsForNewModel returns resource labels needed to correctly label metric data
// exported to StackDriver. Labels contain details on the cluster (project id, location, name)
// and pod for which the metric is exported (namespace, name).
func getResourceLabelsForNewModel(namespace, name string) map[string]string {
	projectId, _ := gce.ProjectID()
	location, _ := gce.InstanceAttributeValue("cluster-location")
	location = strings.TrimSpace(location)
	clusterName, _ := gce.InstanceAttributeValue("cluster-name")
	clusterName = strings.TrimSpace(clusterName)
	return map[string]string{
		"project_id":     projectId,
		"location":       location,
		"cluster_name":   clusterName,
		"namespace_name": namespace,
		"pod_name":       name,
	}
}

// [START gke_custom_metrics_direct_exporter]
// [START container_custom_metrics_direct_exporter]
func exportMetric(client *monitoring.MetricClient, metricName string,
	metricValue int64, metricLabels map[string]string, monitoredResource string, resourceLabels map[string]string) error {
	dataPoint := &monitoringpb.Point{
		Interval: &monitoringpb.TimeInterval{
			EndTime: timestamppb.New(time.Now()),
		},
		Value: &monitoringpb.TypedValue{
			Value: &monitoringpb.TypedValue_Int64Value{Int64Value: metricValue},
		},
	}
	// Write time series data.
	projectName := fmt.Sprintf("projects/%s", resourceLabels["project_id"])
	request := &monitoringpb.CreateTimeSeriesRequest{
		Name: projectName,
		TimeSeries: []*monitoringpb.TimeSeries{
			{
				Metric: &metric.Metric{
					Type:   "custom.googleapis.com/" + metricName,
					Labels: metricLabels,
				},
				Resource: &monitoredres.MonitoredResource{
					Type:   monitoredResource,
					Labels: resourceLabels,
				},
				Points: []*monitoringpb.Point{
					dataPoint,
				},
			},
		},
	}
	err := client.CreateTimeSeries(context.Background(), request)
	return err
}

// [END container_custom_metrics_direct_exporter]
// [END gke_custom_metrics_direct_exporter]
