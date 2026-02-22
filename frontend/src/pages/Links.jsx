import React, { useState, useEffect, useRef } from 'react';
import {
    Link as LinkIcon, Upload, FileUp, Trash2, Calendar, FileText, CheckCircle, ChevronDown, ChevronUp, ExternalLink, Type
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

const formatDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export default function Links() {
    const { t } = useI18n();
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
        if (!confirm(`Удалить ${selected.size} паков?`)) return;
        await fetch(`${API}/links/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
        setSelected(new Set()); load();
    };

    const load = () => fetch(`${API}/links/`).then(r => r.json()).then(setPacks).catch(() => { });
    useEffect(() => { load(); }, []);

    const handleFile = async (file) => {
        if (!file) return;
        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`${API}/links/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            if (data.error) alert(data.error);
        } catch (e) {
            alert('Ошибка загрузки');
        }
        setUploading(false);
        load();
    };

    const handlePasteUpload = async () => {
        if (!pasteText.trim()) return;
        setUploading(true);
        try {
            const res = await fetch(`${API}/links/upload-text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: pasteName, text: pasteText })
            });
            const data = await res.json();
            if (data.error) alert(data.error);
            else { setPasteText(''); setPasteName(''); setShowPaste(false); }
        } catch (e) { alert('Ошибка загрузки'); }
        setUploading(false);
        load();
    };

    const pasteCount = pasteText.trim() ? pasteText.split('\n').filter(l => l.trim().startsWith('http')).length : 0;

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    };

    const deletePack = async (id) => {
        if (!confirm('Удалить этот пак?')) return;
        await fetch(`${API}/links/${id}`, { method: 'DELETE' });
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
            const res = await fetch(`${API}/links/${id}/preview`);
            const data = await res.json();
            setPreviewData(data);
        } catch {
            setPreviewData({ error: 'Ошибка загрузки', links: [] });
        }
        setLoadingPreview(false);
    };

    return (
        <div className="page">
            <h2 className="page-title"><LinkIcon size={24} /> Паки ссылок</h2>

            <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginBottom: 20 }}>
                <div className="card">
                    <div className="card-title"><LinkIcon size={13} style={{ marginRight: 6, color: 'var(--accent)' }} /> ПАКИ</div>
                    <div className="card-value">{packs.length}</div>
                </div>
                <div className="card">
                    <div className="card-title"><LinkIcon size={13} style={{ marginRight: 6, color: 'var(--success)' }} /> ВСЕГО ССЫЛОК</div>
                    <div className="card-value" style={{ WebkitTextFillColor: 'var(--success)' }}>
                        {packs.reduce((sum, p) => sum + (p.total_count || 0), 0)}
                    </div>
                </div>
            </div>

            {/* Upload buttons */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button className="btn btn-primary" onClick={() => fileRef.current?.click()}>
                    <FileUp size={14} /> Загрузить файл
                </button>
                <button className={`btn ${showPaste ? 'btn-primary' : ''}`} onClick={() => setShowPaste(!showPaste)}>
                    <Type size={14} /> Вставить текстом
                </button>
                <input ref={fileRef} type="file" accept=".txt" hidden onChange={e => handleFile(e.target.files[0])} />
            </div>

            {/* Text paste area */}
            {showPaste && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div className="form-group">
                        <label className="form-label">Название пака</label>
                        <input className="form-input" value={pasteName} onChange={e => setPasteName(e.target.value)} placeholder="Необязательно..." />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Ссылки (одна на строку)</label>
                        <textarea className="form-input" value={pasteText} onChange={e => setPasteText(e.target.value)}
                            placeholder={"https://example.com/link1\nhttps://example.com/link2"}
                            rows={8} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em' }} />
                    </div>
                    {pasteCount > 0 && <div style={{ fontSize: '0.8em', color: 'var(--success)', marginBottom: 8 }}>✅ Найдено {pasteCount} ссылок</div>}
                    <button className="btn btn-primary" onClick={handlePasteUpload} disabled={pasteCount === 0 || uploading}>
                        <Upload size={14} /> Загрузить {pasteCount} ссылок
                    </button>
                </div>
            )}

            {/* Drop zone */}
            <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`upload-zone ${dragOver ? 'dragover' : ''}`}
                style={{ marginBottom: 20, cursor: 'pointer', padding: '20px 14px' }}
            >
                <div style={{ textAlign: 'center', fontSize: '0.85em', color: 'var(--text-muted)' }}>
                    или перетащите .txt файл сюда
                </div>
            </div>

            {/* List */}
            {packs.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    Нет загруженных паков ссылок.
                </div>
            ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                    {/* Batch select bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85em' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: 'var(--text-muted)' }}>
                            <input type="checkbox" checked={selected.size === packs.length && packs.length > 0} onChange={toggleAll} /> Выбрать всё
                        </label>
                        {selected.size > 0 && (
                            <button className="btn btn-danger btn-sm" onClick={batchDelete} style={{ marginLeft: 'auto' }}>
                                <Trash2 size={12} /> Удалить выбранные ({selected.size})
                            </button>
                        )}
                    </div>
                    {packs.map(p => (
                        <div key={p.id} className="card" style={{ padding: 0, overflow: 'hidden', border: selected.has(p.id) ? '1px solid var(--danger)' : undefined }}>
                            <div
                                style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', cursor: 'pointer' }}
                                onClick={() => togglePreview(p.id)}
                            >
                                <input type="checkbox" checked={selected.has(p.id)} onChange={(e) => { e.stopPropagation(); toggleSelect(p.id); }} style={{ accentColor: 'var(--danger)' }} />
                                <div style={{
                                    width: 40, height: 40, borderRadius: 8, background: 'var(--bg-secondary)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)'
                                }}>
                                    <FileText size={20} />
                                </div>

                                <div style={{ flex: 1 }}>
                                    <div style={{ fontWeight: 700, fontSize: '1.05em', marginBottom: 4 }}>{p.name}</div>
                                    <div style={{ display: 'flex', gap: 12, fontSize: '0.8em', color: 'var(--text-muted)' }}>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <CheckCircle size={11} /> {p.total_count} ссылок
                                        </span>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <Calendar size={11} /> {formatDate(p.created_at)}
                                        </span>
                                    </div>
                                </div>

                                {expandedId === p.id ? <ChevronUp size={18} style={{ color: 'var(--accent)' }} /> : <ChevronDown size={18} style={{ color: 'var(--text-muted)' }} />}

                                <button className="btn btn-danger btn-sm" onClick={(e) => { e.stopPropagation(); deletePack(p.id); }} title="Удалить пак">
                                    <Trash2 size={16} />
                                </button>
                            </div>

                            {/* Expandable preview */}
                            {expandedId === p.id && (
                                <div style={{ borderTop: '1px solid var(--border)', padding: '12px 20px', background: 'var(--bg-secondary)', maxHeight: 300, overflowY: 'auto' }}>
                                    {loadingPreview ? (
                                        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 10 }}>Загрузка...</div>
                                    ) : previewData?.error ? (
                                        <div style={{ color: 'var(--danger)', fontSize: '0.85em' }}>❌ {previewData.error}</div>
                                    ) : (
                                        <>
                                            <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginBottom: 8 }}>
                                                Показано {previewData?.links?.length || 0} из {previewData?.total || 0}
                                            </div>
                                            {(previewData?.links || []).map((link, i) => (
                                                <div key={i} style={{
                                                    fontSize: '0.82em', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)',
                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                    fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)'
                                                }}>
                                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85em', minWidth: 20 }}>{i + 1}</span>
                                                    <ExternalLink size={11} style={{ flexShrink: 0 }} />
                                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{link}</span>
                                                </div>
                                            ))}
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
