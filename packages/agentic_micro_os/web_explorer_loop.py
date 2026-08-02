from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import re
import time
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from uuid import uuid4

from .brain_access import BrainAccessRequest, BrainAccessRoad
from .browser_read import BrowserReadConnector, BrowserReadRequest
from .capabilities import CapabilityKernel
from .skill_draft import WebSkillDraft, draft_skill_from_sources
from .web_collection_store import ToolUseTrajectory, WebCollectionStore, WebSourceRecord


INVARIANTS = {
    "external_llm": False,
    "external_sllm": False,
    "local_brain_write": False,
    "production_store_mutated": False,
    "candidate_promotion": False,
    "fish_global_install": False,
    "model_weights_committed": False,
    "generated_audio_committed": False,
    "unrestricted_shell": False,
    "arbitrary_js_eval": False,
    "auto_commit": False,
    "auto_push": False,
    "proof_only": True,
    "human_approval_required": True,
}

OPEN_WEB_SUBGOAL_SEEDS = {
    "local TTS alternatives": ["https://github.com/fishaudio/fish-speech"],
    "Fish/Fish S2 install/model/runtime notes": ["https://github.com/fishaudio/fish-speech"],
    "SPLATRA/WebGL/WebGPU particle rendering": ["https://github.com/Cozystone/SPLATRA"],
    "Turbovec/quantization/compression": ["https://github.com/Cozystone/SPLATRA"],
    "MCP security/tool gateway patterns": ["https://modelcontextprotocol.io/docs/concepts/tools"],
    "Hermes-style agent architecture": ["https://github.com/anthropics/anthropic-cookbook"],
    "self-learning skill systems": ["https://modelcontextprotocol.io/docs/concepts/resources"],
    "local-first privacy agent design": ["https://www.w3.org/TR/privacy-principles/"],
}

DENY_PATH_PATTERNS = (
    "login",
    "signin",
    "sign-in",
    "signup",
    "account",
    "checkout",
    "payment",
    "billing",
    "cart",
    "upload",
    "admin",
    "auth",
    "oauth",
    "token",
    "apikey",
    "api_key",
    "secret",
)

DOWNLOAD_EXTENSIONS = (
    ".zip",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".exe",
    ".msi",
    ".dmg",
    ".pkg",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp3",
    ".wav",
    ".mp4",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
)


@dataclass(frozen=True)
class WebPageInput:
    url: str
    title: str = ""
    visible_text: str = ""
    depth: int = 0


@dataclass(frozen=True)
class WebExplorerConfig:
    goal: str
    allowed_domains: list[str]
    pages: list[WebPageInput] = field(default_factory=list)
    max_pages: int = 30
    max_depth: int = 2
    max_runtime_sec: int = 21600
    max_candidate_drafts: int = 100
    max_skill_drafts: int = 20


@dataclass(frozen=True)
class WebExplorerRunResult:
    run_id: str
    goal: str
    pages_read: int
    pages_rejected: int
    candidate_drafts_count: int
    skill_drafts_count: int
    stopped_reason: str
    sources: list[dict[str, object]]
    candidate_drafts: list[dict[str, object]]
    skill_drafts: list[dict[str, object]]
    safety_blocks: list[str]
    trajectory: dict[str, object]
    invariants: dict[str, bool]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body: str
    final_url: str | None = None


@dataclass(frozen=True)
class OpenWebPolicyDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class OpenWebExplorerConfig:
    goal: str
    seed_urls: list[str] = field(default_factory=list)
    max_pages: int = 300
    max_depth: int = 3
    max_runtime_sec: int = 21600
    max_bytes_per_page: int = 250_000
    per_domain_delay_sec: float = 3.0
    max_pages_per_domain: int = 50
    max_candidate_drafts: int = 200
    max_skill_drafts: int = 50
    max_errors: int = 12
    min_report_sources: int = 10
    fetch_live_web: bool = False


@dataclass(frozen=True)
class OpenWebExplorerRunResult:
    run_id: str
    goal: str
    pages_read: int
    pages_rejected: int
    domains_explored: list[str]
    candidate_drafts_count: int
    skill_drafts_count: int
    stopped_reason: str
    report_triggered: bool
    report_reason: str
    state_log: str
    sources: list[dict[str, object]]
    candidate_drafts: list[dict[str, object]]
    skill_drafts: list[dict[str, object]]
    safety_blocks: list[str]
    trajectory: dict[str, object]
    invariants: dict[str, bool]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PublicHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if not clean:
            return
        if self._in_title:
            self.title_parts.append(clean)
        elif self._skip_depth == 0:
            self.text_parts.append(clean)

    def result(self, base_url: str) -> tuple[str, str, list[str]]:
        title = " ".join(self.title_parts)[:180]
        text = " ".join(self.text_parts)[:5000]
        links = []
        for href in self.links:
            joined = urldefrag(urljoin(base_url, href))[0]
            if joined.startswith(("http://", "https://")):
                links.append(joined)
        return title, text, links


class OpenWebPolicy:
    def __init__(self) -> None:
        self.scheme_allowlist = {"https", "http"}

    def validate_url(self, url: str) -> OpenWebPolicyDecision:
        parsed = urlparse(url)
        if parsed.scheme not in self.scheme_allowlist:
            return OpenWebPolicyDecision(False, "unsupported or private URL scheme")
        host = (parsed.hostname or "").lower()
        if not host:
            return OpenWebPolicyDecision(False, "missing host")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return OpenWebPolicyDecision(False, "localhost or local domain rejected")
        if self._is_internal_host(host):
            return OpenWebPolicyDecision(False, "private or internal network rejected")
        combined = f"{parsed.path}?{parsed.query}".lower().rstrip("?")
        if any(pattern in combined for pattern in DENY_PATH_PATTERNS):
            return OpenWebPolicyDecision(False, "login/payment/upload/credentialed pattern rejected")
        if combined.endswith(DOWNLOAD_EXTENSIONS):
            return OpenWebPolicyDecision(False, "download-like URL rejected")
        return OpenWebPolicyDecision(True)

    @staticmethod
    def _is_internal_host(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved


class OpenWebFetcher:
    def __init__(self, user_agent: str = "ATANOR-AgenticMicroOS-Proof/1.0") -> None:
        self.user_agent = user_agent

    def fetch(self, url: str, max_bytes: int) -> FetchResult:
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"})
        with urlopen(request, timeout=12) as response:  # noqa: S310 - public bounded GET only
            content_type = str(response.headers.get("content-type", ""))
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            text = raw.decode("utf-8", errors="replace")
            return FetchResult(url, int(getattr(response, "status", 200)), content_type, text, str(response.url))


class FixtureOpenWebFetcher:
    def __init__(self, fixtures: dict[str, str]) -> None:
        self.fixtures = fixtures

    def fetch(self, url: str, max_bytes: int) -> FetchResult:
        if url not in self.fixtures:
            raise ValueError(f"fixture missing for URL: {url}")
        return FetchResult(url, 200, "text/html", self.fixtures[url][:max_bytes], url)


class OpenWebExplorerLoop:
    """Bounded public web exploration with denylist and budget guards."""

    def __init__(
        self,
        config: OpenWebExplorerConfig,
        fetcher: OpenWebFetcher | FixtureOpenWebFetcher | None = None,
        store: WebCollectionStore | None = None,
        brain_road: BrainAccessRoad | None = None,
        kernel: CapabilityKernel | None = None,
        respect_robots: bool = False,
        user_agent: str = "ATANOR-AgenticMicroOS-Proof/1.0",
    ) -> None:
        self.config = config
        self.fetcher = fetcher or OpenWebFetcher()
        self.store = store or WebCollectionStore()
        self.brain_road = brain_road or BrainAccessRoad()
        self.kernel = kernel or CapabilityKernel()
        self.policy = OpenWebPolicy()
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self.skill_drafts: list[WebSkillDraft] = []
        self.safety_blocks: list[str] = []
        self.domain_counts: dict[str, int] = {}
        self.last_domain_read_at: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.errors = 0

    def run(self) -> OpenWebExplorerRunResult:
        run_id = f"open_web_{uuid4().hex[:12]}"
        start = time.monotonic()
        queue: list[tuple[str, int]] = [(url, 0) for url in (self.config.seed_urls or default_open_web_seed_urls())]
        seen_urls: set[str] = set()
        content_hashes: set[str] = set()
        actions: list[str] = []
        outcomes: list[str] = []
        observations: list[str] = []
        read_count = 0
        rejected_count = 0
        stop_reason = "completed"
        token = self.kernel.issue("browser_read", max_calls=max(1, self.config.max_pages), reason="open web explorer proof")
        decision = self.kernel.decide("browser_read", token)
        if not decision.allowed:
            self.safety_blocks.append(decision.reason)
            stop_reason = "capability_denied"

        while queue and stop_reason == "completed":
            if read_count >= self.config.max_pages:
                stop_reason = "max_pages"
                break
            if time.monotonic() - start > self.config.max_runtime_sec:
                stop_reason = "max_runtime_sec"
                break
            url, depth = queue.pop(0)
            url = urldefrag(url)[0]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            if depth > self.config.max_depth:
                rejected_count += 1
                self.safety_blocks.append(f"depth rejected: {url}")
                continue
            policy_decision = self.policy.validate_url(url)
            if not policy_decision.allowed:
                rejected_count += 1
                self.safety_blocks.append(f"{policy_decision.reason}: {url}")
                continue
            domain = urlparse(url).hostname or ""
            if self.domain_counts.get(domain, 0) >= self.config.max_pages_per_domain:
                rejected_count += 1
                self.safety_blocks.append(f"per-domain budget reached: {domain}")
                continue
            if not self._robots_allows(url):
                rejected_count += 1
                self.safety_blocks.append(f"robots.txt disallow: {url}")
                continue
            self._respect_domain_delay(domain)
            try:
                fetched = self.fetcher.fetch(url, self.config.max_bytes_per_page)
            except Exception as exc:
                self.errors += 1
                rejected_count += 1
                self.safety_blocks.append(f"fetch failed: {url}: {type(exc).__name__}")
                if self.errors >= self.config.max_errors:
                    stop_reason = "repeated_errors"
                continue
            if "text/html" not in fetched.content_type and "application/xhtml" not in fetched.content_type:
                rejected_count += 1
                self.safety_blocks.append(f"non-html content rejected: {url}")
                continue
            parser = PublicHtmlParser()
            parser.feed(fetched.body)
            title, text, links = parser.result(fetched.final_url or url)
            source = WebSourceRecord.from_visible_text(fetched.final_url or url, title or url, text, confidence=0.64)
            content_key = hashlib.sha256(source.excerpt.lower().encode("utf-8")).hexdigest()
            if content_key in content_hashes:
                rejected_count += 1
                self.safety_blocks.append(f"duplicate content rejected: {url}")
                continue
            content_hashes.add(content_key)
            self.store.add_source(source)
            read_count += 1
            self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1
            self.last_domain_read_at[domain] = time.monotonic()
            actions.append(f"open_web_read:{url}")
            observations.append(source.excerpt)
            candidate_response = self.brain_road.request(
                BrainAccessRequest("cloud_brain", "cloud_brain_candidate_write_draft", source.summary, "proof", "public", "open web explorer candidate", run_id)
            )
            if candidate_response.allowed and len(self.store.candidate_drafts) < self.config.max_candidate_drafts:
                self.store.create_candidate_draft(source)
                outcomes.append("candidate_draft_created")
            else:
                self.safety_blocks.append(candidate_response.denied_reason or "candidate draft budget reached")
            for link in links:
                if len(queue) >= self.config.max_pages * 4:
                    break
                if self._link_relevant(link) and link not in seen_urls:
                    queue.append((link, depth + 1))

        production_response = self.brain_road.request(
            BrainAccessRequest("cloud_brain", "cloud_brain_production_write", "forbidden", "proof", "public", "open web safety check", run_id)
        )
        if production_response.allowed or production_response.mutation_performed:
            self.safety_blocks.append("ERROR: production write unexpectedly allowed")
        else:
            self.safety_blocks.append("production write blocked")
        skill = draft_skill_from_sources(self.config.goal, self.store.sources)
        if skill and len(self.skill_drafts) < self.config.max_skill_drafts:
            self.skill_drafts.append(skill)
            outcomes.append("skill_draft_created_not_promoted")
        report_triggered, report_reason = self._report_trigger(stop_reason)
        trajectory = self.store.add_trajectory(
            ToolUseTrajectory(
                trajectory_id=f"trajectory_{run_id}",
                goal=self.config.goal,
                observations=[_redact_private(note) for note in observations],
                actions=actions,
                outcomes=outcomes,
                compressed_summary=_summarize_locally(self.config.goal, observations),
                no_private_raw_data=True,
            )
        )
        return OpenWebExplorerRunResult(
            run_id=run_id,
            goal=self.config.goal,
            pages_read=read_count,
            pages_rejected=rejected_count,
            domains_explored=sorted(self.domain_counts),
            candidate_drafts_count=len(self.store.candidate_drafts),
            skill_drafts_count=len(self.skill_drafts),
            stopped_reason=stop_reason,
            report_triggered=report_triggered,
            report_reason=report_reason,
            state_log=f"read={read_count} rejected={rejected_count} drafts={len(self.store.candidate_drafts)} stop={stop_reason}",
            sources=[asdict(source) for source in self.store.sources],
            candidate_drafts=[asdict(draft) for draft in self.store.candidate_drafts],
            skill_drafts=[draft.to_dict() for draft in self.skill_drafts],
            safety_blocks=self.safety_blocks,
            trajectory=asdict(trajectory),
            invariants=INVARIANTS.copy(),
        )

    def _robots_allows(self, url: str) -> bool:
        # Only enforced for live fetches and only when explicitly enabled. Fixture
        # fetches and disabled mode keep prior behavior. Fail-open on robots fetch
        # errors but fail-closed on an explicit Disallow.
        if not self.respect_robots or isinstance(self.fetcher, FixtureOpenWebFetcher):
            return True
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if domain not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                request = Request(robots_url, headers={"User-Agent": self.user_agent})
                with urlopen(request, timeout=8) as response:  # noqa: S310 - public robots.txt only
                    raw = response.read(80_000).decode("utf-8", errors="replace")
                parser.parse(raw.splitlines())
            except Exception:
                parser = None  # robots unavailable → fail-open
            self._robots[domain] = parser
        cached = self._robots.get(domain)
        if cached is None:
            return True
        try:
            return cached.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def _respect_domain_delay(self, domain: str) -> None:
        if isinstance(self.fetcher, FixtureOpenWebFetcher):
            return
        previous = self.last_domain_read_at.get(domain)
        if previous is None:
            return
        remaining = self.config.per_domain_delay_sec - (time.monotonic() - previous)
        if remaining > 0:
            time.sleep(min(remaining, self.config.per_domain_delay_sec))

    def _link_relevant(self, link: str) -> bool:
        return self.policy.validate_url(link).allowed or any(pattern in link.lower() for pattern in DENY_PATH_PATTERNS)

    def _report_trigger(self, stop_reason: str) -> tuple[bool, str]:
        source_tags = {tag for source in self.store.sources for tag in source.tags}
        if any(block.startswith("ERROR:") for block in self.safety_blocks):
            return True, "safety issue found"
        if len(source_tags) >= 3:
            return True, "new high-value cluster found"
        if len(self.store.candidate_drafts) >= self.config.min_report_sources:
            return True, "enough candidate drafts accumulated"
        if stop_reason in {"max_pages", "max_runtime_sec", "repeated_errors"}:
            return True, "loop budget stopped"
        return False, "compact state log only"


class HermesWebExplorerLoop:
    """Bounded public web exploration proof loop.

    The loop consumes caller-provided public snapshots. It does not crawl,
    submit forms, download files, evaluate JavaScript, or write production data.
    """

    def __init__(
        self,
        config: WebExplorerConfig,
        store: WebCollectionStore | None = None,
        brain_road: BrainAccessRoad | None = None,
        kernel: CapabilityKernel | None = None,
    ) -> None:
        self.config = config
        self.store = store or WebCollectionStore()
        self.brain_road = brain_road or BrainAccessRoad()
        self.kernel = kernel or CapabilityKernel()
        self.browser = BrowserReadConnector(set(config.allowed_domains), self.kernel)
        self.skill_drafts: list[WebSkillDraft] = []
        self.safety_blocks: list[str] = []

    def run_once(self) -> WebExplorerRunResult:
        run_id = f"web_explorer_{uuid4().hex[:12]}"
        pages = self.config.pages or default_pages_for_goal(self.config.goal)
        observations: list[str] = []
        actions: list[str] = []
        outcomes: list[str] = []
        read_count = 0
        rejected_count = 0
        attempted_count = 0
        stop_reason = "completed"
        token = self.kernel.issue("browser_read", max_calls=max(1, self.config.max_pages), reason="web explorer proof read")

        for page in pages:
            if attempted_count >= self.config.max_pages:
                stop_reason = "max_pages"
                break
            attempted_count += 1
            if page.depth > self.config.max_depth:
                rejected_count += 1
                self.safety_blocks.append(f"depth rejected: {page.url}")
                continue
            actions.append(f"browser_read:{page.url}")
            result = self.browser.read(
                BrowserReadRequest(page.url, page.visible_text, {"title": page.title, "depth": page.depth}),
                token,
            )
            if not result.allowed or result.observation is None:
                rejected_count += 1
                self.safety_blocks.append(result.denied_reason or f"browser_read rejected: {page.url}")
                outcomes.append("rejected")
                continue
            source = WebSourceRecord.from_visible_text(page.url, page.title, result.observation.summary)
            self.store.add_source(source)
            observations.append(source.excerpt)
            read_count += 1
            candidate_response = self.brain_road.request(
                BrainAccessRequest(
                    target="cloud_brain",
                    operation="cloud_brain_candidate_write_draft",
                    query=source.excerpt,
                    scope="proof",
                    redaction_level="public",
                    purpose="web explorer candidate draft",
                    requested_by_loop_id=run_id,
                )
            )
            if candidate_response.allowed and len(self.store.candidate_drafts) < self.config.max_candidate_drafts:
                self.store.create_candidate_draft(source)
                outcomes.append("candidate_draft_created")
            else:
                self.safety_blocks.append(candidate_response.denied_reason or "candidate draft budget reached")

        production_response = self.brain_road.request(
            BrainAccessRequest("cloud_brain", "cloud_brain_production_write", "forbidden", "proof", "public", "safety check", run_id)
        )
        if production_response.allowed or production_response.mutation_performed:
            self.safety_blocks.append("ERROR: production write unexpectedly allowed")
        else:
            self.safety_blocks.append("production write blocked")

        skill = draft_skill_from_sources(self.config.goal, self.store.sources)
        if skill and len(self.skill_drafts) < self.config.max_skill_drafts:
            self.skill_drafts.append(skill)
            outcomes.append("skill_draft_created_not_promoted")

        if stop_reason == "completed" and len(pages) > read_count + rejected_count:
            stop_reason = "budget"
        trajectory = self.store.add_trajectory(
            ToolUseTrajectory(
                trajectory_id=f"trajectory_{run_id}",
                goal=self.config.goal,
                observations=[_redact_private(note) for note in observations],
                actions=actions,
                outcomes=outcomes,
                compressed_summary=_summarize_locally(self.config.goal, observations),
                no_private_raw_data=True,
            )
        )
        return WebExplorerRunResult(
            run_id=run_id,
            goal=self.config.goal,
            pages_read=read_count,
            pages_rejected=rejected_count,
            candidate_drafts_count=len(self.store.candidate_drafts),
            skill_drafts_count=len(self.skill_drafts),
            stopped_reason=stop_reason,
            sources=[asdict(source) for source in self.store.sources],
            candidate_drafts=[asdict(draft) for draft in self.store.candidate_drafts],
            skill_drafts=[draft.to_dict() for draft in self.skill_drafts],
            safety_blocks=self.safety_blocks,
            trajectory=asdict(trajectory),
            invariants=INVARIANTS.copy(),
        )


def default_pages_for_goal(goal: str) -> list[WebPageInput]:
    return [
        WebPageInput(
            "http://docs.local/fish2-runtime",
            "Fish 2 local runtime notes",
            f"{goal}. Fish 2 requires isolated runtime, local model path, and generated audio must stay ignored.",
        ),
        WebPageInput(
            "http://docs.local/splatra-particles",
            "SPLATRA particle rendering notes",
            "SPLATRA particle rendering uses bounded budgets, LOD, compression, and proof-only evaluator gates.",
        ),
    ]


def default_open_web_seed_urls() -> list[str]:
    urls: list[str] = []
    for seed_list in OPEN_WEB_SUBGOAL_SEEDS.values():
        for url in seed_list:
            if url not in urls:
                urls.append(url)
    return urls


def _summarize_locally(goal: str, observations: list[str]) -> str:
    joined = " ".join(observations)
    words = []
    for raw in joined.split():
        word = raw.strip(".,:;!?()[]{}").lower()
        if len(word) > 5 and word not in words:
            words.append(word)
        if len(words) >= 10:
            break
    return f"{goal}: " + ", ".join(words)


def _redact_private(text: str) -> str:
    lowered = text.lower()
    if "private" in lowered or "raw_memory" in lowered or "token" in lowered:
        return "[private-redacted]"
    return text


def build_config_from_api(payload: dict[str, Any]) -> WebExplorerConfig:
    pages = [
        WebPageInput(
            url=str(page.get("url", "")),
            title=str(page.get("title", "")),
            visible_text=str(page.get("visible_text", "")),
            depth=int(page.get("depth", 0)),
        )
        for page in payload.get("pages", [])
    ]
    allowed_domains = [str(item) for item in payload.get("allowed_domains", ["docs.local", "127.0.0.1", "localhost"])]
    return WebExplorerConfig(
        goal=str(payload.get("goal", "research local TTS alternatives and SPLATRA particle rendering")),
        allowed_domains=allowed_domains,
        pages=pages,
        max_pages=int(payload.get("max_pages", 30)),
        max_depth=int(payload.get("max_depth", 2)),
        max_runtime_sec=int(payload.get("max_runtime_sec", 21600)),
        max_candidate_drafts=int(payload.get("max_candidate_drafts", 100)),
        max_skill_drafts=int(payload.get("max_skill_drafts", 20)),
    )


def _allowed_domains_from_pages(pages: list[WebPageInput]) -> list[str]:
    domains = sorted({urlparse(page.url).hostname for page in pages if urlparse(page.url).hostname})
    return domains or ["docs.local", "127.0.0.1", "localhost"]


def run_open_web_proof(goal: str, max_runtime_sec: int = 21600, max_pages: int = 300, max_depth: int = 3) -> dict[str, object]:
    fixtures = {
        "https://example.com/fish": "<html><title>Fish S2 runtime</title><body>Fish Speech local TTS runtime requires model weights outside the repository and isolated Python. <a href='https://example.com/splatra'>SPLATRA particle rendering</a><a href='https://example.com/login'>login</a></body></html>",
        "https://example.com/splatra": "<html><title>SPLATRA WebGPU particles</title><body>SPLATRA WebGPU particle rendering uses compression, quantization, and bounded LOD budgets for browser playback.</body></html>",
    }
    config = OpenWebExplorerConfig(
        goal=goal,
        seed_urls=["https://example.com/fish"],
        max_runtime_sec=max_runtime_sec,
        max_pages=min(max_pages, 12),
        max_depth=max_depth,
        per_domain_delay_sec=0,
        max_pages_per_domain=8,
        fetch_live_web=False,
    )
    return OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run().to_dict()


def run_proof(goal: str, max_runtime_sec: int = 21600) -> dict[str, object]:
    pages = default_pages_for_goal(goal) + [
        WebPageInput("https://not-allowed.example/private", "Rejected page", "public text"),
        WebPageInput("http://docs.local/private", "Private marker", "raw_private_memory should be rejected"),
    ]
    config = WebExplorerConfig(goal, _allowed_domains_from_pages(default_pages_for_goal(goal)), pages, max_pages=30, max_runtime_sec=max_runtime_sec)
    result = HermesWebExplorerLoop(config).run_once().to_dict()
    budget_config = WebExplorerConfig(goal, _allowed_domains_from_pages(default_pages_for_goal(goal)), default_pages_for_goal(goal), max_pages=1, max_runtime_sec=max_runtime_sec)
    budget_result = HermesWebExplorerLoop(budget_config).run_once()
    result["budget_stop_demo"] = {
        "stopped_reason": budget_result.stopped_reason,
        "pages_read": budget_result.pages_read,
        "pages_rejected": budget_result.pages_rejected,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run proof-only Hermes web explorer loop.")
    parser.add_argument("--goal", default="research local TTS alternatives and SPLATRA particle rendering")
    parser.add_argument("--max-runtime-sec", type=int, default=21600)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--open-web", action="store_true", help="Run the open-web V1 proof path. Defaults to safe fixture fetcher unless --live-web is set.")
    parser.add_argument("--live-web", action="store_true", help="Use live public web GETs. Still bounded by denylist and budgets.")
    args = parser.parse_args()
    should_run_open_web = args.open_web or "open web" in args.goal.lower() or args.max_pages != 30 or args.max_depth != 2
    if should_run_open_web:
        if args.live_web:
            config = OpenWebExplorerConfig(
                goal=args.goal,
                seed_urls=default_open_web_seed_urls(),
                max_pages=args.max_pages,
                max_depth=args.max_depth,
                max_runtime_sec=args.max_runtime_sec,
                fetch_live_web=True,
            )
            payload = OpenWebExplorerLoop(config).run().to_dict()
        else:
            payload = run_open_web_proof(args.goal, args.max_runtime_sec, args.max_pages, args.max_depth)
    else:
        payload = run_proof(args.goal, args.max_runtime_sec)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
