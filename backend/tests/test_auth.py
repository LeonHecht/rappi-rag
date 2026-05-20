from pathlib import Path
from unittest.mock import MagicMock
import uuid

import pytest

from backend.app.core.config import settings
import backend.app.services.auth as auth


@pytest.fixture()
def auth_env(tmp_path, monkeypatch):
    """Prepare temp upload directory for tests relying on local FS side effects."""
    monkeypatch.setattr(settings, "DATA_UPLOAD", str(tmp_path))
    return tmp_path


@pytest.fixture()
def mock_supabase(monkeypatch):
    """Mock Supabase client for testing."""
    mock_client = MagicMock()
    
    # Mock table responses
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    
    # Setup default empty responses
    mock_response = MagicMock()
    mock_response.data = []
    
    mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
    mock_table.insert.return_value.execute.return_value = mock_response
    
    # Mock the get_supabase function to return our mock client
    monkeypatch.setattr(auth, "get_supabase", lambda: mock_client)
    
    return mock_client


# ============================================================================
# Tests for Supabase-based authentication helpers
# ============================================================================

def test_get_or_create_user_from_supabase_new_user(auth_env, mock_supabase):
    """Test creating a new user from Supabase JWT data."""
    user_id = str(uuid.uuid4())
    email = "test@example.com"
    user_metadata = {"first_name": "Test", "last_name": "User"}
    
    # Mock empty response (user doesn't exist)
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    
    # Mock successful insert
    mock_insert_response = MagicMock()
    mock_insert_response.data = [{"id": user_id, "display_name": "Test User"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_response
    
    # Create user
    user = auth.get_or_create_user_from_supabase(user_id, email, user_metadata)
    
    # Assertions
    assert user.username == email
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert "personal" in user.spaces
    
    # Verify Supabase calls
    assert mock_supabase.table.call_count >= 2  # user_profiles + spaces
    
    # Verify upload directory was created
    upload_dir = Path(settings.DATA_UPLOAD) / email / "personal"
    assert upload_dir.exists() and upload_dir.is_dir()


def test_get_or_create_user_from_supabase_existing_user(auth_env, mock_supabase):
    """Test retrieving an existing user from Supabase."""
    user_id = str(uuid.uuid4())
    email = "existing@example.com"
    
    # Mock existing user profile
    mock_profile_response = MagicMock()
    mock_profile_response.data = [{
        "id": user_id,
        "display_name": "Existing User"
    }]
    
    # Mock existing spaces
    mock_spaces_response = MagicMock()
    mock_spaces_response.data = [
        {"name": "personal"},
        {"name": "work"}
    ]
    
    # Mock org membership (none)
    mock_org_response = MagicMock()
    mock_org_response.data = []
    
    # Setup mock to return different responses for different calls
    call_counter = {"n": 0}
    def mock_execute(*_args, **_kwargs):
        # Sequence: profile -> spaces -> org membership
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            return mock_profile_response
        elif call_counter["n"] == 2:
            return mock_spaces_response
        else:
            return mock_org_response
    
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = mock_execute
    
    # Get user
    user = auth.get_or_create_user_from_supabase(user_id, email)
    
    # Assertions
    assert user.username == email
    assert user.spaces == ["personal", "work"]
    assert user.organization is None


def test_get_or_create_user_from_supabase_with_org(auth_env, mock_supabase):
    """Test user with organization membership."""
    user_id = str(uuid.uuid4())
    email = "org_user@example.com"
    org_id = str(uuid.uuid4())
    
    # Mock existing user profile
    mock_profile_response = MagicMock()
    mock_profile_response.data = [{
        "id": user_id,
        "display_name": "Org User"
    }]
    
    # Mock spaces
    mock_spaces_response = MagicMock()
    mock_spaces_response.data = [{"name": "personal"}]
    
    # Mock org membership
    mock_org_response = MagicMock()
    mock_org_response.data = [{"org_id": org_id}]
    
    call_count = 0
    def mock_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_profile_response
        elif call_count == 2:
            return mock_spaces_response
        else:
            return mock_org_response
    
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = mock_execute
    
    # Get user
    user = auth.get_or_create_user_from_supabase(user_id, email)
    
    # Assertions
    assert user.organization == org_id


def test_get_accessible_spaces(auth_env):
    """Test getting accessible spaces for a user."""
    # Build user and mock Supabase responses
    user = auth.UserData(user_id=str(uuid.uuid4()), username="alice@example.com", spaces=["personal"]) 
    mock_client = MagicMock()
    # Owned spaces
    owned_resp = MagicMock(); owned_resp.data = [{"name": "personal"}]
    # Membership in one org, id "demo_org"
    members_resp = MagicMock(); members_resp.data = [{"org_id": "demo_org"}]
    # Org spaces for that org
    org_spaces_resp = MagicMock(); org_spaces_resp.data = [{"name": "shared"}]

    # Create stable table mocks so repeated calls return the same object/state
    spaces_table = MagicMock()
    members_table = MagicMock()

    # For spaces: first execute -> owned, second execute -> org spaces
    spaces_table.select.return_value.eq.return_value.execute.side_effect = [owned_resp, org_spaces_resp]
    # For members: single execute returns membership
    members_table.select.return_value.eq.return_value.execute.return_value = members_resp

    def table_side_effect(name):
        if name == "spaces":
            return spaces_table
        if name == "members":
            return members_table
        t = MagicMock()
        r = MagicMock(); r.data = []
        t.select.return_value.eq.return_value.execute.return_value = r
        return t

    mock_client.table.side_effect = table_side_effect
    # Patch get_supabase to return our fake client
    from backend.app.services import auth as auth_mod
    old_get = auth_mod.get_supabase
    auth_mod.get_supabase = lambda: mock_client
    try:
        spaces = auth.get_accessible_spaces(user)
    finally:
        auth_mod.get_supabase = old_get

    assert "alice@example.com/personal" in spaces
    assert "demo_org/shared" in spaces
    assert settings.DEFAULT_SPACE in spaces


def test_create_user_space_valid(auth_env, monkeypatch):
    """Test creating a valid user space."""
    user = auth.UserData(user_id=str(uuid.uuid4()), username="alice", spaces=["personal"])
    # No-op Supabase insert (we're testing FS side effect only)
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = []
    mock_table.insert.return_value.execute.return_value.data = [{"name": "newspace"}]
    monkeypatch.setattr(auth, "get_supabase", lambda: mock_client)

    space_key = auth.create_user_space(user, "newspace")
    expected = Path(settings.DATA_UPLOAD) / "alice" / "newspace"
    assert expected.exists() and expected.is_dir()
    assert space_key == "alice/newspace"


def test_create_user_space_invalid(auth_env):
    """Test that invalid space names are rejected."""
    user = auth.UserData(user_id=str(uuid.uuid4()), username="alice")
    with pytest.raises(ValueError, match="Invalid space name"):
        auth.create_user_space(user, "../bad")
    with pytest.raises(ValueError, match="Invalid space name"):
        auth.create_user_space(user, "bad/name")
    with pytest.raises(ValueError, match="Invalid space name"):
        auth.create_user_space(user, "bad\\name")
    
