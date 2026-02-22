import React, { useState, useEffect } from 'react';
import {
    Users, Search, Filter, Mail, Flame, Send, Skull, Clock,
    ChevronDown, X, AlertTriangle, Calendar, Globe
} from 'lucide-react';

const API = 'http://localhost:8000/api';

const statusConfig = {
    new: { label: 'Новый', color: '#64748b', icon: <Clock size={12} /> },
    phase_1: { label: 'Фаза 1', color: '#f59e0b', icon: <Flame size={12} /> },    // 1-3 emails/day
    phase_2: { label: 'Фаза 2', color: '#f97316', icon: <Flame size={12} /> },    // 5-10 emails/day
    phase_3: { label: 'Фаза 3', color: '#ef4444', icon: <Flame size={12} /> },    // 10-20 emails/day
    phase_4: { label: 'Фаза 4', color: '#e11d48', icon: <Flame size={12} /> },    // 20-50 emails/day
    phase_5: { label: 'Фаза 5', color: '#a855f7', icon: <Flame size={12} /> },    // 50-100 emails/day
    warmed: { label: '🔥 WARMED', color: '#00ff41', icon: <Mail size={12} /> },     // fully ready
    sending: { label: 'Рассылка', color: '#a78bfa', icon: <Send size={12} /> },
    paused: { label: 'Пауза', color: '#94a3b8', icon: <Clock size={12} /> },
    dead: { label: 'Dead', color: '#ef4444', icon: <Skull size={12} /> },
    banned: { label: 'Banned', color: '#991b1b', icon: <Skull size={12} /> },
};

export default function Accounts() {
    const [accounts, setAccounts] = useState([]);
    const [farms, setFarms] = useState([]);
    const [filterStatus, setFilterStatus] = useState('');
    const [filterFarm, setFilterFarm] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedAccount, setSelectedAccount] = useState(null);

    useEffect(() => {
        fetch(`${API}/farms/`).then(r => r.json()).then(data => {
            setFarms(data);
            // Extract accounts from all farms
            const allAccounts = [];
            data.forEach(farm => {
                // Fetch each farm's details to get accounts
                fetch(`${API}/farms/${farm.id}`).then(r => r.json()).then(detail => {
                    if (detail.accounts) {
                        detail.accounts.forEach(acc => allAccounts.push({ ...acc, farm_name: farm.name, farm_id: farm.id }));
                        setAccounts([...allAccounts]);
                    }
                }).catch(() => { });
            });
        }).catch(() => { });
    }, []);

    const filtered = accounts.filter(a => {
        if (filterStatus && a.status !== filterStatus) return false;
        if (filterFarm && a.farm_id !== filterFarm) return false;
        if (searchTerm && !a.email?.toLowerCase().includes(searchTerm.toLowerCase())) return false;
        return true;
    });

    const statusCounts = accounts.reduce((acc, a) => {
        acc[a.status] = (acc[a.status] || 0) + 1;
        return acc;
    }, {});

    return (
        <div className="page">
            <h2 className="page-title"><Users size={22} /> Аккаунты</h2>

            {/* Status summary bar */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
                <button onClick={() => setFilterStatus('')} style={{
                    padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                    fontSize: '0.72em', fontWeight: 600, fontFamily: 'inherit',
                    background: !filterStatus ? 'rgba(0,255,65,0.1)' : 'rgba(255,255,255,0.03)',
                    color: !filterStatus ? '#00ff41' : '#006611'
                }}>
                    Все ({accounts.length})
                </button>
                {Object.entries(statusConfig).map(([key, cfg]) => (
                    <button key={key} onClick={() => setFilterStatus(filterStatus === key ? '' : key)} style={{
                        padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                        fontSize: '0.72em', fontWeight: 600, fontFamily: 'inherit',
                        display: 'flex', alignItems: 'center', gap: 4,
                        background: filterStatus === key ? `${cfg.color}12` : 'rgba(255,255,255,0.03)',
                        color: filterStatus === key ? cfg.color : '#006611'
                    }}>
                        {cfg.icon} {cfg.label} ({statusCounts[key] || 0})
                    </button>
                ))}
            </div>

            {/* Filters */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                <div style={{ position: 'relative', flex: 1 }}>
                    <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#006611' }} />
                    <input className="form-input" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                        placeholder="Поиск по email..." style={{ paddingLeft: 34 }} />
                </div>
                <select className="form-input" value={filterFarm} onChange={e => setFilterFarm(e.target.value ? +e.target.value : '')}
                    style={{ width: 180 }}>
                    <option value="">Все фермы</option>
                    {farms.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
            </div>

            {/* Account list */}
            {filtered.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 48, color: '#006611' }}>
                    <Users size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />
                    {accounts.length === 0 ? 'Нет аккаунтов. Создайте на странице BIRTH.' : 'Нет совпадений по фильтру.'}
                </div>
            ) : (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{
                        display: 'grid', gridTemplateColumns: '1fr 100px 80px 80px 60px 80px',
                        padding: '8px 14px', fontSize: '0.65em', fontWeight: 600, letterSpacing: 1.5,
                        color: '#006611', textTransform: 'uppercase', borderBottom: '1px solid rgba(255,255,255,0.04)'
                    }}>
                        <span>Email</span><span>Провайдер</span><span>Статус</span><span>Прогрев</span><span>Отпр.</span><span>Ферма</span>
                    </div>
                    {filtered.map(acc => (
                        <div key={acc.id} onClick={() => setSelectedAccount(acc)} style={{
                            display: 'grid', gridTemplateColumns: '1fr 100px 80px 80px 60px 80px',
                            padding: '10px 14px', fontSize: '0.8em', cursor: 'pointer',
                            borderBottom: '1px solid rgba(255,255,255,0.02)',
                            transition: 'background 0.15s'
                        }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,255,65,0.02)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >
                            <span style={{ color: '#e8ecf4', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {acc.email}
                            </span>
                            <span style={{ color: '#009922', fontSize: '0.9em' }}>{acc.provider?.toUpperCase()}</span>
                            <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: 4,
                                color: statusConfig[acc.status]?.color || '#006611', fontSize: '0.85em', fontWeight: 600
                            }}>
                                {statusConfig[acc.status]?.icon} {statusConfig[acc.status]?.label || acc.status}
                            </span>
                            <span style={{ color: '#009922', fontSize: '0.85em' }}>День {acc.warmup_day || 0}</span>
                            <span style={{ color: '#009922', fontSize: '0.85em' }}>{acc.sent_count || 0}</span>
                            <span style={{ color: '#006611', fontSize: '0.78em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {acc.farm_name}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {/* Account detail modal */}
            {selectedAccount && (
                <div className="modal-overlay" onClick={() => setSelectedAccount(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <div style={{ fontWeight: 700 }}>{selectedAccount.email}</div>
                            <button className="btn btn-sm" onClick={() => setSelectedAccount(null)}><X size={14} /></button>
                        </div>

                        {/* Info grid */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
                            {[
                                { label: 'Провайдер', value: selectedAccount.provider?.toUpperCase(), icon: <Mail size={12} /> },
                                { label: 'Статус', value: statusConfig[selectedAccount.status]?.label, color: statusConfig[selectedAccount.status]?.color },
                                { label: 'Гео', value: selectedAccount.geo || '—', icon: <Globe size={12} /> },
                                { label: 'День прогрева', value: selectedAccount.warmup_day || 0, icon: <Flame size={12} /> },
                                { label: 'Отправлено', value: selectedAccount.sent_count || 0, icon: <Send size={12} /> },
                                { label: 'Ферма', value: selectedAccount.farm_name, icon: <Users size={12} /> },
                            ].map((item, i) => (
                                <div key={i} style={{
                                    padding: '10px 12px', borderRadius: 10,
                                    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)'
                                }}>
                                    <div style={{
                                        fontSize: '0.6em', color: '#006611', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 4,
                                        display: 'flex', alignItems: 'center', gap: 4
                                    }}>
                                        {item.icon} {item.label}
                                    </div>
                                    <div style={{ fontSize: '0.9em', fontWeight: 600, color: item.color || '#e8ecf4' }}>{item.value}</div>
                                </div>
                            ))}
                        </div>

                        {/* History placeholder */}
                        <div style={{
                            padding: '14px', borderRadius: 10, background: 'rgba(255,255,255,0.015)',
                            border: '1px solid rgba(255,255,255,0.03)', fontSize: '0.75em', color: '#006611',
                            textAlign: 'center'
                        }}>
                            <Calendar size={18} style={{ opacity: 0.3, marginBottom: 6 }} /><br />
                            История действий — bounces, отправки, прогрев — будут отображаться здесь
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
