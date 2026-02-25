import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, Play, Pause, Square, FileText, Link2, Users,
    Upload, Trash2, CheckCircle, AlertTriangle, XCircle, Shield, Mail
} from 'lucide-react';
import { API } from '../api';

export default function CampaignDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [c, setC] = useState(null);
    const [preflight, setPreflight] = useState(null);
    const [tab, setTab] = useState('overview');
    const [importText, setImportText] = useState('');
    const [maxUses, setMaxUses] = useState(100);
    const [importing, setImporting] = useState(false);

    const load = () => fetch(`${API}/campaigns/${id}`).then(r => r.json()).then(setC).catch(() => { });
    useEffect(() => { load(); const iv = setInterval(load, 8000); return () => clearInterval(iv); }, [id]);

    const loadPreflight = () => fetch(`${API}/campaigns/${id}/preflight`).then(r => r.json()).then(setPreflight).catch(() => { });
    useEffect(() => { loadPreflight(); }, [id]);

    if (!c) return <div className="page" style={{ padding: 40, color: 'var(--text-muted)' }}>Загрузка...</div>;

    const pct = c.recipients_total > 0 ? Math.round(c.recipients_sent / c.recipients_total * 100) : 0;
    const StatusIcon = (s) => s === 'ok' ? <CheckCircle size={14} style={{ color: 'var(--success)' }} /> : s === 'warning' ? <AlertTriangle size={14} style={{ color: 'var(--warning)' }} /> : <XCircle size={14} style={{ color: 'var(--danger)' }} />;

    const action = async (act) => { await fetch(`${API}/campaigns/${id}/${act}`, { method: 'POST' }); load(); loadPreflight(); };

    const doImport = async (endpoint) => {
        setImporting(true);
        try {
            const body = { content: importText, max_uses: maxUses };
            const r = await fetch(`${API}/campaigns/${id}/${endpoint}/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            const d = await r.json();
            alert(`Добавлено: ${d.added}, пропущено: ${d.skipped || 0}`);
            setImportText('');
            load(); loadPreflight();
        } catch { alert('Ошибка импорта'); }
        finally { setImporting(false); }
    };

    return (
        <div className="page">
            <h2 className="page-title" style={{ cursor: 'pointer' }} onClick={() => navigate('/campaigns')}>
                <ArrowLeft size={20} /> {c.name}
                <span style={{ fontSize: '0.5em', marginLeft: 8, fontWeight: 600, color: statusColor(c.status) }}>{statusLabel(c.status)}</span>
            </h2>

            {/* Action bar */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                {['draft', 'paused', 'stopped'].includes(c.status) &&
                    <button style={btn('var(--success)')} onClick={() => action('start')}><Play size={14} /> Запуск</button>}
                {c.status === 'running' &&
                    <button style={btn('#f59e0b')} onClick={() => action('pause')}><Pause size={14} /> Пауза</button>}
                {['running', 'paused'].includes(c.status) &&
                    <button style={btn('var(--danger)')} onClick={() => action('stop')}><Square size={14} /> Стоп</button>}
                <button style={btn('var(--text-muted)')} onClick={() => loadPreflight()}>🔍 Pre-flight</button>
            </div>

            {/* Stats cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 16 }}>
                <StatBox label="Отправлено" value={c.total_sent || 0} color="var(--success)" icon={Mail} />
                <StatBox label="Ошибки" value={c.total_errors || 0} color="var(--danger)" icon={AlertTriangle} />
                <StatBox label="Акки рожд." value={c.accounts_born || 0} color="var(--info)" icon={Users} />
                <StatBox label="Акки мёрт." value={c.accounts_dead || 0} color="var(--danger)" icon={XCircle} />
                <StatBox label="Прогресс" value={`${pct}%`} color="var(--accent)" icon={CheckCircle} />
            </div>

            {/* Progress bar */}
            {c.recipients_total > 0 && (
                <div className="card" style={{ marginBottom: 16, padding: '12px 18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', marginBottom: 6, color: 'var(--text-muted)' }}>
                        <span>Получатели: {c.recipients_sent} / {c.recipients_total}</span>
                        <span>Линки: {c.links_active} / {c.links_total}</span>
                    </div>
                    <div className="progress-bar"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                </div>
            )}

            {c.stop_reason && (
                <div className="card" style={{ marginBottom: 16, padding: '12px 18px', borderLeft: '3px solid var(--danger)' }}>
                    <span style={{ color: 'var(--danger)', fontWeight: 700 }}>⚠️ Остановлена: </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{c.stop_reason}</span>
                </div>
            )}

            {/* Pre-flight */}
            {preflight && (
                <div className="card" style={{ marginBottom: 16, padding: '16px 18px' }}>
                    <div style={{ fontSize: '0.75em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 10 }}>Pre-flight Check</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                        <PFItem label="Шаблоны" status={preflight.templates?.status} detail={`${preflight.templates?.count || 0} активных`} />
                        <PFItem label="ESP линки" status={preflight.links?.status} detail={`${preflight.links?.count || 0} активных`} />
                        <PFItem label="Получатели" status={preflight.recipients?.status} detail={`${preflight.recipients?.count || 0} не отправлено`} />
                        <PFItem label="SMS баланс" status={preflight.sms?.status} detail={`$${preflight.sms?.total_balance || 0} (~${preflight.sms?.estimated_accounts || 0} акков)`} />
                        <PFItem label="Прокси" status={preflight.proxies?.status} detail={`${preflight.proxies?.alive || 0} живых (${preflight.proxies?.geo_match || 0} GEO)`} />
                        <PFItem label="Провайдеры" status={preflight.providers?.status} detail={(preflight.providers?.list || []).join(', ') || 'нет'} />
                    </div>
                    <div style={{ marginTop: 10, textAlign: 'center', fontWeight: 700, fontSize: '0.9em', color: preflight.ready ? 'var(--success)' : 'var(--danger)' }}>
                        {preflight.ready ? '✅ Готова к запуску' : '❌ Есть критические проблемы'}
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 0, marginBottom: 16, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                {[{ id: 'templates', label: 'Шаблоны', icon: FileText }, { id: 'links', label: 'ESP Линки', icon: Link2 }, { id: 'recipients', label: 'Получатели', icon: Users }].map(t => (
                    <button key={t.id} onClick={() => setTab(t.id)} style={{
                        background: 'none', border: 'none', padding: '10px 20px', cursor: 'pointer',
                        color: tab === t.id ? 'var(--accent)' : 'var(--text-muted)', fontWeight: 700, fontSize: '0.85em',
                        borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <t.icon size={14} /> {t.label}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <div className="card" style={{ padding: '18px' }}>
                {tab === 'templates' && (
                    <>
                        <div style={{ fontSize: '0.75em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 10 }}>
                            Импорт шаблонов (разделитель: ---TEMPLATE---)
                        </div>
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"---TEMPLATE---\nSubject: Olá {first_name}\nBody:\n<p>Olá {first_name}, confira <a href=\"{link}\">aqui</a></p>\n---TEMPLATE---\nSubject: Oportunidade\nBody:\n<p>Veja isso: <a href=\"{link}\">clique</a></p>"} />
                        <button style={{ ...btn('var(--accent)'), marginTop: 8 }} onClick={() => doImport('templates')} disabled={importing || !importText}>
                            <Upload size={14} /> {importing ? '...' : 'Импортировать'}
                        </button>
                        {c.templates && c.templates.length > 0 && (
                            <div style={{ marginTop: 14 }}>
                                {c.templates.map(t => (
                                    <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        <span style={{ fontSize: '0.85em', flex: 1, color: t.active ? 'var(--text-primary)' : 'var(--text-muted)' }}>{t.subject}</span>
                                        <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>×{t.use_count}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                )}

                {tab === 'links' && (
                    <>
                        <div style={{ fontSize: '0.75em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 10 }}>
                            Импорт ESP линков (по одному на строку)
                        </div>
                        <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                            <div style={{ flex: 1 }}>
                                <label style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>Max использований/линк</label>
                                <input style={{ ...inp, width: 120 }} type="number" value={maxUses} onChange={e => setMaxUses(+e.target.value)} />
                            </div>
                        </div>
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"https://esp.com/track/aB3x\nhttps://esp.com/track/cD4y\nhttps://esp.com/track/eF5z"} />
                        <button style={{ ...btn('var(--accent)'), marginTop: 8 }} onClick={() => doImport('links')} disabled={importing || !importText}>
                            <Upload size={14} /> {importing ? '...' : 'Импортировать'}
                        </button>
                    </>
                )}

                {tab === 'recipients' && (
                    <>
                        <div style={{ fontSize: '0.75em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 10 }}>
                            Импорт получателей (email по одному на строку)
                        </div>
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"user1@example.com\nuser2@example.com\nuser3@example.com"} />
                        <button style={{ ...btn('var(--accent)'), marginTop: 8 }} onClick={() => doImport('recipients')} disabled={importing || !importText}>
                            <Upload size={14} /> {importing ? '...' : 'Импортировать'}
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}

// --- helpers ---
const statusColor = (s) => ({ draft: 'var(--text-muted)', running: 'var(--success)', paused: 'var(--warning)', completed: 'var(--info)', stopped: 'var(--danger)' }[s] || 'var(--text-muted)');
const statusLabel = (s) => ({ draft: 'ЧЕРНОВИК', running: 'ЗАПУЩЕНА', paused: 'ПАУЗА', completed: 'ЗАВЕРШЕНА', stopped: 'ОСТАНОВЛЕНА' }[s] || s);

const StatBox = ({ label, value, color, icon: Icon }) => (
    <div className="card" style={{ padding: '12px 14px', textAlign: 'center' }}>
        <Icon size={14} style={{ color, marginBottom: 4 }} />
        <div style={{ fontSize: '1.4em', fontWeight: 800, color }}>{value}</div>
        <div style={{ fontSize: '0.68em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 }}>{label}</div>
    </div>
);

const PFItem = ({ label, status, detail }) => (
    <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.02)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        {status === 'ok' ? <CheckCircle size={14} style={{ color: 'var(--success)' }} /> :
            status === 'warning' ? <AlertTriangle size={14} style={{ color: 'var(--warning)' }} /> :
                <XCircle size={14} style={{ color: 'var(--danger)' }} />}
        <div>
            <div style={{ fontSize: '0.78em', fontWeight: 700, color: 'var(--text-primary)' }}>{label}</div>
            <div style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>{detail}</div>
        </div>
    </div>
);

const btn = (c) => ({
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 18px',
    fontWeight: 700, fontSize: '0.85em', borderRadius: 6, cursor: 'pointer',
    background: `${c}20`, border: `1px solid ${c}55`, color: c,
    transition: 'all 0.2s',
});
const inp = {
    padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
    color: 'var(--text-primary)', fontSize: '0.85em', outline: 'none',
};
const ta = {
    width: '100%', minHeight: 120, padding: '12px 14px',
    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8, color: 'var(--text-primary)', fontSize: '0.85em',
    fontFamily: 'monospace', resize: 'vertical', outline: 'none',
    lineHeight: 1.5,
};

