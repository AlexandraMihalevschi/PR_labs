# Use Python 3.11 as base image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy server and client scripts
COPY server.py /app/
COPY client.py /app/

# Make scripts executable
RUN chmod +x server.py client.py

# Create directory for content
RUN mkdir -p /app/content

# Expose port 8080 for the server
EXPOSE 8080

# Default command (can be overridden in docker-compose)
CMD ["python", "server.py", "/app/content"]