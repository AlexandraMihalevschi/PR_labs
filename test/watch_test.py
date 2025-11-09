"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import pytest
import asyncio
from src.board import Board
from src.commands import watch, flip, look, map_cards


"""
Tests for Problem 5: Watch function for board changes.
"""


class TestWatchFunction:
    """Tests for the watch() function."""
    
    @pytest.mark.asyncio
    async def test_watch_detects_card_turned_face_up(self):
        """Test that watch detects when a card is turned face up."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Start watching
        async def watch_and_get_state():
            state = await watch(board, 'player1')
            return state
        
        watch_task = asyncio.create_task(watch_and_get_state())
        await asyncio.sleep(0.01)
        
        # Flip a card (should trigger watch)
        await flip(board, 'player2', 0, 0)
        
        # Watch should complete
        state = await watch_task
        
        # Verify state shows the face-up card
        assert 'up A' in state or 'my A' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_detects_card_removed(self):
        """Test that watch detects when a card is removed."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Match two cards
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 2)  # Match
        
        # Start watching
        async def watch_and_get_state():
            state = await watch(board, 'player2')
            return state
        
        watch_task = asyncio.create_task(watch_and_get_state())
        await asyncio.sleep(0.01)
        
        # Remove cards (cleanup)
        await flip(board, 'player1', 1, 0)
        
        # Watch should complete
        state = await watch_task
        
        # Verify state shows removed cards
        assert 'none' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_detects_card_turned_face_down(self):
        """Test that watch detects when a card is turned face down."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip a non-matching pair
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 1)  # Doesn't match
        
        # Start watching
        async def watch_and_get_state():
            state = await watch(board, 'player2')
            return state
        
        watch_task = asyncio.create_task(watch_and_get_state())
        await asyncio.sleep(0.01)
        
        # Trigger cleanup (cards turn face down)
        await flip(board, 'player1', 1, 0)
        
        # Watch should complete
        state = await watch_task
        
        # Verify cards are face down
        assert 'down' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_detects_card_value_change(self):
        """Test that watch detects when a card value changes via map."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip a card to see its value
        await flip(board, 'player1', 0, 0)
        
        # Start watching
        async def watch_and_get_state():
            state = await watch(board, 'player2')
            return state
        
        watch_task = asyncio.create_task(watch_and_get_state())
        await asyncio.sleep(0.01)
        
        # Apply map to change card value
        async def transform(card: str) -> str:
            return 'X' if card == 'A' else card
        
        await map_cards(board, 'player1', transform)
        
        # Watch should complete
        state = await watch_task
        
        # Verify card value changed
        assert 'X' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_does_not_detect_control_changes(self):
        """Test that watch does NOT detect control changes without state changes."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip a card face up (player1 controls it)
        await flip(board, 'player1', 0, 0)
        
        # Wait a bit to ensure card is face up
        await asyncio.sleep(0.01)
        
        # Start watching
        watch_completed = False
        
        async def watch_and_set_flag():
            nonlocal watch_completed
            await watch(board, 'player2')
            watch_completed = True
        
        watch_task = asyncio.create_task(watch_and_set_flag())
        await asyncio.sleep(0.01)
        
        # Relinquish control (card stays face up, just uncontrolled)
        await flip(board, 'player1', 0, 1)  # Non-matching, relinquishes control
        
        # Wait a bit - watch should NOT complete yet
        await asyncio.sleep(0.01)
        assert not watch_completed, "Watch should not complete on control change alone"
        
        # Now trigger cleanup (card turns face down)
        await flip(board, 'player1', 1, 0)
        
        # Now watch should complete
        await watch_task
        assert watch_completed
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_does_not_detect_failed_operations(self):
        """Test that watch does NOT detect failed operations."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Start watching
        watch_completed = False
        
        async def watch_and_set_flag():
            nonlocal watch_completed
            await watch(board, 'player1')
            watch_completed = True
        
        watch_task = asyncio.create_task(watch_and_set_flag())
        await asyncio.sleep(0.01)
        
        # Try to flip an empty space (should fail, no change)
        try:
            await flip(board, 'player1', 10, 10)  # Out of bounds
        except (ValueError, IndexError):
            pass
        
        # Wait a bit - watch should NOT complete
        await asyncio.sleep(0.01)
        assert not watch_completed, "Watch should not complete on failed operation"
        
        # Cancel watch task
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_multiple_watchers(self):
        """Test that multiple watchers can watch simultaneously."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Two players start watching
        async def player1_watch():
            return await watch(board, 'player1')
        
        async def player2_watch():
            return await watch(board, 'player2')
        
        task1 = asyncio.create_task(player1_watch())
        task2 = asyncio.create_task(player2_watch())
        await asyncio.sleep(0.01)
        
        # Flip a card (should notify both watchers)
        await flip(board, 'player3', 0, 0)
        
        # Both should complete
        state1 = await task1
        state2 = await task2
        
        assert 'up A' in state1 or 'my A' in state1
        assert 'up A' in state2 or 'my A' in state2
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_while_other_operations_continue(self):
        """Test that watch doesn't block other operations."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Start watching
        watch_task = asyncio.create_task(watch(board, 'player1'))
        await asyncio.sleep(0.01)
        
        # Other operations should work normally
        await look(board, 'player2')  # Should work immediately
        await flip(board, 'player2', 0, 0)  # Should work immediately
        
        # Watch should complete
        state = await watch_task
        assert 'up A' in state or 'my A' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_watch_waits_until_change(self):
        """Test that watch waits until an actual change occurs."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        watch_completed = False
        
        async def watch_and_set_flag():
            nonlocal watch_completed
            await watch(board, 'player1')
            watch_completed = True
        
        watch_task = asyncio.create_task(watch_and_set_flag())
        await asyncio.sleep(0.02)
        
        # No changes yet, watch should still be waiting
        assert not watch_completed
        
        # Now make a change
        await flip(board, 'player2', 0, 0)
        
        # Watch should complete
        await watch_task
        assert watch_completed
        
        board.check_rep()

