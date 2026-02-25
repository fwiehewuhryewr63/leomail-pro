import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Rocket, Plus, Play, Pause, Square, Trash2, ChevronRight,
    Mail, Link2, FileText, Users, ChevronDown
} from 'lucide-react';
import { API } from '../api';

const GEOS = [
    { code: 'BR', name: 'Brazil', flag: '🇧🇷' },
    { code: 'MX', name: 'Mexico', flag: '🇲🇽' },
    { code: 'CO', name: 'Colombia', flag: '🇨🇴' },
    { code: 'AR', name: 'Argentina', flag: '🇦🇷' },
    { code: 'PE', name: 'Peru', flag: '🇵🇪' },
    { code: 'EG', name: 'Egypt', flag: '🇪🇬' },
    { code: 'NG', name: 'Nigeria', flag: '🇳🇬' },
    { code: 'ZA', name: 'South Africa', flag: '🇿🇦' },
    { code: 'US', name: 'USA', flag: '🇺🇸' },
    { code: 'DE', name: 'Germany', flag: '🇩🇪' },
    { code: 'GB', name: 'UK', flag: '🇬🇧' },
    { code: 'FR', name: 'France', flag: '🇫🇷' },
    { code: 'ES', name: 'Spain', flag: '🇪🇸' },
    { code: 'IT', name: 'Italy', flag: '🇮🇹' },
    { code: 'RU', name: 'Russia', flag: '🇷🇺' },
    { code: 'IN', name: 'India', flag: '🇮🇳' },
    { code: 'PH', name: 'Philippines', flag: '🇵🇭' },
    { code: 'ID', name: 'Indonesia', flag: '🇮🇩' },
];
const FLAG = Object.fromEntries(GEOS.map(g => [g.code, g.flag]));

const NICHES = [
    { value: 'nutra', label: 'Nutra', icon: '💊' },
    { value: 'dating', label: 'Dating', icon: '❤️' },
    { value: 'casino', label: 'Casino', icon: '🎰' },
    { value: 'general', label: 'General', icon: '📧' },
];

const PROVIDERS = [
    { id: 'gmail', name: 'Gmail', color: '#EA4335' },
    { id: 'yahoo', name: 'Yahoo', color: '#6001D2' },
    { id: 'aol', name: 'AOL', color: '#FF6B00' },
    { id: 'outlook', name: 'Outlook', color: '#0078D4' },
    { id: 'hotmail', name: 'Hotmail', color: '#0078D4' },
];

const STATUS_COLOR = { draft: 'var(--text-muted)', running: 'var(--success)', paused: 'var(--warning)', completed: 'var(--info)', stopped: 'var(--danger)' };
const STATUS_LABEL = { draft: 'Черновик', running: 'Запущена', paused: 'Пауза', completed: 'Завершена', stopped: 'Остановлена' };

/* Custom dark dropdown */
function DarkSelect({ value, onChange, options, renderOption, renderSelected, style }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, []);
    const selected = options.find(o => (o.value ?? o.code) === value);
    return (
        <div ref={ref} style={{ position: 'relative', ...style }}>
            <div onClick={() => setOpen(!open)} style={{
                ...inp, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                cursor: 'pointer', userSelect: 'none',
            }}>
                <span>{renderSelected ? renderSelected(selected) : (selected?.label || value)}</span>
                <ChevronDown size={14} style={{ opacity: 0.5, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
            </div>
            {open && (
                <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                    marginTop: 4, background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 8, maxHeight: 260, overflowY: 'auto',
                    boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                }}>
                    {options.map(o => {
                        const val = o.value ?? o.code;
                        const isActive = val === value;
                        return (
                            <div key={val} onClick={() => { onChange(val); setOpen(false); }} style={{
                                padding: '8px 14px', cursor: 'pointer', fontSize: '0.88em',
                                background: isActive ? 'rgba(212,168,38,0.15)' : 'transparent',
                                color: isActive ? 'var(--accent)' : 'var(--text-primary)',
                                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                                transition: 'background 0.15s',
                            }}
                                onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                                onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
                            >
                                {renderOption ? renderOption(o) : (o.label || val)}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

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
            if (d.id) { setShowCreate(false); load(); navigate(`/campaigns/${d.id}`); }
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

    const toggleProvider = (p) => {
        setForm(f => ({
            ...f,
            providers: f.providers.includes(p)
                ? f.providers.filter(x => x !== p)
                : [...f.providers, p]
        }));
    };

    return (
        <div className="page">
            <h2 className="page-title">
                <Rocket size={22} /> Кампании
                <span style={{ marginLeft: 'auto', fontSize: '0.42em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 2 }}>BLITZ v4</span>
            </h2>

            {/* Create button */}
            <div style={{ marginBottom: 16 }}>
                <button onClick={() => setShowCreate(!showCreate)} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '10px 22px',
                    fontWeight: 700, fontSize: '0.9em', border: 'none', borderRadius: 8,
                    cursor: 'pointer', background: 'var(--accent)', color: '#000',
                    transition: 'all 0.2s',
                }}>
                    <Plus size={16} /> Новая кампания
                </button>
            </div>

            {/* Create form */}
            {showCreate && (
                <div className="card" style={{ marginBottom: 16, padding: '22px 24px' }}>
                    <div style={{ fontSize: '0.82em', fontWeight: 700, marginBottom: 16, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                        Создать кампанию
                    </div>

                    {/* Row 1: Name, GEO, Niche */}
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 14, marginBottom: 16 }}>
                        <div>
                            <label style={lbl}>Название</label>
                            <input style={inp} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Brazil Nutra Q1" />
                        </div>
                        <div>
                            <label style={lbl}>GEO</label>
                            <DarkSelect
                                value={form.geo}
                                onChange={v => setForm({ ...form, geo: v })}
                                options={GEOS}
                                renderSelected={g => g ? `${g.flag} ${g.code}` : '—'}
                                renderOption={g => `${g.flag} ${g.code} — ${g.name}`}
                            />
                        </div>
                        <div>
                            <label style={lbl}>Ниша</label>
                            <DarkSelect
                                value={form.niche}
                                onChange={v => setForm({ ...form, niche: v })}
                                options={NICHES}
                                renderSelected={n => n ? `${n.icon} ${n.label}` : '—'}
                                renderOption={n => `${n.icon} ${n.label}`}
                            />
                        </div>
                    </div>

                    {/* Row 2: Providers */}
                    <div style={{ marginBottom: 16 }}>
                        <label style={lbl}>Провайдеры</label>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            {PROVIDERS.map(p => {
                                const active = form.providers.includes(p.id);
                                return (
                                    <div key={p.id} onClick={() => toggleProvider(p.id)} style={{
                                        display: 'flex', alignItems: 'center', gap: 6,
                                        padding: '6px 14px', borderRadius: 6, cursor: 'pointer',
                                        background: active ? `${p.color}22` : 'rgba(255,255,255,0.03)',
                                        border: `1px solid ${active ? p.color : 'rgba(255,255,255,0.08)'}`,
                                        transition: 'all 0.2s',
                                    }}>
                                        <div style={{
                                            width: 14, height: 14, borderRadius: 3,
                                            background: active ? p.color : 'transparent',
                                            border: `2px solid ${active ? p.color : 'rgba(255,255,255,0.2)'}`,
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontSize: '10px', color: '#fff', fontWeight: 900,
                                            transition: 'all 0.2s',
                                        }}>
                                            {active && '✓'}
                                        </div>
                                        <span style={{
                                            fontSize: '0.85em', fontWeight: 600,
                                            color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                                        }}>{p.name}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Row 3: Threads */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: 14, marginBottom: 16 }}>
                        <div>
                            <label style={lbl}>Birth потоков</label>
                            <input style={inp} type="number" min="1" max="50" value={form.birth_threads}
                                onChange={e => setForm({ ...form, birth_threads: +e.target.value })} />
                        </div>
                        <div>
                            <label style={lbl}>Send потоков</label>
                            <input style={inp} type="number" min="1" max="100" value={form.send_threads}
                                onChange={e => setForm({ ...form, send_threads: +e.target.value })} />
                        </div>
                        <div />
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 10 }}>
                        <button onClick={create} disabled={loading || !form.name} style={{
                            padding: '10px 28px', fontWeight: 700, fontSize: '0.9em', border: 'none',
                            borderRadius: 6, cursor: loading || !form.name ? 'not-allowed' : 'pointer',
                            background: loading || !form.name ? 'rgba(255,255,255,0.06)' : 'var(--accent)',
                            color: loading || !form.name ? 'var(--text-muted)' : '#000',
                            transition: 'all 0.2s',
                        }}>
                            {loading ? '⏳ Создание...' : '🚀 Создать'}
                        </button>
                        <button onClick={() => setShowCreate(false)} style={{
                            padding: '10px 22px', fontWeight: 600, fontSize: '0.9em', border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 6, cursor: 'pointer', background: 'transparent', color: 'var(--text-secondary)',
                        }}>
                            Отмена
                        </button>
                    </div>
                </div>
            )}

            {/* Empty state */}
            {campaigns.length === 0 && !showCreate && (
                <div className="card" style={{ padding: 50, textAlign: 'center', color: 'var(--text-muted)' }}>
                    <Rocket size={44} style={{ opacity: 0.2, marginBottom: 12 }} />
                    <div style={{ fontSize: '1.1em', fontWeight: 600, marginBottom: 6 }}>Нет кампаний</div>
                    <div style={{ fontSize: '0.85em' }}>Создайте первую кампанию для запуска Blitz Pipeline</div>
                </div>
            )}

            {/* Campaign cards */}
            <div style={{ display: 'grid', gap: 12 }}>
                {campaigns.map(c => {
                    const pct = c.recipients_total > 0 ? Math.round(c.recipients_sent / c.recipients_total * 100) : 0;
                    return (
                        <div key={c.id} className="card card-clickable" style={{ padding: '16px 20px', borderLeft: `3px solid ${STATUS_COLOR[c.status] || 'var(--text-muted)'}` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{ flex: 1, cursor: 'pointer' }} onClick={() => navigate(`/campaigns/${c.id}`)}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <span style={{ fontSize: '1.3em' }}>{FLAG[c.geo] || '🌍'}</span>
                                        <span style={{ fontSize: '1.1em', fontWeight: 800, color: 'var(--text-primary)' }}>{c.name}</span>
                                        <span style={{
                                            fontSize: '0.72em', fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                            background: `${STATUS_COLOR[c.status]}22`, color: STATUS_COLOR[c.status],
                                        }}>
                                            {STATUS_LABEL[c.status] || c.status}
                                        </span>
                                        {c.stop_reason && <span style={{ fontSize: '0.72em', color: 'var(--danger)' }}>⚠️ {c.stop_reason}</span>}
                                    </div>
                                    <div style={{ display: 'flex', gap: 16, fontSize: '0.8em', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                                        <span><Mail size={12} /> Sent: <b style={{ color: 'var(--success)' }}>{c.total_sent || 0}</b></span>
                                        <span>Errors: <b style={{ color: 'var(--danger)' }}>{c.total_errors || 0}</b></span>
                                        <span><Users size={12} /> Акки: <b>{c.accounts_born || 0}</b> / <b style={{ color: 'var(--danger)' }}>{c.accounts_dead || 0}</b> мёрт.</span>
                                        <span><Link2 size={12} /> Линки: <b>{c.links_active || 0}</b>/{c.links_total || 0}</span>
                                        <span><FileText size={12} /> Шаблоны: <b>{c.templates_active || 0}</b></span>
                                    </div>
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
                                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                    {c.status === 'draft' && <ActionBtn color="#10b981" icon={Play} onClick={() => action(c.id, 'start')} title="Запуск" />}
                                    {c.status === 'running' && <ActionBtn color="#f59e0b" icon={Pause} onClick={() => action(c.id, 'pause')} title="Пауза" />}
                                    {c.status === 'paused' && <ActionBtn color="#10b981" icon={Play} onClick={() => action(c.id, 'start')} title="Возобновить" />}
                                    {['running', 'paused'].includes(c.status) && <ActionBtn color="#ef4444" icon={Square} onClick={() => action(c.id, 'stop')} title="Стоп" />}
                                    {['draft', 'stopped', 'completed'].includes(c.status) && <ActionBtn color="#ef4444" icon={Trash2} onClick={() => del(c.id)} title="Удалить" />}
                                    <ActionBtn color="var(--accent)" icon={ChevronRight} onClick={() => navigate(`/campaigns/${c.id}`)} title="Детали" />
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

const ActionBtn = ({ color, icon: Icon, onClick, title }) => (
    <button onClick={onClick} title={title} style={{
        background: `${color}15`, border: `1px solid ${color}33`, cursor: 'pointer',
        color, padding: 7, borderRadius: 6, display: 'flex', transition: 'all 0.2s',
    }}>
        <Icon size={15} />
    </button>
);

const lbl = { fontSize: '0.72em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 6, display: 'block' };
const inp = {
    width: '100%', padding: '9px 12px', background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
    color: 'var(--text-primary)', fontSize: '0.9em', outline: 'none',
    transition: 'border-color 0.2s',
};
