// Copyright 2021 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package api

import (
	"fmt"

	appsV1 "k8s.io/api/apps/v1"
)

//decodeDaemonSet reads k8s DaemonSet yaml and trasform to DaemonSet object - mostly used by unit tests
func decodeDaemonSet(data []byte, conf CostimatorConfig) (DaemonSet, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return DaemonSet{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildDaemonSet(obj, groupVersionKind, conf)
}

//buildDaemonSet reads k8s DaemonSet object and trasform to DaemonSet object
func buildDaemonSet(obj interface{}, groupVersionKind GroupVersionKind, conf CostimatorConfig) (DaemonSet, error) {
	switch obj.(type) {
	default:
		return DaemonSet{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	case *appsV1.DaemonSet:
		return buildDaemonSetV1(obj.(*appsV1.DaemonSet), conf), nil
	}
}

func buildDaemonSetV1(deploy *appsV1.DaemonSet, conf CostimatorConfig) DaemonSet {
	conf = populateConfigNotProvided(conf)
	containers := buildContainers(deploy.Spec.Template.Spec.Containers, conf)
	return DaemonSet{
		APIVersionKindName: buildAPIVersionKindName(deploy.APIVersion, deploy.Kind, deploy.GetNamespace(), deploy.GetName()),
		NodesCount:         conf.ClusterConf.NodesCount,
		Containers:         containers,
	}
}
