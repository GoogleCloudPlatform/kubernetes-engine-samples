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

	v1 "k8s.io/api/autoscaling/v1"
	"k8s.io/api/autoscaling/v2beta1"
	"k8s.io/api/autoscaling/v2beta2"
)

//decodeHPA reads k8s HorizontalPodAutoScaler yaml and trasform to HPA object - mostly used by tests
func decodeHPA(data []byte) (HPA, error) {
	obj, groupVersionKind, err := decode(data)
	if err != nil {
		return HPA{}, fmt.Errorf("Error Decoding. Check if your GroupVersionKind is defined in api/k8s_decoder.go. Root cause %+v", err)
	}
	return buildHPA(obj, groupVersionKind)
}

//buildHPA reads k8s HorizontalPodAutoScaler object and trasform to HPA object
func buildHPA(obj interface{}, groupVersionKind GroupVersionKind) (HPA, error) {
	switch obj.(type) {
	case *v2beta2.HorizontalPodAutoscaler:
		return buildHPAV2beta2(obj.(*v2beta2.HorizontalPodAutoscaler)), nil
	case *v2beta1.HorizontalPodAutoscaler:
		return buildHPAV2beta1(obj.(*v2beta1.HorizontalPodAutoscaler)), nil
	case *v1.HorizontalPodAutoscaler:
		return buildHPAV1(obj.(*v1.HorizontalPodAutoscaler)), nil
	default:
		return HPA{}, fmt.Errorf("APIVersion and Kind not Implemented: %+v", groupVersionKind)
	}
}

func buildHPAV2beta2(hpa *v2beta2.HorizontalPodAutoscaler) HPA {
	targetCPUPercentage := int32(0)
	netrics := hpa.Spec.Metrics
	for i := 0; i < len(netrics); i++ {
		metric := netrics[i]
		if metric.Type == v2beta2.ResourceMetricSourceType {
			res := metric.Resource
			target := res.Target
			if res.Name == "cpu" && target.AverageUtilization != (*int32)(nil) {
				targetCPUPercentage = *target.AverageUtilization
			}
		}
	}

	var minReplicas int32 = 1
	if hpa.Spec.MinReplicas != (*int32)(nil) {
		minReplicas = *hpa.Spec.MinReplicas
	}

	namespace := "default"
	if hpa.GetNamespace() != "" {
		namespace = hpa.GetNamespace()
	}

	targetRef := hpa.Spec.ScaleTargetRef
	return HPA{
		APIVersionKindName:  fmt.Sprintf("%s|%s|%s|%s", hpa.APIVersion, hpa.Kind, namespace, hpa.GetName()),
		TargetRef:           fmt.Sprintf("%s|%s|%s|%s", targetRef.APIVersion, targetRef.Kind, namespace, targetRef.Name),
		MinReplicas:         minReplicas,
		MaxReplicas:         hpa.Spec.MaxReplicas,
		TargetCPUPercentage: targetCPUPercentage,
	}
}

func buildHPAV2beta1(hpa *v2beta1.HorizontalPodAutoscaler) HPA {
	targetCPUPercentage := int32(0)
	netrics := hpa.Spec.Metrics
	for i := 0; i < len(netrics); i++ {
		metric := netrics[i]
		if metric.Type == v2beta1.ResourceMetricSourceType {
			res := metric.Resource
			if res.Name == "cpu" && res.TargetAverageUtilization != (*int32)(nil) {
				targetCPUPercentage = *res.TargetAverageUtilization
			}
		}
	}

	var minReplicas int32 = 1
	if hpa.Spec.MinReplicas != (*int32)(nil) {
		minReplicas = *hpa.Spec.MinReplicas
	}

	namespace := "default"
	if hpa.GetNamespace() != "" {
		namespace = hpa.GetNamespace()
	}

	targetRef := hpa.Spec.ScaleTargetRef
	return HPA{
		APIVersionKindName:  fmt.Sprintf("%s|%s|%s|%s", hpa.APIVersion, hpa.Kind, namespace, hpa.GetName()),
		TargetRef:           fmt.Sprintf("%s|%s|%s|%s", targetRef.APIVersion, targetRef.Kind, namespace, targetRef.Name),
		MinReplicas:         minReplicas,
		MaxReplicas:         hpa.Spec.MaxReplicas,
		TargetCPUPercentage: targetCPUPercentage,
	}
}

func buildHPAV1(hpa *v1.HorizontalPodAutoscaler) HPA {
	var targetCPUPercentage int32 = 0
	if hpa.Spec.TargetCPUUtilizationPercentage != (*int32)(nil) {
		targetCPUPercentage = *hpa.Spec.TargetCPUUtilizationPercentage
	}
	var minReplicas int32 = 1
	if hpa.Spec.MinReplicas != (*int32)(nil) {
		minReplicas = *hpa.Spec.MinReplicas
	}
	targetRef := hpa.Spec.ScaleTargetRef
	return HPA{
		APIVersionKindName:  buildAPIVersionKindName(hpa.APIVersion, hpa.Kind, hpa.GetNamespace(), hpa.GetName()),
		TargetRef:           buildAPIVersionKindName(targetRef.APIVersion, targetRef.Kind, hpa.GetNamespace(), targetRef.Name),
		MinReplicas:         minReplicas,
		MaxReplicas:         hpa.Spec.MaxReplicas,
		TargetCPUPercentage: targetCPUPercentage,
	}
}
