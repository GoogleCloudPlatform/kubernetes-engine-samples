#!/bin/bash
remote_json_url=https://raw.githubusercontent.com/elastic/kibana-demo-data/refs/heads/main/data/logs-nginx_error.ndjson
base_filename=$(basename "$remote_json_url" .ndjson)
echo "Processing ${base_filename}"
curl -s "$remote_json_url" | while IFS= read -r line; do
  processed_line=$(echo "$line" | sed "s/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T/$(date +%Y-%m-%dT)/g")
  echo "{ \"index\" : { \"_index\" : \"${base_filename}\" } }" >> /tmp/dataset.json
  echo "${processed_line}" >> /tmp/dataset.json
done
curl  -u elastic:migration -H 'Content-Type: application/json' -XPOST elasticsearch.default:9200/_bulk --data-binary @/tmp/dataset.json