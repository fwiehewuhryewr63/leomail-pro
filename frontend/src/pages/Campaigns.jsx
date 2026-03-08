import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Rocket, Plus, Play, Pause, Square, Trash2,
    ChevronDown
} from 'lucide-react';
import { API } from '../api';

const STATUS_COLOR = { draft: '#888', running: '#10b981', paused: '#f59e0b', completed: '#3b82f6', stopped: '#ef4444' };
const STATUS_LABEL = { draft: 'DRAFT', running: 'ACTIVE', paused: 'PAUSED', completed: 'DONE', stopped: 'STOPPED' };

/* ── Accent colors per field ── */
const ACCENT = {
    farms: '#10b981',
    threads: '#06b6d4',
    emailsDay: '#f59e0b',
    linkCycles: '#a855f7',
    templates: '#10b981',
    links: '#f97316',
    recipients: '#06b6d4',
};

const lbl = (color) => ({
    fontSize: '0.72em', fontWeight: 700, textTransform: 'uppercase',
    letterSpacing: 1, color: color || 'var(--text-muted)', marginBottom: 5, display: 'block',
});

const inp = {
    width: '100%', padding: '9px 12px', background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
    color: 'var(--text-primary)', fontSize: '0.95em', outline: 'none',
    transition: 'border-color 0.2s', fontFamily: 'inherit',
};

/* ── MultiSelect dropdown ── */
function MultiSelect({ label, color, items, selected, setSelected, renderItem, emptyText }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, []);
    const toggle = (id) => setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    return (
        <div ref={ref} style={{ position: 'relative' }}>
            <label style={lbl(color)}>{label}</label>
            <div onClick={() => setOpen(!open)} style={{
                ...inp, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
                <span style={{ fontSize: '0.92em' }}>{selected.length > 0 ? `${selected.length} selected` : emptyText || 'Select...'}</span>
                <ChevronDown size={14} style={{ opacity: 0.4, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
            </div>
            {open && (
                <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                    marginTop: 4, background: '#141820', border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, maxHeight: 200, overflowY: 'auto', padding: 4,
                    boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                }}>
                    {items.length === 0 ? (
                        <div style={{ padding: 8, fontSize: '0.82em', color: 'var(--text-muted)' }}>Empty</div>
                    ) : items.map(item => {
                        const id = item.id;
                        const active = selected.includes(id);
                        return (
                            <div key={id} onClick={() => toggle(id)} style={{
                                padding: '5px 10px', borderRadius: 5, cursor: 'pointer', fontSize: '0.82em',
                                background: active ? `${color}15` : 'transparent',
                                color: active ? color : 'var(--text-secondary)',
                                fontWeight: active ? 600 : 400, display: 'flex', justifyContent: 'space-between',
                            }}>
                                {renderItem ? renderItem(item) : item.name}
                                {active && <span style={{ color }}>✓</span>}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/* ── Resource list with checkboxes (for Templates/Links/Recipients) ── */
function ResourceList({ label, color, icon, items, selected, setSelected, renderItem, emptyText }) {
    const toggle = (id) => setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    return (
        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ ...lbl(color), marginBottom: 8 }}>{icon} {label}</div>
            <div style={{ display: 'grid', gap: 3, maxHeight: 160, overflowY: 'auto' }}>
                {items.length === 0 ? (
                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>{emptyText || 'None available'}</div>
                ) : items.map(item => {
                    const active = selected.includes(item.id);
                    return (
                        <div key={item.id} onClick={() => toggle(item.id)} style={{
                            padding: '5px 8px', borderRadius: 5, cursor: 'pointer', fontSize: '0.82em',
                            background: active ? `${color}12` : 'transparent',
                            border: `1px solid ${active ? `${color}30` : 'rgba(255,255,255,0.04)'}`,
                            color: active ? color : 'var(--text-secondary)',
                            fontWeight: active ? 600 : 400, transition: 'all 0.15s',
                        }}>
                            {renderItem ? renderItem(item, active) : item.name}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default function Campaigns() {
    const [campaigns, setCampaigns] = useState([]);
    const [showCreate, setShowCreate] = useState(false);
    const [form, setForm] = useState({
        name: '', threads: 10, emails_per_day: 25, max_link_cycles: 0,
    });
    const [loading, setLoading] = useState(false);
    const [farms, setFarms] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [databases, setDatabases] = useState([]);
    const [linkPacks, setLinkPacks] = useState([]);
    const [selectedFarms, setSelectedFarms] = useState([]);
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
                farm_ids: selectedFarms,
                template_ids: selectedTemplates,
                database_ids: selectedDBs,
                link_pack_ids: selectedLinkPacks,
                providers: [], // derived from farms
                use_existing: true,
                emails_per_day_min: form.emails_per_day,
                emails_per_day_max: form.emails_per_day,
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
            alert('❌ Cannot start campaign:\n\n' + d.issues.map(i => '• ' + i).join('\n'));
            return;
        }
        load();
    };

    const del = async (id) => {
        if (!confirm('Delete campaign?')) return;
        await fetch(`${API}/campaigns/${id}`, { method: 'DELETE' });
        load();
    };

    return (
        <div className="page">
            {/* Header */}
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div className="page-breadcrumb">OPERATIONS / CAMPAIGNS</div>
                    <h2 className="page-title">
                        <Rocket size={22} /> Campaigns
                    </h2>
                </div>
                <button onClick={() => setShowCreate(!showCreate)} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '9px 20px',
                    fontWeight: 700, fontSize: '0.88em', border: 'none', borderRadius: 20,
                    cursor: 'pointer', background: 'var(--accent)', color: '#000',
                    fontFamily: 'inherit', transition: 'all 0.2s',
                }}>
                    <Plus size={16} /> New Campaign
                </button>
            </div>

            {/* ═══════════════ Create Form ═══════════════ */}
            {showCreate && (
                <div className="card" style={{ marginBottom: 14, padding: '18px 20px' }}>
                    {/* Campaign Name */}
                    <div style={{ marginBottom: 12 }}>
                        <label style={lbl()}>Campaign Name</label>
                        <input style={{ ...inp, fontSize: '1.05em', padding: '10px 14px' }} value={form.name}
                            onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Brazil Nutra Q1" />
                    </div>

                    {/* Row: Farms + Threads + Emails/Day + Link Cycles */}
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
                        <MultiSelect label="Farms" color={ACCENT.farms}
                            items={farms} selected={selectedFarms} setSelected={setSelectedFarms}
                            renderItem={f => <span>{f.name} <span style={{ opacity: 0.5 }}>({f.account_count || 0})</span></span>}
                            emptyText="All farms" />
                        <div>
                            <label style={lbl(ACCENT.threads)}>Threads</label>
                            <input style={inp} type="text" inputMode="numeric" value={form.threads}
                                onFocus={e => e.target.select()}
                                onChange={e => { const v = e.target.value.replace(/\D/g, ''); setForm({ ...form, threads: v === '' ? '' : v }); }}
                                onBlur={e => setForm({ ...form, threads: Math.min(100, Math.max(1, parseInt(e.target.value) || 1)) })} />
                            <div style={{ fontSize: '0.68em', color: ACCENT.threads, marginTop: 3, opacity: 0.7 }}>SMTP parallel</div>
                        </div>
                        <div>
                            <label style={lbl(ACCENT.emailsDay)}>Emails / Day</label>
                            <input style={inp} type="text" inputMode="numeric" value={form.emails_per_day}
                                onFocus={e => e.target.select()}
                                onChange={e => { const v = e.target.value.replace(/\D/g, ''); setForm({ ...form, emails_per_day: v === '' ? '' : v }); }}
                                onBlur={e => setForm({ ...form, emails_per_day: Math.max(1, parseInt(e.target.value) || 1) })} />
                            <div style={{ fontSize: '0.68em', color: ACCENT.emailsDay, marginTop: 3, opacity: 0.7 }}>per account, rotation</div>
                        </div>
                        <div>
                            <label style={lbl(ACCENT.linkCycles)}>Link Cycles</label>
                            <input style={inp} type="text" inputMode="numeric" value={form.max_link_cycles}
                                onFocus={e => e.target.select()}
                                onChange={e => { const v = e.target.value.replace(/\D/g, ''); setForm({ ...form, max_link_cycles: v === '' ? '' : v }); }}
                                onBlur={e => setForm({ ...form, max_link_cycles: Math.max(0, parseInt(e.target.value) || 0) })} />
                            <div style={{ fontSize: '0.68em', color: ACCENT.linkCycles, marginTop: 3, opacity: 0.7 }}>0 = unlimited</div>
                        </div>
                    </div>

                    {/* Row: Templates + Links + Recipients */}
                    <div className="config-row-3" style={{ marginBottom: 14 }}>
                        <ResourceList label="Templates" color={ACCENT.templates} icon="📝"
                            items={templates} selected={selectedTemplates} setSelected={setSelectedTemplates}
                            emptyText="No templates"
                            renderItem={(t) => (
                                <span>
                                    {t.name}
                                    {t.needs_names && <span style={{ fontSize: '0.68em', background: 'rgba(168,85,247,0.15)', color: '#a78bfa', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>VIP</span>}
                                    {!t.needs_names && <span style={{ fontSize: '0.68em', background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>BASIC</span>}
                                </span>
                            )} />
                        <ResourceList label="Links" color={ACCENT.links} icon="🔗"
                            items={linkPacks} selected={selectedLinkPacks} setSelected={setSelectedLinkPacks}
                            emptyText="No link packs"
                            renderItem={(l) => <span>{l.name} <span style={{ color: ACCENT.links, opacity: 0.7 }}>({l.total_count})</span></span>} />
                        <ResourceList label="Recipients" color={ACCENT.recipients} icon="📧"
                            items={databases} selected={selectedDBs} setSelected={setSelectedDBs}
                            emptyText="No databases"
                            renderItem={(d) => (
                                <span>
                                    {d.with_name ? '⭐' : ''} {d.name} <span style={{ color: ACCENT.recipients, opacity: 0.7 }}>({d.total_count - (d.used_count || 0)})</span>
                                    <span style={{ fontSize: '0.68em', background: d.with_name ? 'rgba(168,85,247,0.15)' : 'rgba(255,255,255,0.06)', color: d.with_name ? '#a78bfa' : 'var(--text-muted)', padding: '1px 4px', borderRadius: 3, marginLeft: 4 }}>{d.with_name ? 'VIP' : 'BASIC'}</span>
                                </span>
                            )} />
                    </div>

                    {/* Buttons */}
                    <div style={{ display: 'flex', gap: 10 }}>
                        <button onClick={create} disabled={loading || !form.name} style={{
                            padding: '12px 32px', fontWeight: 700, fontSize: '0.95em', border: 'none',
                            borderRadius: 8, cursor: loading || !form.name ? 'not-allowed' : 'pointer',
                            background: loading || !form.name ? 'rgba(255,255,255,0.06)' : 'var(--accent)',
                            color: loading || !form.name ? 'var(--text-muted)' : '#000',
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>
                            {loading ? '⏳ Creating...' : '🚀 Create'}
                        </button>
                        <button onClick={() => setShowCreate(false)} style={{
                            padding: '12px 24px', fontWeight: 600, fontSize: '0.95em',
                            border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                            cursor: 'pointer', background: 'transparent', color: 'var(--text-secondary)',
                            fontFamily: 'inherit',
                        }}>
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* ═══════════════ Empty State ═══════════════ */}
            {campaigns.length === 0 && !showCreate && (
                <div className="card" style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <Rocket size={40} style={{ opacity: 0.2, marginBottom: 10 }} />
                    <div style={{ fontSize: '1em', fontWeight: 600, marginBottom: 4 }}>No Campaigns</div>
                    <div style={{ fontSize: '0.82em' }}>Create your first campaign to launch Blitz Pipeline</div>
                </div>
            )}

            {/* ═══════════════ Campaign Cards ═══════════════ */}
            <div className="dash-grid">
                {campaigns.map(c => {
                    const pct = c.recipients_total > 0 ? Math.round(c.recipients_sent / c.recipients_total * 100) : 0;
                    const sColor = STATUS_COLOR[c.status] || '#888';
                    return (
                        <div key={c.id} className="card" style={{
                            padding: '16px 18px', cursor: 'pointer',
                            borderLeft: `3px solid ${sColor}`, transition: 'all 0.2s',
                        }} onClick={() => navigate(`/campaigns/${c.id}`)}>
                            {/* Title + status */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                <div style={{ fontSize: '1.05em', fontWeight: 800 }}>
                                    {c.name}
                                    {c.stop_reason && <span style={{ fontSize: '0.6em', marginLeft: 6, color: '#ef4444' }}>• {c.stop_reason}</span>}
                                </div>
                                <span style={{
                                    fontSize: '0.6em', fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                    background: `${sColor}22`, color: sColor, letterSpacing: 1,
                                }}>{STATUS_LABEL[c.status] || c.status}</span>
                            </div>

                            {/* Progress */}
                            <div style={{ fontSize: '0.82em', color: 'var(--text-secondary)', marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
                                <span><span style={{ color: ACCENT.farms, fontWeight: 700 }}>{c.recipients_sent || 0}</span> / {c.recipients_total || 0}</span>
                                {c.recipients_total > 0 && <span style={{ fontWeight: 700, color: sColor }}>{pct}%</span>}
                            </div>
                            <div className="progress-bar" style={{ marginBottom: 10, height: 4 }}>
                                <div className="progress-fill" style={{ width: `${pct}%`, background: sColor }} />
                            </div>

                            {/* Stats + actions */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>
                                    <span style={{ color: ACCENT.threads }}>{c.total_sent || 0}</span> sent
                                    {' • '}
                                    <span style={{ color: ACCENT.emailsDay }}>{c.accounts_born || 0}</span> accounts
                                    {c.created_at && <span> • {new Date(c.created_at).toLocaleDateString('en', { month: 'short', day: 'numeric' })}</span>}
                                </div>
                                <div style={{ display: 'flex', gap: 3 }} onClick={e => e.stopPropagation()}>
                                    {c.status === 'draft' && <ActionBtn color="#10b981" icon={Play} onClick={() => action(c.id, 'start')} title="Launch" />}
                                    {c.status === 'running' && <ActionBtn color="#f59e0b" icon={Pause} onClick={() => action(c.id, 'pause')} title="Pause" />}
                                    {c.status === 'paused' && <ActionBtn color="#10b981" icon={Play} onClick={() => action(c.id, 'start')} title="Resume" />}
                                    {['running', 'paused'].includes(c.status) && <ActionBtn color="#ef4444" icon={Square} onClick={() => action(c.id, 'stop')} title="Stop" />}
                                    {['draft', 'stopped', 'completed'].includes(c.status) && <ActionBtn color="#ef4444" icon={Trash2} onClick={() => del(c.id)} title="Delete" />}
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
        color, padding: 6, borderRadius: 5, display: 'flex', transition: 'all 0.2s',
    }}>
        <Icon size={13} />
    </button>
);
