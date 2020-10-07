# LANGo
The game 'Go' for two players with devices on the same network.

Arguments:
1. [0 or 1] - 0: server, 1: client
2. [h or ai] - h: human, ai: AI (currently plays random moves)
3. [0.0.0.0 or server internal ip address]

How to run:
1. Run main.py with the arguments 0, [h or ai], 0.0.0.0 to start the server player. The server's internal IP
address will be printed to the console.
2. Run main.py with the arguments 1, [h or ai], [server internal ip address]