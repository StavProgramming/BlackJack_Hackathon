"""
Protocol layer for Blackjack network game.
Defines packet structures and encoding/decoding functions.

Struct format string reference:
    '>' = Big-endian byte order (network standard)
    'I' = Unsigned int (4 bytes)
    'B' = Unsigned char (1 byte)
    'H' = Unsigned short (2 bytes)
"""

import struct

# ============================================================
# CONSTANTS
# ============================================================

# Magic cookie - used to validate packets (must match on both ends)
MAGIC_COOKIE = 0xABCDDCBA

# Message types
MSG_TYPE_OFFER = 0x2    # Server broadcasts this to find clients
MSG_TYPE_REQUEST = 0x3  # Client sends this to request a game
MSG_TYPE_PAYLOAD = 0x4  # Used during gameplay for cards/decisions

# Packet sizes (in bytes)
OFFER_SIZE = 39      # 4 (cookie) + 1 (type) + 2 (port) + 32 (name)
REQUEST_SIZE = 38    # 4 (cookie) + 1 (type) + 1 (rounds) + 32 (name)
PAYLOAD_SIZE = 14    # 4 (cookie) + 1 (type) + 5 (decision) + 1 (result) + 3 (card)

# Decision constants (5 bytes each as per protocol spec)
DECISION_HIT = b'Hittt'    # "Hittt" = 5 bytes
DECISION_STAND = b'Stand'  # "Stand" = 5 bytes

# Game result constants (per protocol: win=0x3, loss=0x2, tie=0x1, none=0x0)
RESULT_NONE = 0x0   # Round not over yet
RESULT_TIE = 0x1    # Tie game
RESULT_LOSE = 0x2   # Player loses
RESULT_WIN = 0x3    # Player wins
RESULT_BUST = 0x4   # Player went over 21


# ============================================================
# OFFER PACKET (Server -> Client via UDP)
# Format: cookie(4) + type(1) + port(2) + name(32) = 39 bytes
# ============================================================

def pack_offer(tcp_port: int, server_name: str) -> bytes:
    """
    Create an offer packet that server broadcasts to find clients.
    
    Args:
        tcp_port: The TCP port clients should connect to
        server_name: Name of the server (max 32 characters)
    
    Returns:
        A 39-byte packet ready to send
    """
    # Step 1: Convert server name from string to bytes
    name_bytes = server_name.encode('utf-8')
    
    # Step 2: Truncate to max 32 bytes (in case name is too long)
    name_bytes = name_bytes[:32]
    
    # Step 3: Pad with null bytes (\x00) to exactly 32 bytes
    name_bytes = name_bytes.ljust(32, b'\x00')
    
    # Step 4: Pack the header using struct
    # '>IBH' means: big-endian, 4-byte uint, 1-byte uint, 2-byte uint
    header = struct.pack('>IBH', MAGIC_COOKIE, MSG_TYPE_OFFER, tcp_port)
    
    # Step 5: Combine header and name to form complete packet
    packet = header + name_bytes
    return packet


def unpack_offer(data: bytes) -> tuple:
    """
    Parse an offer packet received from a server.
    
    Args:
        data: Raw bytes received from UDP socket
    
    Returns:
        (tcp_port, server_name) if valid, None if invalid
    """
    # Check if packet is large enough
    if len(data) < OFFER_SIZE:
        return None
    
    # Step 1: Extract the first 7 bytes (header)
    header_bytes = data[:7]
    
    # Step 2: Unpack the header
    # '>IBH' means: big-endian, 4-byte uint, 1-byte uint, 2-byte uint
    cookie, msg_type, tcp_port = struct.unpack('>IBH', header_bytes)
    
    # Step 3: Validate magic cookie and message type
    if cookie != MAGIC_COOKIE:
        return None  # Invalid packet - wrong magic cookie
    if msg_type != MSG_TYPE_OFFER:
        return None  # Wrong message type
    
    # Step 4: Extract name bytes (bytes 7 to 39)
    name_bytes = data[7:39]
    
    # Step 5: Remove trailing null bytes from name
    name_bytes = name_bytes.rstrip(b'\x00')
    
    # Step 6: Convert bytes back to string
    server_name = name_bytes.decode('utf-8', errors='ignore')
    
    return (tcp_port, server_name)


# ============================================================
# REQUEST PACKET (Client -> Server via TCP)
# Format: cookie(4) + type(1) + rounds(1) + name(32) = 38 bytes
# ============================================================

def pack_request(rounds: int, client_name: str) -> bytes:
    """
    Create a request packet that client sends to join a game.
    
    Args:
        rounds: Number of rounds to play (1-255)
        client_name: Name of the client/player (max 32 characters)
    
    Returns:
        A 38-byte packet ready to send
    """
    # Step 1: Convert client name from string to bytes
    name_bytes = client_name.encode('utf-8')
    
    # Step 2: Truncate to max 32 bytes
    name_bytes = name_bytes[:32]
    
    # Step 3: Pad with null bytes to exactly 32 bytes
    name_bytes = name_bytes.ljust(32, b'\x00')
    
    # Step 4: Pack the header
    # '>IBB' means: big-endian, 4-byte uint, 1-byte uint, 1-byte uint
    header = struct.pack('>IBB', MAGIC_COOKIE, MSG_TYPE_REQUEST, rounds)
    
    # Step 5: Combine header and name
    packet = header + name_bytes
    return packet


def unpack_request(data: bytes) -> tuple:
    """
    Parse a request packet received from a client.
    
    Args:
        data: Raw bytes received from TCP socket
    
    Returns:
        (rounds, client_name) if valid, None if invalid
    """
    # Check if packet is large enough
    if len(data) < REQUEST_SIZE:
        return None
    
    # Step 1: Extract the first 6 bytes (header)
    header_bytes = data[:6]
    
    # Step 2: Unpack the header
    cookie, msg_type, rounds = struct.unpack('>IBB', header_bytes)
    
    # Step 3: Validate magic cookie and message type
    if cookie != MAGIC_COOKIE:
        return None
    if msg_type != MSG_TYPE_REQUEST:
        return None
    
    # Step 4: Extract name bytes (bytes 6 to 38)
    name_bytes = data[6:38]
    
    # Step 5: Remove trailing null bytes
    name_bytes = name_bytes.rstrip(b'\x00')
    
    # Step 6: Convert bytes to string
    client_name = name_bytes.decode('utf-8', errors='ignore')
    
    return (rounds, client_name)


# ============================================================
# PAYLOAD PACKET (Both directions via TCP)
# Format: cookie(4) + type(1) + decision(5) + result(1) + card(3) = 14 bytes
# Card format: rank(2 bytes) + suit(1 byte)
# ============================================================

def pack_payload(decision: bytes = b'\x00' * 5, result: int = RESULT_NONE,
                 card_rank: int = 0, card_suit: int = 0) -> bytes:
    """
    Create a payload packet for game communication.
    
    Used for:
        - Client sending hit/stand decision
        - Server sending cards and round results
    
    Args:
        decision: 5-byte decision (DECISION_HIT or DECISION_STAND)
        result: Game result code (RESULT_WIN, RESULT_LOSE, etc.)
        card_rank: Card rank 1-13 (0 means no card)
        card_suit: Card suit 0-3 (Hearts, Diamonds, Clubs, Spades)
    
    Returns:
        A 14-byte packet ready to send
    """
    # Step 1: Handle decision - convert string to bytes if needed
    if isinstance(decision, str):
        decision = decision.encode('utf-8')
        decision = decision[:5]  # Truncate to 5 bytes
        decision = decision.ljust(5, b'\x00')  # Pad to 5 bytes
    
    # Step 2: Pack the header (cookie + message type)
    header = struct.pack('>IB', MAGIC_COOKIE, MSG_TYPE_PAYLOAD)
    
    # Step 3: Pack the card data (result + rank + suit)
    # '>BHB' means: 1-byte result, 2-byte rank, 1-byte suit
    card_data = struct.pack('>BHB', result, card_rank, card_suit)
    
    # Step 4: Combine all parts
    packet = header + decision + card_data
    return packet


def unpack_payload(data: bytes) -> tuple:
    """
    Parse a payload packet.
    
    Args:
        data: Raw bytes received from socket
    
    Returns:
        (decision, result, card_rank, card_suit) if valid, None if invalid
    """
    # Check if packet is large enough
    if len(data) < PAYLOAD_SIZE:
        return None
    
    # Step 1: Extract and unpack header (first 5 bytes)
    header_bytes = data[:5]
    cookie, msg_type = struct.unpack('>IB', header_bytes)
    
    # Step 2: Validate magic cookie and message type
    if cookie != MAGIC_COOKIE:
        return None
    if msg_type != MSG_TYPE_PAYLOAD:
        return None
    
    # Step 3: Extract decision (bytes 5-10)
    decision = data[5:10]
    
    # Step 4: Extract and unpack card data (bytes 10-14)
    card_bytes = data[10:14]
    result, card_rank, card_suit = struct.unpack('>BHB', card_bytes)
    
    return (decision, result, card_rank, card_suit)


def decode_decision(decision: bytes) -> str:
    """
    Convert decision bytes to a readable string.
    
    Args:
        decision: 5-byte decision from payload
    
    Returns:
        "Hittt" or "Stand"
    """
    # Remove null padding bytes
    decision = decision.rstrip(b'\x00')
    # Convert to string (preserve case)
    return decision.decode('utf-8', errors='ignore')
