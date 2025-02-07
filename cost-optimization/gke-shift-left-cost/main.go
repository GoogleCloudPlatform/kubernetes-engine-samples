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

package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"os"
	"path"
	"strings"

	"github.com/fernandorubbo/k8s-cost-estimator/api"
	log "github.com/sirupsen/logrus"
	"sigs.k8s.io/yaml"
)

const version = "v0.0.1"

var (
	k8sPath     = flag.String("k8s", "", "Required. Path to k8s manifests folder")
	k8sPrevPath = flag.String("k8s-prev", "", "Optional. Path to the previous K8s manifests folder. Useful to compare prices.")
	outputFile  = flag.String("output", "", "Optional. Output file path. If not provided, console is used")
	environ     = flag.String("environ", "LOCAL", "Optional. Where your code is running at. Used to know determine the output file format: GITHUB | GITLAB | LOCAL")
	authKey     = flag.String("auth-key", "", "Optional. The GCP service account JSON key filepath. If not provided, default service account is used (Run 'gcloud auth application-default login' to set your user as the default service account)")
	configFile  = flag.String("config", "", "Optional. The defaults configuration YAML filepath to set: machine family, region and compute resources not provided in k8s manifests")
	verbosity   = flag.String("v", "panic", "Optional. Verbosity: panic|fatal|error|warn|info|debug|trace. Default panic")
)

func init() {
	flag.Parse()

	level, err := log.ParseLevel(*verbosity)
	exitOnError("Invalid 'verbosity' parameter", err)
	if *environ == "GITLAB" {
		log.SetFormatter(&log.JSONFormatter{
			DisableTimestamp: true,
			FieldMap: log.FieldMap{
				log.FieldKeyLevel: "severity",
			},
		})
	}
	log.SetOutput(os.Stdout)
	log.SetLevel(level)

	// required flags
	validateK8sPath(*k8sPath, "k8s")
}

func main() {
	log.Infof("Starting cost estimation (version %s)...", version)

	config := readConfigFromFile()
	priceCatalog := newGCPPriceCatalog(config)
	currentCost := estimateCost(*k8sPath, config, priceCatalog)
	if isPreviousPathProvided() {
		log.Infof("Comparing current cost against previous version. Paths: '%s' vs '%s'", *k8sPath, *k8sPrevPath)
		previousCosts := estimateCost(*k8sPrevPath, config, priceCatalog)
		diffCost := currentCost.Subtract(previousCosts)
		outputDiff(diffCost)
	} else {
		output(currentCost.ToMarkdown())
	}

	log.Info("Finished cost estimation!")
}

func readConfigFromFile() api.CostimatorConfig {
	conf := api.ConfigDefaults()
	if *configFile != "" {
		data, err := ioutil.ReadFile(*configFile)
		exitOnError("Unable to read 'config' file", err)
		err = yaml.Unmarshal(data, &conf)
		exitOnError("Unable to umarshal 'config' file", err)
	} else {
		log.Debugf("Parameter 'config' not provided. Using default config.")
	}
	return conf
}

func newGCPPriceCatalog(config api.CostimatorConfig) api.GCPPriceCatalog {
	log.Debug("Retriving Price Catalog from GCP...")
	credentials := readAuthKeyFromFile()
	priceCatalog, err := api.NewGCPPriceCatalog(credentials, config)
	exitOnError("Unable to read Pricing Catalog from GCP", err)
	return priceCatalog
}

func readAuthKeyFromFile() []byte {
	var credentials []byte
	if *authKey != "" {
		var err error
		credentials, err = ioutil.ReadFile(*authKey)
		exitOnError("Unable to read auth-key file", err)
	} else {
		log.Info("auth-key not provided. Using default service account.")
	}
	return credentials
}

func validateK8sPath(k8sPath string, flag string) {
	if !isK8sPathProvided(k8sPath, flag) {
		exit(fmt.Sprintf("%s is required", flag))
	}
}

func isPreviousPathProvided() bool {
	return isK8sPathProvided(*k8sPrevPath, "k8s-prev")
}

func isK8sPathProvided(k8sPath string, flag string) bool {
	if k8sPath == "" {
		return false
	}

	f, err := os.Stat(k8sPath)
	if os.IsNotExist(err) {
		exit(fmt.Sprintf("%s provided does not exists", flag))
	}
	if !(f.IsDir() || strings.HasSuffix(f.Name(), ".yaml") || strings.HasSuffix(f.Name(), ".yml")) {
		exit(fmt.Sprintf("%s provided must be a folder or a yaml file", flag))
	}
	return true
}

func estimateCost(path string, conf api.CostimatorConfig, pc api.GCPPriceCatalog) api.Cost {
	log.Infof("Estimating monthly cost for k8s objects in path '%s'...", path)
	manifests := api.Manifests{}
	err := manifests.LoadObjectsFromPath(path, conf)
	if err != nil {
		exitOnError(fmt.Sprintf("Unable estimate cost for %s", path), err)
	}
	return manifests.EstimateCost(pc)
}

func outputDiff(diffCost api.DiffCost) {
	output(diffCost.ToMarkdown())

	if *outputFile == "" {
		return
	}
	saveDiffFile(diffCost)
}

func output(markdown string) {
	fmt.Printf("\n%s\n", markdown)

	if *outputFile == "" {
		return
	}

	switch strings.ToUpper(*environ) {
	case "GITHUB":
		log.Debugf("Saving Github file at '%s'", *outputFile)
		saveGithubFile(markdown)
	case "GITLAB":
		log.Debugf("Saving Gitlab file at '%s'", *outputFile)
		saveGithubFile(markdown)
	default:
		log.Debugf("Saving Markdown file at '%s'", *outputFile)
		saveMarkdownFile(markdown)
	}
}

func saveDiffFile(diffCost api.DiffCost) {
	ext := path.Ext(*outputFile)
	diffOutputFile := (*outputFile)[0:len(*outputFile)-len(ext)] + ".diff"
	log.Debugf("Saving Diff file at '%s'", diffOutputFile)

	f, err := os.Create(diffOutputFile)
	exitOnError(fmt.Sprintf("Creating Diff file %s", diffOutputFile), err)
	defer f.Close()
	pd := diffCost.MonthlyDiffRange.ToPriceDiff()
	err = json.NewEncoder(f).Encode(pd)
	exitOnError(fmt.Sprintf("Writting Diff file %s", diffOutputFile), err)
}

func saveGithubFile(markdown string) {
	type github struct {
		Body string `json:"body"`
	}

	gh := &github{
		Body: markdown,
	}
	f, err := os.Create(*outputFile)
	exitOnError(fmt.Sprintf("Creating output file %s", *outputFile), err)
	defer f.Close()
	err = json.NewEncoder(f).Encode(gh)
	exitOnError(fmt.Sprintf("Writting output file %s", *outputFile), err)
}

func saveMarkdownFile(markdown string) {
	err := ioutil.WriteFile(*outputFile, []byte(markdown), 0644)
	exitOnError(fmt.Sprintf("Writing output file %s", *outputFile), err)
}

func exitOnError(message string, err error) {
	if err != nil {
		exitWithError(message, err)
	}
}

func exitWithError(message string, err error) {
	fmt.Printf("\nError: %s\nCause: %+v\n\nSee parameters options below:\n", err, message)
	flag.PrintDefaults()
	os.Exit(-1)
}

func exit(message string) {
	fmt.Printf("\nError: %s\n\nSee parameters options below:\n", message)
	flag.PrintDefaults()
	os.Exit(-1)
}
