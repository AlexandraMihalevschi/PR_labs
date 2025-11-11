"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import pytest
import asyncio
from src.board import Board


"""
Tests for the Board abstract data type.
Comprehensive tests for each gameplay rule.
"""


class TestBoardParsing:
    """Tests for board file parsing."""
    
    @pytest.mark.asyncio
    async def test_parse_from_file_simple(self):
        """Test parsing a simple board file."""
        board = await Board.parse_from_file('boards/ab.txt')
        assert board.get_rows() == 5
        assert board.get_columns() == 5
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_parse_from_file_emoji(self):
        """Test parsing a board file with emoji."""
        board = await Board.parse_from_file('boards/perfect.txt')
        assert board.get_rows() == 3
        assert board.get_columns() == 3
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_parse_from_file_invalid(self):
        """Test parsing an invalid board file."""
        with pytest.raises(ValueError):
            await Board.parse_from_file('boards/nonexistent.txt')
    
    @pytest.mark.asyncio
    async def test_initial_board_state(self):
        """Test that all cards start face down."""
        board = await Board.parse_from_file('boards/ab.txt')
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[0] == '5x5'
        # All cards should be "down"
        for line in lines[1:]:
            assert line == 'down'


class TestRule1A:
    """Tests for Rule 1-A: Empty space fails."""
    
    @pytest.mark.asyncio
    async def test_rule_1a_empty_space_fails(self):
        """Rule 1-A: Flipping an empty space fails."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Remove a card to create an empty space
        board._cards[0][0] = None
        board._face_up[0][0] = False
        board._controllers[0][0] = None
        
        with pytest.raises(ValueError, match='No card'):
            await board.flip_card('player1', 0, 0)
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_1a_empty_space_after_removal(self):
        """Rule 1-A: Flipping a space that was just removed by another player fails."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Simulate another player removing a card
        board._cards[1][1] = None
        board._face_up[1][1] = False
        board._controllers[1][1] = None
        
        with pytest.raises(ValueError, match='No card'):
            await board.flip_card('player1', 1, 1)
        
        board.check_rep()


class TestRule1B:
    """Tests for Rule 1-B: Face down card turns face up and player controls it."""
    
    @pytest.mark.asyncio
    async def test_rule_1b_face_down_turns_face_up(self):
        """Rule 1-B: Flipping a face-down card turns it face up and player controls it."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Verify card starts face down
        assert not board._face_up[0][0]
        assert board._controllers[0][0] is None
        
        await board.flip_card('player1', 0, 0)
        
        # Card should now be face up and controlled
        assert board._face_up[0][0]
        assert board._controllers[0][0] == 'player1'
        assert (0, 0) in board._player_cards.get('player1', [])
        
        # Board state should show "my A"
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'my A'  # First card in ab.txt is A
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_1b_all_players_can_see(self):
        """Rule 1-B: When a card turns face up, all players can see it."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        
        # Another player should see the card as "up A" (not "my A")
        state = board.get_board_state('player2')
        lines = state.strip().split('\n')
        assert lines[1] == 'up A'  # Face up but not controlled by player2
        
        board.check_rep()


class TestRule1C:
    """Tests for Rule 1-C: Face up uncontrolled card can be controlled."""
    
    @pytest.mark.asyncio
    async def test_rule_1c_face_up_uncontrolled(self):
        """Rule 1-C: Flipping a face-up uncontrolled card gives player control."""
        board = await Board.parse_from_file('boards/ab.txt')
        # First, flip a card face up but don't control it (simulate previous relinquish)
        board._face_up[0][0] = True
        board._controllers[0][0] = None  # Uncontrolled
        
        await board.flip_card('player1', 0, 0)
        
        # Player should now control the card
        assert board._face_up[0][0]
        assert board._controllers[0][0] == 'player1'
        assert (0, 0) in board._player_cards.get('player1', [])
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'my A'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_1c_card_stays_face_up(self):
        """Rule 1-C: Card remains face up when player takes control."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Set up face-up uncontrolled card
        board._face_up[0][0] = True
        board._controllers[0][0] = None
        
        # Verify it's face up before
        assert board._face_up[0][0]
        
        await board.flip_card('player1', 0, 0)
        
        # Should still be face up after
        assert board._face_up[0][0]
        assert board._controllers[0][0] == 'player1'
        
        board.check_rep()


class TestRule1D:
    """Tests for Rule 1-D: Face up controlled by another player waits."""
    
    @pytest.mark.asyncio
    async def test_rule_1d_controlled_by_another_raises_error(self):
        """Rule 1-D: In async version, trying to flip a card controlled by another player waits."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player2 controls a card
        board._face_up[0][0] = True
        board._controllers[0][0] = 'player2'
        if 'player2' not in board._player_cards:
            board._player_cards['player2'] = []
        board._player_cards['player2'].append((0, 0))
        
        # Player1 tries to flip it - should wait (not raise error in async version)
        async def player1_flip():
            await board.flip_card('player1', 0, 0)
            return True
        
        # Start the flip (it will wait)
        task = asyncio.create_task(player1_flip())
        await asyncio.sleep(0.01)  # Give it time to start waiting
        
        # Verify it's waiting (task not done yet)
        assert not task.done()
        
        # Player2 relinquishes control
        await board.flip_card('player2', 0, 1)  # Non-matching
        await board.flip_card('player2', 1, 0)  # Cleanup
        
        # Now player1 should get control
        await task
        
        # Card should now be controlled by player1
        assert board._controllers[0][0] == 'player1'
        
        board.check_rep()


class TestRule2A:
    """Tests for Rule 2-A: Empty space as second card fails and relinquishes first card."""
    
    @pytest.mark.asyncio
    async def test_rule_2a_empty_space_fails(self):
        """Rule 2-A: Flipping an empty space as second card fails."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player controls first card
        await board.flip_card('player1', 0, 0)
        assert (0, 0) in board._player_cards.get('player1', [])
        
        # Remove second card
        board._cards[0][1] = None
        board._face_up[0][1] = False
        board._controllers[0][1] = None
        
        # Try to flip empty space
        with pytest.raises(ValueError, match='No card'):
            await board.flip_card('player1', 0, 1)
        
        # First card should no longer be controlled (relinquished)
        assert board._controllers[0][0] is None
        assert (0, 0) not in board._player_cards.get('player1', [])
        # But first card should remain face up
        assert board._face_up[0][0]
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_2a_first_card_stays_face_up(self):
        """Rule 2-A: First card remains face up after failure."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        board._cards[0][1] = None
        
        with pytest.raises(ValueError):
            await board.flip_card('player1', 0, 1)
        
        # First card should be face up but not controlled
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'up A'  # Face up but not controlled
        
        board.check_rep()


class TestRule2B:
    """Tests for Rule 2-B: Controlled card as second card fails and relinquishes first card."""
    
    @pytest.mark.asyncio
    async def test_rule_2b_controlled_by_another_player_fails(self):
        """Rule 2-B: Flipping a card controlled by another player as second card fails."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player1 controls first card
        await board.flip_card('player1', 0, 0)
        
        # Player2 controls another card
        board._face_up[0][1] = True
        board._controllers[0][1] = 'player2'
        if 'player2' not in board._player_cards:
            board._player_cards['player2'] = []
        board._player_cards['player2'].append((0, 1))
        
        # Player1 tries to flip player2's card
        with pytest.raises(ValueError, match='controlled by a player'):
            await board.flip_card('player1', 0, 1)
        
        # Player1 should have relinquished control of first card
        assert board._controllers[0][0] is None
        assert (0, 0) not in board._player_cards.get('player1', [])
        # But first card should remain face up
        assert board._face_up[0][0]
        # Player2's card should still be controlled by player2
        assert board._controllers[0][1] == 'player2'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_2b_controlled_card_cannot_be_second(self):
        """Rule 2-B: Any controlled card (by any player) cannot be flipped as second card."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player1 controls first card
        await board.flip_card('player1', 0, 0)
        
        # Set up a scenario where player1 has previously controlled a card that's still controlled
        # This simulates a case where after a match, player1 still has control
        # Actually, let's test a simpler case: player1 tries to flip a card that player2 controls
        board._face_up[0][1] = True
        board._controllers[0][1] = 'player2'
        if 'player2' not in board._player_cards:
            board._player_cards['player2'] = []
        board._player_cards['player2'].append((0, 1))
        
        # Player1 tries to flip player2's controlled card as second card
        with pytest.raises(ValueError, match='controlled by a player'):
            await board.flip_card('player1', 0, 1)
        
        # Verify player1 relinquished control of first card
        assert board._controllers[0][0] is None
        # Verify player2 still controls their card
        assert board._controllers[0][1] == 'player2'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_2b_no_waiting(self):
        """Rule 2-B: Operation does not wait (to avoid deadlocks)."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        
        # Another player controls a card
        board._face_up[0][1] = True
        board._controllers[0][1] = 'player2'
        if 'player2' not in board._player_cards:
            board._player_cards['player2'] = []
        board._player_cards['player2'].append((0, 1))
        
        # Should fail immediately, not wait
        with pytest.raises(ValueError):
            await board.flip_card('player1', 0, 1)
        
        board.check_rep()


class TestRule2C:
    """Tests for Rule 2-C: Face down card turns face up when flipped as second card."""
    
    @pytest.mark.asyncio
    async def test_rule_2c_face_down_turns_face_up(self):
        """Rule 2-C: Flipping a face-down card as second card turns it face up."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player controls first card
        await board.flip_card('player1', 0, 0)
        
        # Second card is face down
        assert not board._face_up[0][1]
        
        # Flip second card
        await board.flip_card('player1', 0, 1)
        
        # Second card should now be face up
        assert board._face_up[0][1]
        
        # Cards don't match (A != B), so player relinquished control
        assert board._controllers[0][1] is None
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[2] == 'up B'  # Face up but not controlled
        
        board.check_rep()


class TestRule2D:
    """Tests for Rule 2-D: Matching cards - player keeps control of both."""
    
    @pytest.mark.asyncio
    async def test_rule_2d_matching_cards(self):
        """Rule 2-D: When two cards match, player keeps control of both."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Flip first card (A at 0,0)
        await board.flip_card('player1', 0, 0)
        # Flip matching card (A at 0,4) - both are A
        await board.flip_card('player1', 0, 4)
        
        # Player should control both cards
        assert board._controllers[0][0] == 'player1'
        assert board._controllers[0][4] == 'player1'
        assert (0, 0) in board._player_cards.get('player1', [])
        assert (0, 4) in board._player_cards.get('player1', [])
        assert len(board._player_cards.get('player1', [])) == 2
        
        # Both cards should be face up
        assert board._face_up[0][0]
        assert board._face_up[0][4]
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'my A'  # Position (0,0)
        assert lines[5] == 'my A'  # Position (0,4)
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_2d_cards_remain_face_up(self):
        """Rule 2-D: Matched cards remain face up on the board."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 4)  # Matching A card
        
        # Cards should still be on board (not removed yet)
        assert board._cards[0][0] is not None
        assert board._cards[0][4] is not None
        assert board._face_up[0][0]
        assert board._face_up[0][4]
        
        board.check_rep()


class TestRule2E:
    """Tests for Rule 2-E: Non-matching cards - player relinquishes control of both."""
    
    @pytest.mark.asyncio
    async def test_rule_2e_non_matching_cards(self):
        """Rule 2-E: When two cards don't match, player relinquishes control of both."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Flip first card (A)
        await board.flip_card('player1', 0, 0)
        # Flip second card (B) - doesn't match
        await board.flip_card('player1', 0, 1)
        
        # Player should not control either card
        assert board._controllers[0][0] is None
        assert board._controllers[0][1] is None
        assert (0, 0) not in board._player_cards.get('player1', [])
        assert (0, 1) not in board._player_cards.get('player1', [])
        
        # Both cards should be face up (but not controlled)
        assert board._face_up[0][0]
        assert board._face_up[0][1]
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'up A'
        assert lines[2] == 'up B'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_2e_cards_remain_face_up(self):
        """Rule 2-E: Non-matching cards remain face up on the board."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 1)
        
        # Cards should still be on board and face up
        assert board._cards[0][0] is not None
        assert board._cards[0][1] is not None
        assert board._face_up[0][0]
        assert board._face_up[0][1]
        
        board.check_rep()


class TestRule3A:
    """Tests for Rule 3-A: Remove matched cards on next flip."""
    
    @pytest.mark.asyncio
    async def test_rule_3a_remove_matched_cards(self):
        """Rule 3-A: Matched cards are removed when player flips a new first card."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Match two cards (both A)
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 4)  # Matching A card
        
        # Verify they're controlled
        assert len(board._player_cards.get('player1', [])) == 2
        
        # Flip a new first card (triggers cleanup)
        await board.flip_card('player1', 1, 0)
        
        # Matched cards should be removed
        assert board._cards[0][0] is None
        assert board._cards[0][4] is None
        assert not board._face_up[0][0]
        assert not board._face_up[0][4]
        assert board._controllers[0][0] is None
        assert board._controllers[0][4] is None
        assert (0, 0) not in board._player_cards.get('player1', [])
        assert (0, 4) not in board._player_cards.get('player1', [])
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'none'  # First matched card removed (0,0)
        assert lines[5] == 'none'  # Second matched card removed (0,4)
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_3a_player_relinquishes_control(self):
        """Rule 3-A: Player relinquishes control when cards are removed."""
        board = await Board.parse_from_file('boards/ab.txt')
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 4)  # Matching A card
        
        assert len(board._player_cards.get('player1', [])) == 2
        
        await board.flip_card('player1', 1, 0)
        
        # Player should no longer control the removed cards
        # Player should now control the new card
        assert (1, 0) in board._player_cards.get('player1', [])
        assert len(board._player_cards.get('player1', [])) == 1
        
        board.check_rep()


class TestRule3B:
    """Tests for Rule 3-B: Turn non-matching cards face down if uncontrolled."""
    
    @pytest.mark.asyncio
    async def test_rule_3b_turn_face_down_uncontrolled(self):
        """Rule 3-B: Non-matching cards turn face down if uncontrolled."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Flip two non-matching cards
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 1)
        
        # Verify they're face up but not controlled
        assert board._face_up[0][0]
        assert board._face_up[0][1]
        assert board._controllers[0][0] is None
        assert board._controllers[0][1] is None
        
        # Flip a new first card (triggers cleanup)
        await board.flip_card('player1', 1, 0)
        
        # Non-matching cards should be face down
        assert not board._face_up[0][0]
        assert not board._face_up[0][1]
        # Cards should still be on board
        assert board._cards[0][0] is not None
        assert board._cards[0][1] is not None
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert lines[1] == 'down'
        assert lines[2] == 'down'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_3b_controlled_card_stays_face_up(self):
        """Rule 3-B: Cards controlled by another player stay face up."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player1 flips two non-matching cards
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 1)
        
        # Another player takes control of one card
        board._controllers[0][0] = 'player2'
        if 'player2' not in board._player_cards:
            board._player_cards['player2'] = []
        board._player_cards['player2'].append((0, 0))
        
        # Player1 flips a new first card (triggers cleanup)
        await board.flip_card('player1', 1, 0)
        
        # Card controlled by player2 should stay face up
        assert board._face_up[0][0]
        assert board._controllers[0][0] == 'player2'
        # Card not controlled should turn face down
        assert not board._face_up[0][1]
        assert board._controllers[0][1] is None
        
        state = board.get_board_state('player1')
        lines = state.strip().split('\n')
        assert 'up A' in lines[1] or lines[1] == 'up A'  # Controlled by player2
        assert lines[2] == 'down'  # Uncontrolled, turned face down
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_rule_3b_removed_card_not_affected(self):
        """Rule 3-B: Cards that were removed are not affected."""
        board = await Board.parse_from_file('boards/ab.txt')
        # Player flips two non-matching cards
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 1)
        
        # Simulate one card being removed by another player
        board._cards[0][0] = None
        board._face_up[0][0] = False
        board._controllers[0][0] = None
        
        # Player flips a new first card (triggers cleanup)
        await board.flip_card('player1', 1, 0)
        
        # Removed card should stay removed
        assert board._cards[0][0] is None
        # Other card should turn face down if uncontrolled
        if board._cards[0][1] is not None and board._controllers[0][1] is None:
            assert not board._face_up[0][1]
        
        board.check_rep()


class TestRuleIntegration:
    """Integration tests combining multiple rules."""
    
    @pytest.mark.asyncio
    async def test_complete_game_sequence(self):
        """Test a complete sequence of moves."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips first card (rule 1-B)
        await board.flip_card('player1', 0, 0)
        assert board._controllers[0][0] == 'player1'
        
        # Player1 flips matching second card (rule 2-D) - both A cards
        await board.flip_card('player1', 0, 4)
        assert board._controllers[0][0] == 'player1'
        assert board._controllers[0][4] == 'player1'
        
        # Player1 flips new first card (rule 3-A: removes matched cards)
        await board.flip_card('player1', 1, 0)
        assert board._cards[0][0] is None
        assert board._cards[0][4] is None
        assert board._controllers[1][0] == 'player1'
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_multiple_players_see_cards(self):
        """Test that multiple players can see face-up cards correctly."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips a card
        await board.flip_card('player1', 0, 0)
        
        # Player1 sees it as "my A"
        state1 = board.get_board_state('player1')
        assert 'my A' in state1
        
        # Player2 sees it as "up A"
        state2 = board.get_board_state('player2')
        assert 'up A' in state2
        assert 'my A' not in state2
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_card_state_persistence(self):
        """Test that cards maintain their state (controlled/uncontrolled) correctly."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips and matches two cards (both A)
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 4)  # Matching A card
        
        # Cards should be controlled by player1
        assert board._controllers[0][0] == 'player1'
        assert board._controllers[0][4] == 'player1'
        
        # Player1 sees them as "my A"
        state1 = board.get_board_state('player1')
        lines1 = state1.strip().split('\n')
        assert lines1[1] == 'my A'  # Position (0,0)
        assert lines1[5] == 'my A'  # Position (0,4)
        
        # Player2 sees them as "up A"
        state2 = board.get_board_state('player2')
        lines2 = state2.strip().split('\n')
        assert lines2[1] == 'up A'  # Position (0,0)
        assert lines2[5] == 'up A'  # Position (0,4)
        
        # Cards should stay controlled until player1 makes next move
        # (state should persist)
        state1_again = board.get_board_state('player1')
        lines1_again = state1_again.strip().split('\n')
        assert lines1_again[1] == 'my A'  # Position (0,0)
        assert lines1_again[5] == 'my A'  # Position (0,4)
        
        board.check_rep()
    
    @pytest.mark.asyncio
    async def test_card_state_after_relinquish(self):
        """Test that cards show correct state after player relinquishes control."""
        board = await Board.parse_from_file('boards/ab.txt')
        
        # Player1 flips two non-matching cards
        await board.flip_card('player1', 0, 0)
        await board.flip_card('player1', 0, 1)
        
        # Player should have relinquished control
        assert board._controllers[0][0] is None
        assert board._controllers[0][1] is None
        
        # Cards should be face up but uncontrolled
        assert board._face_up[0][0]
        assert board._face_up[0][1]
        
        # All players should see them as "up A" and "up B"
        state1 = board.get_board_state('player1')
        lines1 = state1.strip().split('\n')
        assert lines1[1] == 'up A'
        assert lines1[2] == 'up B'
        
        state2 = board.get_board_state('player2')
        lines2 = state2.strip().split('\n')
        assert lines2[1] == 'up A'
        assert lines2[2] == 'up B'
        
        # Cards should stay in this state until rule 3-B applies
        board.check_rep()


@pytest.mark.asyncio
async def test_reads_file_asynchronously():
    """Test reading a file asynchronously."""
    with open('boards/ab.txt', 'r', encoding='utf-8') as f:
        file_contents = f.read()
    assert file_contents.startswith('5x5')
