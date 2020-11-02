import enum
import uuid

from sqlalchemy import Column, Enum, DateTime, ForeignKey, Integer, Boolean, delete
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from . import ChallengeStatus, Challenge
from .base import Base, Serializer
from ..util import url_for


class AuthorizationStatus(str, enum.Enum):
    # subclassing str simplifies json serialization using json.dumps
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    DEACTIVATED = "deactivated"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Authorization(Base, Serializer):
    __tablename__ = "authorizations"
    __serialize__ = ["status", "expires", "wildcard"]

    authorization_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    identifier_id = Column(
        Integer, ForeignKey("identifiers.identifier_id"), nullable=False
    )
    identifier = relationship(
        "Identifier", back_populates="authorizations", lazy="joined"
    )
    status = Column("status", Enum(AuthorizationStatus), nullable=False)
    expires = Column(DateTime)
    wildcard = Column(Boolean, nullable=False)
    challenges = relationship(
        "Challenge",
        cascade="all, delete",
        back_populates="authorization",
        lazy="joined",
    )

    def url(self, request):
        return url_for(request, "authz", id=str(self.authorization_id))

    async def finalize(self, session):
        # check whether at least one challenge is valid
        for challenge in self.challenges:
            if challenge.status == ChallengeStatus.VALID:
                self.status = AuthorizationStatus.VALID
                break

        # delete all other challenges
        if self.status == AuthorizationStatus.VALID:
            statement = delete(Challenge).filter(
                (Challenge.authorization_id == self.authorization_id)
                & (Challenge.status != ChallengeStatus.VALID)
            )
            await session.execute(statement)

        return self.status

    def serialize(self, request=None):
        d = Serializer.serialize(self)
        d["challenges"] = Serializer.serialize_list(self.challenges, request=request)
        d["identifier"] = self.identifier.serialize()
        return d

    @classmethod
    def create_all(cls, identifier):
        return [
            cls(
                status=AuthorizationStatus.PENDING,
                wildcard=identifier.value.startswith("*"),
            )
        ]
