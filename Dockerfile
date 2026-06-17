# Use an official Python 3.11-slim image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and to buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=run.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# Set working directory inside the container
WORKDIR /app

# Install system dependencies needed for compiling packages or testing connectivity
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the Flask development server port
EXPOSE 5000

# Run Flask on startup
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
