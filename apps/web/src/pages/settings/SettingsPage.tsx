import { Bell, LockKeyhole, Palette, UserRound } from "lucide-react";
import { useState } from "react";
import ApiStatusBadge from "../../components/common/ApiStatusBadge";
import "./SettingsPage.css";
export default function SettingsPage() {
  const [name, setName] = useState("Madhavi");
  const [reminders, setReminders] = useState(true);
  const [theme, setTheme] = useState("Light");
  return (
    <div className="page-content settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">MAKE IT YOURS</p>
          <h1>Settings</h1>
          <p>Manage your profile and interview practice preferences.</p>
        </div>
      </div>
      <section className="card settings-section">
        <div className="settings-section-heading">
          <span>
            <UserRound />
          </span>
          <div>
            <h2>Profile</h2>
            <p>Your personal workspace details.</p>
          </div>
        </div>
        <label className="field-label">
          Display name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field-label">
          Email address
          <input value="madhavi@example.com" readOnly />
        </label>
        <p className="settings-help">
          Profile changes in this starter are local to the page and are not
          saved to the backend.
        </p>
      </section>
      <section className="card settings-section">
        <div className="settings-section-heading">
          <span>
            <Bell />
          </span>
          <div>
            <h2>Reminders</h2>
            <p>Choose how you want to stay on track.</p>
          </div>
        </div>
        <div className="setting-row">
          <div>
            <strong>Practice reminders</strong>
            <p>Receive gentle reminders to keep practicing.</p>
          </div>
          <button
            className={`toggle ${reminders ? "on" : ""}`}
            role="switch"
            aria-checked={reminders}
            onClick={() => setReminders((v) => !v)}
          >
            <span />
          </button>
        </div>
      </section>
      <section className="card settings-section">
        <div className="settings-section-heading">
          <span>
            <Palette />
          </span>
          <div>
            <h2>Appearance</h2>
            <p>Choose the look that feels right for you.</p>
          </div>
        </div>
        <div className="theme-options">
          {["Light", "System"].map((option) => (
            <button
              key={option}
              className={`theme-option ${theme === option ? "selected" : ""}`}
              onClick={() => setTheme(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </section>
      <section className="card settings-section">
        <div className="settings-section-heading">
          <span>
            <LockKeyhole />
          </span>
          <div>
            <h2>Privacy & data</h2>
            <p>Your interview practice should feel like a safe space.</p>
          </div>
        </div>
        <p className="settings-help">
          Connect this section to your backend's account, data-retention, and
          session-deletion settings before production.
        </p>
      </section>
      <section className="card settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>Server</h2>
            <p>Connection to the Mockina API.</p>
          </div>
        </div>
        <ApiStatusBadge />
      </section>
      <button
        className="btn btn-primary"
        onClick={() =>
          window.alert(
            "Settings are currently local demo state. Add an API save action before production.",
          )
        }
      >
        Save preferences
      </button>
    </div>
  );
}
