"""
Blackjack Server
UDP broadcaster for offers + TCP handler for game sessions.

This server:
1. Broadcasts UDP offers every second to let clients know it's available
2. Accepts TCP connections from clients who want to play
3. Handles each client in a separate thread
"""

import socket
import threading
import time
from typing import Optional

from protocol import (
    pack_offer, pack_payload, unpack_request, unpack_payload,
    decode_decision, RESULT_WIN, RESULT_LOSE, RESULT_TIE, RESULT_BUST,
    RESULT_NONE, PAYLOAD_SIZE
)
from game import Deck, Hand, Card, determine_winner


# ============================================================
# SERVER CONFIGURATION
# ============================================================

UDP_BROADCAST_PORT = 13122   # Port where clients listen for offers
SERVER_NAME = "BlackjackServer"  # Server name (shown to clients)
BROADCAST_INTERVAL = 1.0     # Seconds between UDP broadcasts
CLIENT_TIMEOUT = 60          # Seconds before disconnecting idle client


def get_local_ip() -> str:
    """
    Get the local IP address that has a route to external networks.
    This avoids picking WSL/VirtualBox virtual adapters.
    """
    try:
        # Create a UDP socket and "connect" to an external address
        # This doesn't send any data, just determines which interface would be used
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback to binding on all interfaces
        return ''


# ============================================================
# BLACKJACK SERVER CLASS
# ============================================================

class BlackjackServer:
    """Main server class that handles UDP broadcasting and TCP game sessions."""
    
    def __init__(self, tcp_port: int = 0):
        """
        Initialize the server.
        
        Args:
            tcp_port: TCP port to listen on (0 = let OS choose an available port)
        """
        self.running = False
        self.tcp_port = tcp_port
        self.tcp_socket: Optional[socket.socket] = None
        self.udp_socket: Optional[socket.socket] = None
    
    def start(self):
        """Start the server - creates sockets and begins accepting connections."""
        self.running = True
        
        # --------------------------------------------------------
        # STEP 1: Create and configure TCP socket for game sessions
        # --------------------------------------------------------
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Allow reusing the address (helpful when restarting server quickly)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to the correct network interface (avoids WSL/VirtualBox adapters)
        self.local_ip = get_local_ip()
        self.tcp_socket.bind((self.local_ip, self.tcp_port))
        
        # Start listening for connections (queue up to 5)
        self.tcp_socket.listen(5)
        
        # Get the actual port (useful if we passed 0 to let OS choose)
        self.tcp_port = self.tcp_socket.getsockname()[1]
        
        print(f"Server started on {self.local_ip or 'all interfaces'}:{self.tcp_port}")
        
        # --------------------------------------------------------
        # STEP 2: Start UDP broadcaster in a separate thread
        # --------------------------------------------------------
        udp_thread = threading.Thread(target=self._broadcast_offers, daemon=True)
        udp_thread.start()
        
        # --------------------------------------------------------
        # STEP 3: Start accepting TCP connections (blocking loop)
        # --------------------------------------------------------
        self._accept_connections()
    
    def _broadcast_offers(self):
        """
        Broadcast UDP offer packets every second.
        Runs in a separate thread. Lets clients discover this server.
        """
        # Create UDP socket for broadcasting
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Enable broadcast mode
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Create the offer packet (reuse same packet each time)
        offer_packet = pack_offer(self.tcp_port, SERVER_NAME)
        
        # Broadcast loop - runs until server stops
        while self.running:
            try:
                # Send offer to broadcast address on the UDP port
                self.udp_socket.sendto(offer_packet, ('<broadcast>', UDP_BROADCAST_PORT))
                print(f"Server sending offers...")
            except Exception as e:
                print(f"Broadcast error: {e}")
            
            # Wait 1 second before next broadcast (no busy waiting!)
            time.sleep(BROADCAST_INTERVAL)
    
    def _accept_connections(self):
        """
        Accept incoming TCP connections from clients.
        Runs in the main thread. Each client gets their own handler thread.
        """
        print(f"Server waiting for clients...")
        
        while self.running:
            try:
                # Block here waiting for a client to connect
                # This is NOT busy waiting - the thread sleeps until a connection arrives
                client_socket, client_addr = self.tcp_socket.accept()
                print(f"Client connected from {client_addr}")
                
                # Handle this client in a separate thread
                # daemon=True means thread dies when main program exits
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"Accept error: {e}")
    
    def _handle_client(self, client_socket: socket.socket, client_addr):
        """
        Handle a single client's game session.
        Runs in its own thread. Plays the requested number of rounds.
        
        Args:
            client_socket: The TCP socket connected to this client
            client_addr: The client's (ip, port) tuple
        """
        try:
            # Set timeout so we don't wait forever for a stuck client
            client_socket.settimeout(CLIENT_TIMEOUT)
            
            # --------------------------------------------------------
            # STEP 1: Receive and parse the client's request packet
            # --------------------------------------------------------
            request_data = client_socket.recv(1024)
            request = unpack_request(request_data)
            
            # Validate the request
            if not request:
                print(f"Invalid request from {client_addr}")
                client_socket.close()
                return
            
            rounds, client_name = request
            print(f"{client_name} wants to play {rounds} rounds")
            
            # --------------------------------------------------------
            # STEP 2: Play the requested number of rounds
            # --------------------------------------------------------
            for round_num in range(1, rounds + 1):
                print(f"Round {round_num}/{rounds} with {client_name}")
                self._play_round(client_socket, client_name)
            
            print(f"{client_name} finished all rounds")
            
        except socket.timeout:
            print(f"Client {client_addr} timed out")
        except ConnectionResetError:
            print(f"Client {client_addr} disconnected")
        except Exception as e:
            print(f"Error with {client_addr}: {e}")
        finally:
            # Always close the socket when done
            client_socket.close()
    
    def _play_round(self, client_socket: socket.socket, client_name: str):
        """
        Play a single round of blackjack with a client.
        
        Round flow:
        1. Deal initial cards (2 to player, 2 to dealer)
        2. Player's turn (hit/stand until stand or bust)
        3. Dealer's turn (if player didn't bust)
        4. Determine and send result
        
        Args:
            client_socket: The TCP socket connected to this client
            client_name: The client's display name
        """
        # Create a fresh shuffled deck for this round
        deck = Deck()
        player_hand = Hand()
        dealer_hand = Hand()
        
        # ============================================================
        # PHASE 1: DEAL INITIAL CARDS
        # ============================================================
        
        # Deal 2 cards to player, 2 to dealer (alternating like real blackjack)
        player_hand.add_card(deck.draw())
        dealer_hand.add_card(deck.draw())
        player_hand.add_card(deck.draw())
        dealer_hand.add_card(deck.draw())
        
        print(f"  Player hand: {player_hand}")
        print(f"  Dealer shows: {dealer_hand.cards[0]}")
        
        # Send player's first card
        card1 = player_hand.cards[0]
        packet = pack_payload(result=RESULT_NONE, card_rank=card1.rank, card_suit=card1.suit)
        client_socket.send(packet)
        
        # Send player's second card
        card2 = player_hand.cards[1]
        packet = pack_payload(result=RESULT_NONE, card_rank=card2.rank, card_suit=card2.suit)
        client_socket.send(packet)
        
        # Send dealer's visible card (first card only - second is hidden)
        dealer_visible = dealer_hand.cards[0]
        packet = pack_payload(result=RESULT_NONE, card_rank=dealer_visible.rank, card_suit=dealer_visible.suit)
        client_socket.send(packet)
        
        # ============================================================
        # PHASE 2: PLAYER'S TURN (hit or stand)
        # ============================================================
        
        player_busted = False
        
        while True:
            # Wait for player's decision (blocks until data arrives)
            decision_data = client_socket.recv(PAYLOAD_SIZE)
            decision_packet = unpack_payload(decision_data)
            
            if not decision_packet:
                print(f"  Invalid decision from {client_name}")
                break
            
            # Extract and decode the decision
            decision = decode_decision(decision_packet[0])
            print(f"  {client_name} chose: {decision}")
            
            if decision == "Hittt":
                # Player wants another card
                new_card = deck.draw()
                player_hand.add_card(new_card)
                print(f"  Player hand: {player_hand}")
                
                # Check if player busted (over 21)
                if player_hand.is_bust:
                    player_busted = True
                    # Send the card with BUST result
                    packet = pack_payload(
                        result=RESULT_BUST,
                        card_rank=new_card.rank,
                        card_suit=new_card.suit
                    )
                    client_socket.send(packet)
                    print(f"  {client_name} BUSTED!")
                    break
                else:
                    # Send the new card (round not over yet)
                    packet = pack_payload(
                        result=RESULT_NONE,
                        card_rank=new_card.rank,
                        card_suit=new_card.suit
                    )
                    client_socket.send(packet)
            
            elif decision == "Stand":
                # Player is done taking cards
                break
        
        # ============================================================
        # PHASE 3: DEALER'S TURN (only if player didn't bust)
        # ============================================================
        
        if not player_busted:
            print(f"  Dealer's turn. Hand: {dealer_hand}")
            
            # Dealer must hit until reaching 17 or higher
            while dealer_hand.total < 17:
                new_card = deck.draw()
                dealer_hand.add_card(new_card)
                print(f"  Dealer draws: {new_card}, Hand: {dealer_hand}")
            
            # ============================================================
            # PHASE 4: DETERMINE WINNER AND SEND RESULTS
            # ============================================================
            
            result = determine_winner(player_hand, dealer_hand)
            
            # Send dealer's hidden card (the second card)
            dealer_hidden = dealer_hand.cards[1]
            packet = pack_payload(
                result=result,
                card_rank=dealer_hidden.rank,
                card_suit=dealer_hidden.suit
            )
            client_socket.send(packet)
            
            # Send any additional cards dealer drew (cards 3, 4, etc.)
            for i in range(2, len(dealer_hand.cards)):
                extra_card = dealer_hand.cards[i]
                packet = pack_payload(
                    result=result,
                    card_rank=extra_card.rank,
                    card_suit=extra_card.suit
                )
                client_socket.send(packet)
            
            # Send final signal (card_rank=0 means "no more cards")
            packet = pack_payload(result=result, card_rank=0, card_suit=0)
            client_socket.send(packet)
            
            # Log the result
            result_names = {
                RESULT_WIN: "PLAYER WINS",
                RESULT_LOSE: "DEALER WINS",
                RESULT_TIE: "TIE"
            }
            result_text = result_names.get(result, "UNKNOWN")
            print(f"  Result: {result_text}")
        
        else:
            # Player busted - send final result signal
            packet = pack_payload(result=RESULT_LOSE, card_rank=0, card_suit=0)
            client_socket.send(packet)
    
    def stop(self):
        """Stop the server and close all sockets."""
        self.running = False
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.udp_socket:
            self.udp_socket.close()


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Start the blackjack server."""
    server = BlackjackServer()
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        server.stop()


if __name__ == "__main__":
    main()
