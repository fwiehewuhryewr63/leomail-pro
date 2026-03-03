import React, { useState, useEffect } from 'react';
import {
    LayoutDashboard, CheckCircle, Users, Shield, Mail, Database, FileText, Link2, Package, Layers
} from 'lucide-react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';

/* ── SVG mini sparkline ── */
function Sparkline({ data = [], color = '#10B981', height = 30 }) {
    if (!data.length) data = [0, 0, 0, 0, 0, 0, 0];
    const max = Math.max(...data, 1);
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * 100},${100 - (v / max) * 80}`).join(' ');
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

/* ── 7-Day Activity Area Chart ── */
function AreaChart({ data = [], labels = [], height = 180 }) {
    if (!data.length) data = [0, 0, 0, 0, 0, 0, 0];
    if (!labels.length) labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const max = Math.max(...data, 1);
    const w = 600, h = 180, pad = 36;
    const pts = data.map((v, i) => ({
        x: pad + (i / (data.length - 1)) * (w - pad * 2),
        y: pad + (1 - v / max) * (h - pad * 2),
    }));
    const line = pts.map(p => `${p.x},${p.y}`).join(' ');
    const area = `${pad},${h - pad} ${line} ${w - pad},${h - pad}`;
    const gridFracs = [1, 0.75, 0.5, 0.25, 0];
    const gridLines = gridFracs.map(f => pad + (1 - f) * (h - pad * 2));

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
                <text key={i} x={p.x} y={h - 8} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize="10" fontFamily="Inter" fontWeight="600">
                    {labels[i]}
                </text>
            ))}
            <polygon points={area} fill="url(#areaFill)" />
            <polyline fill="none" stroke="#10B981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={line} />
            {pts.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r="3" fill="#10B981" stroke="#0a0a0f" strokeWidth="2" />
            ))}
        </svg>
    );
}

export default function Dashboard() {
    const [s, setS] = useState({});
    const [health, setHealth] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);

    const load = () => {
        fetch(`${API}/dashboard/stats`)
            .then(r => r.json())
            .then(d => { setS(d); setLastUpdate(new Date()); })
            .catch(() => { });
        fetch(`${API}/health/resources`)
            .then(r => r.ok ? r.json() : null)
            .then(d => d && setHealth(d))
            .catch(() => { });
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
        { id: 'gmail', name: 'Gmail', color: '#EA4335' },
        { id: 'yahoo', name: 'Yahoo', color: '#6001D2' },
        { id: 'outlook', name: 'Outlook', color: '#0078D4' },
        { id: 'protonmail', name: 'ProtonMail', color: '#6D4AFF' },
        { id: 'aol', name: 'AOL', color: '#FF6B00' },
        { id: 'hotmail', name: 'Hotmail', color: '#0078D4' },
    ];
    const providerDist = providers.map(p => ({
        ...p,
        count: byProvider[p.id] || 0,
        pct: totalAccs > 0 ? Math.round(((byProvider[p.id] || 0) / totalAccs) * 100) : 0,
    })).filter(p => p.count > 0).sort((a, b) => b.count - a.count);

    const weekData = s.week_activity || [120, 280, 340, 180, 420, 310, 250];
    const weekLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const sparkAccounts = s.accounts_spark || [3, 5, 8, 12, 10, 14, 18];
    const sparkSent = s.sent_spark || [100, 150, 200, 180, 220, 300, 250];

    /* Resource status */
    const resources = [
        { name: 'Names', icon: <Users size={13} />, count: health?.names?.total || s.total_names || 0, color: '#10B981' },
        { name: 'Links', icon: <Link2 size={13} />, count: health?.links?.total || s.total_links || 0, color: '#3B82F6' },
        { name: 'Templates', icon: <FileText size={13} />, count: health?.templates?.total || s.total_templates || 0, color: '#F59E0B' },
        { name: 'Databases', icon: <Database size={13} />, count: health?.databases?.total || s.total_databases || 0, color: '#8B5CF6' },
        { name: 'Farms', icon: <Layers size={13} />, count: health?.farms?.total || s.total_farms || 0, color: '#06B6D4' },
    ];

    const timeAgo = lastUpdate ? (() => {
        const diff = Math.floor((Date.now() - lastUpdate.getTime()) / 1000);
        if (diff < 5) return 'just now';
        if (diff < 60) return `${diff}s ago`;
        return `${Math.floor(diff / 60)}m ago`;
    })() : '—';

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div style={{ fontSize: '0.6em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>OVERVIEW / DASHBOARD</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <LayoutDashboard size={22} /> Dashboard
                </h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75em', color: 'var(--text-muted)' }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 8px rgba(16,185,129,0.6)' }} />
                    Updated {timeAgo}
                </div>
            </div>

            {/* ═══ 5 STAT CARDS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 16 }}>
                {/* ACCOUNTS */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #10B981' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#10B981', lineHeight: 1 }}>
                                {(totalAccs || 0).toLocaleString()}
                            </div>
                            <div style={{ fontSize: '0.62em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>ACCOUNTS</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={sparkAccounts} color="#10B981" /></div>
                    </div>
                </div>

                {/* PROXIES */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #10B981' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ lineHeight: 1 }}>
                                <span style={{ fontSize: '1.8em', fontWeight: 900, color: '#10B981' }}>{proxyAlive}</span>
                                <span style={{ fontSize: '0.9em', fontWeight: 500, color: 'var(--text-muted)' }}>/{proxyTotal}</span>
                            </div>
                            <div style={{ fontSize: '0.62em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>PROXIES</div>
                        </div>
                        <CircleProgress value={proxyAlive} max={proxyTotal} size={48} />
                    </div>
                </div>

                {/* SENT TODAY */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #06B6D4' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#06B6D4', lineHeight: 1 }}>
                                {(ms.total_sent || 0).toLocaleString()}
                            </div>
                            <div style={{ fontSize: '0.62em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>SENT TODAY</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={sparkSent} color="#06B6D4" /></div>
                    </div>
                </div>

                {/* INBOX RATE */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #22C55E' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#22C55E', lineHeight: 1 }}>
                                {ms.inbox_rate || 0}%
                            </div>
                            <div style={{ fontSize: '0.62em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>INBOX RATE</div>
                        </div>
                        <CheckCircle size={24} style={{ color: '#22C55E', opacity: 0.5, flexShrink: 0 }} />
                    </div>
                </div>

                {/* ACTIVE TASKS */}
                <div className="card" style={{ padding: '14px 16px', borderLeft: '3px solid #8B5CF6' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div style={{ fontSize: '1.8em', fontWeight: 900, color: '#8B5CF6', lineHeight: 1 }}>
                                {s.active_tasks || 0}
                            </div>
                            <div style={{ fontSize: '0.62em', fontWeight: 700, letterSpacing: 1.5, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 4 }}>ACTIVE TASKS</div>
                        </div>
                        <div style={{ width: 50 }}><Sparkline data={[1, 2, 3, 2, 3, 4, 3]} color="#8B5CF6" /></div>
                    </div>
                </div>
            </div>

            {/* ═══ MIDDLE ROW: Chart + Providers ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                {/* 7-Day Activity */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Mail size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>7-Day Activity</span>
                        <span style={{ fontSize: '0.68em', color: 'var(--text-muted)', marginLeft: 'auto' }}>emails sent</span>
                    </div>
                    <AreaChart data={weekData} labels={weekLabels} height={180} />
                </div>

                {/* Provider Distribution */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Package size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Provider Distribution</span>
                        <span style={{ fontSize: '0.68em', color: 'var(--text-muted)', marginLeft: 'auto' }}>{totalAccs} total</span>
                    </div>
                    {providerDist.length > 0 ? (
                        providerDist.map(p => (
                            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                                <ProviderLogo provider={p.id} size={22} />
                                <span style={{ fontSize: '0.82em', fontWeight: 600, width: 90, color: 'var(--text-primary)' }}>{p.name}</span>
                                <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.04)', overflow: 'hidden' }}>
                                    <div style={{
                                        height: '100%', borderRadius: 3, width: `${p.pct}%`,
                                        background: `linear-gradient(90deg, ${p.color}, ${p.color}88)`,
                                        transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
                                    }} />
                                </div>
                                <span style={{ fontSize: '0.78em', fontWeight: 700, width: 44, textAlign: 'right', color: p.color }}>{p.count}</span>
                                <span style={{ fontSize: '0.72em', fontWeight: 600, width: 30, textAlign: 'right', color: 'var(--text-muted)' }}>{p.pct}%</span>
                            </div>
                        ))
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', padding: '24px 0', textAlign: 'center' }}>
                            No accounts registered
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ BOTTOM ROW: Resources + Activity ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {/* Resource Status */}
                <div className="card" style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                        <Shield size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>Resource Status</span>
                    </div>
                    {resources.map(r => (
                        <div key={r.name} style={{
                            display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
                            borderBottom: '1px solid rgba(255,255,255,0.03)',
                        }}>
                            <div style={{
                                width: 28, height: 28, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: `${r.color}12`, color: r.color,
                            }}>{r.icon}</div>
                            <span style={{ fontSize: '0.85em', fontWeight: 600, flex: 1, color: 'var(--text-primary)' }}>{r.name}</span>
                            <span style={{ fontSize: '0.9em', fontWeight: 800, color: r.color }}>{r.count.toLocaleString()}</span>
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
                            {s.recent_activity.slice(0, 8).map((a, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.78em' }}>
                                    <span style={{
                                        width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                                        background: a.type === 'success' ? '#22C55E' : a.type === 'error' ? '#EF4444' : '#3B82F6',
                                    }} />
                                    <span style={{ color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.88em', flexShrink: 0, width: 48 }}>
                                        {a.time || '—'}
                                    </span>
                                    <span style={{ color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {a.message || '—'}
                                    </span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.82em', padding: '24px 0', textAlign: 'center' }}>
                            No recent activity
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
