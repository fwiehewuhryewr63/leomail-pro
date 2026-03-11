import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard, Baby, Flame, Rocket,
    Shield, FileText, Users, Boxes, Settings,
    Link, Database, UserCircle, Terminal, Monitor,
    ScanSearch
} from 'lucide-react';

const NAV_SECTIONS = [
    {
        title: 'Control',
        items: [
            { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
            { to: '/birth', icon: Baby, label: 'Autoreg' },
            { to: '/validator', icon: ScanSearch, label: 'Validator' },
        ],
    },
    {
        title: 'Delivery',
        items: [
            { to: '/warmup', icon: Flame, label: 'Warm-up' },
            { to: '/campaigns', icon: Rocket, label: 'Campaigns' },
        ],
    },
    {
        title: 'Assets',
        items: [
            { to: '/farms', icon: Boxes, label: 'Farms' },
            { to: '/accounts', icon: Users, label: 'Accounts' },
            { to: '/names', icon: UserCircle, label: 'Names' },
            { to: '/proxies', icon: Shield, label: 'Proxies' },
            { to: '/templates', icon: FileText, label: 'Templates' },
            { to: '/links', icon: Link, label: 'Links' },
            { to: '/databases', icon: Database, label: 'Recipients' },
        ],
    },
    {
        title: 'System',
        items: [
            { to: '/threads', icon: Terminal, label: 'Threads' },
            { to: '/logs', icon: Monitor, label: 'Logs' },
            { to: '/settings', icon: Settings, label: 'Settings' },
        ],
    },
];

export default function Sidebar({ status, updateAvailable }) {
    return (
        <div className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <img src="/logo.png" alt="Leomail" className="sidebar-logo-img" />
                <div className="sidebar-brand-wrap">
                    <span className="sidebar-brand">Leomail</span>
                    <span className="sidebar-brand-sub">Mail operations suite</span>
                </div>
            </div>

            {/* Nav */}
            <nav className="sidebar-nav">
                {NAV_SECTIONS.map(section => (
                    <div key={section.title} className="nav-section">
                        <div className="section-label">{section.title}</div>
                        {section.items.map(item => (
                            <NavLink key={item.to} to={item.to}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                end={item.end}>
                                <span className="nav-icon-wrap">
                                    <item.icon size={17} />
                                </span>
                                <span className="nav-label">{item.label}</span>
                                {item.label === 'Settings' && updateAvailable && (
                                    <span className="nav-update-dot" />
                                )}
                            </NavLink>
                        ))}
                    </div>
                ))}
            </nav>

            {/* Footer */}
            <div className="sidebar-footer">
                <div className={`status-dot ${status === 'online' ? 'online' : ''}`} />
                <div className="sidebar-footer-copy">
                    <span className="sidebar-footer-title">{status === 'online' ? 'Connected' : 'Offline'}</span>
                    <span className="sidebar-footer-sub">{status === 'online' ? 'API heartbeat healthy' : 'Backend unavailable'}</span>
                </div>
            </div>
        </div>
    );
}
