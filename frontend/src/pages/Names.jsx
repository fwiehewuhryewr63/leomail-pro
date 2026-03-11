import React, { useState, useEffect, useRef } from 'react';
import {
    UserCircle, Upload, FileUp, Trash2, Calendar, CheckCircle, ChevronDown, ChevronUp, Type, Eye, Package
} from 'lucide-react';

import { API } from '../api';

const formatDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: '2-digit' });
};

export default function Names() {
    const [packs, setPacks] = useState([]);
    const [dragOver, setDragOver] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [expandedId, setExpandedId] = useState(null);
    const [previewData, setPreviewData] = useState(null);
    const [loadingPreview, setLoadingPreview] = useState(false);
    const [showPaste, setShowPaste] = useState(false);
    const [pasteText, setPasteText] = useState('');
    const [pasteName, setPasteName] = useState('');
    const [selected, setSelected] = useState(new Set());
    const fileRef = useRef();

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === packs.length ? new Set() : new Set(packs.map(p => p.id)));
    const batchDelete = async () => {
        if (!confirm(`Delete ${selected.size} packs?`)) return;
        await fetch(`${API}/names/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
        setSelected(new Set()); load();
    };

    const load = () => fetch(`${API}/names/`).then(r => r.json()).then(setPacks).catch(() => { });
    useEffect(() => { load(); }, []);

    const handleFile = async (file) => {
        if (!file) return;
        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`${API}/names/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            if (data.error) alert(data.error);
        } catch {
            alert('Upload error');
        }
        setUploading(false);
        load();
    };

    const handlePasteUpload = async () => {
        if (!pasteText.trim()) return;
        setUploading(true);
        try {
            const res = await fetch(`${API}/names/upload-text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: pasteName, text: pasteText })
            });
            const data = await res.json();
            if (data.error) alert(data.error);
            else { setPasteText(''); setPasteName(''); setShowPaste(false); }
        } catch { alert('Upload error'); }
        setUploading(false);
        load();
    };

    const pasteCount = pasteText.trim() ? pasteText.split('\n').filter(l => l.trim().includes(',')).length : 0;

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    };

    const deletePack = async (id) => {
        if (!confirm('Delete this name pack?')) return;
        await fetch(`${API}/names/${id}`, { method: 'DELETE' });
        if (expandedId === id) { setExpandedId(null); setPreviewData(null); }
        load();
    };

    const togglePreview = async (id) => {
        if (expandedId === id) {
            setExpandedId(null);
            setPreviewData(null);
            return;
        }
        setExpandedId(id);
        setLoadingPreview(true);
        try {
            const res = await fetch(`${API}/names/${id}/preview`);
            const data = await res.json();
            setPreviewData(data);
        } catch {
            setPreviewData({ error: 'Failed to load', names: [] });
        }
        setLoadingPreview(false);
    };

    const totalNames = packs.reduce((sum, p) => sum + (p.total_count || 0), 0);

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div className="page-breadcrumb">RESOURCES / NAMES</div>
                    <h2 className="page-title">
                        <UserCircle size={22} /> Name Packs
                    </h2>
                    <div className="engine-hero-strip">
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Packs</span>
                            <span className="engine-hero-chip-value">{packs.length} loaded</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Names</span>
                            <span className="engine-hero-chip-value">{totalNames.toLocaleString()}</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Average</span>
                            <span className="engine-hero-chip-value">{packs.length > 0 ? Math.round(totalNames / packs.length).toLocaleString() : '0'} / pack</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Selection</span>
                            <span className="engine-hero-chip-value">{selected.size} marked</span>
                        </div>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="engine-primary-action" onClick={() => fileRef.current?.click()}>
                        <FileUp size={14} /> Upload File
                    </button>
                    <button className="engine-secondary-action" onClick={() => setShowPaste(!showPaste)}>
                        <Type size={14} /> Paste Text
                    </button>
                    <input ref={fileRef} type="file" accept=".txt,.csv" hidden onChange={e => handleFile(e.target.files[0])} />
                </div>
            </div>

            {/* ═══ STAT CARDS ═══ */}
            <div className="config-row-3" style={{ marginBottom: 20 }}>
                {[
                    { label: 'PACKS', value: packs.length, color: '#10B981' },
                    { label: 'TOTAL NAMES', value: totalNames.toLocaleString(), color: '#10B981' },
                    { label: 'AVG PER PACK', value: packs.length > 0 ? Math.round(totalNames / packs.length).toLocaleString() : '0', color: '#06B6D4' },
                ].map(s => (
                    <div key={s.label} className="card" style={{ padding: '14px 18px', borderLeft: `3px solid ${s.color}` }}>
                        <div style={{ fontSize: '1.6em', fontWeight: 900, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* ═══ PASTE PANEL ═══ */}
            {showPaste && (
                <div className="card engine-card" style={{ marginBottom: 16, padding: '16px 20px' }}>
                    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                        <div style={{ flex: 1 }}>
                            <label className="form-label">Pack Name</label>
                            <input className="form-input" value={pasteName} onChange={e => setPasteName(e.target.value)}
                                placeholder="Optional..." style={{ marginTop: 4 }} />
                        </div>
                    </div>
                    <label className="form-label">Names (First,Last — one per line)</label>
                    <textarea className="form-input" value={pasteText} onChange={e => setPasteText(e.target.value)}
                        placeholder={"John,Smith\nEmily,Johnson\nMichael,Brown"}
                        rows={6} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', marginTop: 4 }} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
                        {pasteCount > 0 && <span style={{ fontSize: '0.78em', color: 'var(--success)', fontWeight: 600 }}>✅ {pasteCount} names detected</span>}
                        <button className="btn btn-primary" onClick={handlePasteUpload} disabled={pasteCount === 0 || uploading}
                            style={{ marginLeft: 'auto', borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                            <Upload size={14} /> Upload {pasteCount} names
                        </button>
                    </div>
                </div>
            )}

            {/* ═══ DROP ZONE ═══ */}
            <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                style={{
                    marginBottom: 20, padding: '16px 14px', textAlign: 'center', cursor: 'pointer',
                    border: `2px dashed ${dragOver ? 'var(--accent)' : 'rgba(16,185,129,0.2)'}`,
                    borderRadius: 12, background: dragOver ? 'rgba(16,185,129,0.05)' : 'rgba(16,185,129,0.015)',
                    transition: 'all 0.2s',
                }}
                onClick={() => fileRef.current?.click()}
            >
                <Upload size={18} style={{ color: 'var(--text-muted)', marginBottom: 4 }} />
                <div style={{ fontSize: '0.82em', color: 'var(--text-muted)' }}>
                    Drop .txt file here · First,Last per line
                </div>
            </div>

            {/* ═══ PACK TABLE ═══ */}
            {packs.length === 0 ? (
                <div className="card polished-empty-card">
                    <Package size={40} />
                    <div className="polished-empty-title">No name packs</div>
                    <div className="polished-empty-copy">Upload a source file to keep personalization inputs ready for campaigns and autoreg.</div>
                </div>
            ) : (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Table header */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '36px 1fr 120px 100px 100px 80px',
                        padding: '10px 16px', borderBottom: '1px solid var(--border)',
                        fontSize: '0.78em', fontWeight: 700, color: 'var(--text-muted)',
                        textTransform: 'uppercase', letterSpacing: 0.5, alignItems: 'center',
                    }}>
                        <div><input type="checkbox" checked={selected.size === packs.length && packs.length > 0} onChange={toggleAll} /></div>
                        <div>Pack Name</div>
                        <div style={{ textAlign: 'center' }}>Names</div>
                        <div style={{ textAlign: 'center' }}>Format</div>
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
                    {packs.map(p => (
                        <div key={p.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                            <div
                                style={{
                                    display: 'grid', gridTemplateColumns: '36px 1fr 120px 100px 100px 80px',
                                    padding: '12px 16px', alignItems: 'center', cursor: 'pointer',
                                    background: selected.has(p.id) ? 'rgba(239,68,68,0.04)' : expandedId === p.id ? 'rgba(16,185,129,0.03)' : 'transparent',
                                    transition: 'background 0.15s',
                                }}
                                onClick={() => togglePreview(p.id)}
                            >
                                <div onClick={e => e.stopPropagation()}>
                                    <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSelect(p.id)} />
                                </div>

                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <div style={{
                                        width: 32, height: 32, borderRadius: 6, background: 'rgba(16,185,129,0.08)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#10B981', flexShrink: 0,
                                    }}>
                                        <UserCircle size={16} />
                                    </div>
                                    <span style={{ fontWeight: 700, fontSize: '0.95em' }}>{p.name}</span>
                                </div>

                                <div style={{ textAlign: 'center' }}>
                                    <span style={{
                                        padding: '3px 10px', borderRadius: 12, fontSize: '0.82em', fontWeight: 700,
                                        background: 'rgba(16,185,129,0.1)', color: '#10B981',
                                        border: '1px solid rgba(16,185,129,0.15)',
                                    }}>
                                        {(p.total_count || 0).toLocaleString()}
                                    </span>
                                </div>

                                <div style={{ textAlign: 'center' }}>
                                    <span style={{
                                        padding: '3px 10px', borderRadius: 12, fontSize: '0.78em', fontWeight: 700,
                                        background: 'rgba(59,130,246,0.1)', color: '#60A5FA',
                                        border: '1px solid rgba(59,130,246,0.12)',
                                    }}>
                                        First,Last
                                    </span>
                                </div>

                                <div style={{ fontSize: '0.85em', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <Calendar size={12} /> {formatDate(p.created_at)}
                                </div>

                                <div style={{ display: 'flex', gap: 3, justifyContent: 'center' }} onClick={e => e.stopPropagation()}>
                                    <button className="btn btn-sm" onClick={() => togglePreview(p.id)} style={{ padding: '4px 6px' }}
                                        title="Preview">
                                        {expandedId === p.id ? <ChevronUp size={12} /> : <Eye size={12} />}
                                    </button>
                                    <button className="btn btn-sm btn-danger" onClick={() => deletePack(p.id)} style={{ padding: '4px 6px' }}
                                        title="Delete">
                                        <Trash2 size={12} />
                                    </button>
                                </div>
                            </div>

                            {/* Expanded preview */}
                            {expandedId === p.id && (
                                <div style={{
                                    padding: '14px 20px', background: 'rgba(16,185,129,0.02)',
                                    borderTop: '1px solid rgba(16,185,129,0.1)', maxHeight: 280, overflowY: 'auto',
                                }}>
                                    {loadingPreview ? (
                                        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: '0.85em' }}>Loading...</div>
                                    ) : previewData?.error ? (
                                        <div style={{ color: 'var(--danger)', fontSize: '0.85em' }}>❌ {previewData.error}</div>
                                    ) : (
                                        <>
                                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginBottom: 10 }}>
                                                Showing {previewData?.names?.length || 0} of {previewData?.total || 0}
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '3px 24px' }}>
                                                {(previewData?.names || []).map((name, i) => (
                                                    <div key={i} style={{
                                                        fontSize: '0.8em', padding: '2px 0',
                                                        display: 'flex', alignItems: 'center', gap: 8,
                                                        fontFamily: 'JetBrains Mono, monospace',
                                                    }}>
                                                        <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.85em', minWidth: 22, textAlign: 'right' }}>{i + 1}.</span>
                                                        <span style={{ color: 'var(--text-secondary)' }}>{name}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
