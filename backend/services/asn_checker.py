"""
Leomail v4 - ASN-based Proxy Type Classifier
Determines if an IP is datacenter, residential, or mobile by checking its ASN.
Uses ipwhois for ASN lookups with aggressive caching.
"""
import socket
import struct
from functools import lru_cache
from typing import Optional
from loguru import logger

# ── IP type cache: {ip_str: "datacenter"|"residential"|"mobile"|"unknown"} ──
_ip_type_cache: dict[str, str] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# Known datacenter / hosting / VPN ASNs (Yahoo/Gmail block these instantly)
# This list covers the most common datacenter ASNs used by proxy providers
# ═══════════════════════════════════════════════════════════════════════════════

DATACENTER_ASNS = {
    # Major hosting / cloud
    "AS14061",  # DigitalOcean
    "AS16509",  # Amazon AWS
    "AS15169",  # Google Cloud
    "AS8075",   # Microsoft Azure
    "AS13335",  # Cloudflare
    "AS20473",  # Vultr / Choopa
    "AS63949",  # Linode / Akamai
    "AS14618",  # Amazon AWS
    "AS16276",  # OVH
    "AS24940",  # Hetzner
    "AS51167",  # Contabo
    "AS46606",  # PhoenixNAP / HostHatch
    "AS36352",  # ColoCrossing
    "AS62567",  # DigitalOcean
    "AS200019", # AlexHost
    "AS9009",   # M247 (huge — ASocks/PIA/etc use this)
    "AS208323", # Stark Industries (VPN/proxy infra)
    "AS44477",  # Stark Industries Solutions
    "AS49981",  # WorldStream
    "AS53667",  # FranTech / BuyVM
    "AS40021",  # Contabo
    "AS47846",  # Serverel
    "AS62005",  # BlueVPS
    "AS212238", # Datacamp
    "AS51396",  # Pfcloud
    "AS41378",  # NexGenTec
    "AS202015", # HZ NL
    "AS210277", # Stark Industries DE
    "AS198953", # ProxyRack
    "AS35540",  # Smartproxy infra
    "AS60781",  # LeaseWeb NL
    "AS28753",  # LeaseWeb DE
    "AS59764",  # Hosting Ukraine
    "AS44546",  # Serverion
    "AS49505",  # Selectel
    "AS47541",  # VPS.ag
    "AS215546", # Stark Industries  
    "AS44901",  # BelCloud Hosting
    "AS61272",  # LU-net
    "AS397036", # Cybertron
    "AS394380", # LEASEWEB-USA
    "AS55286",  # B2 Net (ServerCheap)
    "AS30083",  # HEG US
    "AS62904",  # Eonix
    "AS393406", # DigitalOcean
    "AS7979",   # Servers.com
    "AS29802",  # HIVELOCITY
    "AS37963",  # Alibaba Cloud
    "AS45102",  # Alibaba US
    "AS132203", # Tencent Cloud
    "AS398493", # Clouvider
    "AS211252", # Delis
    "AS211298", # ELFISERV
    "AS6939",   # Hurricane Electric
    "AS209",    # CenturyLink
    "AS174",    # Cogent
    "AS3257",   # GTT
    "AS1299",   # Arelion (Telia)
    "AS8560",   # 1&1 IONOS
    "AS197540", # Netcup
    "AS395003", # Path.net
    # VPN / privacy services
    "AS212238", # Datacamp Ltd (NordVPN infra)
    "AS9009",   # M247 (used by ExpressVPN, PIA, etc.)
    "AS60068",  # Datacamp CDN
    "AS209103", # OVH VPS
    "AS16509",  # AWS (used by many VPNs)
}

# Known IP ranges for major datacenter providers (for instant match without ASN lookup)
# Format: (ip_int_start, ip_int_end, label)
DATACENTER_IP_RANGES = []

def _ip_to_int(ip: str) -> int:
    """Convert IP string to integer for range comparison."""
    try:
        return struct.unpack("!I", socket.inet_aton(ip))[0]
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Known mobile carrier ASNs (Gmail requires these)
# ═══════════════════════════════════════════════════════════════════════════════

MOBILE_ASNS = {
    # US carriers
    "AS22394",  # Verizon Wireless
    "AS6167",   # Verizon Business
    "AS7018",   # AT&T
    "AS20057",  # AT&T Mobility
    "AS21928",  # T-Mobile US
    "AS393225", # T-Mobile US
    "AS10507",  # Sprint / T-Mobile
    "AS11260",  # EarthLink (T-Mobile MVNO)
    # EU carriers
    "AS12479",  # Orange / France Telecom
    "AS5511",   # Orange France
    "AS15169",  # Google Fi (skip — Google cloud)
    "AS3352",   # Telefonica Spain
    "AS12357",  # Vodafone DE
    "AS25255",  # Vodafone IT
    "AS30722",  # Vodafone UK
    "AS6805",   # Telefonica DE
    "AS20940",  # Akamai Mobile
    "AS12430",  # Vodafone Spain
    "AS3209",   # Vodafone DE
    "AS8422",   # NetCologne
    "AS29208",  # T-Mobile NL
    "AS31334",  # KPN Mobile NL
    # RU/CIS carriers
    "AS25159",  # MTS Russia
    "AS12389",  # Rostelecom
    "AS31133",  # MegaFon
    "AS8402",   # Corbina / Vimpelcom
    "AS3216",   # Beeline (PJSC VimpelCom)
    "AS16345",  # Beeline
    "AS34569",  # Tele2 RU
    "AS12714",  # TI Net Italy
    # LATAM
    "AS7303",   # Telecom Argentina
    "AS11172",  # Alestra/AT&T Mexico
    "AS28000",  # Claro Brazil
    "AS18881",  # Global Village Telecom
    "AS10318",  # Movistar Argentina
    "AS27747",  # Claro Colombia
    "AS6503",   # Axtel Mexico
    "AS8151",   # Telmex Mexico
    "AS11888",  # Vivo Brazil
    "AS26599",  # Telefonica Brazil
    "AS22364",  # Entel Chile
}


# ═══════════════════════════════════════════════════════════════════════════════
# ASN lookup (cached)
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=2048)
def _lookup_asn(ip: str) -> Optional[str]:
    """Look up ASN for an IP address. Uses ip-api.com (free, 45 req/min)."""
    # Method 1: ip-api.com HTTP API (always works, requests is a core dep)
    try:
        import requests
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=as",
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            as_str = data.get("as", "")  # "AS9009 M247 Ltd"
            if as_str:
                asn = as_str.split()[0]  # "AS9009"
                return asn
    except Exception as e:
        logger.debug(f"[ASN] ip-api.com failed for {ip}: {e}")

    # Method 2: Team Cymru DNS (needs dnspython, fast if available)
    try:
        import dns.resolver
        parts = ip.split(".")
        if len(parts) == 4:
            rev = ".".join(reversed(parts))
            answers = dns.resolver.resolve(f"{rev}.origin.asn.cymru.com", "TXT")
            for answer in answers:
                txt = str(answer).strip('"')
                asn = txt.split("|")[0].strip()
                return f"AS{asn}"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[ASN] Cymru DNS failed for {ip}: {e}")

    return None


def _lookup_asn_org(ip: str) -> str:
    """Get human-readable ASN org name for logging."""
    try:
        import requests
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=as,org,isp", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get("as", "") or data.get("org", "") or data.get("isp", "")
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Classification
# ═══════════════════════════════════════════════════════════════════════════════

def classify_ip(ip: str) -> str:
    """
    Classify an IP as 'datacenter', 'residential', 'mobile', or 'unknown'.
    Uses cached results.
    """
    if ip in _ip_type_cache:
        return _ip_type_cache[ip]
    
    result = "unknown"
    
    asn = _lookup_asn(ip)
    if asn:
        if asn in DATACENTER_ASNS:
            result = "datacenter"
        elif asn in MOBILE_ASNS:
            result = "mobile"
        else:
            # Not in known datacenter or mobile lists → likely residential ISP
            result = "residential"
    
    _ip_type_cache[ip] = result
    logger.debug(f"[ASN] {ip} → {result} (ASN: {asn})")
    return result


def classify_ip_detailed(ip: str) -> dict:
    """Classify IP and return full details for logging."""
    ip_type = classify_ip(ip)
    asn = _lookup_asn(ip)
    org = _lookup_asn_org(ip) if ip_type == "datacenter" else ""
    return {
        "ip": ip,
        "type": ip_type,
        "asn": asn or "unknown",
        "org": org,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Service compatibility matrix
# ═══════════════════════════════════════════════════════════════════════════════

# Which IP types each service accepts
SERVICE_ACCEPTS = {
    "gmail":      {"mobile"},                           # Gmail: mobile 4G ONLY
    "yahoo":      {"residential", "mobile"},            # Yahoo: residential/mobile ISP only
    "aol":        {"residential", "mobile"},            # AOL: same as Yahoo (Verizon)
    "outlook":    {"residential", "mobile", "datacenter"},  # Outlook: accepts all
    "hotmail":    {"residential", "mobile", "datacenter"},  # Hotmail: same as Outlook
    "protonmail": {"residential", "mobile", "datacenter"},  # Protonmail: accepts all
}


def is_suitable_for(ip: str, service: str) -> bool:
    """
    Check if an IP is suitable for a given email service.
    Returns True if the IP type is accepted by the service.
    """
    ip_type = classify_ip(ip)
    
    if ip_type == "unknown":
        # Unknown IPs: allow for lenient services, block for strict ones
        return service not in ("gmail",)  # Only block unknown for Gmail
    
    accepted = SERVICE_ACCEPTS.get(service.lower(), {"residential", "mobile", "datacenter"})
    return ip_type in accepted


def filter_proxies_for_service(proxies: list, service: str) -> list:
    """
    Filter a list of proxy dicts, keeping only those suitable for the service.
    Each proxy dict must have a 'host' key with the IP.
    Returns (suitable, unsuitable) tuple.
    """
    suitable = []
    unsuitable = []
    
    for p in proxies:
        ip = p.get("host", p.get("ip", ""))
        if not ip:
            unsuitable.append(p)
            continue
        
        if is_suitable_for(ip, service):
            suitable.append(p)
        else:
            ip_type = classify_ip(ip)
            logger.info(f"[ASN] Skipping {ip} for {service} — {ip_type} IP")
            unsuitable.append(p)
    
    return suitable, unsuitable


def precheck_proxies(proxies_db_list, service: str) -> tuple:
    """
    Pre-check a list of Proxy ORM objects for service compatibility.
    Returns (suitable_ids, unsuitable_count).
    """
    suitable_ids = []
    unsuitable_count = 0
    
    for p in proxies_db_list:
        if is_suitable_for(p.host, service):
            suitable_ids.append(p.id)
        else:
            unsuitable_count += 1
    
    return suitable_ids, unsuitable_count
