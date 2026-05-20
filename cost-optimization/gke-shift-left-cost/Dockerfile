# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM golang:1.16.5-alpine3.12 AS builder
WORKDIR /app
# Install dependencies in go.mod and go.sum
COPY go.mod go.sum ./
RUN go mod download
# Copy rest of the application source code
COPY . ./
# Compile the application
RUN go build -mod=readonly -v -o /k8s-cost-estimator


FROM alpine:3.23
WORKDIR /app
# Install utilities needed durin ci/cd process
RUN apk update && apk upgrade && \
    apk add --no-cache bash git curl jq && \
    rm /var/cache/apk/*
# copy applicatrion binary
COPY --from=builder /k8s-cost-estimator /usr/local/bin/k8s-cost-estimator
#ENTRYPOINT ["k8s-cost-estimator"]