FROM python:3.11-slim
WORKDIR /app
COPY server.py /app/
COPY client.py /app/
RUN chmod +x server.py client.py
RUN mkdir -p /app/content
EXPOSE 8081
CMD ["python", "server.py", "/app/content"]