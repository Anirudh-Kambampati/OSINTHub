"""The single place connectors are registered. Add new sources here."""

from app.connectors.authenticated import (
    BraveSearchConnector, InstagramConnector, LinkedInConnector, RedditConnector, XConnector, YouTubeConnector,
)
from app.connectors.base import Connector
from app.connectors.bluesky import BlueskyConnector
from app.connectors.devto import DevToConnector
from app.connectors.domain import CertificatesConnector, DnsConnector, RdapConnector, WaybackConnector
from app.connectors.github import GitHubConnector
from app.connectors.gitlab import GitLabConnector
from app.connectors.gravatar import GravatarConnector
from app.connectors.hackernews import HackerNewsConnector, HackerNewsSearchConnector
from app.connectors.infra import EmailIntelConnector, IpIntelConnector, SecurityTxtConnector
from app.connectors.keybase import KeybaseConnector
from app.connectors.medium import MediumConnector
from app.connectors.people import OrcidConnector, StackExchangeConnector, WikidataConnector
from app.connectors.platforms import (
    ChessComConnector, CodebergConnector, CodewarsConnector, CratesIoConnector, DockerHubConnector,
    HuggingFaceConnector, LichessConnector, MastodonConnector, NpmConnector,
)
from app.connectors.web import DocumentConnector, WebsiteConnector

CONNECTORS: dict[str, Connector] = {
    c.name: c
    for c in (
        GitHubConnector(),
        GitLabConnector(),
        HackerNewsConnector(),
        DevToConnector(),
        KeybaseConnector(),
        BlueskyConnector(),
        MediumConnector(),
        MastodonConnector(),
        CodebergConnector(),
        HuggingFaceConnector(),
        NpmConnector(),
        CratesIoConnector(),
        DockerHubConnector(),
        StackExchangeConnector(),
        CodewarsConnector(),
        ChessComConnector(),
        LichessConnector(),
        OrcidConnector(),
        WikidataConnector(),
        RedditConnector(),
        XConnector(),
        YouTubeConnector(),
        InstagramConnector(),
        LinkedInConnector(),
        GravatarConnector(),
        EmailIntelConnector(),
        HackerNewsSearchConnector(),
        BraveSearchConnector(),
        WebsiteConnector(),
        DnsConnector(),
        RdapConnector(),
        CertificatesConnector(),
        WaybackConnector(),
        SecurityTxtConnector(),
        IpIntelConnector(),
        DocumentConnector(),
    )
}


def get_connector(name: str) -> Connector:
    return CONNECTORS[name]
