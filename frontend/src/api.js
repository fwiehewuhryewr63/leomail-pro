/**
 * Dynamic API URL — works both locally and remotely.
 * When accessed via localhost → API = http://localhost:8000/api
 * When accessed via external IP → API = http://EXTERNAL_IP:8000/api
 */
const hostname = window.location.hostname;
const port = 8000;
export const API = `http://${hostname}:${port}/api`;
