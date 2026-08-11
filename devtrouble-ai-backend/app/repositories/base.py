"""
Repository Pattern의 공통 베이스.

Service 계층은 SQLAlchemy Session을 직접 다루지 않고
반드시 Repository를 통해서만 데이터에 접근한다.
(Service가 ORM/SQL에 의존하지 않도록 격리하는 것이 목적)
"""
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, entity_id: str) -> ModelType | None:
        return self.db.get(self.model, entity_id)

    def add(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        self.db.flush()
        return entity

    def delete(self, entity: ModelType) -> None:
        self.db.delete(entity)
        self.db.flush()
