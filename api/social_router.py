"""
Social API Router — Community features for DriveGuard
"""
import math
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from .database import get_db
from .models import (
    User, Vehicle, Trip, TelemetryPoint, UserFollow, SharedTrip,
    TripReaction, CommunityPost, DrivingChallenge,
    UserChallengeProgress, SharedRoute, Notification
)
from .schemas import (
    DriverProfileResponse, ProfileUpdateRequest,
    FollowRequest, FollowResponse, FollowerListResponse,
    ShareTripRequest, SharedTripResponse, SharedTripFeedResponse,
    ReactionRequest, ReactionResponse,
    LeaderboardEntry, LeaderboardResponse,
    CommunityPostCreate, CommunityPostResponse, CommunityFeedResponse,
    ChallengeResponse, ChallengeProgressResponse, ChallengesListResponse,
    SharedRouteCreate, SharedRouteResponse, SharedRoutesListResponse,
    NearbyDriverResponse,
    NotificationResponse, NotificationListResponse, HeatmapPoint, HeatmapResponse,
    TripCompStats, TripComparisonResponse, DrivingReportResponse
)

logger = logging.getLogger("social_api")
router = APIRouter(prefix="/api/social", tags=["Social"])

XP_LEVELS = {1: 0, 2: 100, 3: 300, 4: 600, 5: 1000, 6: 2000}

def _calc_level(xp: int) -> int:
    level = 1
    for lvl, req in sorted(XP_LEVELS.items()):
        if xp >= req:
            level = lvl
    return level

def _create_notif(user_id, type, title, message=None, extra_data=None, db=None):
    notif = Notification(user_id=user_id, type=type, title=title, message=message, extra_data=extra_data)
    db.add(notif)
    db.commit()
    return notif

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(d_lon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def _user_profile(user, db, requester_id=None):
    followers = db.query(UserFollow).filter(UserFollow.following_id == user.id).count()
    following = db.query(UserFollow).filter(UserFollow.follower_id == user.id).count()
    is_following = False
    if requester_id and requester_id != user.id:
        is_following = db.query(UserFollow).filter(
            UserFollow.follower_id == requester_id, UserFollow.following_id == user.id
        ).first() is not None
    return DriverProfileResponse(
        id=user.id, name=user.name, email=user.email,
        avatar_color=user.avatar_color or "#00E676", bio=user.bio or "",
        safety_score=round(user.safety_score or 100.0, 1),
        total_trips=user.total_trips or 0,
        total_distance_km=round(user.total_distance_km or 0, 1),
        xp_points=user.xp_points or 0, driver_level=user.driver_level or 1,
        followers_count=followers, following_count=following,
        is_following=is_following, created_at=str(user.created_at)
    )

def _shared_trip_resp(st, user, db, requester_id=None):
    likes = db.query(TripReaction).filter(TripReaction.shared_trip_id==st.id, TripReaction.reaction_type=="like").count()
    good = db.query(TripReaction).filter(TripReaction.shared_trip_id==st.id, TripReaction.reaction_type=="good_drive").count()
    warns = db.query(TripReaction).filter(TripReaction.shared_trip_id==st.id, TripReaction.reaction_type=="warning").count()
    user_react = None
    if requester_id:
        r = db.query(TripReaction).filter(TripReaction.shared_trip_id==st.id, TripReaction.user_id==requester_id).first()
        if r: user_react = r.reaction_type
    return SharedTripResponse(
        id=st.id, user_id=st.user_id, user_name=user.name,
        avatar_color=user.avatar_color or "#00E676", driver_level=user.driver_level or 1,
        trip_id=st.trip_id, caption=st.caption, safety_score=st.safety_score,
        distance_km=round(st.distance_km, 1), duration_seconds=st.duration_seconds,
        route_polyline=st.route_polyline, like_count=likes,
        good_drive_count=good, warning_count=warns,
        user_reaction=user_react, created_at=str(st.created_at)
    )


# ─── Profile ─────────────────────────────────────────────────────────────

@router.get("/profile/{user_id}", response_model=DriverProfileResponse)
async def get_profile(user_id: str, requester_id: str = None, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return _user_profile(user, db, requester_id)

@router.put("/profile/{user_id}", response_model=DriverProfileResponse)
async def update_profile(user_id: str, data: ProfileUpdateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if data.bio is not None: user.bio = data.bio
    if data.avatar_color is not None: user.avatar_color = data.avatar_color
    db.commit()
    db.refresh(user)
    return _user_profile(user, db)


# ─── Follow System ───────────────────────────────────────────────────────

@router.post("/follow", response_model=FollowResponse)
async def follow_user(data: FollowRequest, db: Session = Depends(get_db)):
    if data.follower_id == data.following_id:
        raise HTTPException(400, "Cannot follow yourself")
    existing = db.query(UserFollow).filter(
        UserFollow.follower_id == data.follower_id, UserFollow.following_id == data.following_id
    ).first()
    if existing:
        raise HTTPException(409, "Already following")
    follow = UserFollow(follower_id=data.follower_id, following_id=data.following_id)
    db.add(follow)
    # +1 XP for following
    follower = db.query(User).filter(User.id == data.follower_id).first()
    if follower:
        follower.xp_points = (follower.xp_points or 0) + 1
        follower.driver_level = _calc_level(follower.xp_points)
    
    # Notify following user
    _create_notif(data.following_id, "follow", "New Follower", f"{follower.name if follower else 'Someone'} started following you", {"follower_id": data.follower_id}, db)
    
    db.commit()
    db.refresh(follow)
    return FollowResponse(id=follow.id, follower_id=follow.follower_id,
                          following_id=follow.following_id, created_at=str(follow.created_at))

@router.delete("/unfollow")
async def unfollow_user(data: FollowRequest, db: Session = Depends(get_db)):
    follow = db.query(UserFollow).filter(
        UserFollow.follower_id == data.follower_id, UserFollow.following_id == data.following_id
    ).first()
    if not follow:
        raise HTTPException(404, "Not following")
    db.delete(follow)
    db.commit()
    return {"status": "unfollowed"}

@router.get("/followers/{user_id}", response_model=FollowerListResponse)
async def get_followers(user_id: str, db: Session = Depends(get_db)):
    follows = db.query(UserFollow).filter(UserFollow.following_id == user_id).all()
    users = []
    for f in follows:
        u = db.query(User).filter(User.id == f.follower_id).first()
        if u: users.append(_user_profile(u, db, user_id))
    return FollowerListResponse(count=len(users), users=users)

@router.get("/following/{user_id}", response_model=FollowerListResponse)
async def get_following(user_id: str, db: Session = Depends(get_db)):
    follows = db.query(UserFollow).filter(UserFollow.follower_id == user_id).all()
    users = []
    for f in follows:
        u = db.query(User).filter(User.id == f.following_id).first()
        if u: users.append(_user_profile(u, db, user_id))
    return FollowerListResponse(count=len(users), users=users)


# ─── Trip Sharing ────────────────────────────────────────────────────────

def _compute_safety_score(trip):
    base = 100
    base -= (trip.red_alert_count or 0) * 5
    base -= (trip.yellow_alert_count or 0) * 2
    if (trip.red_alert_count or 0) == 0: base += 5
    if (trip.point_count or 0) > 50 and (trip.avg_risk_score or 0) < 20: base += 3
    return max(0, min(100, base))

@router.post("/trips/share", response_model=SharedTripResponse)
async def share_trip(data: ShareTripRequest, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == data.trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    # Already shared?
    existing = db.query(SharedTrip).filter(SharedTrip.trip_id == data.trip_id).first()
    if existing:
        raise HTTPException(409, "Trip already shared")
    # Extract route polyline (sample every 5th point)
    points = db.query(TelemetryPoint).filter(
        TelemetryPoint.trip_id == data.trip_id
    ).order_by(TelemetryPoint.timestamp.asc()).all()
    polyline = [{"lat": p.latitude, "lon": p.longitude} for i, p in enumerate(points) if i % 5 == 0]
    # Compute duration
    duration = 0
    if len(points) >= 2:
        try:
            duration = int((points[-1].timestamp - points[0].timestamp).total_seconds())
        except: pass
    score = _compute_safety_score(trip)
    st = SharedTrip(
        user_id=data.user_id, trip_id=data.trip_id, caption=data.caption,
        safety_score=score, distance_km=trip.total_distance_km or 0,
        duration_seconds=duration, route_polyline=polyline
    )
    db.add(st)
    # +3 XP, update user score
    user.xp_points = (user.xp_points or 0) + 3
    user.driver_level = _calc_level(user.xp_points)
    db.commit()
    db.refresh(st)
    return _shared_trip_resp(st, user, db)

@router.get("/feed", response_model=SharedTripFeedResponse)
async def get_feed(page: int = 0, limit: int = 20, requester_id: str = None, db: Session = Depends(get_db)):
    trips = db.query(SharedTrip).order_by(desc(SharedTrip.created_at)).offset(page*limit).limit(limit).all()
    results = []
    for st in trips:
        user = db.query(User).filter(User.id == st.user_id).first()
        if user:
            results.append(_shared_trip_resp(st, user, db, requester_id))
    return SharedTripFeedResponse(count=len(results), trips=results)

@router.get("/feed/following", response_model=SharedTripFeedResponse)
async def get_following_feed(user_id: str, page: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    following_ids = [f.following_id for f in db.query(UserFollow).filter(UserFollow.follower_id == user_id).all()]
    following_ids.append(user_id)  # Include own posts
    trips = db.query(SharedTrip).filter(SharedTrip.user_id.in_(following_ids))\
        .order_by(desc(SharedTrip.created_at)).offset(page*limit).limit(limit).all()
    results = []
    for st in trips:
        user = db.query(User).filter(User.id == st.user_id).first()
        if user: results.append(_shared_trip_resp(st, user, db, user_id))
    return SharedTripFeedResponse(count=len(results), trips=results)

@router.get("/trips/user/{user_id}", response_model=SharedTripFeedResponse)
async def get_user_shared_trips(user_id: str, requester_id: str = None, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    trips = db.query(SharedTrip).filter(SharedTrip.user_id == user_id).order_by(desc(SharedTrip.created_at)).all()
    results = [_shared_trip_resp(st, user, db, requester_id) for st in trips]
    return SharedTripFeedResponse(count=len(results), trips=results)


# ─── Reactions ───────────────────────────────────────────────────────────

@router.post("/react", response_model=ReactionResponse)
async def react(data: ReactionRequest, db: Session = Depends(get_db)):
    if data.reaction_type not in ("like", "good_drive", "warning"):
        raise HTTPException(400, "Invalid reaction type")
    existing = db.query(TripReaction).filter(
        TripReaction.user_id == data.user_id,
        TripReaction.shared_trip_id == data.shared_trip_id,
        TripReaction.reaction_type == data.reaction_type
    ).first()
    if existing:
        raise HTTPException(409, "Already reacted")
    reaction = TripReaction(user_id=data.user_id, shared_trip_id=data.shared_trip_id, reaction_type=data.reaction_type)
    db.add(reaction)
    # +2 XP for trip author on good_drive
    if data.reaction_type == "good_drive":
        st = db.query(SharedTrip).filter(SharedTrip.id == data.shared_trip_id).first()
        if st:
            author = db.query(User).filter(User.id == st.user_id).first()
            if author:
                author.xp_points = (author.xp_points or 0) + 2
                author.driver_level = _calc_level(author.xp_points)
                # Notify author
                reactor = db.query(User).filter(User.id == data.user_id).first()
                _create_notif(author.id, "reaction", "Good Drive!", f"{reactor.name if reactor else 'Someone'} reacted 'Good Drive' to your trip", {"trip_id": st.trip_id}, db)
    db.commit()
    db.refresh(reaction)
    return ReactionResponse(id=reaction.id, user_id=reaction.user_id,
        shared_trip_id=reaction.shared_trip_id, reaction_type=reaction.reaction_type,
        created_at=str(reaction.created_at))

@router.delete("/react/{reaction_id}")
async def remove_reaction(reaction_id: int, db: Session = Depends(get_db)):
    reaction = db.query(TripReaction).filter(TripReaction.id == reaction_id).first()
    if not reaction: raise HTTPException(404, "Reaction not found")
    db.delete(reaction)
    db.commit()
    return {"status": "removed"}


# ─── Leaderboard ─────────────────────────────────────────────────────────

@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(period: str = "alltime", user_id: str = None, limit: int = 50, db: Session = Depends(get_db)):
    users = db.query(User).filter(User.total_trips > 0).order_by(desc(User.safety_score)).limit(limit).all()
    entries = []
    user_rank = None
    for i, u in enumerate(users):
        entries.append(LeaderboardEntry(
            rank=i+1, user_id=u.id, name=u.name,
            avatar_color=u.avatar_color or "#00E676",
            safety_score=round(u.safety_score or 100, 1),
            total_trips=u.total_trips or 0,
            driver_level=u.driver_level or 1,
            xp_points=u.xp_points or 0
        ))
        if user_id and u.id == user_id:
            user_rank = i + 1
    return LeaderboardResponse(period=period, count=len(entries), entries=entries, user_rank=user_rank)


# ─── Community Posts ─────────────────────────────────────────────────────

@router.post("/feed/post", response_model=CommunityPostResponse)
async def create_post(data: CommunityPostCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user: raise HTTPException(404, "User not found")
    post = CommunityPost(
        user_id=data.user_id, post_type=data.post_type, content=data.content,
        latitude=data.latitude, longitude=data.longitude, extra_data=data.extra_data
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return CommunityPostResponse(
        id=post.id, user_id=post.user_id, user_name=user.name,
        avatar_color=user.avatar_color or "#00E676", driver_level=user.driver_level or 1,
        post_type=post.post_type, content=post.content,
        latitude=post.latitude, longitude=post.longitude,
        extra_data=post.extra_data, like_count=0, created_at=str(post.created_at)
    )


# ─── Challenges ──────────────────────────────────────────────────────────

@router.get("/challenges", response_model=ChallengesListResponse)
async def get_challenges(user_id: str = None, db: Session = Depends(get_db)):
    all_challenges = db.query(DrivingChallenge).filter(DrivingChallenge.is_active == True).all()
    available, active, completed = [], [], []
    joined_ids = set()
    if user_id:
        progresses = db.query(UserChallengeProgress).filter(UserChallengeProgress.user_id == user_id).all()
        for p in progresses:
            joined_ids.add(p.challenge_id)
            ch = db.query(DrivingChallenge).filter(DrivingChallenge.id == p.challenge_id).first()
            if not ch: continue
            cr = ChallengeResponse(id=ch.id, title=ch.title, description=ch.description,
                icon=ch.icon, challenge_type=ch.challenge_type, target_value=ch.target_value,
                xp_reward=ch.xp_reward, period=ch.period, is_active=ch.is_active)
            pct = min(100, (p.current_value / max(ch.target_value, 1)) * 100)
            pr = ChallengeProgressResponse(challenge=cr, current_value=p.current_value,
                completed=p.completed, completed_at=str(p.completed_at) if p.completed_at else None,
                joined_at=str(p.joined_at), progress_pct=round(pct, 1))
            if p.completed: completed.append(pr)
            else: active.append(pr)
    for ch in all_challenges:
        if ch.id not in joined_ids:
            available.append(ChallengeResponse(id=ch.id, title=ch.title, description=ch.description,
                icon=ch.icon, challenge_type=ch.challenge_type, target_value=ch.target_value,
                xp_reward=ch.xp_reward, period=ch.period, is_active=ch.is_active))
    return ChallengesListResponse(available=available, active=active, completed=completed)

@router.post("/challenges/{challenge_id}/join")
async def join_challenge(challenge_id: int, user_id: str = "", db: Session = Depends(get_db)):
    if not user_id: raise HTTPException(400, "user_id required")
    ch = db.query(DrivingChallenge).filter(DrivingChallenge.id == challenge_id).first()
    if not ch: raise HTTPException(404, "Challenge not found")
    existing = db.query(UserChallengeProgress).filter(
        UserChallengeProgress.user_id == user_id, UserChallengeProgress.challenge_id == challenge_id
    ).first()
    if existing: raise HTTPException(409, "Already joined")
    progress = UserChallengeProgress(user_id=user_id, challenge_id=challenge_id)
    db.add(progress)
    db.commit()
    return {"status": "joined", "challenge_id": challenge_id}


# ─── Shared Routes ───────────────────────────────────────────────────────

@router.post("/routes/share", response_model=SharedRouteResponse)
async def share_route(data: SharedRouteCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user: raise HTTPException(404, "User not found")
    trip = db.query(Trip).filter(Trip.id == data.trip_id).first()
    if not trip: raise HTTPException(404, "Trip not found")
    points = db.query(TelemetryPoint).filter(TelemetryPoint.trip_id == data.trip_id)\
        .order_by(TelemetryPoint.timestamp.asc()).all()
    if len(points) < 2: raise HTTPException(400, "Trip has insufficient data")
    polyline = [{"lat": p.latitude, "lon": p.longitude} for i, p in enumerate(points) if i % 3 == 0]
    route = SharedRoute(
        user_id=data.user_id, title=data.title, description=data.description,
        start_lat=points[0].latitude, start_lon=points[0].longitude,
        end_lat=points[-1].latitude, end_lon=points[-1].longitude,
        route_polyline=polyline, safety_score=_compute_safety_score(trip),
        distance_km=trip.total_distance_km or 0
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return SharedRouteResponse(
        id=route.id, user_id=route.user_id, user_name=user.name,
        avatar_color=user.avatar_color or "#00E676",
        title=route.title, description=route.description,
        start_lat=route.start_lat, start_lon=route.start_lon,
        end_lat=route.end_lat, end_lon=route.end_lon,
        route_polyline=route.route_polyline, safety_score=route.safety_score,
        distance_km=round(route.distance_km, 1), follower_count=0,
        created_at=str(route.created_at)
    )

@router.get("/routes/nearby", response_model=SharedRoutesListResponse)
async def get_nearby_routes(lat: float, lon: float, radius_km: float = 10.0, db: Session = Depends(get_db)):
    routes = db.query(SharedRoute).all()
    nearby = []
    for r in routes:
        dist = _haversine(lat, lon, r.start_lat, r.start_lon)
        if dist <= radius_km:
            user = db.query(User).filter(User.id == r.user_id).first()
            nearby.append(SharedRouteResponse(
                id=r.id, user_id=r.user_id, user_name=user.name if user else "",
                avatar_color=(user.avatar_color if user else "#00E676") or "#00E676",
                title=r.title, description=r.description,
                start_lat=r.start_lat, start_lon=r.start_lon,
                end_lat=r.end_lat, end_lon=r.end_lon,
                route_polyline=r.route_polyline, safety_score=r.safety_score,
                distance_km=round(r.distance_km, 1), follower_count=r.follower_count or 0,
                created_at=str(r.created_at)
            ))
    nearby.sort(key=lambda x: x.safety_score, reverse=True)
    return SharedRoutesListResponse(count=len(nearby), routes=nearby)

@router.get("/routes/{route_id}", response_model=SharedRouteResponse)
async def get_route(route_id: int, db: Session = Depends(get_db)):
    r = db.query(SharedRoute).filter(SharedRoute.id == route_id).first()
    if not r: raise HTTPException(404, "Route not found")
    user = db.query(User).filter(User.id == r.user_id).first()
    return SharedRouteResponse(
        id=r.id, user_id=r.user_id, user_name=user.name if user else "",
        avatar_color=(user.avatar_color if user else "#00E676") or "#00E676",
        title=r.title, description=r.description,
        start_lat=r.start_lat, start_lon=r.start_lon,
        end_lat=r.end_lat, end_lon=r.end_lon,
        route_polyline=r.route_polyline, safety_score=r.safety_score,
        distance_km=round(r.distance_km, 1), follower_count=r.follower_count or 0,
        created_at=str(r.created_at)
    )


# ─── Nearby Drivers ──────────────────────────────────────────────────────

@router.get("/nearby")
async def get_nearby_drivers(lat: float, lon: float, radius_km: float = 5.0, db: Session = Depends(get_db)):
    # Find users with recent telemetry near this location
    from sqlalchemy import text
    recent = db.query(TelemetryPoint).order_by(desc(TelemetryPoint.timestamp)).limit(500).all()
    seen = {}
    for p in recent:
        dist = _haversine(lat, lon, p.latitude, p.longitude)
        if dist <= radius_km and p.trip_id not in seen:
            trip = db.query(Trip).filter(Trip.id == p.trip_id).first()
            if trip:
                vehicle_user = db.execute(
                    text("SELECT user_id FROM vehicles WHERE id = :vid"), {"vid": trip.vehicle_id}
                ).first()
                if vehicle_user and vehicle_user[0] not in seen:
                    user = db.query(User).filter(User.id == vehicle_user[0]).first()
                    if user:
                        seen[user.id] = NearbyDriverResponse(
                            user_id=user.id, name=user.name,
                            avatar_color=user.avatar_color or "#00E676",
                            driver_level=user.driver_level or 1,
                            safety_score=round(user.safety_score or 100, 1),
                            last_active=str(p.timestamp), distance_km=round(dist, 1)
                        )
    drivers = sorted(seen.values(), key=lambda d: d.distance_km)
    return {"count": len(drivers), "drivers": [d.model_dump() for d in drivers]}


@router.get("/search")
async def search_users(q: str = "", db: Session = Depends(get_db)):
    """Search for users by name or email."""
    if not q or len(q) < 2:
        return {"count": 0, "users": []}
    
    users = db.query(User).filter(
        (User.name.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%"))
    ).limit(20).all()
    
    return {
        "count": len(users),
        "users": [_user_profile(u, db) for u in users]
    }


# ─── Seed Challenges ─────────────────────────────────────────────────────

def seed_challenges(db: Session):
    """Insert default challenges if none exist."""
    if db.query(DrivingChallenge).count() > 0:
        return
    challenges = [
        DrivingChallenge(title="First Safe Trip", description="Complete a trip with safety score above 80", icon="🛡️", challenge_type="score", target_value=80, xp_reward=20, period="alltime"),
        DrivingChallenge(title="7-Day Streak", description="Drive safely for 7 consecutive days", icon="🔥", challenge_type="streak", target_value=7, xp_reward=50, period="weekly"),
        DrivingChallenge(title="Marathon Driver", description="Drive 100km total distance", icon="🏔️", challenge_type="distance", target_value=100, xp_reward=40, period="monthly"),
        DrivingChallenge(title="Zen Mode", description="Complete a trip with safety score above 95", icon="🧘", challenge_type="score", target_value=95, xp_reward=60, period="weekly"),
        DrivingChallenge(title="Route Explorer", description="Complete 20 trips", icon="🗺️", challenge_type="trips", target_value=20, xp_reward=80, period="monthly"),
        DrivingChallenge(title="Speed Demon Tamed", description="Complete a trip with score above 90 at avg speed > 40kph", icon="⚡", challenge_type="score", target_value=90, xp_reward=30, period="weekly"),
        DrivingChallenge(title="Community Helper", description="Share 5 trips to the community", icon="🌍", challenge_type="trips", target_value=5, xp_reward=25, period="alltime"),
    ]
    db.add_all(challenges)
    db.commit()
    logger.info(f"Seeded {len(challenges)} driving challenges")


# ─── Notifications ──────────────────────────────────────────────────────

@router.get("/notifications/{user_id}", response_model=NotificationListResponse)
async def get_notifications(user_id: str, limit: int = 20, db: Session = Depends(get_db)):
    notifs = db.query(Notification).filter(Notification.user_id == user_id).order_by(desc(Notification.created_at)).limit(limit).all()
    unread = db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).count()
    return NotificationListResponse(
        unread_count=unread,
        notifications=[NotificationResponse(
            id=n.id, user_id=n.user_id, type=n.type, title=n.title,
            message=n.message, extra_data=n.extra_data, is_read=n.is_read,
            created_at=str(n.created_at)
        ) for n in notifs]
    )

@router.put("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: int, db: Session = Depends(get_db)):
    notif = db.query(Notification).filter(Notification.id == notif_id).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"status": "ok"}


# ─── Risk Heatmap ──────────────────────────────────────────────────────

@router.get("/heatmap/{user_id}", response_model=HeatmapResponse)
async def get_personal_heatmap(user_id: str, db: Session = Depends(get_db)):
    # Find all vehicles for user
    from sqlalchemy import text
    v_ids = [v.id for v in db.query(Vehicle).filter(Vehicle.user_id == user_id).all()]
    if not v_ids:
        return HeatmapResponse(user_id=user_id, points=[])
    
    # Find risky telemetry points (risk > 50)
    trips = db.query(Trip).filter(Trip.vehicle_id.in_(v_ids)).all()
    trip_ids = [t.id for t in trips]
    
    points = db.query(TelemetryPoint).filter(
        TelemetryPoint.trip_id.in_(trip_ids)
    ).all()
    
    if not points:
        # Fallback to demo user if requested user has no data
        demo_trips = db.query(Trip).filter(
            Trip.vehicle_id.in_(
                db.query(Vehicle.id).filter(Vehicle.user_id == 'demo-user-001')
            )
        ).all()
        demo_trip_ids = [t.id for t in demo_trips]
        points = db.query(TelemetryPoint).filter(TelemetryPoint.trip_id.in_(demo_trip_ids)).limit(500).all()

    return HeatmapResponse(
        user_id=user_id,
        points=[
            HeatmapPoint(
                trip_id=p.trip_id,
                latitude=p.latitude,
                longitude=p.longitude,
                risk_score=p.risk_score,
                alert_level=p.alert_level or "GREEN"
            ) for p in points
        ]
    )


# ─── Trip Comparison ───────────────────────────────────────────────────

@router.get("/trips/compare", response_model=TripComparisonResponse)
async def compare_trips(trip1_id: str, trip2_id: str, db: Session = Depends(get_db)):
    t1 = db.query(Trip).filter(Trip.id == trip1_id).first()
    t2 = db.query(Trip).filter(Trip.id == trip2_id).first()
    
    if not t1 or not t2:
        raise HTTPException(404, "One or both trips not found")
    
    s1 = TripCompStats(
        distance_km=t1.total_distance_km or 0.0,
        avg_risk_score=t1.avg_risk_score or 0.0,
        red_alerts=t1.red_alert_count or 0,
        yellow_alerts=t1.yellow_alert_count or 0,
        safety_score=_compute_safety_score(t1)
    )
    s2 = TripCompStats(
        distance_km=t2.total_distance_km or 0.0,
        avg_risk_score=t2.avg_risk_score or 0.0,
        red_alerts=t2.red_alert_count or 0,
        yellow_alerts=t2.yellow_alert_count or 0,
        safety_score=_compute_safety_score(t2)
    )
    
    deltas = {
        "safety_score_diff": s2.safety_score - s1.safety_score,
        "risk_improvement_pct": ((s1.avg_risk_score - s2.avg_risk_score) / max(s1.avg_risk_score, 1)) * 100
    }
    
    return TripComparisonResponse(trip1=s1, trip2=s2, deltas=deltas)


# ─── Driving Report ────────────────────────────────────────────────────

@router.get("/report/{user_id}", response_model=DrivingReportResponse)
async def generate_driving_report(user_id: str, period: str = "monthly", db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    
    # Placeholder for a real PDF generation logic
    # In a real app, you'd use reportlab or fpdf here.
    return DrivingReportResponse(
        user_id=user_id,
        period=period,
        total_distance=user.total_distance_km or 0.0,
        avg_safety_score=user.safety_score or 100.0,
        improvement_pct=5.4, # Mock value
        report_url=f"/api/social/report/download/{user_id}"
    )
