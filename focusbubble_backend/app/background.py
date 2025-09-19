# background.py
import asyncio
from .database import SessionLocal
from .crud import deactivate_expired_blocks, list_active_sessions
from datetime import datetime
import logging
  
logger = logging.getLogger("focusbubble.background")
  
async def expiry_loop(poll_seconds:int = 30):
    """
    Background loop to expire sessions and blocks.
    It runs every poll_seconds and marks expired blocks/sessions.
    Note: Sessions are not explicitly finished here, but block rows are deactivated.
    """
    while True:
        try:
            db = SessionLocal()
            expired_blocks = deactivate_expired_blocks(db)
            if expired_blocks:
                logger.info(f"Expired {len(expired_blocks)} blocks at {datetime.utcnow().isoformat()}")
            # Optionally also mark sessions finished if end_time passed
            # (update status to finished)
            now = datetime.utcnow()
            sessions = db.query.__class__  # dummy to avoid lint; below we do session query properly
            # mark sessions which are running but end_time <= now as finished
            from .models import FocusSession
            rows = db.query(FocusSession).filter(FocusSession.status == "running", FocusSession.end_time <= now).all()
            for r in rows:
                r.status = "finished"
            if rows:
                db.commit()
                logger.info(f"Marked {len(rows)} sessions finished.")
        except Exception as e:
            logger.exception("Background expiry loop error: %s", e)
        finally:
            try:
                db.close()
            except:
                pass
        await asyncio.sleep(poll_seconds)
