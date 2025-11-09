# MIT 6.102 (Spring 2025) Problem Set 4: Memory Scramble

The code provided for
[https://web.mit.edu/6.102/www/sp25/psets/ps4](https://web.mit.edu/6.102/www/sp25/psets/ps4).

## Running

The frontend consists of a single static file, `./public/index.html`.

The backend has to be written by you.
You can use any language and libraries.

This repository contains a starting point for the backend written in Python.
You can run it like this:
```
pip install -r requirements.txt
python -m src.server PORT FILENAME
```

For example:
```
python -m src.server 8080 boards/ab.txt
```

To run tests:
```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific test file
pytest test/board_test.py

# Run tests with coverage (requires pytest-cov)
pytest --cov=src --cov-report=html
```

To run the simulation:
```
python -m src.simulation
```
