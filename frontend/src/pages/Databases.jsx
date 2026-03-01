import React, { useState, useEffect, useRef } from 'react';
import {
    Database, Upload, Trash2, Eye, CheckCircle, X, Crown, RefreshCw, Calendar,
    ChevronUp, FileUp, Type, Package
} from 'lucide-react';
import { API } from '../api';

const formatDate = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: '2-digit' });
};

export default function Databases() {
    const [databases, setDatabases] = useState([]);
    const [showPaste, setShowPaste] = useState(false);
    const [uploadName, setUploadName] = useState('');
    const [uploadText, setUploadText] = useState('');
    const [detectedFormat, setDetectedFormat] = useState('email');
    const [preview, setPreview] = useState(null);
    const [selected, setSelected] = useState(new Set());
    const [expandedId, setExpandedId] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const fileRef = useRef();

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === databases.length ? new Set() : new Set(databases.map(d => d.id)));
    const batchDelete = async () => {
        if (!confirm(`Delete ${selected.size} databases?`)) return;
        await fetch(`${API}/databases/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
        setSelected(new Set()); load();
    };

    const load = () => fetch(`${API}/databases/`).then(r => r.json()).then(d => setDatabases(Array.isArray(d) ? d : [])).catch(() => { });
    useEffect(() => { load(); }, []);

    const detectFormat = (text) => {
        const lines = text.split('\n').map(l => l.trim()).filter(l => l && l.includes('@'));
        if (lines.length === 0) return 'email';
        const parts = lines[0].split(',').map(p => p.trim());
        return parts.length >= 2 ? 'email_first' : 'email';
    };

    const parseEntries = (text) => {
        return text.split('\n').map(l => l.trim()).filter(l => l).map(l => {
            const parts = l.split(',').map(p => p.trim());
            const email = parts[0] || '';
            if (!email.includes('@')) return null;
            return { email, first_name: parts[1] || '' };
        }).filter(Boolean);
    };

    useEffect(() => { if (uploadText.trim()) setDetectedFormat(detectFormat(uploadText)); }, [uploadText]);
    const detectedCount = uploadText.trim() ? parseEntries(uploadText).length : 0;

    const uploadDB = async () => {
        if (!uploadName || !uploadText.trim()) return;
        const entries = parseEntries(uploadText);
        if (entries.length === 0) return;
        const data = await (await fetch(`${API}/databases/upload`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: uploadName, entries })
        })).json();
        if (data.error) { alert(data.error); return; }
        setUploadName(''); setUploadText(''); setShowPaste(false); load();
    };

    const deleteDB = async (id) => {
        if (!confirm('Delete database?')) return;
        await fetch(`${API}/databases/${id}`, { method: 'DELETE' });
        if (expandedId === id) setExpandedId(null);
        load();
    };
    const viewDB = async (id) => setPreview(await (await fetch(`${API}/databases/${id}`)).json());

    const handleFile = (file) => {
        if (!file) return;
        if (!uploadName) setUploadName(file.name.replace(/\.[^/.]+$/, ""));
        const reader = new FileReader();
        reader.onload = (ev) => {
            setUploadText(ev.target.result);
            setDetectedFormat(detectFormat(ev.target.result));
            setShowPaste(true);
        };
        reader.readAsText(file);
    };

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    };

    const totalRecipients = databases.reduce((sum, d) => sum + (d.total_count || 0), 0);
    const totalSent = databases.reduce((sum, d) => sum + (d.sent_count || 0), 0);

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div style={{ fontSize: '0.6em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>RESOURCES / DATABASES</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Database size={22} /> Databases
                </h2>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => fileRef.current?.click()}
                        style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                        <FileUp size={14} /> Upload File
                    </button>
                    <button className={`btn ${showPaste ? 'btn-primary' : ''}`} onClick={() => setShowPaste(!showPaste)}
                        style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                        <Type size={14} /> Paste Text
                    </button>
                    <input ref={fileRef} type="file" accept=".txt,.csv" hidden onChange={e => handleFile(e.target.files[0])} />
                </div>
            </div>

            {/* ═══ FORMAT INFO BAR ═══ */}
            <div style={{
                padding: '8px 14px', borderRadius: 10, marginBottom: 16,
                background: 'rgba(16,185,129,0.03)', border: '1px solid rgba(16,185,129,0.1)',
                fontSize: '0.75em', display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
            }}>
                <span style={{ background: 'rgba(16,185,129,0.12)', color: '#10B981', padding: '2px 10px', borderRadius: 4, fontWeight: 700 }}>📧 email</span>
                <span style={{ color: 'var(--text-muted)' }}>BASIC</span>
                <span style={{ color: 'rgba(255,255,255,0.15)' }}>|</span>
                <span style={{ background: 'rgba(245,158,11,0.12)', color: '#F59E0B', padding: '2px 10px', borderRadius: 4, fontWeight: 700 }}>📧+👤 email,name</span>
                <span style={{ color: 'var(--text-muted)' }}>VIP</span>
                <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.9em' }}>Auto-detected from first line</span>
            </div>

            {/* ═══ STAT CARDS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
                <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid #10B981' }}>
                    <div style={{ fontSize: '1.6em', fontWeight: 900, color: '#10B981' }}>{databases.length}</div>
                    <div style={{ fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>DATABASES</div>
                </div>
                <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid #06B6D4' }}>
                    <div style={{ fontSize: '1.6em', fontWeight: 900, color: '#06B6D4' }}>{totalRecipients.toLocaleString()}</div>
                    <div style={{ fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>TOTAL RECIPIENTS</div>
                </div>
                <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid #F59E0B' }}>
                    <div style={{ fontSize: '1.6em', fontWeight: 900, color: '#F59E0B' }}>{totalSent.toLocaleString()} <span style={{ fontSize: '0.5em', fontWeight: 500, color: 'var(--text-muted)' }}>/ {totalRecipients.toLocaleString()}</span></div>
                    <div style={{ fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>SENT PROGRESS</div>
                    {totalRecipients > 0 && (
                        <div style={{ marginTop: 4, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${Math.round(totalSent / totalRecipients * 100)}%`, background: '#F59E0B', borderRadius: 2 }} />
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ PASTE PANEL ═══ */}
            {showPaste && (
                <div className="card" style={{ marginBottom: 16, padding: '16px 20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                        <div>
                            <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Database Name</label>
                            <input className="form-input" value={uploadName} onChange={e => setUploadName(e.target.value)}
                                placeholder="USA Finance 2024..." style={{ marginTop: 4 }} />
                        </div>
                        <div>
                            <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Detected Format</label>
                            <div style={{ marginTop: 8 }}>
                                <span style={{
                                    padding: '4px 12px', borderRadius: 6, fontSize: '0.82em', fontWeight: 700,
                                    background: detectedFormat === 'email' ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
                                    color: detectedFormat === 'email' ? '#10B981' : '#F59E0B',
                                }}>{detectedFormat === 'email' ? '📧 BASIC' : '⭐ VIP (email + name)'}</span>
                            </div>
                        </div>
                    </div>
                    <div>
                        <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Recipients (one per line)</label>
                        <textarea className="form-input" value={uploadText} onChange={e => setUploadText(e.target.value)}
                            placeholder={"email@domain.com,FirstName\nemail2@domain.com,Name\nemail3@domain.com"}
                            rows={6} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', marginTop: 4 }} />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
                        {detectedCount > 0 && <span style={{ fontSize: '0.78em', color: '#22C55E', fontWeight: 600 }}>✅ {detectedCount} recipients detected</span>}
                        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                            <button className="btn" onClick={() => fileRef.current?.click()} style={{ borderRadius: 20, padding: '7px 14px', fontSize: '0.78em' }}>Browse File</button>
                            <button className="btn btn-primary" onClick={uploadDB} disabled={!uploadName || detectedCount === 0}
                                style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                                <Upload size={14} /> Upload ({detectedCount})
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ═══ DROP ZONE ═══ */}
            <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                style={{
                    marginBottom: 20, padding: '16px 14px', textAlign: 'center', cursor: 'pointer',
                    border: `2px dashed ${dragOver ? '#10B981' : 'rgba(16,185,129,0.2)'}`,
                    borderRadius: 12, background: dragOver ? 'rgba(16,185,129,0.05)' : 'rgba(16,185,129,0.015)',
                    transition: 'all 0.2s',
                }}
            >
                <Upload size={18} style={{ color: 'var(--text-muted)', marginBottom: 4 }} />
                <div style={{ fontSize: '0.82em', color: 'var(--text-muted)' }}>Drop .txt / .csv file here</div>
            </div>

            {/* ═══ DATABASE TABLE ═══ */}
            {databases.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)' }}>
                    <Package size={40} style={{ opacity: 0.15, marginBottom: 12 }} />
                    <div style={{ fontSize: '1em', fontWeight: 700, marginBottom: 4 }}>No Databases</div>
                    <div style={{ fontSize: '0.82em' }}>Upload a file with recipient emails</div>
                </div>
            ) : (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Header */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '36px 1fr 80px 100px 140px 100px 100px',
                        padding: '10px 16px', borderBottom: '1px solid var(--border)',
                        fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)',
                        textTransform: 'uppercase', letterSpacing: 0.5, alignItems: 'center',
                    }}>
                        <div><input type="checkbox" checked={selected.size === databases.length && databases.length > 0} onChange={toggleAll} style={{ accentColor: 'var(--accent)' }} /></div>
                        <div>Name</div>
                        <div style={{ textAlign: 'center' }}>Format</div>
                        <div style={{ textAlign: 'center' }}>Recipients</div>
                        <div>Progress</div>
                        <div>Created</div>
                        <div style={{ textAlign: 'center' }}>Actions</div>
                    </div>

                    {/* Batch bar */}
                    {selected.size > 0 && (
                        <div style={{
                            padding: '6px 16px', background: 'rgba(239,68,68,0.06)',
                            borderBottom: '1px solid rgba(239,68,68,0.15)',
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        }}>
                            <span style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>{selected.size} selected</span>
                            <button className="btn btn-danger btn-sm" onClick={batchDelete}
                                style={{ borderRadius: 16, padding: '4px 14px', fontSize: '0.75em' }}>
                                <Trash2 size={11} /> Delete Selected
                            </button>
                        </div>
                    )}

                    {/* Rows */}
                    {databases.map(d => {
                        const pct = d.total_count > 0 ? Math.round((d.sent_count || 0) / d.total_count * 100) : 0;
                        return (
                            <div key={d.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                                <div style={{
                                    display: 'grid', gridTemplateColumns: '36px 1fr 80px 100px 140px 100px 100px',
                                    padding: '12px 16px', alignItems: 'center',
                                    background: selected.has(d.id) ? 'rgba(239,68,68,0.04)' : expandedId === d.id ? 'rgba(16,185,129,0.03)' : 'transparent',
                                }}>
                                    <div>
                                        <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggleSelect(d.id)}
                                            style={{ accentColor: selected.has(d.id) ? 'var(--danger)' : 'var(--accent)' }} />
                                    </div>

                                    {/* Name */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                        <div style={{
                                            width: 32, height: 32, borderRadius: 6, flexShrink: 0,
                                            background: d.with_name ? 'rgba(245,158,11,0.08)' : 'rgba(16,185,129,0.08)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            color: d.with_name ? '#F59E0B' : '#10B981',
                                        }}>
                                            {d.with_name ? <Crown size={16} /> : <Database size={16} />}
                                        </div>
                                        <span style={{ fontWeight: 700, fontSize: '0.9em' }}>{d.name}</span>
                                    </div>

                                    {/* Format badge */}
                                    <div style={{ textAlign: 'center' }}>
                                        <span style={{
                                            padding: '2px 8px', borderRadius: 4, fontSize: '0.68em', fontWeight: 700,
                                            background: d.with_name ? 'rgba(245,158,11,0.12)' : 'rgba(255,255,255,0.06)',
                                            color: d.with_name ? '#F59E0B' : 'var(--text-muted)',
                                        }}>{d.with_name ? '⭐ VIP' : 'BASIC'}</span>
                                    </div>

                                    {/* Recipients */}
                                    <div style={{ textAlign: 'center', fontWeight: 700, fontSize: '0.88em', color: '#10B981' }}>
                                        {(d.total_count || 0).toLocaleString()}
                                    </div>

                                    {/* Progress */}
                                    <div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                                            <span style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                                {(d.sent_count || 0).toLocaleString()}/{(d.total_count || 0).toLocaleString()}
                                            </span>
                                            <span style={{ fontSize: '0.68em', fontWeight: 700, color: pct >= 100 ? '#22C55E' : '#10B981' }}>{pct}%</span>
                                        </div>
                                        <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                                            <div style={{
                                                height: '100%', borderRadius: 2,
                                                width: `${pct}%`,
                                                background: pct >= 100 ? '#22C55E' : '#10B981',
                                                transition: 'width 0.5s ease',
                                            }} />
                                        </div>
                                    </div>

                                    {/* Created */}
                                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <Calendar size={10} /> {formatDate(d.created_at)}
                                    </div>

                                    {/* Actions */}
                                    <div style={{ display: 'flex', gap: 3, justifyContent: 'center' }}>
                                        <button className="btn btn-sm" onClick={() => viewDB(d.id)} style={{ padding: '4px 6px' }} title="Preview">
                                            <Eye size={12} />
                                        </button>
                                        {d.used_count > 0 && (
                                            <button className="btn btn-sm" title="Reset progress"
                                                style={{ padding: '4px 6px', borderColor: 'rgba(245,158,11,0.3)', color: '#F59E0B' }}
                                                onClick={async () => {
                                                    if (!confirm(`Reset progress for "${d.name}"?`)) return;
                                                    const res = await (await fetch(`${API}/databases/${d.id}/reset-progress`, { method: 'POST' })).json();
                                                    if (res.ok) { alert(`Reset! Cleared ${res.cleared_stats} entries`); load(); }
                                                }}>
                                                <RefreshCw size={12} />
                                            </button>
                                        )}
                                        <button className="btn btn-sm btn-danger" onClick={() => deleteDB(d.id)} style={{ padding: '4px 6px' }} title="Delete">
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ═══ PREVIEW MODAL ═══ */}
            {preview && (
                <div className="modal-overlay" onClick={() => setPreview(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <span style={{ fontWeight: 700, fontSize: '0.92em' }}>{preview.name}</span>
                            <button className="btn btn-sm" onClick={() => setPreview(null)}><X size={14} /></button>
                        </div>
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginBottom: 12 }}>
                            Showing {preview.preview?.length || 0} of {preview.total_count || 0}
                        </div>
                        <div style={{
                            fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78em', maxHeight: 360, overflow: 'auto',
                            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '2px 20px',
                        }}>
                            {preview.preview?.map((e, i) => (
                                <div key={i} style={{
                                    padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,0.03)',
                                    color: 'var(--text-secondary)', display: 'flex', gap: 8,
                                }}>
                                    <span style={{ color: 'rgba(255,255,255,0.2)', minWidth: 22, textAlign: 'right' }}>{i + 1}.</span>
                                    <span style={{ color: '#06B6D4' }}>{e}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
