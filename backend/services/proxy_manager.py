"""
Leomail v3 — Proxy Manager
Import, rotate, and manage proxies with round-robin and GEO filtering.
1 proxy = 1 account (hard binding). Auto-reassign on proxy death.
"""
import random
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

            # Check duplicate — include username because rotating proxies
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

    def get_working_proxy(self, geo: str = None, exclude_ids: list[int] = None) -> Proxy | None:
        """
        Get next working proxy with round-robin rotation.
        Filters by GEO and status, excludes specified IDs.
        """
        query = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE)

        if geo and geo.upper() != "ANY":
            query = query.filter(Proxy.geo == geo.upper())

        if exclude_ids:
            query = query.filter(~Proxy.id.in_(exclude_ids))

        proxies = query.order_by(Proxy.id).all()

        if not proxies:
            # Fallback: any active proxy
            proxies = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE).all()

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

    def get_unbound_proxy(self, geo: str = None, device_type: str = None, provider: str = None) -> Proxy | None:
        """Get an active proxy NOT bound to any account.
        Filters by device_type and per-provider-GROUP usage limit.
        Groups: Gmail=G (limit 1, mobile-only), Yahoo+AOL=YA (limit 3), Outlook+Hotmail=OH (limit 3).
        Marks fully exhausted proxies as EXHAUSTED.
        NO FALLBACK: returns None if no matching proxy found.
        """
        query = self.db.query(Proxy).filter(
            Proxy.status == ProxyStatus.ACTIVE,
            Proxy.bound_account_id == None,  # noqa: E711
        )

        # Gmail: FORCE mobile proxy type
        if provider and provider.lower() == 'gmail':
            query = query.filter(Proxy.proxy_type == 'mobile')
        elif device_type:
            if device_type.startswith('phone'):
                query = query.filter(Proxy.proxy_type == 'mobile')
            # Desktop: include ALL proxy types (http, socks5, mobile)

        if provider:
            group_filter = self._provider_group_filter(provider)
            if group_filter is not None:
                query = query.filter(group_filter)
        if geo and geo.upper() != "ANY":
            query = query.filter(Proxy.geo == geo.upper())
        proxies = query.all()

        # Auto-mark exhausted proxies (all groups at limit)
        for p in list(proxies):
            if self._is_exhausted(p):
                proxies.remove(p)
                p.status = ProxyStatus.EXHAUSTED
                logger.info(f"Proxy {p.host}:{p.port} exhausted (all provider groups at limit) → EXHAUSTED")
                self.db.commit()

        if proxies:
            return random.choice(proxies)
        return None  # NO FALLBACK

    def get_proxy_pool(self, count: int, geo: str = None, device_type: str = None, provider: str = None) -> list[Proxy]:
        """Get N unique proxies for batch operation.
        Filters by device_type and per-provider usage limit.
        Gmail: mobile-only. Yahoo/Gmail: mobile proxies prioritized.
        NO FALLBACK: returns empty list if no matching proxies.
        """
        query = self.db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE)

        # Gmail: FORCE mobile proxy type
        if provider and provider.lower() == 'gmail':
            query = query.filter(Proxy.proxy_type == 'mobile')
        elif device_type:
            if device_type.startswith('phone'):
                query = query.filter(Proxy.proxy_type == 'mobile')

        if provider:
            group_filter = self._provider_group_filter(provider)
            if group_filter is not None:
                query = query.filter(group_filter)

        if geo and geo.upper() != "ANY":
            query = query.filter(Proxy.geo == geo.upper())

        proxies = query.all()

        # For strict providers (Yahoo, Gmail): prioritize mobile > residential/socks5/https
        # socks5/https are protocol types for residential proxies, NOT datacenter
        strict_providers = ('yahoo', 'gmail')
        if provider and provider.lower() in strict_providers:
            def proxy_priority(p):
                pt = (p.proxy_type or '').lower()
                if pt == 'mobile':
                    return 0  # Best: mobile
                else:
                    return 1  # Good: residential (socks5/https/http)
            proxies.sort(key=proxy_priority)
            mobile_count = sum(1 for p in proxies if (p.proxy_type or '').lower() == 'mobile')
            logger.info(f"[ProxyPool] {provider}: {len(proxies)} total proxies ({mobile_count} mobile, {len(proxies) - mobile_count} residential)")

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
        }
        return mapping.get(provider.lower())

    @staticmethod
    def _provider_group_filter(provider: str):
        """Get SQLAlchemy filter for provider GROUP limit.
        Groups: Yahoo+AOL (YA, limit 3), Outlook+Hotmail (OH, limit 3), Gmail (G, limit 1).
        """
        provider = provider.lower()
        if provider in ('yahoo', 'aol'):
            return (Proxy.use_yahoo + Proxy.use_aol) < ProxyManager.YA_LIMIT
        elif provider in ('outlook', 'hotmail'):
            return (Proxy.use_outlook + Proxy.use_hotmail) < ProxyManager.OH_LIMIT
        elif provider == 'gmail':
            return Proxy.use_gmail < ProxyManager.GMAIL_LIMIT
        return None

    @staticmethod
    def _is_exhausted(proxy: Proxy) -> bool:
        """Check if ALL provider groups are at their limit.
        Groups: Gmail (limit 1), Yahoo+AOL (limit 3), Outlook+Hotmail (limit 3).
        Returns True only if all 3 groups are exhausted.
        """
        g_exhausted = (proxy.use_gmail or 0) >= ProxyManager.GMAIL_LIMIT
        ya_exhausted = ((proxy.use_yahoo or 0) + (proxy.use_aol or 0)) >= ProxyManager.YA_LIMIT
        oh_exhausted = ((proxy.use_outlook or 0) + (proxy.use_hotmail or 0)) >= ProxyManager.OH_LIMIT
        return g_exhausted and ya_exhausted and oh_exhausted

    def increment_provider_usage(self, proxy: Proxy, provider: str):
        """Increment the per-provider usage counter and total use_count."""
        attr = f"use_{provider.lower()}"
        if hasattr(proxy, attr):
            setattr(proxy, attr, (getattr(proxy, attr) or 0) + 1)
        proxy.use_count = (proxy.use_count or 0) + 1
        self.db.commit()

    def bind_proxy_to_account(self, proxy: Proxy, account: Account):
        """Hard-bind a proxy to an account (1:1)."""
        proxy.bound_account_id = account.id
        account.proxy_id = proxy.id
        account.birth_ip = f"{proxy.host}:{proxy.port}"
        self.db.commit()
        logger.info(f"Proxy {proxy.host}:{proxy.port} bound to {account.email}")

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
        if not candidates:
            # Fallback: any active unbound proxy
            candidates = self.db.query(Proxy).filter(
                Proxy.status == ProxyStatus.ACTIVE,
                Proxy.bound_account_id == None,  # noqa: E711
            ).all()

        if not candidates:
            return None

        # Shuffle to avoid always picking same one
        random.shuffle(candidates)

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

    async def get_verified_unbound_proxy_async(self, proxy_type: str = None, protocol: str = None, exclude_ids: set = None) -> Proxy | None:
        """Async version of get_verified_unbound_proxy.
        exclude_ids: set of proxy IDs to skip (blacklisted/burned).
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

        candidates = query.all()

        # If no non-blacklisted proxies, try ANY unbound active proxy
        # but ONLY if there's no blacklist (first run) — never ignore blacklist
        if not candidates and not exclude_ids:
            candidates = self.db.query(Proxy).filter(
                Proxy.status == ProxyStatus.ACTIVE,
                Proxy.bound_account_id == None,  # noqa: E711
            ).all()

        if not candidates:
            if exclude_ids:
                logger.warning(f"[ProxyManager] All proxies blacklisted ({len(exclude_ids)} blocked), none left")
            return None

        random.shuffle(candidates)

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
        Replace dead proxy with same type (mobile→mobile, socks→socks).
        Unbinds old, binds new, returns new proxy or None.
        """
        # Mark old as dead
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
                        f"{dead_proxy.host}:{dead_proxy.port} → {replacement.host}:{replacement.port}")
            return replacement
        else:
            logger.warning(f"No replacement proxy for {account.email}")
            self.db.commit()
            return None

    def release_all_free_proxies(self) -> dict:
        """
        Reset all dead/expired UNBOUND proxies back to ACTIVE.
        Does NOT touch EXHAUSTED proxies — those stay until manually deleted.
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

            # Find a replacement (unbound, active, same geo if possible)
            replacement = self.get_unbound_proxy(geo=account.geo)
            if not replacement:
                replacement = self.get_unbound_proxy()  # any geo

            if replacement:
                # Unbind old
                dead_proxy.bound_account_id = None

                # Bind new
                self.bind_proxy_to_account(replacement, account)
                reassigned += 1
                logger.info(f"Auto-reassigned {account.email}: "
                            f"{dead_proxy.host}:{dead_proxy.port} → {replacement.host}:{replacement.port}")
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

