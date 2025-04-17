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
from langchain_community.vectorstores.pgvector import PGVector
from google.cloud import storage
import os
# [START gke_databases_postgres_pgvector_docker_embed_docs_retrieval]
bucketname = os.getenv("BUCKET_NAME")
filename = os.getenv("FILE_NAME")

storage_client = storage.Client()
bucket = storage_client.bucket(bucketname)
blob = bucket.blob(filename)
blob.download_to_filename("/documents/" + filename)
# [END gke_databases_postgres_pgvector_docker_embed_docs_retrieval]

# [START gke_databases_postgres_pgvector_docker_embed_docs_split]
loader = PyPDFLoader("/documents/" + filename)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
documents = loader.load_and_split(text_splitter)
for document in documents:
    document.page_content = document.page_content.replace('\x00', '')
# [END gke_databases_postgres_pgvector_docker_embed_docs_split]

# [START gke_databases_postgres_pgvector_docker_embed_docs_embed]
embeddings = VertexAIEmbeddings("text-embedding-005")
# [END gke_databases_postgres_pgvector_docker_embed_docs_embed]

# [START gke_databases_postgres_pgvector_docker_embed_docs_storage]
CONNECTION_STRING = PGVector.connection_string_from_db_params(
    driver="psycopg2",
    host=os.environ.get("POSTGRES_HOST"),
    port=5432,
    database=os.environ.get("DATABASE_NAME"),
    user=os.environ.get("USERNAME"),
    password=os.environ.get("PASSWORD"),
)
COLLECTION_NAME = os.environ.get("COLLECTION_NAME")

db = PGVector.from_documents(
    embedding=embeddings,
    documents=documents,
    collection_name=COLLECTION_NAME,
    connection_string=CONNECTION_STRING,
    use_jsonb=True
)
# [END gke_databases_postgres_pgvector_docker_embed_docs_storage]

print(filename + " was successfully embedded") 
print(f"# of vectors = {len(documents)}")
 
