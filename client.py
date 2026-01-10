"""
Blackjack Client
UDP listener for server offers + TCP player for game sessions.

This client:
1. Listens for UDP offer broadcasts from servers
2. Connects to a server via TCP
3. Plays the requested number of blackjack rounds
4. Tracks and displays win/loss statistics
"""

import socket
import sys
from typing import Optional

from protocol import (
    unpack_offer, pack_request, pack_payload, unpack_payload,
    DECISION_HIT, DECISION_STAND, RESULT_WIN, RESULT_LOSE, RESULT_TIE,
    RESULT_BUST, RESULT_NONE, PAYLOAD_SIZE
)
from game import Card, Hand, SUIT_SYMBOLS, RANK_NAMES


# ============================================================
# CLIENT CONFIGURATION
# ============================================================

UDP_BROADCAST_PORT = 13122   # Port where servers broadcast offers
SERVER_TIMEOUT = 10          # Seconds to wait for server offers
GAME_TIMEOUT = 60            # Seconds timeout for game operations


# ============================================================
# BLACKJACK CLIENT CLASS
# ============================================================

class BlackjackClient:
    """Client that connects to a Blackjack server and plays the game."""
    
    def __init__(self, client_name: str = "Player"):
        """
        Initialize the client.
        
        Args:
            client_name: Display name for this player
        """
        self.client_name = client_name
        
        # Statistics tracking
        self.wins = 0
        self.losses = 0
        self.ties = 0
        
        # TCP socket (created when connecting to server)
        self.tcp_socket: Optional[socket.socket] = None
    
    def listen_for_offer(self) -> Optional[tuple]:
        """
        Listen for UDP offer broadcasts from servers.
        Blocks until an offer is received or timeout occurs.
        
        Returns:
            (server_ip, tcp_port, server_name) if offer received, None otherwise
        """
        print(f"Client listening for server offers on port {UDP_BROADCAST_PORT}...")
        
        # --------------------------------------------------------
        # STEP 1: Create and configure UDP socket
        # --------------------------------------------------------
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Allow address reuse (helpful when running multiple clients)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Try to set SO_REUSEPORT (allows multiple clients on same machine)
        # Note: This option doesn't exist on Windows
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass  # Windows doesn't have SO_REUSEPORT, that's okay
        
        # Bind to the broadcast port on all interfaces
        udp_socket.bind(('', UDP_BROADCAST_PORT))
        
        # Set timeout so we don't block forever
        udp_socket.settimeout(SERVER_TIMEOUT)
        
        # --------------------------------------------------------
        # STEP 2: Wait for an offer packet
        # --------------------------------------------------------
        try:
            while True:
                try:
                    # Block here waiting for data (NOT busy waiting!)
                    data, server_addr = udp_socket.recvfrom(1024)
                    
                    # Try to parse the offer packet
                    offer = unpack_offer(data)
                    
                    if offer:
                        # Valid offer received!
                        tcp_port, server_name = offer
                        server_ip = server_addr[0]
                        
                        print(f"Received offer from {server_name} at {server_ip}:{tcp_port}")
                        
                        udp_socket.close()
                        return (server_ip, tcp_port, server_name)
                    
                    # Invalid packet, ignore and keep waiting
                    
                except socket.timeout:
                    print(f"No offer received, retrying...")
                    continue
                    
        except Exception as e:
            print(f"Error listening for offers: {e}")
            udp_socket.close()
            return None
    
    def connect_to_server(self, server_ip: str, tcp_port: int) -> bool:
        """
        Connect to the server's TCP port.
        
        Args:
            server_ip: IP address of the server
            tcp_port: TCP port number from the offer
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            # Create TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set timeout for game operations
            self.tcp_socket.settimeout(GAME_TIMEOUT)
            
            # Connect to the server
            self.tcp_socket.connect((server_ip, tcp_port))
            
            print(f"Connected to server at {server_ip}:{tcp_port}")
            return True
            
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def send_request(self, rounds: int):
        """
        Send game request to server (how many rounds to play).
        
        Args:
            rounds: Number of rounds to play (1-255)
        """
        request = pack_request(rounds, self.client_name)
        self.tcp_socket.send(request)
        print(f"Requested {rounds} rounds")
    
    def receive_card(self) -> tuple:
        """
        Receive a card payload from server.
        Blocks until data arrives.
        
        Returns:
            (result, card) where card is a Card object or None
        """
        # Receive exactly PAYLOAD_SIZE bytes
        data = self.tcp_socket.recv(PAYLOAD_SIZE)
        
        # Parse the payload
        payload = unpack_payload(data)
        
        if not payload:
            return (None, None)
        
        decision, result, card_rank, card_suit = payload
        
        # card_rank=0 means "no card" (end of dealer's turn signal)
        if card_rank == 0:
            return (result, None)
        
        # Create a Card object from the rank and suit
        card = Card(card_rank, card_suit)
        return (result, card)
    
    def play_round(self, round_num: int):
        """
        Play a single round of blackjack.
        
        Args:
            round_num: Current round number (for display)
        """
        # --------------------------------------------------------
        # DISPLAY ROUND HEADER
        # --------------------------------------------------------
        print(f"\n{'='*50}")
        print(f"  ROUND {round_num}")
        print(f"{'='*50}")
        
        player_hand = Hand()
        dealer_visible_card = None
        
        # ============================================================
        # PHASE 1: RECEIVE INITIAL CARDS FROM SERVER
        # Server sends: player card 1, player card 2, dealer visible card
        # ============================================================
        
        result, card1 = self.receive_card()
        player_hand.add_card(card1)
        
        result, card2 = self.receive_card()
        player_hand.add_card(card2)
        
        result, dealer_visible_card = self.receive_card()
        
        print(f"\n  Your hand: {player_hand}")
        print(f"  Dealer shows: {dealer_visible_card}")
        
        # ============================================================
        # PHASE 2: PLAYER'S TURN (your turn to hit or stand)
        # ============================================================
        
        while True:
            print(f"\n  Current hand: {player_hand}")
            
            # Get user's decision
            while True:
                decision = input("  [H]it or [S]tand? ").strip().upper()
                
                if decision in ['H', 'HIT', 'HITTT']:
                    decision = 'Hittt'
                    break
                elif decision in ['S', 'STAND']:
                    decision = 'Stand'
                    break
                else:
                    print("  Please enter H or S")
            
            # Send decision to server
            if decision == 'Hittt':
                decision_bytes = DECISION_HIT
            else:
                decision_bytes = DECISION_STAND
            
            payload = pack_payload(decision=decision_bytes)
            self.tcp_socket.send(payload)
            
            if decision == 'Stand':
                print("  You stand.")
                break
            
            # Receive new card from server
            result, new_card = self.receive_card()
            
            if new_card:
                player_hand.add_card(new_card)
                print(f"  You drew: {new_card}")
                print(f"  Hand: {player_hand}")
                
                # Check if we busted
                if result == RESULT_BUST:
                    print(f"\n  BUST! You went over 21!")
                    self.losses += 1
                    
                    # Receive final signal from server
                    self.receive_card()
                    return
        
        # ============================================================
        # PHASE 3: RECEIVE DEALER'S CARDS AND RESULT
        # Server reveals hidden card and any cards dealer drew
        # ============================================================
        
        print(f"\n  Dealer's turn...")
        
        dealer_hand = Hand()
        dealer_hand.add_card(dealer_visible_card)
        
        final_result = RESULT_NONE
        
        # Receive dealer's remaining cards
        while True:
            result, card = self.receive_card()
            final_result = result
            
            # card=None means dealer is done sending cards
            if card is None:
                break
            
            dealer_hand.add_card(card)
            print(f"  Dealer has: {card}")
        
        print(f"\n  Dealer's final hand: {dealer_hand}")
        
        # ============================================================
        # PHASE 4: DISPLAY RESULT AND UPDATE STATISTICS
        # ============================================================
        
        if final_result == RESULT_WIN:
            print(f"\n  YOU WIN!")
            self.wins += 1
        elif final_result == RESULT_LOSE:
            print(f"\n  Dealer wins.")
            self.losses += 1
        elif final_result == RESULT_TIE:
            print(f"\n  It's a tie!")
            self.ties += 1
    
    def play_game(self, rounds: int):
        """
        Play the specified number of rounds.
        
        Args:
            rounds: Total rounds to play
        """
        # Tell server how many rounds we want
        self.send_request(rounds)
        
        # Play each round
        for round_num in range(1, rounds + 1):
            self.play_round(round_num)
        
        # Show final statistics
        self.print_stats()
    
    def print_stats(self):
        """Print final game statistics."""
        total = self.wins + self.losses + self.ties
        
        print(f"\n{'='*50}")
        print(f"  FINAL STATISTICS")
        print(f"{'='*50}")
        print(f"  Games played: {total}")
        print(f"  Wins:   {self.wins}")
        print(f"  Losses: {self.losses}")
        print(f"  Ties:   {self.ties}")
        
        if total > 0:
            win_rate = (self.wins / total) * 100
            print(f"  Win rate: {win_rate:.1f}%")
        
        print(f"{'='*50}\n")
    
    def disconnect(self):
        """Disconnect from server."""
        if self.tcp_socket:
            self.tcp_socket.close()
            self.tcp_socket = None
            print(f"Disconnected from server")
    
    def reset_stats(self):
        """Reset game statistics for a new session."""
        self.wins = 0
        self.losses = 0
        self.ties = 0


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Start the blackjack client."""
    
    # Display welcome banner
    print("=" * 50)
    print("  BLACKJACK NETWORK GAME")
    print("=" * 50 + "\n")
    
    # Get player name
    client_name = input("Enter your name: ").strip()
    if not client_name:
        client_name = "Player"
    
    # Create the client
    client = BlackjackClient(client_name)
    
    # --------------------------------------------------------
    # MAIN GAME LOOP - runs until user quits
    # --------------------------------------------------------
    while True:
        try:
            # ------------------------------------------------
            # STEP 1: Get number of rounds from user
            # ------------------------------------------------
            while True:
                try:
                    rounds_input = input("\nHow many rounds do you want to play? (1-255): ").strip()
                    rounds = int(rounds_input)
                    
                    if 1 <= rounds <= 255:
                        break
                    
                    print("Please enter a number between 1 and 255")
                except ValueError:
                    print("Please enter a valid number")
            
            # ------------------------------------------------
            # STEP 2: Listen for server offer
            # ------------------------------------------------
            offer = client.listen_for_offer()
            
            if not offer:
                print("No server found. Retrying...")
                continue
            
            server_ip, tcp_port, server_name = offer
            
            # ------------------------------------------------
            # STEP 3: Connect to server
            # ------------------------------------------------
            if not client.connect_to_server(server_ip, tcp_port):
                continue
            
            # ------------------------------------------------
            # STEP 4: Play the game
            # ------------------------------------------------
            client.reset_stats()
            client.play_game(rounds)
            
            # ------------------------------------------------
            # STEP 5: Disconnect and ask to play again
            # ------------------------------------------------
            client.disconnect()
            
            again = input("\nPlay again? (y/n): ").strip().lower()
            if again != 'y':
                break
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            client.disconnect()
    
    print("\nThanks for playing!")


if __name__ == "__main__":
    main()
