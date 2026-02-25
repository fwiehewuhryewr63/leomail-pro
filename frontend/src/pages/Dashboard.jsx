import React, { useState, useEffect } from 'react';
import {
    LayoutDashboard, Users, Shield, FileText, Zap, Send, Activity,
    Database, StopCircle, Flame, Link2, UserPlus, TrendingUp, Cpu, AlertTriangle
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

export default function Dashboard() {
    const [s, setS] = useState({});
    const [health, setHealth] = useState(null);
    const { t } = useI18n();
    const navigate = useNavigate();

    const load = () => {
        fetch(`${API}/dashboard/stats`)
            .then(r => r.json())
            .then(setS)
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

    const SectionHeader = ({ icon: Icon, label, badge, badgeColor }) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon size={14} style={{ color: 'var(--accent)' }} />
            <span style={{ fontSize: '0.75em', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
            {badge && (
                <span style={{
                    marginLeft: 'auto', fontSize: '0.7em', fontWeight: 700, padding: '2px 10px', borderRadius: 4,
                    background: `${badgeColor || 'var(--success)'}22`,
                    color: badgeColor || 'var(--success)',
                }}>{badge}</span>
            )}
        </div>
    );

    /* helper: statusColor for resource health */
    const sc = (status) => status === 'ok' ? 'var(--success)' : status === 'warning' ? 'var(--warning)' : 'var(--danger)';

    /* ── computed ── */
    const ms = s.mailing_stats || {};
    const ts = s.task_stats || {};
    const ths = s.thread_stats || {};

    return (
        <div className="page">
            <h2 className="page-title">
                <LayoutDashboard size={22} /> {t('dashboardTitle')}
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>v4.0 BLITZ</span>
            </h2>

            {/* ═══ 1. ACTIVE TASKS BANNER ═══ */}
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

            {/* ═══ 2. TOP STATS — inventory counts only, no proxy ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
                <StatCard icon={Users} label="Аккаунты" value={s.total_accounts || 0}
                    sub={`${s.status_warmed || 0} warmed · ${s.status_dead || 0} мёртв.`}
                    onClick={() => navigate('/farms')} />
                <StatCard icon={Flame} label="Фермы" value={s.total_farms || 0}
                    onClick={() => navigate('/farms')} />
                <StatCard icon={FileText} label="Шаблоны" value={s.total_templates || 0}
                    onClick={() => navigate('/templates')} />
                <StatCard icon={Link2} label="Ссылки" value={s.total_links || 0}
                    onClick={() => navigate('/links')} />
                <StatCard icon={Database} label="Базы" value={s.total_databases || 0}
                    onClick={() => navigate('/databases')} />
            </div>

            {/* ═══ 3. RESOURCE ANALYZER — SMS + Captcha + Proxies (ONE place) ═══ */}
            {health && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <SectionHeader icon={Cpu} label="Анализатор ресурсов"
                        badge={health.overall === 'ok' ? 'OK' : health.overall === 'warning' ? 'WARNING' : 'CRITICAL'}
                        badgeColor={sc(health.overall)} />
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                        {/* SMS */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${sc(health.sms?.status)}` }}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>SMS</div>
                            {health.sms?.providers?.length > 0 ? (
                                <>
                                    {health.sms.providers.map(p => (
                                        <div key={p.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em', marginBottom: 3 }}>
                                            <span style={{ fontWeight: 600 }}>{p.name}</span>
                                            <span style={{ fontWeight: 700, color: p.error ? 'var(--danger)' : p.balance > 1 ? 'var(--success)' : 'var(--warning)' }}>
                                                {p.error ? 'err' : `$${p.balance}`}
                                            </span>
                                        </div>
                                    ))}
                                    <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 4, borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 4 }}>
                                        ~{health.sms?.estimated_accounts || 0} регистраций
                                    </div>
                                </>
                            ) : <div style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>Не настроено</div>}
                        </div>
                        {/* Captcha */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${sc(health.captcha?.status)}` }}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Captcha</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em' }}>
                                <span style={{ fontWeight: 600 }}>Баланс</span>
                                <span style={{ fontWeight: 700, color: (health.captcha?.balance || 0) > 0.5 ? 'var(--success)' : 'var(--danger)' }}>
                                    ${health.captcha?.balance || 0}
                                </span>
                            </div>
                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 4 }}>~{health.captcha?.estimated_solves || 0} решений</div>
                        </div>
                        {/* Proxies — единственное место */}
                        <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px', borderLeft: `3px solid ${sc(health.proxies?.status)}`, cursor: 'pointer' }} onClick={() => navigate('/proxies')}>
                            <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Прокси</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em', marginBottom: 3 }}>
                                <span style={{ fontWeight: 600 }}>Всего</span>
                                <span style={{ fontWeight: 700 }}>{health.proxies?.total ?? 0}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em', marginBottom: 3 }}>
                                <span style={{ fontWeight: 600 }}>Живые</span>
                                <span style={{ fontWeight: 700, color: 'var(--success)' }}>{health.proxies?.alive ?? 0}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82em' }}>
                                <span style={{ fontWeight: 600 }}>Мёртвые</span>
                                <span style={{ fontWeight: 700, color: 'var(--danger)' }}>{health.proxies?.dead ?? 0}</span>
                            </div>
                        </div>
                    </div>
                    {/* Per-campaign resource health */}
                    {health.campaigns?.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                            <div style={{ fontSize: '0.7em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Ресурсы кампаний</div>
                            <div style={{ display: 'grid', gap: 6 }}>
                                {health.campaigns.map(c => (
                                    <div key={c.id} onClick={() => navigate(`/campaigns/${c.id}`)} style={{
                                        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px', cursor: 'pointer',
                                        background: 'rgba(255,255,255,0.02)', borderRadius: 6,
                                        borderLeft: `3px solid ${sc(c.resource_status)}`,
                                    }}>
                                        <span style={{ fontSize: '0.82em', fontWeight: 600, flex: 1 }}>{c.name}</span>
                                        <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>
                                            📝{c.templates} · 🔗{c.links} · 📫{c.recipients_remaining}
                                        </span>
                                        {c.issues?.length > 0 && (
                                            <span style={{ fontSize: '0.72em', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                                <AlertTriangle size={12} /> {c.issues.join(' · ')}
                                            </span>
                                        )}
                                        <span style={{
                                            fontSize: '0.68em', fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                                            background: c.resource_status === 'ok' ? 'rgba(16,185,129,0.15)' : c.resource_status === 'warning' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                                            color: sc(c.resource_status),
                                        }}>{c.resource_status?.toUpperCase()}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ═══ 4. ACCOUNT LIFECYCLE ═══ */}
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
                        <SectionHeader icon={Users} label="Жизненный цикл аккаунтов" />
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

            {/* ═══ 5. PER-PROVIDER BREAKDOWN ═══ */}
            {(s.total_accounts || 0) > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <SectionHeader icon={Activity} label="Аккаунты по провайдерам" />
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

            {/* ═══ 6. MAILING STATS — always show if any data ═══ */}
            <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                <SectionHeader icon={Send} label="Рассылка" />
                <div style={{ display: 'flex', gap: 0 }}>
                    <MiniStat label="Отправлено" value={ms.total_sent || 0} color="var(--success)" />
                    <MiniStat label="Ошибки" value={ms.total_errors || 0} color="var(--danger)" />
                    <MiniStat label="Bounce" value={ms.total_bounced || 0} color="var(--warning)" />
                    <MiniStat label="Лимит" value={ms.total_limited || 0} color="var(--info)" />
                    <MiniStat label="Inbox %"
                        value={`${ms.inbox_rate || 0}%`}
                        color={(ms.inbox_rate || 0) >= 80 ? 'var(--success)' : (ms.inbox_rate || 0) >= 50 ? 'var(--warning)' : 'var(--danger)'} />
                </div>
            </div>

            {/* ═══ 7. THREAD & TASK STATS — always show ═══ */}
            <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                <SectionHeader icon={Zap} label="Потоки и задачи" />
                <div style={{ display: 'flex', gap: 0 }}>
                    <MiniStat label="Потоки ✅" value={ths.completed_ok || 0} color="var(--success)" />
                    <MiniStat label="Потоки ❌" value={ths.completed_err || 0} color="var(--danger)" />
                    <MiniStat label="Активные" value={ths.running || 0} color="var(--info)" />
                    <MiniStat label="Задачи ✅" value={ts.completed || 0} color="var(--success)" />
                    <MiniStat label="Задачи ❌" value={ts.failed || 0} color="var(--danger)" />
                    <MiniStat label="Запущено" value={ts.running || 0} color="var(--accent)" />
                </div>
            </div>

            {/* ═══ 8. DATABASE PROGRESS ═══ */}
            {s.database_progress && s.database_progress.length > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <SectionHeader icon={Database} label="Базы получателей" />
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

            {/* ═══ 9. FARM HEALTH ═══ */}
            {s.farm_health && s.farm_health.length > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '14px 18px' }}>
                    <SectionHeader icon={Flame} label="Здоровье ферм" />
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

            {/* ═══ 10. QUICK ACTIONS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                {[
                    { icon: UserPlus, label: t('birth'), desc: 'Авторег', to: '/birth' },
                    { icon: TrendingUp, label: 'Кампании', desc: 'Blitz Pipeline', to: '/campaigns' },
                    { icon: Shield, label: t('proxies'), desc: 'Прокси', to: '/proxies' },
                    { icon: Flame, label: 'Фермы', desc: 'Аккаунты', to: '/farms' },
                    { icon: FileText, label: 'Шаблоны', desc: 'Писем', to: '/templates' },
                    { icon: Link2, label: 'Ссылки', desc: 'Для писем', to: '/links' },
                ].map((a, i) => (
                    <div key={i} className="card card-clickable" onClick={() => navigate(a.to)}
                        style={{ textAlign: 'center', padding: '16px 10px', cursor: 'pointer' }}>
                        <a.icon size={20} style={{ color: 'var(--accent)', marginBottom: 6 }} />
                        <div style={{ fontWeight: 700, fontSize: '0.88em', color: 'var(--text-primary)' }}>{a.label}</div>
                        <div style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>{a.desc}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}
