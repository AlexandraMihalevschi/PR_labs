"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

from typing import Optional, List, Tuple, Dict, Set, Callable, Awaitable
import re
import asyncio
from collections import defaultdict


class Board:
    """
    A mutable Memory Scramble game board with asynchronous support for concurrent players.
    
    A Board represents a grid of cards that players can flip over to find matching pairs.
    Cards can be face up or face down, controlled by players, or removed from the board.
    
    Representation:
    - _rows: number of rows in the board
    - _columns: number of columns in the board
    - _cards: 2D list of card values (strings), None if card is removed
    - _face_up: 2D list of booleans, True if card is face up, False if face down
    - _controllers: 2D list of player IDs (strings) or None, tracks who controls each card
    - _player_cards: maps player_id to list of (row, col) tuples of cards they control
    - _previous_moves: maps player_id to (cards_list, matched) tuple for cleanup rules
    - _waiting_players: maps (row, col) to list of asyncio.Event for players waiting on that card
    - _lock: asyncio.Lock for thread-safety
    - _map_locks: maps card value to asyncio.Lock for pairwise consistency in map operations
    
    Abstraction function:
    AF(self) = a Memory Scramble board with:
    - Grid size: _rows × _columns
    - For each position (r, c):
      - If _cards[r][c] is None: empty space (card removed)
      - If _cards[r][c] is a string: card with that value
      - _face_up[r][c] indicates if card is face up
      - _controllers[r][c] indicates which player controls it (None if uncontrolled)
    - _player_cards[player_id] = list of positions controlled by that player
    - _previous_moves[player_id] = (previous cards, whether they matched) for cleanup
    - _waiting_players[(r, c)] = list of events for players waiting to control card at (r, c)
    
    Representation invariant:
    - _rows > 0 and _columns > 0
    - len(_cards) == _rows
    - For all r in [0, _rows): len(_cards[r]) == _columns
    - len(_face_up) == _rows and len(_controllers) == _rows
    - For all r in [0, _rows): len(_face_up[r]) == _columns and len(_controllers[r]) == _columns
    - If _cards[r][c] is None, then _face_up[r][c] is False and _controllers[r][c] is None
    - If _controllers[r][c] is not None, then _face_up[r][c] is True
    - _player_cards[player_id] contains only valid positions where _controllers[row][col] == player_id
    - All positions in _player_cards[player_id] have _controllers set to player_id
    
    Safety from rep exposure:
    - All fields are private (start with _)
    - Methods return new lists/tuples, not references to internal representation
    - Player IDs are strings provided by clients, so no rep exposure concern
    """
    
    def __init__(self, rows: int, columns: int, cards: List[List[str]]):
        """
        Create a new board with the given dimensions and cards.
        
        Preconditions:
            - rows > 0
            - columns > 0
            - len(cards) == rows
            - For all i in [0, rows): len(cards[i]) == columns
            - All card values are non-empty strings of non-whitespace characters
        
        Args:
            rows: number of rows (must be > 0)
            columns: number of columns (must be > 0)
            cards: 2D list of card values, must be rows×columns
        
        Raises:
            ValueError if dimensions are invalid or cards don't match dimensions
        
        Postconditions:
            - self._rows == rows
            - self._columns == columns
            - self._cards contains copies of the input cards (no rep exposure)
            - All cards start face down
            - No cards are controlled
            - self.check_rep() passes
        """
        if rows <= 0 or columns <= 0:
            raise ValueError('Board dimensions must be positive')
        if len(cards) != rows:
            raise ValueError(f'Expected {rows} rows, got {len(cards)}')
        for i, row in enumerate(cards):
            if len(row) != columns:
                raise ValueError(f'Row {i} has {len(row)} columns, expected {columns}')
        
        self._rows = rows
        self._columns = columns
        # Make copies to avoid rep exposure
        self._cards = [row[:] for row in cards]
        # All cards start face down
        self._face_up = [[False for _ in range(columns)] for _ in range(rows)]
        # No cards are controlled initially
        self._controllers = [[None for _ in range(columns)] for _ in range(rows)]
        # Track which cards each player controls
        self._player_cards: Dict[str, List[Tuple[int, int]]] = {}
        # Track previous moves for cleanup (rule 3-A/B)
        self._previous_moves: Dict[str, Optional[Tuple[List[Tuple[int, int]], bool]]] = {}
        
        # Async support for Problem 3: waiting players
        self._waiting_players: Dict[Tuple[int, int], List[asyncio.Event]] = defaultdict(list)
        # Lock for thread-safety
        self._lock = asyncio.Lock()
        # Map locks for Problem 4: pairwise consistency (lock per card value)
        self._map_locks: Dict[str, asyncio.Lock] = {}
        # Track active map operations
        self._active_maps: Set[int] = set()
        self._map_counter = 0
        
        # Problem 5: Change watchers - list of events for players watching for changes
        self._change_watchers: List[asyncio.Event] = []
        
        self.check_rep()
    
    def check_rep(self) -> None:
        """
        Check representation invariant.
        
        Verifies that all representation invariants hold:
        - Dimensions are positive
        - All arrays have correct sizes
        - Removed cards are face down and uncontrolled
        - Controlled cards are face up
        - _player_cards is consistent with _controllers
        
        Raises:
            AssertionError if any invariant is violated
        """
        assert self._rows > 0 and self._columns > 0
        assert len(self._cards) == self._rows
        assert len(self._face_up) == self._rows
        assert len(self._controllers) == self._rows
        
        for r in range(self._rows):
            assert len(self._cards[r]) == self._columns
            assert len(self._face_up[r]) == self._columns
            assert len(self._controllers[r]) == self._columns
            
            for c in range(self._columns):
                # If card is removed, it must be face down and uncontrolled
                if self._cards[r][c] is None:
                    assert not self._face_up[r][c], f'Removed card at ({r},{c}) cannot be face up'
                    assert self._controllers[r][c] is None, f'Removed card at ({r},{c}) cannot be controlled'
                # If card is controlled, it must be face up
                if self._controllers[r][c] is not None:
                    assert self._face_up[r][c], f'Controlled card at ({r},{c}) must be face up'
        
        # Verify _player_cards is consistent with _controllers
        for player_id, cards_list in self._player_cards.items():
            for row, col in cards_list:
                assert 0 <= row < self._rows and 0 <= col < self._columns
                assert self._controllers[row][col] == player_id
                assert self._cards[row][col] is not None
        
        # Verify _controllers matches _player_cards
        for r in range(self._rows):
            for c in range(self._columns):
                if self._controllers[r][c] is not None:
                    player_id = self._controllers[r][c]
                    assert (r, c) in self._player_cards.get(player_id, [])
    
    def get_rows(self) -> int:
        """
        Returns the number of rows in the board.
        
        Returns:
            number of rows (always > 0)
        """
        return self._rows
    
    def get_columns(self) -> int:
        """
        Returns the number of columns in the board.
        
        Returns:
            number of columns (always > 0)
        """
        return self._columns
    
    async def look(self, player_id: str) -> str:
        """
        Looks at the current state of the board.
        
        This is a convenience method that matches the TypeScript Board interface pattern.
        It's an alias for get_board_state() but made async for consistency.
        
        Args:
            player_id: ID of the player viewing the board
        Returns:
            Board state string
        """
        return self.get_board_state(player_id)
    
    def get_board_state(self, player_id: str) -> str:
        """
        Returns the board state from the perspective of the given player.
        
        Preconditions:
            - player_id is a nonempty string
        
        Format:
        ROWxCOLUMN
        SPOT (one per line, row by row)
        where SPOT is: "none", "down", "up CARD", or "my CARD"
        
        Args:
            player_id: ID of the player viewing the board
        
        Returns:
            string representation of the board state in the format described above.
            The string ends with a newline character.
        
        Postconditions:
            - Return value is a valid board state string
            - All cards are represented exactly once
            - "my CARD" appears only for cards controlled by player_id
        """
        lines = [f'{self._rows}x{self._columns}']
        
        for r in range(self._rows):
            for c in range(self._columns):
                if self._cards[r][c] is None:
                    lines.append('none')
                elif not self._face_up[r][c]:
                    lines.append('down')
                elif self._controllers[r][c] == player_id:
                    lines.append(f'my {self._cards[r][c]}')
                else:
                    lines.append(f'up {self._cards[r][c]}')
        
        return '\n'.join(lines) + '\n'
    
    async def flip(self, player_id: str, row: int, column: int) -> str:
        """
        Tries to flip over a card and returns the board state.
        
        This is a convenience method that combines flip_card() and get_board_state().
        Matches the TypeScript Board interface pattern.
        
        Args:
            player_id: ID of the player making the flip
            row: row index (0-based)
            column: column index (0-based)
        Returns:
            Board state string after the flip
        Raises:
            ValueError if the flip operation fails (rules 1-A, 2-A, 2-B)
            IndexError if row or column is out of bounds
        """
        await self.flip_card(player_id, row, column)
        return self.get_board_state(player_id)
    
    async def flip_card(self, player_id: str, row: int, column: int) -> None:
        """
        Tries to flip over a card, following the Memory Scramble gameplay rules.
        
        This is the async version for Problem 3, supporting waiting for cards controlled by others.
        
        Rules:
        First card (player controls 0 cards):
          1-A: Empty space → fails (raises ValueError)
          1-B: Face down → turns face up, player controls it
          1-C: Face up, uncontrolled → player controls it
          1-D: Face up, controlled by another → waits until card becomes available
        
        Second card (player controls 1 card):
          2-A: Empty space → fails, relinquish first card
          2-B: Controlled by any player → fails, relinquish first card
          2-C: Face down → turns face up
          2-D: Cards match → player keeps control of both
          2-E: Cards don't match → player relinquishes control of both
        
        Cleanup (when flipping new first card):
          3-A: Previous cards matched → remove them, relinquish control
          3-B: Previous cards didn't match → turn face down if uncontrolled
        
        Args:
            player_id: ID of the player making the flip
            row: row index (0-based)
            column: column index (0-based)
        Raises:
            ValueError if the flip operation fails (rules 1-A, 2-A, 2-B)
            IndexError if row or column is out of bounds
        """
        if not (0 <= row < self._rows and 0 <= column < self._columns):
            raise IndexError(f'Position ({row}, {column}) is out of bounds')
        
        # Retry loop for waiting (Rule 1-D)
        while True:
            event_to_wait = None
            async with self._lock:
                controlled_cards = self._player_cards.get(player_id, [])
                num_controlled = len(controlled_cards)
                
                # Cleanup previous move (rule 3-A/B)
                if player_id in self._previous_moves and self._previous_moves[player_id] is not None:
                    prev_cards, prev_matched = self._previous_moves[player_id]
                    
                    if prev_matched:
                        # Rule 3-A: Remove matched cards
                        for r, c in prev_cards:
                            if (0 <= r < self._rows and 0 <= c < self._columns and 
                                self._cards[r][c] is not None):
                                # Remove card and clear control
                                self._cards[r][c] = None
                                self._face_up[r][c] = False
                                self._controllers[r][c] = None
                                # Remove from player's controlled cards
                                if player_id in self._player_cards and (r, c) in self._player_cards[player_id]:
                                    self._player_cards[player_id].remove((r, c))
                                # Notify waiting players (card is now gone, they should fail)
                                self._notify_waiting_players((r, c))
                                # Notify change watchers (card removed)
                                self._notify_change_watchers()
                        # Clean up empty player card lists
                        if player_id in self._player_cards and not self._player_cards[player_id]:
                            del self._player_cards[player_id]
                    else:
                        # Rule 3-B: Turn face down if uncontrolled
                        for r, c in prev_cards:
                            if (0 <= r < self._rows and 0 <= c < self._columns and
                                self._cards[r][c] is not None and
                                self._face_up[r][c] and
                                self._controllers[r][c] is None):
                                # Card is on board, face up, and uncontrolled - turn it face down
                                self._face_up[r][c] = False
                                # Notify waiting players (card state changed)
                                self._notify_waiting_players((r, c))
                                # Notify change watchers (card turned face down)
                                self._notify_change_watchers()
                    
                    # Clear previous move
                    self._previous_moves[player_id] = None
                    
                    # Update controlled cards list after cleanup
                    controlled_cards = self._player_cards.get(player_id, [])
                    num_controlled = len(controlled_cards)
                
                # Check if the card still exists (it might have been removed while waiting)
                # This check must happen after cleanup but before trying to flip
                # This ensures waiting players fail immediately when their card is removed
                if self._cards[row][column] is None:
                    # If player was waiting for their first card, fail immediately
                    if num_controlled == 0:
                        raise ValueError(f'No card at position ({row}, {column})')
                    # If player was waiting for their second card, relinquish first card and fail
                    elif num_controlled == 1:
                        first_card_pos = controlled_cards[0]
                        first_row, first_col = first_card_pos
                        # Relinquish control of first card (but it remains face up)
                        self._relinquish_control(player_id, first_row, first_col)
                        # Record previous move for cleanup (Rule 3-B): one card that was relinquished
                        self._previous_moves[player_id] = ([(first_row, first_col)], False)
                        self._notify_waiting_players((first_row, first_col))
                        raise ValueError(f'No card at position ({row}, {column})')
                
                # First card (player controls 0 cards after cleanup, or had 0 to begin with)
                if num_controlled == 0:
                    
                    controller = self._controllers[row][column]
                    
                    # Rule 1-D: Controlled by another player - wait
                    if controller is not None and controller != player_id:
                        # Create event and add to waiting list
                        wait_event = asyncio.Event()
                        self._waiting_players[(row, column)].append(wait_event)
                        event_to_wait = wait_event
                    else:
                        # Can proceed with flip
                        # Rule 1-B: Face down → turn face up and control
                        if not self._face_up[row][column]:
                            self._face_up[row][column] = True
                            self._controllers[row][column] = player_id
                            if player_id not in self._player_cards:
                                self._player_cards[player_id] = []
                            self._player_cards[player_id].append((row, column))
                            # Notify waiting players and change watchers
                            self._notify_waiting_players((row, column))
                            self._notify_change_watchers()
                        # Rule 1-C: Face up, uncontrolled → control it
                        elif controller is None:
                            self._controllers[row][column] = player_id
                            if player_id not in self._player_cards:
                                self._player_cards[player_id] = []
                            self._player_cards[player_id].append((row, column))
                            # Notify waiting players (no change watcher - card already face up)
                            self._notify_waiting_players((row, column))
                        
                        # Clear previous move (starting fresh)
                        self._previous_moves[player_id] = None
                        self.check_rep()
                        return  # Successfully flipped
                
                # Second card (player controls 1 card)
                elif num_controlled == 1:
                    first_card_pos = controlled_cards[0]
                    first_row, first_col = first_card_pos
                    
                    # Rule 2-A: Empty space
                    if self._cards[row][column] is None:
                        # Relinquish control of first card (but it remains face up)
                        self._relinquish_control(player_id, first_row, first_col)
                        # Record previous move for cleanup (Rule 3-B): one card that was relinquished
                        self._previous_moves[player_id] = ([(first_row, first_col)], False)
                        self._notify_waiting_players((first_row, first_col))
                        raise ValueError(f'No card at position ({row}, {column})')
                    
                    controller = self._controllers[row][column]
                    
                    # Rule 2-B: Controlled by any player (including self)
                    # Check if card is face up and controlled
                    if self._face_up[row][column] and controller is not None:
                        # Relinquish control of first card (but it remains face up)
                        self._relinquish_control(player_id, first_row, first_col)
                        # Record previous move for cleanup (Rule 3-B): one card that was relinquished
                        self._previous_moves[player_id] = ([(first_row, first_col)], False)
                        self._notify_waiting_players((first_row, first_col))
                        raise ValueError(f'Card at ({row}, {column}) is controlled by a player')
                    
                    # Rule 2-C: Face down → turn face up (if not already face up)
                    if not self._face_up[row][column]:
                        self._face_up[row][column] = True
                        # Notify waiting players and change watchers
                        self._notify_waiting_players((row, column))
                        self._notify_change_watchers()
                    
                    first_card_value = self._cards[first_row][first_col]
                    second_card_value = self._cards[row][column]
                    
                    # Rule 2-D: Cards match
                    if first_card_value == second_card_value:
                        # Player keeps control of both cards
                        self._controllers[row][column] = player_id
                        self._player_cards[player_id].append((row, column))
                        # Record successful match for cleanup
                        self._previous_moves[player_id] = ([(first_row, first_col), (row, column)], True)
                        # Notify waiting players
                        self._notify_waiting_players((row, column))
                    
                    # Rule 2-E: Cards don't match
                    else:
                        # Relinquish control of both cards
                        self._relinquish_control(player_id, first_row, first_col)
                        self._relinquish_control(player_id, row, column)
                        # Record unsuccessful match for cleanup
                        self._previous_moves[player_id] = ([(first_row, first_col), (row, column)], False)
                        # Notify waiting players
                        self._notify_waiting_players((first_row, first_col))
                        self._notify_waiting_players((row, column))
                    
                    self.check_rep()
                    return  # Successfully flipped
                
                else:
                    # This shouldn't happen - player should have 0, 1, or 2 controlled cards
                    raise ValueError(f'Invalid state: Player {player_id} controls {num_controlled} cards')
            
            # If we need to wait, do so outside the lock
            if event_to_wait is not None:
                await event_to_wait.wait()
                # Loop back to try again
            else:
                break
    
    def _notify_waiting_players(self, position: Tuple[int, int]) -> None:
        """
        Notify all players waiting on a card at the given position.
        
        Preconditions:
            - Must be called while holding self._lock
            - position is a valid (row, column) tuple
        
        Args:
            position: (row, column) tuple
        
        Postconditions:
            - All events in _waiting_players[position] are set
            - _waiting_players[position] is cleared
        """
        if position in self._waiting_players:
            events = self._waiting_players[position]
            # Set all events to notify waiting players
            for event in events:
                event.set()
            # Clear the list (players will create new events if they need to wait again)
            self._waiting_players[position].clear()
            # If the list is now empty and the card is removed, delete the entry
            # to prevent stale state from affecting future operations
            if len(events) > 0 and self._cards[position[0]][position[1]] is None:
                # We just notified players about a removed card, so delete the entry
                del self._waiting_players[position]
    
    def _notify_change_watchers(self) -> None:
        """
        Notify all players watching for board changes.
        
        Preconditions:
            - Must be called while holding self._lock
            - A board change has just occurred (card flipped, removed, or value changed)
        
        Postconditions:
            - All events in _change_watchers are set
            - _change_watchers is cleared
        """
        # Set all events to notify watchers
        for event in self._change_watchers:
            event.set()
        # Clear the list (watchers will create new events if they want to watch again)
        self._change_watchers.clear()
    
    async def watch(self, player_id: str) -> str:
        """
        Watches the board for a change and returns the board state.
        
        This is a convenience method that combines watch_for_change() and get_board_state().
        Matches the TypeScript Board interface pattern.
        
        Args:
            player_id: ID of the player watching the board
        Returns:
            Board state string after a change occurs
        """
        await self.watch_for_change()
        return self.get_board_state(player_id)
    
    async def watch_for_change(self) -> None:
        """
        Wait for the next board change.
        
        A change is defined as:
        - Cards turning face up or face down
        - Cards being removed from the board
        - Cards changing from one string to a different string
        
        Changes that do NOT count:
        - Taking control or relinquishing control without changing face up/down state
        - Failed operations (e.g., trying to flip an empty space)
        
        Preconditions:
            - None (can be called at any time)
        
        Returns:
            None (just waits until a change occurs)
        
        Postconditions:
            - A board change has occurred (card flipped, removed, or value changed)
            - The method returns after the change is complete
        """
        # Create an event for this watcher
        watch_event = asyncio.Event()
        
        async with self._lock:
            # Add to watchers list
            self._change_watchers.append(watch_event)
        
        # Wait for notification (outside the lock)
        await watch_event.wait()
        # Event was set, meaning a change occurred
    
    def _relinquish_control(self, player_id: str, row: int, column: int) -> None:
        """
        Helper method to remove player's control of a card.
        The card remains face up.
        
        Preconditions:
            - 0 <= row < self._rows
            - 0 <= column < self._columns
            - Must be called while holding self._lock
        
        Args:
            player_id: ID of the player
            row: row index
            column: column index
        
        Postconditions:
            - If the card was controlled by player_id, it is no longer controlled
            - The card remains face up
            - _player_cards[player_id] no longer contains (row, column)
        """
        if self._controllers[row][column] == player_id:
            self._controllers[row][column] = None
            if player_id in self._player_cards:
                if (row, column) in self._player_cards[player_id]:
                    self._player_cards[player_id].remove((row, column))
                # Clean up empty lists
                if not self._player_cards[player_id]:
                    del self._player_cards[player_id]
    
    async def map(self, player_id: str, f: Callable[[str], Awaitable[str]]) -> str:
        """
        Modifies board by replacing every card with f(card) and returns the board state.
        
        This is a convenience method that combines map_cards() and get_board_state().
        Matches the TypeScript Board interface pattern.
        
        Args:
            player_id: ID of the player applying the map
            f: async function from cards to cards
        Returns:
            Board state string after the replacement
        """
        await self.map_cards(player_id, f)
        return self.get_board_state(player_id)
    
    async def map_cards(self, player_id: str, f: Callable[[str], Awaitable[str]]) -> None:
        """
        Modifies board by replacing every card with f(card), maintaining pairwise consistency.
        
        This operation can interleave with other operations. If two cards match at the start,
        they will continue to match throughout the operation (pairwise consistency).
        
        The implementation ensures that all cards with the same value are replaced atomically,
        so matching cards remain matching even if the map operation interleaves with other operations.
        
        Preconditions:
            - f is a mathematical function (same input always produces same output)
            - f(card) returns a valid card string for any card on the board
        
        Args:
            player_id: ID of the player applying the map (for consistency, not used in logic)
            f: async function from cards to cards
        
        Postconditions:
            - All cards with value v are replaced with f(v)
            - Cards with the same original value still match after transformation
            - Face up/down and control states are unchanged
            - Change watchers are notified if card values actually changed
        """
        # First, collect all unique card values and their positions while holding the lock
        card_value_positions: Dict[str, List[Tuple[int, int]]] = {}
        
        async with self._lock:
            # Collect all card values and their positions
            for r in range(self._rows):
                for c in range(self._columns):
                    if self._cards[r][c] is not None:
                        card_value = self._cards[r][c]
                        if card_value not in card_value_positions:
                            card_value_positions[card_value] = []
                        card_value_positions[card_value].append((r, c))
        
        # Process each unique card value (ensures pairwise consistency)
        # Cards with the same value are processed together atomically
        for card_value, positions in card_value_positions.items():
            # Get or create lock for this card value
            if card_value not in self._map_locks:
                async with self._lock:
                    if card_value not in self._map_locks:
                        self._map_locks[card_value] = asyncio.Lock()
            
            # Lock by card value to ensure matching cards are updated atomically
            async with self._map_locks[card_value]:
                # Apply transformation to get new value (outside board lock for concurrency)
                new_value = await f(card_value)
                
                # Update all cards with this value atomically
                cards_changed = False
                async with self._lock:
                    # Re-check positions (cards might have been removed or changed)
                    for r, c in positions:
                        if (0 <= r < self._rows and 0 <= c < self._columns and
                            self._cards[r][c] == card_value):
                            # Card still has the original value, update it
                            self._cards[r][c] = new_value
                            cards_changed = True
                    
                    # Ensure lock exists for new value (if different)
                    if new_value != card_value:
                        if new_value not in self._map_locks:
                            self._map_locks[new_value] = asyncio.Lock()
                    
                    # Notify change watchers if cards were actually changed
                    if cards_changed and new_value != card_value:
                        self._notify_change_watchers()
        
        # Final rep check (outside all locks for efficiency)
        async with self._lock:
            self.check_rep()
    
    def __str__(self) -> str:
        """
        Returns a string representation of the board for debugging.
        
        Returns:
            A human-readable string representation of the board state.
            Format: '---' for empty, '???' for face down, '[CARD]' for controlled, ' CARD ' for face up uncontrolled.
        """
        lines = []
        for r in range(self._rows):
            row_str = []
            for c in range(self._columns):
                if self._cards[r][c] is None:
                    row_str.append('---')
                elif not self._face_up[r][c]:
                    row_str.append('???')
                else:
                    controller = self._controllers[r][c]
                    if controller:
                        row_str.append(f'[{self._cards[r][c]}]')
                    else:
                        row_str.append(f' {self._cards[r][c]} ')
            lines.append(' '.join(row_str))
        return '\n'.join(lines)
    
    @staticmethod
    async def parse_from_file(filename: str) -> 'Board':
        """
        Make a new board by parsing a file.
        
        PS4 instructions: the specification of this method may not be changed.
        
        Preconditions:
            - filename is a valid path to a board file
            - The file exists and is readable
            - The file follows the BOARD_FILE grammar specified in the problem set
        
        Args:
            filename: path to game board file
        
        Returns:
            a new board with the size and cards from the file
        
        Raises:
            ValueError if the file cannot be read or is not a valid game board
            FileNotFoundError if the file does not exist (wrapped in ValueError)
            IOError if there is an error reading the file (wrapped in ValueError)
        
        Postconditions:
            - Returned board has dimensions and cards as specified in the file
            - All cards start face down
            - No cards are controlled
            - board.check_rep() passes
        """
        try:
            # Read file asynchronously
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise ValueError(f'File not found: {filename}')
        except IOError as e:
            raise ValueError(f'Error reading file {filename}: {e}')
        
        lines = content.strip().split('\n')
        if not lines:
            raise ValueError('Board file is empty')
        
        # Parse first line: ROWxCOLUMN
        first_line = lines[0].strip()
        match = re.match(r'^(\d+)x(\d+)$', first_line)
        if not match:
            raise ValueError(f'Invalid board dimensions format: {first_line}')
        
        rows = int(match.group(1))
        columns = int(match.group(2))
        
        # Parse cards
        card_lines = [line.strip() for line in lines[1:] if line.strip()]
        
        if len(card_lines) != rows * columns:
            raise ValueError(
                f'Expected {rows * columns} cards, got {len(card_lines)}'
            )
        
        # Validate cards (non-empty, non-whitespace)
        cards = []
        for i, line in enumerate(card_lines):
            # Card must be non-empty and contain no whitespace/newlines
            if not line or re.search(r'[\s\n\r]', line):
                raise ValueError(f'Invalid card at line {i+2}: {repr(line)}')
            cards.append(line)
        
        # Convert to 2D list (row by row)
        card_grid = []
        for r in range(rows):
            row = []
            for c in range(columns):
                index = r * columns + c
                row.append(cards[index])
            card_grid.append(row)
        
        return Board(rows, columns, card_grid)
