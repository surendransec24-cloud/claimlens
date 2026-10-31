"""
ClaimLens Demo User Seeding Script.
Creates default accounts for each role with passwords read from environment variables.
"""
import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.database import SessionLocal, Base, engine
from backend.models.user import User
from backend.services.auth_service import hash_password
from backend.config import settings

DEMO_USERS = [
    {
        "full_name": "Alex Adjuster",
        "email": "adjuster@claimlens.internal",
        "role": "adjuster",
        "env_var": "DEMO_ADJUSTER_PASSWORD",
        "password": settings.DEMO_ADJUSTER_PASSWORD
    },
    {
        "full_name": "Sam Supervisor",
        "email": "supervisor@claimlens.internal",
        "role": "supervisor",
        "env_var": "DEMO_SUPERVISOR_PASSWORD",
        "password": settings.DEMO_SUPERVISOR_PASSWORD
    },
    {
        "full_name": "Morgan Admin",
        "email": "admin@claimlens.internal",
        "role": "admin",
        "env_var": "DEMO_ADMIN_PASSWORD",
        "password": settings.DEMO_ADMIN_PASSWORD
    }
]

def seed_users():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("=" * 60)
        print("ClaimLens Staff Account Seeder")
        print("=" * 60)
        print("Note: To customize demo passwords, configure these environment variables in your .env:")
        for u in DEMO_USERS:
            print(f"  - {u['env_var']}")
        print("-" * 60)

        for u in DEMO_USERS:
            user = db.query(User).filter(User.email == u["email"]).first()
            if not user:
                hashed = hash_password(u["password"])
                user = User(
                    full_name=u["full_name"],
                    email=u["email"],
                    password_hash=hashed,
                    role=u["role"],
                    is_active=True
                )
                db.add(user)
                print(f"[CREATED] {u['role'].upper()}: {u['email']} (Name: {u['full_name']})")
            else:
                user.password_hash = hash_password(u["password"])
                user.is_active = True
                user.failed_attempts = 0
                user.locked_until = None
                print(f"[UPDATED] {u['role'].upper()}: {u['email']} (Reset password)")

        db.commit()
        print("=" * 60)
        print("Demo accounts ready:")
        print("  1. Adjuster:   adjuster@claimlens.internal")
        print("  2. Supervisor: supervisor@claimlens.internal")
        print("  3. Admin:      admin@claimlens.internal")
        print("=" * 60)
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()

