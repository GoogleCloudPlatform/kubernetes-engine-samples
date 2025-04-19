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


# home.py
from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

BOOK_SERVICE_URL = 'http://localhost:8081'
REVIEW_SERVICE_URL = 'http://localhost:8082'
IMAGE_SERVICE_URL = 'http://localhost:8083'

@app.route('/')
def home():
    response = requests.get(f'{BOOK_SERVICE_URL}/books')
    books = response.json()
    return render_template('home.html', books=books)

@app.route('/book/<int:book_id>')
def book_details(book_id):
    book_response = requests.get(f'{BOOK_SERVICE_URL}/book/{book_id}')
    book = book_response.json()
    return render_template('book_details.html', book=book)

@app.route('/book/<int:book_id>/reviews')
def book_reviews(book_id):
    reviews_response = requests.get(f'{REVIEW_SERVICE_URL}/book/{book_id}/reviews')
    return jsonify(reviews_response.json())

@app.route('/images/<path:filename>')
def serve_image(filename):
    response = requests.get(f'{IMAGE_SERVICE_URL}/images/{filename}')
    return response.content, response.status_code, response.headers.items()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)