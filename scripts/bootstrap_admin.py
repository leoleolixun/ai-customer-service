import argparse
import asyncio

from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory, engine
from app.core.security import hash_password
from app.domains.identities.repository import IdentityRepository
from scripts.password_input import read_password


async def create_admin(email: str, display_name: str, password: str) -> None:
    async with async_session_factory() as session:
        try:
            user = await IdentityRepository(session).create_platform_admin(
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise SystemExit("A staff user with this email already exists.") from None
        print(f"Created platform administrator {user.email} ({user.id}).")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first platform administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input instead of prompting.",
    )
    args = parser.parse_args()
    password = read_password(from_stdin=args.password_stdin, prompt="Initial admin password: ")
    if len(password) < 12:
        parser.error("password must contain at least 12 characters")
    asyncio.run(create_admin(args.email, args.display_name, password))


if __name__ == "__main__":
    main()
