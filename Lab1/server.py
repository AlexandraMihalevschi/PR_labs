#!/usr/bin/env python3
"""
Simple HTTP File Server
Serves HTML, PNG, and PDF files from a directory
"""

import socket
import os
import sys
from pathlib import Path

# MIME types for different file extensions
MIME_TYPES = {
    '.html': 'text/html',
    '.png': 'image/png',
    '.pdf': 'application/pdf'
}


def generate_directory_listing(directory_path, url_path):
    """
    Generate an HTML page showing files in a directory

    Args:
        directory_path: Physical path on disk
        url_path: URL path requested by client

    Returns:
        HTML string with directory listing
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Directory listing for {url_path}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ padding: 8px; border-bottom: 1px solid #eee; }}
        a {{ text-decoration: none; color: #0066cc; }}
        a:hover {{ text-decoration: underline; }}
        .dir {{ font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Directory listing for {url_path}</h1>
    <hr>
    <ul>
"""

    # Add parent directory link if not at root
    if url_path != '/':
        parent = '/'.join(url_path.rstrip('/').split('/')[:-1]) or '/'
        html += f'        <li><a href="{parent}">[Parent Directory]</a></li>\n'

    # List all files and directories
    try:
        items = sorted(os.listdir(directory_path))
        for item in items:
            item_path = os.path.join(directory_path, item)
            if os.path.isdir(item_path):
                # Directory - add trailing slash
                link = url_path.rstrip('/') + '/' + item + '/'
                html += f'        <li class="dir"><a href="{link}">{item}/</a></li>\n'
            else:
                # File
                link = url_path.rstrip('/') + '/' + item
                html += f'        <li><a href="{link}">{item}</a></li>\n'
    except Exception as e:
        html += f'        <li>Error listing directory: {e}</li>\n'

    html += """    </ul>
    <hr>
</body>
</html>"""

    return html


def get_content_type(file_path):
    """
    Get MIME type based on file extension

    Args:
        file_path: Path to the file

    Returns:
        MIME type string or None if unknown
    """
    ext = os.path.splitext(file_path)[1].lower()
    return MIME_TYPES.get(ext)


def handle_request(client_socket, base_directory):
    """
    Handle a single HTTP request

    Args:
        client_socket: Socket connected to client
        base_directory: Root directory to serve files from
    """
    try:
        # Receive the HTTP request (up to 1024 bytes)
        request = client_socket.recv(1024).decode('utf-8')

        # Parse the request line (first line)
        # Format: GET /path/to/file.html HTTP/1.1
        lines = request.split('\n')
        if not lines:
            return

        request_line = lines[0]
        print(f"Request: {request_line}")

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
        # Convert /path/to/file to path/to/file
        if url_path == '/':
            url_path = 'index.html'  # Default file
        else:
            url_path = url_path.lstrip('/')

        # Build the full file path
        # os.path.join safely combines paths
        file_path = os.path.join(base_directory, url_path)

        # Security check: prevent directory traversal attacks
        # Make sure the requested file is actually inside base_directory
        real_base = os.path.realpath(base_directory)
        real_file = os.path.realpath(file_path)

        if not real_file.startswith(real_base):
            # Trying to access files outside the base directory!
            response = "HTTP/1.1 403 Forbidden\r\n\r\n"
            client_socket.send(response.encode())
            return

        # Check if path is a directory
        if os.path.isdir(file_path):
            # Generate directory listing
            html_content = generate_directory_listing(file_path, '/' + url_path)

            # Create HTTP response
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/html\r\n"
            response += f"Content-Length: {len(html_content)}\r\n"
            response += "\r\n"

            # Send response
            client_socket.send(response.encode())
            client_socket.send(html_content.encode())
            return

        # Check if file exists
        if not os.path.isfile(file_path):
            # File not found - send 404 error
            response = "HTTP/1.1 404 Not Found\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>404 Not Found</h1>"
            response += f"<p>The file '{url_path}' was not found on this server.</p>"
            response += "</body></html>"

            client_socket.send(response.encode())
            return

        # Get the content type
        content_type = get_content_type(file_path)

        if content_type is None:
            # Unknown file type
            response = "HTTP/1.1 415 Unsupported Media Type\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>415 Unsupported Media Type</h1>"
            response += f"<p>The file type is not supported.</p>"
            response += "</body></html>"

            client_socket.send(response.encode())
            return

        # Read the file
        # For binary files (PNG, PDF), read in binary mode
        if content_type in ['image/png', 'application/pdf']:
            with open(file_path, 'rb') as f:
                file_content = f.read()
        else:
            with open(file_path, 'r') as f:
                file_content = f.read().encode()

        # Create HTTP response with headers
        response = "HTTP/1.1 200 OK\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(file_content)}\r\n"
        response += "\r\n"  # Empty line separates headers from body

        # Send headers
        client_socket.send(response.encode())
        # Send file content
        client_socket.send(file_content)

        print(f"Sent: {file_path} ({content_type})")

    except Exception as e:
        print(f"Error handling request: {e}")
        try:
            response = "HTTP/1.1 500 Internal Server Error\r\n\r\n"
            client_socket.send(response.encode())
        except:
            pass


def main():
    """
    Main function - starts the HTTP server
    """
    # Check command-line arguments
    if len(sys.argv) != 2:
        print("Usage: python server.py <directory>")
        print("Example: python server.py ./content")
        sys.exit(1)

    directory = sys.argv[1]

    # Check if directory exists
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist!")
        sys.exit(1)

    # Server configuration
    HOST = '0.0.0.0'  # Listen on all network interfaces
    PORT = 8080  # Port number

    # Create a TCP socket
    # AF_INET = IPv4, SOCK_STREAM = TCP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow reusing the address (helps when restarting server)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind socket to address and port
    server_socket.bind((HOST, PORT))

    # Start listening for connections
    # Backlog of 5 means up to 5 clients can wait in queue
    server_socket.listen(5)

    print(f"Server started on http://{HOST}:{PORT}")
    print(f"Serving files from: {os.path.abspath(directory)}")
    print("Press Ctrl+C to stop the server")

    try:
        while True:
            # Wait for a client connection
            # This blocks until a client connects
            client_socket, client_address = server_socket.accept()
            print(f"\nConnection from {client_address}")

            # Handle the request
            handle_request(client_socket, directory)

            # Close the connection
            client_socket.close()

    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()