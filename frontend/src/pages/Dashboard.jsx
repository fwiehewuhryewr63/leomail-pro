import React, { useState, useEffect } from 'react';
import {
    LayoutDashboard, Users, Shield, FileText, Zap, Send, Activity,
    Database, StopCircle, Flame, Link2, UserPlus, TrendingUp
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

export default function Dashboard() {
    const [s, setS] = useState({});
    const { t } = useI18n();
    const navigate = useNavigate();

    const load = () => {
        fetch(`${API}/dashboard/stats`)
            .then(r => r.json())
            .then(setS)
            .catch(() => { });
    };

    useEffect(() => {
        load();
        const iv = setInterval(load, 15000);
        return () => clearInterval(iv);
    }, []);

    /* ── helpers ── */
    const StatCard = ({ icon: Icon, label, value, sub, color, onClick }) => (
        <div className="card card-clickable" onClick={onClick} style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Icon size={14} style={{ color: color || 'var(--accent)' }} />
                <span style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
            </div>
            <div style={{ fontSize: '1.8em', fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
            {sub && <div style={{ fontSize: '0.78em', color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div>}
        </div>
    );

    const MiniStat = ({ label, value, color }) => (
        <div style={{ textAlign: 'center', flex: 1, padding: '8px 4px' }}>
            <div style={{ fontSize: '1.4em', fontWeight: 800, color: color || 'var(--text-primary)' }}>{value}</div>
            <div style={{ fontSize: '0.7em', fontWeight: 600, letterSpacing: 0.8, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 2 }}>{label}</div>
        </div>
    );

    /* ── computed ── */
    const proxyAlive = s.proxies_alive || 0;
    const proxyDead = s.proxies_dead || 0;
    const proxyTotal = s.total_proxies || 0;
    const proxyFree = Math.max(0, proxyAlive - (s.total_accounts || 0));
    const linksCount = s.total_links || 0;
    const dbCount = s.total_databases || 0;

    const ms = s.mailing_stats || {};
    const ts = s.task_stats || {};
    const ths = s.thread_stats || {};

    return (
        <div className="page">
            <h2 className="page-title">
                <LayoutDashboard size={22} /> {t('dashboardTitle')}
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>v4.0 BLITZ</span>
            </h2>

            {/* ═══ TOP STATS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 16 }}>
                <StatCard icon={Users} label="Аккаунты" value={s.total_accounts || 0}
                    sub={`${s.status_warmed || 0} warmed · ${s.status_dead || 0} мёртв.`}
                    onClick={() => navigate('/farms')} />
                <StatCard icon={Shield} label="Прокси" value={proxyTotal}
                    sub={`${proxyAlive} живых · ${proxyDead} мёртв.`}
                    color={proxyDead > proxyAlive ? 'var(--danger)' : 'var(--success)'}
                    onClick={() => navigate('/proxies')} />
                <StatCard icon={FileText} label="Шаблоны" value={s.total_templates || 0}
                    onClick={() => navigate('/templates')} />
                <StatCard icon={Link2} label="Ссылки" value={linksCount}
                    onClick={() => navigate('/links')} />
                <StatCard icon={Database} label="Базы" value={dbCount}
                    onClick={() => navigate('/databases')} />
            </div>

            {/* ═══ ACTIVE TASKS — always visible ═══ */}
            {(s.active_tasks || 0) > 0 && (
                <div className="card" style={{
                    marginBottom: 16, padding: '12px 18px',
                    borderLeft: '3px solid var(--success)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <span style={{ fontWeight: 700, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Activity size={16} className="spin" /> {s.active_tasks} активных задач
                    </span>
                    <button className="btn" onClick={() => {
                        if (!confirm('Остановить ВСЕ задачи?')) return;
                        fetch(`${API}/tasks/stop-all`, { method: 'POST' })
                            .then(r => r.json())
                            .then(d => {
                                alert(`Остановлено: ${d.stopped_tasks} задач, ${d.stopped_threads} потоков`);
                                load();
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

            {/* ═══ PROXY BAR ═══ */}
            {proxyTotal > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px', cursor: 'pointer' }} onClick={() => navigate('/proxies')}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Shield size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Прокси пул</span>
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

            {/* ═══ ACCOUNT LIFECYCLE ═══ */}
            {(s.total_accounts || 0) > 0 && (() => {
                const lifecycle = [
                    { label: 'Новые', count: s.status_new || 0, color: 'var(--info)' },
                    { label: 'Прогрев', count: s.status_warmup || 0, color: 'var(--warning)' },
                    { label: 'Warmed', count: s.status_warmed || 0, color: 'var(--success)' },
                    { label: 'Работают', count: s.status_working || 0, color: 'var(--accent)' },
                    { label: 'Пауза', count: s.status_paused || 0, color: 'var(--text-muted)' },
                    { label: 'Мёртвые', count: s.status_dead || 0, color: 'var(--danger)' },
                ];
                const totalLife = lifecycle.reduce((a, l) => a + l.count, 0) || 1;
                return (
                    <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                            <Users size={14} style={{ color: 'var(--accent)' }} />
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
                );
            })()}

            {/* ═══ PER-PROVIDER BREAKDOWN ═══ */}
            {(s.total_accounts || 0) > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Activity size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Аккаунты по провайдерам</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
                        {[
                            { id: 'gmail', name: 'Gmail', color: '#EA4335' },
                            { id: 'yahoo', name: 'Yahoo', color: '#6001D2' },
                            { id: 'aol', name: 'AOL', color: '#FF6B00' },
                            { id: 'outlook', name: 'Outlook', color: '#0078D4' },
                            { id: 'hotmail', name: 'Hotmail', color: '#0078D4' },
                        ].filter(p => ((s.by_provider || {})[p.id] || 0) > 0).map(p => {
                            const total = (s.by_provider || {})[p.id] || 0;
                            const st = (s.by_provider_status || {})[p.id] || {};
                            return (
                                <div key={p.id} style={{
                                    background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px',
                                    borderLeft: `3px solid ${p.color}`,
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ color: p.color, fontSize: '0.7em' }}>●</span>
                                        <span style={{ fontWeight: 700, fontSize: '0.85em' }}>{p.name}</span>
                                        <span style={{ marginLeft: 'auto', fontWeight: 800, fontSize: '1.1em', color: p.color }}>{total}</span>
                                    </div>
                                    {total > 0 && (
                                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                                            {(st.new || 0) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 6px', background: 'rgba(59,130,246,0.15)', color: '#60a5fa' }}>new {st.new}</span>}
                                            {(st.warmed || 0) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 6px', background: 'rgba(16,185,129,0.15)', color: '#34d399' }}>warm {st.warmed}</span>}
                                            {(st.sending || 0) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 6px', background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>send {st.sending}</span>}
                                            {((st.dead || 0) + (st.banned || 0)) > 0 && <span className="badge" style={{ fontSize: '0.65em', padding: '1px 6px', background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>dead {(st.dead || 0) + (st.banned || 0)}</span>}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ═══ MAILING STATS ═══ */}
            {ms.total_sent > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Send size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Статистика рассылок</span>
                    </div>
                    <div style={{ display: 'flex', gap: 0 }}>
                        <MiniStat label="Отправлено" value={ms.total_sent || 0} color="var(--success)" />
                        <MiniStat label="Ошибки" value={ms.total_errors || 0} color="var(--danger)" />
                        <MiniStat label="Bounce" value={ms.total_bounced || 0} color="var(--warning)" />
                        <MiniStat label="Лимит" value={ms.total_limited || 0} color="var(--info)" />
                        <MiniStat label="Inbox %" value={`${ms.inbox_rate || 0}%`}
                            color={(ms.inbox_rate || 0) >= 80 ? 'var(--success)' : (ms.inbox_rate || 0) >= 50 ? 'var(--warning)' : 'var(--danger)'} />
                    </div>
                </div>
            )}

            {/* ═══ QUICK ACTIONS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
                {[
                    { icon: UserPlus, label: t('birth'), desc: 'Пакетная регистрация', to: '/birth' },
                    { icon: TrendingUp, label: 'Кампании', desc: 'Blitz Pipeline', to: '/campaigns' },
                    { icon: Shield, label: t('proxies'), desc: 'Управление прокси', to: '/proxies' },
                    { icon: Flame, label: 'Фермы', desc: 'Организация акков', to: '/farms' },
                ].map((a, i) => (
                    <div key={i} className="card card-clickable" onClick={() => navigate(a.to)}
                        style={{ textAlign: 'center', padding: '20px 14px', cursor: 'pointer' }}>
                        <a.icon size={24} style={{ color: 'var(--accent)', marginBottom: 8 }} />
                        <div style={{ fontWeight: 700, fontSize: '0.95em', marginBottom: 4, color: 'var(--text-primary)' }}>{a.label}</div>
                        <div style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>{a.desc}</div>
                    </div>
                ))}
            </div>

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

            {/* ═══ FARM HEALTH ═══ */}
            {s.farm_health && s.farm_health.length > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Flame size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Здоровье ферм</span>
                    </div>
                    <div style={{ display: 'grid', gap: 8 }}>
                        {s.farm_health.map(f => (
                            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 10px', background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: '0.85em', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</div>
                                    <div style={{ display: 'flex', gap: 6, marginTop: 4, fontSize: '0.72em' }}>
                                        <span style={{ color: 'var(--success)' }}>✅{f.active}</span>
                                        <span style={{ color: 'var(--accent)' }}>{f.warmed} warm</span>
                                        <span style={{ color: 'var(--info)' }}>{f.sending} send</span>
                                        {f.banned > 0 && <span style={{ color: 'var(--danger)' }}>💀{f.banned}</span>}
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

            {/* ═══ THREAD & TASK STATS ═══ */}
            {(ths.completed_ok > 0 || ths.completed_err > 0 || ts.completed > 0) && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Zap size={14} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Потоки и задачи</span>
                    </div>
                    <div style={{ display: 'flex', gap: 0 }}>
                        <MiniStat label="Успешно" value={ths.completed_ok || 0} color="var(--success)" />
                        <MiniStat label="Ошибки" value={ths.completed_err || 0} color="var(--danger)" />
                        <MiniStat label="Активные" value={ths.running || 0} color="var(--info)" />
                        <MiniStat label="Задачи ✅" value={ts.completed || 0} color="var(--success)" />
                        <MiniStat label="Задачи ❌" value={ts.failed || 0} color="var(--danger)" />
                    </div>
                </div>
            )}
        </div>
    );
}
