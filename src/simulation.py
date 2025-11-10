"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import asyncio
import random
from .board import Board


async def simulation_main():
    """
    Simulate a multi-player Memory Scramble game.
    
    Requirements: 4 players, timeouts between 0.1ms and 2ms, 100 moves each.
    This function simulates multiple players making random moves concurrently
    to test that the game works correctly under concurrent access and never crashes.
    
    PS4 instructions: you may use, modify, or remove this file,
      completing it is recommended but not required.
    
    Raises:
        Error if an error occurs reading or parsing the board
    """
    filename = 'boards/ab.txt'
    board: Board = await Board.parse_from_file(filename)
    size = board.get_rows()  # Use actual board size
    players = 4  # Required: 4 players
    moves_per_player = 100  # Required: 100 moves each
    min_delay_ms = 0.1  # Required: minimum 0.1ms
    max_delay_ms = 2.0  # Required: maximum 2ms

    print(f'Starting simulation with {players} players, {moves_per_player} moves each')
    print(f'Board size: {size}x{size}')
    print(f'Delay range: {min_delay_ms}ms - {max_delay_ms}ms')
    
    # start up one or more players as concurrent asynchronous function calls
    player_tasks = []
    for ii in range(players):
        # Use different random seeds for different movesets
        random.seed(ii * 42)  # Different seed per player for different movesets
        player_tasks.append(player(ii, board, size, moves_per_player, min_delay_ms, max_delay_ms))
    
    # wait for all the players to finish (unless one throws an exception)
    try:
        movesets = await asyncio.gather(*player_tasks)
        print('\n' + '='*60)
        print('SIMULATION COMPLETED SUCCESSFULLY - NO CRASHES!')
        print('='*60)
        
        # Print movesets for each player
        print('\nMovesets for each player:')
        print('-'*60)
        for player_num, moveset in enumerate(movesets):
            print(f'\nPlayer {player_num} moveset ({len(moveset)} moves):')
            for move_idx, move in enumerate(moveset):
                (row1, col1), (row2, col2) = move
                print(f'  Move {move_idx + 1}: ({row1},{col1}) -> ({row2},{col2})')
        
        print('\n' + '='*60)
        board.check_rep()  # Verify board is still in valid state
    except Exception as err:
        print(f'Simulation failed with error: {err}')
        raise


async def player(player_number: int, board: Board, size: int, moves: int, min_delay_ms: float, max_delay_ms: float):
    """
    Simulate a player making moves.
    
    Each move consists of flipping two cards (first card, then second card).
    Uses random delays between actions to simulate realistic gameplay.
    
    Args:
        player_number: player identifier (used to create unique player IDs)
        board: game board
        size: board size (used to generate random positions)
        moves: number of moves (each move = 2 card flips)
        min_delay_ms: minimum delay between actions in milliseconds
        max_delay_ms: maximum delay between actions in milliseconds
    
    Returns:
        List of moves made by this player, where each move is ((row1, col1), (row2, col2))
    """
    player_id = f'player_{player_number}'
    moveset = []  # Track all moves for this player
    
    for move_num in range(moves):
        # Generate positions for this move (before any delays/operations)
        row1 = random_int(size)
        col1 = random_int(size)
        row2 = random_int(size)
        col2 = random_int(size)
        
        try:
            # Random delay before first card flip (between min and max)
            delay = min_delay_ms + random.random() * (max_delay_ms - min_delay_ms)
            await timeout(delay)
            
            # Try to flip over a first card at random position
            # This might wait until this player can control that card (Rule 1-D)
            await board.flip_card(player_id, row1, col1)
            
            # Random delay before second card flip
            delay = min_delay_ms + random.random() * (max_delay_ms - min_delay_ms)
            await timeout(delay)
            
            # Try to flip over a second card at random position
            await board.flip_card(player_id, row2, col2)
            
        except (ValueError, IndexError) as err:
            # Expected errors (empty space, controlled card, out of bounds)
            # These are normal game rules, not crashes
            pass
        except Exception as err:
            # Unexpected errors should be logged
            print(f'Player {player_number} move {move_num} failed with unexpected error: {err}')
            raise
        
        # Record the move (regardless of success/failure)
        moveset.append(((row1, col1), (row2, col2)))
    
    return moveset


def random_int(max_val: int) -> int:
    """
    Random positive integer generator
    
    Args:
        max_val: a positive integer which is the upper bound of the generated number
    Returns:
        a random integer >= 0 and < max
    """
    return random.randrange(0, max_val)


async def timeout(milliseconds: float):
    """
    Args:
        milliseconds: duration to wait
    Returns:
        a coroutine that completes no less than `milliseconds` after timeout() was called
    """
    await asyncio.sleep(milliseconds / 1000.0)


if __name__ == '__main__':
    asyncio.run(simulation_main())

