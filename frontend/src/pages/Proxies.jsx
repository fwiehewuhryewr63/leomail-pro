import React, { useState, useEffect, useRef } from 'react';
import { Shield, Upload, Trash2, RefreshCw, CheckCircle, XCircle, Clock, WifiOff, Edit3, Unlink, Save, X, Zap, Link2 } from 'lucide-react';
import { API } from '../api';

export default function Proxies() {
    const [proxies, setProxies] = useState([]);
    const [stats, setStats] = useState({});
    const [filter, setFilter] = useState(null);
    const [showUpload, setShowUpload] = useState(false);
    const [uploadText, setUploadText] = useState('');
    const [expiresAt, setExpiresAt] = useState('');
    const [loading, setLoading] = useState(false);
    const [checking, setChecking] = useState(false);
    const [checkingId, setCheckingId] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [editData, setEditData] = useState({});
    const [selected, setSelected] = useState(new Set());
    const [showFormats, setShowFormats] = useState(false);
    const fileRef = useRef();

    const total = stats.total || 0;
    const alive = stats.active || 0;
    const dead = stats.dead || 0;
    const exhausted = stats.exhausted || 0;

    const filteredProxies = filter ? proxies.filter(p => {
        if (filter === 'active') return p.status === 'active' && !p.bound_to;
        if (filter === 'exhausted') return p.status === 'exhausted';
        if (filter === 'dead') return ['dead', 'expired', 'banned'].includes(p.status);
        return true;
    }) : proxies;

    const loadProxies = () => {
        fetch(`${API}/proxies/`).then(r => r.json()).then(setProxies).catch(() => { /* ignore */ });
        fetch(`${API}/proxies/stats`).then(r => r.json()).then(setStats).catch(() => { /* ignore */ });
    };
    useEffect(() => { loadProxies(); }, []);

    const parseProxyLines = (text) => text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));

    const handleUpload = async () => {
        const lines = parseProxyLines(uploadText);
        if (lines.length === 0) return;
        setLoading(true);
        try {
            const res = await fetch(`${API}/proxies/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proxies: lines, expires_at: expiresAt || null })
            });
            const data = await res.json();
            if (data.types) {
                alert(`Imported: ${data.imported}\nSOCKS5: ${data.types.socks5 || 0}\nHTTP: ${data.types.http || 0}\nMOBILE: ${data.types.mobile || 0}`);
            }
            setUploadText(''); setShowUpload(false); loadProxies();
        } catch { /* ignore */ }
        setLoading(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (ev) => { setUploadText(ev.target.result); setShowUpload(true); };
            reader.readAsText(file);
        }
    };

    const handleFile = (e) => {
        const file = e.target?.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => { setUploadText(ev.target.result); setShowUpload(true); };
        reader.readAsText(file);
    };

    const checkAll = async () => {
        setChecking(true);
        try { await fetch(`${API}/proxies/check-all`, { method: 'POST' }); } catch { /* ignore */ }
        setChecking(false); loadProxies();
    };

    const checkOne = async (id) => {
        setCheckingId(id);
        try { await fetch(`${API}/proxies/check/${id}`, { method: 'POST' }); } catch { /* ignore */ }
        setCheckingId(null); loadProxies();
    };

    const deleteProxy = async (id) => { await fetch(`${API}/proxies/${id}`, { method: 'DELETE' }); selected.delete(id); setSelected(new Set(selected)); loadProxies(); };
    const _deleteAll = async () => { if (!confirm('Delete ALL proxies?')) return; await fetch(`${API}/proxies/all`, { method: 'DELETE' }); setSelected(new Set()); loadProxies(); };
    const _unbindProxy = async (id) => { await fetch(`${API}/proxies/${id}/unbind`, { method: 'POST' }); loadProxies(); };

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === filteredProxies.length ? new Set() : new Set(filteredProxies.map(p => p.id)));
    const batchDelete = async () => {
        if (!confirm(`Delete ${selected.size} proxies?`)) return;
        for (const id of selected) { await fetch(`${API}/proxies/${id}`, { method: 'DELETE' }); }
        setSelected(new Set()); loadProxies();
    };

    const resetAll = async () => {
        if (!confirm('Reset ALL counters?')) return;
        const res = await fetch(`${API}/proxies/reset-all`, { method: 'POST' });
        const d = await res.json();
        alert(`Reset ${d.reset} proxies`);
        loadProxies();
    };

    const startEdit = (proxy) => {
        setEditingId(proxy.id);
        setEditData({ host: proxy.host || '', port: proxy.port || '', username: proxy.username || '', password: '' });
    };

    const saveEdit = async (id) => {
        try {
            await fetch(`${API}/proxies/${id}/refresh`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host: editData.host || null, port: editData.port ? parseInt(editData.port) : null, username: editData.username ?? null, password: editData.password || null })
            });
        } catch { /* ignore */ }
        setEditingId(null); setEditData({}); loadProxies();
    };

    /* ── Usage cell color based on count ── */
    const usageCell = (count) => {
        const c = count || 0;
        let bg = 'transparent';
        let color = 'var(--text-muted)';
        if (c >= 4) { bg = 'rgba(239,68,68,0.15)'; color = '#EF4444'; }
        else if (c >= 3) { bg = 'rgba(245,158,11,0.15)'; color = '#F59E0B'; }
        else if (c >= 1) { bg = 'rgba(16,185,129,0.12)'; color = '#10B981'; }
        return { background: bg, color, fontWeight: c > 0 ? 700 : 400 };
    };

    /* ── GEO flag helper ── */
    const geoFlag = (geo) => {
        if (!geo) return '—';
        const flags = { US: '🇺🇸', UK: '🇬🇧', DE: '🇩🇪', RU: '🇷🇺', NL: '🇳🇱', FR: '🇫🇷', CA: '🇨🇦' };
        return (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {flags[geo.toUpperCase()] || '🌐'} {geo}
            </span>
        );
    };

    return (
        <div className="page">
            {/* Header + actions */}
            <div style={{ fontSize: '0.6em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>NETWORK / PROXIES</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Shield size={22} /> Proxies
                </h2>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => setShowUpload(!showUpload)}
                        style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>Import</button>
                    <button className="btn btn-success" onClick={checkAll} disabled={checking || total === 0}
                        style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                        {checking ? 'Checking...' : 'Check All'}
                    </button>
                    <button className="btn" onClick={resetAll} disabled={total === 0}
                        style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>Reset Counters</button>
                </div>
            </div>

            {/* ═══ Stat Cards ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
                {[
                    { label: 'Total', value: total, color: '#10B981', filterKey: null },
                    { label: 'Active', value: alive, color: '#10B981', filterKey: 'active' },
                    { label: 'Exhausted', value: exhausted, color: '#F59E0B', filterKey: 'exhausted' },
                    { label: 'Dead', value: dead, color: '#EF4444', filterKey: 'dead' },
                ].map(s => (
                    <div key={s.label} className="card" onClick={() => setFilter(filter === s.filterKey ? null : s.filterKey)}
                        style={{
                            cursor: 'pointer', padding: '16px 20px',
                            borderColor: filter === s.filterKey ? s.color : undefined,
                            borderLeft: `3px solid ${s.color}`,
                        }}>
                        <div style={{ fontSize: '1.8em', fontWeight: 900, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: '0.75em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* ═══ Import Area ═══ */}
            <div className="card" style={{ padding: '16px 20px', marginBottom: 20 }}>
                <div style={{ fontSize: '0.82em', fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                    Import area
                    <div style={{ position: 'relative', display: 'inline-flex' }}
                        onMouseEnter={() => setShowFormats(true)}
                        onMouseLeave={() => setShowFormats(false)}>
                        <span style={{
                            width: 18, height: 18, borderRadius: '50%', display: 'inline-flex',
                            alignItems: 'center', justifyContent: 'center', fontSize: '0.75em',
                            background: 'rgba(16,185,129,0.15)', color: '#10B981', cursor: 'help',
                            fontWeight: 800, border: '1px solid rgba(16,185,129,0.3)',
                        }}>i</span>
                        {showFormats && (
                            <div style={{
                                position: 'absolute', top: 24, left: 0, zIndex: 100,
                                background: '#1a1d24', border: '1px solid var(--border-default)',
                                borderRadius: 10, padding: '14px 18px', width: 320,
                                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                                fontSize: '0.85em',
                            }}>
                                <div style={{ fontWeight: 700, color: '#10B981', marginBottom: 8 }}>Supported Formats</div>
                                {[
                                    { label: 'SOCKS5', examples: ['socks5://user:pass@host:port', 'socks5://host:port'] },
                                    { label: 'HTTP/S', examples: ['http://user:pass@host:port', 'https://host:port'] },
                                    { label: 'Plain', examples: ['host:port:user:pass', 'user:pass@host:port', 'host:port'] },
                                ].map(f => (
                                    <div key={f.label} style={{ marginBottom: 8 }}>
                                        <div style={{ fontWeight: 700, color: 'var(--text-secondary)', fontSize: '0.88em', marginBottom: 2 }}>{f.label}</div>
                                        {f.examples.map(ex => (
                                            <div key={ex} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', color: '#06B6D4', padding: '1px 0' }}>{ex}</div>
                                        ))}
                                    </div>
                                ))}
                                <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginTop: 4, borderTop: '1px solid var(--border-default)', paddingTop: 6 }}>
                                    Auto-detects protocol, auth, and format
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                <div
                    onDrop={handleDrop}
                    onDragOver={e => e.preventDefault()}
                    onClick={() => showUpload ? null : setShowUpload(true)}
                    style={{
                        border: '2px dashed rgba(16,185,129,0.25)',
                        borderRadius: 12,
                        padding: showUpload ? 0 : 32,
                        textAlign: 'center',
                        cursor: 'pointer',
                        background: 'rgba(16,185,129,0.02)',
                        transition: 'all 0.2s',
                    }}>
                    {showUpload ? (
                        <div style={{ padding: 12 }}>
                            <textarea className="form-input"
                                style={{ border: 'none', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em', minHeight: 100 }}
                                rows={4}
                                placeholder={"IP:PORT:USER:PASS\nlogin:password@ip:port\nsocks5://user:pass@ip:port"}
                                value={uploadText}
                                onChange={e => setUploadText(e.target.value)}
                            />
                            <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
                                <input className="form-input" type="datetime-local" value={expiresAt}
                                    onChange={e => setExpiresAt(e.target.value)} style={{ width: 200 }} />
                                <button className="btn btn-primary" onClick={handleUpload} disabled={!uploadText.trim() || loading}>
                                    {loading ? 'Adding...' : `Add ${parseProxyLines(uploadText).length} proxies`}
                                </button>
                                <button className="btn" onClick={() => fileRef.current?.click()}>Browse file</button>
                                <button className="btn" onClick={() => { setShowUpload(false); setUploadText(''); }}>
                                    <X size={14} />
                                </button>
                            </div>
                        </div>
                    ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.85em' }}>
                            Drop proxy list here (IP:PORT:USER:PASS)
                        </span>
                    )}
                </div>
                <input type="file" ref={fileRef} accept=".txt" style={{ display: 'none' }} onChange={handleFile} />
            </div>

            {/* ═══ Batch action bar ═══ */}
            {selected.size > 0 && (
                <div style={{
                    padding: '10px 16px', marginBottom: 12,
                    background: 'rgba(239,68,68,0.06)', borderRadius: 10,
                    border: '1px solid rgba(239,68,68,0.15)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <span style={{ fontSize: '0.82em', color: 'var(--text-muted)' }}>{selected.size} proxies selected</span>
                    <button className="btn btn-danger" onClick={batchDelete}
                        style={{ borderRadius: 16, padding: '6px 16px', fontSize: '0.78em' }}>
                        <Trash2 size={12} /> Delete Selected
                    </button>
                </div>
            )}

            {/* ═══ Proxy Table ═══ */}
            {total > 0 && (
                <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
                    <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--border-default)' }}>
                                <th style={thStyle}><input type="checkbox" checked={selected.size === filteredProxies.length && filteredProxies.length > 0} onChange={toggleAll} style={{ accentColor: 'var(--accent)' }} /></th>
                                <th style={thStyle}>Status</th>
                                <th style={thStyle}>Host:Port</th>
                                <th style={thStyle}>Type</th>
                                <th style={thStyle}>Source</th>
                                <th style={thStyle}>Geo</th>
                                <th style={thStyle}>Speed</th>
                                {[
                                    { label: 'G', color: '#EA4335', bg: 'rgba(234,67,53,0.15)' },
                                    { label: 'Y/A', color: '#6001D2', bg: 'rgba(96,1,210,0.15)' },
                                    { label: 'O/H', color: '#0078D4', bg: 'rgba(0,120,212,0.15)' },
                                    { label: 'P', color: '#6D4AFF', bg: 'rgba(109,74,255,0.15)' },
                                    { label: 'T', color: '#840010', bg: 'rgba(132,0,16,0.15)' },
                                ].map(b => (
                                    <th key={b.label} style={{ ...thStyle, textAlign: 'center', padding: '8px 4px' }}>
                                        <span style={{
                                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                            width: b.label.length > 1 ? 32 : 22, height: 22, borderRadius: 6,
                                            background: b.bg, color: b.color,
                                            fontSize: '0.85em', fontWeight: 900, letterSpacing: 0,
                                            border: `1px solid ${b.color}33`,
                                        }}>{b.label}</span>
                                    </th>
                                ))}
                                <th style={thStyle}>Last Used</th>
                                <th style={thStyle}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredProxies.map((p, i) => (
                                <tr key={p.id || i} style={{
                                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                                    background: selected.has(p.id) ? 'rgba(239,68,68,0.04)' : 'transparent',
                                }}>
                                    {/* Checkbox */}
                                    <td style={tdStyle}>
                                        <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSelect(p.id)}
                                            style={{ accentColor: selected.has(p.id) ? 'var(--danger)' : 'var(--accent)' }} />
                                    </td>
                                    {/* Status dot */}
                                    <td style={tdStyle}>
                                        <div style={{
                                            width: 10, height: 10, borderRadius: '50%',
                                            background: p.status === 'active' ? '#10B981'
                                                : p.status === 'exhausted' ? '#F59E0B' : '#EF4444',
                                            boxShadow: p.status === 'active' ? '0 0 6px rgba(16,185,129,0.5)' : undefined,
                                        }} />
                                    </td>

                                    {/* Host:Port */}
                                    <td style={{ ...tdStyle, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em' }}>
                                        {p.host}:{p.port}
                                    </td>

                                    {/* Type badge */}
                                    <td style={tdStyle}>
                                        <span style={{
                                            padding: '2px 8px', borderRadius: 4, fontSize: '0.75em', fontWeight: 600,
                                            background: (p.proxy_type || 'http') === 'socks5' ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)',
                                            color: (p.proxy_type || 'http') === 'socks5' ? '#A78BFA' : '#60A5FA',
                                        }}>{(p.proxy_type || 'HTTP').toUpperCase()}</span>
                                    </td>

                                    {/* Source badge */}
                                    <td style={tdStyle}>
                                        {(() => {
                                            const src = p.source || 'manual';
                                            const srcMap = {
                                                manual: { color: '#9CA3AF', bg: 'rgba(156,163,175,0.15)', label: '📄' },
                                                asocks: { color: '#8B5CF6', bg: 'rgba(139,92,246,0.15)', label: '📱 AS' },
                                                proxy6: { color: '#F59E0B', bg: 'rgba(245,158,11,0.15)', label: '6️⃣ P6' },
                                                belurk: { color: '#EF4444', bg: 'rgba(239,68,68,0.15)', label: '🛡 BL' },
                                                iproyal: { color: '#3B82F6', bg: 'rgba(59,130,246,0.15)', label: '🏠 IR' },
                                            };
                                            const s = srcMap[src] || srcMap.manual;
                                            return <span style={{
                                                padding: '2px 6px', borderRadius: 4, fontSize: '0.72em', fontWeight: 700,
                                                background: s.bg, color: s.color, border: `1px solid ${s.color}33`,
                                            }}>{s.label}</span>;
                                        })()}
                                    </td>

                                    {/* Geo with flag */}
                                    <td style={{ ...tdStyle, fontSize: '0.82em' }}>{geoFlag(p.geo)}</td>

                                    {/* Speed */}
                                    <td style={{ ...tdStyle, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', color: 'var(--text-muted)' }}>
                                        {p.response_time_ms ? `${p.response_time_ms}ms` : '—'}
                                    </td>

                                    {/* Per-provider usage cells: G, Y/A, O/H, P, T */}
                                    {[
                                        { key: 'G', limit: 1 },
                                        { key: 'YA', limit: 3 },
                                        { key: 'OH', limit: 3 },
                                        { key: 'PT', limit: 3 },
                                        { key: 'TT', limit: 3 },
                                    ].map(({ key, limit }) => {
                                        const cnt = p[`use_${key}`] || 0;
                                        const style = usageCell(cnt);
                                        return (
                                            <td key={key} style={{
                                                ...tdStyle, textAlign: 'center', fontSize: '0.85em',
                                                ...style, padding: '8px 4px', borderRadius: 0,
                                            }}>
                                                {cnt > 0 ? `${cnt}/${limit}` : '—'}
                                            </td>
                                        );
                                    })}

                                    {/* Last used */}
                                    <td style={{ ...tdStyle, fontSize: '0.78em', color: 'var(--text-muted)' }}>
                                        {p.last_used ? timeAgo(p.last_used) : '—'}
                                    </td>

                                    {/* Actions */}
                                    <td style={tdStyle}>
                                        <div style={{ display: 'flex', gap: 4 }}>
                                            <button className="btn btn-sm" onClick={() => checkOne(p.id)}
                                                disabled={checkingId === p.id} style={{ padding: '5px 8px' }} title="Check proxy">
                                                {checkingId === p.id ? <RefreshCw size={14} className="spin" /> : <Zap size={14} />}
                                            </button>
                                            <button className="btn btn-sm" onClick={() => startEdit(p)} style={{ padding: '5px 8px' }} title="Edit proxy">
                                                <Edit3 size={14} />
                                            </button>
                                            <button className="btn btn-sm btn-danger" onClick={() => deleteProxy(p.id)} style={{ padding: '5px 8px' }} title="Delete proxy">
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Edit Modal */}
            {editingId && (
                <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    onClick={() => { setEditingId(null); setEditData({}); }}>
                    <div className="card" style={{ width: 420, padding: '24px 28px' }} onClick={e => e.stopPropagation()}>
                        <div style={{ fontWeight: 800, marginBottom: 16 }}>Edit Proxy</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 12 }}>
                            <div><label className="form-label">Host</label><input className="form-input" value={editData.host} onChange={e => setEditData({ ...editData, host: e.target.value })} /></div>
                            <div><label className="form-label">Port</label><input className="form-input" type="number" value={editData.port} onChange={e => setEditData({ ...editData, port: e.target.value })} /></div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                            <div><label className="form-label">Username</label><input className="form-input" value={editData.username} onChange={e => setEditData({ ...editData, username: e.target.value })} /></div>
                            <div><label className="form-label">Password</label><input className="form-input" type="password" value={editData.password} onChange={e => setEditData({ ...editData, password: e.target.value })} /></div>
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => saveEdit(editingId)}><Save size={14} /> Save</button>
                            <button className="btn" onClick={() => { setEditingId(null); setEditData({}); }}>Cancel</button>
                        </div>
                    </div>
                </div>
            )}

            {total === 0 && !showUpload && (
                <div className="card" style={{ textAlign: 'center', padding: 48, marginTop: 20 }}>
                    <WifiOff size={40} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.95em', fontWeight: 600 }}>No proxies yet</p>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.82em', marginTop: 4 }}>Import proxies to get started</p>
                </div>
            )}
        </div>
    );
}

/* ── Table styles ── */
const thStyle = {
    padding: '10px 8px',
    fontSize: '0.68em',
    fontWeight: 700,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    textAlign: 'left',
    whiteSpace: 'nowrap',
};

const tdStyle = {
    padding: '10px 8px',
    fontSize: '0.88em',
    verticalAlign: 'middle',
};

/* ── Time ago ── */
function timeAgo(dateStr) {
    if (!dateStr) return '—';
    const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}
