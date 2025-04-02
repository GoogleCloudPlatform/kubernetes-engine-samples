from flask import Flask, render_template, jsonify
import requests
import os

app = Flask(__name__)

#Notice how port numbers no longer need to be specified in
#the URLs.

BOOK_SERVICE_URL = 'http://book-details-service' 
REVIEW_SERVICE_URL = 'http://book-reviews-service'
IMAGE_SERVICE_URL = 'http://images-service'

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
