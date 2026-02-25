import React, { useState, useEffect } from 'react';
import {
    LayoutDashboard, Users, Flame, Send, Activity,
    Shield, FileText, Zap, TrendingUp, Database, CheckCircle, XCircle, Clock, AlertTriangle, StopCircle,
    Cpu, HardDrive, Wifi
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { useNavigate } from 'react-router-dom';

import { API } from '../api';

export default function Dashboard() {
    const [s, setS] = useState({});
    const [health, setHealth] = useState(null);
    const { t } = useI18n();
    const navigate = useNavigate();

    useEffect(() => {
        fetch(`${API}/dashboard/stats`)
            .then(r => r.json())
            .then(setS)
            .catch(() => { });
        fetch(`${API}/dashboard/health/resources`)
            .then(r => r.json())
            .then(setHealth)
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
        { label: 'Новые', count: s.status_new || 0, color: 'var(--info)' },
        { label: 'Прогрев', count: s.status_warmup || 0, color: 'var(--warning)' },
        { label: 'WARMED', count: s.status_warmed || 0, color: 'var(--success)' },
        { label: 'В работе', count: s.status_working || 0, color: 'var(--accent)' },
        { label: 'Пауза', count: s.status_paused || 0, color: 'var(--text-muted)' },
        { label: 'Мёртвые', count: s.status_dead || 0, color: 'var(--danger)' },
    ];

    const totalLife = lifecycle.reduce((a, l) => a + l.count, 0) || 1;

    return (
        <div className="page">
            <h2 className="page-title">
                <LayoutDashboard size={22} /> {t('dashboardTitle')}
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>v4.0 BLITZ</span>
            </h2>

            {/* Top stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
                <StatCard icon={Users} label="Аккаунты" value={s.total_accounts || 0}
                    sub={`${s.status_warmed || 0} warmed / ${s.status_dead || 0} мёртв.`}
                    onClick={() => navigate('/accounts')} />
                <StatCard icon={Shield} label="Прокси" value={proxyTotal}
                    sub={`${proxyAlive} живых / ${proxyDead} мёртвых / ${proxyFree} своб.`}
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
                            { id: 'gmail', name: 'Gmail', color: '#EA4335' },
                            { id: 'yahoo', name: 'Yahoo', color: '#6001D2' },
                            { id: 'aol', name: 'AOL', color: '#FF6B00' },
                            { id: 'outlook', name: 'Outlook', color: '#0078D4' },
                            { id: 'hotmail', name: 'Hotmail', color: '#0078D4' },
                        ].map(p => {
                            const total = (s.by_provider || {})[p.id] || 0;
                            const statuses = (s.by_provider_status || {})[p.id] || {};
                            return (
                                <div key={p.id} style={{
                                    background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px',
                                    borderLeft: `3px solid ${p.color}`,
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                                        <span style={{ color: p.color, fontSize: '0.7em' }}>●</span>
                                        <span style={{ fontWeight: 700, fontSize: '0.85em', color: 'var(--text-primary)' }}>{p.name}</span>
                                        <span style={{ marginLeft: 'auto', fontWeight: 800, fontSize: '1.1em', color: p.color }}>{total}</span>
                                    </div>
                                    {total > 0 && (
                                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                            {statuses.new > 0 && <span className="badge" style={{ fontSize: '0.68em', padding: '2px 6px', background: 'rgba(59,130,246,0.15)', color: '#60a5fa' }}><span style={{ color: '#60a5fa', marginRight: 2 }}>●</span>{statuses.new}</span>}
                                            {(statuses.phase_1 || 0) + (statuses.phase_2 || 0) + (statuses.phase_3 || 0) + (statuses.phase_4 || 0) + (statuses.phase_5 || 0) > 0 && <span className="badge" style={{ fontSize: '0.68em', padding: '2px 6px', background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}><span style={{ color: '#fbbf24', marginRight: 2 }}>●</span>{(statuses.phase_1 || 0) + (statuses.phase_2 || 0) + (statuses.phase_3 || 0) + (statuses.phase_4 || 0) + (statuses.phase_5 || 0)}</span>}
                                            {statuses.warmed > 0 && <span className="badge" style={{ fontSize: '0.68em', padding: '2px 6px', background: 'rgba(16,185,129,0.15)', color: '#34d399' }}><span style={{ color: '#34d399', marginRight: 2 }}>●</span>{statuses.warmed}</span>}
                                            {statuses.sending > 0 && <span className="badge" style={{ fontSize: '0.68em', padding: '2px 6px', background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}><span style={{ color: '#a78bfa', marginRight: 2 }}>●</span>{statuses.sending}</span>}
                                            {(statuses.dead || 0) + (statuses.banned || 0) > 0 && <span className="badge" style={{ fontSize: '0.68em', padding: '2px 6px', background: 'rgba(239,68,68,0.15)', color: '#f87171' }}><span style={{ color: '#f87171', marginRight: 2 }}>●</span>{(statuses.dead || 0) + (statuses.banned || 0)}</span>}
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
                    <span style={{ fontWeight: 700, color: 'var(--success)' }}>{s.active_tasks} активных задач</span>
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

            {/* ═══ RESOURCE ANALYZER ═══ */}
            {health && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Cpu size={14} style={{ color: health.overall === 'ok' ? 'var(--success)' : health.overall === 'warning' ? 'var(--warning)' : 'var(--danger)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Анализатор ресурсов</span>
                        <span style={{
                            marginLeft: 'auto', fontSize: '0.7em', fontWeight: 700, padding: '2px 10px', borderRadius: 4,
                            background: health.overall === 'ok' ? 'rgba(16,185,129,0.15)' : health.overall === 'warning' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                            color: health.overall === 'ok' ? 'var(--success)' : health.overall === 'warning' ? 'var(--warning)' : 'var(--danger)',
                        }}>
                            {health.overall === 'ok' ? '✅ OK' : health.overall === 'warning' ? '⚠️ WARNING' : '🔴 CRITICAL'}
                        </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: health.campaigns?.length ? 12 : 0 }}>
                        {/* SMS */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${health.sms?.status === 'ok' ? 'var(--success)' : health.sms?.status === 'warning' ? 'var(--warning)' : 'var(--danger)'}` }}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>📱 SMS</div>
                            {health.sms?.providers ? Object.entries(health.sms.providers).map(([name, info]) => (
                                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.82em', marginBottom: 3 }}>
                                    <span style={{ fontWeight: 600 }}>{name}</span>
                                    <span style={{ fontWeight: 700, color: typeof info.balance === 'number' && info.balance > 1 ? 'var(--success)' : 'var(--danger)' }}>
                                        {info.error ? '❌' : `$${info.balance?.toFixed?.(2) ?? info.balance}`}
                                    </span>
                                </div>
                            )) : <div style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>—</div>}
                        </div>
                        {/* Captcha */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${health.captcha?.status === 'ok' ? 'var(--success)' : 'var(--danger)'}` }}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>🧩 Captcha</div>
                            {health.captcha?.providers ? Object.entries(health.captcha.providers).map(([name, info]) => (
                                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.82em', marginBottom: 3 }}>
                                    <span style={{ fontWeight: 600 }}>{name}</span>
                                    <span style={{ fontWeight: 700, color: typeof info.balance === 'number' && info.balance > 0.5 ? 'var(--success)' : 'var(--danger)' }}>
                                        {info.error ? '❌' : `$${info.balance?.toFixed?.(2) ?? info.balance}`}
                                    </span>
                                </div>
                            )) : <div style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>—</div>}
                        </div>
                        {/* Proxies */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${health.proxies?.status === 'ok' ? 'var(--success)' : health.proxies?.status === 'warning' ? 'var(--warning)' : 'var(--danger)'}` }}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>🛡️ Прокси</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em', marginBottom: 3 }}>
                                <span style={{ fontWeight: 600 }}>Живые</span>
                                <span style={{ fontWeight: 700, color: 'var(--success)' }}>{health.proxies?.alive ?? 0}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em', marginBottom: 3 }}>
                                <span style={{ fontWeight: 600 }}>Мёртвые</span>
                                <span style={{ fontWeight: 700, color: 'var(--danger)' }}>{health.proxies?.dead ?? 0}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em' }}>
                                <span style={{ fontWeight: 600 }}>Свободные</span>
                                <span style={{ fontWeight: 700, color: 'var(--info)' }}>{health.proxies?.free ?? 0}</span>
                            </div>
                        </div>
                    </div>
                    {/* Per-campaign resources */}
                    {health.campaigns?.length > 0 && (
                        <div>
                            <div style={{ fontSize: '0.7em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Кампании</div>
                            <div style={{ display: 'grid', gap: 6 }}>
                                {health.campaigns.map(c => (
                                    <div key={c.id} style={{
                                        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px',
                                        background: 'rgba(255,255,255,0.02)', borderRadius: 6,
                                        borderLeft: `3px solid ${c.resource_status === 'ok' ? 'var(--success)' : c.resource_status === 'warning' ? 'var(--warning)' : 'var(--danger)'}`,
                                    }}>
                                        <span style={{ fontSize: '0.82em', fontWeight: 600, flex: 1 }}>{c.name}</span>
                                        {c.issues?.length > 0 && (
                                            <span style={{ fontSize: '0.72em', color: 'var(--warning)' }}>{c.issues.join(' · ')}</span>
                                        )}
                                        <span style={{
                                            fontSize: '0.68em', fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                                            background: c.resource_status === 'ok' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                            color: c.resource_status === 'ok' ? 'var(--success)' : 'var(--danger)',
                                        }}>{c.resource_status?.toUpperCase()}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Quick Actions */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
                {[
                    { icon: Zap, label: t('birth'), desc: t('registerAccounts'), to: '/birth' },
                    { icon: TrendingUp, label: 'Кампании', desc: 'Blitz Pipeline', to: '/campaigns' },
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

            {/* ═══ MAILING STATISTICS ═══ */}
            {s.mailing_stats && (s.mailing_stats.total_sent > 0 || s.mailing_stats.total_errors > 0) && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Send size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Статистика рассылок</span>
                    </div>
                    <div style={{ display: 'flex', gap: 0 }}>
                        <MiniStat label="Отправлено" value={s.mailing_stats.total_sent} color="var(--success)" />
                        <MiniStat label="Ошибки" value={s.mailing_stats.total_errors} color="var(--danger)" />
                        <MiniStat label="Bounce" value={s.mailing_stats.total_bounced} color="var(--warning)" />
                        <MiniStat label="Лимит" value={s.mailing_stats.total_limited} color="var(--info)" />
                        <MiniStat label="Inbox %" value={`${s.mailing_stats.inbox_rate}%`}
                            color={s.mailing_stats.inbox_rate >= 80 ? 'var(--success)' : s.mailing_stats.inbox_rate >= 50 ? 'var(--warning)' : 'var(--danger)'} />
                    </div>
                </div>
            )}

            {/* ═══ FARM HEALTH ═══ */}
            {s.farm_health && s.farm_health.length > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Activity size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Здоровье ферм</span>
                    </div>
                    <div style={{ display: 'grid', gap: 8 }}>
                        {s.farm_health.map(f => (
                            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 10px', background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: '0.85em', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</div>
                                    <div style={{ display: 'flex', gap: 6, marginTop: 4, fontSize: '0.72em' }}>
                                        <span style={{ color: 'var(--success)' }}>✅{f.active}</span>
                                        <span style={{ color: 'var(--accent)' }}>{f.warmed}</span>
                                        <span style={{ color: 'var(--info)' }}>{f.sending}</span>
                                        {f.banned > 0 && <span style={{ color: 'var(--danger)' }}>{f.banned}</span>}
                                    </div>
                                </div>
                                <div style={{ width: 60, textAlign: 'right' }}>
                                    <div style={{ fontSize: '1.1em', fontWeight: 800, color: f.health_pct >= 80 ? 'var(--success)' : f.health_pct >= 50 ? 'var(--warning)' : 'var(--danger)' }}>
                                        {f.health_pct}%
                                    </div>
                                    <div style={{ fontSize: '0.65em', color: 'var(--text-muted)' }}>{f.total} всего</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ═══ DATABASE PROGRESS ═══ */}
            {s.database_progress && s.database_progress.length > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Database size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Базы получателей</span>
                    </div>
                    <div style={{ display: 'grid', gap: 8 }}>
                        {s.database_progress.map(d => {
                            const pct = d.total > 0 ? Math.round(d.used / d.total * 100) : 0;
                            return (
                                <div key={d.id} style={{ padding: '6px 0' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                        <span style={{ fontSize: '0.82em', fontWeight: 600 }}>{d.name}</span>
                                        <span style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>{d.used}/{d.total} ({pct}%)</span>
                                    </div>
                                    <div className="progress-bar">
                                        <div className="progress-fill" style={{ width: `${pct}%` }} />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ═══ THREAD & TASK STATS ═══ */}
            {s.thread_stats && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Zap size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Потоки и задачи</span>
                    </div>
                    <div style={{ display: 'flex', gap: 0 }}>
                        <MiniStat label="Потоки ✅" value={s.thread_stats.completed_ok} color="var(--success)" />
                        <MiniStat label="Потоки ❌" value={s.thread_stats.completed_err} color="var(--danger)" />
                        <MiniStat label="Активные" value={s.thread_stats.running} color="var(--info)" />
                        {s.task_stats && <>
                            <MiniStat label="Задач ✅" value={s.task_stats.completed} color="var(--success)" />
                            <MiniStat label="Задач ❌" value={s.task_stats.failed} color="var(--danger)" />
                        </>}
                    </div>
                </div>
            )}
        </div>
    );
}
