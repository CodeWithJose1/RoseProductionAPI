import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  BarChart3, CalendarRange, Flower2, Home, LayoutGrid, LogOut, Map, Menu, Scissors, Sprout, TrendingUp, X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';

export const NAV_SECTIONS = [
  {
    title: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', icon: Home, end: true },
      { to: '/analytics', label: 'Production analysis', icon: BarChart3 },
    ],
  },
  {
    title: 'Farm structure',
    items: [
      { to: '/farms', label: 'Farms', icon: Map },
      { to: '/lots', label: 'Lots', icon: LayoutGrid },
      { to: '/varieties', label: 'Rose varieties', icon: Flower2 },
      { to: '/crops', label: 'Crops', icon: Sprout },
    ],
  },
  {
    title: 'Production',
    items: [
      { to: '/seasons', label: 'Seasons', icon: CalendarRange },
      { to: '/harvests', label: 'Harvests', icon: Scissors },
      { to: '/forecasts', label: 'Forecasts', icon: TrendingUp },
    ],
  },
];

const ALL_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);

function currentTitle(pathname) {
  const match = ALL_ITEMS
    .filter((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to)))
    .sort((a, b) => b.to.length - a.to.length)[0];
  return match?.label || 'Rose Production';
}

export function Layout() {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    document.title = `${currentTitle(location.pathname)} · Rose Production`;
  }, [location.pathname]);

  return (
    <div className={`app-shell${open ? ' nav-open' : ''}`}>
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><Flower2 size={22} /></span>
          <div>
            <strong>Rose Production</strong>
            <span>Management &amp; Forecasting</span>
          </div>
          <button type="button" className="icon-button sidebar-close" onClick={() => setOpen(false)} aria-label="Close menu">
            <X size={18} />
          </button>
        </div>
        <nav>
          {NAV_SECTIONS.map((section) => (
            <div className="nav-section" key={section.title}>
              <span className="nav-heading">{section.title}</span>
              {section.items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                  <item.icon size={18} aria-hidden="true" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span>RoseProductionDB · MySQL 8</span>
        </div>
      </aside>
      <div className="sidebar-scrim" onClick={() => setOpen(false)} aria-hidden="true" />

      <div className="main-area">
        <header className="topbar">
          <button type="button" className="icon-button menu-toggle" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <div className="topbar-title">
            <span className="muted">Rose Production</span>
            <span aria-hidden="true" className="muted">/</span>
            <strong>{currentTitle(location.pathname)}</strong>
          </div>
          <div className="topbar-actions">
            <span className="status-pill" title="Signed in with a secure session">
              <span className="status-dot" aria-hidden="true" /> Connected
            </span>
            <button type="button" className="btn btn-ghost" onClick={logout}>
              <LogOut size={16} aria-hidden="true" /> Sign out
            </button>
          </div>
        </header>
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
