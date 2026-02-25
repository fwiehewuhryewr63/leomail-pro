import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Rocket, Plus, Play, Pause, Square, Trash2, ChevronRight,
    Globe, Mail, Shield, Link2, FileText, Users
} from 'lucide-react';
import { API } from '../api';

const FLAG = { BR: '🇧🇷', MX: '🇲🇽', CO: '🇨🇴', AR: '🇦🇷', PE: '🇵🇪', EG: '🇪🇬', NG: '🇳🇬', ZA: '🇿🇦', US: '🇺🇸', DE: '🇩🇪', GB: '🇬🇧', FR: '🇫🇷', ES: '🇪🇸', IT: '🇮🇹', RU: '🇷🇺', IN: '🇮🇳', PH: '🇵🇭', ID: '🇮🇩' };
const STATUS_COLOR = { draft: 'var(--text-muted)', running: 'var(--success)', paused: 'var(--warning)', completed: 'var(--info)', stopped: 'var(--danger)' };
const STATUS_LABEL = { draft: 'Черновик', running: 'Запущена', paused: 'Пауза', completed: 'Завершена', stopped: 'Остановлена' };

export default function Campaigns() {
    const [campaigns, setCampaigns] = useState([]);
    const [showCreate, setShowCreate] = useState(false);
    const [form, setForm] = useState({ name: '', geo: 'BR', niche: 'nutra', name_pack: 'brazil_5k', providers: ['yahoo', 'aol'], birth_threads: 10, send_threads: 20 });
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const load = () => fetch(`${API}/campaigns`).then(r => r.json()).then(setCampaigns).catch(() => { });
    useEffect(() => { load(); const iv = setInterval(load, 10000); return () => clearInterval(iv); }, []);

    const create = async () => {
        setLoading(true);
        try {
            const r = await fetch(`${API}/campaigns`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
            const d = await r.json();
            if (d.id) { setShowCreate(false); navigate(`/campaigns/${d.id}`); }
        } finally { setLoading(false); }
    };

    const action = async (id, act) => {
        await fetch(`${API}/campaigns/${id}/${act}`, { method: 'POST' });
        load();
    };

    const del = async (id) => {
        if (!confirm('Удалить кампанию?')) return;
        await fetch(`${API}/campaigns/${id}`, { method: 'DELETE' });
        load();
    };

    return (
        <div className="page">
            <h2 className="page-title">
                <Rocket size={22} /> Кампании
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>BLITZ v4</span>
            </h2>

            {/* Create button */}
            <div style={{ marginBottom: 16, display: 'flex', gap: 10 }}>
                <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px', fontWeight: 700, fontSize: '0.9em', border: 'none', borderRadius: 8, cursor: 'pointer', background: 'var(--accent)', color: '#000' }}>
                    <Plus size={16} /> Новая кампания
                </button>
            </div>

            {/* Create form */}
            {showCreate && (
                <div className="card" style={{ marginBottom: 16, padding: '20px' }}>
                    <div style={{ fontSize: '0.85em', fontWeight: 700, marginBottom: 12, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: 1 }}>Создать кампанию</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                        <div>
                            <label style={lbl}>Название</label>
                            <input style={inp} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Brazil Nutra" />
                        </div>
                        <div>
                            <label style={lbl}>GEO</label>
                            <select style={inp} value={form.geo} onChange={e => setForm({ ...form, geo: e.target.value })}>
                                {['BR', 'MX', 'CO', 'AR', 'PE', 'EG', 'NG', 'ZA', 'US', 'DE', 'GB', 'FR', 'ES', 'IT', 'RU', 'IN', 'PH', 'ID'].map(g =>
                                    <option key={g} value={g}>{FLAG[g] || ''} {g}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={lbl}>Ниша</label>
                            <select style={inp} value={form.niche} onChange={e => setForm({ ...form, niche: e.target.value })}>
                                <option value="nutra">💊 Nutra</option>
                                <option value="dating">❤️ Dating</option>
                                <option value="casino">🎰 Casino</option>
                                <option value="general">📧 General</option>
                            </select>
                        </div>
                        <div>
                            <label style={lbl}>Провайдеры</label>
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                {['gmail', 'yahoo', 'aol', 'outlook', 'hotmail'].map(p => (
                                    <label key={p} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.85em', cursor: 'pointer', color: form.providers.includes(p) ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                                        <input type="checkbox" checked={form.providers.includes(p)}
                                            onChange={e => setForm({ ...form, providers: e.target.checked ? [...form.providers, p] : form.providers.filter(x => x !== p) })} />
                                        {p}
                                    </label>
                                ))}
                            </div>
                        </div>
                        <div>
                            <label style={lbl}>Birth потоков</label>
                            <input style={inp} type="number" value={form.birth_threads} onChange={e => setForm({ ...form, birth_threads: +e.target.value })} />
                        </div>
                        <div>
                            <label style={lbl}>Send потоков</label>
                            <input style={inp} type="number" value={form.send_threads} onChange={e => setForm({ ...form, send_threads: +e.target.value })} />
                        </div>
                    </div>
                    <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
                        <button style={{ ...btnStyle, background: 'var(--accent)', color: '#000' }} onClick={create} disabled={loading || !form.name}>
                            {loading ? '...' : 'Создать'}
                        </button>
                        <button style={{ ...btnStyle, background: 'rgba(255,255,255,0.06)', color: 'var(--text-secondary)' }} onClick={() => setShowCreate(false)}>
                            Отмена
                        </button>
                    </div>
                </div>
            )}

            {/* Campaign cards */}
            {campaigns.length === 0 && !showCreate && (
                <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
                    <Rocket size={40} style={{ opacity: 0.3, marginBottom: 12 }} />
                    <div style={{ fontSize: '1.1em', fontWeight: 600 }}>Нет кампаний</div>
                    <div style={{ fontSize: '0.85em', marginTop: 6 }}>Создайте первую кампанию для запуска Blitz Pipeline</div>
                </div>
            )}

            <div style={{ display: 'grid', gap: 12 }}>
                {campaigns.map(c => {
                    const pct = c.recipients_total > 0 ? Math.round(c.recipients_sent / c.recipients_total * 100) : 0;
                    return (
                        <div key={c.id} className="card card-clickable" style={{ padding: '16px 20px', borderLeft: `3px solid ${STATUS_COLOR[c.status] || 'var(--text-muted)'}` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                {/* Left: info */}
                                <div style={{ flex: 1, cursor: 'pointer' }} onClick={() => navigate(`/campaigns/${c.id}`)}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <span style={{ fontSize: '1.3em' }}>{FLAG[c.geo] || '🌍'}</span>
                                        <span style={{ fontSize: '1.1em', fontWeight: 800, color: 'var(--text-primary)' }}>{c.name}</span>
                                        <span style={{ fontSize: '0.72em', fontWeight: 700, padding: '2px 8px', borderRadius: 4, background: `${STATUS_COLOR[c.status]}22`, color: STATUS_COLOR[c.status] }}>
                                            {STATUS_LABEL[c.status] || c.status}
                                        </span>
                                        {c.stop_reason && <span style={{ fontSize: '0.72em', color: 'var(--danger)' }}>⚠️ {c.stop_reason}</span>}
                                    </div>

                                    {/* Stats row */}
                                    <div style={{ display: 'flex', gap: 16, fontSize: '0.8em', color: 'var(--text-secondary)' }}>
                                        <span><Mail size={12} /> Sent: <b style={{ color: 'var(--success)' }}>{c.total_sent || 0}</b></span>
                                        <span>Errors: <b style={{ color: 'var(--danger)' }}>{c.total_errors || 0}</b></span>
                                        <span><Users size={12} /> Акки: <b>{c.accounts_born || 0}</b> / <b style={{ color: 'var(--danger)' }}>{c.accounts_dead || 0}</b> мёрт.</span>
                                        <span><Link2 size={12} /> Линки: <b>{c.links_active || 0}</b>/{c.links_total || 0}</span>
                                        <span><FileText size={12} /> Шаблоны: <b>{c.templates_active || 0}</b></span>
                                    </div>

                                    {/* Progress bar */}
                                    {c.recipients_total > 0 && (
                                        <div style={{ marginTop: 8 }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72em', color: 'var(--text-muted)', marginBottom: 3 }}>
                                                <span>Получатели: {c.recipients_sent}/{c.recipients_total}</span>
                                                <span>{pct}%</span>
                                            </div>
                                            <div className="progress-bar"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                                        </div>
                                    )}
                                </div>

                                {/* Right: actions */}
                                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                    {c.status === 'draft' && <button style={actBtn('#10b981')} onClick={() => action(c.id, 'start')} title="Запуск"><Play size={16} /></button>}
                                    {c.status === 'running' && <button style={actBtn('#f59e0b')} onClick={() => action(c.id, 'pause')} title="Пауза"><Pause size={16} /></button>}
                                    {c.status === 'paused' && <button style={actBtn('#10b981')} onClick={() => action(c.id, 'start')} title="Возобновить"><Play size={16} /></button>}
                                    {['running', 'paused'].includes(c.status) && <button style={actBtn('#ef4444')} onClick={() => action(c.id, 'stop')} title="Стоп"><Square size={16} /></button>}
                                    {['draft', 'stopped', 'completed'].includes(c.status) && <button style={actBtn('#ef4444')} onClick={() => del(c.id)} title="Удалить"><Trash2 size={16} /></button>}
                                    <button style={actBtn('var(--accent)')} onClick={() => navigate(`/campaigns/${c.id}`)} title="Детали"><ChevronRight size={16} /></button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

const lbl = { fontSize: '0.72em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 4, display: 'block' };
const inp = { width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, color: 'var(--text-primary)', fontSize: '0.9em' };
const btnStyle = { padding: '8px 20px', fontWeight: 700, fontSize: '0.9em', border: 'none', borderRadius: 6, cursor: 'pointer' };
const actBtn = (c) => ({ background: 'none', border: 'none', cursor: 'pointer', color: c, padding: 6, borderRadius: 6, display: 'flex' });
