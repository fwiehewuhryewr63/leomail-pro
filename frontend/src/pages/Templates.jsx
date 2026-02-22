import React, { useState, useEffect, useRef } from 'react';
import { FileText, Plus, Trash2, Eye, X, Upload, Package, AlertTriangle, CheckCircle, Archive } from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

const API = 'http://localhost:8000/api';

const VAR_COLORS = {
    LINK: '#d4a853',
    FIRSTNAME: '#5b9bd5',
    LASTNAME: '#7ec8a0',
    EMAILNAME: '#c27ba0',
};

const highlightVars = (text) => {
    if (!text) return text;
    return text.replace(/\{\{(\w+)\}\}/g, (match, name) => {
        const color = VAR_COLORS[name.toUpperCase()] || 'var(--accent)';
        return `<span style="background:${color}22;color:${color};padding:1px 4px;border-radius:3px;font-weight:700;font-size:0.85em">{{${name}}}</span>`;
    });
};

const formatDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export default function Templates() {
    const { t } = useI18n();
    const [templates, setTemplates] = useState([]);
    const [tab, setTab] = useState('list');
    const [preview, setPreview] = useState(null);
    const [name, setName] = useState('');
    const [subject, setSubject] = useState('');
    const [body, setBody] = useState('');
    const [uploading, setUploading] = useState(false);
    const [importResult, setImportResult] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const fileRef = useRef();

    const load = () => fetch(`${API}/templates/`).then(r => r.json()).then(setTemplates).catch(() => { });
    useEffect(() => { load(); }, []);

    const createManual = async () => {
        if (!name || !subject || !body) return;
        await fetch(`${API}/templates/`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, subject, body })
        });
        setName(''); setSubject(''); setBody(''); setTab('list'); load();
    };

    const importZip = async (file) => {
        if (!file || !file.name.endsWith('.zip')) return;
        setUploading(true);
        const form = new FormData();
        form.append('file', file);
        try {
            const resp = await fetch(`${API}/templates/import-zip`, { method: 'POST', body: form });
            const data = await resp.json();
            setImportResult(data);
            load();
        } catch (e) {
            setImportResult({ error: e.message });
        } finally { setUploading(false); }
    };

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) importZip(file);
    };

    const deleteTemplate = async (id) => { if (!confirm('Удалить шаблон?')) return; await fetch(`${API}/templates/${id}`, { method: 'DELETE' }); load(); };
    const deletePack = async (packName) => {
        if (!confirm(`Удалить все шаблоны из пачки "${packName}"?`)) return;
        await fetch(`${API}/templates/pack/${encodeURIComponent(packName)}`, { method: 'DELETE' });
        load();
    };
    const viewTemplate = async (id) => setPreview(await (await fetch(`${API}/templates/${id}`)).json());

    // Group by pack
    const packs = {};
    const noPack = [];
    templates.forEach(t => {
        if (t.pack_name) {
            (packs[t.pack_name] = packs[t.pack_name] || []).push(t);
        } else {
            noPack.push(t);
        }
    });

    const hasLink = (vars) => (vars || []).includes('LINK');
    const hasPersonalization = (vars) => (vars || []).some(v => ['FIRSTNAME', 'LASTNAME', 'EMAILNAME'].includes(v));

    const Tab = ({ id, icon, label }) => (
        <button onClick={() => setTab(id)} style={{
            padding: '8px 18px', borderRadius: 10, border: 'none', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: '0.78em', fontWeight: 600, letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 6,
            background: tab === id ? 'rgba(212,168,83,0.12)' : 'transparent',
            color: tab === id ? 'var(--accent)' : 'var(--text-muted)', transition: 'all 0.2s'
        }}>{icon} {label}</button>
    );

    const VarBadge = ({ name: varName }) => (
        <span style={{
            background: `${VAR_COLORS[varName] || 'var(--accent)'}22`,
            color: VAR_COLORS[varName] || 'var(--accent)',
            padding: '1px 6px', borderRadius: 4, fontSize: '0.65em', fontWeight: 700,
        }}>{`{{${varName}}}`}</span>
    );

    const TemplateCard = ({ t: tmpl }) => (
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9em' }}>{tmpl.name}</span>
                    {!hasLink(tmpl.variables) && (
                        <span className="badge badge-danger" style={{ fontSize: '0.6em' }}>
                            <AlertTriangle size={9} /> NO {'{{'}LINK{'}}'}
                        </span>
                    )}
                    {hasLink(tmpl.variables) && hasPersonalization(tmpl.variables) && (
                        <span className="badge badge-success" style={{ fontSize: '0.6em' }}>
                            <CheckCircle size={9} /> OK
                        </span>
                    )}
                </div>
                <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 3, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span>{tmpl.subject?.substring(0, 60)}{tmpl.subject?.length > 60 ? '...' : ''}</span>
                    <span>·</span>
                    {(tmpl.variables || []).map(v => <VarBadge key={v} name={v} />)}
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.9em' }}>· {formatDate(tmpl.created_at)}</span>
                </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-sm" onClick={() => viewTemplate(tmpl.id)}><Eye size={13} /></button>
                <button className="btn btn-sm btn-danger" onClick={() => deleteTemplate(tmpl.id)}><Trash2 size={13} /></button>
            </div>
        </div>
    );

    return (
        <div className="page">
            <h2 className="page-title"><FileText size={22} /> {t('templatesTitle')}</h2>

            <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: 'rgba(255,255,255,0.02)', borderRadius: 12, padding: 4 }}>
                <Tab id="list" label={t('templatesTitle')} />
                <Tab id="create" icon={<Plus size={13} />} label={t('createTemplate')} />
                <Tab id="import" icon={<Archive size={13} />} label="ZIP Import" />
            </div>

            {/* Variable legend */}
            <div style={{
                padding: '8px 14px', borderRadius: 10, marginBottom: 14,
                background: 'rgba(212,168,83,0.04)', border: '1px solid rgba(212,168,83,0.1)',
                fontSize: '0.72em', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap'
            }}>
                {Object.entries(VAR_COLORS).map(([v, c]) => (
                    <span key={v} style={{ color: c, fontWeight: 700 }}>{`{{${v}}}`}</span>
                ))}
                <span style={{ color: 'var(--text-muted)' }}>— обязательно {'{{'}LINK{'}}'}  + минимум 1 персонализация</span>
            </div>

            {/* List tab */}
            {tab === 'list' && (
                templates.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                        <FileText size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />
                        Нет шаблонов. Загрузите ZIP архив или создайте вручную.
                    </div>
                ) : (
                    <div>
                        {/* Packed templates */}
                        {Object.entries(packs).map(([packName, packTemplates]) => (
                            <div key={packName} style={{ marginBottom: 16 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                    <Package size={14} style={{ color: 'var(--accent)' }} />
                                    <span style={{ fontWeight: 700, fontSize: '0.88em', color: 'var(--accent)' }}>{packName}</span>
                                    <span className="badge badge-accent" style={{ fontSize: '0.6em' }}>{packTemplates.length} шаблонов</span>
                                    <button className="btn btn-sm btn-danger" onClick={() => deletePack(packName)} style={{ marginLeft: 'auto' }}>
                                        <Trash2 size={11} /> Удалить пачку
                                    </button>
                                </div>
                                {packTemplates.map(tmpl => <TemplateCard key={tmpl.id} t={tmpl} />)}
                            </div>
                        ))}
                        {/* Standalone templates */}
                        {noPack.length > 0 && (
                            <div>
                                {Object.keys(packs).length > 0 && (
                                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 }}>
                                        ОТДЕЛЬНЫЕ ШАБЛОНЫ
                                    </div>
                                )}
                                {noPack.map(tmpl => <TemplateCard key={tmpl.id} t={tmpl} />)}
                            </div>
                        )}
                    </div>
                )
            )}

            {/* Create tab */}
            {tab === 'create' && (
                <div className="card">
                    <div className="card-title">{t('createTemplate')}</div>
                    <div className="form-group">
                        <label className="form-label">Название</label>
                        <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="Offer USA #1..." />
                    </div>
                    <div className="form-group">
                        <label className="form-label">
                            Тема письма
                            <span style={{ fontSize: '0.8em', color: 'var(--text-muted)', marginLeft: 8 }}>
                                Используйте {`{{EMAILNAME}}`}, {`{{FIRSTNAME}}`}, {`{{LINK}}`}
                            </span>
                        </label>
                        <input className="form-input" value={subject} onChange={e => setSubject(e.target.value)}
                            placeholder="Hey {{EMAILNAME}}, check this out" />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Тело (HTML)</label>
                        <textarea className="form-input" value={body} onChange={e => setBody(e.target.value)}
                            placeholder={'<p>Hi {{FIRSTNAME}},</p>\n<p>Click here: {{LINK}}</p>'} rows={10} />
                    </div>
                    {/* Live variable detection */}
                    {(subject || body) && (
                        <div style={{ marginBottom: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
                            <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>Переменные:</span>
                            {['LINK', 'FIRSTNAME', 'LASTNAME', 'EMAILNAME'].filter(v =>
                                (subject + ' ' + body).toUpperCase().includes('{{' + v + '}}')
                            ).map(v => <VarBadge key={v} name={v} />)}
                        </div>
                    )}
                    <button className="btn btn-primary" onClick={createManual}>{t('saveTemplate')}</button>
                </div>
            )}

            {/* ZIP Import tab */}
            {tab === 'import' && (
                <div className="card">
                    <div className="card-title"><Archive size={13} style={{ marginRight: 6 }} /> Импорт ZIP пачки</div>

                    <div style={{
                        padding: '10px 14px', borderRadius: 10, marginBottom: 16,
                        background: 'rgba(212,168,83,0.05)', border: '1px solid rgba(212,168,83,0.1)',
                        fontSize: '0.75em', color: 'var(--text-secondary)', lineHeight: 1.8,
                    }}>
                        <strong style={{ color: 'var(--accent)' }}>Формат ZIP:</strong><br />
                        <code>manifest.json</code> + <code>templates/*.html</code><br />
                        Или просто <code>.html</code> файлы (первая строка = <code>Subject: ...</code>)
                    </div>

                    <div
                        className={`upload-zone ${dragOver ? 'dragover' : ''}`}
                        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={handleDrop}
                        onClick={() => fileRef.current?.click()}
                    >
                        <Upload size={28} />
                        <p>Перетащите .zip файл или нажмите для выбора</p>
                        <span>manifest.json + templates/*.html</span>
                    </div>
                    <input ref={fileRef} type="file" accept=".zip" hidden onChange={e => e.target.files[0] && importZip(e.target.files[0])} />

                    {uploading && (
                        <div style={{ textAlign: 'center', padding: 20, color: 'var(--accent)' }}>
                            Распаковка и импорт...
                        </div>
                    )}

                    {importResult && (
                        <div className="card" style={{ marginTop: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                <div className="card-title" style={{ margin: 0 }}>Результат импорта</div>
                                <button className="btn btn-sm" onClick={() => setImportResult(null)}><X size={12} /></button>
                            </div>
                            {importResult.error ? (
                                <div style={{ color: 'var(--danger)', fontSize: '0.85em' }}>{importResult.error}</div>
                            ) : (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                    <div style={{ textAlign: 'center', padding: 12, borderRadius: 8, background: 'rgba(212,168,83,0.06)' }}>
                                        <div style={{ fontSize: '1.6em', fontWeight: 700, color: 'var(--accent)' }}>{importResult.imported}</div>
                                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)' }}>ИМПОРТИРОВАНО</div>
                                    </div>
                                    <div style={{ textAlign: 'center', padding: 12, borderRadius: 8, background: 'rgba(255,255,255,0.02)' }}>
                                        <div style={{ fontSize: '1.6em', fontWeight: 700, color: 'var(--text-secondary)' }}>{importResult.pack_name}</div>
                                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)' }}>ПАЧКА</div>
                                    </div>
                                </div>
                            )}
                            {importResult.errors?.length > 0 && (
                                <div style={{ marginTop: 10, fontSize: '0.72em', color: 'var(--danger)' }}>
                                    {importResult.errors.map((e, i) => <div key={i}>⚠ {e}</div>)}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Preview modal */}
            {preview && (
                <div className="modal-overlay" onClick={() => setPreview(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <div className="card-title" style={{ margin: 0 }}>Предпросмотр — {preview.name}</div>
                            <button className="btn btn-sm" onClick={() => setPreview(null)}><X size={14} /></button>
                        </div>
                        <div style={{ fontSize: '0.82em', marginBottom: 8, color: 'var(--text-secondary)' }}>
                            <strong>Subject:</strong>{' '}
                            <span dangerouslySetInnerHTML={{ __html: highlightVars(preview.subject) }} />
                        </div>
                        {preview.variables?.length > 0 && (
                            <div style={{ marginBottom: 10, display: 'flex', gap: 6 }}>
                                {preview.variables.map(v => <VarBadge key={v} name={v} />)}
                            </div>
                        )}
                        <div style={{
                            background: 'var(--bg-secondary)', padding: 20, borderRadius: 12,
                            fontSize: '0.85em', lineHeight: 1.6, maxHeight: 400, overflow: 'auto',
                            color: 'var(--text-secondary)'
                        }} dangerouslySetInnerHTML={{ __html: highlightVars(preview.body) }} />
                        <div style={{ fontSize: '0.68em', color: 'var(--text-muted)', marginTop: 8 }}>
                            {preview.pack_name && `Пачка: ${preview.pack_name} · `}
                            {formatDate(preview.created_at)}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
