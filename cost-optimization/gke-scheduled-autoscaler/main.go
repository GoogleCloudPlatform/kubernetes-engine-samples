/**
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package main

import (
	"context"
	"flag"
	"log"
	"strings"
	"time"

	gce "cloud.google.com/go/compute/metadata"
	monitoring "cloud.google.com/go/monitoring/apiv3/v2"
	"cloud.google.com/go/monitoring/apiv3/v2/monitoringpb"
	"google.golang.org/genproto/googleapis/api/metric"
	"google.golang.org/genproto/googleapis/api/monitoredres"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var (
	name  = flag.String("name", "", "The metric name.")
	value = flag.Float64("value", 0.0, "The value to export.")
)

func main() {
	flag.Parse()
	export(*name, *value)
}

func export(name string, value float64) {
	client, err := monitoring.NewMetricClient(context.Background())
	if err != nil {
		panic(err)
	}
	defer client.Close()

	projectID, _ := gce.ProjectID()
	project := "projects/" + projectID
	metric, request := buildTimeSeriesRequest(project, name, value)
	if err = client.CreateTimeSeries(context.Background(), request); err != nil {
		panic(err)
	}
	log.Printf("Exported custom metric '%v' = %v.", metric, value)
}

func buildTimeSeriesRequest(project, name string, value float64) (string, *monitoringpb.CreateTimeSeriesRequest) {
	metricType := "custom.googleapis.com/" + name
	metricLabels := map[string]string{}
	monitoredResourceType := "k8s_cluster"
	monitoredResourceLabels := buildMonitoredResourceLabels()
	return metricType, &monitoringpb.CreateTimeSeriesRequest{
		Name: project,
		TimeSeries: []*monitoringpb.TimeSeries{
			{
				Metric: &metric.Metric{
					Type:   metricType,
					Labels: metricLabels,
				},
				Resource: &monitoredres.MonitoredResource{
					Type:   monitoredResourceType,
					Labels: monitoredResourceLabels,
				},
				Points: []*monitoringpb.Point{{
					Interval: &monitoringpb.TimeInterval{
						EndTime: timestamppb.New(time.Now()),
					},
					Value: &monitoringpb.TypedValue{
						Value: &monitoringpb.TypedValue_DoubleValue{DoubleValue: value},
					},
				}},
			},
		},
	}
}

func buildMonitoredResourceLabels() map[string]string {
	projectID, _ := gce.ProjectID()
	location, _ := gce.InstanceAttributeValue("cluster-location")
	location = strings.TrimSpace(location)
	clusterName, _ := gce.InstanceAttributeValue("cluster-name")
	clusterName = strings.TrimSpace(clusterName)
	return map[string]string{
		"project_id":   projectID,
		"location":     location,
		"cluster_name": clusterName,
	}
}
