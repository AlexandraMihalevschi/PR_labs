#!/usr/bin/env python3
import threading
import requests
import time
import sys

def fetch(url):
    try:
        r = requests.get(url)
        print(f"{r.status_code} - {len(r.content)} bytes from {url}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")

def run_test(url, num_requests):
    threads = []
    start = time.time()
    for _ in range(num_requests):
        t = threading.Thread(target=fetch, args=(url,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    end = time.time()
    print(f"\nTotal time for {num_requests} requests to {url}: {end-start:.2f} seconds\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_requests.py <URL> <NUM_REQUESTS>")
        print("Example: python test_requests.py http://localhost:8080/index.html 10")
        sys.exit(1)

    URL = sys.argv[1]
    NUM_REQUESTS = int(sys.argv[2])
    run_test(URL, NUM_REQUESTS)
