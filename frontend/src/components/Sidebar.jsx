import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard, Baby, Flame, Send, Database, Users, UserCircle,
    FileText, Monitor, Settings, Link, Globe, Shield, Boxes,
    Terminal, Rocket
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

export default function Sidebar({ status }) {
    const { t, lang, toggleLang } = useI18n();

    const sections = [
        {
            label: t('lifecycle'),
            items: [
                { to: '/', icon: LayoutDashboard, label: t('dashboard'), end: true },
                { to: '/birth', icon: Baby, label: t('birth') },
                { to: '/campaigns', icon: Rocket, label: 'Кампании' },
                { to: '/work', icon: Send, label: t('work') },
            ]
        },
        {
            label: t('resources'),
            items: [
                { to: '/proxies', icon: Shield, label: t('proxies') },
                { to: '/farms', icon: Boxes, label: t('farms') },
                { to: '/accounts', icon: Users, label: t('accounts') },
                { to: '/templates', icon: FileText, label: t('templates') },
                { to: '/links', icon: Link, label: t('links') },
                { to: '/databases', icon: Database, label: 'Базы получателей' },
                { to: '/names', icon: UserCircle, label: 'Имена (рег.)' },
            ]
        },
        {
            label: t('system'),
            items: [
                { to: '/threads', icon: Terminal, label: t('threads') },
                { to: '/logs', icon: Monitor, label: t('logs') },
                { to: '/settings', icon: Settings, label: t('settings') },
            ]
        }
    ];

    return (
        <div className="sidebar">
            <div className="sidebar-logo">
                <h1>LEOMAIL<span>BLITZ PIPELINE v4.0</span></h1>
            </div>

            <div className="lang-toggle" onClick={toggleLang}>
                <Globe size={14} style={{ color: 'var(--accent)' }} />
                <span style={{ fontSize: '0.82em', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {lang === 'ru' ? 'RU' : 'EN'}
                </span>
                <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>
                    → {lang === 'ru' ? 'EN' : 'RU'}
                </span>
            </div>

            <nav className="sidebar-nav">
                {sections.map((section, si) => (
                    <div key={si}>
                        <div className="section-label">{section.label}</div>
                        {section.items.map((item) => (
                            <NavLink key={item.to} to={item.to}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                end={item.end}>
                                <item.icon size={17} />
                                <span>{item.label}</span>
                            </NavLink>
                        ))}
                    </div>
                ))}
            </nav>

            <div className="sidebar-footer">
                <div className={`status-dot ${status === 'online' ? 'online' : ''}`} />
                <span>{status === 'online' ? t('engineOnline') : t('engineOffline')}</span>
            </div>
        </div>
    );
}
