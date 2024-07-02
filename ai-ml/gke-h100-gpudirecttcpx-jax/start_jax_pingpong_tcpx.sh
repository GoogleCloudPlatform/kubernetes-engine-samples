# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/bash
set -e
set -x
set -u
set -o pipefail

: "${NNODES:?Must set NNODES}"
: "${NODE_RANK:?Must set NODE_RANK}"
: "${COORDINATOR_PORT:?Must set COORDINATOR_PORT}"
: "${COORDINATOR_ADDR:?Must set COORDINATOR_ADDR}"

export COORDINATOR_PORT=$COORDINATOR_PORT
export COORDINATOR_ADDR=$COORDINATOR_ADDR
export NNODES=$NNODES
export NODE_RANK=$NODE_RANK

set_nccl_gpudirect_tcpx_specific_configuration() {
  if [[ "$USE_GPUDIRECT_TCPX" == "yes" ]]; then
    echo "Using GPUDirect-TCPX"
    export NCCL_CROSS_NIC=0
    export NCCL_ALGO=Ring
    export NCCL_PROTO=Simple
    export NCCL_DEBUG=INFO
    export NCCL_NET_GDR_LEVEL=PIX
    export NCCL_P2P_PXN_LEVEL=0
    export NCCL_DEBUG_SUBSYS=INIT,GRAPH,ENV,TUNING,NET,VERSION
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/tcpx/lib64"
    export NCCL_GPUDIRECTTCPX_UNIX_CLIENT_PREFIX=/run/tcpx
    export NCCL_GPUDIRECTTCPX_FORCE_ACK=0
    export NCCL_GPUDIRECTTCPX_TX_COMPLETION_NANOSLEEP=1000
    export NCCL_DYNAMIC_CHUNK_SIZE=524288
    export NCCL_P2P_NET_CHUNKSIZE=524288
    export NCCL_P2P_PCI_CHUNKSIZE=524288
    export NCCL_P2P_NVL_CHUNKSIZE=1048576
    export NCCL_NSOCKS_PERTHREAD=4
    export NCCL_SOCKET_NTHREADS=1
    export NCCL_MAX_NCHANNELS=12
    export NCCL_MIN_NCHANNELS=12
    export NCCL_GPUDIRECTTCPX_PROGRAM_FLOW_STEERING_WAIT_MICROS=1000000
    export NCCL_SOCKET_IFNAME=eth0
    export NCCL_GPUDIRECTTCPX_TX_BINDINGS="eth1:8-21,112-125;eth2:8-21,112-125;eth3:60-73,164-177;eth4:60-73,164-177"
    export NCCL_GPUDIRECTTCPX_RX_BINDINGS="eth1:22-35,124-139;eth2:22-35,124-139;eth3:74-87,178-191;eth4:74-87,178-191"
    export NCCL_GPUDIRECTTCPX_SOCKET_IFNAME=eth1,eth2,eth3,eth4
    export NCCL_GPUDIRECTTCPX_CTRL_DEV=eth0
  else
    echo "NOT using TCPX"
  fi
}

function on_script_completion {
  # semaphore to cleanly exit hardware utilization monitor
  touch /run/tcpx/workload_terminated
}
trap on_script_completion EXIT

set_nccl_gpudirect_tcpx_specific_configuration

python jax_pingpong_tcpx.py