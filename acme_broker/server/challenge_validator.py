import abc
import contextlib
import ipaddress
import itertools
import logging
import typing
import dns.asyncresolver

from acme_broker.models import ChallengeType

logger = logging.getLogger(__name__)


class CouldNotValidateChallenge(Exception):
    pass


class ChallengeValidator(abc.ABC):
    SUPPORTED_CHALLENGES: typing.Iterable[ChallengeType]

    @abc.abstractmethod
    async def validate_challenge(self, challenge, **kwargs):
        """Validate the given challenge.

        This method should attempt to validate the given challenge and
        raise a CouldNotValidateChallenge exception if it did not succeed.

        :param challenge: The challenge to be validated
        :type challenge: acme_broker.models.Challenge
        """
        pass


class RequestIPDNSChallengeValidator(ChallengeValidator):
    """Validator for the Request IP DNS challenge.

    This validator does not actually validate a challenge defined by
    the ACME protocol. Instead, it checks whether the corresponding
    authorization's identifier resolves to the IP that the validation
    request is being made from by checking for a A/AAAA record.
    """

    SUPPORTED_CHALLENGES = frozenset([ChallengeType.DNS_01, ChallengeType.HTTP_01])

    async def _query_record(self, name, type_):
        resolved_ips = []

        with contextlib.suppress(
            dns.asyncresolver.NXDOMAIN, dns.asyncresolver.NoAnswer
        ):
            resp = await dns.asyncresolver.resolve(name, type_)
            resolved_ips.extend(
                [
                    ipaddress.ip_address(record.address)
                    for record in resp.rrset.items.keys()
                ]
            )

        return resolved_ips

    async def query_records(self, name):
        resolved_ips = [
            await self._query_record(name, type_) for type_ in ("A", "AAAA")
        ]

        return set(itertools.chain.from_iterable(resolved_ips))

    async def validate_challenge(self, challenge, request=None):
        identifier = challenge.authorization.identifier.value
        logger.debug(
            "Validating challenge %s for identifier %s",
            challenge.challenge_id,
            identifier,
        )

        resolved_ips = await self.query_records(identifier)

        if request["actual_ip"] not in resolved_ips:
            raise CouldNotValidateChallenge


class DummyValidator(ChallengeValidator):
    """Does not do any validation and reports every challenge as valid."""

    SUPPORTED_CHALLENGES = frozenset([ChallengeType.DNS_01, ChallengeType.HTTP_01])

    async def validate_challenge(self, challenge, **kwargs):
        pass