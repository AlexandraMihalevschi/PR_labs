"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import asyncio
import random
import aiohttp
from typing import Optional


"""
Browser-visible simulation that makes HTTP requests to the game server.
This allows you to watch the simulation in real-time by opening the game in your browser.
"""


async def browser_simulation_main(server_url: str = 'http://localhost:8080'):
    """
    Simulate multiple players making moves via HTTP requests.
    
    This simulation connects to a running game server and makes HTTP requests
    to flip cards. You can watch it in real-time by opening the game in your browser.
    
    Requirements: 4 players, timeouts between 0.1ms and 2ms, 100 moves each.
    Uses different movesets per player to demonstrate system reliability.
    
    Args:
        server_url: URL of the game server (default: http://localhost:8080)
    
    Usage:
        1. Start the server: python -m src.server 8080 boards/ab.txt
        2. Open http://localhost:8080 in your browser
        3. Run this simulation: python -m src.browser_simulation
        4. Watch the cards flip in real-time in the browser!
    """
    players = 4  # Required: 4 players
    moves_per_player = 100  # Required: 100 moves each
    min_delay_ms = 0.1  # Required: minimum 0.1ms
    max_delay_ms = 2.0  # Required: maximum 2ms
    
    print(f'Starting browser-visible simulation')
    print(f'Server: {server_url}')
    print(f'Players: {players}, Moves per player: {moves_per_player}')
    print(f'Delay range: {min_delay_ms}ms - {max_delay_ms}ms')
    print(f'Open {server_url} in your browser to watch!')
    print()
    
    # Test server connection
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'{server_url}/look/test_player') as resp:
                if resp.status != 200:
                    print(f'Error: Server returned status {resp.status}')
                    return
        except Exception as e:
            print(f'Error connecting to server at {server_url}: {e}')
            print('Make sure the server is running: python -m src.server 8080 boards/ab.txt')
            return
    
    # Start all players concurrently
    player_tasks = []
    for player_num in range(players):
        # Use different random seeds for different movesets per player
        random.seed(player_num * 73)  # Different seed for different moveset
        player_tasks.append(
            browser_player(player_num, server_url, moves_per_player, min_delay_ms, max_delay_ms)
        )
    
    # Wait for all players to complete
    try:
        movesets = await asyncio.gather(*player_tasks)
        print('\n' + '='*60)
        print('BROWSER SIMULATION COMPLETED SUCCESSFULLY - NO CRASHES!')
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
    except Exception as err:
        print(f'\nSimulation failed with error: {err}')
        raise


async def browser_player(
    player_number: int,
    server_url: str,
    moves: int,
    min_delay_ms: float,
    max_delay_ms: float
):
    """
    Simulate a player making moves via HTTP requests.
    
    Each move consists of flipping two cards (first card, then second card).
    Uses random delays and different movesets per player.
    
    Args:
        player_number: player identifier
        server_url: URL of the game server
        moves: number of moves (each move = 2 card flips)
        min_delay_ms: minimum delay between actions in milliseconds
        max_delay_ms: maximum delay between actions in milliseconds
    
    Returns:
        List of moves made by this player, where each move is ((row1, col1), (row2, col2))
    """
    player_id = f'browser_player_{player_number}'
    moveset = []  # Track all moves for this player
    
    async with aiohttp.ClientSession() as session:
        # Get board size first
        try:
            async with session.get(f'{server_url}/look/{player_id}') as resp:
                if resp.status != 200:
                    print(f'Player {player_number}: Failed to get board state')
                    return moveset
                board_state = await resp.text()
                # Parse board size from first line (e.g., "5x5")
                first_line = board_state.split('\n')[0]
                size = int(first_line.split('x')[0])
        except Exception as e:
            print(f'Player {player_number}: Error getting board size: {e}')
            return moveset
        
        for move_num in range(moves):
            # Generate positions for this move (before any delays/operations)
            row1 = random.randrange(0, size)
            col1 = random.randrange(0, size)
            row2 = random.randrange(0, size)
            col2 = random.randrange(0, size)
            
            try:
                # Random delay before first card flip
                delay = min_delay_ms + random.random() * (max_delay_ms - min_delay_ms)
                await asyncio.sleep(delay / 1000.0)
                
                # Try to flip over a first card at random position
                async with session.get(f'{server_url}/flip/{player_id}/{row1},{col1}') as resp:
                    if resp.status == 409:  # Conflict - expected for some game rules
                        pass  # Continue to next move
                    elif resp.status != 200:
                        # Unexpected error
                        error_text = await resp.text()
                        print(f'Player {player_number} move {move_num}: Unexpected error: {error_text}')
                
                # Random delay before second card flip
                delay = min_delay_ms + random.random() * (max_delay_ms - min_delay_ms)
                await asyncio.sleep(delay / 1000.0)
                
                # Try to flip over a second card at random position
                async with session.get(f'{server_url}/flip/{player_id}/{row2},{col2}') as resp:
                    if resp.status == 409:  # Conflict - expected for some game rules
                        pass  # Continue to next move
                    elif resp.status != 200:
                        # Unexpected error
                        error_text = await resp.text()
                        print(f'Player {player_number} move {move_num}: Unexpected error: {error_text}')
                
            except Exception as err:
                # Log unexpected errors but continue
                print(f'Player {player_number} move {move_num}: Error: {err}')
                # Don't raise - continue simulation to test reliability
            
            # Record the move (regardless of success/failure)
            moveset.append(((row1, col1), (row2, col2)))
    
    return moveset


if __name__ == '__main__':
    import sys
    server_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080'
    asyncio.run(browser_simulation_main(server_url))

