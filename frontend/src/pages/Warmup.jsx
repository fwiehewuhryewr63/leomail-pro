import React, { useState, useEffect, useCallback } from 'react';
import {
    Flame, Play, Square, RefreshCw, Activity, ChevronDown
} from 'lucide-react';
import { API } from '../api';

/* ── Phase definitions ── */
const PHASES = [
    { id: 1, label: 'Phase 1', emails: '1-3 emails/day', min: 1, max: 3, color: '#4ecdc4', defaultDays: 3 },
    { id: 2, label: 'Phase 2', emails: '5-10 emails/day', min: 5, max: 10, color: '#45b7d1', defaultDays: 4 },
    { id: 3, label: 'Phase 3', emails: '10-20 emails/day', min: 10, max: 20, color: '#f7dc6f', defaultDays: 7 },
    { id: 4, label: 'Phase 4', emails: '20-50 emails/day', min: 20, max: 50, color: '#f39c12', defaultDays: 7 },
    { id: 5, label: 'Phase 5', emails: '50-100 emails/day', min: 50, max: 100, color: '#e74c3c', defaultDays: 9 },
];

const labelStyle = {
    fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)',
    letterSpacing: 1, textTransform: 'uppercase', marginBottom: 6, display: 'block',
};

export default function Warmup() {
    /* ── Config state ── */
    const [farms, setFarms] = useState([]);
    const [selectedFarms, setSelectedFarms] = useState([]);
    const [farmsOpen, setFarmsOpen] = useState(false);
    const [phase, setPhase] = useState(1);
    const [days, setDays] = useState(3);
    const [threads, setThreads] = useState(3);
    const [templates, setTemplates] = useState([]);
    const [selectedTemplates, setSelectedTemplates] = useState([]);
    const [templatesOpen, setTemplatesOpen] = useState(false);
    const [links, setLinks] = useState([]);
    const [selectedLinks, setSelectedLinks] = useState([]);
    const [linksOpen, setLinksOpen] = useState(false);

    /* ── Runtime state ── */
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(false);

    const isRunning = status?.running;
    const stats = status?.stats || {};
    const phases = status?.phases || {};
    const topAccounts = status?.top_accounts || [];

    /* ── Fetch data ── */
    const fetchAll = useCallback(async () => {
        try {
            const [statusRes, farmsRes, tplRes] = await Promise.all([
                fetch(`${API}/warmup/status`),
                fetch(`${API}/farms`),
                fetch(`${API}/templates`),
            ]);
            if (statusRes.ok) setStatus(await statusRes.json());
            if (farmsRes.ok) {
                const d = await farmsRes.json();
                setFarms(Array.isArray(d) ? d : d.farms || []);
            }
            if (tplRes.ok) {
                const d = await tplRes.json();
                setTemplates(Array.isArray(d) ? d : d.templates || []);
            }
        } catch (e) { console.error('Warmup fetch:', e); }
    }, []);

    useEffect(() => {
        fetchAll();
        const iv = setInterval(fetchAll, 5000);
        return () => clearInterval(iv);
    }, [fetchAll]);

    /* ── Update days when phase changes ── */
    useEffect(() => {
        const p = PHASES.find(p => p.id === phase);
        if (p) setDays(p.defaultDays);
    }, [phase]);

    /* ── Actions ── */
    const startWarmup = async () => {
        setLoading(true);
        try {
            await fetch(`${API}/warmup/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    farm_ids: selectedFarms,
                    threads,
                    phase,
                    days,
                    template_ids: selectedTemplates,
                    link_ids: selectedLinks,
                }),
            });
            setTimeout(fetchAll, 1000);
        } catch (e) { console.error('Start warmup:', e); }
        setLoading(false);
    };

    const stopWarmup = async () => {
        try {
            await fetch(`${API}/warmup/stop`, { method: 'POST' });
            setTimeout(fetchAll, 1000);
        } catch (e) { console.error('Stop warmup:', e); }
    };

    const selectedPhase = PHASES.find(p => p.id === phase);
    const avgEmails = selectedPhase ? Math.round((selectedPhase.min + selectedPhase.max) / 2) : 1;
    const delayHours = avgEmails > 0 ? (24 / avgEmails) : 24;

    /* ── Phase bar data ── */
    const totalPhaseAccs = Object.values(phases).reduce((a, b) => a + b, 0);

    return (
        <div className="page">
            {/* Header */}
            <div style={{ fontSize: '0.6em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>OPERATIONS / WARM-UP</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Flame size={22} /> Warm-up Engine
                    {isRunning && <span style={{
                        fontSize: '0.45em', fontWeight: 700, padding: '3px 10px', borderRadius: 12,
                        background: 'rgba(16,185,129,0.15)', color: '#10B981', border: '1px solid rgba(16,185,129,0.3)',
                        marginLeft: 8, animation: 'pulse 1.5s infinite',
                    }}>● ACTIVE</span>}
                </h2>
            </div>

            {/* ═══════════════ Config Card ═══════════════ */}
            <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 14 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }} />
                    Configuration
                </div>

                {/* ── Row 1: Farms + Phase ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 14, marginBottom: 14 }}>
                    {/* Farms multi-select */}
                    <div>
                        <label style={labelStyle}>Farms</label>
                        <div className="form-input" onClick={() => setFarmsOpen(!farmsOpen)}
                            style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px' }}>
                            <span>{selectedFarms.length > 0 ? `${selectedFarms.length} selected` : 'All farms (default)'}</span>
                            <ChevronDown size={16} style={{ color: 'var(--text-muted)', transform: farmsOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                        </div>
                        {farmsOpen && (
                            <div style={{
                                marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 8, maxHeight: 180, overflowY: 'auto', padding: 6,
                            }}>
                                {farms.length === 0 ? (
                                    <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', padding: 8 }}>No farms — create in Autoreg</div>
                                ) : farms.map(f => (
                                    <div key={f.id} onClick={() => setSelectedFarms(prev =>
                                        prev.includes(f.id) ? prev.filter(x => x !== f.id) : [...prev, f.id]
                                    )} style={{
                                        padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.85em',
                                        background: selectedFarms.includes(f.id) ? 'rgba(16,185,129,0.12)' : 'transparent',
                                        color: selectedFarms.includes(f.id) ? 'var(--accent)' : 'var(--text-secondary)',
                                        fontWeight: selectedFarms.includes(f.id) ? 600 : 400,
                                        display: 'flex', justifyContent: 'space-between',
                                    }}>
                                        <span>{f.name}</span>
                                        <span style={{ opacity: 0.5 }}>{f.account_count || 0} acc</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Phase selector */}
                    <div>
                        <label style={labelStyle}>Phase</label>
                        <select className="form-input" value={phase} onChange={e => setPhase(parseInt(e.target.value))}
                            style={{ fontSize: '1.05em', padding: '10px 14px', cursor: 'pointer' }}
                            disabled={isRunning}>
                            {PHASES.map(p => (
                                <option key={p.id} value={p.id}>{p.label} ({p.emails})</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* ── Row 2: Days + Threads + Templates + Links ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 14, marginBottom: 14 }}>
                    <div>
                        <label style={labelStyle}>Days</label>
                        <input className="form-input" type="text" inputMode="numeric" value={days}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setDays(v === '' ? '' : v); }}
                            onBlur={e => setDays(Math.max(1, parseInt(e.target.value) || 1))}
                            disabled={isRunning} />
                    </div>
                    <div>
                        <label style={labelStyle}>Threads</label>
                        <input className="form-input" type="text" inputMode="numeric" value={threads}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setThreads(v === '' ? '' : v); }}
                            onBlur={e => setThreads(Math.min(20, Math.max(1, parseInt(e.target.value) || 1)))}
                            disabled={isRunning} />
                    </div>
                    <div>
                        <label style={labelStyle}>Templates</label>
                        <div className="form-input" onClick={() => setTemplatesOpen(!templatesOpen)}
                            style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px' }}>
                            <span style={{ fontSize: '0.95em' }}>{selectedTemplates.length > 0 ? `${selectedTemplates.length} selected` : 'Built-in'}</span>
                            <ChevronDown size={14} style={{ color: 'var(--text-muted)', transform: templatesOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                        </div>
                        {templatesOpen && (
                            <div style={{
                                marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 8, maxHeight: 180, overflowY: 'auto', padding: 6, position: 'relative', zIndex: 10,
                            }}>
                                {templates.length === 0 ? (
                                    <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', padding: 8 }}>No templates — using built-in</div>
                                ) : templates.map(t => (
                                    <div key={t.id} onClick={() => setSelectedTemplates(prev =>
                                        prev.includes(t.id) ? prev.filter(x => x !== t.id) : [...prev, t.id]
                                    )} style={{
                                        padding: '5px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em',
                                        background: selectedTemplates.includes(t.id) ? 'rgba(16,185,129,0.12)' : 'transparent',
                                        color: selectedTemplates.includes(t.id) ? 'var(--accent)' : 'var(--text-secondary)',
                                        fontWeight: selectedTemplates.includes(t.id) ? 600 : 400,
                                    }}>
                                        {t.name || t.subject || `Template #${t.id}`}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <div>
                        <label style={labelStyle}>Links <span style={{ opacity: 0.5, fontWeight: 400, textTransform: 'none' }}>(optional)</span></label>
                        <div className="form-input" onClick={() => setLinksOpen(!linksOpen)}
                            style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px' }}>
                            <span style={{ fontSize: '0.95em' }}>{selectedLinks.length > 0 ? `${selectedLinks.length} selected` : 'None'}</span>
                            <ChevronDown size={14} style={{ color: 'var(--text-muted)', transform: linksOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                        </div>
                        {linksOpen && (
                            <div style={{
                                marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 8, maxHeight: 180, overflowY: 'auto', padding: 6, position: 'relative', zIndex: 10,
                            }}>
                                {links.length === 0 ? (
                                    <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', padding: 8 }}>No links uploaded</div>
                                ) : links.map(l => (
                                    <div key={l.id} onClick={() => setSelectedLinks(prev =>
                                        prev.includes(l.id) ? prev.filter(x => x !== l.id) : [...prev, l.id]
                                    )} style={{
                                        padding: '5px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em',
                                        background: selectedLinks.includes(l.id) ? 'rgba(16,185,129,0.12)' : 'transparent',
                                        color: selectedLinks.includes(l.id) ? 'var(--accent)' : 'var(--text-secondary)',
                                        fontWeight: selectedLinks.includes(l.id) ? 600 : 400,
                                    }}>
                                        {l.url || l.name || `Link #${l.id}`}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Phase info ── */}
                {selectedPhase && (
                    <div style={{
                        padding: '10px 14px', marginBottom: 16, borderRadius: 8,
                        background: `${selectedPhase.color}0A`, border: `1px solid ${selectedPhase.color}20`,
                        fontSize: '0.82em', color: 'var(--text-secondary)', lineHeight: 1.5,
                    }}>
                        <span style={{ color: selectedPhase.color, fontWeight: 700 }}>{selectedPhase.label}</span>
                        {' '} {selectedPhase.emails} · Delay: ~{delayHours.toFixed(1)}h between sends (±15% random jitter) · Peer-to-peer (send + reply) · Duration: {days} day{days > 1 ? 's' : ''}
                    </div>
                )}

                {/* ── Buttons: START / STOP ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <button onClick={startWarmup} disabled={isRunning || loading}
                        style={{
                            padding: '14px 24px', fontSize: '1em', fontWeight: 800, cursor: isRunning ? 'not-allowed' : 'pointer',
                            background: isRunning ? 'rgba(16,185,129,0.15)' : 'var(--accent)', color: isRunning ? 'var(--accent)' : '#000',
                            border: 'none', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>
                        <Play size={18} /> {loading ? 'Starting...' : 'START'}
                    </button>
                    <button onClick={stopWarmup} disabled={!isRunning}
                        style={{
                            padding: '14px 24px', fontSize: '1em', fontWeight: 800, cursor: !isRunning ? 'not-allowed' : 'pointer',
                            background: !isRunning ? 'rgba(239,68,68,0.08)' : 'rgba(239,68,68,0.15)',
                            color: !isRunning ? 'rgba(239,68,68,0.3)' : '#ef4444',
                            border: `1px solid ${!isRunning ? 'rgba(239,68,68,0.1)' : 'rgba(239,68,68,0.3)'}`,
                            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>
                        <Square size={16} /> STOP
                    </button>
                </div>
            </div>

            {/* ═══════════════ Live Status ═══════════════ */}
            {isRunning && (
                <div className="card" style={{
                    padding: '14px 20px', marginBottom: 16,
                    background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                            width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)',
                            animation: 'pulse 1.5s infinite',
                        }} />
                        <span style={{ fontWeight: 700, color: 'var(--accent)' }}>Warming...</span>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.88em' }}>
                            Sent: {stats.total_sent || 0} | Received: {stats.total_received || 0} | Errors: {stats.total_errors || 0} | Processed: {stats.accounts_processed || 0}
                        </span>
                        <button onClick={fetchAll} style={{
                            marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)',
                            cursor: 'pointer', padding: 4,
                        }}>
                            <RefreshCw size={14} />
                        </button>
                    </div>
                </div>
            )}

            {/* ═══════════════ Phase Distribution ═══════════════ */}
            {totalPhaseAccs > 0 && (
                <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#06B6D4' }} />
                        Phase Distribution
                    </div>

                    {/* Stacked bar */}
                    <div style={{ display: 'flex', height: 36, borderRadius: 8, overflow: 'hidden', marginBottom: 12 }}>
                        {PHASES.map(p => {
                            const key = `phase_${p.id}`;
                            const count = phases[key] || 0;
                            const pct = totalPhaseAccs > 0 ? (count / totalPhaseAccs * 100) : 0;
                            if (pct === 0) return null;
                            return (
                                <div key={key} style={{
                                    width: `${pct}%`, background: p.color,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: '0.75em', fontWeight: 800, color: '#000', minWidth: 24,
                                }} title={`${p.label}: ${count}`}>
                                    {count}
                                </div>
                            );
                        })}
                        {(phases.warmed || 0) > 0 && (
                            <div style={{
                                width: `${(phases.warmed / totalPhaseAccs * 100)}%`, background: '#10B981',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '0.75em', fontWeight: 800, color: '#000', minWidth: 24,
                            }} title={`Warmed: ${phases.warmed}`}>
                                {phases.warmed}
                            </div>
                        )}
                    </div>

                    {/* Legend */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', fontSize: '0.82em' }}>
                        {PHASES.map(p => {
                            const count = phases[`phase_${p.id}`] || 0;
                            return (
                                <span key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <span style={{ width: 10, height: 10, borderRadius: 3, background: p.color }} />
                                    {p.label}: <strong>{count}</strong>
                                </span>
                            );
                        })}
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 10, height: 10, borderRadius: 3, background: '#10B981' }} />
                            Warmed: <strong>{phases.warmed || 0}</strong>
                        </span>
                    </div>
                </div>
            )}

            {/* ═══════════════ Accounts Table ═══════════════ */}
            {topAccounts.length > 0 && (
                <div className="card" style={{ padding: '20px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#F59E0B' }} />
                        Accounts in Warm-up ({topAccounts.length})
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', fontSize: '0.85em', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border-default)' }}>
                                    <th style={{ textAlign: 'left', padding: '8px 10px', fontWeight: 600 }}>Email</th>
                                    <th style={{ textAlign: 'center', padding: '8px 10px', fontWeight: 600 }}>Phase</th>
                                    <th style={{ textAlign: 'right', padding: '8px 10px', fontWeight: 600 }}>Today</th>
                                    <th style={{ textAlign: 'right', padding: '8px 10px', fontWeight: 600 }}>Total</th>
                                    <th style={{ textAlign: 'right', padding: '8px 10px', fontWeight: 600 }}>Health</th>
                                </tr>
                            </thead>
                            <tbody>
                                {topAccounts.map(acc => {
                                    const ph = PHASES.find(p => `phase_${p.id}` === acc.status);
                                    const phColor = ph ? ph.color : (acc.status === 'warmed' ? '#10B981' : '#888');
                                    const phLabel = ph ? ph.label : (acc.status === 'warmed' ? 'Warmed ✅' : 'New');
                                    const hp = acc.health_score ?? 100;
                                    return (
                                        <tr key={acc.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                                            <td style={{ padding: '8px 10px', borderLeft: `3px solid ${phColor}`, paddingLeft: 14 }}>
                                                {acc.email}
                                            </td>
                                            <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                                <span style={{
                                                    padding: '3px 10px', borderRadius: 6, fontSize: '0.85em', fontWeight: 600,
                                                    background: `${phColor}18`, color: phColor,
                                                }}>
                                                    {phLabel}
                                                </span>
                                            </td>
                                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600 }}>{acc.emails_sent_today || 0}</td>
                                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600 }}>{acc.total_emails_sent || 0}</td>
                                            <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                                                <span style={{
                                                    fontWeight: 700,
                                                    color: hp >= 80 ? '#10B981' : hp >= 50 ? '#f39c12' : '#ef4444',
                                                }}>
                                                    {hp}%
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ═══════════════ Empty state ═══════════════ */}
            {topAccounts.length === 0 && totalPhaseAccs === 0 && !isRunning && (
                <div className="card" style={{ padding: '40px 24px', textAlign: 'center' }}>
                    <Flame size={40} style={{ color: 'var(--text-muted)', opacity: 0.3, marginBottom: 12 }} />
                    <div style={{ fontSize: '0.95em', color: 'var(--text-muted)', marginBottom: 4 }}>No warm-up activity</div>
                    <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', opacity: 0.6 }}>Select farms and start warming to build sender reputation</div>
                </div>
            )}
        </div>
    );
}
