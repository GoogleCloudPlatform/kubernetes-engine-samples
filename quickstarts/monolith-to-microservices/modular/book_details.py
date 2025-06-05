# Copyright 2025 Google LLC
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


# book_details.py
from flask import Flask, jsonify
import json
import os

app = Flask(__name__)

DATA_DIR = 'details_data'

def read_json_file(filename):
    with open(os.path.join(DATA_DIR, filename), 'r') as file:
        return json.load(file)

@app.route('/books')
def get_books():
    books = [read_json_file(f'book-{i}.json') for i in range(1, 4)]
    return jsonify(books)

@app.route('/book/<int:book_id>')
def get_book(book_id):
    book = read_json_file(f'book-{book_id}.json')
    return jsonify(book)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)