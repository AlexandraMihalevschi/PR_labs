#!/usr/bin/env python3

import socket
import os
import sys


# MIME types for different file extensions
MIME_TYPES = {
    '.html': 'text/html',
    '.png': 'image/png',
    '.pdf': 'application/pdf'
}


def generate_directory_listing(directory_path, url_path):
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Directory listing for {url_path}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Patrick+Hand&display=swap');
        body {{ font-family: 'Patrick-Hand', cursive; }}
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

    ext = os.path.splitext(file_path)[1].lower()
    return MIME_TYPES.get(ext)


def handle_request(client_socket, base_directory):

    try:

        request = client_socket.recv(1024).decode('utf-8')

        lines = request.split('\n')
        if not lines:
            return

        request_line = lines[0]
        print(f"Request: {request_line}")

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

        if url_path == '/':
            url_path = 'index.html'  # Default file
        else:
            url_path = url_path.lstrip('/')

        file_path = os.path.join(base_directory, url_path)

        real_base = os.path.realpath(base_directory)
        real_file = os.path.realpath(file_path)

        if not real_file.startswith(real_base):
            # try to access files outside the base directory
            response = "HTTP/1.1 403 Forbidden\r\n\r\n"
            client_socket.send(response.encode())
            return

        if os.path.isdir(file_path):
            html_content = generate_directory_listing(file_path, '/' + url_path)

            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/html\r\n"
            response += f"Content-Length: {len(html_content)}\r\n"
            response += "\r\n"

            client_socket.send(response.encode())
            client_socket.send(html_content.encode())
            return

        if not os.path.isfile(file_path):
            response = "HTTP/1.1 404 Not Found\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>404 Not Found</h1>"
            response += f"<p>The file '{url_path}' was not found on this server.</p>"
            response += "</body></html>"

            client_socket.send(response.encode())
            return

        content_type = get_content_type(file_path)

        if content_type is None:
            response = "HTTP/1.1 415 Unsupported Media Type\r\n"
            response += "Content-Type: text/html\r\n"
            response += "\r\n"
            response += "<html><body><h1>415 Unsupported Media Type</h1>"
            response += f"<p>The file type is not supported.</p>"
            response += "</body></html>"

            client_socket.send(response.encode())
            return

        if content_type in ['image/png', 'application/pdf']:
            with open(file_path, 'rb') as f:
                file_content = f.read()
        else:
            with open(file_path, 'r') as f:
                file_content = f.read().encode()

        response = "HTTP/1.1 200 OK\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(file_content)}\r\n"
        response += "\r\n"

        client_socket.send(response.encode())
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

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_socket.bind((HOST, PORT))

    server_socket.listen(5)

    print(f"Server started on http://{HOST}:{PORT}")
    print(f"Serving files from: {os.path.abspath(directory)}")
    print("Press Ctrl+C to stop the server")

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"\nConnection from {client_address}")

            handle_request(client_socket, directory)

            client_socket.close()

    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()