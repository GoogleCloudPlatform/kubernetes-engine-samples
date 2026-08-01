# use the specified base image
FROM us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20240220_0936_RC01 as base_image

# declare a new build argument
ARG MODEL_PATH

# set the model path as an environment variable
ENV MODEL_PATH=${MODEL_PATH}

# copy model files from the first stage build
COPY ./$MODEL_PATH /app/$MODEL_PATH
