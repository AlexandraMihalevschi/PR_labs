"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import asyncio
import random
from .board import Board


async def simulation_main():
    """
    Simulate a multi-player Memory Scramble game.
    
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
    players = 3  # Multiple concurrent players
    tries = 20  # More attempts per player
    max_delay_milliseconds = 50  # Shorter delays for faster testing

    print(f'Starting simulation with {players} players, {tries} tries each')
    print(f'Board size: {size}x{size}')
    
    # start up one or more players as concurrent asynchronous function calls
    player_tasks = []
    for ii in range(players):
        player_tasks.append(player(ii, board, size, tries, max_delay_milliseconds))
    
    # wait for all the players to finish (unless one throws an exception)
    try:
        await asyncio.gather(*player_tasks)
        print('Simulation completed successfully - no crashes!')
        board.check_rep()  # Verify board is still in valid state
    except Exception as err:
        print(f'Simulation failed with error: {err}')
        raise


async def player(player_number: int, board: Board, size: int, tries: int, max_delay_ms: int):
    """
    Simulate a player making random moves.
    
    This function simulates a player making random moves on the board with random delays.
    The goal is to test that the game never crashes under concurrent access.
    
    Args:
        player_number: player identifier (used to create unique player IDs)
        board: game board
        size: board size (used to generate random positions)
        tries: number of attempts to flip cards
        max_delay_ms: maximum delay between actions in milliseconds
    """
    player_id = f'player_{player_number}'
    
    for jj in range(tries):
        try:
            # Random delay before first card flip
            await timeout(random.random() * max_delay_ms)
            
            # Try to flip over a first card at random position
            # This might wait until this player can control that card (Rule 1-D)
            row1 = random_int(size)
            col1 = random_int(size)
            await board.flip_card(player_id, row1, col1)
            
            # Random delay before second card flip
            await timeout(random.random() * max_delay_ms)
            
            # Try to flip over a second card at random position
            row2 = random_int(size)
            col2 = random_int(size)
            await board.flip_card(player_id, row2, col2)
            
        except (ValueError, IndexError) as err:
            # Expected errors (empty space, controlled card, out of bounds)
            # These are normal game rules, not crashes
            pass
        except Exception as err:
            # Unexpected errors should be logged
            print(f'Player {player_number} attempt {jj} failed with unexpected error: {err}')
            raise


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

