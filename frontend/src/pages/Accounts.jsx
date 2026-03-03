import React, { useState, useEffect } from 'react';
import {
    Users, Search, Mail, Flame, Send, Skull, Clock,
    X, ChevronLeft, ChevronRight, Download, MoreHorizontal, Play, Pause, Trash2
} from 'lucide-react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';

/* ── Provider colors (for status indicators) ── */
const PROVIDER_COLORS = {
    gmail: '#EA4335', yahoo: '#6001D2', aol: '#FF6B00',
    outlook: '#0078D4', hotmail: '#0078D4', protonmail: '#6D4AFF',
};

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

const TABS = ['All', 'Warming', 'Warmed', 'Banned'];

const PAGE_SIZE = 25;

export default function Accounts() {
    const [accounts, setAccounts] = useState([]);
    const [_farms, setFarms] = useState([]);
    const [tab, setTab] = useState('All');
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const [selectedAccount, setSelectedAccount] = useState(null);

    useEffect(() => {
        fetch(`${API}/farms/`).then(r => r.json()).then(data => {
            setFarms(data);
            const allAccounts = [];
            data.forEach(farm => {
                fetch(`${API}/farms/${farm.id}`).then(r => r.json()).then(detail => {
                    if (detail.accounts) {
                        detail.accounts.forEach(acc => allAccounts.push({ ...acc, farm_name: farm.name, farm_id: farm.id }));
                        setAccounts([...allAccounts]);
                    }
                }).catch(() => { /* ignore */ });
            });
        }).catch(() => { /* ignore */ });
    }, []);

    /* Filter by tab */
    const tabFilter = (acc) => {
        if (tab === 'All') return true;
        const badge = STATUS_BADGES[acc.status];
        return badge?.group === tab;
    };

    const filtered = accounts
        .filter(tabFilter)
        .filter(a => !searchTerm || a.email?.toLowerCase().includes(searchTerm.toLowerCase()));

    const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
    const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const _tabCounts = {
        All: accounts.length,
        Warming: accounts.filter(a => a.status?.startsWith('phase_')).length,
        Warmed: accounts.filter(a => ['warmed', 'sending'].includes(a.status)).length,
        Banned: accounts.filter(a => ['dead', 'banned'].includes(a.status)).length,
    };

    return (
        <div className="page">
            {/* Header */}
            <div style={{ fontSize: '0.65em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>ACCOUNTS</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-block' }}>
                    <Users size={22} style={{ verticalAlign: 'middle', marginRight: 8 }} /> Accounts
                </h2>
                <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '1.1em' }}>{accounts.length} total</span>
            </div>

            {/* ═══ Tabs ═══ */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
                {TABS.map(t => (
                    <button key={t} onClick={() => { setTab(t); setPage(1); }} style={{
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

            {/* ═══ Search + Actions ═══ */}
            <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: '0.78em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: 0.5 }}>Search + Actions</div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <div style={{ position: 'relative', flex: 1 }}>
                        <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                        <input className="form-input" value={searchTerm} onChange={e => { setSearchTerm(e.target.value); setPage(1); }}
                            placeholder="Search accounts..." style={{ paddingLeft: 34 }} />
                    </div>
                    <button className="btn btn-primary" style={{ borderRadius: 8, padding: '8px 16px', fontSize: '0.82em' }}>
                        <Download size={14} /> Export ↓
                    </button>
                    <button className="btn" style={{ borderRadius: 8, padding: '8px 16px', fontSize: '0.82em' }}>
                        Bulk ∨
                    </button>
                </div>
            </div>

            {/* ═══ Table ═══ */}
            {filtered.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                    <Users size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />
                    {accounts.length === 0 ? 'No accounts yet. Create on AUTOREG page.' : 'No matches.'}
                </div>
            ) : (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Header */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '32px 40px 1fr 80px 80px 60px 80px 100px',
                        padding: '10px 14px', fontSize: '0.68em', fontWeight: 700, letterSpacing: 1,
                        color: 'var(--text-muted)', textTransform: 'uppercase',
                        borderBottom: '1px solid var(--border-default)',
                    }}>
                        <span>☐</span><span>Provider</span><span>Email</span><span>Status</span>
                        <span>Farm</span><span>Sent</span><span>Last Active</span><span>Actions</span>
                    </div>

                    {/* Rows */}
                    {paginated.map(acc => {
                        const badge = STATUS_BADGES[acc.status] || { label: acc.status, bg: 'rgba(100,116,139,0.1)', color: '#94A3B8' };
                        return (
                            <div key={acc.id} onClick={() => setSelectedAccount(acc)} style={{
                                display: 'grid', gridTemplateColumns: '32px 40px 1fr 80px 80px 60px 80px 100px',
                                padding: '10px 14px', fontSize: '0.82em', cursor: 'pointer',
                                borderBottom: '1px solid rgba(255,255,255,0.02)',
                                transition: 'background 0.15s',
                            }}
                                onMouseEnter={e => e.currentTarget.style.background = 'rgba(16,185,129,0.03)'}
                                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                            >
                                {/* Checkbox */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <div style={{ width: 16, height: 16, borderRadius: 3, border: '1px solid var(--border-default)' }} />
                                </span>

                                {/* Provider logo */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <ProviderLogo provider={acc.provider} size={28} />
                                </span>

                                {/* Email */}
                                <span style={{ color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center' }}>
                                    {acc.email}
                                </span>

                                {/* Status badge */}
                                <span style={{ display: 'flex', alignItems: 'center' }}>
                                    <span style={{
                                        padding: '3px 10px', borderRadius: 12, fontSize: '0.72em', fontWeight: 600,
                                        background: badge.bg, color: badge.color,
                                    }}>{badge.label}</span>
                                </span>

                                {/* Farm */}
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.85em', display: 'flex', alignItems: 'center' }}>
                                    {acc.farm_name || '—'}
                                </span>

                                {/* Sent */}
                                <span style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center' }}>{acc.sent_count || 0}</span>

                                {/* Last active */}
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.78em', display: 'flex', alignItems: 'center' }}>
                                    {acc.last_active ? timeAgo(acc.last_active) : '—'}
                                </span>

                                {/* Actions */}
                                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <button className="btn btn-sm" style={{ padding: '3px 5px' }}><Play size={10} /></button>
                                    <button className="btn btn-sm" style={{ padding: '3px 5px' }}><Pause size={10} /></button>
                                    <button className="btn btn-sm btn-danger" style={{ padding: '3px 5px' }}><Trash2 size={10} /></button>
                                </span>
                            </div>
                        );
                    })}

                    {/* Pagination */}
                    <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '10px 14px', borderTop: '1px solid var(--border-default)',
                        fontSize: '0.75em', color: 'var(--text-muted)',
                    }}>
                        <span>{(page - 1) * PAGE_SIZE + 1}-{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => (
                                <button key={i + 1} onClick={() => setPage(i + 1)} style={{
                                    width: 8, height: 8, borderRadius: '50%', border: 'none', cursor: 'pointer',
                                    background: page === i + 1 ? 'var(--accent)' : 'rgba(255,255,255,0.15)',
                                }} />
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Detail modal */}
            {selectedAccount && (
                <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    onClick={() => setSelectedAccount(null)}>
                    <div className="card" style={{ maxWidth: 500, padding: 24 }} onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                            <span style={{ fontWeight: 700 }}>{selectedAccount.email}</span>
                            <button className="btn btn-sm" onClick={() => setSelectedAccount(null)}><X size={14} /></button>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                            {[
                                { label: 'Provider', value: selectedAccount.provider?.toUpperCase() },
                                { label: 'Status', value: STATUS_BADGES[selectedAccount.status]?.label || selectedAccount.status },
                                { label: 'Warmup Day', value: selectedAccount.warmup_day || 0 },
                                { label: 'Sent', value: selectedAccount.sent_count || 0 },
                                { label: 'Farm', value: selectedAccount.farm_name },
                                { label: 'Geo', value: selectedAccount.geo || '—' },
                            ].map((item, i) => (
                                <div key={i} style={{ padding: '10px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: '0.6em', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>{item.label}</div>
                                    <div style={{ fontSize: '0.9em', fontWeight: 600 }}>{item.value}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function timeAgo(dateStr) {
    if (!dateStr) return '—';
    const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}
