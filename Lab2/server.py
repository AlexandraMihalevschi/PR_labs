#!/usr/bin/env python3
"""
Multithreaded HTTP File Server with Request Counter and Rate Limiting
Handles multiple concurrent requests using threading
"""

import socket
import os
import sys
import threading
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# MIME types for different file extensions
MIME_TYPES = {
    '.html': 'text/html',
    '.png': 'image/png',
    '.pdf': 'application/pdf'
}

# Global variables for request counter and rate limiting
# Using defaultdict for automatic initialization
request_counts = defaultdict(int)  # {file_path: count}
request_counts_lock = threading.Lock()  # Protects request_counts

# Rate limiting: track requests per IP
# {ip_address: [timestamp1, timestamp2, ...]}
rate_limit_data = defaultdict(list)
rate_limit_lock = threading.Lock()
RATE_LIMIT = 5  # requests per second
RATE_WINDOW = 1.0  # time window in seconds

# Statistics
total_requests = 0
total_requests_lock = threading.Lock()


def is_rate_limited(client_ip):
    """
    Check if client IP is rate limited

    Args:
        client_ip: IP address of client

    Returns:
        True if rate limited, False otherwise
    """
    with rate_limit_lock:
        current_time = time.time()

        # Remove old timestamps outside the window
        rate_limit_data[client_ip] = [
            ts for ts in rate_limit_data[client_ip]
            if current_time - ts < RATE_WINDOW
        ]

        # Check if rate limit exceeded
        if len(rate_limit_data[client_ip]) >= RATE_LIMIT:
            return True

        # Add current timestamp
        rate_limit_data[client_ip].append(current_time)
        return False


def increment_request_count(file_path):
    """
    Thread-safe increment of request counter

    Args:
        file_path: Path to the file being requested
    """
    with request_counts_lock:
        request_counts[file_path] += 1


def get_request_count(file_path):
    """
    Thread-safe read of request counter

    Args:
        file_path: Path to the file

    Returns:
        Number of requests for this file
    """
    with request_counts_lock:
        return request_counts[file_path]


def increment_total_requests():
    """Thread-safe increment of total request counter"""
    global total_requests
    with total_requests_lock:
        total_requests += 1


def generate_directory_listing(directory_path, url_path, base_directory):
    """
    Generate an HTML page showing files in a directory with request counts

    Args:
        directory_path: Physical path on disk
        url_path: URL path requested by client
        base_directory: Root directory being served

    Returns:
        HTML string with directory listing
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Directory listing for {url_path}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .stats {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ padding: 12px; margin: 8px 0; background: white; border-left: 4px solid #2196F3; 
              border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }}
        li:hover {{ background: #f0f0f0; }}
        a {{ text-decoration: none; color: #0066cc; font-weight: bold; }}
        a:hover {{ text-decoration: underline; }}
        .dir {{ border-left-color: #FF9800; }}
        .count {{ 
            background: #4CAF50; 
            color: white; 
            padding: 4px 12px; 
            border-radius: 12px; 
            font-size: 0.9em;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>📁 Directory listing for {url_path}</h1>
    <div class="stats">
        <strong>Total server requests:</strong> {total_requests}
    </div>
    <hr>
    <ul>
"""

    # Add parent directory link if not at root
    if url_path != '/':
        parent = '/'.join(url_path.rstrip('/').split('/')[:-1]) or '/'
        html += f'        <li><a href="{parent}"> [Parent Directory]</a></li>\n'

    # List all files and directories with request counts
    try:
        items = sorted(os.listdir(directory_path))
        for item in items:
            item_path = os.path.join(directory_path, item)

            # Calculate relative path for counting
            rel_path = os.path.relpath(item_path, base_directory)
            count = get_request_count(rel_path)

            if os.path.isdir(item_path):
                # Directory - add trailing slash
                link = url_path.rstrip('/') + '/' + item + '/'
                html += f'        <li class="dir">'
                html += f'<a href="{link}"> {item}/</a>'
                html += f'<span class="count">{count} views</span>'
                html += f'</li>\n'
            else:
                # File
                link = url_path.rstrip('/') + '/' + item
                html += f'        <li>'
                html += f'<a href="{link}"> {item}</a>'
                html += f'<span class="count">{count} requests</span>'
                html += f'</li>\n'
    except Exception as e:
        html += f'        <li>Error listing directory: {e}</li>\n'

    html += """    </ul>
    <hr>
    <p style="color: #666; font-size: 0.9em;">
        Request counters are tracked server-wide and persist during server runtime
    </p>
</body>
</html>"""

    return html


def get_content_type(file_path):
    """Get MIME type based on file extension"""
    ext = os.path.splitext(file_path)[1].lower()
    return MIME_TYPES.get(ext)


def handle_request(client_socket, client_address, base_directory):
    """
    Handle a single HTTP request in a thread

    Args:
        client_socket: Socket connected to client
        client_address: Tuple of (ip, port)
        base_directory: Root directory to serve files from
    """
    client_ip = client_address[0]
    thread_id = threading.current_thread().name

    try:
        # Check rate limiting FIRST
        if is_rate_limited(client_ip):
            print(f"[{thread_id}] ⛔ Rate limited: {client_ip}")
            response = "HTTP/1.1 429 Too Many Requests\r\n"
            response += "Content-Type: text/html\r\n"
            response += "Retry-After: 1\r\n"
            response += "\r\n"
            response += "<html><body><h1>429 Too Many Requests</h1>"
            response += "<p>Rate limit exceeded. Please slow down.</p>"
            response += "<p>Limit: 5 requests per second</p>"
            response += "</body></html>"
            client_socket.send(response.encode())
            return

        # Increment total requests counter
        increment_total_requests()

        # Add artificial delay to simulate work (for testing concurrency)
        # Comment this out for production use
        time.sleep(1)  # 1 second delay

        # Receive the HTTP request
        request = client_socket.recv(1024).decode('utf-8')

        # Parse the request line
        lines = request.split('\n')
        if not lines:
            return

        request_line = lines[0]
        print(f"[{thread_id}] 📨 Request from {client_ip}: {request_line}")

        # Extract the HTTP method and path
        parts = request_line.split()
        if len(parts) < 2:
            return

        method = parts[0]
        url_path = parts[1]

        # Only handle GET requests
        if method != 'GET':
            response = "HTTP/1.1 405 Method Not Allowed\r\n\r\n"
            client_socket.send(response.encode())
            return

        # Remove leading slash and decode URL
        if url_path == '/':
            html_content = generate_directory_listing(base_directory, '/', base_directory)
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/html; charset=utf-8\r\n"
            response += f"Content-Length: {len(html_content.encode())}\r\n"
            response += "\r\n"
            client_socket.send(response.encode())
            client_socket.send(html_content.encode())
            print(f"[{thread_id}] ✅ Sent directory listing for root /")
            return
        else:
            url_path = url_path.lstrip('/')

        # Build the full file path
        file_path = os.path.join(base_directory, url_path)

        # Security check: prevent directory traversal
        real_base = os.path.realpath(base_directory)
        real_file = os.path.realpath(file_path)

        if not real_file.startswith(real_base):
            response = "HTTP/1.1 403 Forbidden\r\n\r\n"
            client_socket.send(response.encode())
            return

        # Calculate relative path for counting
        rel_path = os.path.relpath(real_file, real_base)

        # Check if path is a directory
        if os.path.isdir(file_path):
            # Increment counter for directory
            increment_request_count(rel_path)

            # Generate directory listing
            html_content = generate_directory_listing(file_path, '/' + url_path, base_directory)

            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/html\r\n"
            response += f"Content-Length: {len(html_content)}\r\n"
            response += "\r\n"

            client_socket.send(response.encode())
            client_socket.send(html_content.encode())
            print(f"[{thread_id}] ✅ Sent directory listing for {url_path}")
            return

        # Check if file exists
        if not os.path.isfile(file_path):
            response = "HTTP/1.1 404 Not Found\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>404 Not Found</h1>"
            response += f"<p>The file '{url_path}' was not found on this server.</p>"
            response += "</body></html>"

            client_socket.send(response.encode())
            print(f"[{thread_id}] ❌ 404: {url_path}")
            return

        # Increment request counter for this file
        increment_request_count(rel_path)

        # Get the content type
        content_type = get_content_type(file_path)

        if content_type is None:
            response = "HTTP/1.1 415 Unsupported Media Type\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>415 Unsupported Media Type</h1></body></html>"
            client_socket.send(response.encode())
            return

        # Read the file
        if content_type in ['image/png', 'application/pdf']:
            with open(file_path, 'rb') as f:
                file_content = f.read()
        else:
            with open(file_path, 'r') as f:
                file_content = f.read().encode()

        # Create HTTP response
        response = "HTTP/1.1 200 OK\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(file_content)}\r\n"
        response += "\r\n"

        # Send headers and content
        client_socket.send(response.encode())
        client_socket.send(file_content)

        print(f"[{thread_id}] ✅ Sent: {url_path} ({content_type}) - "
              f"Request #{get_request_count(rel_path)}")

    except Exception as e:
        print(f"[{thread_id}] ❌ Error: {e}")
        try:
            response = "HTTP/1.1 500 Internal Server Error\r\n\r\n"
            client_socket.send(response.encode())
        except:
            pass
    finally:
        client_socket.close()


def main():
    """Main function - starts the multithreaded HTTP server"""
    if len(sys.argv) != 2:
        print("Usage: python server.py <directory>")
        print("Example: python server.py ./content")
        sys.exit(1)

    directory = sys.argv[1]

    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist!")
        sys.exit(1)

    # Server configuration
    HOST = '0.0.0.0'
    PORT = 8080

    # Create TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind and listen
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)  # Increased backlog for concurrent connections

    print(f"🚀 Multithreaded HTTP Server started on http://{HOST}:{PORT}")
    print(f"📁 Serving files from: {os.path.abspath(directory)}")
    print(f"🧵 Using threading for concurrent request handling")
    print(f"⚡ Rate limit: {RATE_LIMIT} requests per second per IP")
    print(f"📊 Request counting enabled")
    print("Press Ctrl+C to stop the server\n")

    try:
        while True:
            # Accept connection
            client_socket, client_address = server_socket.accept()

            # Create a new thread to handle this request
            # Using daemon threads so they don't prevent shutdown
            thread = threading.Thread(
                target=handle_request,
                args=(client_socket, client_address, directory),
                daemon=True
            )
            thread.start()

            # Show active threads count
            active_threads = threading.active_count() - 1  # Exclude main thread
            print(f"🔄 Active threads: {active_threads}")

    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down server...")
        print(f"📊 Total requests handled: {total_requests}")
        print("👋 Goodbye!")
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()