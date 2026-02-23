import React, { useState, useEffect, useRef } from 'react';
import { Shield, Upload, Trash2, RefreshCw, CheckCircle, XCircle, Clock, Wifi, WifiOff, Globe2, Calendar, Edit3, Link2, Unlink, Save, X, Zap } from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

export default function Proxies() {
    const { t } = useI18n();
    const [proxies, setProxies] = useState([]);
    const [stats, setStats] = useState({});
    const [filter, setFilter] = useState(null); // null=all, 'active', 'free', 'dead'
    const [showUpload, setShowUpload] = useState(false);
    const [uploadText, setUploadText] = useState('');
    const [expiresAt, setExpiresAt] = useState('');
    const [loading, setLoading] = useState(false);
    const [checking, setChecking] = useState(false);
    const [checkingId, setCheckingId] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [editData, setEditData] = useState({});
    const fileRef = useRef();

    const total = stats.total || 0;
    const alive = stats.active || 0;
    const dead = stats.dead || 0;
    const bound = stats.bound || 0;
    const free = stats.free || 0;

    const filteredProxies = filter ? proxies.filter(p => {
        if (filter === 'active') return p.status === 'active' && !p.bound_to;
        if (filter === 'bound') return !!p.bound_to;
        if (filter === 'free') return p.status === 'free';
        if (filter === 'dead') return ['dead', 'expired', 'banned'].includes(p.status);
        return true;
    }) : proxies;

    const loadProxies = () => {
        fetch(`${API}/proxies/`).then(r => r.json()).then(setProxies).catch(() => { });
        fetch(`${API}/proxies/stats`).then(r => r.json()).then(setStats).catch(() => { });
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
                body: JSON.stringify({
                    proxies: lines,
                    expires_at: expiresAt || null
                })
            });
            const data = await res.json();
            if (data.types) {
                alert(`Импортировано: ${data.imported}\nSOCKS5: ${data.types.socks5 || 0}\nHTTP: ${data.types.http || 0}\nMOBILE: ${data.types.mobile || 0}`);
            }
            setUploadText(''); setShowUpload(false); loadProxies();
        } catch { }
        setLoading(false);
    };

    const handleFile = (e) => {
        const file = e.dataTransfer?.files[0] || e.target?.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => { setUploadText(ev.target.result); setShowUpload(true); };
        reader.readAsText(file);
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

    const checkAll = async () => {
        setChecking(true);
        try { await fetch(`${API}/proxies/check-all`, { method: 'POST' }); } catch { }
        setChecking(false);
        loadProxies();
    };

    const checkOne = async (id) => {
        setCheckingId(id);
        try {
            const res = await fetch(`${API}/proxies/check/${id}`, { method: 'POST' });
            const d = await res.json();
            if (d.alive === false) {
                alert(`Прокси #${id} — НЕ ОТВЕЧАЕТ (fail: ${d.fail_count})`);
            }
        } catch { }
        setCheckingId(null);
        loadProxies();
    };

    const deleteProxy = async (id) => {
        await fetch(`${API}/proxies/${id}`, { method: 'DELETE' });
        loadProxies();
    };

    const deleteAll = async () => {
        if (!confirm('Удалить ВСЕ прокси?')) return;
        await fetch(`${API}/proxies/all`, { method: 'DELETE' });
        loadProxies();
    };

    const resetAll = async () => {
        if (!confirm('Сбросить ВСЕ прокси в статус Active? (полезно после миграции)')) return;
        const res = await fetch(`${API}/proxies/reset-all`, { method: 'POST' });
        const d = await res.json();
        alert(`Сброшено ${d.reset} прокси в Active`);
        loadProxies();
    };

    const releaseFree = async () => {
        const res = await fetch(`${API}/proxies/release-free`, { method: 'POST' });
        const d = await res.json();
        alert(`Освобождено ${d.released} прокси → Active`);
        loadProxies();
    };

    const unbindProxy = async (id) => {
        await fetch(`${API}/proxies/${id}/unbind`, { method: 'POST' });
        loadProxies();
    };

    const startEdit = (proxy) => {
        setEditingId(proxy.id);
        setEditData({ host: proxy.host, port: proxy.port, username: '', password: '' });
    };

    const cancelEdit = () => { setEditingId(null); setEditData({}); };

    const saveEdit = async (id) => {
        const body = {};
        if (editData.host) body.host = editData.host;
        if (editData.port) body.port = parseInt(editData.port);
        if (editData.username) body.username = editData.username;
        if (editData.password) body.password = editData.password;

        await fetch(`${API}/proxies/${id}/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        setEditingId(null);
        setEditData({});
        loadProxies();
    };

    const autoReassign = async () => {
        const res = await (await fetch(`${API}/proxies/auto-reassign`, { method: 'POST' })).json();
        alert(`Переназначено: ${res.reassigned || 0}, Нет прокси: ${res.no_proxy_available || 0}`);
        loadProxies();
    };

    const getDaysLeft = (expiresDate) => {
        if (!expiresDate) return null;
        const diff = Math.ceil((new Date(expiresDate) - new Date()) / (1000 * 60 * 60 * 24));
        return diff;
    };

    return (
        <div className="page">
            <h2 className="page-title"><Shield size={24} /> {t('proxyManager')}</h2>

            {/* Stats — clickable filter tabs */}
            <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
                {[
                    { key: null, label: 'ВСЕГО', value: total, color: 'var(--accent)', icon: <Wifi size={13} /> },
                    { key: 'active', label: 'ЖИВЫЕ', value: alive, color: 'var(--success)', icon: <CheckCircle size={13} /> },
                    { key: 'dead', label: 'МЁРТВЫЕ', value: dead, color: 'var(--danger)', icon: <XCircle size={13} /> },
                    { key: 'bound', label: 'ПРИВЯЗАНЫ', value: bound, color: 'var(--info)', icon: <Link2 size={13} /> },
                    { key: 'free', label: 'СВОБОДНЫЕ', value: free, color: 'var(--warning)', icon: <Globe2 size={13} /> },
                ].map(tab => (
                    <div key={tab.label} className="card" onClick={() => setFilter(filter === tab.key ? null : tab.key)}
                        style={{
                            cursor: 'pointer', borderColor: filter === tab.key ? tab.color : undefined,
                            boxShadow: filter === tab.key ? `0 0 12px ${tab.color}33` : undefined
                        }}>
                        <div className="card-title" style={{ color: tab.color }}>{tab.icon} {tab.label}</div>
                        <div className="card-value" style={{ WebkitTextFillColor: tab.color }}>{tab.value}</div>
                    </div>
                ))}
            </div>

            {/* Proxy Type breakdown — inline */}
            {total > 0 && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.75em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Тип:</span>
                    {Object.entries(stats.by_type || {}).map(([type, cnt]) => (
                        <span key={type} className="badge" style={{
                            background: type === 'socks5' ? 'rgba(139,92,246,0.2)' : type === 'mobile' ? 'rgba(251,191,36,0.2)' : 'rgba(59,130,246,0.2)',
                            color: type === 'socks5' ? '#a78bfa' : type === 'mobile' ? '#fbbf24' : '#60a5fa',
                            fontSize: '0.78em', padding: '2px 8px'
                        }}>
                            {type === 'socks5' ? '🔒' : type === 'mobile' ? '📱' : '🌐'} {type.toUpperCase()}: {cnt}
                        </span>
                    ))}
                </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
                <button className="btn btn-primary" onClick={() => setShowUpload(!showUpload)}>
                    <Upload size={15} /> Загрузить прокси
                </button>
                <button className="btn btn-success" onClick={checkAll} disabled={checking || total === 0}>
                    <RefreshCw size={15} className={checking ? 'spin' : ''} /> {checking ? 'Проверяю...' : 'Проверить всё'}
                </button>
                {total > 0 && (
                    <button className="btn btn-danger" onClick={deleteAll}>
                        <Trash2 size={15} /> Удалить всё
                    </button>
                )}
                <button className="btn btn-danger" disabled={dead === 0} onClick={async () => {
                    if (!confirm(`Удалить ${dead} мёртвых прокси?`)) return;
                    const res = await fetch(`${API}/proxies/dead`, { method: 'DELETE' });
                    const d = await res.json();
                    alert(`Удалено ${d.deleted} мёртвых прокси` + (d.unbound_accounts ? `, отвязано ${d.unbound_accounts} аккаунтов` : ''));
                    loadProxies();
                }}>
                    <Trash2 size={15} /> Очистить мёртвые {dead > 0 && `(${dead})`}
                </button>
                <button className="btn" onClick={releaseFree} disabled={dead === 0} style={{ borderColor: 'var(--warning)', color: 'var(--warning)' }}>
                    <RefreshCw size={15} /> Освободить свободные
                </button>
                <input type="file" ref={fileRef} accept=".txt" style={{ display: 'none' }} onChange={handleFile} />
            </div>

            {/* Upload zone — SIMPLIFIED */}
            {showUpload && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div className="card-title"><Upload size={14} style={{ marginRight: 6 }} /> ДОБАВИТЬ ПРОКСИ</div>

                    <div style={{ fontSize: '0.9em', color: 'var(--text-muted)', marginBottom: 10 }}>
                        Вставьте прокси в любом формате — тип определится автоматически (SOCKS5 / HTTP / MOBILE)
                    </div>

                    <div onDrop={handleDrop} onDragOver={e => e.preventDefault()}
                        style={{ border: '2px dashed var(--border-hover)', borderRadius: 12, padding: 8, marginBottom: 12 }}>
                        <textarea className="form-input"
                            style={{ border: 'none', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.9em' }}
                            rows={6}
                            placeholder={"ip:port:login:password\nlogin:password@ip:port\nsocks5://user:pass@ip:port\n..."}
                            value={uploadText}
                            onChange={e => setUploadText(e.target.value)}
                        />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                        <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label">СРОК ДЕЙСТВИЯ</label>
                            <input className="form-input" type="datetime-local" value={expiresAt}
                                onChange={e => setExpiresAt(e.target.value)} />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                            <button className="btn btn-primary" onClick={handleUpload} disabled={!uploadText.trim() || loading}
                                style={{ flex: 1, padding: '12px' }}>
                                {loading ? 'Добавляю...' : 'Добавить'}
                            </button>
                            <button className="btn" onClick={() => fileRef.current?.click()}>Обзор файла</button>
                        </div>
                    </div>

                    {uploadText.trim() && (
                        <div style={{ fontSize: '0.9em', color: 'var(--accent)', fontWeight: 600 }}>
                            {parseProxyLines(uploadText).length} прокси найдено
                        </div>
                    )}
                </div>
            )}

            {/* Proxy Table */}
            {total > 0 && (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>{t('host')}</th>
                                <th>{t('port')}</th>
                                <th>{t('type')}</th>
                                <th>{t('status')}</th>
                                <th>{t('responseTime')}</th>
                                <th>GEO</th>
                                <th>{t('proxyExpires')}</th>
                                <th style={{ textAlign: 'center', fontSize: '0.7em' }}>G</th>
                                <th style={{ textAlign: 'center', fontSize: '0.7em' }}>YA</th>
                                <th style={{ textAlign: 'center', fontSize: '0.7em' }}>OH</th>
                                <th>BOUND TO</th>
                                <th>ACTIONS</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredProxies.map((p, i) => {
                                const daysLeft = getDaysLeft(p.expires_at);
                                const isEditing = editingId === p.id;
                                return (
                                    <tr key={p.id || i}>
                                        <td style={{ color: 'var(--text-muted)', fontSize: '0.8em' }}>{i + 1}</td>

                                        {/* Host - editable */}
                                        <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em' }}>
                                            {isEditing ? (
                                                <input className="form-input" style={{ fontSize: '0.85em', padding: '2px 6px', width: 120 }}
                                                    value={editData.host} onChange={e => setEditData({ ...editData, host: e.target.value })} />
                                            ) : p.host}
                                        </td>

                                        {/* Port - editable */}
                                        <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em' }}>
                                            {isEditing ? (
                                                <input className="form-input" type="number" style={{ fontSize: '0.85em', padding: '2px 6px', width: 60 }}
                                                    value={editData.port} onChange={e => setEditData({ ...editData, port: e.target.value })} />
                                            ) : p.port}
                                        </td>

                                        <td><span className="badge" style={{
                                            background: (p.proxy_type || 'http') === 'socks5' ? 'rgba(139,92,246,0.2)' : (p.proxy_type || 'http') === 'mobile' ? 'rgba(251,191,36,0.2)' : 'rgba(59,130,246,0.2)',
                                            color: (p.proxy_type || 'http') === 'socks5' ? '#a78bfa' : (p.proxy_type || 'http') === 'mobile' ? '#fbbf24' : '#60a5fa',
                                        }}>{(p.proxy_type || 'http').toUpperCase()}</span></td>
                                        <td>
                                            {p.status === 'active' ? (
                                                <span className="badge badge-success"><CheckCircle size={10} /> ALIVE</span>
                                            ) : p.status === 'free' ? (
                                                <span className="badge badge-warning"><Globe2 size={10} /> FREE</span>
                                            ) : p.status === 'dead' ? (
                                                <span className="badge badge-danger"><XCircle size={10} /> DEAD</span>
                                            ) : (
                                                <span className="badge badge-danger"><Clock size={10} /> {p.status || '—'}</span>
                                            )}
                                        </td>
                                        <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em', color: 'var(--text-muted)' }}>
                                            {p.response_time_ms ? `${p.response_time_ms}ms` : '—'}
                                        </td>
                                        <td style={{ fontSize: '0.85em', fontWeight: 600 }}>{p.geo || '—'}</td>
                                        <td style={{ fontSize: '0.78em' }}>
                                            {daysLeft !== null ? (
                                                <span style={{
                                                    color: daysLeft <= 3 ? 'var(--danger)' : daysLeft <= 7 ? 'var(--warning)' : 'var(--text-muted)',
                                                    fontWeight: daysLeft <= 7 ? 700 : 400,
                                                }}>
                                                    {daysLeft <= 0 ? '⛔ EXPIRED' : `${daysLeft}d`}
                                                </span>
                                            ) : '—'}
                                        </td>

                                        {/* Per-provider group usage G/YA/OH */}
                                        {['G', 'YA', 'OH'].map(group => {
                                            const cnt = p[`use_${group}`] || 0;
                                            return (
                                                <td key={group} style={{
                                                    textAlign: 'center', fontWeight: 600, fontSize: '0.8em',
                                                    color: cnt >= 3 ? 'var(--danger)' : cnt >= 2 ? 'var(--warning)' : cnt > 0 ? 'var(--text-primary)' : 'var(--text-muted)'
                                                }}>
                                                    {cnt || '·'}
                                                </td>
                                            );
                                        })}

                                        {/* Bound column */}
                                        <td style={{ fontSize: '0.75em' }}>
                                            {p.bound_to ? (
                                                <span style={{ color: 'var(--info)', fontWeight: 600 }}>
                                                    {p.bound_to}
                                                </span>
                                            ) : (
                                                <span style={{ color: 'var(--text-muted)' }}>—</span>
                                            )}
                                        </td>

                                        {/* Actions */}
                                        <td>
                                            <div style={{ display: 'flex', gap: 3 }}>
                                                {isEditing ? (
                                                    <>
                                                        <button className="btn btn-sm btn-success" onClick={() => saveEdit(p.id)} title="Save">
                                                            <Save size={12} />
                                                        </button>
                                                        <button className="btn btn-sm" onClick={cancelEdit} title="Cancel">
                                                            <X size={12} />
                                                        </button>
                                                    </>
                                                ) : (
                                                    <>
                                                        <button className="btn btn-sm btn-success" onClick={() => checkOne(p.id)}
                                                            title="Проверить" disabled={checkingId === p.id}
                                                            style={{ padding: '3px 6px', minWidth: 28 }}>
                                                            {checkingId === p.id ? <RefreshCw size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={11} />}
                                                        </button>
                                                        <button className="btn btn-sm" onClick={() => startEdit(p)} title="Edit proxy">
                                                            <Edit3 size={12} />
                                                        </button>
                                                        {(p.status === 'free' || p.status === 'dead') && (
                                                            <button className="btn btn-sm btn-success" title="→ Active" onClick={async () => {
                                                                await fetch(`${API}/proxies/${p.id}/move-to-active`, { method: 'POST' });
                                                                loadProxies();
                                                            }}>
                                                                <CheckCircle size={12} />
                                                            </button>
                                                        )}
                                                        {p.bound_to && (
                                                            <button className="btn btn-sm btn-warning" onClick={() => unbindProxy(p.id)} title="Unbind">
                                                                <Unlink size={12} />
                                                            </button>
                                                        )}
                                                        <button className="btn btn-sm btn-danger" onClick={() => deleteProxy(p.id)} title="Delete">
                                                            <Trash2 size={12} />
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Edit panel for credentials */}
            {editingId && (
                <div className="card" style={{ marginTop: 12, borderLeft: '3px solid var(--accent)' }}>
                    <div className="card-title"><Edit3 size={13} style={{ marginRight: 6 }} /> Edit Proxy Credentials (ID: {editingId})</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                        <div className="form-group">
                            <label className="form-label">Username</label>
                            <input className="form-input" value={editData.username} placeholder="leave empty to keep"
                                onChange={e => setEditData({ ...editData, username: e.target.value })} />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Password</label>
                            <input className="form-input" value={editData.password} placeholder="leave empty to keep"
                                onChange={e => setEditData({ ...editData, password: e.target.value })} />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <button className="btn btn-primary" onClick={() => saveEdit(editingId)}>
                            <Save size={14} /> Save Changes
                        </button>
                        <button className="btn" onClick={cancelEdit}>Cancel</button>
                    </div>
                </div>
            )}

            {total === 0 && !showUpload && (
                <div className="card" style={{ textAlign: 'center', padding: 48 }}>
                    <WifiOff size={40} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.95em', fontWeight: 600 }}>{t('noProxies')}</p>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.82em', marginTop: 4 }}>{t('uploadToStart')}</p>
                </div>
            )}
        </div>
    );
}
