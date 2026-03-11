"""
Leomail v4 - Proxy Manager
1 proxy = 1 account (hard binding). Auto-reassign on proxy death.
Per-provider usage: success (use_*) counts toward limit.
Fail handling: soft fail = cooldown only (no burn), hard fail = fail_* +1 (permanent burn).
"""
import random
import asyncio
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger
from ..models import Proxy, ProxyStatus, Account


class ProxyManager:
    """Manage proxy pool with rotation and account binding."""

    def __init__(self, db: Session):
        self.db = db
        self._rotation_index = 0

    def import_proxies(self, lines: list[str], proxy_type: str = "residential", geo: str = None) -> dict:
        """
        Parse and import proxy lines.
        Supported formats:
          host:port
          host:port:user:pass
          user:pass@host:port
          protocol://user:pass@host:port
        """
        added = 0
        skipped = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parsed = self._parse_proxy_line(line)
            if not parsed:
                skipped += 1
                continue

            # Check duplicate - include username because rotating proxies
            # use same host:port but different sessions via username
            dup_query = self.db.query(Proxy).filter(
                Proxy.host == parsed["host"],
                Proxy.port == parsed["port"],
            )
            if parsed.get("username"):
                dup_query = dup_query.filter(Proxy.username == parsed["username"])
            else:
                dup_query = dup_query.filter(Proxy.username == None)  # noqa: E711
            existing = dup_query.first()
            if existing:
                skipped += 1
                continue

            proxy = Proxy(
                host=parsed["host"],
                port=parsed["port"],
                username=parsed.get("username"),
                password=parsed.get("password"),
                protocol=parsed.get("protocol", "http"),
                proxy_type=proxy_type,
                geo=geo,
                status=ProxyStatus.ACTIVE,
            )
            self.db.add(proxy)
            added += 1

        self.db.commit()
        logger.info(f"Imported {added} proxies, skipped {skipped}")
        return {"added": added, "skipped": skipped}

    # ── Provider-local cooldown helpers ──

    @staticmethod
    def _get_provider_cooldowns(proxy) -> dict:
        """Parse cooldown_providers JSON → dict of provider→datetime."""
        raw = getattr(proxy, 'cooldown_providers', None)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return {k: datetime.fromisoformat(v) for k, v in data.items() if v}
        except (json.JSONDecodeError, ValueError):
            return {}

    @staticmethod
    def _is_provider_cooled_down(proxy, provider: str) -> bool:
        """Check if a specific provider is still in cooldown for this proxy."""
        if not provider:
            return False
        raw = getattr(proxy, 'cooldown_providers', None)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            ts = data.get(provider.lower())
            if ts:
                return datetime.fromisoformat(ts) > datetime.utcnow()
        except (json.JSONDecodeError, ValueError):
            pass
        return False

    def _set_provider_cooldown(self, proxy, provider: str, until: datetime):
        """Set cooldown for a specific provider. Updates JSON blob + derived global."""
        cooldowns = self._get_provider_cooldowns(proxy)
        cooldowns[provider.lower()] = until.isoformat()
        proxy.cooldown_providers = json.dumps({k: v.isoformat() if isinstance(v, datetime) else v for k, v in cooldowns.items()})
        # Derive global cooldown_until = max of all active provider cooldowns (backward compat)
        now = datetime.utcnow()
        active_cooldowns = [dt for dt in cooldowns.values() if isinstance(dt, datetime) and dt > now]
        proxy.cooldown_until = max(active_cooldowns) if active_cooldowns else None

    @staticmethod
    def _filter_by_provider_cooldown(candidates: list, provider: str) -> list:
        """Post-filter: remove proxies that are in cooldown for a specific provider."""
        if not provider:
            return candidates
        now = datetime.utcnow()
        result = []
        for p in candidates:
            raw = getattr(p, 'cooldown_providers', None)
            if not raw:
                result.append(p)
                continue
            try:
                data = json.loads(raw)
                ts = data.get(provider.lower())
                if ts and datetime.fromisoformat(ts) > now:
                    continue  # skip — this proxy is cooled down for this provider
            except (json.JSONDecodeError, ValueError):
                pass
            result.append(p)
        return result

    def _parse_proxy_line(self, line: str) -> dict | None:
        """Parse a single proxy line into components."""
        result = {"protocol": "http"}

        # Strip protocol prefix
        for proto in ["socks5://", "socks4://", "http://", "https://"]:
            if line.startswith(proto):
                result["protocol"] = proto.replace("://", "")
                line = line[len(proto):]
                break

        # user:pass@host:port
        if "@" in line:
            auth, server = line.rsplit("@", 1)
            parts = auth.split(":", 1)
            result["username"] = parts[0]
            result["password"] = parts[1] if len(parts) > 1 else ""
            server_parts = server.split(":")
            result["host"] = server_parts[0]
            result["port"] = int(server_parts[1]) if len(server_parts) > 1 else 80
        else:
            # host:port or host:port:user:pass
            parts = line.split(":")
            if len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
            elif len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["username"] = parts[2]
                result["password"] = parts[3]
            else:
                return None

        return result

    def get_working_proxy(self, exclude_ids: list[int] = None, provider: str = None) -> Proxy | None:
        """
        Get next working proxy with round-robin rotation.
        Excludes specified IDs. Optional provider for cooldown filtering.
        """
        query = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE)

        if exclude_ids:
            query = query.filter(~Proxy.id.in_(exclude_ids))

        proxies = query.order_by(Proxy.id).all()

        # Provider-local cooldown post-filter
        if provider:
            proxies = self._filter_by_provider_cooldown(proxies, provider)

        if not proxies:
            return None

        # Round-robin rotation
        proxy = proxies[self._rotation_index % len(proxies)]
        self._rotation_index += 1

        return proxy

    # Provider-specific limits
    GMAIL_LIMIT = 1   # Gmail: 1 use only, first error = done
    YA_LIMIT = 3      # Yahoo+AOL combined limit
    OH_LIMIT = 3      # Outlook+Hotmail combined limit
    PT_LIMIT = 3      # ProtonMail limit
    WD_LIMIT = 3      # Web.de limit (per-proxy tracking needs migration)

    def get_unbound_proxy(self, provider: str = None) -> Proxy | None:
        """Get an active proxy NOT bound to any account.
        Filters by per-provider-GROUP usage limit.
        Groups: Gmail=G (limit 1, mobile proxy), Yahoo+AOL=YA (limit 3), Outlook+Hotmail=OH (limit 3).
        Marks fully exhausted proxies as EXHAUSTED.
        NO FALLBACK: returns None if no matching proxy found.
        """
        query = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.bound_account_id == None,  # noqa: E711
        )

        # Gmail: FORCE mobile proxy type (IP-based trust)
        if provider and provider.lower() == 'gmail':
            query = query.filter(Proxy.proxy_type == 'mobile')

        if provider:
            group_filter = self._provider_group_filter(provider)
            if group_filter is not None:
                query = query.filter(group_filter)
        proxies = query.all()

        # Provider-local cooldown post-filter
        proxies = self._filter_by_provider_cooldown(proxies, provider)

        # Auto-mark exhausted proxies (all groups at limit)
        for p in list(proxies):
            if self._is_exhausted(p):
                proxies.remove(p)
                p.status = ProxyStatus.EXHAUSTED
                logger.info(f"Proxy {p.host}:{p.port} exhausted (all provider groups at limit) -> EXHAUSTED")
                self.db.commit()

        if proxies:
            return random.choice(proxies)
        return None  # NO FALLBACK

    def get_proxy_pool(self, count: int, provider: str = None) -> list[Proxy]:
        """Get N unique proxies for batch operation.
        Filters by per-provider usage limit.
        Gmail: mobile proxy type forced.
        NO FALLBACK: returns empty list if no matching proxies.
        """
        query = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
        )

        # Gmail: FORCE mobile proxy type (IP-based trust)
        if provider and provider.lower() == 'gmail':
            query = query.filter(Proxy.proxy_type == 'mobile')

        if provider:
            group_filter = self._provider_group_filter(provider)
            if group_filter is not None:
                query = query.filter(group_filter)

        proxies = query.all()

        # Provider-local cooldown post-filter
        proxies = self._filter_by_provider_cooldown(proxies, provider)

        # ── ASN-based filtering: skip datacenter proxies for strict services ──
        if provider and provider.lower() in ('yahoo', 'aol', 'gmail', 'outlook', 'hotmail'):
            try:
                from .asn_checker import is_suitable_for
                before = len(proxies)
                proxies = [p for p in proxies if is_suitable_for(p.host, provider.lower(), db_proxy=p)]
                skipped = before - len(proxies)
                if skipped > 0:
                    logger.info(f"[ProxyPool] ASN filter: skipped {skipped}/{before} unsuitable proxies for {provider}")
                # Persist any newly-classified ASN types to DB
                self.db.commit()
            except Exception as e:
                logger.debug(f"[ProxyPool] ASN check skipped: {e}")

        # Gmail: prioritize mobile proxies (ONLY Gmail needs mobile)
        if provider and provider.lower() == 'gmail':
            def proxy_priority(p):
                pt = (p.proxy_type or '').lower()
                return 0 if pt == 'mobile' else 1
            proxies.sort(key=proxy_priority)
            mobile_count = sum(1 for p in proxies if (p.proxy_type or '').lower() == 'mobile')
            logger.info(f"[ProxyPool] {provider}: {len(proxies)} total proxies ({mobile_count} mobile, {len(proxies) - mobile_count} residential)")
        else:
            # All other providers: sort by usage (least-used first)
            def _pool_usage_key(p):
                total = sum(getattr(p, f, 0) or 0 for f in (
                    'use_yahoo', 'use_aol', 'use_gmail', 'use_outlook',
                    'use_hotmail', 'use_protonmail', 'use_webde'))
                return (total, random.random())
            proxies.sort(key=_pool_usage_key)
            if provider:
                logger.info(f"[ProxyPool] {provider}: {len(proxies)} proxies (sorted least-used first)")

        if len(proxies) <= count:
            return proxies

        return random.sample(proxies, count)

    @staticmethod
    def _provider_usage_col(provider: str):
        """Get the SQLAlchemy column for per-provider usage counter."""
        mapping = {
            'gmail': Proxy.use_gmail,
            'yahoo': Proxy.use_yahoo,
            'aol': Proxy.use_aol,
            'outlook': Proxy.use_outlook,
            'hotmail': Proxy.use_hotmail,
            'protonmail': Proxy.use_protonmail,
            'webde': Proxy.use_webde,
        }
        return mapping.get(provider.lower())

    @staticmethod
    def _provider_group_filter(provider: str):
        """Get SQLAlchemy filter for provider GROUP limit.
        Groups: Yahoo+AOL (YA, limit 3), Outlook+Hotmail (OH, limit 3), Gmail (G, limit 1),
        ProtonMail (PT, limit 3).
        Counts BOTH successes (use_*) and failures (fail_*) toward the limit.
        Uses coalesce() for NULL safety on fail_* columns.
        """
        _c = func.coalesce  # shorthand
        provider = provider.lower()
        if provider in ('yahoo', 'aol'):
            return (_c(Proxy.use_yahoo, 0) + _c(Proxy.use_aol, 0) + _c(Proxy.fail_yahoo, 0) + _c(Proxy.fail_aol, 0)) < ProxyManager.YA_LIMIT
        elif provider in ('outlook', 'hotmail'):
            return (_c(Proxy.use_outlook, 0) + _c(Proxy.use_hotmail, 0) + _c(Proxy.fail_outlook, 0) + _c(Proxy.fail_hotmail, 0)) < ProxyManager.OH_LIMIT
        elif provider == 'gmail':
            return (_c(Proxy.use_gmail, 0) + _c(Proxy.fail_gmail, 0)) < ProxyManager.GMAIL_LIMIT
        elif provider == 'protonmail':
            return (_c(Proxy.use_protonmail, 0) + _c(Proxy.fail_protonmail, 0)) < ProxyManager.PT_LIMIT
        elif provider == 'webde':
            return (_c(Proxy.use_webde, 0) + _c(Proxy.fail_webde, 0)) < ProxyManager.WD_LIMIT
        return None

    @staticmethod
    def _is_exhausted(proxy: Proxy) -> bool:
        """Check if ALL provider groups are at their limit.
        Groups: Gmail (1), Yahoo+AOL (3), Outlook+Hotmail (3), ProtonMail (3).
        Counts BOTH successes and failures toward the limit.
        Returns True only if ALL groups are exhausted.
        """
        g_exhausted = ((proxy.use_gmail or 0) + (proxy.fail_gmail or 0)) >= ProxyManager.GMAIL_LIMIT
        ya_exhausted = ((proxy.use_yahoo or 0) + (proxy.use_aol or 0) + (proxy.fail_yahoo or 0) + (proxy.fail_aol or 0)) >= ProxyManager.YA_LIMIT
        oh_exhausted = ((proxy.use_outlook or 0) + (proxy.use_hotmail or 0) + (proxy.fail_outlook or 0) + (proxy.fail_hotmail or 0)) >= ProxyManager.OH_LIMIT
        pt_exhausted = ((proxy.use_protonmail or 0) + (proxy.fail_protonmail or 0)) >= ProxyManager.PT_LIMIT
        wd_exhausted = ((proxy.use_webde or 0) + (proxy.fail_webde or 0)) >= ProxyManager.WD_LIMIT
        return g_exhausted and ya_exhausted and oh_exhausted and pt_exhausted and wd_exhausted

    def increment_provider_usage(self, proxy: Proxy, provider: str):
        """Increment the per-provider SUCCESS counter and total use_count.
        Called ONLY after successful registration."""
        attr = f"use_{provider.lower()}"
        if hasattr(proxy, attr):
            setattr(proxy, attr, (getattr(proxy, attr) or 0) + 1)
        proxy.use_count = (proxy.use_count or 0) + 1
        proxy.total_births = (proxy.total_births or 0) + 1
        proxy.last_used_at = datetime.utcnow()
        self.db.commit()

    def increment_provider_fail(self, proxy: Proxy, provider: str, hard: bool = False):
        """Record a provider-specific failure with soft/hard classification.

        hard=False (soft fail): transient signal (e500, datacenter, 'something went wrong').
            Sets cooldown_until = now + 10 min. Does NOT burn permanent fail_* counter.
        hard=True (hard fail): strong provider rejection (blocked, e302, banned).
            Increments fail_* counter (permanent burn) + sets cooldown_until = now + 30 min.

        total_fails is always incremented (lifetime global metric).
        """
        now = datetime.utcnow()
        if hard:
            attr = f"fail_{provider.lower()}"
            if hasattr(proxy, attr):
                setattr(proxy, attr, (getattr(proxy, attr) or 0) + 1)
            duration = timedelta(minutes=30)
            logger.info(f"[Proxy] HARD fail {proxy.host}:{proxy.port} for {provider} — fail_* +1, cooldown 30m")
        else:
            duration = timedelta(minutes=10)
            logger.info(f"[Proxy] Soft fail {proxy.host}:{proxy.port} for {provider} — cooldown 10m (no burn)")
        # Provider-local cooldown (only blocks this provider, not others)
        self._set_provider_cooldown(proxy, provider, now + duration)
        proxy.total_fails = (proxy.total_fails or 0) + 1
        proxy.last_used_at = now
        self.db.commit()

    def bind_proxy_to_account(self, proxy: Proxy, account: Account):
        """Hard-bind a proxy to an account (1:1). Sets proxy status to BOUND."""
        proxy.bound_account_id = account.id
        proxy.status = ProxyStatus.BOUND
        account.proxy_id = proxy.id
        account.birth_ip = f"{proxy.host}:{proxy.port}"
        self.db.commit()
        logger.info(f"Proxy {proxy.host}:{proxy.port} BOUND to {account.email}")

    def get_verified_unbound_proxy(self, proxy_type: str = None, protocol: str = None) -> Proxy | None:
        """
        Get a free active proxy matching type/protocol.
        Verifies it's alive with a quick check before returning.
        Returns None if no working proxy found.
        """
        query = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.bound_account_id == None,  # noqa: E711
        )
        if proxy_type:
            query = query.filter(Proxy.proxy_type == proxy_type)
        if protocol:
            query = query.filter(Proxy.protocol == protocol)

        candidates = query.all()
        # Provider-local cooldown post-filter (provider from caller context if available)
        candidates = self._filter_by_provider_cooldown(candidates, getattr(self, '_current_provider', None))
        if not candidates:
            # Fallback: any active unbound proxy (still respects provider cooldown)
            fallback = self.db.query(Proxy).filter(
                Proxy.status == ProxyStatus.ACTIVE,
                Proxy.bound_account_id == None,  # noqa: E711
            ).all()
            candidates = self._filter_by_provider_cooldown(fallback, getattr(self, '_current_provider', None))

        if not candidates:
            return None

        # Sort by total usage (least-used first) so fresh proxies are preferred
        def _usage_key(p):
            total = sum(getattr(p, f, 0) or 0 for f in (
                'use_yahoo', 'use_aol', 'use_gmail', 'use_outlook',
                'use_hotmail', 'use_protonmail', 'use_webde'))
            return (total, random.random())
        candidates.sort(key=_usage_key)

        # Quick-check: try each until one works
        import asyncio
        from .proxy_monitor import check_single_proxy

        for proxy in candidates:
            try:
                result = asyncio.get_event_loop().run_until_complete(check_single_proxy(proxy))
                if result.get("alive"):
                    proxy.fail_count = 0
                    proxy.response_time_ms = result.get("response_time_ms")
                    if result.get("external_ip") and result["external_ip"] != "unknown":
                        proxy.external_ip = result["external_ip"]
                    self.db.commit()
                    return proxy
                else:
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    if proxy.fail_count >= 3:
                        proxy.status = ProxyStatus.DEAD
                        logger.warning(f"Proxy verified DEAD: {proxy.host}:{proxy.port}")
                    self.db.commit()
            except Exception as e:
                logger.debug(f"Proxy verify error {proxy.host}:{proxy.port}: {e}")
                continue

        return None

    async def get_verified_unbound_proxy_async(self, proxy_type: str = None, protocol: str = None, exclude_ids: set = None, provider: str = None) -> Proxy | None:
        """Async version of get_verified_unbound_proxy.
        exclude_ids: set of proxy IDs to skip (blacklisted/burned).
        provider: e.g. 'yahoo' - excludes proxies that hit per-provider usage limit.
        """
        query = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.bound_account_id == None,  # noqa: E711
        )
        if proxy_type:
            query = query.filter(Proxy.proxy_type == proxy_type)
        if protocol:
            query = query.filter(Proxy.protocol == protocol)
        if exclude_ids:
            query = query.filter(~Proxy.id.in_(exclude_ids))
        if provider:
            group_filter = self._provider_group_filter(provider)
            if group_filter is not None:
                query = query.filter(group_filter)

        candidates = query.all()

        # Provider-local cooldown post-filter
        candidates = self._filter_by_provider_cooldown(candidates, provider)

        # ── ASN-based filtering: skip datacenter proxies for strict services ──
        if provider and provider.lower() in ('yahoo', 'aol', 'gmail', 'outlook', 'hotmail'):
            try:
                from .asn_checker import is_suitable_for
                before = len(candidates)
                candidates = [p for p in candidates if is_suitable_for(p.host, provider.lower(), db_proxy=p)]
                skipped = before - len(candidates)
                if skipped > 0:
                    logger.info(f"[ProxyManager] ASN filter: skipped {skipped}/{before} datacenter proxies for {provider}")
                # Persist any newly-classified ASN types to DB
                self.db.commit()
            except Exception as e:
                logger.debug(f"[ProxyManager] ASN check skipped: {e}")

        # If no non-blacklisted proxies, try ANY unbound active proxy
        # but ONLY if there's no blacklist (first run) - never ignore blacklist
        # IMPORTANT: still apply ASN filter to fallback candidates!
        if not candidates and not exclude_ids:
            fallback = self.db.query(Proxy).filter(
                Proxy.status == ProxyStatus.ACTIVE,
                Proxy.bound_account_id == None,  # noqa: E711
            ).all()
            fallback = self._filter_by_provider_cooldown(fallback, provider)
            if provider and provider.lower() in ('yahoo', 'aol', 'gmail', 'outlook', 'hotmail'):
                try:
                    from .asn_checker import is_suitable_for
                    fallback = [p for p in fallback if is_suitable_for(p.host, provider.lower(), db_proxy=p)]
                    self.db.commit()
                except Exception:
                    pass
            candidates = fallback

        if not candidates:
            if exclude_ids:
                logger.warning(f"[ProxyManager] All proxies blacklisted ({len(exclude_ids)} blocked), none left")
            return None

        # Sort by total usage (least-used first) so fresh proxies are preferred
        def _usage_key(p):
            total = sum(getattr(p, f, 0) or 0 for f in (
                'use_yahoo', 'use_aol', 'use_gmail', 'use_outlook',
                'use_hotmail', 'use_protonmail', 'use_webde'))
            return (total, random.random())
        candidates.sort(key=_usage_key)

        from .proxy_monitor import check_single_proxy

        for proxy in candidates:
            try:
                result = await check_single_proxy(proxy)
                if result.get("alive"):
                    proxy.fail_count = 0
                    proxy.response_time_ms = result.get("response_time_ms")
                    if result.get("external_ip") and result["external_ip"] != "unknown":
                        proxy.external_ip = result["external_ip"]
                    self.db.commit()
                    return proxy
                else:
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    if proxy.fail_count >= 3:
                        proxy.status = ProxyStatus.DEAD
                        logger.warning(f"Proxy verified DEAD: {proxy.host}:{proxy.port}")
                    self.db.commit()
            except Exception as e:
                logger.debug(f"Proxy verify error {proxy.host}:{proxy.port}: {e}")
                continue

        return None

    def replace_dead_proxy_same_type(self, account: Account, dead_proxy: Proxy) -> Proxy | None:
        """
        Replace dead proxy with same type (mobile->mobile, socks->socks).
        Unbinds old, binds new, returns new proxy or None.
        """
        # Mark old as dead, unbind
        dead_proxy.status = ProxyStatus.DEAD
        dead_proxy.bound_account_id = None

        # Find replacement with same type
        replacement = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.bound_account_id == None,  # noqa: E711
            Proxy.proxy_type == dead_proxy.proxy_type,
        ).first()

        if not replacement:
            # Last resort: any active unbound
            replacement = self.db.query(Proxy).filter(
                Proxy.status == ProxyStatus.ACTIVE,
                Proxy.bound_account_id == None,  # noqa: E711
            ).first()

        if replacement:
            self.bind_proxy_to_account(replacement, account)
            logger.info(f"Replaced proxy for {account.email}: "
                        f"{dead_proxy.host}:{dead_proxy.port} -> {replacement.host}:{replacement.port}")
            return replacement
        else:
            logger.warning(f"No replacement proxy for {account.email}")
            self.db.commit()
            return None

    def release_all_free_proxies(self) -> dict:
        """
        Reset all dead/expired UNBOUND proxies back to ACTIVE.
        Does NOT touch EXHAUSTED proxies - those stay until manually deleted.
        """
        freed = self.db.query(Proxy).filter(
            Proxy.status.in_([ProxyStatus.DEAD, ProxyStatus.EXPIRED]),
            Proxy.bound_account_id == None,  # noqa: E711
        ).all()

        count = 0
        for proxy in freed:
            proxy.status = ProxyStatus.ACTIVE
            proxy.fail_count = 0
            count += 1

        self.db.commit()
        logger.info(f"Released {count} dead/expired proxies back to ACTIVE")
        return {"released": count}

    def reset_all_counters(self) -> dict:
        """
        Reset ALL per-provider usage AND fail counters on all proxies.
        Re-activates EXHAUSTED proxies back to ACTIVE.
        Use when starting fresh or when all counters have maxed out.
        """
        proxies = self.db.query(Proxy).filter(
            Proxy.status.in_([ProxyStatus.ACTIVE, ProxyStatus.EXHAUSTED]),
        ).all()

        count = 0
        reactivated = 0
        for p in proxies:
            p.use_gmail = 0
            p.use_yahoo = 0
            p.use_aol = 0
            p.use_outlook = 0
            p.use_hotmail = 0
            p.use_protonmail = 0
            p.use_webde = 0
            p.fail_gmail = 0
            p.fail_yahoo = 0
            p.fail_aol = 0
            p.fail_outlook = 0
            p.fail_hotmail = 0
            p.fail_protonmail = 0
            p.fail_webde = 0
            p.use_count = 0
            p.last_used_at = None
            p.cooldown_until = None
            p.cooldown_providers = None
            if p.status == ProxyStatus.EXHAUSTED:
                p.status = ProxyStatus.ACTIVE
                reactivated += 1
            count += 1

        self.db.commit()
        logger.info(f"[ProxyManager] Reset counters on {count} proxies ({reactivated} exhausted -> active)")
        return {"reset": count, "reactivated": reactivated}

    def reset_single_proxy_counters(self, proxy_id: int) -> dict:
        """Reset usage AND fail counters for a single proxy."""
        proxy = self.db.query(Proxy).filter(Proxy.id == proxy_id).first()
        if not proxy:
            return {"status": "error", "message": "Proxy not found"}
        proxy.use_gmail = 0
        proxy.use_yahoo = 0
        proxy.use_aol = 0
        proxy.use_outlook = 0
        proxy.use_hotmail = 0
        proxy.use_protonmail = 0
        proxy.use_webde = 0
        proxy.fail_gmail = 0
        proxy.fail_yahoo = 0
        proxy.fail_aol = 0
        proxy.fail_outlook = 0
        proxy.fail_hotmail = 0
        proxy.fail_protonmail = 0
        proxy.fail_webde = 0
        proxy.use_count = 0
        proxy.last_used_at = None
        proxy.cooldown_until = None
        proxy.cooldown_providers = None
        if proxy.status == ProxyStatus.EXHAUSTED:
            proxy.status = ProxyStatus.ACTIVE
        self.db.commit()
        logger.info(f"[ProxyManager] Reset counters for proxy {proxy.host}:{proxy.port}")
        return {"status": "ok", "proxy_id": proxy.id}

    def refresh_proxy(self, proxy_id: int, new_host: str = None, new_port: int = None,
                      new_username: str = None, new_password: str = None) -> dict:
        """
        Refresh proxy connection data (same provider changed credentials).
        The IP identity stays the same, just auth/port may change.
        """
        proxy = self.db.query(Proxy).get(proxy_id)
        if not proxy:
            return {"status": "error", "message": "Proxy not found"}

        if new_host:
            proxy.host = new_host
        if new_port:
            proxy.port = new_port
        if new_username is not None:
            proxy.username = new_username
        if new_password is not None:
            proxy.password = new_password

        # Reset health
        proxy.status = ProxyStatus.ACTIVE
        proxy.fail_count = 0
        proxy.cooldown_until = None
        proxy.cooldown_providers = None
        self.db.commit()

        bound_email = None
        if proxy.bound_account_id:
            account = self.db.query(Account).get(proxy.bound_account_id)
            bound_email = account.email if account else None

        logger.info(f"Proxy {proxy.host}:{proxy.port} refreshed (bound to: {bound_email or 'none'})")
        return {
            "status": "ok",
            "proxy_id": proxy.id,
            "bound_to": bound_email,
            "new_connection": proxy.to_string(),
        }

    def auto_reassign_dead_proxies(self) -> dict:
        """
        Find accounts bound to dead proxies and reassign them
        to available unbound active proxies from the pool.
        """
        reassigned = 0
        no_proxy = 0

        # Find all dead/expired proxies that have bound accounts
        dead_proxies = self.db.query(Proxy).filter(
            Proxy.status.in_([ProxyStatus.DEAD, ProxyStatus.EXPIRED]),
            Proxy.bound_account_id != None,  # noqa: E711
        ).all()

        for dead_proxy in dead_proxies:
            account = self.db.query(Account).get(dead_proxy.bound_account_id)
            if not account:
                dead_proxy.bound_account_id = None
                continue

            # Find a replacement (unbound, active)
            replacement = self.get_unbound_proxy()

            if replacement:
                # Unbind old
                dead_proxy.bound_account_id = None

                # Bind new
                self.bind_proxy_to_account(replacement, account)
                reassigned += 1
                logger.info(f"Auto-reassigned {account.email}: "
                            f"{dead_proxy.host}:{dead_proxy.port} -> {replacement.host}:{replacement.port}")
            else:
                no_proxy += 1
                logger.warning(f"No free proxy for {account.email} (old proxy dead)")

        self.db.commit()
        return {"reassigned": reassigned, "no_proxy_available": no_proxy}

    def mark_dead(self, proxy_id: int):
        """Mark a proxy as dead and auto-reassign its account."""
        proxy = self.db.query(Proxy).get(proxy_id)
        if proxy:
            proxy.status = ProxyStatus.DEAD
            self.db.commit()

            # Auto-reassign if bound to account
            if proxy.bound_account_id:
                self.auto_reassign_dead_proxies()

    def get_stats(self) -> dict:
        """Get proxy pool statistics."""
        total = self.db.query(Proxy).count()
        active = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE).count()
        dead = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.DEAD).count()
        exhausted = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.EXHAUSTED).count()
        bound = self.db.query(Proxy).filter(Proxy.bound_account_id != None).count()  # noqa: E711

        # Type breakdown (socks5 / http / mobile)
        from sqlalchemy import func
        type_rows = self.db.query(Proxy.proxy_type, func.count()).group_by(Proxy.proxy_type).all()
        by_type = {row[0] or "http": row[1] for row in type_rows}

        return {
            "total": total,
            "active": active,
            "dead": dead,
            "exhausted": exhausted,
            "bound": bound,
            "by_type": by_type,
        }

    async def check_all_proxies_health(self) -> dict:
        """
        Batch health check: TCP test all ACTIVE proxies.
        Returns stats: checked, alive, dead_marked, avg_latency_ms.
        """
        from .proxy_monitor import check_single_proxy

        active = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE
        ).all()

        if not active:
            return {"checked": 0, "alive": 0, "dead_marked": 0}

        checked = 0
        alive_count = 0
        dead_marked = 0
        latencies = []

        for proxy in active:
            try:
                result = await check_single_proxy(proxy)
                checked += 1
                if result.get("alive"):
                    alive_count += 1
                    proxy.fail_count = 0
                    ms = result.get("response_time_ms", 0)
                    proxy.response_time_ms = ms
                    if ms > 0:
                        latencies.append(ms)
                    if result.get("external_ip") and result["external_ip"] != "unknown":
                        proxy.external_ip = result["external_ip"]
                else:
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    if proxy.fail_count >= 3:
                        proxy.status = ProxyStatus.DEAD
                        dead_marked += 1
                        logger.warning(f"[Health] Proxy DEAD: {proxy.host}:{proxy.port} (3+ fails)")
            except Exception as e:
                logger.debug(f"[Health] Check error {proxy.host}:{proxy.port}: {e}")

        self.db.commit()
        avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

        logger.info(f"[Health] Checked {checked} proxies: {alive_count} alive, {dead_marked} → DEAD, avg {avg_latency}ms")
        return {
            "checked": checked,
            "alive": alive_count,
            "dead_marked": dead_marked,
            "avg_latency_ms": avg_latency,
        }

    async def auto_deactivate_slow_proxies(self, max_latency_ms: int = 10000) -> dict:
        """
        Mark proxies with latency > max_latency_ms as DEAD.
        Call after check_all_proxies_health() to have fresh latency data.
        """
        slow = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.response_time_ms > max_latency_ms,
        ).all()

        count = 0
        for proxy in slow:
            proxy.status = ProxyStatus.DEAD
            count += 1
            logger.warning(f"[Health] Slow proxy DEAD: {proxy.host}:{proxy.port} ({proxy.response_time_ms}ms > {max_latency_ms}ms)")

        if count:
            self.db.commit()
            logger.info(f"[Health] Deactivated {count} slow proxies (>{max_latency_ms}ms)")

        return {"deactivated": count, "threshold_ms": max_latency_ms}

