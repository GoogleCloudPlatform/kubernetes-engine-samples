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
	appsV1 "k8s.io/api/apps/v1"
	autoscaleV1 "k8s.io/api/autoscaling/v1"
	autoscaleV2beta1 "k8s.io/api/autoscaling/v2beta1"
	autoscaleV2beta2 "k8s.io/api/autoscaling/v2beta2"
	coreV1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/runtime/serializer"
)

func decode(data []byte) (runtime.Object, GroupVersionKind, error) {
	scheme := buildScheme()
	decoder := serializer.NewCodecFactory(scheme).UniversalDeserializer()
	obj, gvk, err := decoder.Decode(data, nil, nil)
	if err != nil {
		return (runtime.Object)(nil), GroupVersionKind{}, err
	}
	groupVersionKind := GroupVersionKind{
		Group:   gvk.Group,
		Version: gvk.Version,
		Kind:    gvk.Kind,
	}
	return obj, groupVersionKind, err
}

func buildScheme() *runtime.Scheme {
	scheme := runtime.NewScheme()
	registryHPAVersions(scheme)
	registryDeploymentVersions(scheme)
	registryReplicaSetVersions(scheme)
	registryStatefulSetVersions(scheme)
	registryDeamonSetVersions(scheme)
	registryVolumeClaimVersions(scheme)
	return scheme
}

func registryHPAVersions(scheme *runtime.Scheme) {
	gvkAutoscaleV1 := schema.GroupVersionKind{
		Group:   "autoscaling",
		Version: "v1",
		Kind:    HPAKind,
	}
	scheme.AddKnownTypeWithName(gvkAutoscaleV1, &autoscaleV1.HorizontalPodAutoscaler{})

	gvkAutoscaleV2beta1 := schema.GroupVersionKind{
		Group:   "autoscaling",
		Version: "v2beta1",
		Kind:    HPAKind,
	}
	scheme.AddKnownTypeWithName(gvkAutoscaleV2beta1, &autoscaleV2beta1.HorizontalPodAutoscaler{})

	gvkAutoscaleV2beta2 := schema.GroupVersionKind{
		Group:   "autoscaling",
		Version: "v2beta2",
		Kind:    HPAKind,
	}
	scheme.AddKnownTypeWithName(gvkAutoscaleV2beta2, &autoscaleV2beta2.HorizontalPodAutoscaler{})
}

func registryDeploymentVersions(scheme *runtime.Scheme) {
	gvkAppsV1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1",
		Kind:    DeploymentKind,
	}
	scheme.AddKnownTypeWithName(gvkAppsV1, &appsV1.Deployment{})

	gvkAppsV1beta1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta1",
		Kind:    DeploymentKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_deployment.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta1, &appsV1.Deployment{})

	gvkAppsV1beta2 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta2",
		Kind:    DeploymentKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_deployment.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta2, &appsV1.Deployment{})
}

func registryReplicaSetVersions(scheme *runtime.Scheme) {
	gvkAppsV1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1",
		Kind:    ReplicaSetKind,
	}
	scheme.AddKnownTypeWithName(gvkAppsV1, &appsV1.ReplicaSet{})

	gvkAppsV1beta1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta1",
		Kind:    ReplicaSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_replicaset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta1, &appsV1.ReplicaSet{})

	gvkAppsV1beta2 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta2",
		Kind:    ReplicaSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_replicaset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta2, &appsV1.ReplicaSet{})
}

func registryStatefulSetVersions(scheme *runtime.Scheme) {
	gvkAppsV1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1",
		Kind:    StatefulSetKind,
	}
	scheme.AddKnownTypeWithName(gvkAppsV1, &appsV1.StatefulSet{})

	gvkAppsV1beta1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta1",
		Kind:    StatefulSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_statefulset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta1, &appsV1.StatefulSet{})

	gvkAppsV1beta2 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta2",
		Kind:    StatefulSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_statefulset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta2, &appsV1.StatefulSet{})
}

func registryDeamonSetVersions(scheme *runtime.Scheme) {
	gvkAppsV1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1",
		Kind:    DaemonSetKind,
	}
	scheme.AddKnownTypeWithName(gvkAppsV1, &appsV1.DaemonSet{})

	gvkAppsV1beta1 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta1",
		Kind:    DaemonSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_deamonset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta1, &appsV1.DaemonSet{})

	gvkAppsV1beta2 := schema.GroupVersionKind{
		Group:   "apps",
		Version: "v1beta2",
		Kind:    DaemonSetKind,
	}
	// we load v1, once the fields we are interested have in v1
	// This way, we don't need many implementations in builder_deamonset.go file
	scheme.AddKnownTypeWithName(gvkAppsV1beta2, &appsV1.DaemonSet{})
}

func registryVolumeClaimVersions(scheme *runtime.Scheme) {
	gvkV1 := schema.GroupVersionKind{
		Version: "v1",
		Kind:    VolumeClaimKind,
	}
	scheme.AddKnownTypeWithName(gvkV1, &coreV1.PersistentVolumeClaim{})
}
