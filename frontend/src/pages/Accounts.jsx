import React, { useState, useEffect, useCallback } from 'react';
import {
    Users, Search, Mail, Download, Trash2, ArrowRight, Eye, EyeOff,
    X, ChevronLeft, ChevronRight, RefreshCw, Filter, CheckSquare, Square,
    Shield, Globe, Clock, Zap, Copy, AlertTriangle
} from 'lucide-react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';

const STATUS_BADGES = {
    new: { label: 'New', bg: 'rgba(100,116,139,0.15)', color: '#94A3B8', group: 'New' },
    phase_1: { label: 'Phase 1', bg: 'rgba(78,205,196,0.15)', color: '#4ecdc4', group: 'Warming' },
    phase_2: { label: 'Phase 2', bg: 'rgba(69,183,209,0.15)', color: '#45b7d1', group: 'Warming' },
    phase_3: { label: 'Phase 3', bg: 'rgba(247,220,111,0.15)', color: '#f7dc6f', group: 'Warming' },
    phase_4: { label: 'Phase 4', bg: 'rgba(243,156,18,0.15)', color: '#f39c12', group: 'Warming' },
    phase_5: { label: 'Phase 5', bg: 'rgba(231,76,60,0.15)', color: '#e74c3c', group: 'Warming' },
    warmed: { label: 'Warmed', bg: 'rgba(16,185,129,0.15)', color: '#10B981', group: 'Warmed' },
    sending: { label: 'Sending', bg: 'rgba(16,185,129,0.15)', color: '#10B981', group: 'Warmed' },
    paused: { label: 'Paused', bg: 'rgba(59,130,246,0.15)', color: '#3B82F6', group: 'Paused' },
    dead: { label: 'Dead', bg: 'rgba(239,68,68,0.15)', color: '#EF4444', group: 'Banned' },
    banned: { label: 'Banned', bg: 'rgba(239,68,68,0.15)', color: '#EF4444', group: 'Banned' },
};

const STATUS_FILTER_GROUPS = {
    'All': null,
    'New': ['new'],
    'Warming': ['phase_1', 'phase_2', 'phase_3', 'phase_4', 'phase_5'],
    'Warmed': ['warmed', 'sending'],
    'Paused': ['paused'],
    'Dead': ['dead', 'banned'],
};

const PAGE_SIZE = 50;

export default function Accounts() {
    const [accounts, setAccounts] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [farms, setFarms] = useState([]);

    // Filters
    const [tab, setTab] = useState('All');
    const [searchTerm, setSearchTerm] = useState('');
    const [providerFilter, setProviderFilter] = useState('');
    const [farmFilter, setFarmFilter] = useState('');

    // Selection
    const [selected, setSelected] = useState(new Set());

    // Modals
    const [detailAccount, setDetailAccount] = useState(null);
    const [showPassword, setShowPassword] = useState(false);
    const [showMoveModal, setShowMoveModal] = useState(false);
    const [showStatusModal, setShowStatusModal] = useState(false);
    const [showExportModal, setShowExportModal] = useState(false);

    // Load accounts from API
    const loadAccounts = useCallback(() => {
        const statuses = STATUS_FILTER_GROUPS[tab];
        const params = new URLSearchParams();
        params.set('page', page);
        params.set('page_size', PAGE_SIZE);
        if (statuses) params.set('status', statuses.join(','));
        if (searchTerm) params.set('search', searchTerm);
        if (providerFilter) params.set('provider', providerFilter);
        if (farmFilter) params.set('farm_id', farmFilter);

        fetch(`${API}/accounts/?${params}`)
            .then(r => r.json())
            .then(d => {
                setAccounts(d.accounts || []);
                setTotal(d.total || 0);
                setTotalPages(d.total_pages || 1);
            })
            .catch(() => { });
    }, [page, tab, searchTerm, providerFilter, farmFilter]);

    // Load farms for filters & move modal
    useEffect(() => {
        fetch(`${API}/farms/`).then(r => r.json()).then(setFarms).catch(() => { });
    }, []);

    useEffect(() => { loadAccounts(); }, [loadAccounts]);

    // Reset page on filter change
    useEffect(() => { setPage(1); setSelected(new Set()); }, [tab, searchTerm, providerFilter, farmFilter]);

    // Selection helpers
    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === accounts.length ? new Set() : new Set(accounts.map(a => a.id)));
    const clearSelection = () => setSelected(new Set());

    // ─── Bulk Actions ───

    const bulkDelete = async () => {
        if (!confirm(`Delete ${selected.size} accounts permanently? This cannot be undone.`)) return;
        await fetch(`${API}/accounts/batch-delete`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: [...selected] })
        });
        clearSelection(); loadAccounts();
    };

    const bulkMove = async (farmId) => {
        const res = await fetch(`${API}/accounts/batch-move`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: [...selected], target_farm_id: farmId })
        });
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        setShowMoveModal(false); clearSelection(); loadAccounts();
    };

    const bulkStatus = async (newStatus) => {
        const res = await fetch(`${API}/accounts/batch-status`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: [...selected], status: newStatus })
        });
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        setShowStatusModal(false); clearSelection(); loadAccounts();
    };

    const exportAccounts = async (format) => {
        const ids = selected.size > 0 ? [...selected] : null;
        const res = await fetch(`${API}/accounts/export`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, format })
        });
        if (format === 'json') {
            const d = await res.json();
            const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
            a.download = 'accounts_export.json'; a.click();
        } else {
            const blob = await res.blob();
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
            a.download = 'accounts_export.txt'; a.click();
        }
        setShowExportModal(false);
    };

    const deleteOne = async (id) => {
        if (!confirm('Delete this account?')) return;
        await fetch(`${API}/accounts/${id}`, { method: 'DELETE' });
        setDetailAccount(null); loadAccounts();
    };

    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text).catch(() => { });
    };

    const viewDetail = async (id) => {
        const d = await (await fetch(`${API}/accounts/${id}`)).json();
        setDetailAccount(d);
        setShowPassword(false);
    };

    const bStyle = { padding: '6px 14px', borderRadius: 6, border: '1px solid var(--border-default)', background: 'transparent', color: 'var(--text-secondary)', fontSize: '0.78em', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5, transition: 'all 0.15s' };

    return (
        <div className="page">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div className="page-breadcrumb">ACCOUNTS</div>
                    <h2 className="page-title">
                        <Users size={22} style={{ verticalAlign: 'middle', marginRight: 8 }} /> Accounts
                    </h2>
                </div>
                <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '1.1em' }}>{total} total</span>
            </div>

            {/* ═══ Status Tabs ═══ */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
                {Object.keys(STATUS_FILTER_GROUPS).map(t => (
                    <button key={t} onClick={() => setTab(t)} style={{
                        padding: '6px 16px', borderRadius: 20, border: '1px solid',
                        borderColor: tab === t ? 'var(--accent)' : 'var(--border-default)',
                        background: tab === t ? 'var(--accent)' : 'transparent',
                        color: tab === t ? '#000' : 'var(--text-secondary)',
                        fontSize: '0.78em', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                    }}>
                        {t}
                    </button>
                ))}
            </div>

            {/* ═══ Search + Filters ═══ */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                    <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                    <input className="form-input" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                        placeholder="Search by email..." style={{ paddingLeft: 34, fontSize: '0.85em' }} />
                </div>
                <select className="form-input" value={providerFilter} onChange={e => setProviderFilter(e.target.value)}
                    style={{ width: 130, fontSize: '0.82em', cursor: 'pointer' }}>
                    <option value="">All Providers</option>
                    <option value="gmail">Gmail</option>
                    <option value="outlook">Outlook</option>
                    <option value="hotmail">Hotmail</option>
                    <option value="yahoo">Yahoo</option>
                    <option value="aol">AOL</option>
                    <option value="protonmail">Proton</option>
                    <option value="webde">Web.de</option>
                </select>
                <select className="form-input" value={farmFilter} onChange={e => setFarmFilter(e.target.value)}
                    style={{ width: 150, fontSize: '0.82em', cursor: 'pointer' }}>
                    <option value="">All Farms</option>
                    {farms.map(f => <option key={f.id} value={f.id}>{f.name} ({f.accounts_count})</option>)}
                </select>
                <button onClick={loadAccounts} style={{ ...bStyle, borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                    <RefreshCw size={13} /> Refresh
                </button>
            </div>

            {/* ═══ Bulk Actions Bar ═══ */}
            {selected.size > 0 && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '10px 16px',
                    borderRadius: 10, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)',
                }}>
                    <span style={{ fontSize: '0.82em', fontWeight: 700, color: 'var(--accent)', marginRight: 4 }}>
                        <CheckSquare size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                        {selected.size} selected
                    </span>
                    <div style={{ flex: 1 }} />
                    <button onClick={() => setShowMoveModal(true)} style={{ ...bStyle, borderColor: '#06b6d4', color: '#06b6d4' }}>
                        <ArrowRight size={13} /> Move to Farm
                    </button>
                    <button onClick={() => setShowStatusModal(true)} style={{ ...bStyle, borderColor: '#a78bfa', color: '#a78bfa' }}>
                        <Zap size={13} /> Change Status
                    </button>
                    <button onClick={() => setShowExportModal(true)} style={{ ...bStyle, borderColor: '#f59e0b', color: '#f59e0b' }}>
                        <Download size={13} /> Export
                    </button>
                    <button onClick={bulkDelete} style={{ ...bStyle, borderColor: '#ef4444', color: '#ef4444' }}>
                        <Trash2 size={13} /> Delete
                    </button>
                    <button onClick={clearSelection} style={{ ...bStyle, padding: '6px 8px' }}><X size={13} /></button>
                </div>
            )}

            {/* ═══ Table ═══ */}
            {accounts.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                    <Users size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />
                    {total === 0 ? 'No accounts yet. Create them on the AUTOREG page.' : 'No matches for filters.'}
                </div>
            ) : (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Header row */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '36px 36px 1fr 80px 100px 60px 80px 60px',
                        padding: '10px 14px', fontSize: '0.68em', fontWeight: 700, letterSpacing: 1,
                        color: 'var(--text-muted)', textTransform: 'uppercase',
                        borderBottom: '1px solid var(--border-default)',
                    }}>
                        <span style={{ display: 'flex', alignItems: 'center' }}>
                            <input type="checkbox" checked={selected.size === accounts.length && accounts.length > 0}
                                onChange={toggleAll} style={{ accentColor: 'var(--accent)', cursor: 'pointer' }} />
                        </span>
                        <span></span><span>Email</span><span>Status</span>
                        <span>Farm</span><span>Sent</span><span>Health</span><span>Geo</span>
                    </div>

                    {/* Rows */}
                    {accounts.map(acc => {
                        const badge = STATUS_BADGES[acc.status] || { label: acc.status, bg: 'rgba(100,116,139,0.1)', color: '#94A3B8' };
                        const isSelected = selected.has(acc.id);
                        return (
                            <div key={acc.id} style={{
                                display: 'grid', gridTemplateColumns: '36px 36px 1fr 80px 100px 60px 80px 60px',
                                padding: '9px 14px', fontSize: '0.82em', cursor: 'pointer',
                                borderBottom: '1px solid rgba(255,255,255,0.02)',
                                background: isSelected ? 'rgba(16,185,129,0.04)' : 'transparent',
                                transition: 'background 0.12s',
                            }}
                                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
                                onClick={() => viewDetail(acc.id)}
                            >
                                {/* Checkbox */}
                                <span style={{ display: 'flex', alignItems: 'center' }} onClick={e => e.stopPropagation()}>
                                    <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(acc.id)}
                                        style={{ accentColor: 'var(--accent)', cursor: 'pointer' }} />
                                </span>

                                {/* Provider logo */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <ProviderLogo provider={acc.provider} size={24} />
                                </span>

                                {/* Email */}
                                <span style={{ color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center' }}>
                                    {acc.email}
                                </span>

                                {/* Status */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <span style={{
                                        padding: '3px 10px', borderRadius: 12, fontSize: '0.72em', fontWeight: 600,
                                        background: badge.bg, color: badge.color,
                                    }}>{badge.label}</span>
                                </span>

                                {/* Farm */}
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.82em', display: 'flex', alignItems: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {acc.farm_name || '—'}
                                </span>

                                {/* Sent */}
                                <span style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center' }}>
                                    {acc.sent_count || 0}
                                </span>

                                {/* Health */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <span style={{
                                        fontSize: '0.78em', fontWeight: 600,
                                        color: (acc.health_score || 0) >= 80 ? '#10b981' : (acc.health_score || 0) >= 50 ? '#f59e0b' : '#ef4444',
                                    }}>{Math.round(acc.health_score || 0)}%</span>
                                </span>

                                {/* Geo */}
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.82em', display: 'flex', alignItems: 'center' }}>
                                    {acc.geo || '—'}
                                </span>
                            </div>
                        );
                    })}

                    {/* Pagination */}
                    <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '10px 14px', borderTop: '1px solid var(--border-default)',
                        fontSize: '0.78em', color: 'var(--text-muted)',
                    }}>
                        <span>{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}</span>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                                style={{ ...bStyle, padding: '4px 8px', opacity: page <= 1 ? 0.3 : 1 }}>
                                <ChevronLeft size={14} />
                            </button>
                            <span style={{ padding: '0 8px', fontWeight: 600 }}>Page {page}/{totalPages}</span>
                            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                                style={{ ...bStyle, padding: '4px 8px', opacity: page >= totalPages ? 0.3 : 1 }}>
                                <ChevronRight size={14} />
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ═══ Detail Modal ═══ */}
            {detailAccount && (
                <div className="modal-overlay" onClick={() => setDetailAccount(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 560, padding: 24 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: '1.05em', display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <ProviderLogo provider={detailAccount.provider} size={22} />
                                    {detailAccount.email}
                                    <button onClick={() => copyToClipboard(detailAccount.email)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}>
                                        <Copy size={13} />
                                    </button>
                                </div>
                                <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 2 }}>{detailAccount.farm_name || 'No farm'}</div>
                            </div>
                            <button className="btn btn-sm" onClick={() => setDetailAccount(null)}><X size={14} /></button>
                        </div>

                        {/* Password row */}
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, padding: '10px 14px',
                            borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)',
                        }}>
                            <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, width: 70 }}>Password</span>
                            <span style={{ fontFamily: 'monospace', fontSize: '0.88em', flex: 1, letterSpacing: showPassword ? 0.5 : 3 }}>
                                {showPassword ? detailAccount.password : '••••••••'}
                            </span>
                            <button onClick={() => setShowPassword(!showPassword)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}>
                                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                            <button onClick={() => copyToClipboard(detailAccount.password)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}>
                                <Copy size={13} />
                            </button>
                        </div>

                        {/* Info grid */}
                        <div className="config-row-3" style={{ marginBottom: 16 }}>
                            {[
                                { label: 'Status', value: STATUS_BADGES[detailAccount.status]?.label || detailAccount.status, color: STATUS_BADGES[detailAccount.status]?.color },
                                { label: 'Provider', value: detailAccount.provider?.toUpperCase() },
                                { label: 'Health', value: `${Math.round(detailAccount.health_score || 0)}%`, color: (detailAccount.health_score || 0) >= 80 ? '#10b981' : '#f59e0b' },
                                { label: 'Warmup Day', value: detailAccount.warmup_day || 0 },
                                { label: 'Emails Sent', value: detailAccount.sent_count || 0 },
                                { label: 'Bounces', value: detailAccount.bounces || 0 },
                                { label: 'Geo', value: detailAccount.geo || '—' },
                                { label: 'IMAP', value: detailAccount.imap_verified ? '✓ Verified' : '✗ Not verified', color: detailAccount.imap_verified ? '#10b981' : '#ef4444' },
                                { label: 'Created', value: detailAccount.created_at ? new Date(detailAccount.created_at).toLocaleDateString() : '—' },
                            ].map((item, i) => (
                                <div key={i} style={{ padding: '8px 10px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: '0.58em', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 3 }}>{item.label}</div>
                                    <div style={{ fontSize: '0.85em', fontWeight: 600, color: item.color || 'var(--text-primary)' }}>{item.value}</div>
                                </div>
                            ))}
                        </div>

                        {/* Proxy info */}
                        {detailAccount.proxy && (
                            <div style={{ marginBottom: 16, padding: '8px 14px', borderRadius: 8, background: 'rgba(6,182,212,0.04)', border: '1px solid rgba(6,182,212,0.1)' }}>
                                <div style={{ fontSize: '0.65em', color: '#06b6d4', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Bound Proxy</div>
                                <div style={{ fontFamily: 'monospace', fontSize: '0.78em', color: 'var(--text-secondary)' }}>{detailAccount.proxy}</div>
                            </div>
                        )}

                        {/* Actions */}
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button onClick={() => { copyToClipboard(`${detailAccount.email}:${detailAccount.password}`); }}
                                style={{ ...bStyle, borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                <Copy size={13} /> Copy email:pass
                            </button>
                            <div style={{ flex: 1 }} />
                            <button onClick={() => deleteOne(detailAccount.id)}
                                style={{ ...bStyle, borderColor: '#ef4444', color: '#ef4444' }}>
                                <Trash2 size={13} /> Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ═══ Move to Farm Modal ═══ */}
            {showMoveModal && (
                <div className="modal-overlay" onClick={() => setShowMoveModal(false)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 400, padding: 24 }}>
                        <div style={{ fontWeight: 700, fontSize: '1em', marginBottom: 12 }}>
                            <ArrowRight size={16} /> Move {selected.size} accounts to farm
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {farms.map(f => (
                                <button key={f.id} className="btn" onClick={() => bulkMove(f.id)}
                                    style={{ textAlign: 'left', padding: '10px 14px', fontSize: '0.85em', justifyContent: 'space-between', display: 'flex' }}>
                                    <span>{f.name}</span>
                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.82em' }}>{f.accounts_count} accounts</span>
                                </button>
                            ))}
                            {farms.length === 0 && <span style={{ fontSize: '0.82em', color: 'var(--text-muted)', padding: 10 }}>No farms. Create one first.</span>}
                        </div>
                        <button className="btn" onClick={() => setShowMoveModal(false)} style={{ marginTop: 12, width: '100%' }}>Cancel</button>
                    </div>
                </div>
            )}

            {/* ═══ Change Status Modal ═══ */}
            {showStatusModal && (
                <div className="modal-overlay" onClick={() => setShowStatusModal(false)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 400, padding: 24 }}>
                        <div style={{ fontWeight: 700, fontSize: '1em', marginBottom: 12 }}>
                            <Zap size={16} /> Change status of {selected.size} accounts
                        </div>
                        <div className="config-row-2" style={{ gap: 6 }}>
                            {Object.entries(STATUS_BADGES).map(([key, badge]) => (
                                <button key={key} onClick={() => bulkStatus(key)}
                                    style={{
                                        ...bStyle, borderColor: badge.color, color: badge.color,
                                        justifyContent: 'center', padding: '8px 12px',
                                    }}>
                                    {badge.label}
                                </button>
                            ))}
                        </div>
                        <button className="btn" onClick={() => setShowStatusModal(false)} style={{ marginTop: 12, width: '100%' }}>Cancel</button>
                    </div>
                </div>
            )}

            {/* ═══ Export Modal ═══ */}
            {showExportModal && (
                <div className="modal-overlay" onClick={() => setShowExportModal(false)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 380, padding: 24 }}>
                        <div style={{ fontWeight: 700, fontSize: '1em', marginBottom: 6 }}>
                            <Download size={16} /> Export {selected.size > 0 ? `${selected.size} selected` : `all ${total}`} accounts
                        </div>
                        <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 16 }}>
                            Choose format:
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button onClick={() => exportAccounts('text')}
                                style={{ ...bStyle, flex: 1, justifyContent: 'center', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                email:password (TXT)
                            </button>
                            <button onClick={() => exportAccounts('json')}
                                style={{ ...bStyle, flex: 1, justifyContent: 'center', borderColor: '#06b6d4', color: '#06b6d4' }}>
                                Full Data (JSON)
                            </button>
                        </div>
                        <button className="btn" onClick={() => setShowExportModal(false)} style={{ marginTop: 12, width: '100%' }}>Cancel</button>
                    </div>
                </div>
            )}
        </div>
    );
}
