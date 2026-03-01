/**
 * Dynamic API URL — works in browser, Electron, and remote access.
 * - Electron (file://) → http://localhost:8000/api
 * - Browser localhost    → http://localhost:8000/api
 * - Browser remote IP    → http://REMOTE_IP:8000/api
 */
const isElectron = window.location.protocol === 'file:' || window.electronAPI?.isElectron;
const hostname = isElectron ? 'localhost' : window.location.hostname;
const port = 8000;
export const API = `http://${hostname}:${port}/api`;
