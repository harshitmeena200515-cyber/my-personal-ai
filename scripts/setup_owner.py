"""
Interactive Primary Owner Provisioning CLI for MY PERSONAL AI.

Enables secure local provisioning of the primary system OWNER account without
hardcoded credentials, environment variable exposure, or log leakage.
Uses getpass for terminal input masking and Argon2id for password hashing.
"""

import getpass
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import create_user, validate_password_strength, validate_username
from data.db import db


def setup_owner():
    """Interactively provision the primary OWNER account."""
    print("=" * 60)
    print("   MY PERSONAL AI — Primary Owner Setup (Phase 4A)")
    print("=" * 60)

    db.init_db()

    # Check if an OWNER account already exists
    existing_owner = db.fetch_one("SELECT username FROM users WHERE role = 'OWNER';")
    if existing_owner:
        print(f"\n⚠️  An OWNER account already exists: '{existing_owner['username']}'")
        choice = input("Do you want to create an additional user with OWNER privileges? (y/N): ").strip().lower()
        if choice != "y":
            print("Setup aborted. No changes made.")
            return

    # Prompt for username
    while True:
        username = input("\nEnter Owner Username (e.g., harshit): ").strip()
        is_valid, err = validate_username(username)
        if not is_valid:
            print(f"❌ {err}")
            continue

        # Check existing username
        existing = db.fetch_one("SELECT id FROM users WHERE username = ? COLLATE NOCASE;", (username,))
        if existing:
            print(f"❌ Username '{username}' already exists. Choose a different username.")
            continue
        break

    # Prompt for password securely with getpass
    while True:
        password = getpass.getpass("Enter Owner Password (min 8 chars, letters + numbers/special): ")
        is_valid, err = validate_password_strength(password)
        if not is_valid:
            print(f"❌ {err}")
            continue

        confirm = getpass.getpass("Confirm Owner Password: ")
        if password != confirm:
            print("❌ Passwords do not match. Try again.")
            continue
        break

    try:
        user = create_user(username=username, password=password, role="OWNER")
        print("\n" + "=" * 60)
        print("✅ SUCCESS: Primary OWNER account created successfully!")
        print(f"   Username: {user['username']}")
        print(f"   Role:     {user['role']}")
        print(f"   User ID:  {user['id']}")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error creating owner account: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    setup_owner()
