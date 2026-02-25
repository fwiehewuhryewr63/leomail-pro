import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { I18nProvider } from './i18n/I18nContext';
import { API } from './api';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Birth from './pages/Birth';
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

  useEffect(() => {
    const check = () =>
      fetch(`${API}/health`)
        .then(r => r.json())
        .then(() => setStatus('online'))
        .catch(() => setStatus('offline'));
    check();
    const interval = setInterval(check, 120000);
    return () => clearInterval(interval);
  }, []);

  return (
    <I18nProvider>
      <Router>
        <div className="app-container">
          <Sidebar status={status} />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/birth" element={<Birth />} />
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
        </div>
      </Router>
    </I18nProvider>
  );
}

export default App;
