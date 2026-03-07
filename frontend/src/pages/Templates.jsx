import React, { useState, useEffect, useRef } from 'react';
import { FileText, Plus, Trash2, Eye, X, Upload, Package, AlertTriangle, CheckCircle, Archive } from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { API } from '../api';

const VAR_COLORS = {
    LINK: '#10B981',
    USERNAME: '#06B6D4',
    NAME: '#F59E0B',
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
    return d.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: '2-digit' });
};

export default function Templates() {
    const { t: _T } = useI18n();
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
        } catch (err) {
            setImportResult({ error: err.message });
        } finally { setUploading(false); }
    };

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) importZip(file);
    };

    const deleteTemplate = async (id) => { if (!confirm('Delete template?')) return; await fetch(`${API}/templates/${id}`, { method: 'DELETE' }); load(); };
    const deletePack = async (packName) => {
        if (!confirm(`Delete all templates from pack "${packName}"?`)) return;
        await fetch(`${API}/templates/pack/${encodeURIComponent(packName)}`, { method: 'DELETE' });
        load();
    };
    const viewTemplate = async (id) => setPreview(await (await fetch(`${API}/templates/${id}`)).json());

    // Group by pack
    const packs = {};
    const noPack = [];
    templates.forEach(tmpl => {
        if (tmpl.pack_name) {
            (packs[tmpl.pack_name] = packs[tmpl.pack_name] || []).push(tmpl);
        } else {
            noPack.push(tmpl);
        }
    });

    const hasLink = (vars) => (vars || []).includes('LINK');
    const hasPersonalization = (vars) => (vars || []).some(v => ['USERNAME', 'NAME', 'FIRSTNAME', 'EMAILNAME'].includes(v));

    const VarBadge = ({ name: varName }) => (
        <span style={{
            background: `${VAR_COLORS[varName] || 'var(--accent)'}22`,
            color: VAR_COLORS[varName] || 'var(--accent)',
            padding: '1px 6px', borderRadius: 4, fontSize: '0.65em', fontWeight: 700,
        }}>{`{{${varName}}}`}</span>
    );

    const totalTemplates = templates.length;
    const totalPacks = Object.keys(packs).length;
    const allVars = new Set();
    templates.forEach(tmpl => (tmpl.variables || []).forEach(v => allVars.add(v)));

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div style={{ fontSize: '0.6em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>RESOURCES / TEMPLATES</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={22} /> Templates
                </h2>
                <div style={{ display: 'flex', gap: 6 }}>
                    {[
                        { id: 'list', label: 'List', icon: <FileText size={13} /> },
                        { id: 'create', label: 'Create', icon: <Plus size={13} /> },
                        { id: 'import', label: 'ZIP Import', icon: <Archive size={13} /> },
                    ].map(tb => (
                        <button key={tb.id} onClick={() => setTab(tb.id)} style={{
                            padding: '7px 16px', borderRadius: 20, border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                            fontSize: '0.78em', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5,
                            background: tab === tb.id ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.03)',
                            color: tab === tb.id ? '#10B981' : 'var(--text-muted)', transition: 'all 0.2s',
                        }}>{tb.icon} {tb.label}</button>
                    ))}
                </div>
            </div>

            {/* ═══ STAT CARDS ═══ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
                {[
                    { label: 'TEMPLATES', value: totalTemplates, color: '#10B981' },
                    { label: 'PACKS', value: totalPacks, color: '#06B6D4' },
                    { label: 'VARIABLES USED', value: allVars.size, color: '#F59E0B' },
                ].map(s => (
                    <div key={s.label} className="card" style={{ padding: '14px 18px', borderLeft: `3px solid ${s.color}` }}>
                        <div style={{ fontSize: '1.6em', fontWeight: 900, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: '0.68em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* ═══ VARIABLE REFERENCE BAR ═══ */}
            <div style={{
                padding: '8px 14px', borderRadius: 10, marginBottom: 16,
                background: 'rgba(16,185,129,0.03)', border: '1px solid rgba(16,185,129,0.1)',
                fontSize: '0.72em', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'
            }}>
                {Object.entries(VAR_COLORS).map(([v, c]) => (
                    <span key={v} style={{
                        background: `${c}22`, color: c, padding: '2px 8px', borderRadius: 4, fontWeight: 700, fontSize: '0.9em',
                    }}>{`{{${v}}}`}</span>
                ))}
                <span style={{ color: 'var(--text-muted)', fontSize: '0.92em' }}>— required {'{{'}LINK{'}}'}  + {'{{'}USERNAME{'}}'}  or {'{{'}NAME{'}}'}  for personalization</span>
            </div>

            {/* ═══ LIST TAB ═══ */}
            {tab === 'list' && (
                templates.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                        <Package size={40} style={{ opacity: 0.15, marginBottom: 12 }} />
                        <div style={{ fontSize: '1em', fontWeight: 700, marginBottom: 4 }}>No Templates</div>
                        <div style={{ fontSize: '0.82em' }}>Upload a ZIP archive or create manually</div>
                    </div>
                ) : (
                    <div>
                        {/* Packed templates */}
                        {Object.entries(packs).map(([packName, packTemplates]) => (
                            <div key={packName} style={{ marginBottom: 20 }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
                                    padding: '8px 14px', background: 'rgba(16,185,129,0.03)', borderRadius: 8,
                                }}>
                                    <Package size={15} style={{ color: '#10B981' }} />
                                    <span style={{ fontWeight: 700, fontSize: '0.9em', color: '#10B981' }}>{packName}</span>
                                    <span style={{
                                        padding: '2px 8px', borderRadius: 4, fontSize: '0.68em', fontWeight: 700,
                                        background: 'rgba(16,185,129,0.12)', color: '#10B981',
                                    }}>{packTemplates.length} templates</span>
                                    <button className="btn btn-sm btn-danger" onClick={() => deletePack(packName)}
                                        style={{ marginLeft: 'auto', borderRadius: 16, padding: '4px 12px', fontSize: '0.75em' }}>
                                        <Trash2 size={11} /> Delete Pack
                                    </button>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                                    {packTemplates.map(tmpl => (
                                        <TemplateGridCard key={tmpl.id} tmpl={tmpl} onView={viewTemplate} onDelete={deleteTemplate}
                                            hasLink={hasLink} hasPersonalization={hasPersonalization} formatDate={formatDate} />
                                    ))}
                                </div>
                            </div>
                        ))}
                        {/* Standalone */}
                        {noPack.length > 0 && (
                            <div>
                                {totalPacks > 0 && (
                                    <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
                                        STANDALONE TEMPLATES
                                    </div>
                                )}
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                                    {noPack.map(tmpl => (
                                        <TemplateGridCard key={tmpl.id} tmpl={tmpl} onView={viewTemplate} onDelete={deleteTemplate}
                                            hasLink={hasLink} hasPersonalization={hasPersonalization} formatDate={formatDate} />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )
            )}

            {/* ═══ CREATE TAB ═══ */}
            {tab === 'create' && (
                <div className="card" style={{ padding: '20px 24px' }}>
                    <div style={{ fontSize: '0.9em', fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Plus size={16} style={{ color: '#10B981' }} /> Create Template
                    </div>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Name</label>
                        <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="Offer USA #1..." style={{ marginTop: 4 }} />
                    </div>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                            Subject Line
                            <span style={{ fontSize: '0.9em', color: 'var(--text-muted)', marginLeft: 8, fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                                Use {`{{LINK}}`}, {`{{USERNAME}}`}, {`{{NAME}}`}
                            </span>
                        </label>
                        <input className="form-input" value={subject} onChange={e => setSubject(e.target.value)}
                            placeholder="Hey {{USERNAME}}, check this out" style={{ marginTop: 4 }} />
                    </div>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Body (HTML)</label>
                        <textarea className="form-input" value={body} onChange={e => setBody(e.target.value)}
                            placeholder={'<p>Hi {{NAME}},</p>\n<p>Click here: {{LINK}}</p>'} rows={10}
                            style={{ marginTop: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85em' }} />
                    </div>
                    {(subject || body) && (
                        <div style={{ marginBottom: 14, display: 'flex', gap: 6, alignItems: 'center' }}>
                            <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>Variables:</span>
                            {['LINK', 'USERNAME', 'NAME'].filter(v =>
                                (subject + ' ' + body).toUpperCase().includes('{{' + v + '}}')
                            ).map(v => <VarBadge key={v} name={v} />)}
                        </div>
                    )}
                    <button className="btn btn-primary" onClick={createManual}
                        style={{ borderRadius: 20, padding: '8px 20px', fontSize: '0.82em' }}>
                        <CheckCircle size={14} /> Save Template
                    </button>
                </div>
            )}

            {/* ═══ ZIP IMPORT TAB ═══ */}
            {tab === 'import' && (
                <div className="card" style={{ padding: '20px 24px' }}>
                    <div style={{ fontSize: '0.9em', fontWeight: 700, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Archive size={16} style={{ color: '#10B981' }} /> ZIP Import
                    </div>

                    <div style={{
                        padding: '10px 14px', borderRadius: 10, marginBottom: 16,
                        background: 'rgba(16,185,129,0.03)', border: '1px solid rgba(16,185,129,0.08)',
                        fontSize: '0.75em', color: 'var(--text-secondary)', lineHeight: 1.8,
                    }}>
                        <strong style={{ color: '#10B981' }}>ZIP Format:</strong><br />
                        <code>manifest.json</code> + <code>templates/*.html</code><br />
                        Or just <code>.html</code> files (first line = <code>Subject: ...</code>)
                    </div>

                    <div
                        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={handleDrop}
                        onClick={() => fileRef.current?.click()}
                        style={{
                            border: `2px dashed ${dragOver ? '#10B981' : 'rgba(16,185,129,0.2)'}`,
                            borderRadius: 12, padding: '28px 14px', textAlign: 'center', cursor: 'pointer',
                            background: dragOver ? 'rgba(16,185,129,0.05)' : 'rgba(16,185,129,0.015)',
                            transition: 'all 0.2s',
                        }}
                    >
                        <Upload size={28} style={{ color: 'var(--text-muted)', marginBottom: 6 }} />
                        <p style={{ fontSize: '0.88em', color: 'var(--text-muted)', margin: '4px 0' }}>Drop .zip file here or click to browse</p>
                        <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>manifest.json + templates/*.html</span>
                    </div>
                    <input ref={fileRef} type="file" accept=".zip" hidden onChange={e => e.target.files[0] && importZip(e.target.files[0])} />

                    {uploading && (
                        <div style={{ textAlign: 'center', padding: 20, color: '#10B981', fontSize: '0.88em' }}>
                            Extracting and importing...
                        </div>
                    )}

                    {importResult && (
                        <div className="card" style={{ marginTop: 16, padding: '16px 20px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                <span style={{ fontWeight: 700, fontSize: '0.88em' }}>Import Result</span>
                                <button className="btn btn-sm" onClick={() => setImportResult(null)}><X size={12} /></button>
                            </div>
                            {importResult.error ? (
                                <div style={{ color: 'var(--danger)', fontSize: '0.85em' }}>{importResult.error}</div>
                            ) : (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                    <div style={{ textAlign: 'center', padding: 14, borderRadius: 8, background: 'rgba(16,185,129,0.06)' }}>
                                        <div style={{ fontSize: '1.6em', fontWeight: 900, color: '#10B981' }}>{importResult.imported}</div>
                                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)' }}>IMPORTED</div>
                                    </div>
                                    <div style={{ textAlign: 'center', padding: 14, borderRadius: 8, background: 'rgba(255,255,255,0.02)' }}>
                                        <div style={{ fontSize: '1.6em', fontWeight: 700, color: 'var(--text-secondary)' }}>{importResult.pack_name}</div>
                                        <div style={{ fontSize: '0.65em', color: 'var(--text-muted)' }}>PACK</div>
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

            {/* ═══ PREVIEW MODAL ═══ */}
            {preview && (
                <div className="modal-overlay" onClick={() => setPreview(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <span style={{ fontWeight: 700, fontSize: '0.92em' }}>Preview — {preview.name}</span>
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
                            {preview.pack_name && `Pack: ${preview.pack_name} · `}
                            {formatDate(preview.created_at)}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ═══ Template Grid Card Component ═══ */
function TemplateGridCard({ tmpl, onView, onDelete, hasLink, hasPersonalization, formatDate }) {
    return (
        <div className="card" style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* Name + status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, fontSize: '0.88em', flex: 1 }}>{tmpl.name}</span>
                {!hasLink(tmpl.variables) && (
                    <span style={{
                        padding: '1px 6px', borderRadius: 4, fontSize: '0.6em', fontWeight: 700,
                        background: 'rgba(239,68,68,0.12)', color: '#EF4444',
                    }}>
                        <AlertTriangle size={8} style={{ verticalAlign: 'middle' }} /> NO LINK
                    </span>
                )}
                {hasLink(tmpl.variables) && hasPersonalization(tmpl.variables) && (
                    <span style={{
                        padding: '1px 6px', borderRadius: 4, fontSize: '0.6em', fontWeight: 700,
                        background: 'rgba(34,197,94,0.12)', color: '#22C55E',
                    }}>
                        <CheckCircle size={8} style={{ verticalAlign: 'middle' }} /> OK
                    </span>
                )}
            </div>

            {/* Subject */}
            <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', lineHeight: 1.3, minHeight: 18 }}>
                {tmpl.subject?.substring(0, 55)}{tmpl.subject?.length > 55 ? '...' : ''}
            </div>

            {/* Variables */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {(tmpl.variables || []).map(v => <VarBadge key={v} name={v} />)}
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>{formatDate(tmpl.created_at)}</span>
                <div style={{ display: 'flex', gap: 3 }}>
                    <button className="btn btn-sm" onClick={() => onView(tmpl.id)} style={{ padding: '4px 6px' }}>
                        <Eye size={12} />
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => onDelete(tmpl.id)} style={{ padding: '4px 6px' }}>
                        <Trash2 size={12} />
                    </button>
                </div>
            </div>
        </div>
    );
}
