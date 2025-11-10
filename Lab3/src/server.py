"""Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
Redistribution of original or derived work requires permission of course staff.
"""

import sys
import asyncio
from urllib.parse import unquote
from quart import Quart, send_from_directory
from .board import Board
from .commands import look, flip, map_cards, watch


async def main():
    """
    Start a game server using the given arguments.
    
    PS4 instructions: you are advised *not* to modify this file.

    Command-line usage:
        python -m src.server PORT FILENAME
    where:
    
      - PORT is an integer that specifies the server's listening port number,
        0 specifies that a random unused port will be automatically chosen.
      - FILENAME is the path to a valid board file, which will be loaded as
        the starting game board.
    
    For example, to start a web server on a randomly-chosen port using the
    board in `boards/hearts.txt`:
        python -m src.server 0 boards/hearts.txt
    
    Raises:
        Error if an error occurs parsing a file or starting a server
    """
    if len(sys.argv) < 3:
        raise ValueError('missing PORT or FILENAME')
    
    port_string = sys.argv[1]
    filename = sys.argv[2]
    
    try:
        port = int(port_string)
        if port < 0:
            raise ValueError('invalid PORT')
    except ValueError:
        raise ValueError('invalid PORT')
    
    if not filename:
        raise ValueError('missing FILENAME')
    
    board = await Board.parse_from_file(filename)
    server = WebServer(board, port)
    await server.start()


class WebServer:
    """
    HTTP web game server.
    """

    def __init__(self, board: Board, requested_port: int):
        """
        Make a new web game server using board that listens for connections on port.
        
        Args:
            board: shared game board
            requested_port: server port number
        """
        self.board = board
        self.requested_port = requested_port
        self.app = Quart(__name__)
        self.server = None
        self._actual_port = requested_port
        
        # CORS middleware - allow requests from web pages hosted anywhere
        @self.app.after_request
        async def after_request(response):
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response
        
        """
        GET /look/<playerId>
        playerId must be a nonempty string of alphanumeric or underscore characters
        
        Response is the board state from playerId's perspective, as described in the ps4 handout.
        """
        @self.app.route('/look/<player_id>', methods=['GET'])
        async def look_endpoint(player_id: str):
            board_state = await look(self.board, player_id)
            return board_state, 200, {'Content-Type': 'text/plain'}

        """
        GET /flip/<playerId>/<row>,<column>
        playerId must be a nonempty string of alphanumeric or underscore characters;
        row and column must be integers, 0 <= row,column < height,width of board (respectively)
        
        Response is the state of the board after the flip from the perspective of playerID,
        as described in the ps4 handout.
        """
        @self.app.route('/flip/<player_id>/<location>', methods=['GET'])
        async def flip_endpoint(player_id: str, location: str):
            try:
                row_str, column_str = location.split(',')
                row = int(row_str)
                column = int(column_str)
            except (ValueError, AttributeError):
                return 'invalid location format', 400, {'Content-Type': 'text/plain'}
            
            try:
                board_state = await flip(self.board, player_id, row, column)
                return board_state, 200, {'Content-Type': 'text/plain'}
            except Exception as err:
                return f'cannot flip this card: {err}', 409, {'Content-Type': 'text/plain'}

        """
        GET /replace/<playerId>/<oldcard>/<newcard>
        playerId must be a nonempty string of alphanumeric or underscore characters;
        oldcard and newcard must be nonempty strings.
        
        Replaces all occurrences of oldcard with newcard (as card labels) on the board.
        
        Response is the state of the board after the replacement from the the perspective of playerID,
        as described in the ps4 handout.
        """
        @self.app.route('/replace/<player_id>/<from_card>/<to_card>', methods=['GET'])
        async def replace_endpoint(player_id: str, from_card: str, to_card: str):
            # URL decode the card names
            from_card = unquote(from_card)
            to_card = unquote(to_card)
            
            async def card_mapper(card: str) -> str:
                return to_card if card == from_card else card
            
            board_state = await map_cards(self.board, player_id, card_mapper)
            return board_state, 200, {'Content-Type': 'text/plain'}

        """
        GET /watch/<playerId>
        playerId must be a nonempty string of alphanumeric or underscore characters
        
        Waits until the next time the board changes (defined as any cards turning face up or face down, 
        being removed from the board, or changing from one string to a different string).
        
        Response is the new state of the board from the perspective of playerID,
        as described in the ps4 handout.
        """
        @self.app.route('/watch/<player_id>', methods=['GET'])
        async def watch_endpoint(player_id: str):
            board_state = await watch(self.board, player_id)
            return board_state, 200, {'Content-Type': 'text/plain'}

        """
        GET /
        Response is the game UI as an HTML page.
        """
        @self.app.route('/')
        async def index():
            import os
            public_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public')
            return await send_from_directory(public_dir, 'index.html')

    async def start(self):
        """
        Start this server.
        """
        import socket
        from hypercorn.asyncio import serve
        from hypercorn.config import Config
        
        # If port is 0, bind to a socket first to get an available port
        actual_port = self.requested_port
        if self.requested_port == 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', 0))
            actual_port = sock.getsockname()[1]
            sock.close()
        
        config = Config()
        config.bind = [f'0.0.0.0:{actual_port}']
        
        print(f'server now listening at http://localhost:{actual_port}')
        
        # Store actual port for property access
        self._actual_port = actual_port
        await serve(self.app, config)

    @property
    def port(self) -> int:
        """
        Returns the actual port that server is listening at. (May be different
        than the requestedPort used in the constructor, since if
        requestedPort = 0 then an arbitrary available port is chosen.)
        Requires that start() has already been called and completed.
        """
        return getattr(self, '_actual_port', self.requested_port)

    def stop(self):
        """
        Stop this server. Once stopped, this server cannot be restarted.
        """
        # Quart/Hypercorn shutdown would be handled differently
        print('server stopped')


if __name__ == '__main__':
    asyncio.run(main())
