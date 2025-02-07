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

//decodeReplicaSet reads k8s replicaSet yaml and trasform to ReplicaSet object - mainly used by tests
func decodeReplicaSet(data []byte, conf CostimatorConfig) (ReplicaSet, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return ReplicaSet{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildReplicaSet(obj, groupVersionKind, conf)
}

//buildReplicaSet reads k8s replicaSet object and trasform to ReplicaSet object
func buildReplicaSet(obj interface{}, groupVersionKind GroupVersionKind, conf CostimatorConfig) (ReplicaSet, error) {
	switch obj.(type) {
	default:
		return ReplicaSet{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	case *appsV1.ReplicaSet:
		return buildReplicaSetV1(obj.(*appsV1.ReplicaSet), conf), nil
	}
}

func buildReplicaSetV1(replicaset *appsV1.ReplicaSet, conf CostimatorConfig) ReplicaSet {
	conf = populateConfigNotProvided(conf)
	containers := buildContainers(replicaset.Spec.Template.Spec.Containers, conf)
	var replicas int32 = 1
	if replicaset.Spec.Replicas != (*int32)(nil) {
		replicas = *replicaset.Spec.Replicas
	}
	return ReplicaSet{
		APIVersionKindName: buildAPIVersionKindName(replicaset.APIVersion, replicaset.Kind, replicaset.GetNamespace(), replicaset.GetName()),
		Replicas:           replicas,
		Containers:         containers,
	}
}
