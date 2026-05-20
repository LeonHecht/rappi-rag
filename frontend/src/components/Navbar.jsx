import { Link, useNavigate } from 'react-router-dom';
import { useLayoutEffect, useRef, useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { APP_NAME } from '../config/appConfig';

export default function Navbar() {
  const { session } = useAuth();
  const user = session?.user;
  const navRef = useRef(null);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);
  const [tier, setTier] = useState("free");

  const fullName = user?.user_metadata?.full_name;
  const initial = fullName?.[0] || user?.email?.[0];

  useLayoutEffect(() => {
    const el = navRef.current;
    if (!el) return;

    const setVar = () => {
      const h = el.offsetHeight || 64;
      document.documentElement.style.setProperty("--navbar-h", `${h}px`);
    };

    setVar();
    const ro = new ResizeObserver(setVar);
    ro.observe(el);
    window.addEventListener("resize", setVar);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", setVar);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (!menuRef.current) return;
      if (!menuRef.current.contains(e.target)) setOpen(false);
    };
    const onEsc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  useEffect(() => {
    let active = true;
    async function fetchTier() {
      if (!user) return setTier("free");
      try {
        const mod = await import('../hooks/useApi.jsx');
        const fetcher = mod.apiFetch || mod.default || mod.useApi;
        const res = await fetcher('billing/status');
        if (!active) return;
        setTier(res?.subscription_tier || 'free');
      } catch {
        if (active) setTier('free');
      }
    }
    fetchTier();
    return () => { active = false; };
  }, [user]);

  async function handleLogout() {
    try {
      try { localStorage.removeItem('auth'); } catch { /* noop */ }
      const { supabase } = await import('../lib/supabaseClient');
      await supabase.auth.signOut();
    } catch { /* noop */ }
    setOpen(false);
    navigate('/login');
  }

  return (
    <nav ref={navRef} className="bg-white shadow-md z-30 relative">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between max-w-full">
        <Link to="/" className="flex items-center hover:opacity-80 transition">
          <span className="text-lg font-semibold tracking-tight text-gray-900">{APP_NAME}</span>
        </Link>
        <div className="space-x-4 flex items-center">
          <Link to="/search" className="text-gray-600 hover:text-gray-700">
            Buscar
          </Link>
          <Link to="/chat" className="text-gray-600 hover:text-gray-700">
            Chat
          </Link>
          <Link to="/uploads" className="text-gray-600 hover:text-gray-700">
            Subir
          </Link>
          {user ? (
            <div className="relative" ref={menuRef}>
              <button
                className="w-8 h-8 rounded-full bg-indigo-500 text-white flex items-center justify-center hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                onClick={() => setOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={open}
              >
                {initial?.toUpperCase()}
              </button>
              {open && (
                <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-xl ring-1 ring-black/5 overflow-hidden">
                  <div className="px-4 py-3 border-b">
                    <div className="font-semibold text-gray-900 line-clamp-1">{fullName}</div>
                    <div className="text-gray-600 text-xs line-clamp-1 mt-0.5">{user.email}</div>
                    <div className="mt-2 inline-flex items-center gap-1.5">
                      <span className="text-xs font-medium text-gray-600">Plan:</span>
                      <span className={
                        `px-2 py-0.5 rounded-full text-xs font-semibold ` +
                        (tier === 'free'
                          ? 'bg-gray-200 text-gray-700'
                          : tier === 'pro'
                          ? 'bg-indigo-600 text-white'
                          : tier === 'team'
                          ? 'bg-purple-600 text-white'
                          : 'bg-emerald-600 text-white'
                        )
                      }>
                        {tier.charAt(0).toUpperCase() + tier.slice(1)}
                      </span>
                    </div>
                  </div>
                  <div className="py-1">
                    <button
                      className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors font-medium"
                      onClick={handleLogout}
                    >
                      Cerrar sesion
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Link to="/login" className="text-gray-600 hover:text-gray-400">
              Login
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
