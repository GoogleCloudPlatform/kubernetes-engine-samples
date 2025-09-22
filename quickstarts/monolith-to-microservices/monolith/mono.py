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



from flask import Flask, jsonify, render_template, send_from_directory, request
import json
import os

app = Flask(__name__)

# Configuration
DATA_DIR = 'data'

# Helper function to read JSON files
def read_json_file(filename):
    with open(os.path.join(DATA_DIR, filename), 'r') as file:
        return json.load(file)

# Load book details
books = [read_json_file(f'book-{i}.json') for i in range(1, 4)]

# Load book reviews
def get_book_reviews(book_id):
    return read_json_file(f'reviews-{book_id}.json')

@app.route('/')
def home():
    return render_template('home.html', books=books)

@app.route('/book/<int:book_id>')
def book_details(book_id):
    book = next((book for book in books if book['id'] == book_id), None)
    if book is None:
        return "Book not found", 404
    return render_template('book_details.html', book=book)

@app.route('/book/<int:book_id>/reviews')
def book_reviews(book_id):
    reviews = get_book_reviews(book_id)
    return jsonify(reviews)

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(DATA_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)