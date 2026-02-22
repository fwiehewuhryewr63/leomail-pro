import React, { useState, useEffect } from 'react';
import {
    LayoutDashboard, Users, Flame, Send, Activity,
    Shield, FileText, Zap, TrendingUp, Database, CheckCircle, XCircle, Clock, AlertTriangle, StopCircle
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { useNavigate } from 'react-router-dom';

import { API } from '../api';

export default function Dashboard() {
    const [s, setS] = useState({});
    const { t } = useI18n();
    const navigate = useNavigate();

    useEffect(() => {
        fetch(`${API}/dashboard/stats`)
            .then(r => r.json())
            .then(setS)
            .catch(() => { });
    }, []);

    const StatCard = ({ icon: Icon, label, value, sub, color, onClick }) => (
        <div className="card card-clickable" onClick={onClick} style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Icon size={14} style={{ color: color || 'var(--accent)' }} />
                <span style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
            </div>
            <div style={{ fontSize: '1.8em', fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
            {sub && <div style={{ fontSize: '0.8em', color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div>}
        </div>
    );

    const MiniStat = ({ label, value, color }) => (
        <div style={{ textAlign: 'center', flex: 1, padding: '8px 4px' }}>
            <div style={{ fontSize: '1.4em', fontWeight: 800, color: color || 'var(--text-primary)' }}>{value}</div>
            <div style={{ fontSize: '0.7em', fontWeight: 600, letterSpacing: 0.8, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 2 }}>{label}</div>
        </div>
    );

    const proxyAlive = s.proxies_alive || 0;
    const proxyDead = s.proxies_dead || 0;
    const proxyTotal = s.total_proxies || 0;
    const proxyFree = Math.max(0, proxyAlive - (s.total_accounts || 0));

    const lifecycle = [
        { label: 'Новые', count: s.status_new || 0, color: 'var(--info)', icon: '🆕' },
        { label: 'Прогрев', count: s.status_warmup || 0, color: 'var(--warning)', icon: '🔥' },
        { label: 'WARMED', count: s.status_warmed || 0, color: 'var(--success)', icon: '✅' },
        { label: 'В работе', count: s.status_working || 0, color: 'var(--accent)', icon: '📨' },
        { label: 'Пауза', count: s.status_paused || 0, color: 'var(--text-muted)', icon: '⏸' },
        { label: 'Мёртвые', count: s.status_dead || 0, color: 'var(--danger)', icon: '💀' },
    ];

    const totalLife = lifecycle.reduce((a, l) => a + l.count, 0) || 1;

    return (
        <div className="page">
            <h2 className="page-title">
                <LayoutDashboard size={22} /> {t('dashboardTitle')}
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>v3.0</span>
            </h2>

            {/* Top stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
                <StatCard icon={Users} label="Аккаунты" value={s.total_accounts || 0}
                    sub={`${s.status_warmed || 0} warmed · ${s.status_dead || 0} мёртв.`}
                    onClick={() => navigate('/accounts')} />
                <StatCard icon={Shield} label="Прокси" value={proxyTotal}
                    sub={`🟢${proxyAlive} · 🔴${proxyDead} · 💤${proxyFree} своб.`}
                    color={proxyDead > proxyAlive ? 'var(--danger)' : 'var(--success)'}
                    onClick={() => navigate('/proxies')} />
                <StatCard icon={Flame} label="Фермы" value={s.total_farms || 0}
                    onClick={() => navigate('/farms')} />
                <StatCard icon={FileText} label="Шаблоны" value={s.total_templates || 0}
                    sub={`${s.total_databases || 0} баз`}
                    onClick={() => navigate('/templates')} />
            </div>

            {/* Proxy detail bar */}
            {proxyTotal > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Shield size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Прокси детали</span>
                    </div>
                    <div style={{ height: 8, borderRadius: 4, overflow: 'hidden', display: 'flex', marginBottom: 10, background: 'rgba(255,255,255,0.03)' }}>
                        {proxyAlive > 0 && <div style={{ width: `${(proxyAlive / proxyTotal) * 100}%`, background: 'var(--success)', transition: 'width 0.6s' }} />}
                        {proxyDead > 0 && <div style={{ width: `${(proxyDead / proxyTotal) * 100}%`, background: 'var(--danger)', transition: 'width 0.6s' }} />}
                    </div>
                    <div style={{ display: 'flex', gap: 0 }}>
                        <MiniStat label="Всего" value={proxyTotal} />
                        <MiniStat label="Живые" value={proxyAlive} color="var(--success)" />
                        <MiniStat label="Мёртвые" value={proxyDead} color="var(--danger)" />
                        <MiniStat label="Свободные" value={proxyFree} color="var(--info)" />
                    </div>
                </div>
            )}

            {/* Account lifecycle */}
            <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Activity size={14} style={{ color: 'var(--accent)' }} />
                    <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Жизненный цикл аккаунтов</span>
                </div>
                <div style={{ height: 8, borderRadius: 4, overflow: 'hidden', display: 'flex', marginBottom: 10, background: 'rgba(255,255,255,0.03)' }}>
                    {lifecycle.map((l, i) => l.count > 0 ? (
                        <div key={i} style={{ width: `${(l.count / totalLife) * 100}%`, background: l.color, transition: 'width 0.6s' }} />
                    ) : null)}
                </div>
                <div style={{ display: 'flex', gap: 0 }}>
                    {lifecycle.map((l, i) => (
                        <MiniStat key={i} label={l.label} value={l.count} color={l.color} />
                    ))}
                </div>
            </div>

            {/* Per-provider account breakdown */}
            {(s.total_accounts || 0) > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Users size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Аккаунты по провайдерам</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
                        {[
                            { id: 'gmail', name: 'Gmail', icon: '📮', color: '#EA4335' },
                            { id: 'yahoo', name: 'Yahoo', icon: '📭', color: '#6001D2' },
                            { id: 'aol', name: 'AOL', icon: '📪', color: '#FF6B00' },
                            { id: 'outlook', name: 'Outlook', icon: '📧', color: '#0078D4' },
                            { id: 'hotmail', name: 'Hotmail', icon: '📬', color: '#0078D4' },
                        ].map(p => {
                            const total = (s.by_provider || {})[p.id] || 0;
                            const statuses = (s.by_provider_status || {})[p.id] || {};
                            return (
                                <div key={p.id} style={{
                                    background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px',
                                    borderLeft: `3px solid ${p.color}`,
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                                        <span>{p.icon}</span>
                                        <span style={{ fontWeight: 700, fontSize: '0.85em', color: 'var(--text-primary)' }}>{p.name}</span>
                                        <span style={{ marginLeft: 'auto', fontWeight: 800, fontSize: '1.1em', color: p.color }}>{total}</span>
                                    </div>
                                    {total > 0 && (
                                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                            {statuses.new > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 5px', background: 'rgba(59,130,246,0.15)', color: '#60a5fa' }}>🆕{statuses.new}</span>}
                                            {(statuses.phase_1 || 0) + (statuses.phase_2 || 0) + (statuses.phase_3 || 0) + (statuses.phase_4 || 0) + (statuses.phase_5 || 0) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 5px', background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}>🔥{(statuses.phase_1 || 0) + (statuses.phase_2 || 0) + (statuses.phase_3 || 0) + (statuses.phase_4 || 0) + (statuses.phase_5 || 0)}</span>}
                                            {statuses.warmed > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 5px', background: 'rgba(16,185,129,0.15)', color: '#34d399' }}>✅{statuses.warmed}</span>}
                                            {statuses.sending > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 5px', background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>📨{statuses.sending}</span>}
                                            {(statuses.dead || 0) + (statuses.banned || 0) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 5px', background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>💀{(statuses.dead || 0) + (statuses.banned || 0)}</span>}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Active tasks */}
            {(s.active_tasks || 0) > 0 && (
                <div className="card" style={{
                    marginBottom: 16, padding: '12px 18px',
                    borderLeft: '3px solid var(--success)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <span style={{ fontWeight: 700, color: 'var(--success)' }}>⚡ {s.active_tasks} активных задач</span>
                    <button className="btn" onClick={() => {
                        fetch(`${API}/tasks/stop-all`, { method: 'POST' })
                            .then(r => r.json())
                            .then(d => {
                                alert(`Остановлено: ${d.stopped_tasks} задач, ${d.stopped_threads} потоков`);
                                fetch(`${API}/dashboard/stats`).then(r => r.json()).then(setS).catch(() => { });
                            })
                            .catch(() => alert('Ошибка остановки'));
                    }} style={{
                        background: 'var(--danger)', color: '#fff',
                        padding: '8px 20px', fontWeight: 700, fontSize: '0.9em',
                        border: 'none', borderRadius: 6, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <StopCircle size={16} /> СТОП ВСЁ
                    </button>
                </div>
            )}

            {/* Quick Actions */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {[
                    { icon: Zap, label: t('birth'), desc: t('registerAccounts'), to: '/birth' },
                    { icon: TrendingUp, label: t('warmup'), desc: t('warmupAccounts'), to: '/warmup' },
                    { icon: Send, label: t('work'), desc: t('startMailing'), to: '/work' },
                    { icon: Shield, label: t('proxies'), desc: t('manageProxies'), to: '/proxies' },
                ].map((a, i) => (
                    <div key={i} className="card card-clickable" onClick={() => navigate(a.to)}
                        style={{ textAlign: 'center', padding: '20px 14px', cursor: 'pointer' }}>
                        <a.icon size={24} style={{ color: 'var(--accent)', marginBottom: 8 }} />
                        <div style={{ fontWeight: 700, fontSize: '0.95em', marginBottom: 4, color: 'var(--text-primary)' }}>{a.label}</div>
                        <div style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>{a.desc}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}
