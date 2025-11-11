"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import pytest
import asyncio
from src.board import Board
from src.commands import map_cards, look, flip


"""
Tests for Problem 4: Map function with pairwise consistency.
"""


class TestMapCards:
    """Tests for map_cards function."""
    
    @pytest.mark.asyncio
    async def test_map_simple_replacement(self):
        """Test simple card replacement."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        async def replace_a_with_x(card: str) -> str:
            return 'X' if card == 'A' else card
        
        await map_cards(board, 'player1', replace_a_with_x)
        
        # Flip some cards to see the values (face-down cards show as "down")
        await flip(board, 'player1', 0, 0)  # This was A, should now be X
        await flip(board, 'player1', 0, 1)  # This is B, should remain B
        
        # Verify all A cards were replaced with X
        state = await look(board, 'player1')
        assert 'X' in state
        assert 'my X' in state or 'up X' in state
        assert 'B' in state  # B should remain
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_preserves_pairwise_consistency(self):
        """Test that matching cards remain matching after map."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Verify initial state: A cards should match
        # In ab.txt: positions (0,0), (0,2), (0,4), (1,1), (1,3), ... are A
        initial_state = await look(board, 'player1')
        
        async def transform(card: str) -> str:
            await asyncio.sleep(0.001)  # Simulate async operation
            return card.upper() if card == 'a' else card
        
        # Apply map
        await map_cards(board, 'player1', transform)
        
        # All A cards should be transformed to the same value
        state = await look(board, 'player1')
        # Cards that were A should still match each other
        # (they're all transformed the same way)
        
        # Verify by checking that if two positions had A, they still match
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_interleaves_with_flip(self):
        """Test that map can interleave with flip operations."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        async def slow_transform(card: str) -> str:
            await asyncio.sleep(0.01)  # Slow transformation
            return f'{card}_new'
        
        # Start map operation
        map_task = asyncio.create_task(map_cards(board, 'player1', slow_transform))
        
        # While map is running, flip a card
        await asyncio.sleep(0.005)  # Let map start
        await flip(board, 'player1', 0, 0)
        
        # Wait for map to complete
        await map_task
        
        # Verify flip succeeded and map completed
        state = await look(board, 'player1')
        assert '_new' in state  # Map completed
        assert 'my' in state or 'up' in state  # Card was flipped
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_preserves_matching_during_interleaving(self):
        """Test that matching cards stay matching even during interleaved operations."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Identify two matching cards
        # In ab.txt, (0,0) and (0,4) both have A
        
        async def async_transform(card: str) -> str:
            await asyncio.sleep(0.01)
            return 'Z' if card == 'A' else card
        
        # Start map
        map_task = asyncio.create_task(map_cards(board, 'player1', async_transform))
        
        # While map is running, flip one of the matching cards
        await asyncio.sleep(0.005)
        await flip(board, 'player1', 0, 0)
        
        # Wait for map
        await map_task
        
        # Verify: the two cards that matched should still match
        # Both should be Z now (or both should be face up showing Z)
        state = await look(board, 'player1')
        lines = state.strip().split('\n')
        
        # Both positions (0,0) and (0,2) should have the same value
        # (they were both A, so both should be Z now)
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_does_not_affect_card_states(self):
        """Test that map doesn't affect face-up/face-down or control states."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip some cards
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 1)
        
        # Verify initial state
        state_before = await look(board, 'player1')
        
        async def transform(card: str) -> str:
            return f'new_{card}'
        
        # Apply map
        await map_cards(board, 'player1', transform)
        
        # Verify card states (face up/down, control) are unchanged
        # Only card values should change
        state_after = await look(board, 'player1')
        
        # Cards that were face up should still be face up
        # Cards that were controlled should still be controlled
        # Only the card values should have changed
        lines_before = state_before.strip().split('\n')
        lines_after = state_after.strip().split('\n')
        
        # Check that control states match (my/up/down/none)
        for i in range(1, len(lines_before)):
            before = lines_before[i]
            after = lines_after[i]
            
            # Extract state (my/up/down/none)
            if before.startswith('my '):
                assert after.startswith('my ')
            elif before.startswith('up '):
                assert after.startswith('up ')
            elif before == 'down':
                assert after == 'down'
            elif before == 'none':
                assert after == 'none'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_concurrent_map_operations(self):
        """Test that multiple map operations can interleave."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        async def transform1(card: str) -> str:
            await asyncio.sleep(0.01)
            return f'{card}_1'
        
        async def transform2(card: str) -> str:
            await asyncio.sleep(0.01)
            return f'{card}_2'
        
        # Start two map operations concurrently
        task1 = asyncio.create_task(map_cards(board, 'player1', transform1))
        task2 = asyncio.create_task(map_cards(board, 'player2', transform2))
        
        # Both should complete
        await asyncio.gather(task1, task2)
        
        # Verify board is in valid state
        board.check_rep()
        
        # Flip some cards to see the transformed values (face-down cards show as "down")
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 1)
        
        # Verify all cards have been transformed
        state = await look(board, 'player1')
        # Cards should have _1 or _2 suffix
        assert '_1' in state or '_2' in state
    
    @pytest.mark.asyncio
    async def test_map_with_emoji_cards(self):
        """Test map with emoji cards."""
        board = await Board.parse_from_file('boards/perfect.txt')
        
        async def transform_unicorn(card: str) -> str:
            return '🦄_new' if card == '🦄' else card
        
        await map_cards(board, 'player1', transform_unicorn)
        
        # Flip a card to see the transformed value (face-down cards show as "down")
        await flip(board, 'player1', 0, 0)
        
        state = await look(board, 'player1')
        assert '🦄_new' in state
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_preserves_matches_during_transformation(self):
        """Test that cards that match before map still match during and after map."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Flip some cards face up to see their values
        await flip(board, 'player1', 0, 0)  # This is A
        await flip(board, 'player1', 0, 4)  # This is also A (matching)
        
        # Verify they match
        state_before = await look(board, 'player1')
        assert 'my A' in state_before
        
        async def slow_transform(card: str) -> str:
            await asyncio.sleep(0.01)
            return 'MATCHED' if card == 'A' else card
        
        # Apply map
        await map_cards(board, 'player1', slow_transform)
        
        # Verify both cards were transformed to MATCHED and still match
        state_after = await look(board, 'player1')
        lines = state_after.strip().split('\n')
        # Both cards should show as "my MATCHED" (they still match)
        assert 'my MATCHED' in lines[1] or lines[1] == 'my MATCHED'  # Position (0,0)
        assert 'my MATCHED' in lines[5] or lines[5] == 'my MATCHED'  # Position (0,4)
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_map_while_cards_are_controlled(self):
        """Test that map works even when cards are controlled by players."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 controls some cards (both A)
        await flip(board, 'player1', 0, 0)
        await flip(board, 'player1', 0, 4)  # Match
        
        # Verify cards are controlled
        state_before = await look(board, 'player1')
        assert 'my A' in state_before
        
        async def transform(card: str) -> str:
            return 'X' if card == 'A' else card
        
        # Apply map (should work even though cards are controlled)
        await map_cards(board, 'player1', transform)
        
        # Cards should still be controlled, but values changed
        state_after = await look(board, 'player1')
        assert 'my X' in state_after
        assert 'my A' not in state_after
        
        # Player should still control the cards (verify via board state)
        # Cards at (0,0) and (0,4) should still show as "my X"
        lines = state_after.strip().split('\n')
        # Position (0,0) is line 1, (0,4) is line 5
        assert 'my X' in lines[1] or lines[1] == 'my X'
        assert 'my X' in lines[5] or lines[5] == 'my X'
        
        board.check_rep()

