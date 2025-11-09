"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import asyncio
import random
from .board import Board


async def simulation_main():
    """
    Example code for simulating a game.
    
    PS4 instructions: you may use, modify, or remove this file,
      completing it is recommended but not required.
    
    Raises:
        Error if an error occurs reading or parsing the board
    """
    filename = 'boards/ab.txt'
    board: Board = await Board.parse_from_file(filename)
    size = 5
    players = 1
    tries = 10
    max_delay_milliseconds = 100

    # start up one or more players as concurrent asynchronous function calls
    player_tasks = []
    for ii in range(players):
        player_tasks.append(player(ii, board, size, tries, max_delay_milliseconds))
    # wait for all the players to finish (unless one throws an exception)
    await asyncio.gather(*player_tasks)


async def player(player_number: int, board: Board, size: int, tries: int, max_delay_ms: int):
    """
    Simulate a player.
    
    Args:
        player_number: player to simulate
        board: game board
        size: board size
        tries: number of attempts
        max_delay_ms: maximum delay between actions in milliseconds
    """
    # TODO set up this player on the board if necessary

    for jj in range(tries):
        try:
            await timeout(random.random() * max_delay_ms)
            # TODO try to flip over a first card at (random_int(size), random_int(size))
            #      which might wait until this player can control that card

            await timeout(random.random() * max_delay_ms)
            # TODO and if that succeeded,
            #      try to flip over a second card at (random_int(size), random_int(size))
        except Exception as err:
            print(f'attempt to flip a card failed: {err}')


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

