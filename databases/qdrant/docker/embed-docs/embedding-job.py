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
from langchain_community.vectorstores import Qdrant
from google.cloud import storage
import os
# [START gke_databases_qdrant_docker_embed_docs_retrieval]
bucketname = os.getenv("BUCKET_NAME")
filename = os.getenv("FILE_NAME")

storage_client = storage.Client()
bucket = storage_client.bucket(bucketname)
blob = bucket.blob(filename)
blob.download_to_filename("/documents/" + filename)
# [END gke_databases_qdrant_docker_embed_docs_retrieval]

# [START gke_databases_qdrant_docker_embed_docs_split]
loader = PyPDFLoader("/documents/" + filename)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
documents = loader.load_and_split(text_splitter)
# [END gke_databases_qdrant_docker_embed_docs_split]

# [START gke_databases_qdrant_docker_embed_docs_embed]
embeddings = VertexAIEmbeddings("text-embedding-005")
# [END gke_databases_qdrant_docker_embed_docs_embed]

# [START gke_databases_qdrant_docker_embed_docs_storage]
qdrant = Qdrant.from_documents(
    documents, embeddings,
    collection_name=os.getenv("COLLECTION_NAME"),
    url=os.getenv("QDRANT_URL"), 
    api_key=os.getenv("APIKEY"),
    shard_number=6,
    replication_factor=2
)
# [END gke_databases_qdrant_docker_embed_docs_storage]
print(filename + " was successfully embedded") 
print(f"# of vectors = {len(documents)}")
 
