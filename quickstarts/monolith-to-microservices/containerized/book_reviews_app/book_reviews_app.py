from flask import Flask, jsonify
import json
import os

app = Flask(__name__)

DATA_DIR = 'data'

def read_json_file(filename):
    with open(os.path.join(DATA_DIR, filename), 'r') as file:
        return json.load(file)

@app.route('/book/<int:book_id>/reviews')
def get_reviews(book_id):
    reviews = read_json_file(f'reviews-{book_id}.json')
    return jsonify(reviews)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
