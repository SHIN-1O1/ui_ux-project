import argparse
import sys
import getpass
from app import create_app, db
from app.models import User, Department

def setup_database():
    """Create tables and seed default reference data (departments)."""
    try:
        db.create_all()  # ensure tables exist
        print("Database tables created (if they did not exist).")

        default_depts = [
            'General', 'Cardiology', 'Orthopedics', 'ENT',
            'Dermatology', 'Neurology', 'Pediatrics'
        ]
        added = 0
        for name in default_depts:
            if not Department.query.filter_by(name=name).first():
                dept = Department(name=name)
                db.session.add(dept)
                added += 1
        if added > 0:
            db.session.commit()
            print(f"Added {added} default departments.")
        else:
            print("Default departments already present.")
    except Exception as e:
        db.session.rollback()
        print(f"Error during setup_database(): {e}")
        sys.exit(1)

def create_admin_user(interactive=True, username=None, email=None, full_name=None):
    """
    Create an admin user. If interactive=True (default) ask for details and password.
    If interactive=False, username/email/full_name must be provided and function will prompt only for password.
    """
    try:
        # Ensure tables exist so queries won't fail
        db.create_all()

        # Check existing admin(s)
        existing_admin = User.query.filter_by(role='admin').first()
        if existing_admin:
            print("An admin user already exists.")
            if not interactive:
                print("Use interactive mode to create another admin or remove existing one first.")
                return
            choice = input("Do you still want to create another admin? (y/N): ").strip().lower()
            if choice != 'y':
                print("Aborting admin creation.")
                return

        # Collect details
        if interactive:
            print("\nEnter admin details (press Enter to accept defaults):")
            username = input("Username (default: admin): ").strip() or 'admin'
            email = input("Email (default: admin@example.com): ").strip() or 'admin@example.com'
            full_name = input("Full Name (default: Admin): ").strip() or 'Admin'
        else:
            if not (username and email):
                raise ValueError("username and email are required in non-interactive mode.")

        # check uniqueness
        conflict = User.query.filter((User.username == username) | (User.email == email)).first()
        if conflict:
            print(f"User with username '{username}' or email '{email}' already exists.")
            return

        # Password (secure input)
        while True:
            try:
                password = getpass.getpass("Password (min 6 chars): ")
            except (KeyboardInterrupt, EOFError):
                print("\nPassword input cancelled.")
                return
            if not password or len(password) < 6:
                print("Password must be at least 6 characters.")
                continue
            try:
                confirm = getpass.getpass("Confirm Password: ")
            except (KeyboardInterrupt, EOFError):
                print("\nPassword confirmation cancelled.")
                return
            if password != confirm:
                print("Passwords do not match. Try again.")
                continue
            break

        # Create admin using explicit commit (avoids nested transaction issues)
        admin = User(username=username, email=email, role='admin', full_name=full_name)
        admin.set_password(password)
        try:
            db.session.add(admin)
            db.session.commit()
            print("\n✅ Admin user created successfully.")
            print(f"   Username: {username}")
            print(f"   Email: {email}")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Failed to create admin (DB error): {e}")

    except Exception as e:
        print(f"❌ create_admin_user() error: {e}")

def reset_database(require_yes=False):
    """
    Destructively drop and recreate all tables.
    require_yes True -> requires explicit '--yes' flag in CLI to proceed.
    """
    if require_yes:
        print("You requested a database reset. This will DELETE ALL DATA.")
        confirm = input("Type 'DELETE ALL DATA' to confirm: ").strip()
        if confirm != 'DELETE ALL DATA':
            print("Reset cancelled.")
            return False

    try:
        db.drop_all()
        print("All tables dropped.")
        db.create_all()
        print("Tables recreated.")
        return True
    except Exception as e:
        print(f"Error during reset_database(): {e}")
        return False

def interactive_menu():
    """Fallback simple interactive menu if the user runs script without CLI args."""
    while True:
        print("\n" + "="*60)
        print("Hospital Management System - Database Utility (interactive)")
        print("="*60)
        print("1) Initialize database (create tables & default data)")
        print("2) Create admin user")
        print("3) Reset database (DESTROY ALL DATA) - requires typing DELETE ALL DATA")
        print("4) Exit")
        choice = input("\nEnter choice (1-4): ").strip()
        if choice == '1':
            setup_database()
        elif choice == '2':
            create_admin_user(interactive=True)
        elif choice == '3':
            if reset_database(require_yes=False):
                setup_database()
                print("Database reset and initialized.")
        elif choice == '4':
            print("Goodbye.")
            break
        else:
            print("Invalid choice. Please enter 1-4.")

def parse_args():
    p = argparse.ArgumentParser(description="Database setup utility for Hospital Management System")
    group = p.add_mutually_exclusive_group()
    group.add_argument('--init', action='store_true', help='Create tables and default data, then interactively create admin')
    group.add_argument('--admin', action='store_true', help='Interactively create an admin user')
    group.add_argument('--reset', action='store_true', help='Drop all tables and recreate them (destructive)')
    p.add_argument('--yes', action='store_true', help="Confirm the destructive action (--reset). Required for --reset in non-interactive runs.")
    # optional non-interactive admin details (if you want to script admin creation)
    p.add_argument('--username', type=str, help='Admin username (non-interactive mode)')
    p.add_argument('--email', type=str, help='Admin email (non-interactive mode)')
    p.add_argument('--full-name', type=str, help='Admin full name (non-interactive mode)')
    return p.parse_args()

if __name__ == "__main__":
    app = create_app()
    args = parse_args()

    with app.app_context():
        # Always ensure tables exist before running queries (safe)
        db.create_all()

        if args.init:
            setup_database()
            create_admin_user(interactive=True)
            print("\n✨ Initialization complete.")
            sys.exit(0)

        if args.admin:
            # Non-interactive admin creation if username/email provided, else interactive prompt
            if args.username and args.email:
                create_admin_user(interactive=False, username=args.username, email=args.email, full_name=args.full_name or 'Admin')
            else:
                create_admin_user(interactive=True)
            sys.exit(0)

        if args.reset:
            # Require explicit --yes flag for scripted destructive runs.
            if args.yes:
                ok = reset_database(require_yes=False)  # will still ask "DELETE ALL DATA" inside; acceptable for extra guard
                if ok:
                    setup_database()
                    print("\nReset + initialization complete.")
                else:
                    print("Reset failed or cancelled.")
            else:
                print("--reset requires --yes flag to proceed in CLI (extra safety).")
                print("If you are running interactively, re-run without flags to use the interactive menu.")
            sys.exit(0)

        # If no args provided, fall back to simple interactive menu
        interactive_menu()

    print("\n Database setup script finished.")
