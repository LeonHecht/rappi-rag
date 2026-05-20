import { supabase } from "../lib/supabaseClient";

/**
 * Llama al endpoint de la API en /v1/{path}{params}
 * @param {string} path   Ruta tras /v1/, p.ej. "search" o "chat"
 * @param {string} params Query string, e.g. "?q=policy&space=default"
 * @returns {Promise<any>}  JSON parseado
 */
export const apiFetch = async (path, params = "", options = {}) => {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  // Normalize to avoid trailing slash that would produce URLs like //v1/...
  const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/+$/, "");

  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  return fetch(`${API_BASE}/v1/${path}${params}`, {
    ...options,
    headers,
  }).then((res) => {
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  });
};

// Back-compat named export; avoid using this name in app code to satisfy eslint-hooks
export { apiFetch as useApi };
export default apiFetch;
