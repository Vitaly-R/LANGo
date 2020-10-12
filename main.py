import socket
import sys
import numpy as np
import pygame
from threading import Thread
import time


class Communicator:

    HEADER_LENGTH = 8
    ENCODING = 'utf-8'

    def __init__(self, connection_socket):
        self.socket = connection_socket
        self.listener = Thread(target=self.receive_message, args=())
        self.run_thread = True
        self.message = ''
        self.listener.start()

    def send_message(self, msg):
        buffer_size = str(len(msg))
        buffer_size = '0' * (self.HEADER_LENGTH - len(buffer_size)) + buffer_size
        self.socket.send(buffer_size.encode(self.ENCODING))
        self.socket.send(msg.encode(self.ENCODING))

    def receive_message(self):
        while self.run_thread:
            try:
                buffer_size = int(self.socket.recv(self.HEADER_LENGTH).decode(self.ENCODING))
                self.message = self.socket.recv(buffer_size).decode(self.ENCODING)
            except:
                pass

    def get_message(self):
        msg = self.message[:]
        if msg != '':
            self.message = ''
        return msg

    def wait_for_message(self):
        message = self.get_message()
        while message == '':
            message = self.get_message()
        return message

    def end(self):
        self.run_thread = False
        self.listener.join(0.01)
        self.socket.close()


class Player:

    LEFT = 1
    RIGHT = 3
    PORT = 8080

    def __init__(self, as_server, as_ai, server_ip):
        self.is_server = as_server
        self.is_ai = as_ai
        if as_server:
            self.__initialize_server()
        else:
            self.__initialize_client(server_ip)

    def __initialize_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ip = socket.gethostbyname(socket.gethostname())
        sock.bind((ip, self.PORT))
        print('[SERVER] internal ip address:', ip)
        sock.listen()
        r_sock, addr = sock.accept()
        sock.close()
        sock = r_sock
        self.communicator = Communicator(sock)
        print('[SERVER] connected to', addr[0])
        print('[SERVER] received message:', self.communicator.wait_for_message())
        self.communicator.send_message('Hello Client')
        print('[SERVER] received', self.communicator.wait_for_message())
        self.color = np.random.choice([GameInstance.BLACK, GameInstance.WHITE])
        self.communicator.send_message('[BLACK]' if self.color == GameInstance.WHITE else '[WHITE]')

    def __initialize_client(self, server_ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, self.PORT))
        self.communicator = Communicator(sock)
        print('[CLIENT] connected to', server_ip)
        self.communicator.send_message('Hello Server')
        print('[CLIENT] received message:', self.communicator.wait_for_message())
        self.communicator.send_message('[READY]')
        self.color = GameInstance.BLACK if self.communicator.wait_for_message() == '[BLACK]' else GameInstance.WHITE

    def act(self, board, offset, radius):
        if self.is_ai:
            return self.__act_ai(board, offset, radius)
        return self.__act_human()

    def __act_human(self):
        run_game = True
        disconnect = False
        make_move = False
        pass_move = False
        mouse_pos = (-1, -1)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.send_message('[END]')
                run_game = False
                disconnect = True
            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == self.LEFT:
                    make_move = True
                    mouse_pos = pygame.mouse.get_pos()
                elif event.button == self.RIGHT:
                    pass_move = True
        return run_game, disconnect, make_move, pass_move, mouse_pos

    @staticmethod
    def __act_ai(board, offset, radius):
        # random AI
        pygame.event.get()
        row = np.random.randint(0, board.shape[0], size=(1, ))[0]
        col = np.random.randint(0, board.shape[1], size=(1, ))[0]
        pass_move = np.random.random() < 0.01
        return True, False, not pass_move, pass_move, (radius + offset + col * 2 * radius,
                                                       radius + offset + row * 2 * radius)

    def send_message(self, message):
        self.communicator.send_message(message)

    def get_message(self):
        return self.communicator.get_message()

    def wait_for_message(self):
        return self.communicator.wait_for_message()

    def end(self):
        self.communicator.end()


class GameInstance:

    EMPTY = 0
    BLACK = 1
    WHITE = 2

    def __init__(self, player):
        self.player = player
        self.gui = GUI()
        self.turn = self.BLACK
        self.board = np.zeros((19, 19))
        self.run_game = True
        self.black_score = 0
        self.white_score = 0
        self.black_prisoners = 0
        self.white_prisoners = 0
        self.opponent_passed = False
        self.self_passed = False
        self.end_game = False
        self.disconnected = False

    def play_game(self):
        while self.run_game:
            self.do_game_loop()
        if self.end_game:
            self.do_end_of_game_procedures()
        elif not self.disconnected:
            self.gui.show_opponent_disconnected()
        self.player.end()
        pygame.quit()

    def do_game_loop(self):
        self.run_game, self.disconnected, make_move, pass_move, mouse_pos = self.player.act(self.board, GUI.OFFSET,
                                                                                            GUI.RADIUS)
        message = self.player.get_message()
        if message != '':
            print('[RECEIVED]', message)
            if message == '[END]':
                self.run_game = False
        if self.run_game:
            if self.turn == self.player.color:
                if make_move:
                    self.attempt_move(mouse_pos)
                elif pass_move:
                    self.player.send_message('[PASS]')
                    self.turn = 2 // self.turn
                    self.self_passed = True
            else:
                if message != '':
                    self.update_board_from_opponents_move(message)
            self.end_game = self.self_passed and self.opponent_passed
            if self.end_game:
                self.run_game = False

        self.gui.show_board(self.board, self.player.color, self.turn, self.player.is_server)

    def attempt_move(self, mouse_pos):
        (col, row) = mouse_pos
        if self.gui.pos_on_board(row, col):
            r, c = self.gui.to_coordinates(row, col)
            if self.board[r, c] == self.EMPTY:
                self.board[r, c] = self.player.color
                has_liberties, to_erase = self.check_for_liberties(r, c)
                if has_liberties:
                    for (y, x) in to_erase:
                        self.board[y, x] = self.EMPTY
                        self.player.send_message('[CAPTURE][{},{}]'.format(y, x))
                        time.sleep(0.05)
                    if self.player.color == self.BLACK:
                        self.white_prisoners += len(to_erase)
                    else:
                        self.black_prisoners += len(to_erase)
                    self.player.send_message('[{},{}]'.format(r, c))
                    self.turn = 2 // self.turn
                    self.self_passed = False
                else:
                    self.board[r, c] = self.EMPTY

    def check_for_liberties(self, row, col):
        has_liberties = self.check_direct_liberties(row, col)
        to_erase = self.check_resulting_liberties(row, col)
        if len(to_erase):
            has_liberties = True
        return has_liberties, to_erase

    def check_direct_liberties(self, row, col):
        neighbors = list()
        for y, x in [(row - 1, col), (row, col + 1), (row + 1, col), (row, col - 1)]:
            if 0 <= y < 19 and 0 <= x < 19:
                neighbors.append((y, x))
        visited = {(row, col)}
        while len(neighbors):
            current = neighbors.pop(0)
            if self.board[current] == self.player.color:
                visited.add(current)
                for y, x in [(current[0] - 1, current[1]), (current[0], current[1] + 1),
                             (current[0] + 1, current[1]), (current[0], current[1] - 1)]:
                    if 0 <= y < 19 and 0 <= x < 19:
                        if (y, x) not in visited:
                            neighbors.append((y, x))
            elif self.board[current] == self.EMPTY:
                return True
        return False

    def check_resulting_liberties(self, row, col):
        r_color = 2 // self.player.color
        to_erase = set()
        starting_positions = []
        for y, x in [(row - 1, col), (row, col + 1), (row + 1, col), (row, col - 1)]:
            if 0 <= y < 19 and 0 <= x < 19:
                if self.board[y, x] == r_color:
                    starting_positions.append((y, x))
        for y, x in starting_positions:
            has_liberties = False
            neighbors = []
            for r, c in [(y - 1, x), (y, x + 1), (y + 1, x), (y, x - 1)]:
                if 0 <= r < 19 and 0 <= c < 19:
                    neighbors.append((r, c))
            visited = {(y, x)}
            while len(neighbors):
                current = neighbors.pop(0)
                if self.board[current] == r_color:
                    visited.add(current)
                    for r, c in [(current[0] - 1, current[1]), (current[0], current[1] + 1),
                                     (current[0] + 1, current[1]),
                                     (current[0], current[1] - 1)]:
                        if 0 <= r < 19 and 0 <= c < 19:
                            if (r, c) not in visited:
                                neighbors.append((r, c))
                elif self.board[current] == self.EMPTY:
                    has_liberties = True
                    break
            if not has_liberties:
                to_erase = to_erase.union(visited)
        return to_erase

    def update_board_from_opponents_move(self, message):
        if message == '[PASS]':
            self.turn = 2 // self.turn
            self.opponent_passed = True
        elif message.startswith('[CAPTURE]'):
            coords_msg = message[len('[CAPTURE]'):]
            sep = coords_msg.find(',')
            r = int(coords_msg[1: sep])
            c = int(coords_msg[sep + 1: len(coords_msg) - 1])
            self.board[r, c] = self.EMPTY
        else:
            sep = message.find(',')
            r = int(message[1: sep])
            c = int(message[sep + 1: len(message) - 1])
            self.board[r, c] = self.turn
            self.turn = 2 // self.turn
            self.opponent_passed = False

    def do_end_of_game_procedures(self):
        print("[SCORE CALCULATION]")
        self.count_territories()
        self.black_score += len(np.argwhere(self.board == self.BLACK))
        self.white_score += len(np.argwhere(self.board == self.WHITE))
        self.white_score += 6.5
        winner = self.BLACK if self.white_score < self.black_score else self.WHITE
        self.gui.show_game_result("YOU WON" if winner == self.player.color else "MAYBE NEXT TIME", self.black_score,
                                  self.white_score)

    def count_territories(self):
        empty_positions = np.argwhere(self.board == self.EMPTY)
        visited = set()
        pos = 0
        for r, c in empty_positions:
            pos += 1
            if (r, c) not in visited:
                print("[TERRITORY CALCULATION] scanning position {} out of {}".format(pos, empty_positions.shape[0]))
                local_visited = {(r, c)}
                neighbors = []
                for y, x in [(r - 1, c), (r, c + 1), (r + 1, c), (r, c - 1)]:
                    if 0 <= y < self.board.shape[0] and 0 <= x < self.board.shape[1]:
                        neighbors.append((y, x))
                found_black = False
                found_white = False
                iteration = 0
                while len(neighbors):
                    iteration += 1
                    print("[TERRITORY COUNT] iteration {}".format(iteration))
                    current = neighbors.pop(0)
                    if self.board[current] == self.EMPTY:
                        local_visited.add(current)
                        for y, x in [(current[0] - 1, current[1]), (current[0], current[1] + 1),
                                     (current[0] + 1, current[1]), (current[0], current[1] - 1)]:
                            if 0 <= y < self.board.shape[0] and 0 <= x < self.board.shape[1]:
                                if (y, x) not in local_visited and (y, x) not in neighbors:
                                    neighbors.append((y, x))
                    elif self.board[current] == self.BLACK:
                        found_black = True
                    else:
                        found_white = True
                visited = visited.union(local_visited)
                if found_black and not found_white:
                    self.black_score += len(local_visited)
                if found_white and not found_black:
                    self.white_score += len(local_visited)


class GUI:

    TEXT_SIZE = 20
    RADIUS = 20
    OFFSET = 40
    BOARD_LENGTH = 800
    MENU_HEIGHT = 100
    WINDOW_SIZE = (BOARD_LENGTH, BOARD_LENGTH + MENU_HEIGHT)

    def __init__(self):
        pygame.init()
        self.font = pygame.font.Font(pygame.font.get_default_font(), self.TEXT_SIZE)
        self.window = pygame.display.set_mode(self.WINDOW_SIZE)

    def pos_on_board(self, row, col):
        return self.OFFSET <= col <= self.BOARD_LENGTH and self.OFFSET <= row <= self.BOARD_LENGTH

    def to_coordinates(self, row, col):
        return (row - self.OFFSET) // (2 * self.RADIUS), (col - self.OFFSET) // (2 * self.RADIUS)

    def show_board(self, board, color, turn, is_server):
        self.window.fill((225, 150, 0))
        for i in range(board.shape[0]):
            pygame.draw.line(self.window, (0, 0, 0),
                             (self.OFFSET + self.RADIUS, self.OFFSET + self.RADIUS + 2 * i * self.RADIUS),
                             (self.OFFSET + self.RADIUS + 18 * 2 * self.RADIUS, self.OFFSET + self.RADIUS + 2 * i * self.RADIUS), 2)
            pygame.draw.line(self.window, (0, 0, 0),
                             (self.OFFSET + self.RADIUS + 2 * i * self.RADIUS, self.OFFSET + self.RADIUS),
                             (self.OFFSET + self.RADIUS + 2 * i * self.RADIUS, self.OFFSET + self.RADIUS + 18 * 2 * self.RADIUS), 2)
            text = self.font.render(str(i + 1), True, (0, 0, 0))
            self.window.blit(text, (self.RADIUS, 3 * self.RADIUS - 10 + i * 2 * self.RADIUS))
            self.window.blit(text, (3 * self.RADIUS - 10 + i * 2 * self.RADIUS, self.RADIUS))
        pygame.draw.rect(self.window, (100, 100, 100), pygame.rect.Rect(0, self.BOARD_LENGTH, self.BOARD_LENGTH, self.MENU_HEIGHT))

        text = self.font.render('you are black' if color == GameInstance.BLACK else 'you are white', True, (0, 0, 0))
        self.window.blit(text, (50, 810))

        if turn == color:
            text = self.font.render('your turn', True, (0, 0, 0))
            self.window.blit(text, (380, 830))

        for r in range(board.shape[0]):
            for c in range(board.shape[1]):
                if board[r, c] != GameInstance.EMPTY:
                    pygame.draw.circle(self.window, (0, 0, 0) if board[r, c] == GameInstance.BLACK else (255, 255, 255),
                                       (self.OFFSET + self.RADIUS + 2 * c * self.RADIUS, self.OFFSET + self.RADIUS + 2 * r * self.RADIUS), self.RADIUS)

        pygame.display.flip()

    def show_game_result(self, win_lose_message, black_score, white_score):
        pygame.draw.rect(self.window, (100, 100, 100), pygame.rect.Rect(0, 800, 800, 100))
        text = self.font.render(win_lose_message, True, (0, 0, 0))
        self.window.blit(text, (10, 810))
        b_score = self.font.render("Black: " + str(black_score), True, (0, 0, 0))
        w_score = self.font.render("White: " + str(white_score), True, (0, 0, 0))
        self.window.blit(b_score, (10, 830))
        self.window.blit(w_score, (10, 850))
        pygame.display.flip()
        wait_for_exit = True
        while wait_for_exit:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    wait_for_exit = False

    def show_opponent_disconnected(self):
        pygame.draw.rect(self.window, (100, 100, 100), pygame.rect.Rect(0, 800, 800, 100))
        text = self.font.render("OPPONENT DISCONNECTED", True, (0, 0, 0))
        self.window.blit(text, (10, 810))
        pygame.display.flip()
        wait_for_exit = True
        while wait_for_exit:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    wait_for_exit = False


# check arguments
valid_arguments = True
if len(sys.argv) < 4:
    valid_arguments = False
elif sys.argv[1] not in ['0', '1']:
    valid_arguments = False
elif sys.argv[2] not in ['h', 'ai']:
    valid_arguments = False
else:
    if sys.argv[3] != '0.0.0.0':
        try:
            socket.inet_aton(sys.argv[3])
        except socket.error:
            valid_arguments = False
    elif sys.argv[1] == '1':
        valid_arguments = False

if not valid_arguments:
    print('[USAGE ERROR] please pass the following arguments: '
          '[0 or 1] (0 - server, 1 - client) '
          '[h or ai] (h - human, ai - AI) '
          '[server ip address or 0.0.0.0 when running as server]')
    exit()

GameInstance(Player(sys.argv[1] == '0', sys.argv[2] == 'ai', sys.argv[3])).play_game()
