# Use Python 3.12-slim (Matches your local version)
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
# 'gcc' is often needed for some python packages to compile
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install dependencies
# --default-timeout=100 helps prevent timeouts when downloading huge Torch files
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Copy the app code
COPY . .

# Expose port
EXPOSE 8080

# Run the app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]