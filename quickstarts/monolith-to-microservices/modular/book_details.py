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