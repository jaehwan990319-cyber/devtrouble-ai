from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def exists_by_email(self, email: str) -> bool:
        return self.get_by_email(email) is not None
