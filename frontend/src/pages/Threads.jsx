import React, { useState, useEffect } from 'react';
import { Layers, Cpu, RefreshCw, Play, CheckCircle, XCircle, Clock, Eye, Monitor, StopCircle, Square } from 'lucide-react';

import { API } from '../api';

const statusMap = {
    running: { icon: Play, color: 'var(--accent)', label: 'Работает', bg: 'rgba(212,168,38,0.08)' },
    done: { icon: CheckCircle, color: 'var(--success)', label: 'Готово', bg: 'rgba(0,210,160,0.06)' },
    error: { icon: XCircle, color: 'var(--danger)', label: 'Ошибка', bg: 'rgba(255,107,74,0.06)' },
    stopped: { icon: Square, color: 'var(--warning)', label: 'Стоп', bg: 'rgba(255,180,0,0.06)' },
    idle: { icon: Clock, color: 'var(--text-muted)', label: 'Ожидание', bg: 'transparent' },
};

const GROUPS = [
    { key: 'birth', label: '🍼 Авторегистрация', color: '#6C5CE7', stopUrl: '/birth/stop', statusUrl: '/birth/status' },
    { key: 'warmup', label: '🔥 Прогрев', color: '#E17055', stopUrl: '/warmup/stop', statusUrl: '/warmup/status' },
    { key: 'work', label: '📨 Рассылка', color: '#00B894', stopUrl: '/work/stop', statusUrl: '/work/status' },
];

const formatTime = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

export default function Threads() {
    const [health, setHealth] = useState(null);
    const [threads, setThreads] = useState([]);
    const [activePages, setActivePages] = useState([]);
    const [error, setError] = useState(false);
    const [screenshot, setScreenshot] = useState(null);
    const [statuses, setStatuses] = useState({});  // { birth: {...}, warmup: {...}, work: {...} }
    const [stopConfirm, setStopConfirm] = useState(null);  // { group: 'birth', ... }

    const load = () => {
        setError(false);
        fetch(`${API}/resources/health`)
            .then(r => { if (!r.ok) throw new Error(); return r.json(); })
            .then(setHealth)
            .catch(() => setError(true));
        fetch(`${API}/resources/active-threads`)
            .then(r => r.json())
            .then(d => setThreads(Array.isArray(d) ? d : []))
            .catch(() => { });
        fetch(`${API}/birth/active-pages`)
            .then(r => r.json())
            .then(d => setActivePages(d.active || []))
            .catch(() => { });

        // Load all group statuses
        GROUPS.forEach(g => {
            fetch(`${API}${g.statusUrl}`)
                .then(r => r.json())
                .then(d => setStatuses(prev => ({ ...prev, [g.key]: d })))
                .catch(() => { });
        });
    };

    useEffect(() => { load(); const iv = setInterval(load, 20000); return () => clearInterval(iv); }, []);

    const handleStop = (groupKey, mode) => {
        const group = GROUPS.find(g => g.key === groupKey);
        if (!group) return;
        fetch(`${API}${group.stopUrl}?mode=${mode}`, { method: 'POST' })
            .then(r => r.json())
            .then(() => { setStopConfirm(null); load(); })
            .catch(() => { });
    };

    const viewScreenshot = (threadId) => {
        const ts = Date.now();
        setScreenshot({ threadId, url: `${API}/birth/screenshot/${threadId}?t=${ts}`, loading: true });
    };

    const refreshScreenshot = () => {
        if (!screenshot) return;
        const ts = Date.now();
        setScreenshot({ ...screenshot, url: `${API}/birth/screenshot/${screenshot.threadId}?t=${ts}`, loading: true });
    };

    const statusColor = { healthy: 'var(--success)', warning: 'var(--warning)', critical: 'var(--danger)' };

    const Bar = ({ value, max, color }) => (
        <div style={{ height: 10, borderRadius: 5, background: 'var(--bg-input)', flex: 1, overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
            <div style={{
                width: `${Math.min(100, (value / max) * 100)}%`, height: '100%', borderRadius: 5,
                background: `linear-gradient(90deg, ${color}90, ${color})`, transition: 'width 0.5s'
            }} />
        </div>
    );

    // Group threads by type, only running ones
    const runningByType = {};
    const recentByType = {};
    threads.forEach(t => {
        const type = t.type || 'unknown';
        if (t.status === 'running') {
            if (!runningByType[type]) runningByType[type] = [];
            runningByType[type].push(t);
        } else {
            if (!recentByType[type]) recentByType[type] = [];
            recentByType[type].push(t);
        }
    });

    // Renumber running threads sequentially per group
    Object.values(runningByType).forEach(arr => {
        arr.forEach((t, i) => { t._displayIndex = i + 1; });
    });

    const totalRunning = threads.filter(t => t.status === 'running').length;

    if (error) {
        return (
            <div className="page">
                <h2 className="page-title"><Layers size={22} /> Потоки</h2>
                <div className="card" style={{ textAlign: 'center', padding: 40 }}>
                    <Cpu size={40} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
                    <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>Сервер не отвечает</p>
                    <button className="btn btn-primary" onClick={load}><RefreshCw size={14} /> Повторить</button>
                </div>
            </div>
        );
    }

    return (
        <div className="page">
            <h2 className="page-title">
                <Layers size={22} /> Потоки
                {totalRunning > 0 && (
                    <span style={{
                        marginLeft: 12, fontSize: '0.6em', padding: '4px 12px',
                        borderRadius: 20, background: 'var(--accent)', color: '#000',
                        fontWeight: 800, verticalAlign: 'middle',
                    }}>
                        {totalRunning} активных
                    </span>
                )}
            </h2>

            {/* Stop Confirmation Modal */}
            {stopConfirm && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
                    background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    backdropFilter: 'blur(4px)',
                }} onClick={() => setStopConfirm(null)}>
                    <div className="card" style={{
                        maxWidth: 420, width: '90%', padding: '24px',
                    }} onClick={e => e.stopPropagation()}>
                        <div style={{
                            fontWeight: 800, fontSize: '1.1em', color: 'var(--danger)',
                            marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8,
                        }}>
                            <StopCircle size={20} /> Остановить {GROUPS.find(g => g.key === stopConfirm)?.label}?
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
                            <button className="btn" onClick={() => handleStop(stopConfirm, 'instant')}
                                style={{
                                    padding: '14px 20px', background: 'var(--danger)', color: '#fff',
                                    fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8,
                                }}>
                                ⚡ Мгновенно — убить все потоки сейчас
                            </button>
                            <button className="btn" onClick={() => handleStop(stopConfirm, 'graceful')}
                                style={{
                                    padding: '14px 20px', background: 'var(--warning)', color: '#000',
                                    fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8,
                                }}>
                                ⏳ Дождаться завершения текущих потоков
                            </button>
                        </div>
                        <button className="btn" onClick={() => setStopConfirm(null)}
                            style={{ width: '100%', padding: '10px', fontSize: '0.9em' }}>
                            Отмена
                        </button>
                    </div>
                </div>
            )}

            {/* Screenshot Modal */}
            {screenshot && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
                    background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    backdropFilter: 'blur(4px)',
                }} onClick={() => setScreenshot(null)}>
                    <div style={{
                        maxWidth: '90vw', maxHeight: '90vh', position: 'relative',
                        border: '2px solid var(--border-hover)', borderRadius: 12, overflow: 'hidden',
                        background: 'var(--bg-card)',
                    }} onClick={e => e.stopPropagation()}>
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '10px 16px', background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-default)',
                        }}>
                            <span style={{ fontWeight: 700, color: 'var(--text-accent)', fontSize: '0.9em' }}>
                                <Eye size={14} /> Поток #{screenshot.threadId} — Live View
                            </span>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button className="btn btn-sm" onClick={refreshScreenshot}><RefreshCw size={12} /> Обновить</button>
                                <button className="btn btn-sm btn-danger" onClick={() => setScreenshot(null)}>✕</button>
                            </div>
                        </div>
                        <img
                            src={screenshot.url}
                            alt="Browser Screenshot"
                            style={{ maxWidth: '85vw', maxHeight: '80vh', display: 'block' }}
                            onLoad={() => setScreenshot(s => s ? { ...s, loading: false } : null)}
                            onError={() => setScreenshot(s => s ? { ...s, loading: false } : null)}
                        />
                        {screenshot.loading && (
                            <div style={{
                                position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                                color: 'var(--text-accent)', fontWeight: 700, fontSize: '1.1em',
                            }}>Загрузка...</div>
                        )}
                    </div>
                </div>
            )}

            {/* Server health */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        {health && (
                            <>
                                <div style={{
                                    width: 10, height: 10, borderRadius: '50%',
                                    background: statusColor[health.status] || 'var(--text-muted)',
                                    boxShadow: `0 0 8px ${statusColor[health.status]}60`,
                                }} />
                                <span style={{ fontWeight: 700, color: statusColor[health.status] }}>
                                    {health.status === 'healthy' ? '● Сервер OK' : health.status === 'warning' ? '● Нагрузка' : '● Перегрузка'}
                                </span>
                            </>
                        )}
                    </div>
                    <button className="btn btn-sm" onClick={load}><RefreshCw size={14} /> Обновить</button>
                </div>
                {health?.resources && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85em', marginBottom: 6, fontWeight: 600 }}>
                                <span>RAM</span>
                                <span style={{ color: health.resources.ram_used_percent > 80 ? 'var(--danger)' : 'var(--success)' }}>
                                    {health.resources.ram_available_mb} MB свободно · {health.resources.ram_used_percent}%
                                </span>
                            </div>
                            <Bar value={health.resources.ram_used_percent} max={100}
                                color={health.resources.ram_used_percent > 80 ? 'var(--danger)' : 'var(--success)'} />
                        </div>
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85em', marginBottom: 6, fontWeight: 600 }}>
                                <span>CPU</span>
                                <span style={{ color: health.resources.cpu_used_percent > 80 ? 'var(--danger)' : 'var(--success)' }}>
                                    {health.resources.cpu_cores} ядер · {health.resources.cpu_used_percent}%
                                </span>
                            </div>
                            <Bar value={health.resources.cpu_used_percent} max={100}
                                color={health.resources.cpu_used_percent > 80 ? 'var(--danger)' : 'var(--success)'} />
                        </div>
                    </div>
                )}
            </div>

            {/* Process groups */}
            {GROUPS.map(group => {
                const groupRunning = runningByType[group.key] || [];
                const groupRecent = (recentByType[group.key] || []).slice(0, 10);
                const groupStatus = statuses[group.key];
                const isActive = groupStatus?.running || groupRunning.length > 0;

                if (!isActive && groupRecent.length === 0) return null;

                return (
                    <div key={group.key} className="card" style={{
                        marginBottom: 16,
                        borderLeft: isActive ? `3px solid ${group.color}` : undefined,
                    }}>
                        {/* Group header with stop button */}
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            marginBottom: groupRunning.length > 0 ? 14 : 8,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <span style={{ fontWeight: 800, fontSize: '1em', color: group.color }}>
                                    {group.label}
                                </span>
                                {isActive && (
                                    <span style={{
                                        fontSize: '0.75em', padding: '2px 10px', borderRadius: 12,
                                        background: `${group.color}22`, color: group.color,
                                        fontWeight: 700, border: `1px solid ${group.color}44`,
                                    }}>
                                        {groupRunning.length} потоков
                                    </span>
                                )}
                                {groupStatus?.running && (
                                    <span style={{ fontSize: '0.8em', color: 'var(--text-secondary)' }}>
                                        — {groupStatus.completed}/{groupStatus.total} готово, ошибок: {groupStatus.failed}
                                    </span>
                                )}
                                {isActive && (
                                    <div style={{
                                        width: 8, height: 8, borderRadius: '50%', background: group.color,
                                        animation: 'pulse 1.5s infinite', boxShadow: `0 0 6px ${group.color}`,
                                    }} />
                                )}
                            </div>
                            {isActive && (
                                <button className="btn" onClick={() => setStopConfirm(group.key)}
                                    style={{
                                        background: 'var(--danger)', color: '#fff',
                                        padding: '6px 16px', fontWeight: 700, fontSize: '0.85em',
                                        border: 'none', borderRadius: 6,
                                        display: 'flex', alignItems: 'center', gap: 5,
                                    }}>
                                    <StopCircle size={14} /> СТОП
                                </button>
                            )}
                        </div>

                        {/* Running threads */}
                        {groupRunning.length > 0 && (
                            <div style={{ display: 'grid', gap: 6, marginBottom: groupRecent.length > 0 ? 14 : 0 }}>
                                {groupRunning.map(t => {
                                    const s = statusMap[t.status] || statusMap.idle;
                                    const Icon = s.icon;
                                    const hasLiveView = activePages.includes(t.id);
                                    return (
                                        <div key={t.id} style={{
                                            display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                                            background: s.bg, borderRadius: 8, border: '1px solid var(--border-default)',
                                        }}>
                                            <div style={{
                                                width: 32, height: 32, borderRadius: 6, display: 'flex',
                                                alignItems: 'center', justifyContent: 'center',
                                                background: `${group.color}15`, border: `1px solid ${group.color}33`,
                                                fontWeight: 800, fontSize: '0.85em', color: group.color,
                                            }}>
                                                #{t._displayIndex}
                                            </div>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2 }}>
                                                    {t.email && <span style={{ fontSize: '0.85em', color: 'var(--text-primary)', fontWeight: 600 }}>{t.email}</span>}
                                                </div>
                                                <div style={{ fontSize: '0.82em', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {t.action || 'Работает...'}
                                                </div>
                                                {t.proxy && (
                                                    <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 1 }}>🔗 {t.proxy}</div>
                                                )}
                                            </div>
                                            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                                {hasLiveView && (
                                                    <button className="btn btn-sm btn-success" onClick={() => viewScreenshot(t.id)}
                                                        title="Посмотреть браузер" style={{ padding: '4px 10px' }}>
                                                        <Eye size={13} /> View
                                                    </button>
                                                )}
                                            </div>
                                            <span style={{ fontSize: '0.75em', color: 'var(--text-muted)', fontWeight: 600 }}>{formatTime(t.updated)}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {/* Recent completed/failed threads (compact) */}
                        {groupRecent.length > 0 && (
                            <div style={{ display: 'grid', gap: 3 }}>
                                <div style={{ fontSize: '0.75em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
                                    Недавние
                                </div>
                                {groupRecent.map(t => {
                                    const s = statusMap[t.status] || statusMap.idle;
                                    const Icon = s.icon;
                                    return (
                                        <div key={t.id} style={{
                                            display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
                                            borderRadius: 6, border: '1px solid var(--border-subtle)', background: s.bg,
                                        }}>
                                            <Icon size={12} style={{ color: s.color, flexShrink: 0 }} />
                                            <span style={{
                                                fontSize: '0.75em', fontWeight: 700, minWidth: 50, color: s.color,
                                                padding: '1px 6px', borderRadius: 4,
                                            }}>{s.label}</span>
                                            <span style={{ flex: 1, fontSize: '0.75em', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {t.error || t.action || t.email || '—'}
                                            </span>
                                            <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', flexShrink: 0 }}>{formatTime(t.updated)}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {/* Empty state */}
                        {groupRunning.length === 0 && groupRecent.length === 0 && (
                            <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: '0.9em' }}>
                                Нет активных потоков
                            </div>
                        )}
                    </div>
                );
            })}

            {/* No activity at all */}
            {totalRunning === 0 && threads.length === 0 && (
                <div className="card" style={{ textAlign: 'center', padding: 40 }}>
                    <Cpu size={32} style={{ color: 'var(--text-muted)', marginBottom: 10 }} />
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.95em' }}>Нет активных процессов</div>
                </div>
            )}
        </div>
    );
}
