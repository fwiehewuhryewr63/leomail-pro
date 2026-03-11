import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    LayoutDashboard, CheckCircle, Users, Shield, Mail, Database, FileText, Link2, Package, Layers,
    BarChart3, AlertTriangle, Clock, DollarSign, X, Send, TrendingUp
} from 'lucide-react';
import { API } from '../api';
import { PROVIDER_COLORS, domainToColor } from '../utils/providers';
import { ProviderLogo } from '../components/ProviderLogos';

/* ── SVG mini sparkline ── */
function Sparkline({ data = [], color = '#10B981', height = 30 }) {
    if (!data.length) data = [0, 0, 0, 0, 0, 0, 0];
    const max = Math.max(...data, 1);
    const len = Math.max(data.length - 1, 1);
    const pts = data.map((v, i) => `${(i / len) * 100},${100 - (v / max) * 80}`).join(' ');
    return (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: '100%', height, opacity: 0.7 }}>
            <polyline fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" points={pts} />
        </svg>
    );
}

/* ── Circular progress ring ── */
function CircleProgress({ value = 0, max = 100, size = 52, color = '#10B981' }) {
    const pct = max > 0 ? Math.round((value / max) * 100) : 0;
    const r = (size - 6) / 2;
    const circ = 2 * Math.PI * r;
    const offset = circ - (pct / 100) * circ;
    return (
        <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
            <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5"
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.16,1,0.3,1)' }} />
            </svg>
            <div style={{
                position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.72em', fontWeight: 800, color: 'var(--text-primary)',
            }}>{pct}%</div>
        </div>
    );
}

/* ── Activity Area Chart ── */
function AreaChart({ data = [], labels = [], height = 180 }) {
    if (!data.length) data = [0];
    if (!labels.length) labels = ['—'];
    const max = Math.max(...data, 1);
    const w = 600, h = 180, pad = 36;
    const pts = data.map((v, i) => ({
        x: pad + (data.length > 1 ? (i / (data.length - 1)) * (w - pad * 2) : (w - pad * 2) / 2),
        y: pad + (1 - v / max) * (h - pad * 2),
    }));
    const line = pts.map(p => `${p.x},${p.y}`).join(' ');
    const area = `${pad},${h - pad} ${line} ${w - pad},${h - pad}`;
    const gridFracs = [1, 0.75, 0.5, 0.25, 0];
    const gridLines = gridFracs.map(f => pad + (1 - f) * (h - pad * 2));

    // Show max ~10 labels to avoid clutter
    const labelStep = Math.max(1, Math.ceil(labels.length / 10));

    return (
        <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height }}>
            <defs>
                <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10B981" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#10B981" stopOpacity="0.02" />
                </linearGradient>
            </defs>
            {gridLines.map((y, i) => (
                <g key={i}>
                    <line x1={pad} y1={y} x2={w - pad} y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                    <text x={pad - 6} y={y + 3} textAnchor="end" fill="rgba(255,255,255,0.25)" fontSize="9" fontFamily="Inter">
                        {Math.round(max * [1, 0.75, 0.5, 0.25, 0][i])}
                    </text>
                </g>
            ))}
            {pts.map((p, i) => (
                i % labelStep === 0 || i === pts.length - 1 ? (
                    <text key={i} x={p.x} y={h - 8} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize="9" fontFamily="Inter" fontWeight="600">
                        {labels[i]}
                    </text>
                ) : null
            ))}
            <polygon points={area} fill="url(#areaFill)" />
            <polyline fill="none" stroke="#10B981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={line} />
            {pts.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r="3" fill="#10B981" stroke="#0a0a0f" strokeWidth="2" />
            ))}
        </svg>
    );
}

/* ── Period selector pill ── */
const PERIODS = [
    { label: '1D', days: 1 },
    { label: '7D', days: 7 },
    { label: '14D', days: 14 },
    { label: '30D', days: 30 },
];

export default function Dashboard() {
    const navigate = useNavigate();
    const [s, setS] = useState({});
    const [health, setHealth] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [period, setPeriod] = useState(7);
    const [analytics, setAnalytics] = useState(null);
    const [warmupData, setWarmupData] = useState(null);
    const [alerts, setAlerts] = useState(null);
    const [costs, setCosts] = useState(null);
    const [campaignStats, setCampaignStats] = useState(null);
    const [dismissedAlerts, setDismissedAlerts] = useState(new Set());

    const load = (days) => {
        const d = days || period;
        fetch(`${API}/dashboard/stats?days=${d}`)
            .then(r => r.json())
            .then(data => { setS(data); setLastUpdate(new Date()); })
            .catch(() => { });
        fetch(`${API}/health/resources`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setHealth(data))
            .catch(() => { });
        fetch(`${API}/dashboard/autoreg-analytics`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setAnalytics(data))
            .catch(() => { });
        fetch(`${API}/dashboard/warmup-analytics`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setWarmupData(data))
            .catch(() => { });
        fetch(`${API}/dashboard/alerts`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setAlerts(data))
            .catch(() => { });
        fetch(`${API}/dashboard/costs`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setCosts(data))
            .catch(() => { });
        fetch(`${API}/dashboard/campaign-stats`)
            .then(r => r.ok ? r.json() : null)
            .then(data => data && setCampaignStats(data))
            .catch(() => { });
    };

    const changePeriod = (days) => {
        setPeriod(days);
        load(days);
    };

    useEffect(() => {
        load();
        const iv = setInterval(load, 15000);
        return () => clearInterval(iv);
    }, []);

    const ms = s.mailing_stats || {};
    const proxyTotal = health?.proxies?.total || 0;
    const proxyAlive = health?.proxies?.alive || 0;
    const totalAccs = s.total_accounts || 0;

    /* Provider distribution */
    const byProvider = s.by_provider || {};
    const providers = [
        { id: 'gmail', name: 'Gmail', color: PROVIDER_COLORS.gmail },
        { id: 'yahoo', name: 'Yahoo', color: PROVIDER_COLORS.yahoo },
        { id: 'outlook', name: 'Outlook', color: PROVIDER_COLORS.outlook },
        { id: 'protonmail', name: 'ProtonMail', color: PROVIDER_COLORS.protonmail },
        { id: 'aol', name: 'AOL', color: PROVIDER_COLORS.aol },
        { id: 'hotmail', name: 'Hotmail', color: PROVIDER_COLORS.hotmail },
        { id: 'webde', name: 'Web.de', color: PROVIDER_COLORS.webde },
    ];
    const providerDist = providers.map(p => ({
        ...p,
        count: byProvider[p.id] || 0,
        pct: totalAccs > 0 ? Math.round(((byProvider[p.id] || 0) / totalAccs) * 100) : 0,
    })).filter(p => p.count > 0).sort((a, b) => b.count - a.count);

    /* Activity data from API */
    const activityData = s.activity_data || [];
    const chartLabels = activityData.map(d => d.date);
    const chartAccounts = activityData.map(d => d.accounts);
    const chartEmails = activityData.map(d => d.emails);
    const chartData = chartAccounts.map((a, i) => a + (chartEmails[i] || 0)); // combined

    const sparkAccounts = chartAccounts.length > 0 ? chartAccounts.slice(-7) : [0];
    const sparkSent = chartEmails.length > 0 ? chartEmails.slice(-7) : [0];

    /* Resource status */
    const resources = [
        { name: 'Names', icon: <Users size={14} />, count: s.total_names || 0, color: '#10B981', path: '/names' },
        { name: 'Links', icon: <Link2 size={14} />, count: s.total_links || 0, color: '#3B82F6', path: '/links' },
        { name: 'Templates', icon: <FileText size={14} />, count: s.total_templates || 0, color: '#F59E0B', path: '/templates' },
        { name: 'Databases', icon: <Database size={14} />, count: s.total_databases || 0, color: '#8B5CF6', path: '/databases' },
        { name: 'Farms', icon: <Layers size={14} />, count: s.total_farms || 0, color: '#06B6D4', path: '/farms' },
    ];

    const timeAgo = lastUpdate ? (() => {
        const diff = Math.floor((Date.now() - lastUpdate.getTime()) / 1000);
        if (diff < 5) return 'just now';
        if (diff < 60) return `${diff}s ago`;
        return `${Math.floor(diff / 60)}m ago`;
    })() : '—';

    /* Clickable card wrapper */
    const ClickCard = ({ to, children, style = {}, ...rest }) => (
        <div className="card dash-click-card" onClick={() => navigate(to)} style={style} {...rest}>
            {children}
        </div>
    );

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div className="page-header">
                <div className="page-breadcrumb">OVERVIEW / DASHBOARD</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h2 className="page-title">
                        <LayoutDashboard size={22} /> Dashboard
                    </h2>
                    <div className="dashboard-header-status">
                        <div className="dashboard-header-status-dot" />
                        Updated {timeAgo}
                    </div>
                </div>
                <div className="dashboard-hero-strip">
                    <div className="dashboard-hero-chip">
                        <span className="dashboard-hero-chip-label">Accounts</span>
                        <span className="dashboard-hero-chip-value">{(totalAccs || 0).toLocaleString()}</span>
                    </div>
                    <div className="dashboard-hero-chip">
                        <span className="dashboard-hero-chip-label">Live Proxies</span>
                        <span className="dashboard-hero-chip-value">{proxyAlive}/{proxyTotal}</span>
                    </div>
                    <div className="dashboard-hero-chip">
                        <span className="dashboard-hero-chip-label">Sent Today</span>
                        <span className="dashboard-hero-chip-value">{(ms.total_sent || 0).toLocaleString()}</span>
                    </div>
                    <div className="dashboard-hero-chip">
                        <span className="dashboard-hero-chip-label">Inbox Rate</span>
                        <span className="dashboard-hero-chip-value">{ms.inbox_rate || 0}%</span>
                    </div>
                </div>
            </div>

            {/* ═══ SYSTEM ALERTS ═══ */}
            {alerts && alerts.length > 0 && (() => {
                const visible = alerts.filter(a => !dismissedAlerts.has(a.id || a.message));
                if (!visible.length) return null;
                const sevColors = { critical: '#EF4444', warning: '#F59E0B', info: '#3B82F6' };
                const sevBg = { critical: 'rgba(239,68,68,0.08)', warning: 'rgba(245,158,11,0.06)', info: 'rgba(59,130,246,0.06)' };
                return (
                    <div style={{ marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {visible.slice(0, 5).map((alert, i) => {
                            const sev = (alert.severity || 'info').toLowerCase();
                            return (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'center', gap: 10,
                                    padding: '10px 14px', borderRadius: 8,
                                    background: sevBg[sev] || sevBg.info,
                                    borderLeft: `3px solid ${sevColors[sev] || sevColors.info}`,
                                }}>
                                    <AlertTriangle size={14} style={{ color: sevColors[sev] || sevColors.info, flexShrink: 0 }} />
                                    <span style={{ fontSize: '0.82em', fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
                                        {alert.message}
                                    </span>
                                    <span style={{ fontSize: '0.68em', fontWeight: 700, color: sevColors[sev], textTransform: 'uppercase', flexShrink: 0 }}>
                                        {sev}
                                    </span>
                                    <X size={12} style={{ cursor: 'pointer', color: 'var(--text-muted)', flexShrink: 0 }}
                                        onClick={() => setDismissedAlerts(prev => new Set([...prev, alert.id || alert.message]))} />
                                </div>
                            );
                        })}
                    </div>
                );
            })()}

            {/* ═══ 5 STAT CARDS ═══ */}
            <div className="dash-stats stagger">
                {/* ACCOUNTS */}
                <ClickCard to="/accounts" style={{ padding: '14px 16px', borderLeft: '3px solid #10B981' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#10B981', lineHeight: 1 }}>
                                {(totalAccs || 0).toLocaleString()}
                            </div>
                            <div style={{ fontSize: '0.65em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>ACCOUNTS</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={sparkAccounts} color="#10B981" /></div>
                    </div>
                </ClickCard>

                {/* PROXIES */}
                <ClickCard to="/proxies" style={{ padding: '14px 16px', borderLeft: '3px solid #10B981' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ lineHeight: 1 }}>
                                <span style={{ fontSize: '1.8em', fontWeight: 900, color: '#10B981' }}>{proxyAlive}</span>
                                <span style={{ fontSize: '0.9em', fontWeight: 500, color: 'var(--text-muted)' }}>/{proxyTotal}</span>
                            </div>
                            <div style={{ fontSize: '0.65em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>PROXIES</div>
                        </div>
                        <CircleProgress value={proxyAlive} max={proxyTotal} size={48} />
                    </div>
                </ClickCard>

                {/* SENT TODAY */}
                <ClickCard to="/campaigns" style={{ padding: '14px 16px', borderLeft: '3px solid #06B6D4' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#06B6D4', lineHeight: 1 }}>
                                {(ms.total_sent || 0).toLocaleString()}
                            </div>
                            <div style={{ fontSize: '0.65em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>SENT TODAY</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={sparkSent} color="#06B6D4" /></div>
                    </div>
                </ClickCard>

                {/* INBOX RATE */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #22C55E' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#22C55E', lineHeight: 1 }}>
                                {ms.inbox_rate || 0}%
                            </div>
                            <div style={{ fontSize: '0.65em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>INBOX RATE</div>
                        </div>
                        <CheckCircle size={24} style={{ color: '#22C55E', opacity: 0.5, flexShrink: 0 }} />
                    </div>
                </div>

                {/* ACTIVE TASKS */}
                <ClickCard to="/threads" style={{ padding: '14px 16px', borderLeft: '3px solid #8B5CF6' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#8B5CF6', lineHeight: 1 }}>
                                {s.active_tasks || 0}
                            </div>
                            <div style={{ fontSize: '0.65em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>ACTIVE TASKS</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={[1, 2, 3, 2, 3, 4, 3]} color="#8B5CF6" /></div>
                    </div>
                </ClickCard>
            </div>

            {/* ═══ MIDDLE ROW: Chart + Providers ═══ */}
            <div className="dash-grid">
                {/* Activity Chart with Period Selector */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Mail size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Activity</span>
                        <span style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>accounts + emails</span>
                        {/* Period selector */}
                        <div className="pill-tabs" style={{ marginLeft: 'auto' }}>
                            {PERIODS.map(p => (
                                <button key={p.days} onClick={() => changePeriod(p.days)}
                                    className={`pill-tab${period === p.days ? ' active' : ''}`}>
                                    {p.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <AreaChart data={chartData} labels={chartLabels} height={180} />
                </div>

                {/* Provider Distribution */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Package size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Provider Distribution</span>
                        <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: 'auto' }}>{totalAccs} total</span>
                    </div>
                    {providerDist.length > 0 ? (
                        providerDist.map(p => (
                            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                                <ProviderLogo provider={p.id} size={22} />
                                <span style={{ fontSize: '0.85em', fontWeight: 600, width: 90, color: 'var(--text-primary)' }}>{p.name}</span>
                                <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.04)', overflow: 'hidden' }}>
                                    <div style={{
                                        height: '100%', borderRadius: 3, width: `${p.pct}%`,
                                        background: `linear-gradient(90deg, ${p.color}, ${p.color}88)`,
                                        transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
                                    }} />
                                </div>
                                <span style={{ fontSize: '0.82em', fontWeight: 700, width: 44, textAlign: 'right', color: p.color }}>{p.count}</span>
                                <span style={{ fontSize: '0.75em', fontWeight: 600, width: 30, textAlign: 'right', color: 'var(--text-muted)' }}>{p.pct}%</span>
                            </div>
                        ))
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85em', padding: '24px 0', textAlign: 'center' }}>
                            No accounts registered
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ BOTTOM ROW: Resources + Activity ═══ */}
            <div className="dash-grid">
                {/* Resource Status */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Shield size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Resource Status</span>
                    </div>
                    {resources.map(r => (
                        <div key={r.name} onClick={() => navigate(r.path)} style={{
                            display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
                            borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: 'pointer',
                            transition: 'all 0.15s',
                        }} onMouseEnter={e => e.currentTarget.style.paddingLeft = '6px'}
                            onMouseLeave={e => e.currentTarget.style.paddingLeft = '0'}>
                            <div style={{
                                width: 28, height: 28, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: `${r.color}12`, color: r.color,
                            }}>{r.icon}</div>
                            <span style={{ fontSize: '0.88em', fontWeight: 600, flex: 1, color: 'var(--text-primary)' }}>{r.name}</span>
                            <span style={{ fontSize: '0.95em', fontWeight: 800, color: r.color }}>{r.count.toLocaleString()}</span>
                            <div style={{
                                width: 7, height: 7, borderRadius: '50%',
                                background: r.count > 0 ? '#22C55E' : 'rgba(255,255,255,0.15)',
                                boxShadow: r.count > 0 ? '0 0 6px rgba(34,197,94,0.5)' : 'none',
                            }} />
                        </div>
                    ))}
                </div>

                {/* Live Activity */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 8px rgba(16,185,129,0.6)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Live Activity</span>
                    </div>
                    {s.recent_activity && s.recent_activity.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {s.recent_activity.slice(0, 8).map((a, i) => {
                                // Color-code by provider from email in message
                                const msg = a.message || '—';
                                const emailMatch = msg.match(/[\w.-]+@([\w.-]+)/i);
                                const domain = emailMatch ? emailMatch[1].toLowerCase() : '';
                                const provColor = domainToColor(domain);
                                return (
                                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82em' }}>
                                        <span style={{
                                            width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                                            background: a.type === 'success' ? '#22C55E' : a.type === 'error' ? '#EF4444' : '#3B82F6',
                                        }} />
                                        <span style={{ color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.88em', flexShrink: 0, width: 48 }}>
                                            {a.time || '—'}
                                        </span>
                                        <span style={{ color: provColor, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: emailMatch ? 600 : 400 }}>
                                            {msg}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85em', padding: '24px 0', textAlign: 'center' }}>
                            No recent activity
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ ALERTS + WARMUP ROW ═══ */}
            <div className="dash-grid" style={{ marginTop: 12 }}>
                {/* System Alerts */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <AlertTriangle size={14} style={{ color: alerts?.counts?.critical > 0 ? '#EF4444' : alerts?.counts?.warning > 0 ? '#F59E0B' : '#10B981' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>System Health</span>
                        {alerts?.counts?.critical > 0 && (
                            <span style={{ fontSize: '0.7em', fontWeight: 700, color: '#EF4444', background: 'rgba(239,68,68,0.1)', padding: '2px 8px', borderRadius: 10 }}>
                                {alerts.counts.critical} critical
                            </span>
                        )}
                        {alerts?.counts?.warning > 0 && (
                            <span style={{ fontSize: '0.7em', fontWeight: 700, color: '#F59E0B', background: 'rgba(245,158,11,0.1)', padding: '2px 8px', borderRadius: 10 }}>
                                {alerts.counts.warning} warning
                            </span>
                        )}
                        {!alerts?.alerts?.length && (
                            <span style={{ fontSize: '0.7em', fontWeight: 700, color: '#10B981', background: 'rgba(16,185,129,0.1)', padding: '2px 8px', borderRadius: 10 }}>
                                All clear
                            </span>
                        )}
                    </div>
                    {alerts?.alerts?.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {alerts.alerts.slice(0, 6).map((a, i) => (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 10px', borderRadius: 6,
                                    background: a.level === 'critical' ? 'rgba(239,68,68,0.06)' : a.level === 'warning' ? 'rgba(245,158,11,0.06)' : 'rgba(59,130,246,0.06)',
                                    borderLeft: `3px solid ${a.level === 'critical' ? '#EF4444' : a.level === 'warning' ? '#F59E0B' : '#3B82F6'}`,
                                }}>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: '0.8em', fontWeight: 700, color: a.level === 'critical' ? '#EF4444' : a.level === 'warning' ? '#F59E0B' : '#3B82F6' }}>
                                            {a.title}
                                        </div>
                                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 2 }}>{a.message}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '20px 0' }}>
                            ✅ No active alerts — system healthy
                        </div>
                    )}
                </div>

                {/* Warmup Progress */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Mail size={14} style={{ color: '#F59E0B' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Warmup Progress</span>
                        {warmupData?.overall && (
                            <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                                {warmupData.overall.warming_count} warming · {warmupData.overall.warmed_count} warmed · Avg health: {warmupData.overall.avg_health}
                            </span>
                        )}
                    </div>
                    {warmupData?.phases && Object.keys(warmupData.phases).length > 0 ? (
                        <>
                            {/* Phase bar */}
                            <div style={{ display: 'flex', gap: 2, height: 24, borderRadius: 6, overflow: 'hidden', marginBottom: 12 }}>
                                {['new', 'phase_1', 'phase_2', 'phase_3', 'phase_4', 'phase_5', 'warmed'].map(key => {
                                    const d = warmupData.phases[key];
                                    if (!d || !d.count) return null;
                                    const colors = { new: '#6B7280', phase_1: '#3B82F6', phase_2: '#06B6D4', phase_3: '#10B981', phase_4: '#F59E0B', phase_5: '#EF4444', warmed: '#22C55E' };
                                    const total = Object.values(warmupData.phases).reduce((s, p) => s + (p?.count || 0), 0);
                                    const pct = total > 0 ? (d.count / total * 100) : 0;
                                    return (
                                        <div key={key} title={`${key}: ${d.count} (health: ${d.avg_health})`}
                                            style={{ width: `${pct}%`, background: colors[key] || '#6B7280', display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: pct > 5 ? 0 : 2 }}>
                                            {pct > 10 && <span style={{ fontSize: '0.65em', fontWeight: 700, color: '#fff' }}>{d.count}</span>}
                                        </div>
                                    );
                                })}
                            </div>
                            {/* Health distribution */}
                            {warmupData.health_distribution && (
                                <div style={{ display: 'flex', gap: 6 }}>
                                    {Object.entries(warmupData.health_distribution).map(([range, count]) => {
                                        const colors = { '0-20': '#EF4444', '21-40': '#F59E0B', '41-60': '#F59E0B', '61-80': '#10B981', '81-100': '#22C55E' };
                                        return (
                                            <div key={range} style={{ flex: 1, textAlign: 'center', padding: '4px 0', borderRadius: 4, background: `${colors[range]}08` }}>
                                                <div style={{ fontSize: '1em', fontWeight: 800, color: colors[range] }}>{count}</div>
                                                <div style={{ fontSize: '0.62em', fontWeight: 600, color: 'var(--text-muted)' }}>{range}</div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '20px 0' }}>
                            No warmup data
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ COST TRACKER ═══ */}
            <div className="dash-grid">
                {/* Session Costs */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <DollarSign size={14} style={{ color: '#F59E0B' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Cost Tracker</span>
                        {costs?.session && (
                            <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                                Session: ${costs.session.total?.toFixed(2) || '0.00'}
                            </span>
                        )}
                    </div>
                    {costs?.session ? (
                        <div style={{ display: 'flex', gap: 8 }}>
                            {[{ label: 'SMS', value: costs.session.sms, count: costs.session.sms_orders, color: '#3B82F6' },
                            { label: 'Captcha', value: costs.session.captcha, count: costs.session.captcha_solves, color: '#8B5CF6' },
                            { label: 'Total', value: costs.session.total, count: null, color: '#F59E0B' },
                            ].map(item => (
                                <div key={item.label} style={{ flex: 1, textAlign: 'center', padding: '10px 6px', borderRadius: 6, background: `${item.color}08` }}>
                                    <div style={{ fontSize: '1.2em', fontWeight: 800, color: item.color }}>${item.value?.toFixed(2) || '0.00'}</div>
                                    <div style={{ fontSize: '0.65em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 2 }}>{item.label}</div>
                                    {item.count !== null && (
                                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', marginTop: 1 }}>{item.count} ops</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '20px 0' }}>
                            💰 Данные о расходах появятся после первого авторега
                        </div>
                    )}
                    {/* 7-day spending */}
                    {costs?.daily?.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                            <Sparkline data={costs.daily.map(d => d.amount)} color="#F59E0B" height={24} />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62em', color: 'var(--text-muted)', marginTop: 2 }}>
                                <span>{costs.daily[0]?.date}</span>
                                <span>{costs.daily[costs.daily.length - 1]?.date}</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Pre-flight Cost Estimates */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Shield size={14} style={{ color: '#10B981' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Pre-flight Estimate</span>
                    </div>
                    {health?.cost_estimate ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <div style={{ flex: 1, textAlign: 'center', padding: '10px 6px', borderRadius: 6, background: 'rgba(16,185,129,0.06)' }}>
                                    <div style={{ fontSize: '1.4em', fontWeight: 900, color: '#10B981' }}>{health.cost_estimate.affordable_accounts}</div>
                                    <div style={{ fontSize: '0.62em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Can Afford</div>
                                </div>
                                <div style={{ flex: 1, textAlign: 'center', padding: '10px 6px', borderRadius: 6, background: 'rgba(245,158,11,0.06)' }}>
                                    <div style={{ fontSize: '1.4em', fontWeight: 900, color: '#F59E0B' }}>${health.cost_estimate.total_per_account}</div>
                                    <div style={{ fontSize: '0.62em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Per Account</div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: 8, fontSize: '0.75em' }}>
                                <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between', padding: '4px 8px', borderRadius: 4, background: 'rgba(255,255,255,0.03)' }}>
                                    <span style={{ color: 'var(--text-muted)' }}>50 accounts</span>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>${health.cost_estimate.estimated_cost_for_50}</span>
                                </div>
                                <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between', padding: '4px 8px', borderRadius: 4, background: 'rgba(255,255,255,0.03)' }}>
                                    <span style={{ color: 'var(--text-muted)' }}>100 accounts</span>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>${health.cost_estimate.estimated_cost_for_100}</span>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '20px 0' }}>
                            📊 Оценка стоимости загружается...
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ CAMPAIGN DELIVERY STATS ═══ */}
            {campaignStats && campaignStats.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Send size={14} style={{ color: '#06B6D4' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Campaign Delivery</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
                        {campaignStats.slice(0, 6).map((c, i) => {
                            const inboxRate = c.total_sent > 0 ? Math.round(((c.total_sent - (c.total_errors || 0)) / c.total_sent) * 100) : 0;
                            return (
                                <div key={i} className="card" style={{ padding: '14px 16px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                        <span style={{ fontSize: '0.78em', fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>
                                            {c.campaign_name || `Campaign #${c.campaign_id}`}
                                        </span>
                                        <span style={{
                                            fontSize: '0.72em', fontWeight: 800,
                                            color: inboxRate >= 80 ? '#10B981' : inboxRate >= 50 ? '#F59E0B' : '#EF4444',
                                        }}>
                                            {inboxRate}% inbox
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6 }}>
                                        <div style={{ flex: 1, textAlign: 'center', padding: '6px 4px', borderRadius: 4, background: 'rgba(6,182,212,0.06)' }}>
                                            <div style={{ fontSize: '1.1em', fontWeight: 800, color: '#06B6D4' }}>{c.total_sent || 0}</div>
                                            <div style={{ fontSize: '0.6em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Sent</div>
                                        </div>
                                        <div style={{ flex: 1, textAlign: 'center', padding: '6px 4px', borderRadius: 4, background: 'rgba(239,68,68,0.06)' }}>
                                            <div style={{ fontSize: '1.1em', fontWeight: 800, color: '#EF4444' }}>{c.total_errors || 0}</div>
                                            <div style={{ fontSize: '0.6em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Errors</div>
                                        </div>
                                        <div style={{ flex: 1, textAlign: 'center', padding: '6px 4px', borderRadius: 4, background: 'rgba(16,185,129,0.06)' }}>
                                            <div style={{ fontSize: '1.1em', fontWeight: 800, color: '#10B981' }}>{c.accounts_used || 0}</div>
                                            <div style={{ fontSize: '0.6em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Accounts</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ═══ AUTOREG ANALYTICS ═══ */}
            {analytics && (
                <div style={{ marginTop: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Autoreg Analytics</span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>

                        {/* Provider Success Rates (7d) */}
                        <div className="card" style={{ padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                                <CheckCircle size={14} style={{ color: '#10B981' }} />
                                <span style={{ fontSize: '0.82em', fontWeight: 700, color: 'var(--text-primary)' }}>Success Rate (7d)</span>
                            </div>
                            {(() => {
                                const rates = analytics.provider_success_rates?.['7d'] || {};
                                const entries = Object.entries(rates).sort((a, b) => b[1].total - a[1].total);
                                if (!entries.length) return <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '16px 0' }}>No data</div>;
                                return entries.map(([prov, d]) => (
                                    <div key={prov} style={{ marginBottom: 10 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                            <span style={{ fontSize: '0.82em', fontWeight: 600, color: 'var(--text-primary)', textTransform: 'capitalize' }}>{prov}</span>
                                            <span style={{ fontSize: '0.78em', fontWeight: 700, color: d.rate >= 50 ? '#10B981' : d.rate >= 25 ? '#F59E0B' : '#EF4444' }}>
                                                {d.rate}% <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>({d.success}/{d.total})</span>
                                            </span>
                                        </div>
                                        <div style={{ height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.04)', overflow: 'hidden' }}>
                                            <div style={{
                                                height: '100%', borderRadius: 3, width: `${d.rate}%`,
                                                background: d.rate >= 50 ? 'linear-gradient(90deg, #10B981, #059669)' : d.rate >= 25 ? 'linear-gradient(90deg, #F59E0B, #D97706)' : 'linear-gradient(90deg, #EF4444, #DC2626)',
                                                transition: 'width 0.8s ease',
                                            }} />
                                        </div>
                                    </div>
                                ));
                            })()}
                        </div>

                        {/* Top Failure Reasons */}
                        <div className="card" style={{ padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                                <AlertTriangle size={14} style={{ color: '#EF4444' }} />
                                <span style={{ fontSize: '0.82em', fontWeight: 700, color: 'var(--text-primary)' }}>Top Failures</span>
                            </div>
                            {analytics.top_failures?.length > 0 ? (
                                analytics.top_failures.slice(0, 6).map((f, i) => (
                                    <div key={i} style={{
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)',
                                    }}>
                                        <span style={{ fontSize: '0.8em', color: 'var(--text-secondary)' }}>{f.reason}</span>
                                        <span style={{ fontSize: '0.82em', fontWeight: 700, color: '#EF4444', fontFamily: 'JetBrains Mono, monospace' }}>{f.count}</span>
                                    </div>
                                ))
                            ) : (
                                <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '16px 0' }}>No failures recorded</div>
                            )}
                        </div>

                        {/* Account Lifetime */}
                        <div className="card" style={{ padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                                <Clock size={14} style={{ color: '#8B5CF6' }} />
                                <span style={{ fontSize: '0.82em', fontWeight: 700, color: 'var(--text-primary)' }}>Account Lifetime</span>
                            </div>
                            {analytics.lifetime ? (
                                <>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                                        <div style={{ textAlign: 'center', padding: 8, borderRadius: 6, background: 'rgba(16,185,129,0.06)' }}>
                                            <div style={{ fontSize: '1.4em', fontWeight: 900, color: '#10B981' }}>{analytics.lifetime.avg_alive_age_days}d</div>
                                            <div style={{ fontSize: '0.68em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Avg Alive Age</div>
                                        </div>
                                        <div style={{ textAlign: 'center', padding: 8, borderRadius: 6, background: 'rgba(239,68,68,0.06)' }}>
                                            <div style={{ fontSize: '1.4em', fontWeight: 900, color: '#EF4444' }}>{analytics.lifetime.avg_dead_age_days}d</div>
                                            <div style={{ fontSize: '0.68em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Avg Dead Age</div>
                                        </div>
                                    </div>
                                    <div style={{ fontSize: '0.75em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 1 }}>Survival Rates</div>
                                    {Object.entries(analytics.lifetime.survival_rates || {}).map(([period, rate]) => (
                                        <div key={period} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                            <span style={{ fontSize: '0.8em', fontWeight: 600, color: 'var(--text-secondary)', width: 30 }}>{period}</span>
                                            <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.04)', overflow: 'hidden' }}>
                                                <div style={{
                                                    height: '100%', borderRadius: 3, width: `${rate}%`,
                                                    background: 'linear-gradient(90deg, #8B5CF6, #6D28D9)',
                                                    transition: 'width 0.8s ease',
                                                }} />
                                            </div>
                                            <span style={{ fontSize: '0.78em', fontWeight: 700, color: '#8B5CF6', width: 40, textAlign: 'right' }}>{rate}%</span>
                                        </div>
                                    ))}
                                </>
                            ) : (
                                <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', textAlign: 'center', padding: '16px 0' }}>No data</div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
