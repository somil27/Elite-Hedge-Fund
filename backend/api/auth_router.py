from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any
from pydantic import BaseModel, EmailStr

from db.database import get_db
from db.indian_models import User
from core.security import verify_password, get_password_hash, create_access_token
from api.deps import get_current_user

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str = None

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None

    class Config:
        from_attributes = True

@router.post("/login", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Find user by email
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=60 * 24 * 7) # 7 days
    return {
        "access_token": create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create new user.
    """
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
        
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        name=user_in.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name
    )

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current user.
    """
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name
    )

import httpx
from fastapi.responses import RedirectResponse
from core.config import settings
import urllib.parse
import secrets

@router.get("/google/login")
async def google_login():
    """Redirect to Google OAuth consent screen."""
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={settings.google_client_id}"
        f"&redirect_uri={urllib.parse.quote(settings.google_redirect_uri)}"
        f"&scope={urllib.parse.quote(scope)}"
        f"&access_type=offline"
    )
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback, create/login user, and redirect to frontend."""
    # 1. Exchange code for access token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange token with Google")
        token_data = resp.json()
        access_token = token_data.get("access_token")
        
        # 2. Get user info
        user_info_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        user_resp = await client.get(user_info_url, headers={"Authorization": f"Bearer {access_token}"})
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        user_info = user_resp.json()
        
    email = user_info.get("email")
    name = user_info.get("name")
    
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")
        
    # 3. Find or create user
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Create new user with a random unguessable password hash
        user = User(
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            name=name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    # 4. Generate JWT token
    access_token_expires = timedelta(minutes=60 * 24 * 7) # 7 days
    jwt_token = create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    # 5. Redirect back to frontend
    redirect_url = f"{settings.frontend_url}/?token={jwt_token}"
    return RedirectResponse(redirect_url)
