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
	"context"
	"fmt"
	"strings"

	billing "cloud.google.com/go/billing/apiv1"
	"google.golang.org/api/iterator"
	"google.golang.org/api/option"
	billingpb "google.golang.org/genproto/googleapis/cloud/billing/v1"
)

var cpuPrefixes = map[MachineFamily]string{
	N1:  "N1 Predefined Instance Core",
	N2:  "N2 Instance Core",
	E2:  "E2 Instance Core",
	N2D: "N2D AMD Custom Instance Core",
}

var memoryPrefixes = map[MachineFamily]string{
	N1:  "N1 Predefined Instance Ram",
	N2:  "N2 Instance Ram",
	E2:  "E2 Instance Ram",
	N2D: "N2D AMD Instance Ram",
}

var pdStandardPrefix = "Regional Storage PD Capacity"

// NewGCPPriceCatalog creates a gcpResourcePrice struct with Monthly prices for cpu and memory
// If credentials is nil, then the default service account will be used
func NewGCPPriceCatalog(credentials []byte, conf CostimatorConfig) (GCPPriceCatalog, error) {
	conf = populateConfigNotProvided(conf)
	var client *billing.CloudCatalogClient
	var err error
	if credentials == nil {
		client, err = billing.NewCloudCatalogClient(context.Background())
	} else {
		client, err = billing.NewCloudCatalogClient(context.Background(), option.WithCredentialsJSON(credentials))
	}
	if err != nil {
		return GCPPriceCatalog{}, err
	}
	return retrievePrices(client, conf)
}

func retrievePrices(client *billing.CloudCatalogClient, conf CostimatorConfig) (GCPPriceCatalog, error) {
	skuIter, err := retrieveAllSKUs(client)

	var cpuPi, memoryPi, storagePdPi *billingpb.PricingInfo
	for {
		sku, err := skuIter.Next()
		if err == iterator.Done ||
			(cpuPi != nil && memoryPi != nil && storagePdPi != nil) {
			break
		}
		if err != nil {
			return GCPPriceCatalog{}, err
		}

		if cpuPi == nil && matchCPU(sku, conf) {
			cpuPi = sku.GetPricingInfo()[0]
		} else if memoryPi == nil && matchMemory(sku, conf) {
			memoryPi = sku.GetPricingInfo()[0]
		} else if storagePdPi == nil && matchGCEPersistentDisk(sku, conf) {
			storagePdPi = sku.GetPricingInfo()[0]
		}
	}
	if err == nil && (cpuPi == nil || memoryPi == nil || storagePdPi == nil) {
		return GCPPriceCatalog{}, fmt.Errorf("Couldn't find all Price Infos: %+v", conf)
	}

	cpuPrice, err := calculateMonthlyPrice(cpuPi)
	if err != nil {
		return GCPPriceCatalog{}, err
	}
	memoryPrice, err := calculateMonthlyPrice(memoryPi)
	if err != nil {
		return GCPPriceCatalog{}, err
	}
	pdStandardPrice, err := calculateMonthlyPrice(storagePdPi)
	if err != nil {
		return GCPPriceCatalog{}, err
	}
	return GCPPriceCatalog{
		cpuPrice:        cpuPrice,
		memoryPrice:     memoryPrice,
		pdStandardPrice: pdStandardPrice}, nil
}

func retrieveAllSKUs(client *billing.CloudCatalogClient) (*billing.SkuIterator, error) {
	ctx := context.Background()
	req := &billingpb.ListSkusRequest{
		Parent: "services/6F81-5844-456A",
	}
	return client.ListSkus(ctx, req), nil
}

func matchCPU(sku *billingpb.Sku, conf CostimatorConfig) bool {
	prefix, _ := cpuPrefixes[conf.ResourceConf.MachineFamily]
	return skuMatcher(sku, prefix, conf)
}

func matchMemory(sku *billingpb.Sku, conf CostimatorConfig) bool {
	prefix, _ := memoryPrefixes[conf.ResourceConf.MachineFamily]
	return skuMatcher(sku, prefix, conf)
}

func matchGCEPersistentDisk(sku *billingpb.Sku, conf CostimatorConfig) bool {
	return skuMatcher(sku, pdStandardPrefix, conf)
}

func skuMatcher(sku *billingpb.Sku, skuPrefix string, conf CostimatorConfig) bool {
	return strings.HasPrefix(sku.GetDescription(), skuPrefix) &&
		contains(sku.GetServiceRegions(), conf.ResourceConf.Region)
}

func calculateMonthlyPrice(pi *billingpb.PricingInfo) (float32, error) {
	pe := pi.GetPricingExpression()
	pu := pe.GetTieredRates()[0].GetUnitPrice()

	unit := pe.GetUsageUnit()
	switch unit {
	case "h":
		// 1 vcpu core per hour rate
		hourlyPrice := float32(pu.GetUnits()) + float32(pu.GetNanos())/1000000000.0
		return hourlyPrice * float32(24) * float32(31), nil
	case "GiBy.h":
		// 1 Byte per hour pricing
		hourlyPrice := (float32(pu.GetUnits()) + float32(pu.GetNanos())/1000000000.0) / (1024 * 1024 * 1024)
		return hourlyPrice * float32(24) * float32(31), nil
	case "GiBy.mo":
		// 1 Byte per month pricing
		monthlyPrice := (float32(pu.GetUnits()) + float32(pu.GetNanos())/1000000000.0) / (1024 * 1024 * 1024)
		return monthlyPrice, nil
	default:
		return 0, fmt.Errorf("Price UsageUnit Not implemented: %s", unit)
	}
}

func contains(items []string, s string) bool {
	for _, item := range items {
		if strings.EqualFold(item, s) {
			return true
		}
	}
	return false
}
