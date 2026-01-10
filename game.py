"""
Game logic for Blackjack network game.
Contains Card, Deck, and Hand classes.
"""

import random
from typing import List, Optional


# ============================================================
# SUIT CONSTANTS
# Suits are numbered 0-3 for network transmission
# ============================================================

SUIT_HEARTS = 0
SUIT_DIAMONDS = 1
SUIT_CLUBS = 2
SUIT_SPADES = 3

# Display symbols for each suit
SUIT_SYMBOLS = ['♥', '♦', '♣', '♠']
SUIT_NAMES = ['Hearts', 'Diamonds', 'Clubs', 'Spades']

# Display names for card ranks (1=Ace, 11=Jack, 12=Queen, 13=King)
RANK_NAMES = {
    1: 'A', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7',
    8: '8', 9: '9', 10: '10', 11: 'J', 12: 'Q', 13: 'K'
}


# ============================================================
# CARD CLASS
# ============================================================

class Card:
    """Represents a single playing card."""
    
    def __init__(self, rank: int, suit: int):
        """
        Create a card.
        
        Args:
            rank: Card rank from 1-13
                  1 = Ace, 2-10 = number cards, 11=Jack, 12=Queen, 13=King
            suit: Card suit from 0-3
                  0=Hearts, 1=Diamonds, 2=Clubs, 3=Spades
        """
        self.rank = rank
        self.suit = suit
    
    @property
    def value(self) -> int:
        """
        Get the blackjack point value of this card.
        
        Returns:
            11 for Ace, 10 for face cards (J/Q/K), otherwise the rank number
        """
        if self.rank == 1:
            # Ace is worth 11 points
            return 11
        elif self.rank >= 11:
            # Face cards (Jack, Queen, King) are worth 10 points
            return 10
        else:
            # Number cards are worth their face value
            return self.rank
    
    def __str__(self) -> str:
        """Return a nice display string like 'A♥' or 'K♠'."""
        rank_str = RANK_NAMES[self.rank]
        suit_str = SUIT_SYMBOLS[self.suit]
        return f"{rank_str}{suit_str}"
    
    def __repr__(self) -> str:
        """Return a debug string like 'Card(1, 0)'."""
        return f"Card({self.rank}, {self.suit})"


# ============================================================
# DECK CLASS
# ============================================================

class Deck:
    """Represents a deck of 52 playing cards."""
    
    def __init__(self):
        """Create a new shuffled deck."""
        self.cards: List[Card] = []
        self.reset()
    
    def reset(self):
        """Reset the deck with all 52 cards and shuffle."""
        # Clear any existing cards
        self.cards = []
        
        # Create all 52 cards using nested loops
        # Outer loop: iterate through all 4 suits (0-3)
        for suit in range(4):
            # Inner loop: iterate through all 13 ranks (1-13)
            for rank in range(1, 14):
                # Create a new card and add it to the deck
                new_card = Card(rank, suit)
                self.cards.append(new_card)
        
        # Shuffle the deck
        self.shuffle()
    
    def shuffle(self):
        """Randomly shuffle the deck."""
        random.shuffle(self.cards)
    
    def draw(self) -> Optional[Card]:
        """
        Draw a card from the top of the deck.
        
        Returns:
            The drawn Card, or None if deck is empty
        """
        if len(self.cards) > 0:
            # Remove and return the last card (top of deck)
            return self.cards.pop()
        else:
            return None
    
    def __len__(self) -> int:
        """Return how many cards are left in the deck."""
        return len(self.cards)


# ============================================================
# HAND CLASS
# ============================================================

class Hand:
    """Represents a player's or dealer's hand of cards."""
    
    def __init__(self):
        """Create an empty hand."""
        self.cards: List[Card] = []
    
    def add_card(self, card: Card):
        """Add a card to the hand."""
        self.cards.append(card)
    
    @property
    def total(self) -> int:
        """
        Calculate the best total for this hand.
        
        In blackjack, Aces can be worth 11 or 1. This method
        automatically reduces Aces from 11 to 1 if needed to avoid busting.
        
        Returns:
            The total point value of the hand
        """
        # Step 1: Calculate total treating all Aces as 11
        total = 0
        for card in self.cards:
            total = total + card.value
        
        # Step 2: Count how many Aces we have
        ace_count = 0
        for card in self.cards:
            if card.rank == 1:  # Rank 1 is Ace
                ace_count = ace_count + 1
        
        # Step 3: Reduce Aces from 11 to 1 (subtract 10) if we're over 21
        # Keep reducing until we're at 21 or below, or no more Aces to reduce
        while total > 21 and ace_count > 0:
            total = total - 10  # Change one Ace from 11 to 1
            ace_count = ace_count - 1
        
        return total
    
    @property
    def is_bust(self) -> bool:
        """Check if the hand has busted (total over 21)."""
        return self.total > 21
    
    @property
    def is_blackjack(self) -> bool:
        """Check if this is a natural blackjack (21 with exactly 2 cards)."""
        has_two_cards = len(self.cards) == 2
        has_21_points = self.total == 21
        return has_two_cards and has_21_points
    
    def __str__(self) -> str:
        """Return a display string like '[A♥ K♠] (Total: 21)'."""
        # Build a string of all cards separated by spaces
        card_strings = []
        for card in self.cards:
            card_strings.append(str(card))
        cards_display = ' '.join(card_strings)
        
        return f"[{cards_display}] (Total: {self.total})"
    
    def __len__(self) -> int:
        """Return how many cards are in the hand."""
        return len(self.cards)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def determine_winner(player_hand: Hand, dealer_hand: Hand) -> int:
    """
    Determine the winner of a blackjack round.
    
    Args:
        player_hand: The player's hand
        dealer_hand: The dealer's hand
    
    Returns:
        RESULT_WIN (1) if player wins
        RESULT_LOSE (2) if dealer wins
        RESULT_TIE (3) if it's a tie
    """
    # Import result constants from protocol
    from protocol import RESULT_WIN, RESULT_LOSE, RESULT_TIE
    
    player_total = player_hand.total
    dealer_total = dealer_hand.total
    
    # Rule 1: If player busted, dealer wins
    if player_hand.is_bust:
        return RESULT_LOSE
    
    # Rule 2: If dealer busted, player wins
    if dealer_hand.is_bust:
        return RESULT_WIN
    
    # Rule 3: Compare totals
    if player_total > dealer_total:
        return RESULT_WIN
    elif dealer_total > player_total:
        return RESULT_LOSE
    else:
        return RESULT_TIE
