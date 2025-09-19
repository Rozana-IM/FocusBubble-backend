# crud.py
from sqlalchemy.orm import Session
from . import models, schemas
from datetime import datetime, timedelta
from typing import List
from . import models

  
# USER
def get_or_create_user(db: Session, email: str, name: str = None, picture: str = None):
    u = db.query(models.User).filter(models.User.email == email).first()
    if u:
        # update name/picture if changed
        changed = False
        if name and u.name != name:
            u.name = name; changed = True
        if picture and u.picture != picture:
            u.picture = picture; changed = True
        if changed:
            db.commit(); db.refresh(u)
        return u
    u = models.User(email=email, name=name, picture=picture)
    db.add(u); db.commit(); db.refresh(u)
    return u
  
def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()
  
# SCHEDULES
def create_schedule(db: Session, user_id: int, sched: schemas.ScheduleCreate):
    s = models.Schedule(
        user_id=user_id,
        label=sched.label,
        duration_minutes=sched.duration_minutes,
        apps_csv=",".join(sched.apps),
        is_active=sched.is_active
    )
    db.add(s); db.commit(); db.refresh(s)
    return s
  
def list_schedules(db: Session, user_id: int):
    rows = db.query(models.Schedule).filter(models.Schedule.user_id == user_id).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id, "label": r.label, "duration_minutes": r.duration_minutes,
            "apps": r.apps_csv.split(",") if r.apps_csv else [], "is_active": r.is_active,
            "created_at": r.created_at
        })
    return out
  
def delete_schedule(db: Session, user_id: int, schedule_id: int):
    s = db.query(models.Schedule).filter(models.Schedule.user_id == user_id,
                                         models.Schedule.id == schedule_id).first()
    if s:
        db.delete(s); db.commit(); return True
    return False
  
# SESSIONS
def start_session(db: Session, user_id: int, schedule_id: int, duration_minutes: int):
    now = datetime.utcnow()
    end = now + timedelta(minutes=duration_minutes)
    s = models.FocusSession(
        user_id=user_id,
        schedule_id=schedule_id,
        start_time=now,
        end_time=end,
        paused=False,
        remaining_seconds=None,
        status="running"
    )
    db.add(s); db.commit(); db.refresh(s)
    return s
  
def pause_session(db: Session, session_id: int):
    s = db.query(models.FocusSession).filter(models.FocusSession.id == session_id).first()
    if not s:
        return None
    if s.paused or s.status != "running":
        return s
    now = datetime.utcnow()
    remaining = int((s.end_time - now).total_seconds())
    s.paused = True
    s.paused_at = now
    s.remaining_seconds = remaining
    s.status = "paused"
    db.commit(); db.refresh(s)
    return s
  
def resume_session(db: Session, session_id: int):
    s = db.query(models.FocusSession).filter(models.FocusSession.id == session_id).first()
    if not s:
        return None
    if not s.paused:
        return s
    now = datetime.utcnow()
    new_end = now + timedelta(seconds=s.remaining_seconds or 0)
    s.paused = False
    s.paused_at = None
    s.end_time = new_end
    s.remaining_seconds = None
    s.status = "running"
    db.commit(); db.refresh(s)
    return s
  
def stop_session(db: Session, session_id: int):
    s = db.query(models.FocusSession).filter(models.FocusSession.id == session_id).first()
    if not s:
        return None
    s.status = "stopped"
    s.paused = False
    s.remaining_seconds = None
    db.commit(); db.refresh(s)
    return s
  
def list_active_sessions(db: Session, user_id: int):
    now = datetime.utcnow()
    rows = db.query(models.FocusSession).filter(
        models.FocusSession.user_id == user_id,
        models.FocusSession.status == "running",
        models.FocusSession.end_time > now
    ).all()
    return rows
  
# BLOCKS
def create_blocked_apps_for_session(db: Session, user_id: int, package_names: List[str], duration_minutes: int, app_names = None):
    """
    Creates BlockedApp rows for given packages for given duration (from now).
    """
    now = datetime.utcnow()
    end = now + timedelta(minutes=duration_minutes)
    created = []
    for i, pkg in enumerate(package_names):
        app_name = None
        if app_names and len(app_names) > i:
            app_name = app_names[i]
        # upsert active block for same package: create new row
        b = models.BlockedApp(
            user_id=user_id, package_name=pkg, app_name=app_name,
            start_time=now, end_time=end, is_active=True
        )
        db.add(b)
        created.append(b)
    db.commit()
    for c in created: db.refresh(c)
    return created
  
def list_active_blocked_apps(db: Session, user_id: int):
    now = datetime.utcnow()
    rows = db.query(models.BlockedApp).filter(
        models.BlockedApp.user_id == user_id,
        models.BlockedApp.is_active == True,
        models.BlockedApp.end_time > now
    ).all()
    return rows
  
def deactivate_expired_blocks(db: Session):
    now = datetime.utcnow()
    expired = db.query(models.BlockedApp).filter(
        models.BlockedApp.is_active == True,
        models.BlockedApp.end_time <= now
    ).all()
    for e in expired:
        e.is_active = False
    db.commit()
    return expired
