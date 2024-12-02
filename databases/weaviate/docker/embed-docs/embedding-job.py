# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from langchain_google_vertexai import VertexAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import weaviate
from weaviate.connect import ConnectionParams
from langchain_weaviate.vectorstores import WeaviateVectorStore
from google.cloud import storage
import os
# [START gke_databases_weaviate_docker_embed_docs_retrieval]
bucketname = os.getenv("BUCKET_NAME")
filename = os.getenv("FILE_NAME")

storage_client = storage.Client()
bucket = storage_client.bucket(bucketname)
blob = bucket.blob(filename)
blob.download_to_filename("/documents/" + filename)
# [END gke_databases_weaviate_docker_embed_docs_retrieval]

# [START gke_databases_weaviate_docker_embed_docs_split]
loader = PyPDFLoader("/documents/" + filename)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
documents = loader.load_and_split(text_splitter)
# [END gke_databases_weaviate_docker_embed_docs_split]

# [START gke_databases_weaviate_docker_embed_docs_embed]
embeddings = VertexAIEmbeddings("text-embedding-005")
# [END gke_databases_weaviate_docker_embed_docs_embed]

# [START gke_databases_weaviate_docker_embed_docs_storage]
auth_config = weaviate.auth.AuthApiKey(api_key=os.getenv("APIKEY"))
client = weaviate.WeaviateClient(
    connection_params=ConnectionParams.from_params(
        http_host=os.getenv("WEAVIATE_ENDPOINT"),
        http_port="80",
        http_secure=False,
        grpc_host=os.getenv("WEAVIATE_GRPC_ENDPOINT"),
        grpc_port="50051",
        grpc_secure=False,
    ),
    auth_client_secret=auth_config
)
client.connect()
if not client.collections.exists("trainingdocs"):
    collection = client.collections.create(name="trainingdocs")
db = WeaviateVectorStore.from_documents(documents, embeddings, client=client, index_name="trainingdocs")
# [END gke_databases_weaviate_docker_embed_docs_storage]

print(filename + " was successfully embedded") 
print(f"# of vectors = {len(documents)}")
 
