from dataclasses import dataclass, field
from typing import List, Optional
from supabase import create_client, Client
from pathlib import Path
from threading import Lock

from ..core.config import settings

# Lazy-initialized Supabase client
_supabase_client: Optional[Client] = None
_supabase_lock = Lock()


def get_supabase() -> Client:
    """Return a singleton Supabase client. Created on first use (thread-safe)."""
    global _supabase_client
    if _supabase_client is None:
        with _supabase_lock:
            # Double-check pattern: another thread might have initialized while we waited
            if _supabase_client is None:
                url = settings.SUPABASE_URL
                key = settings.SUPABASE_KEY
                if not url or not key:
                    raise RuntimeError("Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")
                _supabase_client = create_client(url, key)
    return _supabase_client


PUBLIC_SPACES = [settings.DEFAULT_SPACE]

@dataclass
class UserData:
    """Represents the authenticated user context derived from Supabase.

    Fields:
        user_id: Supabase auth.users UUID (sub claim)
        username: Email (kept for backward compatibility with existing code that expects `username`)
        first_name / last_name: From JWT user_metadata if present
        spaces: Names of personal spaces already indexed (not authoritative; convenience only)
        organization: Single org UUID if membership exists (simplified)
    """
    user_id: str
    username: str  # email
    first_name: str = ""
    last_name: str = ""
    spaces: List[str] = field(default_factory=list)
    organization: Optional[str] = None


def get_or_create_user_from_supabase(user_id: str, email: str, user_metadata: Optional[dict] = None) -> UserData:
    """
    Get or create a user from Supabase JWT token data.
    This replaces the in-memory users_db with Supabase database.
    
    Args:
        user_id: Supabase user UUID (from JWT 'sub' claim)
        email: User's email (from JWT 'email' claim)
        user_metadata: Additional metadata from JWT (first_name, last_name, etc.)
    
    Returns:
        UserData object with user information
    """
    # Check if user profile exists in Supabase
    try:
        sb = get_supabase()
        response = sb.table("user_profiles").select("*").eq("id", user_id).execute()
        
        if response.data and len(response.data) > 0:
            # User exists, return their data
            profile = response.data[0]
            
            # Get user's spaces
            spaces_response = sb.table("spaces").select("name").eq("owner_id", user_id).execute()
            space_names = [s["name"] for s in spaces_response.data] if spaces_response.data else ["personal"]
            
            # Check if user belongs to any organization
            org_membership = sb.table("members").select("org_id").eq("user_id", user_id).execute()
            organization = org_membership.data[0]["org_id"] if org_membership.data else None
            
            return UserData(
                user_id=user_id,
                username=email,
                first_name=user_metadata.get("first_name", "") if user_metadata else "",
                last_name=user_metadata.get("last_name", "") if user_metadata else "",
                spaces=space_names,
                organization=organization,
            )
        else:
            # User doesn't exist, create profile
            print(f"Creating new user profile for {email}")
            
            # 1. Create user_profile (only with fields that exist in schema)
            sb.table("user_profiles").insert({
                "id": user_id,
                "display_name": user_metadata.get("full_name") if user_metadata else email,
            }).execute()
            
            # 2. Create default "personal" space
            sb.table("spaces").insert({
                "name": "personal",
                "owner_id": user_id,
                "is_public": False,
            }).execute()
            
            # 3. Create local upload directory
            upload_dir = Path(settings.DATA_UPLOAD) / email / "personal"
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"✅ User profile created for {email}")
            
            return UserData(
                user_id=user_id,
                username=email,
                first_name=user_metadata.get("first_name", "") if user_metadata else "",
                last_name=user_metadata.get("last_name", "") if user_metadata else "",
                spaces=["personal"],
                organization=None,
            )
    except Exception as e:
        print(f"Error getting/creating user from Supabase: {e}")
        raise ValueError(f"Failed to get or create user: {str(e)}")
    

def get_accessible_spaces(user: UserData) -> List[str]:
    """Return a list of space identifiers the user can access.

    Format matches existing frontend expectations:
        - Public spaces: settings.DEFAULT_SPACE (no slash)
        - Personal spaces: "<email>/<space_name>"
        - Org spaces: "<org_id>/<space_name>" (can later be swapped to org name)
    """
    try:
        sb = get_supabase()
        # Personal spaces owned by the user
        owned_resp = sb.table("spaces").select("name").eq("owner_id", user.user_id).execute()
        personal = [f"{user.username}/{row['name']}" for row in owned_resp.data] if owned_resp.data else []

        # Org membership -> fetch spaces for each org_id
        org_spaces: List[str] = []
        membership_resp = sb.table("members").select("org_id").eq("user_id", user.user_id).execute()
        org_ids = [m["org_id"] for m in membership_resp.data] if membership_resp.data else []
        if org_ids:
            # For simplicity assume org_ids small; fetch spaces per org
            for oid in org_ids:
                s_resp = sb.table("spaces").select("name").eq("org_id", oid).execute()
                if s_resp.data:
                    org_spaces.extend([f"{oid}/{row['name']}" for row in s_resp.data])

        return list(dict.fromkeys(PUBLIC_SPACES + personal + org_spaces))  # preserve order, de-dup
    except Exception as e:
        print(f"get_accessible_spaces error: {e}")
        return PUBLIC_SPACES.copy()


def create_user_space(user: UserData, name: str) -> str:
    """Create a new personal space for the user in Supabase and local FS.

    Safeguards against traversal and ensures directory creation under DATA_UPLOAD/<email>/<space>.
    Returns identifier '<email>/<space>'.
    """
    if any(token in name for token in ("..", "/", "\\")):
        raise ValueError("Invalid space name")
    try:
        sb = get_supabase()
        # Insert space row (id auto-generated). Avoid duplicates.
        existing = sb.table("spaces").select("name").eq("owner_id", user.user_id).eq("name", name).execute()
        if not (existing.data and len(existing.data) > 0):
            sb.table("spaces").insert({
                "name": name,
                "owner_id": user.user_id,
                "is_public": False,
            }).execute()
        # local directory
        uploads_root = Path(settings.DATA_UPLOAD) / user.username
        space_dir = uploads_root / name
        space_dir.mkdir(parents=True, exist_ok=True)
        # Update in-memory convenience list (not authoritative)
        if name not in user.spaces:
            user.spaces.append(name)
        return f"{user.username}/{name}"
    except Exception as e:
        raise ValueError(f"Failed to create space: {e}")


