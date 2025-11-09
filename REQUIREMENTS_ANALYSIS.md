# Memory Scramble - Requirements Analysis

## Game Overview
Memory Scramble is a networked multiplayer version of Memory/Concentration where players turn over face-down cards simultaneously to find matching pairs.

## Key Components

### 1. Board File Format
```
BOARD_FILE ::= ROW "x" COLUMN NEWLINE (CARD NEWLINE)+
```
- First line: `ROWxCOLUMN` (e.g., `5x5`, `3x3`)
- Followed by exactly ROW×COLUMN cards, one per line
- Cards: non-empty strings of non-whitespace characters (can include emoji)
- Cards are listed row by row, left to right, top to bottom

### 2. Board State Format (HTTP Response)
```
BOARD_STATE ::= ROW "x" COLUMN NEWLINE (SPOT NEWLINE)+
SPOT ::= "none" | "down" | "up " CARD | "my " CARD
```
- `none`: No card at this location (removed)
- `down`: Face-down card (player cannot see value)
- `up CARD`: Face-up card, not controlled by this player
- `my CARD`: Face-up card controlled by this player

### 3. Gameplay Rules

#### First Card (when player has 0 controlled cards):
- **1-A**: Empty space → operation **fails**
- **1-B**: Face down → turns face up, player **controls** it
- **1-C**: Face up, uncontrolled → stays face up, player **controls** it
- **1-D**: Face up, controlled by another player → operation **waits** until available

#### Second Card (when player controls exactly 1 card):
- **2-A**: Empty space → operation **fails**, player relinquishes control of first card
- **2-B**: Face up, controlled by any player → operation **fails**, player relinquishes control of first card (no waiting to avoid deadlocks)
- **2-C**: Face down → turns face up
- **2-D**: Cards match → player **keeps control** of both cards (match!)
- **2-E**: Cards don't match → player **relinquishes control** of both cards

#### Cleanup (when player tries to flip a new first card):
- **3-A**: If player had matching pair → remove both cards from board, relinquish control
- **3-B**: Otherwise, for each previously controlled card: if still on board, face up, and not controlled by another player → turn face down

### 4. Player State Tracking
Each player needs to track:
- Which cards they currently control (0, 1, or 2 cards)
- What their previous move was (for cleanup rules 3-A/B)

### 5. Concurrency Requirements
- Multiple players can play simultaneously
- Operations must be thread-safe/concurrency-safe
- When a card is controlled by another player, operation must wait (asyncio)
- While waiting, other players can continue playing
- Need to handle race conditions when multiple players try to control the same card

### 6. API Functions

#### `look(player_id: str) -> str`
- Returns current board state from player's perspective
- Shows which cards player controls ("my") vs others control ("up") vs face down ("down") vs empty ("none")

#### `flip(player_id: str, row: int, column: int) -> str`
- Tries to flip a card following all gameplay rules (1-A through 3-B)
- May wait if card is controlled by another player (rule 1-D)
- Returns board state after the operation
- Raises error if operation fails (1-A, 2-A, 2-B)

#### `map_cards(player_id: str, f: Callable[[str], Awaitable[str]]) -> str`
- Replaces every card on board with f(card)
- Must maintain pairwise consistency: if two cards match before map, they must match after map (even if values change)
- Can interleave with other operations (look, flip)
- Multiple map operations can interleave
- Returns board state after replacement

#### `watch(player_id: str) -> str`
- Waits for any board change:
  - Card turns face up
  - Card turns face down
  - Card is removed
  - Card value changes (string changes)
- Returns board state when change occurs

## Implementation Strategy

### Data Structures Needed:
1. **Board Grid**: 2D array/list to store cards at each position
2. **Card State**: For each card, track:
   - Card value (string)
   - Face state (up/down)
   - Controller (player_id or None)
   - Whether card exists (removed or not)
3. **Player State**: For each player, track:
   - Currently controlled cards (list of (row, col))
   - Previous move state (for cleanup)

### Concurrency Mechanisms:
- Use `asyncio.Lock` or similar for card-level locking
- Use `asyncio.Condition` or `asyncio.Event` for waiting when cards are controlled
- Use `asyncio.Lock` for board-level operations to ensure atomicity
- Consider fine-grained locking (per-card) vs coarse-grained (whole board)

### Key Design Decisions:
1. **Card Representation**: 
   - Option A: Separate arrays for values, face states, controllers
   - Option B: Card objects with all state together
   
2. **Player State Storage**:
   - Option A: Track in Board class (centralized)
   - Option B: Track separately (distributed)
   
3. **Locking Strategy**:
   - Fine-grained: Lock per card (better concurrency)
   - Coarse-grained: Lock entire board (simpler, less concurrent)

4. **Waiting Mechanism**:
   - Use asyncio.Condition for each card to notify waiting players
   - When card becomes available, notify all waiting players

## Testing Strategy
- Test board file parsing
- Test single-player gameplay (flip, match, remove)
- Test multi-player concurrency (multiple players flipping same card)
- Test edge cases (empty spaces, already face-up cards, etc.)
- Test cleanup rules (3-A, 3-B)
- Test map_cards with pairwise consistency
- Test watch for board changes

## Problems Breakdown
- **Problem 1-2**: Implement Board ADT and connect to server (synchronous first, then async)
- **Problem 3**: Add concurrency support (async operations, waiting, locking)
- **Problem 4**: Implement map_cards with pairwise consistency
- **Problem 5**: Implement watch for board changes

