import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route } from 'react-router-dom';
import { I18nProvider } from './i18n/I18nContext';
import { ToastProvider } from './components/Toast';
import CommandPalette from './components/CommandPalette';
import { API } from './api';
import Sidebar from './components/Sidebar';
import Titlebar from './components/Titlebar';
import Dashboard from './pages/Dashboard';
import Birth from './pages/Birth';
import Warmup from './pages/Warmup';
import Campaigns from './pages/Campaigns';
import CampaignDetail from './pages/CampaignDetail';
import Farms from './pages/Farms';
import Accounts from './pages/Accounts';
import Databases from './pages/Databases';
import Templates from './pages/Templates';
import Links from './pages/Links';
import Names from './pages/Names';
import Threads from './pages/Threads';

import Logs from './pages/Logs';
import Settings from './pages/Settings';
import Proxies from './pages/Proxies';

function App() {
  const [status, setStatus] = useState('offline');
  const [cmdOpen, setCmdOpen] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState(false);

  useEffect(() => {
    const check = () =>
      fetch(`${API}/health`)
        .then(r => r.json())
        .then(() => setStatus('online'))
        .catch(() => setStatus('offline'));
    check();
    const interval = setInterval(check, 120000);

    // Auto-check for updates (5s delay so UI loads first)
    const updateTimer = setTimeout(() => {
      fetch(`${API}/update/check`)
        .then(r => r.json())
        .then(d => { if (d.update_available) setUpdateAvailable(true); })
        .catch(() => { });
    }, 5000);

    return () => { clearInterval(interval); clearTimeout(updateTimer); };
  }, []);

  // ⌘K / Ctrl+K — Command Palette
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <I18nProvider>
      <ToastProvider>
        <Router>
          <Titlebar />
          <div className="app-container" style={{ paddingTop: window.electronAPI?.isElectron ? 32 : 0 }}>
            <Sidebar status={status} updateAvailable={updateAvailable} />
            <main className="main-content">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/birth" element={<Birth />} />
                <Route path="/warmup" element={<Warmup />} />
                <Route path="/campaigns" element={<Campaigns />} />
                <Route path="/campaigns/:id" element={<CampaignDetail />} />
                <Route path="/proxies" element={<Proxies />} />
                <Route path="/farms" element={<Farms />} />
                <Route path="/accounts" element={<Accounts />} />
                <Route path="/databases" element={<Databases />} />
                <Route path="/templates" element={<Templates />} />
                <Route path="/links" element={<Links />} />
                <Route path="/names" element={<Names />} />
                <Route path="/threads" element={<Threads />} />

                <Route path="/logs" element={<Logs />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </main>
            <CommandPalette isOpen={cmdOpen} onClose={() => setCmdOpen(false)} />
          </div>
        </Router>
      </ToastProvider>
    </I18nProvider>
  );
}

export default App;
