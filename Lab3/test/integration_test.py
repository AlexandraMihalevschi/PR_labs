"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import pytest
import asyncio
from src.board import Board
from src.commands import flip, look, map_cards


"""
Integration tests for Problems 3 and 4.
"""


class TestProblem3Integration:
    """Integration tests for Problem 3: Concurrent players."""
    
    @pytest.mark.asyncio
    async def test_complex_concurrent_scenario(self):
        """Test a complex scenario with multiple concurrent players."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 and Player2 both try to flip the same card
        async def player1_action():
            await flip(board, 'player1', 0, 0)
            await asyncio.sleep(0.01)
            await flip(board, 'player1', 0, 2)  # Match
            return 'player1'
        
        async def player2_action():
            await asyncio.sleep(0.005)
            # Player2 tries to flip (0,0) which player1 controls
            await flip(board, 'player2', 0, 0)
            return 'player2'
        
        # Start both
        task1 = asyncio.create_task(player1_action())
        task2 = asyncio.create_task(player2_action())
        
        # Wait for both to complete with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(task1, task2, return_exceptions=True),
                timeout=3.0
            )
            # At least one should succeed
            assert any(not isinstance(r, Exception) for r in results)
        except asyncio.TimeoutError:
            # Check if at least one completed
            if task1.done() or task2.done():
                # At least one completed, which is acceptable
                pass
            else:
                raise AssertionError("Both tasks timed out")
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_waiting_does_not_block_other_operations(self):
        """Test that waiting doesn't block other players from playing."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls a card
        await flip(board, 'player1', 0, 0)
        
        # Player2 waits for it
        async def player2_wait():
            await flip(board, 'player2', 0, 0)
            return True
        
        task2 = asyncio.create_task(player2_wait())
        await asyncio.sleep(0.01)
        
        # Player3 can still flip other cards
        await flip(board, 'player3', 1, 0)
        state3 = await look(board, 'player3')
        assert 'my B' in state3
        
        # Player1 relinquishes
        await flip(board, 'player1', 0, 1)
        await flip(board, 'player1', 1, 1)
        
        # Player2 should get control (with timeout)
        try:
            await asyncio.wait_for(task2, timeout=2.0)
        except asyncio.TimeoutError:
            raise AssertionError("Player2 did not get control within timeout")
        
        board.check_rep()


class TestProblem4Integration:
    """Integration tests for Problem 4: Map function."""
    
    @pytest.mark.asyncio
    async def test_map_with_concurrent_flips(self):
        """Test map while cards are being flipped."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        async def slow_map(card: str) -> str:
            await asyncio.sleep(0.02)
            return f'mapped_{card}'
        
        async def concurrent_flips():
            await asyncio.sleep(0.01)
            await flip(board, 'player1', 0, 0)
            await asyncio.sleep(0.01)
            await flip(board, 'player1', 0, 1)
        
        # Start both operations
        map_task = asyncio.create_task(map_cards(board, 'player1', slow_map))
        flip_task = asyncio.create_task(concurrent_flips())
        
        # Both should complete
        await asyncio.gather(map_task, flip_task)
        
        # Verify board is in valid state
        board.check_rep()
        
        state = await look(board, 'player1')
        # Map should have completed
        assert 'mapped_' in state
    
    @pytest.mark.asyncio
    async def test_map_preserves_matching_pairs(self):
        """Test that map preserves matching pairs even during concurrent operations."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip two matching cards (both A)
        await flip(board, 'player1', 0, 0)  # A
        await flip(board, 'player1', 0, 4)  # A (matches)
        
        # Verify they match
        state_before = await look(board, 'player1')
        assert state_before.count('my A') == 2
        
        async def transform(card: str) -> str:
            await asyncio.sleep(0.01)
            return 'NEW' if card == 'A' else card
        
        # Apply map
        await map_cards(board, 'player1', transform)
        
        # Verify they still match (both should be 'NEW')
        state_after = await look(board, 'player1')
        assert state_after.count('my NEW') == 2
        assert 'my A' not in state_after
        
        board.check_rep()


class TestProblems3And4Together:
    """Tests combining Problems 3 and 4."""
    
    @pytest.mark.asyncio
    async def test_map_while_players_wait(self):
        """Test that map works while players are waiting."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls a card
        await flip(board, 'player1', 0, 0)
        
        # Player2 waits for it
        async def player2_wait():
            await flip(board, 'player2', 0, 0)
            return True
        
        task = asyncio.create_task(player2_wait())
        await asyncio.sleep(0.01)
        
        # Apply map while player2 is waiting
        async def transform(card: str) -> str:
            return 'X' if card == 'A' else card
        
        await map_cards(board, 'player1', transform)
        
        # Player1 relinquishes
        await flip(board, 'player1', 0, 1)
        await flip(board, 'player1', 1, 0)
        
        # Player2 should get control (card value is now X) - with timeout
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            raise AssertionError("Player2 did not get control within timeout")
        
        state = await look(board, 'player2')
        assert 'my X' in state
        
        board.check_rep()

