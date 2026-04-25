import logging
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, TemplateResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.game_service import GameSession, get_session
from app.models import GameState

# Configuration
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")
BOARD_SIZE = 25  # 5x5 bingo board
SESSION_LIFETIME_SECONDS = 86400  # 24 hours
CLEANUP_INTERVAL_SECONDS = 3600  # 1 hour

BASE_DIR = Path(__file__).resolve().parent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Soc Ops - Social Bingo")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Track last cleanup time
_last_cleanup_time = time.time()


def _get_game_session(request: Request) -> GameSession:
    """Get or create a game session using cookie-based sessions.
    
    Args:
        request: FastAPI request object
        
    Returns:
        GameSession instance for the current user
    """
    if "session_id" not in request.session:
        session_id = uuid.uuid4().hex
        request.session["session_id"] = session_id
        logger.info(f"Created new session: {session_id}")
    return get_session(request.session["session_id"])


def _render_template(
    name: str, request: Request, session: GameSession, **kwargs
) -> TemplateResponse:
    """Helper to render templates with common context.
    
    Args:
        name: Template file name
        request: FastAPI request object
        session: Game session instance
        **kwargs: Additional context variables
        
    Returns:
        TemplateResponse with rendered template
    """
    context = {"session": session, **kwargs}
    return templates.TemplateResponse(request, name, context)


def _cleanup_stale_sessions() -> None:
    """Remove sessions that haven't been accessed in SESSION_LIFETIME_SECONDS.
    
    This prevents memory leaks from accumulating abandoned sessions.
    """
    global _last_cleanup_time
    current_time = time.time()
    
    # Only run cleanup at intervals to avoid performance impact
    if current_time - _last_cleanup_time < CLEANUP_INTERVAL_SECONDS:
        return
    
    _last_cleanup_time = current_time
    cutoff_time = current_time - SESSION_LIFETIME_SECONDS
    
    from app.game_service import _sessions
    
    expired_sessions = [
        sid for sid, sess in _sessions.items() if sess.last_accessed < cutoff_time
    ]
    
    for sid in expired_sessions:
        del _sessions[sid]
        logger.info(f"Cleaned up expired session: {sid}")
    
    if expired_sessions:
        logger.info(f"Cleanup completed: removed {len(expired_sessions)} expired sessions")


@app.on_event("startup")
def startup_event() -> None:
    """Application startup event handler."""
    logger.info("Soc Ops - Social Bingo app started")


@app.on_event("shutdown")
def shutdown_event() -> None:
    """Application shutdown event handler."""
    logger.info("Running final session cleanup...")
    _cleanup_stale_sessions()
    logger.info("Soc Ops - Social Bingo app stopped")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> TemplateResponse:
    """Home page endpoint.
    
    Displays the main page where users can start a new game.
    """
    session = _get_game_session(request)
    _cleanup_stale_sessions()
    return _render_template("home.html", request, session, GameState=GameState)


@app.post("/start", response_class=HTMLResponse)
async def start_game(request: Request) -> TemplateResponse:
    """Start a new game.
    
    Initializes a new bingo board and transitions to playing state.
    """
    session = _get_game_session(request)
    session.start_game()
    logger.info(f"Game started for session {request.session['session_id']}")
    return _render_template("components/game_screen.html", request, session)


@app.post("/toggle/{square_id}", response_class=HTMLResponse)
async def toggle_square(request: Request, square_id: int) -> TemplateResponse:
    """Toggle a bingo square.
    
    Marks or unmarks a square on the board and checks for winning lines.
    
    Args:
        request: FastAPI request object
        square_id: ID of the square to toggle (0-24)
        
    Returns:
        TemplateResponse with updated game screen
        
    Raises:
        HTTPException: If square_id is out of valid range
    """
    if not (0 <= square_id < BOARD_SIZE):
        logger.warning(f"Invalid square ID attempted: {square_id}")
        raise HTTPException(status_code=400, detail=f"Square ID must be between 0 and {BOARD_SIZE - 1}")
    
    session = _get_game_session(request)
    session.handle_square_click(square_id)
    logger.debug(f"Square {square_id} toggled for session {request.session['session_id']}")
    return _render_template("components/game_screen.html", request, session)


@app.post("/reset", response_class=HTMLResponse)
async def reset_game(request: Request) -> TemplateResponse:
    """Reset the current game.
    
    Returns the game to the start state, clearing the board and resetting the session.
    """
    session = _get_game_session(request)
    session.reset_game()
    logger.info(f"Game reset for session {request.session['session_id']}")
    return _render_template(
        "components/start_screen.html", request, session, GameState=GameState
    )


@app.post("/dismiss-modal", response_class=HTMLResponse)
async def dismiss_modal(request: Request) -> TemplateResponse:
    """Dismiss the bingo modal and resume playing.
    
    Closes the bingo celebration modal and returns to the game screen.
    """
    session = _get_game_session(request)
    session.dismiss_modal()
    logger.debug(f"Modal dismissed for session {request.session['session_id']}")
    return _render_template("components/game_screen.html", request, session)


def run() -> None:
    """Entry point for the application.
    
    Starts the Uvicorn development server with auto-reload enabled.
    """
    import uvicorn

    logger.info("Starting Uvicorn server...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
