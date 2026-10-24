import { NavLink, Outlet } from "react-router-dom";
import {
  BrainCircuit,
  ChartNoAxesColumn,
  House,
  Settings2,
} from "lucide-react";
import "./AppLayout.css";

const links = [
  { to: "/", label: "Dashboard", icon: House, end: true },
  { to: "/progress", label: "My progress", icon: ChartNoAxesColumn },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

export default function AppLayout() {
  return (
    <div className="app-shell layout-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">
            <BrainCircuit size={22} />
          </span>
          <span>
            mockina<small>INTERVIEW PRACTICE</small>
          </span>
        </NavLink>
        <p className="nav-caption">WORKSPACE</p>
        <nav className="side-nav">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="note-icon">✦</span>
          <strong>Small practice. Big progress.</strong>
          <p>Build confidence one interview at a time.</p>
        </div>
        <div className="profile-mini">
          <div className="avatar">M</div>
          <div>
            <strong>Madhavi</strong>
            <small>Free workspace</small>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <span className="topbar-label">Your interview workspace</span>
          <span className="topbar-status">
            <span /> All progress saved locally
          </span>
        </header>
        <Outlet />
      </main>
      <nav className="mobile-nav">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} aria-label={label}>
            <Icon size={19} />
            <small>{label}</small>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
