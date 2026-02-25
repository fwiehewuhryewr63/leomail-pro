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
    const [form, setForm] = useState({
        name: '', geo: 'BR', niche: 'nutra', providers: ['yahoo', 'aol'],
        birth_threads: 10, send_threads: 20,
        use_existing: false, farm_ids: [],
        max_link_uses: 0, max_link_cycles: 0,
    });
    const [loading, setLoading] = useState(false);
    const [farms, setFarms] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [databases, setDatabases] = useState([]);
    const [linkPacks, setLinkPacks] = useState([]);
    const [selectedTemplates, setSelectedTemplates] = useState([]);
    const [selectedDBs, setSelectedDBs] = useState([]);
    const [selectedLinkPacks, setSelectedLinkPacks] = useState([]);
    const navigate = useNavigate();

    const load = () => fetch(`${API}/campaigns`).then(r => r.json()).then(setCampaigns).catch(() => { });
    useEffect(() => {
        load();
        const iv = setInterval(load, 10000);
        fetch(`${API}/farms/`).then(r => r.json()).then(f => setFarms(Array.isArray(f) ? f : [])).catch(() => { });
        fetch(`${API}/resources/batch`).then(r => r.json()).then(d => {
            setTemplates(Array.isArray(d.templates) ? d.templates : []);
            setDatabases(Array.isArray(d.databases) ? d.databases : []);
            setLinkPacks(Array.isArray(d.links) ? d.links : []);
        }).catch(() => { });
        return () => clearInterval(iv);
    }, []);

    const create = async () => {
        setLoading(true);
        try {
            const payload = {
                ...form,
                template_ids: selectedTemplates,
                database_ids: selectedDBs,
                link_pack_ids: selectedLinkPacks,
            };
            const r = await fetch(`${API}/campaigns`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            const d = await r.json();
            if (d.id) { setShowCreate(false); load(); navigate(`/campaigns/${d.id}`); }
        } finally { setLoading(false); }
    };

    const action = async (id, act) => {
        const r = await fetch(`${API}/campaigns/${id}/${act}`, { method: 'POST' });
        const d = await r.json();
        if (act === 'start' && d.ok === false && d.issues) {
            alert('❌ Нельзя запустить кампанию:\n\n' + d.issues.map(i => '• ' + i).join('\n'));
            return;
        }
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

    const toggleList = (list, setList, id) => {
        setList(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
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
                <div className="card" style={{ marginBottom: 16, padding: '28px 30px' }}>
                    <div style={{ fontSize: '0.9em', fontWeight: 700, marginBottom: 20, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                        Создать кампанию
                    </div>

                    {/* Row 1: Name */}
                    <div style={{ marginBottom: 20 }}>
                        <label style={lbl}>Название кампании</label>
                        <input style={{ ...inp, fontSize: '1.05em', padding: '12px 16px' }} value={form.name}
                            onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Brazil Nutra Q1" />
                    </div>

                    {/* Row 2: GEO + Niche */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
                        <div>
                            <label style={lbl}>GEO (регион)</label>
                            <DarkSelect
                                value={form.geo}
                                onChange={v => setForm({ ...form, geo: v })}
                                options={GEOS}
                                renderSelected={g => g ? `${g.flag} ${g.code} — ${g.name}` : '—'}
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

                    {/* Row 3: Providers — BIG CARDS */}
                    <div style={{ marginBottom: 24 }}>
                        <label style={lbl}>Почтовые провайдеры</label>
                        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${PROVIDERS.length}, 1fr)`, gap: 10 }}>
                            {PROVIDERS.map(p => {
                                const active = form.providers.includes(p.id);
                                return (
                                    <div key={p.id} onClick={() => toggleProvider(p.id)} style={{
                                        display: 'flex', flexDirection: 'column', alignItems: 'center',
                                        justifyContent: 'center', gap: 8,
                                        padding: '16px 10px', borderRadius: 10, cursor: 'pointer',
                                        background: active ? `${p.color}18` : 'rgba(255,255,255,0.02)',
                                        border: `2px solid ${active ? p.color : 'rgba(255,255,255,0.06)'}`,
                                        borderLeft: `4px solid ${active ? p.color : 'rgba(255,255,255,0.06)'}`,
                                        transition: 'all 0.2s',
                                        boxShadow: active ? `0 0 20px ${p.color}15` : 'none',
                                    }}>
                                        <div style={{
                                            width: 22, height: 22, borderRadius: 5,
                                            background: active ? p.color : 'transparent',
                                            border: `2.5px solid ${active ? p.color : 'rgba(255,255,255,0.2)'}`,
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontSize: '13px', color: '#fff', fontWeight: 900,
                                            transition: 'all 0.2s',
                                        }}>
                                            {active && '✓'}
                                        </div>
                                        <span style={{
                                            fontSize: '1em', fontWeight: 700, letterSpacing: 0.5,
                                            color: active ? p.color : 'var(--text-muted)',
                                        }}>{p.name}</span>
                                    </div>
                                );
                            })}
                        </div>
                        {form.providers.length === 0 && (
                            <div style={{ fontSize: '0.8em', color: 'var(--danger)', marginTop: 6, fontWeight: 600 }}>
                                Выберите хотя бы одного провайдера
                            </div>
                        )}
                    </div>

                    {/* Row 4: Account source */}
                    <div style={{ marginBottom: 24 }}>
                        <label style={lbl}>Источник аккаунтов</label>
                        <div style={{ padding: '12px 16px', borderRadius: 8, background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)', marginBottom: 10 }}>
                            <div style={{ fontWeight: 700, fontSize: '0.9em', color: 'var(--success)', marginBottom: 2 }}>
                                🚀 Birth Engine — всегда регит новые акки
                            </div>
                            <div style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                Авторег работает параллельно с отправкой
                            </div>
                        </div>
                        {/* Optional: also use existing */}
                        <div onClick={() => setForm(prev => ({ ...prev, use_existing: !prev.use_existing, farm_ids: !prev.use_existing ? prev.farm_ids : [] }))} style={{
                            padding: '12px 16px', borderRadius: 8, cursor: 'pointer',
                            background: form.use_existing ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.02)',
                            border: `1px solid ${form.use_existing ? 'var(--info)' : 'rgba(255,255,255,0.06)'}`,
                            transition: 'all 0.2s', marginBottom: form.use_existing && farms.length > 0 ? 10 : 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <div style={{
                                width: 18, height: 18, borderRadius: 4,
                                background: form.use_existing ? 'var(--info)' : 'transparent',
                                border: `2px solid ${form.use_existing ? 'var(--info)' : 'rgba(255,255,255,0.2)'}`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '11px', color: '#fff', fontWeight: 900, flexShrink: 0,
                            }}>{form.use_existing && '✓'}</div>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: '0.9em', color: form.use_existing ? 'var(--info)' : 'var(--text-muted)', marginBottom: 2 }}>
                                    📦 + Подключить существующие аккаунты
                                </div>
                                <div style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                    Выжившие акки из ферм сразу пойдут в рассылку
                                </div>
                            </div>
                        </div>
                        {/* Farm selector */}
                        {form.use_existing && (
                            <div>
                                {farms.length === 0 ? (
                                    <div style={{ fontSize: '0.85em', color: 'var(--warning)', fontWeight: 600, padding: '10px 0' }}>
                                        ⚠️ Нет ферм — сначала зарегистрируйте аккаунты
                                    </div>
                                ) : (
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
                                        {farms.map(f => {
                                            const selected = form.farm_ids.includes(f.id);
                                            return (
                                                <div key={f.id} onClick={() => setForm(prev => ({
                                                    ...prev,
                                                    farm_ids: selected ? prev.farm_ids.filter(x => x !== f.id) : [...prev.farm_ids, f.id]
                                                }))} style={{
                                                    padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                                                    background: selected ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.02)',
                                                    border: `1px solid ${selected ? 'var(--info)' : 'rgba(255,255,255,0.06)'}`,
                                                    transition: 'all 0.15s',
                                                }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <div style={{
                                                            width: 16, height: 16, borderRadius: 4,
                                                            background: selected ? 'var(--info)' : 'transparent',
                                                            border: `2px solid ${selected ? 'var(--info)' : 'rgba(255,255,255,0.2)'}`,
                                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                            fontSize: '10px', color: '#fff', fontWeight: 900,
                                                        }}>{selected && '✓'}</div>
                                                        <span style={{ fontWeight: 600, fontSize: '0.88em', color: selected ? 'var(--text-primary)' : 'var(--text-muted)' }}>{f.name}</span>
                                                    </div>
                                                    <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 4, marginLeft: 24, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                                                        <span>{f.account_count || 0} акк.</span>
                                                        {f.providers && Object.entries(f.providers).map(([p, c]) => (
                                                            <span key={p} style={{ background: 'rgba(255,255,255,0.06)', padding: '1px 5px', borderRadius: 3, fontSize: '0.9em' }}>{p} {c}</span>
                                                        ))}
                                                        {f.geos && Object.entries(f.geos).map(([g, c]) => (
                                                            <span key={g} style={{ background: 'rgba(212,168,38,0.1)', color: 'var(--accent)', padding: '1px 5px', borderRadius: 3, fontSize: '0.9em' }}>{g}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Row 5: Resources — auto-filtered by niche */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 24 }}>
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ ...lbl, marginBottom: 8 }}>📝 Шаблоны {form.niche && <span style={{ fontSize: '0.75em', color: 'var(--accent)', fontWeight: 400 }}>({form.niche})</span>}</div>
                            <div style={{ display: 'grid', gap: 4, maxHeight: 180, overflowY: 'auto' }}>
                                {templates.length === 0 && <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет шаблонов</div>}
                                {templates
                                    .sort((a, b) => (a.niche === form.niche ? -1 : 1) - (b.niche === form.niche ? -1 : 1))
                                    .map(t => {
                                        const match = !form.niche || !t.niche || t.niche === form.niche;
                                        return (
                                            <div key={t.id} onClick={() => toggleList(selectedTemplates, setSelectedTemplates, t.id)}
                                                style={{
                                                    padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em',
                                                    background: selectedTemplates.includes(t.id) ? 'rgba(212,168,38,0.12)' : 'transparent',
                                                    border: `1px solid ${selectedTemplates.includes(t.id) ? 'var(--accent)' : 'rgba(255,255,255,0.06)'}`,
                                                    color: selectedTemplates.includes(t.id) ? 'var(--accent)' : match ? 'var(--text-secondary)' : 'var(--text-muted)',
                                                    fontWeight: selectedTemplates.includes(t.id) ? 600 : 400,
                                                    opacity: match ? 1 : 0.5,
                                                }}>
                                                {t.name}
                                                {t.needs_names && <span style={{ fontSize: '0.68em', background: 'rgba(139,92,246,0.15)', color: '#a78bfa', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>VIP</span>}
                                                {!t.needs_names && <span style={{ fontSize: '0.68em', background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>BASIC</span>}
                                                {t.niche && <span style={{ fontSize: '0.65em', opacity: 0.5, marginLeft: 3 }}>{t.niche}</span>}
                                            </div>
                                        );
                                    })}
                            </div>
                            {/* Name compatibility warning */}
                            {selectedTemplates.some(id => templates.find(t => t.id === id)?.needs_names) &&
                                selectedDBs.length > 0 &&
                                selectedDBs.every(id => !databases.find(d => d.id === id)?.with_name) && (
                                    <div style={{ fontSize: '0.72em', color: 'var(--info)', fontWeight: 600, marginTop: 6, padding: '4px 8px', background: 'rgba(59,130,246,0.08)', borderRadius: 4 }}>
                                        ℹ️ VIP шаблон + BASIC база → {'{{NAME}}'} = username
                                    </div>
                                )}
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ ...lbl, marginBottom: 8 }}>📧 Базы получателей</div>
                            <div style={{ display: 'grid', gap: 4, maxHeight: 180, overflowY: 'auto' }}>
                                {databases.length === 0 && <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет баз</div>}
                                {databases.map(d => (
                                    <div key={d.id} onClick={() => toggleList(selectedDBs, setSelectedDBs, d.id)}
                                        style={{
                                            padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em',
                                            background: selectedDBs.includes(d.id) ? 'rgba(212,168,38,0.12)' : 'transparent',
                                            border: `1px solid ${selectedDBs.includes(d.id) ? 'var(--accent)' : 'rgba(255,255,255,0.06)'}`,
                                            color: selectedDBs.includes(d.id) ? 'var(--accent)' : 'var(--text-muted)',
                                            fontWeight: selectedDBs.includes(d.id) ? 600 : 400,
                                        }}>
                                        {d.with_name ? '⭐' : '📧'} {d.name} ({d.total_count - (d.used_count || 0)})
                                        <span style={{ fontSize: '0.68em', background: d.with_name ? 'rgba(139,92,246,0.15)' : 'rgba(255,255,255,0.06)', color: d.with_name ? '#a78bfa' : 'var(--text-muted)', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>{d.with_name ? 'VIP' : 'BASIC'}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ ...lbl, marginBottom: 8 }}>🔗 Паки ссылок {form.niche && <span style={{ fontSize: '0.75em', color: 'var(--accent)', fontWeight: 400 }}>({form.niche})</span>}</div>
                            <div style={{ display: 'grid', gap: 4, maxHeight: 180, overflowY: 'auto' }}>
                                {linkPacks.length === 0 && <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет паков</div>}
                                {linkPacks
                                    .sort((a, b) => (a.niche === form.niche ? -1 : 1) - (b.niche === form.niche ? -1 : 1))
                                    .map(l => {
                                        const match = !form.niche || !l.niche || l.niche === form.niche;
                                        return (
                                            <div key={l.id} onClick={() => toggleList(selectedLinkPacks, setSelectedLinkPacks, l.id)}
                                                style={{
                                                    padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em',
                                                    background: selectedLinkPacks.includes(l.id) ? 'rgba(212,168,38,0.12)' : 'transparent',
                                                    border: `1px solid ${selectedLinkPacks.includes(l.id) ? 'var(--accent)' : 'rgba(255,255,255,0.06)'}`,
                                                    color: selectedLinkPacks.includes(l.id) ? 'var(--accent)' : match ? 'var(--text-secondary)' : 'var(--text-muted)',
                                                    fontWeight: selectedLinkPacks.includes(l.id) ? 600 : 400,
                                                    opacity: match ? 1 : 0.5,
                                                }}>
                                                {l.name} ({l.total_count}) {l.niche && <span style={{ fontSize: '0.7em', opacity: 0.6 }}>({l.niche})</span>}
                                            </div>
                                        );
                                    })}
                            </div>
                        </div>
                    </div>



                    {/* Row 7: Link controls + Same/Cross */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 14, marginBottom: 24 }}>
                        <div>
                            <label style={lbl}>🔗 Циклы ссылок</label>
                            <input style={inp} type="number" min="0" value={form.max_link_cycles}
                                onChange={e => setForm({ ...form, max_link_cycles: +e.target.value || 0 })} />
                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 3 }}>0 = ∞ кругов</div>
                        </div>
                        <div>
                            <label style={lbl}>🔗 Макс. раз/ссылку</label>
                            <input style={inp} type="number" min="0" value={form.max_link_uses}
                                onChange={e => setForm({ ...form, max_link_uses: +e.target.value || 0 })} />
                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 3 }}>0 = без лимита</div>
                        </div>
                        <div>
                            <label style={lbl}>Пресеты ссылок</label>
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 2 }}>
                                {[
                                    { label: '∞', c: 0, u: 0 },
                                    { label: '1×', c: 1, u: 1 },
                                    { label: '3×', c: 3, u: 0 },
                                ].map(p => (
                                    <div key={p.label} onClick={() => setForm({ ...form, max_link_cycles: p.c, max_link_uses: p.u })} style={{
                                        padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: '0.82em', fontWeight: 700,
                                        background: form.max_link_cycles === p.c && form.max_link_uses === p.u ? 'rgba(212,168,38,0.15)' : 'rgba(255,255,255,0.03)',
                                        border: `1px solid ${form.max_link_cycles === p.c && form.max_link_uses === p.u ? 'var(--accent)' : 'rgba(255,255,255,0.08)'}`,
                                        color: form.max_link_cycles === p.c && form.max_link_uses === p.u ? 'var(--accent)' : 'var(--text-muted)',
                                    }}>{p.label}</div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Row 8: Threads */}
                    <div style={{ display: 'grid', gridTemplateColumns: form.use_existing ? '1fr' : '1fr 1fr', gap: 16, marginBottom: 24 }}>
                        {!form.use_existing && (
                            <div>
                                <label style={lbl}>Потоков регистрации</label>
                                <input style={{ ...inp, fontSize: '1.05em', padding: '12px 16px' }} type="number" min="1" max="50" value={form.birth_threads}
                                    onChange={e => setForm({ ...form, birth_threads: +e.target.value })} />
                                <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 4 }}>~300MB RAM / поток</div>
                            </div>
                        )}
                        <div>
                            <label style={lbl}>Потоков отправки</label>
                            <input style={{ ...inp, fontSize: '1.05em', padding: '12px 16px' }} type="number" min="1" max="100" value={form.send_threads}
                                onChange={e => setForm({ ...form, send_threads: +e.target.value })} />
                            <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 4 }}>SMTP параллельно</div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 12 }}>
                        <button onClick={create} disabled={loading || !form.name || form.providers.length === 0} style={{
                            padding: '14px 36px', fontWeight: 700, fontSize: '1em', border: 'none',
                            borderRadius: 8, cursor: loading || !form.name ? 'not-allowed' : 'pointer',
                            background: loading || !form.name || form.providers.length === 0 ? 'rgba(255,255,255,0.06)' : 'var(--accent)',
                            color: loading || !form.name || form.providers.length === 0 ? 'var(--text-muted)' : '#000',
                            transition: 'all 0.2s',
                        }}>
                            {loading ? '⏳ Создание...' : '🚀 Создать'}
                        </button>
                        <button onClick={() => setShowCreate(false)} style={{
                            padding: '14px 28px', fontWeight: 600, fontSize: '1em', border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 8, cursor: 'pointer', background: 'transparent', color: 'var(--text-secondary)',
                        }}>
                            Отмена
                        </button>
                    </div>
                </div>
            )
            }

            {/* Empty state */}
            {
                campaigns.length === 0 && !showCreate && (
                    <div className="card" style={{ padding: 50, textAlign: 'center', color: 'var(--text-muted)' }}>
                        <Rocket size={44} style={{ opacity: 0.2, marginBottom: 12 }} />
                        <div style={{ fontSize: '1.1em', fontWeight: 600, marginBottom: 6 }}>Нет кампаний</div>
                        <div style={{ fontSize: '0.85em' }}>Создайте первую кампанию для запуска Blitz Pipeline</div>
                    </div>
                )
            }

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
                                        <span><Mail size={12} /> Отпр: <b style={{ color: 'var(--success)' }}>{c.total_sent || 0}</b></span>
                                        <span>Ошибки: <b style={{ color: 'var(--danger)' }}>{c.total_errors || 0}</b></span>
                                        <span><Users size={12} /> Акки: <b>{c.accounts_born || 0}</b> / <b style={{ color: 'var(--danger)' }}>{c.accounts_dead || 0}</b> мёрт.</span>
                                        <span><Link2 size={12} /> Ссылки: <b>{c.links_active || 0}</b>/{c.links_total || 0}</span>
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
        </div >
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
