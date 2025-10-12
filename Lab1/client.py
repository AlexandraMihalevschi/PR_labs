#!/usr/bin/env python3
"""
Simple HTTP Client
Downloads files from the HTTP server
"""

import socket
import os
import sys


def parse_response(response_bytes):
    """
    Parse HTTP response into headers and body

    Args:
        response_bytes: Raw HTTP response

    Returns:
        Tuple of (status_code, headers_dict, body_bytes)
    """
    # Split headers and body
    # HTTP headers end with \r\n\r\n
    try:
        header_end = response_bytes.find(b'\r\n\r\n')
        if header_end == -1:
            return None, {}, response_bytes

        headers_section = response_bytes[:header_end].decode('utf-8')
        body = response_bytes[header_end + 4:]  # Skip the \r\n\r\n

        # Parse status line
        lines = headers_section.split('\r\n')
        status_line = lines[0]

        # Extract status code (e.g., "HTTP/1.1 200 OK" -> 200)
        status_code = int(status_line.split()[1])

        # Parse headers into dictionary
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()

        return status_code, headers, body

    except Exception as e:
        print(f"Error parsing response: {e}")
        return None, {}, response_bytes


def make_request(host, port, path):
    """
    Make an HTTP GET request

    Args:
        host: Server hostname or IP
        port: Server port
        path: URL path (e.g., /index.html)

    Returns:
        Raw HTTP response bytes
    """
    try:
        # Create TCP socket
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Set timeout (10 seconds)
        client_socket.settimeout(10)

        # Connect to server
        print(f"Connecting to {host}:{port}...")
        client_socket.connect((host, port))

        # Build HTTP request
        request = f"GET {path} HTTP/1.1\r\n"
        request += f"Host: {host}\r\n"
        request += "Connection: close\r\n"
        request += "\r\n"

        # Send request
        print(f"Requesting: {path}")
        client_socket.send(request.encode())

        # Receive response
        response = b''
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response += chunk

        # Close socket
        client_socket.close()

        return response

    except socket.timeout:
        print("Error: Connection timed out")
        return None
    except ConnectionRefusedError:
        print(f"Error: Could not connect to {host}:{port}")
        print("Make sure the server is running!")
        return None
    except Exception as e:
        print(f"Error making request: {e}")
        return None


def get_content_type(headers):
    """
    Get content type from headers

    Args:
        headers: Dictionary of HTTP headers

    Returns:
        Content type string or None
    """
    return headers.get('content-type', '').split(';')[0].strip()


def get_filename_from_path(path):
    """
    Extract filename from URL path

    Args:
        path: URL path (e.g., /folder/file.pdf)

    Returns:
        Filename (e.g., file.pdf)
    """
    # Remove trailing slash if present
    path = path.rstrip('/')

    # Get last part of path
    if '/' in path:
        return path.split('/')[-1]
    return path.lstrip('/')


def main():
    """
    Main function - runs the HTTP client
    """
    # Check command-line arguments
    if len(sys.argv) != 5:
        print("Usage: python client.py <host> <port> <url_path> <save_directory>")
        print("Example: python client.py localhost 8080 /book1.pdf ./downloads")
        print("Example: python client.py localhost 8080 / ./downloads")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    url_path = sys.argv[3]
    save_dir = sys.argv[4]

    # Ensure path starts with /
    if not url_path.startswith('/'):
        url_path = '/' + url_path

    # Create save directory if it doesn't exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"Created directory: {save_dir}")

    # Make HTTP request
    response = make_request(host, port, url_path)

    if response is None:
        sys.exit(1)

    # Parse response
    status_code, headers, body = parse_response(response)

    if status_code is None:
        print("Error: Could not parse server response")
        sys.exit(1)

    print(f"Status: {status_code}")

    # Check status code
    if status_code != 200:
        print(f"Error: Server returned status {status_code}")
        if body:
            try:
                print(body.decode('utf-8'))
            except:
                pass
        sys.exit(1)

    # Get content type
    content_type = get_content_type(headers)
    print(f"Content-Type: {content_type}")

    # Handle based on content type
    if content_type == 'text/html':
        # HTML - print to console
        print("\n--- HTML Content ---")
        try:
            print(body.decode('utf-8'))
        except Exception as e:
            print(f"Error decoding HTML: {e}")

    elif content_type == 'image/png':
        # PNG - save to file
        filename = get_filename_from_path(url_path)
        if not filename or filename == '':
            filename = 'downloaded_image.png'

        filepath = os.path.join(save_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(body)

        print(f"\nSaved PNG to: {filepath}")
        print(f"Size: {len(body)} bytes")

    elif content_type == 'application/pdf':
        # PDF - save to file
        filename = get_filename_from_path(url_path)
        if not filename or filename == '':
            filename = 'downloaded_file.pdf'

        filepath = os.path.join(save_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(body)

        print(f"\nSaved PDF to: {filepath}")
        print(f"Size: {len(body)} bytes")

    else:
        print(f"Unknown content type: {content_type}")
        print("Saving as 'downloaded_file'...")

        filepath = os.path.join(save_dir, 'downloaded_file')
        with open(filepath, 'wb') as f:
            f.write(body)

        print(f"Saved to: {filepath}")


if __name__ == '__main__':
    main()