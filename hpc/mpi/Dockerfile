# Copyright 2025 Google LLC
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

# Import Rocky linux 8 from spack that contains pre-installed spack
FROM spack/rockylinux8:sha256:c530b10099eeedad9d384ffc7419f355d93289b2e615143256186406ee04e275 AS spack-builder

# Install build packages
RUN dnf update -y && \
    dnf install -y \
    sudo \
    gcc-c++ \
    gcc-gfortran \
    make \
    tar \
    git \
    wget \
    xz \
    patch \
    bzip2 \
    && dnf clean all

# Install workload dependencies with spack
RUN mkdir /opt/spack-env \
&&  (echo "spack:" \
&&   echo "  specs:" \
&&   echo "  - hpl@2.3 +openmp %gcc@8.5.0" \
&&   echo "  - intel-oneapi-mpi@2021.13.1" \
&&   echo "  - openblas@0.3.29 threads=openmp" \
&&   echo "  - cmake target=x86_64 %gcc@8.5.0" \
&&   echo "  concretizer:" \
&&   echo "    unify: true" \
&&   echo "  config:" \
&&   echo "    install_tree: /opt/software" \
&&   echo "  view: /opt/view") > /opt/spack-env/spack.yaml

RUN cd /opt/spack-env && spack env activate . && spack install --fail-fast && spack gc -y

# Strip binaries
RUN find -L /opt/view/* -type f -exec readlink -f '{}' \; | \
    xargs file -i | \
    grep 'charset=binary' | \
    grep 'x-executable\|x-archive\|x-sharedlib' | \
    awk -F: '{print $1}' | xargs strip -s

# Environment modification required to run
RUN cd /opt/spack-env && \
    spack env activate --sh -d . >> /etc/profile.d/z10_spack_environment.sh

# Final image
FROM rockylinux:8.9

# Install required rpm library for correct version (for RDMA)
RUN dnf update -y && dnf install https://depot.ciq.com/public/files/gce-accelerator/irdma-kernel-modules-el8-x86_64/irdma-repos.rpm -y

RUN dnf install rdma-core libibverbs-utils librdmacm-utils infiniband-diags perftest -y

# Install other packages for running
RUN dnf install sudo \
                ca-certificates \
                hwloc \
                numactl \
                infiniband-diags \
                libibverbs \
                librdmacm \
                iproute \
                libibverbs-devel \
                librdmacm-devel \
                kmod-idpf-irdma \
                dnf-plugins-core \
                NetworkManager \
                bc -y \
                && dnf clean all

RUN sudo yum -y update && sudo yum -y install cmake pkgconfig procps && sudo yum -y --nobest --skip-broken groupinstall "Development Tools"

# Install and configure ssh for MPI
RUN dnf install openssh-server openssh-clients -y && mkdir -p /var/run/sshd && ssh-keygen -A

RUN sed -i 's/[ #]\(.*StrictHostKeyChecking \).*/ \1no/g' /etc/ssh/ssh_config && \
    echo "    UserKnownHostsFile /dev/null" >> /etc/ssh/ssh_config && \
    sed -i 's/#\(StrictModes \).*/\1no/g' /etc/ssh/sshd_config && \
    sed -i 's/#\(PasswordAuthentication \).*/\1no/g' /etc/ssh/sshd_config && \
    sed -i 's/#\(PermitRootLogin \).*/\1yes/g' /etc/ssh/sshd_config

# Move workload dependencies to image
COPY --from=spack-builder /opt/spack-env /opt/spack-env
COPY --from=spack-builder /opt/view /opt/view
COPY --from=spack-builder /opt/software /opt/software
COPY --from=spack-builder /etc/profile.d/z10_spack_environment.sh /etc/profile.d/z10_spack_environment.sh

ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile", "-l"]
