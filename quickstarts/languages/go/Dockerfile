# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START gke_quickstarts_languages_go_dockerfile]
# Use the offical Go image to create a build artifact.
# This is based on Debian and sets the GOPATH to /go.
# https://hub.docker.com/_/golang
FROM golang:1.25.6 as builder
WORKDIR /app

# Initialize a new Go module.
RUN go mod init quickstart-go

# Copy local code to the container image.
COPY *.go ./

# Build the command inside the container.
RUN CGO_ENABLED=0 GOOS=linux go build -o /quickstart-go

# Use a Docker multi-stage build to create a lean production image.
# https://docs.docker.com/develop/develop-images/multistage-build/#use-multi-stage-builds
FROM gcr.io/distroless/base-debian11

# Change the working directory.
WORKDIR /

# Copy the binary to the production image from the builder stage.
COPY --from=builder /quickstart-go /quickstart-go

# Run the web service on container startup.
USER nonroot:nonroot
ENTRYPOINT ["/quickstart-go"]
# [END gke_quickstarts_languages_go_dockerfile]
