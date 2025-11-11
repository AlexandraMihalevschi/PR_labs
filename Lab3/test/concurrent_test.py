"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import pytest
import asyncio
from src.board import Board
from src.commands import flip, look


"""
Tests for Problem 3: Concurrent players and async waiting.
"""


class TestConcurrentPlayers:
    """Tests for concurrent player operations."""
    
    @pytest.mark.asyncio
    async def test_rule_1d_waiting_for_controlled_card(self):
        """Test Rule 1-D: Player waits when card is controlled by another player."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips a card and controls it
        await flip(board, 'player1', 0, 0)
        
        # Player2 tries to flip the same card - should wait
        async def player2_flip():
            await flip(board, 'player2', 0, 0)
            return True
        
        # Start player2's flip (it will wait)
        player2_task = asyncio.create_task(player2_flip())
        
        # Give it a moment to start waiting
        await asyncio.sleep(0.01)
        
        # Player1 relinquishes control by flipping a second card
        await flip(board, 'player1', 0, 1)  # Non-matching, so player1 relinquishes control
        
        # Player2 should now be able to take control
        await asyncio.sleep(0.01)
        
        # Player1 flips a new first card (cleanup)
        await flip(board, 'player1', 1, 0)
        
        # Now player2 should have control
        result = await player2_task
        
        # Verify player2 controls the card
        state = await look(board, 'player2')
        lines = state.strip().split('\n')
        assert 'my A' in lines[1] or lines[1] == 'my A'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_multiple_players_wait_for_same_card(self):
        """Test that multiple players can wait for the same card."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls a card
        await flip(board, 'player1', 0, 0)
        
        # Player2 and Player3 both try to flip the same card
        async def player2_flip():
            await flip(board, 'player2', 0, 0)
            return 'player2'
        
        async def player3_flip():
            await flip(board, 'player3', 0, 0)
            return 'player3'
        
        # Start both players
        task2 = asyncio.create_task(player2_flip())
        task3 = asyncio.create_task(player3_flip())
        
        # Give them time to start waiting
        await asyncio.sleep(0.05)
        
        # Player1 relinquishes control
        await flip(board, 'player1', 0, 1)  # Non-matching
        
        # Give waiting players time to wake up and try to take control
        await asyncio.sleep(0.1)
        
        # Now do cleanup (this might turn cards face down, but players should have taken control by now)
        await flip(board, 'player1', 1, 0)  # Cleanup
        
        # Give a bit more time for any final operations
        await asyncio.sleep(0.1)
        
        # One of the players should get control - use timeout to prevent infinite hang
        try:
            results = await asyncio.wait_for(
                asyncio.gather(task2, task3, return_exceptions=True),
                timeout=2.0
            )
            # At least one should succeed
            assert any(not isinstance(r, Exception) for r in results)
        except asyncio.TimeoutError:
            # If timeout, at least check that one task completed
            if task2.done():
                result2 = await task2
                assert result2 == 'player2' or isinstance(result2, Exception)
            elif task3.done():
                result3 = await task3
                assert result3 == 'player3' or isinstance(result3, Exception)
            else:
                # Both still waiting - this shouldn't happen
                raise AssertionError("Both players are still waiting after timeout")
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_concurrent_players_flip_different_cards(self):
        """Test that concurrent players can flip different cards simultaneously."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Two players flip different cards concurrently
        async def player1_flip():
            await flip(board, 'player1', 0, 0)
            return 'player1'
        
        async def player2_flip():
            await flip(board, 'player2', 0, 4)  # Another A card (matching)
            return 'player2'
        
        # Execute concurrently
        results = await asyncio.gather(player1_flip(), player2_flip())
        
        # Both should succeed
        assert 'player1' in results
        assert 'player2' in results
        
        # Verify both players control their cards
        state1 = await look(board, 'player1')
        assert 'my A' in state1
        
        state2 = await look(board, 'player2')
        assert 'my A' in state2
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_waiting_player_fails_when_card_removed(self):
        """Test that a waiting player fails when card is removed."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 matches two cards (both A)
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 4)  # Match
        
        # Player2 tries to flip one of the matched cards (should wait)
        async def player2_flip():
            try:
                await flip(board, 'player2', 0, 0)
                return False
            except ValueError as e:
                if 'No card' in str(e):
                    return True
                raise
        
        task = asyncio.create_task(player2_flip())
        await asyncio.sleep(0.01)
        
        # Player1 flips a new card (cleanup removes matched cards)
        await flip(board, 'player1', 1, 0)
        
        # Player2 should fail because card was removed
        result = await task
        assert result is True  # Should have caught ValueError
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_waiting_player_succeeds_when_card_freed(self):
        """Test that a waiting player successfully takes control when card is freed."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls a card
        await flip(board, 'player1', 0, 0)
        
        # Player2 tries to flip it (should wait)
        async def player2_flip():
            await flip(board, 'player2', 0, 0)
            return True
        
        task = asyncio.create_task(player2_flip())
        await asyncio.sleep(0.01)
        
        # Player1 relinquishes control (non-matching second card)
        await flip(board, 'player1', 0, 1)  # Doesn't match
        
        # Wait a bit for notification
        await asyncio.sleep(0.01)
        
        # Player1 flips new card (cleanup - but card should still be available if player2 took control)
        await flip(board, 'player1', 1, 0)
        
        # Player2 should have control now
        await task
        
        state = await look(board, 'player2')
        assert 'my A' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_waiting_while_other_players_continue(self):
        """Test that while one player waits, other players can continue playing."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls a card
        await flip(board, 'player1', 0, 0)
        
        # Player2 tries to flip player1's card (will wait)
        async def player2_flip():
            await asyncio.sleep(0.01)  # Small delay
            await flip(board, 'player2', 0, 0)
            return True
        
        task2 = asyncio.create_task(player2_flip())
        await asyncio.sleep(0.01)
        
        # Player3 flips a different card (should succeed immediately)
        await flip(board, 'player3', 1, 0)
        
        # Verify player3's card is flipped
        state3 = await look(board, 'player3')
        assert 'my B' in state3
        
        # Player1 relinquishes control
        await flip(board, 'player1', 0, 1)
        await flip(board, 'player1', 1, 1)
        
        # Player2 should now get control
        await task2
        
        state2 = await look(board, 'player2')
        assert 'my A' in state2 or 'up A' in state2
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_concurrent_matching_sequence(self):
        """Test concurrent players playing a complete matching sequence."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 and Player2 both try to match cards concurrently
        async def player1_sequence():
            await flip(board, 'player1', 0, 0)
            await asyncio.sleep(0.01)
            await flip(board, 'player1', 0, 2)  # Should match
            await asyncio.sleep(0.01)
            await flip(board, 'player1', 1, 0)  # Cleanup and new card
            return 'player1'
        
        async def player2_sequence():
            await asyncio.sleep(0.005)  # Slight delay
            await flip(board, 'player2', 0, 1)
            await asyncio.sleep(0.01)
            await flip(board, 'player2', 0, 3)  # Should match
            await asyncio.sleep(0.01)
            await flip(board, 'player2', 1, 1)  # Cleanup and new card
            return 'player2'
        
        # Execute concurrently
        results = await asyncio.gather(player1_sequence(), player2_sequence())
        
        assert 'player1' in results
        assert 'player2' in results
        
        board.check_rep()


class TestRule1DWaiting:
    """Specific tests for Rule 1-D waiting behavior."""
    
    @pytest.mark.asyncio
    async def test_wait_for_face_up_uncontrolled_becomes_controlled(self):
        """Test waiting when card becomes controlled by another player."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips a card face up but doesn't control it (simulate previous relinquish)
        board._face_up[0][0] = True
        board._controllers[0][0] = None
        
        # Player2 takes control
        await flip(board, 'player2', 0, 0)
        
        # Player1 tries to flip it (should wait)
        async def player1_flip():
            await flip(board, 'player1', 0, 0)
            return True
        
        task = asyncio.create_task(player1_flip())
        await asyncio.sleep(0.01)
        
        # Player2 relinquishes control
        await flip(board, 'player2', 0, 1)  # Non-matching
        await flip(board, 'player2', 1, 0)  # Cleanup
        
        # Player1 should now get control
        await task
        
        state = await look(board, 'player1')
        assert 'my A' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_wait_until_card_removed_fails(self):
        """Test that waiting player fails if card is removed while waiting."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 matches cards (both A)
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 4)  # Match
        
        # Player2 tries to flip one (will wait)
        async def player2_flip():
            await flip(board, 'player2', 0, 0)
            return True
        
        task = asyncio.create_task(player2_flip())
        await asyncio.sleep(0.01)
        
        # Player1 removes the card (cleanup)
        await flip(board, 'player1', 1, 0)
        
        # Player2 should fail
        with pytest.raises(ValueError, match='No card'):
            await task
        
        board.check_rep()

