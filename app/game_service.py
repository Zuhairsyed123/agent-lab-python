import time
from dataclasses import dataclass, field

from app.game_logic import (
    check_bingo,
    generate_board,
    get_winning_square_ids,
    toggle_square,
)
from app.models import BingoLine, BingoSquareData, GameState


@dataclass
class GameSession:
    """Holds the state for a single game session."""

    game_state: GameState = GameState.START
    board: list[BingoSquareData] = field(default_factory=list)
    winning_line: BingoLine | None = None
    show_bingo_modal: bool = False
    last_accessed: float = field(default_factory=time.time)

    @property
    def winning_square_ids(self) -> set[int]:
        return get_winning_square_ids(self.winning_line)

    @property
    def has_bingo(self) -> bool:
        return self.game_state == GameState.BINGO

    def start_game(self) -> None:
        self._update_accessed()
        self.board = generate_board()
        self.winning_line = None
        self.game_state = GameState.PLAYING
        self.show_bingo_modal = False

    def handle_square_click(self, square_id: int) -> None:
        self._update_accessed()
        if self.game_state != GameState.PLAYING:
            return
        self.board = toggle_square(self.board, square_id)

        if self.winning_line is None:
            bingo = check_bingo(self.board)
            if bingo is not None:
                self.winning_line = bingo
                self.game_state = GameState.BINGO
                self.show_bingo_modal = True

    def reset_game(self) -> None:
        self._update_accessed()
        self.game_state = GameState.START
        self.board = []
        self.winning_line = None
        self.show_bingo_modal = False

    def dismiss_modal(self) -> None:
        self._update_accessed()
        self.show_bingo_modal = False
        self.game_state = GameState.PLAYING

    def _update_accessed(self) -> None:
        """Update the last accessed timestamp for session cleanup."""
        self.last_accessed = time.time()


# In-memory session store keyed by session ID
_sessions: dict[str, GameSession] = {}


def get_session(session_id: str) -> GameSession:
    """Get or create a game session for the given session ID.
    
    Args:
        session_id: Unique identifier for the session
    
    Returns:
        GameSession instance for the given session_id
    """
    if session_id not in _sessions:
        _sessions[session_id] = GameSession()
    else:
        _sessions[session_id]._update_accessed()
    return _sessions[session_id]
