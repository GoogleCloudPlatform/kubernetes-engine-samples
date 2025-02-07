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

//decodeDeployment reads k8s deployment yaml and trasform to Deployment object - mainly used by tests
func decodeDeployment(data []byte, conf CostimatorConfig) (Deployment, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return Deployment{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildDeployment(obj, groupVersionKind, conf)
}

//buildDeployment reads k8s deployment object and trasform to Deployment object
func buildDeployment(obj interface{}, groupVersionKind GroupVersionKind, conf CostimatorConfig) (Deployment, error) {
	switch obj.(type) {
	default:
		return Deployment{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	case *appsV1.Deployment:
		return buildDeploymentV1(obj.(*appsV1.Deployment), conf), nil
	}
}

func buildDeploymentV1(deploy *appsV1.Deployment, conf CostimatorConfig) Deployment {
	conf = populateConfigNotProvided(conf)
	containers := buildContainers(deploy.Spec.Template.Spec.Containers, conf)
	var replicas int32 = 1
	if deploy.Spec.Replicas != (*int32)(nil) {
		replicas = *deploy.Spec.Replicas
	}
	return Deployment{
		APIVersionKindName: buildAPIVersionKindName(deploy.APIVersion, deploy.Kind, deploy.GetNamespace(), deploy.GetName()),
		Replicas:           replicas,
		Containers:         containers,
	}
}
