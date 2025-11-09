"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

from typing import Optional, List, Tuple, Dict
import re
import asyncio


class Board:
    """
    A mutable Memory Scramble game board.
    
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
        
        Args:
            rows: number of rows (must be > 0)
            columns: number of columns (must be > 0)
            cards: 2D list of card values, must be rows×columns
        Raises:
            ValueError if dimensions are invalid or cards don't match dimensions
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
        
        self.check_rep()
    
    def check_rep(self) -> None:
        """Check representation invariant."""
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
        """Returns the number of rows in the board."""
        return self._rows
    
    def get_columns(self) -> int:
        """Returns the number of columns in the board."""
        return self._columns
    
    def get_board_state(self, player_id: str) -> str:
        """
        Returns the board state from the perspective of the given player.
        
        Format:
        ROWxCOLUMN
        SPOT (one per line, row by row)
        where SPOT is: "none", "down", "up CARD", or "my CARD"
        
        Args:
            player_id: ID of the player viewing the board
        Returns:
            string representation of the board state
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
    
    def flip_card(self, player_id: str, row: int, column: int) -> None:
        """
        Tries to flip over a card, following the Memory Scramble gameplay rules.
        
        This is the synchronous version for Problems 1 & 2.
        For Problem 3, this will be made async to handle waiting.
        
        Rules:
        First card (player controls 0 cards):
          1-A: Empty space → fails (raises ValueError)
          1-B: Face down → turns face up, player controls it
          1-C: Face up, uncontrolled → player controls it
          1-D: Face up, controlled by another → waits (not implemented in sync version)
        
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
        
        controlled_cards = self._player_cards.get(player_id, [])
        num_controlled = len(controlled_cards)
        
        # Cleanup previous move (rule 3-A/B)
        # Cleanup happens when starting a new turn (0 controlled cards) OR after a match (2 controlled cards)
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
                        # Remove from player's controlled cards (we know player controls these)
                        if player_id in self._player_cards and (r, c) in self._player_cards[player_id]:
                            self._player_cards[player_id].remove((r, c))
                # Clean up empty player card lists
                if player_id in self._player_cards and not self._player_cards[player_id]:
                    del self._player_cards[player_id]
            else:
                # Rule 3-B: Turn face down if uncontrolled by any player
                # For each card that was part of the previous move:
                # - If it's still on the board
                # - And currently face up
                # - And not controlled by any player (including the original player who relinquished control)
                # Then turn it face down
                for r, c in prev_cards:
                    if (0 <= r < self._rows and 0 <= c < self._columns and
                        self._cards[r][c] is not None and
                        self._face_up[r][c] and
                        self._controllers[r][c] is None):
                        # Card is on board, face up, and uncontrolled - turn it face down
                        self._face_up[r][c] = False
            
            # Clear previous move
            self._previous_moves[player_id] = None
            
            # Update controlled cards list after cleanup
            controlled_cards = self._player_cards.get(player_id, [])
            num_controlled = len(controlled_cards)
        
        # First card (player controls 0 cards after cleanup, or had 0 to begin with)
        if num_controlled == 0:
            # Rule 1-A: Empty space
            if self._cards[row][column] is None:
                raise ValueError(f'No card at position ({row}, {column})')
            
            controller = self._controllers[row][column]
            
            # Rule 1-D: Controlled by another player
            # In sync version, we'll raise an error (waiting comes in Problem 3)
            if controller is not None and controller != player_id:
                raise ValueError(f'Card at ({row}, {column}) is controlled by another player')
            
            # Rule 1-B: Face down → turn face up and control
            if not self._face_up[row][column]:
                self._face_up[row][column] = True
                self._controllers[row][column] = player_id
                if player_id not in self._player_cards:
                    self._player_cards[player_id] = []
                self._player_cards[player_id].append((row, column))
            # Rule 1-C: Face up, uncontrolled → control it
            else:
                # Card is face up and controller is None (uncontrolled)
                assert controller is None, "Should have been handled by rule 1-D"
                self._controllers[row][column] = player_id
                if player_id not in self._player_cards:
                    self._player_cards[player_id] = []
                self._player_cards[player_id].append((row, column))
            
            # Clear previous move (starting fresh)
            self._previous_moves[player_id] = None
        
        # Second card (player controls 1 card)
        elif num_controlled == 1:
            first_card_pos = controlled_cards[0]
            first_row, first_col = first_card_pos
            
            # Rule 2-A: Empty space
            if self._cards[row][column] is None:
                # Relinquish control of first card
                self._relinquish_control(player_id, first_row, first_col)
                raise ValueError(f'No card at position ({row}, {column})')
            
            controller = self._controllers[row][column]
            
            # Rule 2-B: Controlled by any player (including self)
            # Check if card is face up and controlled
            if self._face_up[row][column] and controller is not None:
                # Relinquish control of first card (but it remains face up)
                self._relinquish_control(player_id, first_row, first_col)
                raise ValueError(f'Card at ({row}, {column}) is controlled by a player')
            
            # Rule 2-C: Face down → turn face up (if not already face up)
            if not self._face_up[row][column]:
                self._face_up[row][column] = True
            
            first_card_value = self._cards[first_row][first_col]
            second_card_value = self._cards[row][column]
            
            # Rule 2-D: Cards match
            if first_card_value == second_card_value:
                # Player keeps control of both cards
                self._controllers[row][column] = player_id
                self._player_cards[player_id].append((row, column))
                # Record successful match for cleanup
                self._previous_moves[player_id] = ([(first_row, first_col), (row, column)], True)
            
            # Rule 2-E: Cards don't match
            else:
                # Relinquish control of both cards
                self._relinquish_control(player_id, first_row, first_col)
                self._relinquish_control(player_id, row, column)
                # Record unsuccessful match for cleanup
                self._previous_moves[player_id] = ([(first_row, first_col), (row, column)], False)
        
        else:
            # This shouldn't happen - player should have 0, 1, or 2 controlled cards
            raise ValueError(f'Invalid state: Player {player_id} controls {num_controlled} cards')
        
        self.check_rep()
    
    def _relinquish_control(self, player_id: str, row: int, column: int) -> None:
        """
        Helper method to remove player's control of a card.
        The card remains face up.
        
        Args:
            player_id: ID of the player
            row: row index
            column: column index
        """
        if self._controllers[row][column] == player_id:
            self._controllers[row][column] = None
            if player_id in self._player_cards:
                if (row, column) in self._player_cards[player_id]:
                    self._player_cards[player_id].remove((row, column))
                # Clean up empty lists
                if not self._player_cards[player_id]:
                    del self._player_cards[player_id]
    
    def __str__(self) -> str:
        """Returns a string representation of the board for debugging."""
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
        
        Args:
            filename: path to game board file
        Returns:
            a new board with the size and cards from the file
        Raises:
            ValueError if the file cannot be read or is not a valid game board
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
