import React, { useState, useEffect } from 'react';
import { Database, Upload, Trash2, Eye, CheckCircle, X, Crown, Mail, User, Users as UsersIcon, RefreshCw } from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

export default function Databases() {
    const { t } = useI18n();
    const [databases, setDatabases] = useState([]);
    const [showUpload, setShowUpload] = useState(false);
    const [uploadName, setUploadName] = useState('');
    const [uploadText, setUploadText] = useState('');
    const [detectedFormat, setDetectedFormat] = useState('email');
    const [preview, setPreview] = useState(null);
    const [selected, setSelected] = useState(new Set());

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === databases.length ? new Set() : new Set(databases.map(d => d.id)));
    const batchDelete = async () => {
        if (!confirm(`Удалить ${selected.size} баз?`)) return;
        await fetch(`${API}/databases/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
        setSelected(new Set()); load();
    };

    const load = () => fetch(`${API}/databases/`).then(r => r.json()).then(d => setDatabases(Array.isArray(d) ? d : [])).catch(() => { });
    useEffect(() => { load(); }, []);

    const detectFormat = (text) => {
        const lines = text.split('\n').map(l => l.trim()).filter(l => l && l.includes('@'));
        if (lines.length === 0) return 'email';
        const firstLine = lines[0];
        const parts = firstLine.split(',').map(p => p.trim());
        if (parts.length >= 3) return 'email_first_last';
        if (parts.length === 2) return 'email_first';
        return 'email';
    };

    const parseEntries = (text) => {
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);
        return lines.map(l => {
            const parts = l.split(',').map(p => p.trim());
            const email = parts[0] || '';
            if (!email.includes('@')) return null;
            return {
                email,
                first_name: parts[1] || '',
                last_name: parts[2] || '',
            };
        }).filter(Boolean);
    };

    const uploadDB = async () => {
        if (!uploadName || !uploadText.trim()) return;
        const entries = parseEntries(uploadText);
        if (entries.length === 0) return;

        const data = await (await fetch(`${API}/databases/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: uploadName, entries })
        })).json();
        if (data.error) { alert(data.error); return; }
        setUploadName(''); setUploadText(''); setShowUpload(false); load();
    };

    const deleteDB = async (id) => { if (!confirm(t('confirmDeleteDB'))) return; await fetch(`${API}/databases/${id}`, { method: 'DELETE' }); load(); };
    const viewDB = async (id) => setPreview(await (await fetch(`${API}/databases/${id}`)).json());

    const handleFile = (e) => {
        const file = e.dataTransfer?.files[0] || e.target?.files[0];
        if (file) {
            if (!uploadName) setUploadName(file.name.replace(/\.[^/.]+$/, ""));
            const reader = new FileReader();
            reader.onload = (ev) => {
                const text = ev.target.result;
                setUploadText(text);
                setDetectedFormat(detectFormat(text));
            };
            reader.readAsText(file);
        }
    };

    // Auto-detect on text change
    useEffect(() => {
        if (uploadText.trim()) {
            setDetectedFormat(detectFormat(uploadText));
        }
    }, [uploadText]);

    const detectedCount = uploadText.trim() ? parseEntries(uploadText).length : 0;

    const FORMAT_INFO = {
        email: {
            label: 'BASIC',
            desc: 'Только email',
            color: 'var(--text-muted)',
            icon: '📧',
            example: 'jessica.smith92@gmail.com\njohn.doe@yahoo.com\nmaria.santos@aol.com',
            vars: ['{{USERNAME}} — часть email до @', '{{LINK}} — ссылка из кампании'],
            rules: '{{USERNAME}} работает с любой базой',
        },
        email_first: {
            label: 'VIP',
            desc: 'Email + Имя через запятую',
            color: '#f59e0b',
            icon: '⭐',
            example: 'jessica.smith92@gmail.com,Jessica\njohn.doe@yahoo.com,John\nmaria.santos@aol.com,Maria',
            vars: ['{{USERNAME}} — часть email до @', '{{NAME}} — имя из базы', '{{LINK}} — ссылка из кампании'],
            rules: '{{NAME}} работает ТОЛЬКО с VIP базой!',
        },
        // email_first_last detected → treat as VIP
        email_first_last: {
            label: 'VIP',
            desc: 'Email + Имя (+ фамилия)',
            color: '#f59e0b',
            icon: '⭐',
            example: 'jessica@gmail.com,Jessica,Smith\njohn@yahoo.com,John,Doe',
            vars: ['{{USERNAME}} — часть email до @', '{{NAME}} — имя из базы', '{{LINK}} — ссылка из кампании'],
            rules: '{{NAME}} работает ТОЛЬКО с VIP базой!',
        },
    };

    const fmt = FORMAT_INFO[detectedFormat];

    return (
        <div className="page">
            <h2 className="page-title"><Database size={22} /> {t('databasesTitle')}</h2>

            <button className="btn btn-primary" onClick={() => setShowUpload(!showUpload)} style={{ marginBottom: 16 }}>
                <Upload size={14} /> {t('uploadDatabase')}
            </button>

            {showUpload && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div className="card-title">{t('uploadRecipients')}</div>

                    <div className="form-group">
                        <label className="form-label">{t('databaseName')}</label>
                        <input className="form-input" value={uploadName} onChange={e => setUploadName(e.target.value)}
                            placeholder="USA Finance 2024..." />
                    </div>

                    {/* BASIC / VIP format cards — only 2 types */}
                    <div style={{ marginBottom: 16 }}>
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
                            2 типа баз
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                            {[['email', FORMAT_INFO.email], ['email_first', FORMAT_INFO.email_first]].map(([key, info]) => {
                                const isActive = key === 'email' ? detectedFormat === 'email' : (detectedFormat === 'email_first' || detectedFormat === 'email_first_last');
                                return (
                                    <div key={key} style={{
                                        padding: '10px 12px', borderRadius: 8,
                                        border: isActive ? `2px solid ${info.color}` : '1px solid var(--border-subtle)',
                                        background: isActive ? `${info.color}10` : 'var(--bg-elevated)',
                                        transition: 'all 0.2s',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                            <span>{info.icon}</span>
                                            <span style={{ fontSize: '0.85em', fontWeight: 800, color: isActive ? info.color : 'var(--text-muted)' }}>
                                                {info.label}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '0.72em', color: 'var(--text-secondary)', marginBottom: 4 }}>{info.desc}</div>
                                        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65em', color: 'var(--text-muted)' }}>
                                            {info.example.split('\n').map((l, i) => <div key={i}>{l}</div>)}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Template variables + compatibility rules */}
                    <div style={{
                        padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: 12,
                        background: `${fmt.color}08`,
                        border: `1px solid ${fmt.color}25`,
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                            <span>{fmt.icon}</span>
                            <span style={{ color: fmt.color, fontWeight: 800, fontSize: '0.85em' }}>{fmt.label}</span>
                            <span style={{ fontSize: '0.75em', color: 'var(--text-secondary)' }}>— {fmt.desc}</span>
                        </div>
                        <div style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginBottom: 8 }}>
                            <div style={{ fontWeight: 700, marginBottom: 3, color: fmt.color }}>Переменные для шаблонов:</div>
                            {fmt.vars.map((v, i) => (
                                <div key={i} style={{ fontFamily: 'JetBrains Mono, monospace', padding: '1px 0' }}>{v}</div>
                            ))}
                        </div>
                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 6 }}>
                            <div style={{ fontWeight: 700, marginBottom: 3 }}>Совместимость:</div>
                            <div>✅ BASIC шаблон + BASIC база → OK</div>
                            <div>✅ BASIC шаблон + VIP база → OK</div>
                            <div>✅ VIP шаблон + VIP база → OK (имя из базы)</div>
                            <div>✅ VIP шаблон + BASIC база → OK ({'{{NAME}}'} = username)</div>
                        </div>
                    </div>

                    {/* Text area */}
                    <div className="form-group">
                        <div onDrop={e => { e.preventDefault(); handleFile(e); }} onDragOver={e => e.preventDefault()}
                            style={{ border: '2px dashed var(--border-hover)', borderRadius: 12, padding: 8 }}>
                            <textarea className="form-input" value={uploadText} onChange={e => setUploadText(e.target.value)}
                                placeholder={"email@example.com,Name,LastName\nemail2@example.com,Name2\nemail3@example.com\n\n" + (t('orDragFile') || 'or drag & drop a .txt/.csv file')}
                                rows={8}
                                style={{ border: 'none', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em' }} />
                        </div>
                        <div style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                            <span>{detectedCount > 0 ? `${detectedCount} ${t('recipientsDetected')}` : t('supportedFormats')}</span>
                            {detectedCount > 0 && (
                                <span style={{ color: fmt.color, fontWeight: 600 }}>
                                    Format: {FORMAT_INFO[detectedFormat].desc}
                                </span>
                            )}
                        </div>
                    </div>

                    <input type="file" accept=".txt,.csv" onChange={handleFile} style={{ display: 'none' }} id="db-file-input" />
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-primary" onClick={uploadDB} disabled={!uploadName || detectedCount === 0}>
                            <CheckCircle size={14} /> {t('upload')} ({detectedCount})
                        </button>
                        <label htmlFor="db-file-input" className="btn" style={{ cursor: 'pointer' }}>{t('browseFile')}</label>
                    </div>
                </div>
            )}

            {databases.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                    <Database size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />{t('noDatabases')}
                </div>
            ) : (
                <div style={{ display: 'grid', gap: 8 }}>
                    {/* Batch select bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85em' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: 'var(--text-muted)' }}>
                            <input type="checkbox" checked={selected.size === databases.length && databases.length > 0} onChange={toggleAll} /> Выбрать всё
                        </label>
                        {selected.size > 0 && (
                            <button className="btn btn-danger btn-sm" onClick={batchDelete} style={{ marginLeft: 'auto' }}>
                                <Trash2 size={12} /> Удалить выбранные ({selected.size})
                            </button>
                        )}
                    </div>
                    {databases.map(d => (
                        <div key={d.id} className="card" style={{ border: selected.has(d.id) ? '1px solid var(--danger)' : undefined }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggleSelect(d.id)} style={{ accentColor: 'var(--danger)' }} />
                                    <div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ fontWeight: 600, fontSize: '0.9em' }}>{d.name}</span>
                                            <span style={{
                                                background: d.with_name ? 'linear-gradient(135deg, #f59e0b, #f97316)' : 'rgba(255,255,255,0.08)',
                                                color: d.with_name ? '#000' : 'var(--text-muted)',
                                                padding: '1px 8px', borderRadius: 4, fontSize: '0.6em',
                                                fontWeight: 800, letterSpacing: '0.05em'
                                            }}>
                                                {d.with_name ? '👑 VIP' : '📧 BASIC'}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 3 }}>
                                            {d.total_count?.toLocaleString()} {t('total')}
                                            {d.sent_count > 0 && (
                                                <span style={{ color: 'var(--success)', fontWeight: 600 }}> · ✉ {d.sent_count} отпр.</span>
                                            )}
                                            {d.error_count > 0 && (
                                                <span style={{ color: 'var(--danger)', fontWeight: 600 }}
                                                    title={d.error_details ? Object.entries(d.error_details).map(([k, v]) => `${k}: ${v}`).join(', ') : ''}
                                                > · ⚠ {d.error_count} ошиб.</span>
                                            )}
                                            {' · '}{t('remaining')}: <span style={{ fontWeight: 600, color: d.remaining === 0 ? 'var(--success)' : 'var(--accent)' }}>{d.remaining?.toLocaleString()}</span>
                                            {d.invalid_count > 0 && <span style={{ color: 'var(--danger)' }}> · {d.invalid_count} {t('invalid')}</span>}
                                        </div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: 4 }}>
                                    <button className="btn btn-sm" onClick={() => viewDB(d.id)}><Eye size={13} /></button>
                                    {d.used_count > 0 && (
                                        <button className="btn btn-sm" title="Сбросить прогресс" style={{ borderColor: 'var(--warning)', color: 'var(--warning)' }}
                                            onClick={async () => {
                                                if (!confirm(`Сбросить прогресс базы "${d.name}"? Все получатели станут доступны для повторной рассылки.`)) return;
                                                const res = await (await fetch(`${API}/databases/${d.id}/reset-progress`, { method: 'POST' })).json();
                                                if (res.ok) {
                                                    alert(`Прогресс сброшен! Очищено ${res.cleared_stats} записей`);
                                                    load();
                                                }
                                            }}><RefreshCw size={13} /></button>
                                    )}
                                    <button className="btn btn-sm btn-danger" onClick={() => deleteDB(d.id)}><Trash2 size={13} /></button>
                                </div>
                            </div>
                            {(() => {
                                const pct = d.total_count > 0 ? Math.round((d.sent_count || 0) / d.total_count * 100) : 0;
                                const barColor = pct >= 100 ? '#22c55e' : pct > 50 ? 'var(--gradient-primary)' : 'var(--gradient-primary)';
                                return (
                                    <div style={{ marginTop: 8, position: 'relative' }}>
                                        <div style={{ width: '100%', height: 6, background: 'var(--bg-input)', borderRadius: 3, overflow: 'hidden' }}>
                                            <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: 3, transition: 'width 0.5s ease' }} />
                                        </div>
                                        {pct > 0 && (
                                            <div style={{ fontSize: '0.6em', color: 'var(--text-muted)', textAlign: 'right', marginTop: 2 }}>
                                                {pct}% отправлено
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    ))}
                </div>
            )}

            {preview && (
                <div className="modal-overlay" onClick={() => setPreview(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <div className="card-title" style={{ margin: 0 }}>{preview.name}</div>
                            <button className="btn btn-sm" onClick={() => setPreview(null)}><X size={14} /></button>
                        </div>
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginBottom: 12 }}>
                            {t('first') || 'First'} {preview.preview?.length} {t('of') || 'of'} {preview.total_count}
                        </div>
                        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78em', maxHeight: 320, overflow: 'auto' }}>
                            {preview.preview?.map((e, i) => (
                                <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>{e}</div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
