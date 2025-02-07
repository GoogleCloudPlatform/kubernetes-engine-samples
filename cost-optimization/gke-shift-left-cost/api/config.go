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

// MachineFamily type
type MachineFamily string

const (
	// E2 machines
	E2 MachineFamily = "E2"
	// N1 machines
	N1 MachineFamily = "N1"
	// N2 machines
	N2 MachineFamily = "N2"
	// N2D machines
	N2D MachineFamily = "N2D"
)

// CostimatorConfig Defaults for not provided info in manifests
type CostimatorConfig struct {
	ResourceConf ResourceConfig `yaml:"resourceConf,omitempty"`
	ClusterConf  ClusterConfig  `yaml:"clusterConf,omitempty"`
}

// ResourceConfig is used to setup defaults for resources
type ResourceConfig struct {
	MachineFamily                          MachineFamily `yaml:"machineFamily,omitempty"`
	Region                                 string        `yaml:"region,omitempty"`
	DefaultCPUinMillis                     int64         `yaml:"defaultCPUinMillis,omitempty"`
	DefaultMemoryinBytes                   int64         `yaml:"defaultMemoryinBytes,omitempty"`
	PercentageIncreaseForUnboundedRerouces int64         `yaml:"percentageIncreaseForUnboundedRerouces,omitempty"`
}

// ClusterConfig is used to setup defaults for cluster
type ClusterConfig struct {
	NodesCount int32 `yaml:"nodesCount,omitempty"`
}

// ConfigDefaults set default values for config
func ConfigDefaults() CostimatorConfig {
	return CostimatorConfig{
		ResourceConf: ResourceConfig{
			MachineFamily:                          E2,
			Region:                                 "us-central1",
			DefaultCPUinMillis:                     250,      //250m
			DefaultMemoryinBytes:                   64000000, //64M
			PercentageIncreaseForUnboundedRerouces: 200,
		},
		ClusterConf: ClusterConfig{
			NodesCount: 3,
		},
	}
}

func populateConfigNotProvided(conf CostimatorConfig) CostimatorConfig {
	ret := ConfigDefaults()
	if conf.ResourceConf.MachineFamily != "" {
		ret.ResourceConf.MachineFamily = conf.ResourceConf.MachineFamily
	}
	if conf.ResourceConf.Region != "" {
		ret.ResourceConf.Region = conf.ResourceConf.Region
	}
	if conf.ResourceConf.DefaultCPUinMillis != 0 {
		ret.ResourceConf.DefaultCPUinMillis = conf.ResourceConf.DefaultCPUinMillis
	}
	if conf.ResourceConf.DefaultMemoryinBytes != 0 {
		ret.ResourceConf.DefaultMemoryinBytes = conf.ResourceConf.DefaultMemoryinBytes
	}
	if conf.ResourceConf.PercentageIncreaseForUnboundedRerouces != 0 {
		ret.ResourceConf.PercentageIncreaseForUnboundedRerouces = conf.ResourceConf.PercentageIncreaseForUnboundedRerouces
	}

	if conf.ClusterConf.NodesCount != 0 {
		ret.ClusterConf.NodesCount = conf.ClusterConf.NodesCount
	}
	return ret
}
