from flask import Flask, send_from_directory
import os

app = Flask(__name__)

IMAGES_DIR = 'images'

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
