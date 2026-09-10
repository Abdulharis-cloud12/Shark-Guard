FROM python:3.12-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Send Python output directly to the terminal
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-root user
RUN groupadd --system sharkguard \
    && useradd --system --gid sharkguard sharkguard

# Install dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src/ ./src/
COPY tests/ ./tests/

# Give the non-root user ownership of the application
RUN chown -R sharkguard:sharkguard /app

# Run the container as the non-root user
USER sharkguard

CMD ["python", "-c", "print('🦈 SharkGuard container is running')"]
