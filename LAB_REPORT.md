# Lab 3: Multiplayer Game - Memory Scramble

**Student Name:** Mihalevschi Alexandra
**Date:** 11.11.2025
**Course:** Network Programming

---

## 1. Project Structure

### Directory Contents

```
MIT-6.102-ps4/
├── src/
│   ├── board.py          # Board ADT implementation
│   ├── commands.py       # Glue code module (calls Board methods)
│   ├── server.py         # HTTP API server
│   ├── simulation.py     # Multi-player simulation script
│   └── browser_simulation.py  # Browser-visible simulation
├── test/
│   ├── board_test.py     # Unit tests for Board ADT
│   ├── concurrent_test.py # Tests for Problem 3 (concurrency)
│   ├── map_test.py       # Tests for Problem 4 (map function)
│   └── watch_test.py     # Tests for Problem 5 (watch function)
├── boards/
│   ├── ab.txt            # Sample board file
│   ├── perfect.txt       # 3x3 rainbow/unicorn board
│   └── zoom.txt          # Another sample board
├── public/
│   └── index.html        # Web UI for playing the game
├── requirements.txt      # Python dependencies
└── pytest.ini           # Pytest configuration
```

**Screenshot:** Project directory structure

![Directory Structure](screenshots/structure.png)

### Key Files

- **board.py**: Mutable Board ADT with `check_rep()`, rep invariants, and all game logic
- **commands.py**: Simple glue code (1 line per function) that calls Board methods
- **server.py**: HTTP API that only calls functions from commands module
- **simulation.py**: Tests 4 players, 100 moves each, 0.1-2ms delays

---

## 2. Problem 1: Game Board ADT

### 2.1 Board ADT Specification

**Location:** `src/board.py`

The `Board` class implements a mutable ADT for the Memory Scramble game board.

**Key Methods:**
- `parse_from_file(filename)`: Static factory method to create board from file
- `get_board_state(player_id)`: Returns board state string from player's perspective
- `flip_card(player_id, row, column)`: Flips a card following game rules
- `check_rep()`: Verifies representation invariants

**Representation Invariants:**
- All cards are non-empty strings
- Face-up cards have valid controller or None
- Player-controlled cards are tracked consistently
- Board dimensions match card grid size

**Safety from Rep Exposure:**
- All fields are private (prefixed with `_`)
- No direct access to internal representation
- Methods return copies or immutable views

**Screenshot:** Board ADT class structure

![Board ADT](screenshots/board_adt.png)

### 2.2 Game Rules Implementation

All 11 gameplay rules are implemented:

**First Card Rules:**
- 1-A: Empty space → fails (raises ValueError)
- 1-B: Face down → turns face up, player controls
- 1-C: Face up, uncontrolled → player controls
- 1-D: Face up, controlled by another → waits (async)

**Second Card Rules:**
- 2-A: Empty space → fails, relinquish first card
- 2-B: Controlled by any player → fails, relinquish first card
- 2-C: Face down → turns face up
- 2-D: Cards match → player keeps control of both
- 2-E: Cards don't match → player relinquishes control

**Cleanup Rules:**
- 3-A: Previous cards matched → remove them
- 3-B: Previous cards didn't match → turn face down if uncontrolled

**Commands to test:**
```bash
# Run unit tests for all game rules
pytest test/board_test.py -v

# Test specific rule
pytest test/board_test.py::TestRule1A -v
```

**Screenshot:** Test results showing all rules passing

![Game Rules Tests](screenshots/rules_tests.png)

### 2.3 Board File Parsing

**Format:** `ROWxCOLUMN\nCARD\nCARD\n...`

**Example:** `boards/perfect.txt`
```
3x3
🦄
🦄
🌈
🌈
🌈
🦄
🌈
🦄
🌈
```

**Commands to test:**
```bash
# Test parsing
python -c "from src.board import Board; import asyncio; board = asyncio.run(Board.parse_from_file('boards/perfect.txt')); print(board)"
```

**Screenshot:** Parsed board visualization

![Board Parsing](screenshots/board_parsing.png)

---

## 3. Problem 2: Connect to Web Server

### 3.1 Commands Module Structure

**Location:** `src/commands.py`

The commands module is **pure glue code** - each function is 1 line:

```python
async def look(board: Board, player_id: str) -> str:
    return await board.look(player_id)

async def flip(board: Board, player_id: str, row: int, column: int) -> str:
    return await board.flip(player_id, row, column)

async def map_cards(board: Board, player_id: str, f: Callable) -> str:
    return await board.map(player_id, f)

async def watch(board: Board, player_id: str) -> str:
    return await board.watch(player_id)
```

**Verification:** No control statements, no additional logic, just delegation to Board methods.

**Screenshot:** Commands module code

![Commands Module](screenshots/commands_module.png)

### 3.2 HTTP API Server

**Location:** `src/server.py`

**Endpoints:**
- `GET /look/<player_id>` - Get board state
- `GET /flip/<player_id>/<row>,<column>` - Flip a card
- `GET /replace/<player_id>/<old>/<new>` - Replace cards (map)
- `GET /watch/<player_id>` - Watch for board changes
- `GET /` - Web UI

**Key Feature:** Server **only** calls functions from `commands` module, never Board methods directly.

**Commands to run:**
```bash
# Start server
python -m src.server 8080 boards/perfect.txt

# In browser, open:
# http://localhost:8080
```

**Screenshot:** Server running and web UI

![Web Server](screenshots/web_server.png)

**Screenshot:** Game in browser

![Game UI](screenshots/game_ui.png)

### 3.3 Board State Format

**Format:** `ROWxCOLUMN\nSPOT\nSPOT\n...`

**SPOT values:**
- `none` - Empty space
- `down` - Face-down card
- `up CARD` - Face-up card (not controlled by player)
- `my CARD` - Face-up card controlled by player

**Example:**
```
3x3
up 🦄
down
down
none
my 🌈
none
down
down
up 🦄
```

**Screenshot:** Board state example

![Board State](screenshots/board_state.png)

---

## 4. Problem 3: Concurrent Players

### 4.1 Asynchronous Board Implementation

**Changes:**
- `flip_card()` is now `async`
- Uses `asyncio.Lock()` for thread-safety
- Implements Rule 1-D waiting with `asyncio.Event`

**Waiting Mechanism:**
- When a card is controlled by another player, create an event
- Wait outside the lock (non-blocking for other operations)
- When card becomes available, event is set and waiting player proceeds

**Commands to test:**
```bash
# Run concurrent tests
pytest test/concurrent_test.py -v

# Test waiting behavior
pytest test/concurrent_test.py::TestConcurrentWaiting -v
```

**Screenshot:** Concurrent test results

![Concurrent Tests](screenshots/concurrent_tests.png)

### 4.2 Multi-Player Simulation

**Requirements:**
- 4 players
- 100 moves each
- Timeouts between 0.1ms and 2ms
- No shuffling
- Never crashes

**Commands to run:**
```bash
# Run simulation
python -m src.simulation

# Expected output: "SIMULATION COMPLETED SUCCESSFULLY - NO CRASHES!"
```

**Screenshot:** Simulation output with movesets

![Simulation Output](screenshots/simulation.png)

**Screenshot:** Movesets printed for each player

![Movesets](screenshots/movesets.png)

### 4.3 Concurrency Verification

**Key Features:**
- Multiple players can flip different cards simultaneously
- Waiting players don't block other operations
- No race conditions or deadlocks
- Board state remains consistent

**Screenshot:** Concurrent operations diagram

![Concurrency](screenshots/concurrency.png)

---

## 5. Problem 4: Map Function

### 5.1 Pairwise Consistency

**Requirement:** If two cards match at the start of `map()`, they must continue to match throughout the operation.

**Implementation:**
- Use per-card-value locks (`_map_locks`)
- All cards with the same value are transformed atomically
- Other operations (flip, look) can interleave

**Commands to test:**
```bash
# Run map tests
pytest test/map_test.py -v

# Test pairwise consistency
pytest test/map_test.py::TestPairwiseConsistency -v
```

**Screenshot:** Map function tests

![Map Tests](screenshots/map_tests.png)

### 5.2 Map Function Usage

**Example:** Replace all `🦄` with `🌈`

**Command:**
```bash
# Start server
python -m src.server 8080 boards/perfect.txt

# In another terminal, use curl or browser:
curl "http://localhost:8080/replace/player1/🦄/🌈"
```

**Screenshot:** Before and after map operation

![Map Operation](screenshots/map_operation.png)

---

## 6. Problem 5: Watch Function

### 6.1 Change Detection

**Changes that trigger watch:**
- Cards turning face up
- Cards turning face down
- Cards being removed
- Card values changing (via map)

**Changes that DON'T trigger watch:**
- Control changes only (no state change)
- Failed operations

**Implementation:**
- `_change_watchers`: List of events waiting for changes
- `_notify_change_watchers()`: Called when observable changes occur
- `watch_for_change()`: Creates event and waits

**Commands to test:**
```bash
# Run watch tests
pytest test/watch_test.py -v

# Test change detection
pytest test/watch_test.py::TestWatchDetectsChanges -v
```

**Screenshot:** Watch function tests

![Watch Tests](screenshots/watch_tests.png)

### 6.2 Web UI with Watch

**Feature:** Switch from "polling" to "watching" mode in web UI

**Benefits:**
- Faster updates (no polling delay)
- Lower server load
- More responsive UI

**Commands:**
```bash
# Start server
python -m src.server 8080 boards/perfect.txt

# Open browser, flip switch to "update by watching"
# Open multiple tabs to see real-time updates
```

**Screenshot:** Web UI with watch mode enabled

![Watch UI](screenshots/watch_ui.png)

---

## 7. Testing Summary

### 7.1 Unit Tests Coverage

**Test Files:**
- `test/board_test.py`: All game rules (1-A to 3-B)
- `test/concurrent_test.py`: Concurrency and waiting
- `test/map_test.py`: Map function and pairwise consistency
- `test/watch_test.py`: Watch function and change detection
- `test/integration_test.py`: Combined operations

**Commands:**
```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest test/board_test.py -v
```

**Screenshot:** All tests passing

![All Tests](screenshots/all_tests.png)

**Screenshot:** Test coverage report

![Coverage](screenshots/coverage.png)

### 7.2 Simulation Results

**Standard Simulation:**
- 4 players
- 100 moves each
- 0.1-2ms delays
- Result: ✅ No crashes

**Browser Simulation:**
- 4 players via HTTP
- 100 moves each
- 0.1-2ms delays
- Result: ✅ No crashes, visible in browser

**Commands:**
```bash
# Standard simulation
python -m src.simulation

# Browser simulation (requires server running)
python -m src.server 8080 boards/ab.txt  # Terminal 1
python -m src.browser_simulation          # Terminal 2
```

**Screenshot:** Simulation completion

![Simulation Success](screenshots/simulation_success.png)

---

## 8. Design and Documentation

### 8.1 Module Structure

**✅ Required Structure:**
- ✅ Mutable Board ADT with `check_rep()`
- ✅ Commands module (pure glue code)
- ✅ HTTP API only calls commands module

**Verification:**
```bash
# Check commands module is simple
grep -n "if\|while\|for" src/commands.py
# Should return no matches (or only in comments)
```

**Screenshot:** Module structure verification

![Module Structure](screenshots/module_structure.png)

### 8.2 Representation Invariants

**Location:** `src/board.py` (lines 42-51)

**Key Invariants:**
- Board dimensions match grid size
- All cards are non-empty strings or None
- Face-up cards have valid controller state
- Player-controlled cards tracked consistently
- No duplicate controllers for same card

**Screenshot:** Rep invariants documentation

![Rep Invariants](screenshots/rep_invariants.png)

### 8.3 Safety from Rep Exposure

**Location:** `src/board.py` (lines 53-56)

**Protection Mechanisms:**
- All fields private (`_` prefix)
- No public access to internal representation
- Methods return copies or immutable views
- No direct field access from outside class

**Screenshot:** Safety documentation

![Safety](screenshots/safety.png)

### 8.4 Method Specifications

**Every method includes:**
- Function signature with types
- Preconditions
- Postconditions
- Docstring with Args/Returns/Raises

**Example:**
```python
async def flip(self, player_id: str, row: int, column: int) -> str:
    """
    Tries to flip over a card and returns the board state.
    
    Preconditions:
        - 0 <= row < self._rows
        - 0 <= column < self._columns
        - player_id is nonempty string
    
    Postconditions:
        - If successful, card is face up and controlled by player_id
        - Returns board state string
        - check_rep() holds
    
    Raises:
        ValueError: If flip fails (rules 1-A, 2-A, 2-B)
        IndexError: If row/column out of bounds
    """
```

**Screenshot:** Method specifications

![Specifications](screenshots/specifications.png)

---

## 9. Commands Reference

### Running the Server
```bash
# Install dependencies
pip install -r requirements.txt

# Start server
python -m src.server 8080 boards/perfect.txt

# Access in browser
# http://localhost:8080
```

### Running Tests
```bash
# All tests
pytest -v

# Specific test file
pytest test/board_test.py -v

# With coverage
pytest --cov=src --cov-report=html
```

### Running Simulations
```bash
# Standard simulation
python -m src.simulation

# Browser simulation (requires server)
python -m src.server 8080 boards/ab.txt  # Terminal 1
python -m src.browser_simulation         # Terminal 2
```

### Testing Specific Features
```bash
# Test game rules
pytest test/board_test.py -v

# Test concurrency
pytest test/concurrent_test.py -v

# Test map function
pytest test/map_test.py -v

# Test watch function
pytest test/watch_test.py -v
```

---

## 10. Conclusion

This implementation successfully completes all 5 problems:

1. ✅ **Problem 1**: Board ADT with all game rules
2. ✅ **Problem 2**: Web server integration
3. ✅ **Problem 3**: Concurrent players with waiting
4. ✅ **Problem 4**: Map function with pairwise consistency
5. ✅ **Problem 5**: Watch function for responsive UI

The code follows all required structures, includes comprehensive tests, and handles concurrent operations correctly without crashes.

