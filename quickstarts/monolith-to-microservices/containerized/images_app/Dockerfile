# Use an official Python runtime as the base image
FROM python:3.14-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python script into the container
COPY images_app.py .

# Copy the images folder into the container
COPY images/ ./images/

# Run the Python script when the container launches
CMD ["python", "images_app.py"]
