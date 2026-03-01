import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';


// ── Status config ──
const STATUS_CONFIG = {
    registered: { label: 'Зарегистрирован ✓', color: '#10B981', icon: '✓' },
    done: { label: 'Готово ✓', color: '#10B981', icon: '✓' },
    sms: { label: 'SMS код...', color: '#06B6D4', icon: '↔' },
    captcha: { label: 'Captcha...', color: '#F59E0B', icon: '🛡' },
    running: { label: 'Работает...', color: '#06B6D4', icon: '↻' },
    error: { label: 'Ошибка', color: '#EF4444', icon: '✗' },
    queued: { label: 'В очереди', color: '#6B7280', icon: '⏳' },
    proxy_timeout: { label: 'Proxy timeout', color: '#EF4444', icon: '⏱' },
};

function getStatusInfo(status, action) {
    if (status === 'done') return STATUS_CONFIG.done;
    if (status === 'error') return STATUS_CONFIG.error;
    if (status === 'running') {
        if (action?.toLowerCase().includes('sms')) return STATUS_CONFIG.sms;
        if (action?.toLowerCase().includes('captcha')) return STATUS_CONFIG.captcha;
        return STATUS_CONFIG.running;
    }
    return STATUS_CONFIG[status] || STATUS_CONFIG.queued;
}

function formatElapsed(startTime) {
    if (!startTime) return '';
    const diff = Math.max(0, Math.floor((Date.now() - new Date(startTime).getTime()) / 1000));
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function maskProxy(proxy) {
    if (!proxy) return '—';
    // "192.168.1.100:8080" → "192.168.*.*"
    const parts = proxy.split(':')[0].split('.');
    if (parts.length === 4) return `${parts[0]}.${parts[1]}.*.*`;
    return proxy.substring(0, 12) + '...';
}

const TASK_TYPE_LABELS = {
    birth: 'Авторег',
    warmup: 'Прогрев',
    work: 'Рассылка',
};


export default function Threads() {
    const [threads, setThreads] = useState([]);
    const [collapsedTasks, setCollapsedTasks] = useState({});
    const [selectedThread, setSelectedThread] = useState(null);
    const [screenshotUrl, setScreenshotUrl] = useState(null);
    const [screenshotError, setScreenshotError] = useState(false);
    const [activePages, setActivePages] = useState([]);
    const screenshotTimerRef = useRef(null);

    // ── Load threads ──
    const load = useCallback(() => {
        fetch(`${API}/resources/active-threads`)
            .then(r => r.json())
            .then(d => setThreads(Array.isArray(d) ? d : []))
            .catch(() => { });
    }, []);

    // ── Load active browser pages ──
    const loadActivePages = useCallback(() => {
        fetch(`${API}/birth/active-pages`)
            .then(r => r.json())
            .then(d => setActivePages(d.active || []))
            .catch(() => { });
    }, []);

    useEffect(() => {
        load();
        loadActivePages();
        const iv = setInterval(() => { load(); loadActivePages(); }, 3000);
        return () => clearInterval(iv);
    }, [load, loadActivePages]);

    // ── Screenshot polling ──
    useEffect(() => {
        if (screenshotTimerRef.current) clearInterval(screenshotTimerRef.current);
        if (selectedThread && activePages.includes(selectedThread)) {
            const fetchScreenshot = () => {
                fetch(`${API}/birth/screenshot/${selectedThread}`)
                    .then(r => {
                        if (r.ok && r.headers.get('content-type')?.includes('image')) {
                            return r.blob();
                        }
                        throw new Error('No screenshot');
                    })
                    .then(blob => {
                        setScreenshotUrl(URL.createObjectURL(blob));
                        setScreenshotError(false);
                    })
                    .catch(() => {
                        setScreenshotError(true);
                    });
            };
            fetchScreenshot();
            screenshotTimerRef.current = setInterval(fetchScreenshot, 2000);
        } else {
            setScreenshotUrl(null);
            setScreenshotError(false);
        }
        return () => { if (screenshotTimerRef.current) clearInterval(screenshotTimerRef.current); };
    }, [selectedThread, activePages]);

    // ── Group by task_id ──
    const taskGroups = {};
    threads.forEach(t => {
        const key = t.task_id || 0;
        if (!taskGroups[key]) {
            taskGroups[key] = {
                task_id: key,
                task_type: t.task_type || 'birth',
                provider: t.provider || '',
                threads: [],
            };
        }
        taskGroups[key].threads.push(t);
    });

    // Sort: active tasks first, then by task_id desc
    const sortedGroups = Object.values(taskGroups).sort((a, b) => {
        const aRunning = a.threads.some(t => t.status === 'running');
        const bRunning = b.threads.some(t => t.status === 'running');
        if (aRunning && !bRunning) return -1;
        if (!aRunning && bRunning) return 1;
        return b.task_id - a.task_id;
    });

    // ── Stats ──
    const running = threads.filter(t => t.status === 'running').length;
    const done = threads.filter(t => t.status === 'done').length;
    const failed = threads.filter(t => t.status === 'error').length;
    const total = done + failed;
    const rate = total > 0 ? ((done / total) * 100).toFixed(0) : '—';

    const toggleTask = (taskId) => {
        setCollapsedTasks(prev => ({ ...prev, [taskId]: !prev[taskId] }));
    };

    const clearThreads = () => {
        setThreads([]);
        setSelectedThread(null);
    };

    const hasPreview = selectedThread && activePages.includes(selectedThread);

    return (
        <div className="page" style={{ display: 'flex', gap: 16, height: 'calc(100vh - 100px)' }}>
            {/* ── Left: Thread list ── */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <h2 style={{ margin: 0, fontSize: '1.4em', fontWeight: 300, fontStyle: 'italic', color: 'var(--text-primary)' }}>
                        Потоки
                        {running > 0 && (
                            <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                fontSize: '0.45em', padding: '3px 10px', borderRadius: 20,
                                color: '#10B981', fontWeight: 700, marginLeft: 12,
                            }}>
                                <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 6px #10B981', animation: 'pulse 1.5s infinite' }} />
                                {running} active
                            </span>
                        )}
                    </h2>
                    <button className="btn" onClick={clearThreads} style={{
                        padding: '5px 14px', fontSize: '0.8em', fontWeight: 600,
                        border: '1px solid var(--border-default)', background: 'transparent',
                    }}>Clear</button>
                </div>

                {/* Stats bar */}
                <div className="card" style={{
                    padding: '8px 16px', marginBottom: 12,
                    fontSize: '0.82em', color: 'var(--text-secondary)',
                    display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                }}>
                    <span style={{ color: '#10B981', fontWeight: 700 }}>{done} ✓</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span style={{ color: '#EF4444', fontWeight: 700 }}>{failed} ✗</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span style={{ color: '#06B6D4', fontWeight: 700 }}>{running} ↻</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span style={{ fontWeight: 700 }}>{rate}% success</span>
                </div>

                {/* Thread groups */}
                <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {sortedGroups.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
                            <div style={{ fontSize: '2em', marginBottom: 8 }}>⊘</div>
                            <div style={{ fontSize: '0.95em' }}>Нет активных потоков</div>
                            <div style={{ fontSize: '0.8em', marginTop: 4, opacity: 0.6 }}>Запустите авторег чтобы увидеть потоки</div>
                        </div>
                    ) : (
                        sortedGroups.map(group => {
                            const isRunning = group.threads.some(t => t.status === 'running');
                            const isCollapsed = collapsedTasks[group.task_id] && !isRunning;
                            const groupDone = group.threads.filter(t => t.status === 'done').length;
                            const groupFailed = group.threads.filter(t => t.status === 'error').length;
                            const groupRunning = group.threads.filter(t => t.status === 'running').length;
                            const providerName = (group.provider || 'mail').charAt(0).toUpperCase() + (group.provider || 'mail').slice(1);
                            const taskLabel = TASK_TYPE_LABELS[group.task_type] || group.task_type;

                            return (
                                <div key={group.task_id} className="card" style={{ padding: 0, overflow: 'hidden' }}>
                                    {/* Task header */}
                                    <div
                                        onClick={() => toggleTask(group.task_id)}
                                        style={{
                                            padding: '10px 16px',
                                            display: 'flex', alignItems: 'center', gap: 10,
                                            cursor: 'pointer',
                                            background: isRunning ? 'rgba(6,182,212,0.04)' : 'transparent',
                                            borderBottom: isCollapsed ? 'none' : '1px solid var(--border-default)',
                                            userSelect: 'none',
                                        }}
                                    >
                                        <span style={{ fontSize: '0.9em', color: 'var(--text-muted)', fontWeight: 600, width: 16 }}>
                                            {isCollapsed ? '▸' : '▾'}
                                        </span>
                                        <ProviderLogo provider={group.provider || 'mail'} size={24} />
                                        <span style={{ fontWeight: 700, fontSize: '0.9em', color: 'var(--text-primary)' }}>
                                            Task #{group.task_id}
                                        </span>
                                        <span style={{ fontSize: '0.82em', color: 'var(--text-secondary)' }}>
                                            {taskLabel} {providerName} × {group.threads.length}
                                        </span>
                                        <div style={{ flex: 1 }} />
                                        {/* Mini counters */}
                                        <div style={{ display: 'flex', gap: 8, fontSize: '0.78em', fontWeight: 700 }}>
                                            {groupDone > 0 && <span style={{ color: '#10B981' }}>{groupDone}✓</span>}
                                            {groupFailed > 0 && <span style={{ color: '#EF4444' }}>{groupFailed}✗</span>}
                                            {groupRunning > 0 && <span style={{ color: '#06B6D4' }}>{groupRunning}↻</span>}
                                        </div>
                                        {/* Status dot */}
                                        <span style={{
                                            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                                            background: isRunning ? '#06B6D4' : groupFailed === group.threads.length ? '#EF4444' : '#10B981',
                                            boxShadow: isRunning ? '0 0 8px #06B6D4' : 'none',
                                            animation: isRunning ? 'pulse 1.5s infinite' : 'none',
                                        }} />
                                    </div>

                                    {/* Thread rows */}
                                    {!isCollapsed && (
                                        <div style={{ padding: '4px 0' }}>
                                            {group.threads.map((t, i) => {
                                                const si = getStatusInfo(t.status, t.action);
                                                const isActive = activePages.includes(t.id);
                                                const isSelected = selectedThread === t.id;

                                                return (
                                                    <div
                                                        key={t.id || i}
                                                        onClick={() => isActive && setSelectedThread(isSelected ? null : t.id)}
                                                        style={{
                                                            display: 'flex', alignItems: 'center', gap: 10,
                                                            padding: '8px 16px 8px 42px',
                                                            cursor: isActive ? 'pointer' : 'default',
                                                            background: isSelected ? 'rgba(6,182,212,0.08)' : 'transparent',
                                                            borderLeft: isSelected ? '3px solid #06B6D4' : '3px solid transparent',
                                                            transition: 'all 0.15s',
                                                        }}
                                                        onMouseEnter={e => { if (isActive) e.currentTarget.style.background = isSelected ? 'rgba(6,182,212,0.08)' : 'rgba(255,255,255,0.02)'; }}
                                                        onMouseLeave={e => { e.currentTarget.style.background = isSelected ? 'rgba(6,182,212,0.08)' : 'transparent'; }}
                                                    >
                                                        {/* Thread number */}
                                                        <span style={{
                                                            width: 26, height: 26, borderRadius: '50%',
                                                            border: `1.5px solid ${si.color}44`,
                                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                            fontWeight: 800, fontSize: '0.7em', color: si.color, flexShrink: 0,
                                                        }}>
                                                            {(t.index ?? i) + 1}
                                                        </span>

                                                        {/* Provider */}
                                                        <ProviderLogo provider={t.provider || group.provider || 'mail'} size={22} />

                                                        {/* Email */}
                                                        <span style={{
                                                            flex: '0 0 200px', minWidth: 0,
                                                            fontSize: '0.85em', fontWeight: 500, color: 'var(--text-primary)',
                                                            fontFamily: 'monospace',
                                                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                                        }}>
                                                            {t.email || '—'}
                                                        </span>

                                                        {/* Action text */}
                                                        <span style={{
                                                            flex: 1, minWidth: 0,
                                                            fontSize: '0.78em', color: si.color,
                                                            fontWeight: 600,
                                                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                                        }}>
                                                            {t.action || si.label}
                                                        </span>

                                                        {/* Proxy */}
                                                        <span style={{
                                                            fontSize: '0.72em', color: 'var(--text-muted)',
                                                            fontFamily: 'monospace', flexShrink: 0,
                                                        }}>
                                                            {maskProxy(t.proxy)}
                                                        </span>

                                                        {/* Time */}
                                                        <span style={{
                                                            fontSize: '0.78em', color: 'var(--text-muted)',
                                                            fontFamily: 'monospace', flexShrink: 0, minWidth: 40, textAlign: 'right',
                                                        }}>
                                                            {formatElapsed(t.started || t.updated)}
                                                        </span>

                                                        {/* Live indicator */}
                                                        {isActive && (
                                                            <span style={{
                                                                width: 6, height: 6, borderRadius: '50%',
                                                                background: '#10B981', boxShadow: '0 0 4px #10B981',
                                                                flexShrink: 0,
                                                            }} title="Live — кликни для превью" />
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* ── Right: Live Preview panel ── */}
            {hasPreview && (
                <div style={{
                    width: 420, flexShrink: 0,
                    display: 'flex', flexDirection: 'column', gap: 8,
                }}>
                    <div className="card" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.9em', color: 'var(--text-primary)' }}>
                                🖥 Live Preview
                            </span>
                            <span style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                Thread #{selectedThread} · обновление 2с
                            </span>
                        </div>
                        <div style={{
                            flex: 1, borderRadius: 8, overflow: 'hidden',
                            background: '#0a0a0a', border: '1px solid var(--border-default)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            position: 'relative', minHeight: 300,
                        }}>
                            {screenshotError ? (
                                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85em' }}>
                                    <div style={{ fontSize: '1.5em', marginBottom: 4 }}>📷</div>
                                    Браузер закрыт или скриншот недоступен
                                </div>
                            ) : screenshotUrl ? (
                                <img
                                    src={screenshotUrl}
                                    alt="Live browser"
                                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                                />
                            ) : (
                                <div style={{ color: 'var(--text-muted)', fontSize: '0.85em' }}>
                                    Загрузка скриншота...
                                </div>
                            )}
                        </div>
                        <button
                            className="btn"
                            onClick={() => { setSelectedThread(null); setScreenshotUrl(null); }}
                            style={{
                                padding: '6px 14px', fontSize: '0.8em', border: '1px solid var(--border-default)',
                                background: 'transparent', alignSelf: 'flex-end',
                            }}
                        >
                            Закрыть превью
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
